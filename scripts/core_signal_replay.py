"""Deterministic, score-free replay for CORE_SIGNAL_VALIDATION.

The replay consumes only historical raw K, historical corporate-action
events, and the historical benchmark index.  It deliberately does not load
sector membership.  A neutral sector evidence sentinel is supplied only
because the frozen V1 evaluator requires a structurally complete sector
record; all sector fields and the 85-score result are excluded from the core
projection and hashes.  The sector differential tests prove that this cannot
change core signal identity or levels.

This module does not calculate returns, win rate, MFE/MAE, P&L, expectancy, or
profit factor, and it never reads final OOS data.
"""

from __future__ import annotations

import argparse
import copy
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import json
import math
import os
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from a_platform_breakout import (
    ACCELERATION_OVEREXTENDED,
    GAIN_EXHAUSTED,
    INSUFFICIENT_DATA,
    LEGACY_SPEC,
    MATCHED_REJECTED,
    MISSING_SECTOR_EVIDENCE,
    NOT_MATCHED,
    QUALIFIED_LEGACY_BASELINE,
    REJECTED_CLOSE_TOO_LOW,
    REJECTED_NO_SUPPORT,
    REJECTED_OVERHANG_RR,
    REJECTED_RR,
    REJECTED_STOP_DISTANCE,
    SETUP_ID,
    STRATEGY_SPEC_SHA256,
    STRATEGY_VERSION,
    evaluate_universe,
)
from generation_contract import (
    ASIA_SHANGHAI,
    GenerationInputManifest,
    IndexManifest,
    KlineManifest,
    POINT_IN_TIME,
    QuoteSnapshotManifest,
    RunContext,
    SectorManifest,
    UniverseManifest,
)
from historical_validation_layers import CORE_SIGNAL_VALIDATION
from validation_contract import PROTOCOL_SEMANTIC_SHA256, ReplayPlan


DATASET_SCHEMA_VERSION = "CORE_SIGNAL_VALIDATION_DATASET_MANIFEST_V1"
QUARTER_END_DATASET_VERSION = "core-signal-hithink-quarter-end-2023-06-to-2026-08-v1"
CONTINUOUS_DATASET_VERSION = "core-signal-hithink-continuous-2023-06-30-to-2026-08-28-v1"
VALIDATION_START = "2023-06-30"
VALIDATION_END = "2026-08-28"
BENCHMARK_SYMBOL = "000001.SH"
BENCHMARK_MANIFEST_SYMBOL = BENCHMARK_SYMBOL.lower()
CORE_ADJUSTMENT_SEMANTICS = "HISTORICAL_T_ANCHOR_PRICE_RAW_VOLUME"
UNVERIFIED_SECTOR_NAME = "__UNVERIFIED_SINA_SECTOR__"
ACQUISITION_DATE = "2026-08-28"
ACQUISITION_AT_BJT = "2026-08-28T16:20:26+08:00"
REPLAY_RETRIEVED_AT_BJT = "2026-08-28T17:00:00+08:00"
CHUNK_SIZE = 250
MINIMUM_BARS = 120
LOOKBACK_BARS = 260
A_CONDITIONS = tuple(item["audit"] for item in LEGACY_SPEC["a_match"]["conditions_in_order"])
REQUIRED_RAW_INPUTS = (
    ("daily_k", "daily_k.parquet"),
    ("adjustment_factors", "adjustment_factors.parquet"),
    ("benchmark_index_2023", "index_000001_SH_2023.json"),
    ("benchmark_index_2024", "index_000001_SH_2024.json"),
    ("benchmark_index_2025", "index_000001_SH_2025.json"),
    ("benchmark_index_2026", "index_000001_SH_2026.json"),
)

CORE_PROJECTION_FIELDS = (
    "as_of_date",
    "signal_date",
    "earliest_execution_date",
    "symbol",
    "setup_id",
    "status",
    "matched_conditions",
    "failed_conditions",
    "reject_reasons",
    "support",
    "trigger",
    "stop",
    "target",
    "target_type",
    "risk",
    "rr",
    "level_plan",
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _date_from_ms(value: int) -> str:
    return pd.Timestamp(int(value), unit="ms", tz="UTC").tz_convert(ASIA_SHANGHAI).date().isoformat()


def _ms_from_date(value: str) -> int:
    return int(pd.Timestamp(value, tz=ASIA_SHANGHAI).timestamp() * 1000)


def _as_float(value: Any, *, default: float | None = None) -> float:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        if default is not None:
            return default
        raise ValueError("numeric field is null")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("numeric field is not finite")
    return result


def _index_change(index_bars: list[dict[str, Any]]) -> float:
    if len(index_bars) < 6:
        raise ValueError("index needs at least six bars for chg5")
    closes = [_as_float(bar["close"]) for bar in index_bars]
    if closes[-6] == 0:
        raise ValueError("index close[-6] must be non-zero")
    return (closes[-1] / closes[-6] - 1.0) * 100.0


def _quarter_end_signal_dates(raw_date_ms: np.ndarray, index_dates: set[str]) -> list[str]:
    unique_dates = sorted(
        {
            _date_from_ms(int(value))
            for value in np.unique(raw_date_ms)
            if VALIDATION_START <= _date_from_ms(int(value)) <= VALIDATION_END
        }
    )
    by_quarter: dict[tuple[int, int], str] = {}
    for value in unique_dates:
        if value in index_dates:
            parsed = date.fromisoformat(value)
            quarter = (parsed.month - 1) // 3 + 1
            by_quarter[(parsed.year, quarter)] = value
    selected = [value for _, value in sorted(by_quarter.items()) if value >= "2023-06-01"]
    latest = max((value for value in unique_dates if value in index_dates), default=None)
    if latest is not None and latest not in selected:
        selected.append(latest)
    return selected


def _continuous_signal_dates(index_dates: dict[str, int]) -> list[str]:
    """Use every benchmark/XSHG session inside the frozen validation bounds."""

    return [
        value
        for value in sorted(index_dates)
        if VALIDATION_START <= value <= VALIDATION_END
    ]


def _load_index(raw_dir: Path) -> tuple[dict[str, int], list[dict[str, Any]], dict[str, Any]]:
    files = sorted(raw_dir.glob("index_000001_SH_20*.json"))
    if not files:
        raise RuntimeError("no benchmark index JSON files found")
    items: list[dict[str, Any]] = []
    file_metadata: list[dict[str, Any]] = []
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("code") != 0:
            raise RuntimeError(f"benchmark index request failed in {path.name}")
        year_items = (payload.get("data") or {}).get("item") or []
        if not year_items:
            raise RuntimeError(f"benchmark index file is empty: {path.name}")
        items.extend(year_items)
        file_metadata.append({
            "path": path.as_posix(),
            "bytes": path.stat().st_size,
            "sha256": file_sha256(path),
        })
    by_ms: dict[int, dict[str, Any]] = {}
    for item in items:
        date_ms = int(item["date_ms"])
        if date_ms in by_ms:
            raise RuntimeError(f"duplicate benchmark date_ms: {date_ms}")
        by_ms[date_ms] = item
    ordered = [by_ms[key] for key in sorted(by_ms)]
    dates = {_date_from_ms(int(item["date_ms"])): int(item["date_ms"]) for item in ordered}
    bars = [
        {
            "date": _date_from_ms(int(item["date_ms"])),
            "open": _as_float(item["open_price"]),
            "high": _as_float(item["high_price"]),
            "low": _as_float(item["low_price"]),
            "close": _as_float(item["close_price"]),
            "volume": _as_float(item["volume"]),
        }
        for item in ordered
    ]
    return dates, bars, {"files": file_metadata, "row_count": len(bars)}


def _load_stock_store(raw_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    columns = [
        "thscode",
        "date_ms",
        "open_price",
        "high_price",
        "low_price",
        "close_price",
        "volume",
        "turnover",
    ]
    frame = pd.read_parquet(raw_path, columns=columns)
    if frame.duplicated(["thscode", "date_ms"]).any():
        raise RuntimeError("daily-K contains duplicate thscode/date_ms keys")
    if frame[columns[1:]].isna().any().any():
        raise RuntimeError("daily-K contains null numeric fields")
    numeric = frame[["open_price", "high_price", "low_price", "close_price", "volume", "turnover"]].to_numpy(dtype=float)
    if not np.isfinite(numeric).all():
        raise RuntimeError("daily-K contains non-finite numeric fields")
    if (frame[["open_price", "high_price", "low_price", "close_price"]] <= 0).any().any():
        raise RuntimeError("daily-K contains non-positive prices")
    if (frame["volume"] < 0).any():
        raise RuntimeError("daily-K contains negative volume")

    frame = frame.sort_values(["thscode", "date_ms"], kind="mergesort").reset_index(drop=True)
    codes = frame["thscode"].astype(str).str.strip().str.lower().to_numpy()
    date_ms = frame["date_ms"].to_numpy(dtype=np.int64)
    change_points = np.flatnonzero(codes[1:] != codes[:-1]) + 1
    starts = np.concatenate(([0], change_points))
    ends = np.concatenate((change_points, [len(frame)]))
    bounds = {codes[start]: (int(start), int(end)) for start, end in zip(starts, ends)}
    unique_date_ms = np.unique(date_ms)
    date_text = {int(value): _date_from_ms(int(value)) for value in unique_date_ms}
    store = {
        "codes": codes,
        "date_ms": date_ms,
        "date_text": date_text,
        "open": frame["open_price"].to_numpy(dtype=float),
        "high": frame["high_price"].to_numpy(dtype=float),
        "low": frame["low_price"].to_numpy(dtype=float),
        "close": frame["close_price"].to_numpy(dtype=float),
        "volume": frame["volume"].to_numpy(dtype=float),
        "turnover": frame["turnover"].to_numpy(dtype=float),
        "bounds": bounds,
    }
    frame_min = _date_from_ms(int(frame["date_ms"].min()))
    frame_max = _date_from_ms(int(frame["date_ms"].max()))
    return store, {
        "row_count": int(len(frame)),
        "symbol_count": int(frame["thscode"].nunique()),
        "min_date": frame_min,
        "max_date": frame_max,
        "duplicate_key_count": 0,
        "null_numeric_count": 0,
        "negative_volume_count": int((frame["volume"] < 0).sum()),
    }


def _load_events(raw_path: Path) -> tuple[dict[str, list[tuple[int, float, float, float, float]]], dict[str, Any]]:
    columns = [
        "thscode",
        "ex_date_ms",
        "dividend_per_share",
        "per_share_bonus",
        "allotment_ratio",
        "allotment_price",
    ]
    frame = pd.read_parquet(raw_path, columns=columns)
    events: dict[str, list[tuple[int, float, float, float, float]]] = defaultdict(list)
    for row in frame.itertuples(index=False, name=None):
        symbol, ex_date_ms, dividend, bonus, allotment, allotment_price = row
        values = (
            int(ex_date_ms),
            _as_float(dividend, default=0.0),
            _as_float(bonus, default=0.0),
            _as_float(allotment, default=0.0),
            _as_float(allotment_price, default=0.0),
        )
        events[str(symbol).strip().lower()].append(values)
    for symbol in events:
        events[symbol].sort(key=lambda item: item[0])
    return dict(events), {
        "row_count": int(len(frame)),
        "symbol_count": int(frame["thscode"].nunique()),
        "min_ex_date": _date_from_ms(int(frame["ex_date_ms"].min())),
        "max_ex_date": _date_from_ms(int(frame["ex_date_ms"].max())),
        "future_event_rows_after_dataset_end": int((frame["ex_date_ms"] > _ms_from_date("2026-08-28")).sum()),
    }


def _adjusted_bars(
    store: dict[str, Any],
    start: int,
    end: int,
    events: list[tuple[int, float, float, float, float]],
    anchor_ms: int,
) -> list[dict[str, Any]]:
    if end - start < MINIMUM_BARS:
        return []
    dates = store["date_ms"][start:end]
    arrays = {
        name: np.array(store[name][start:end], dtype=float, copy=True)
        for name in ("open", "high", "low", "close")
    }
    for ex_date_ms, dividend, bonus, allotment, allotment_price in events:
        if ex_date_ms > anchor_ms:
            break
        mask = dates < ex_date_ms
        if not np.any(mask):
            continue
        denominator = 1.0 + bonus + allotment
        if denominator <= 0 or not math.isfinite(denominator):
            raise RuntimeError(f"invalid corporate-action denominator for {series}")
        for name in arrays:
            arrays[name][mask] = (arrays[name][mask] - dividend + allotment_price * allotment) / denominator
    return [
        {
            "date": store["date_text"][int(store["date_ms"][index])],
            "open": float(arrays["open"][index - start]),
            "high": float(arrays["high"][index - start]),
            "low": float(arrays["low"][index - start]),
            "close": float(arrays["close"][index - start]),
            "volume": float(store["volume"][index]),
        }
        for index in range(start, end)
    ]


def _bars_for_date(
    store: dict[str, Any],
    signal_date: str,
    anchor_ms: int,
    events: dict[str, list[tuple[int, float, float, float, float]]],
    symbol_filter: set[str] | None = None,
) -> tuple[list[str], dict[str, list[dict[str, Any]]]]:
    eligible: list[str] = []
    bars_by_symbol: dict[str, list[dict[str, Any]]] = {}
    for symbol, (group_start, group_end) in store["bounds"].items():
        if symbol_filter is not None and symbol not in symbol_filter:
            continue
        dates = store["date_ms"][group_start:group_end]
        end = int(np.searchsorted(dates, anchor_ms, side="right"))
        if end == 0 or int(dates[end - 1]) != anchor_ms or end < MINIMUM_BARS:
            continue
        local_start = max(0, end - LOOKBACK_BARS)
        absolute_start = group_start + local_start
        absolute_end = group_start + end
        bars = _adjusted_bars(
            store,
            absolute_start,
            absolute_end,
            events.get(symbol, []),
            anchor_ms,
        )
        if len(bars) < MINIMUM_BARS or bars[-1]["date"] != signal_date:
            raise RuntimeError(f"raw coverage/timing failure for {symbol} at {signal_date}")
        eligible.append(symbol)
        bars_by_symbol[symbol] = bars
    return eligible, bars_by_symbol


def _adjusted_numeric_bars(
    store: dict[str, Any],
    start: int,
    end: int,
    events: list[tuple[int, float, float, float, float]],
    anchor_ms: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None:
    """Return the same T-anchor transform as _adjusted_bars without row dicts."""

    if end - start < MINIMUM_BARS:
        return None
    dates = store["date_ms"][start:end]
    arrays = {
        name: np.array(store[name][start:end], dtype=float, copy=True)
        for name in ("high", "low", "close")
    }
    for ex_date_ms, dividend, bonus, allotment, allotment_price in events:
        if ex_date_ms > anchor_ms:
            break
        mask = dates < ex_date_ms
        if not np.any(mask):
            continue
        denominator = 1.0 + bonus + allotment
        if denominator <= 0 or not math.isfinite(denominator):
            raise RuntimeError("invalid corporate-action denominator")
        for name in arrays:
            arrays[name][mask] = (arrays[name][mask] - dividend + allotment_price * allotment) / denominator
    return dates, arrays["close"], store["volume"][start:end].astype(float, copy=False), arrays["high"], arrays["low"]


def _numeric_bars_for_date(
    store: dict[str, Any],
    signal_date: str,
    anchor_ms: int,
    events: dict[str, list[tuple[int, float, float, float, float]]],
    symbol_filter: set[str] | None = None,
) -> tuple[list[str], dict[str, tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]]:
    eligible: list[str] = []
    bars_by_symbol: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = {}
    for symbol, (group_start, group_end) in store["bounds"].items():
        if symbol_filter is not None and symbol not in symbol_filter:
            continue
        dates = store["date_ms"][group_start:group_end]
        end = int(np.searchsorted(dates, anchor_ms, side="right"))
        if end == 0 or int(dates[end - 1]) != anchor_ms or end < MINIMUM_BARS:
            continue
        local_start = max(0, end - LOOKBACK_BARS)
        absolute_start = group_start + local_start
        absolute_end = group_start + end
        adjusted = _adjusted_numeric_bars(
            store,
            absolute_start,
            absolute_end,
            events.get(symbol, []),
            anchor_ms,
        )
        if adjusted is None or len(adjusted[0]) < MINIMUM_BARS or _date_from_ms(int(adjusted[0][-1])) != signal_date:
            raise RuntimeError(f"raw coverage/timing failure for {symbol} at {signal_date}")
        _, close, volume, high, low = adjusted
        eligible.append(symbol)
        bars_by_symbol[symbol] = (close, volume, high, low)
    return eligible, bars_by_symbol


def _fast_core_projection(
    *,
    symbol: str,
    signal_date: str,
    earliest_execution_date: str,
    bars: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
    index_chg5: float,
) -> dict[str, Any]:
    """Formula-equivalent core projection used only after parity is witnessed."""

    c, v, hi, lo = bars
    matched: list[str] = []
    failed: list[str] = []
    rejects: list[str] = []
    close = float(c[-1])
    ma5, ma20 = float(np.mean(c[-5:])), float(np.mean(c[-20:]))
    vma20_prev = float(np.mean(v[-21:-1]))
    vol_ratio_k = float(v[-1] / vma20_prev) if vma20_prev > 0 else 0.0
    chg1 = float((c[-1] / c[-2] - 1) * 100)
    chg5 = float((c[-1] / c[-6] - 1) * 100)
    chg10 = float((c[-1] / c[-11] - 1) * 100)
    chg20 = float((c[-1] / c[-21] - 1) * 100)
    bias20 = float((close / ma20 - 1) * 100)
    llv250, hhv250 = float(np.min(lo[-250:])), float(np.max(hi[-250:]))
    pos250 = float((close - llv250) / (hhv250 - llv250)) if hhv250 > llv250 else 0.5
    diff = np.diff(c[-21:])
    up_v, dn_v = v[-20:][diff > 0], v[-20:][diff < 0]
    ud_ratio = float(np.mean(up_v) / np.mean(dn_v)) if len(up_v) and len(dn_v) and np.mean(dn_v) > 0 else 1.0
    prev60_hi_c, prev60_lo = float(np.max(c[-61:-1])), float(np.min(lo[-61:-1]))
    plat_range = float((np.max(hi[-61:-1]) - prev60_lo) / prev60_lo)
    condition_pairs = (
        ("PLATFORM_RANGE_LE_30_PCT", plat_range <= 0.30),
        ("CLOSE_ABOVE_PREV_60_CLOSE_HIGH", close > prev60_hi_c),
        ("VOLUME_RATIO_K_GE_1_8", vol_ratio_k >= 1.8),
        ("CHG1_GE_3_PCT", chg1 >= 3),
        ("CLOSE_ABOVE_MA20", close > ma20),
    )
    matched.extend(name for name, passed in condition_pairs if passed)
    failed.extend(name for name, passed in condition_pairs if not passed)

    base = {
        "as_of_date": signal_date,
        "signal_date": signal_date,
        "earliest_execution_date": earliest_execution_date,
        "symbol": symbol,
        "setup_id": SETUP_ID,
        "matched_conditions": matched,
        "failed_conditions": failed,
        "reject_reasons": rejects,
        "support": None,
        "trigger": None,
        "stop": None,
        "target": None,
        "target_type": None,
        "risk": None,
        "rr": None,
        "level_plan": None,
    }
    if failed:
        base["status"] = NOT_MATCHED
        return base

    matched.append("SECTOR_EVIDENCE_COMPLETE")
    if close <= 2:
        base.update(status=MATCHED_REJECTED, failed_conditions=["CLOSE_GT_2"], reject_reasons=[REJECTED_CLOSE_TOO_LOW])
        return base
    matched.append("CLOSE_GT_2")
    if chg10 > 35 and bias20 > 15:
        base.update(status=MATCHED_REJECTED, failed_conditions=["NO_ACCELERATION_OVEREXTENDED"], reject_reasons=[ACCELERATION_OVEREXTENDED])
        return base
    matched.append("NO_ACCELERATION_OVEREXTENDED")
    if pos250 > 0.9 and chg20 > 40:
        base.update(status=MATCHED_REJECTED, failed_conditions=["NO_GAIN_EXHAUSTED"], reject_reasons=[GAIN_EXHAUSTED])
        return base
    matched.append("NO_GAIN_EXHAUSTED")

    vol_bar_lo = float(lo[-10:][int(np.argmax(v[-10:]))])
    support_candidates = [ma20, prev60_hi_c, vol_bar_lo, float(np.min(lo[-20:]))]
    valid_supports = [value for value in support_candidates if value < close]
    if not valid_supports:
        base.update(status=MATCHED_REJECTED, failed_conditions=["VALID_SUPPORT_EXISTS"], reject_reasons=[REJECTED_NO_SUPPORT])
        return base
    matched.append("VALID_SUPPORT_EXISTS")
    support = float(max(valid_supports))
    stop = round(support * 0.98, 2)
    risk = float((close - stop) / close)
    if risk <= 0 or risk > 0.09:
        base.update(status=MATCHED_REJECTED, failed_conditions=["RISK_IN_0_TO_9_PCT"], reject_reasons=[REJECTED_STOP_DISTANCE])
        return base
    matched.append("RISK_IN_0_TO_9_PCT")

    bins = np.linspace(float(np.min(lo[-120:])), float(np.max(hi[-120:])), 21)
    indices = np.clip(np.digitize(c[-120:], bins) - 1, 0, 19)
    vol_by_price = np.zeros(20, dtype=float)
    for index, volume in zip(indices, v[-120:]):
        vol_by_price[int(index)] += float(volume)
    total_vol = float(np.sum(vol_by_price))
    overhang = float(np.sum(vol_by_price[bins[:-1] > close * 1.02]) / total_vol) if total_vol > 0 else 0.0
    h60, hhv120 = float(np.max(hi[-60:])), float(np.max(hi[-120:]))
    target_candidates: list[float] = []
    if h60 > close * 1.03:
        target_candidates.append(h60)
    above_bin_indices = [index for index in range(20) if bins[index] > close * 1.03]
    if above_bin_indices:
        peak_index = max(above_bin_indices, key=lambda index: vol_by_price[index])
        target_candidates.append(float(bins[peak_index]))
    if hhv120 > close * 1.03:
        target_candidates.append(hhv120)
    if target_candidates:
        target, target_type = float(min(target_candidates)), "PRESSURE"
    else:
        target, target_type = float(close * (1 + 2.5 * risk)), "TREND_2_5R"
    rr = float((target - close) / (close - stop))
    trigger = round(max(prev60_hi_c, ma5), 2)
    base.update(
        support=support,
        trigger=trigger,
        stop=stop,
        target=target,
        target_type=target_type,
        risk=risk,
        rr=rr,
        level_plan={
            "support": support,
            "trigger": trigger,
            "stop": stop,
            "target": target,
            "target_type": target_type,
            "risk": risk,
            "rr": rr,
            "overhang": overhang,
        },
    )
    if rr < 2:
        base.update(status=MATCHED_REJECTED, failed_conditions=["RR_GE_2"], reject_reasons=[REJECTED_RR])
        return base
    matched.append("RR_GE_2")
    if overhang > 0.5 and rr < 2.5:
        base.update(status=MATCHED_REJECTED, failed_conditions=["OVERHANG_RR_COMBINATION_ACCEPTED"], reject_reasons=[REJECTED_OVERHANG_RR])
        return base
    matched.append("OVERHANG_RR_COMBINATION_ACCEPTED")
    base["status"] = QUALIFIED_LEGACY_BASELINE
    return base


def _eligible_symbols_for_date(store: dict[str, Any], anchor_ms: int) -> list[str]:
    eligible: list[str] = []
    for symbol, (group_start, group_end) in store["bounds"].items():
        dates = store["date_ms"][group_start:group_end]
        end = int(np.searchsorted(dates, anchor_ms, side="right"))
        if end >= MINIMUM_BARS and end > 0 and int(dates[end - 1]) == anchor_ms:
            eligible.append(symbol)
    return eligible


def _manifest_for_chunk(
    signal_date: str,
    symbols: list[str],
    bars_by_symbol: dict[str, list[dict[str, Any]]],
    index: IndexManifest,
    source_content_sha256: str,
) -> GenerationInputManifest:
    retrieved_at = REPLAY_RETRIEVED_AT_BJT
    universe = UniverseManifest(
        as_of_date=signal_date,
        retrieved_at_bjt=retrieved_at,
        source="HiThink daily-K rows at T; historical raw-row universe",
        symbols=symbols,
        temporal_semantics=POINT_IN_TIME,
    )
    quotes = {
        symbol: {
            "code": symbol,
            "quote_date": signal_date,
            "price": bars_by_symbol[symbol][-1]["close"],
            # Core does not use quote turnover for any gate/level.  The raw
            # turnover field remains in the source artifact, but is not
            # relabeled as the live quote's percentage turnover.
            "turnover": 0.0,
        }
        for symbol in symbols
    }
    quote_snapshot = QuoteSnapshotManifest(
        as_of_date=signal_date,
        retrieved_at_bjt=retrieved_at,
        source="HiThink daily-K close-derived core quote placeholder",
        provider="HiThink Financial-API",
        quotes=quotes,
        temporal_semantics=POINT_IN_TIME,
    )
    stock_klines = []
    for symbol in symbols:
        bars = bars_by_symbol[symbol]
        # GenerationInputManifest only needs the validated KlineManifest
        # fields below.  The expensive per-bar canonical hash is unnecessary
        # here because the frozen raw-file SHA covers the complete source;
        # include symbol/T/adjustment identity in the deterministic digest.
        item = object.__new__(KlineManifest)
        object.__setattr__(item, "symbol", symbol)
        object.__setattr__(item, "as_of_date", signal_date)
        object.__setattr__(item, "retrieved_at_bjt", retrieved_at)
        object.__setattr__(item, "bars", tuple(bars))
        object.__setattr__(item, "provider", "HiThink Financial-API")
        object.__setattr__(item, "adjustment_mode", CORE_ADJUSTMENT_SEMANTICS)
        object.__setattr__(item, "source", "HiThink daily-K + T-filtered corporate actions")
        object.__setattr__(item, "temporal_semantics", POINT_IN_TIME)
        object.__setattr__(item, "first_bar_date", bars[0]["date"])
        object.__setattr__(item, "last_bar_date", bars[-1]["date"])
        object.__setattr__(item, "bar_count", len(bars))
        object.__setattr__(
            item,
            "normalized_data_sha256",
            sha256_json({
                "source_content_sha256": source_content_sha256,
                "symbol": symbol,
                "signal_date": signal_date,
                "bar_count": len(bars),
                "adjustment_semantics": CORE_ADJUSTMENT_SEMANTICS,
            }),
        )
        stock_klines.append(item)
    rank_input = {
        symbol: {
            "sector_name": UNVERIFIED_SECTOR_NAME,
            "sector_rank": 50.0,
            "sector_chg": 0.0,
        }
        for symbol in symbols
    }
    sector = SectorManifest(
        as_of_date=signal_date,
        retrieved_at_bjt=retrieved_at,
        source="CORE_SIGNAL_VALIDATION neutral sector sentinel; no membership loaded",
        definitions={},
        members={},
        rank_input=rank_input,
        temporal_semantics=POINT_IN_TIME,
    )
    return GenerationInputManifest(
        run_context=RunContext(
            as_of_date=signal_date,
            historical=True,
            provider_version_metadata={
                "source": "HiThink Financial-API",
                "acquisition_date": ACQUISITION_DATE,
                "sector_score_status": "UNVERIFIED",
            },
        ),
        universe=universe,
        quote_snapshot=quote_snapshot,
        stock_klines=stock_klines,
        index=index,
        sector=sector,
        provider_version_metadata={"core_layer": CORE_SIGNAL_VALIDATION},
    )


def _core_projection(result: Any) -> dict[str, Any]:
    level_plan = None if result.level_plan is None else result.level_plan.to_dict()
    return {
        "as_of_date": result.as_of_date,
        "signal_date": result.signal_date,
        "earliest_execution_date": result.earliest_execution_date,
        "symbol": result.symbol,
        "setup_id": result.setup_id,
        "status": result.status,
        "matched_conditions": list(result.matched_conditions),
        "failed_conditions": list(result.failed_conditions),
        "reject_reasons": list(result.reject_reasons),
        "support": result.support,
        "trigger": result.trigger,
        "stop": result.stop,
        "target": result.target,
        "target_type": result.target_type,
        "risk": result.risk,
        "rr": result.rr,
        "level_plan": level_plan,
    }


def _projection_hash(projection: dict[str, Any]) -> str:
    return sha256_json(projection)


def _phase(signal_date: str) -> str:
    if signal_date < "2024-01-01":
        return "2023_H2"
    if signal_date < "2025-01-01":
        return "2024"
    if signal_date < "2026-01-01":
        return "2025"
    return "2026_YTD"


def _result_stats(signal_date: str, projections: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(item["status"] for item in projections)
    a_matches = sum(set(A_CONDITIONS).issubset(item["matched_conditions"]) for item in projections)
    qualified = sum(item["status"] == QUALIFIED_LEGACY_BASELINE for item in projections)
    matched_rejected = sum(item["status"] == MATCHED_REJECTED for item in projections)
    total = len(projections)
    return {
        "signal_date": signal_date,
        "phase": _phase(signal_date),
        "candidate_count": total,
        "a_match_count": int(a_matches),
        "matched_rejected_count": int(matched_rejected),
        "qualified_count": int(qualified),
        "status_counts": dict(sorted(statuses.items())),
        "a_match_frequency": (a_matches / total) if total else None,
        "qualified_frequency": (qualified / total) if total else None,
    }


def _make_gzip_writer(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = path.open("wb")
    return raw, gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0)


def _replay_once(
    *,
    signal_dates: list[str],
    stock_store: dict[str, Any],
    events: dict[str, list[tuple[int, float, float, float, float]]],
    index_dates: dict[str, int],
    index_bars: list[dict[str, Any]],
    source_content_sha256: str,
    output_path: Path | None,
    workers: int = 1,
    chunk_size: int = CHUNK_SIZE,
    engine: str = "evaluator",
) -> dict[str, Any]:
    if workers < 1:
        raise ValueError("workers must be >= 1")
    if chunk_size < 1:
        raise ValueError("chunk_size must be >= 1")
    if engine not in {"evaluator", "formula"}:
        raise ValueError(f"unsupported replay engine: {engine!r}")
    output_file = None
    gzip_handle = None
    if output_path is not None:
        output_file, gzip_handle = _make_gzip_writer(output_path)
    digest = hashlib.sha256()
    per_date: list[dict[str, Any]] = []
    all_qualified: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    total_candidates = 0
    timing_rows: list[dict[str, str]] = []
    ordered_index_ms = np.array(sorted(index_dates.values()), dtype=np.int64)
    try:
        for signal_date in signal_dates:
            anchor_ms = index_dates[signal_date]
            index_end = int(np.searchsorted(ordered_index_ms, anchor_ms, side="right"))
            t_index_bars = index_bars[:index_end]
            if len(t_index_bars) < 6 or t_index_bars[-1]["date"] != signal_date:
                raise RuntimeError(f"benchmark coverage/timing failure at {signal_date}")
            index_manifest = IndexManifest(
                symbol=BENCHMARK_SYMBOL,
                as_of_date=signal_date,
                retrieved_at_bjt=REPLAY_RETRIEVED_AT_BJT,
                bars=t_index_bars,
                provider="HiThink Financial-API",
                adjustment_mode="INDEX_UNADJUSTED_AS_OF",
                source="HiThink historical benchmark index K",
                temporal_semantics=POINT_IN_TIME,
            )
            date_projections: list[dict[str, Any]] = []
            if engine == "formula":
                eligible_symbols, numeric_bars_by_symbol = _numeric_bars_for_date(
                    stock_store, signal_date, anchor_ms, events
                )
                if not eligible_symbols:
                    raise RuntimeError(f"no eligible symbols at {signal_date}")
                earliest_execution_date = RunContext(
                    as_of_date=signal_date,
                    historical=True,
                ).earliest_execution_date()
                timing_rows.append({"signal_date": signal_date, "earliest_execution_date": earliest_execution_date})
                idx_chg5 = _index_change(t_index_bars)
                for symbol in eligible_symbols:
                    projection = _fast_core_projection(
                        symbol=symbol,
                        signal_date=signal_date,
                        earliest_execution_date=earliest_execution_date,
                        bars=numeric_bars_by_symbol[symbol],
                        index_chg5=idx_chg5,
                    )
                    line = canonical_json(projection).encode("utf-8") + b"\n"
                    digest.update(line)
                    date_projections.append(projection)
                    status_counts[projection["status"]] += 1
                    total_candidates += 1
                    if projection["status"] == QUALIFIED_LEGACY_BASELINE:
                        all_qualified[projection["symbol"]] += 1
                    if gzip_handle is not None:
                        gzip_handle.write(line)
            else:
                eligible_symbols, bars_by_symbol = _bars_for_date(stock_store, signal_date, anchor_ms, events)
                if not eligible_symbols:
                    raise RuntimeError(f"no eligible symbols at {signal_date}")
                chunk_manifests = []
                for offset in range(0, len(eligible_symbols), chunk_size):
                    chunk_symbols = eligible_symbols[offset : offset + chunk_size]
                    manifest = _manifest_for_chunk(
                        signal_date,
                        chunk_symbols,
                        bars_by_symbol,
                        index_manifest,
                        source_content_sha256,
                    )
                    chunk_manifests.append(manifest)
                if workers == 1:
                    replay_results = [evaluate_universe(manifest) for manifest in chunk_manifests]
                else:
                    with ThreadPoolExecutor(max_workers=workers) as executor:
                        replay_results = list(executor.map(evaluate_universe, chunk_manifests))
                replay_plan = ReplayPlan(
                    signal_date=signal_date,
                    earliest_execution_date=chunk_manifests[0].earliest_execution_date or "",
                    strategy_version=STRATEGY_VERSION,
                    strategy_spec_sha256=STRATEGY_SPEC_SHA256,
                    dataset_manifest_sha256=chunk_manifests[0].input_fingerprint or "",
                )
                timing_rows.append({"signal_date": signal_date, "earliest_execution_date": replay_plan.earliest_execution_date})
                for chunk_results in replay_results:
                    for result in chunk_results:
                        projection = _core_projection(result)
                        line = canonical_json(projection).encode("utf-8") + b"\n"
                        digest.update(line)
                        date_projections.append(projection)
                        status_counts[result.status] += 1
                        total_candidates += 1
                        if result.status == QUALIFIED_LEGACY_BASELINE:
                            all_qualified[result.symbol] += 1
                        if gzip_handle is not None:
                            gzip_handle.write(line)
            date_projections.sort(key=lambda item: item["symbol"])
            per_date.append(_result_stats(signal_date, date_projections))
    finally:
        if gzip_handle is not None:
            gzip_handle.close()
        if output_file is not None:
            output_file.close()
    result = {
        "projection_stream_sha256": digest.hexdigest(),
        "total_candidate_evaluations": total_candidates,
        "status_counts": dict(sorted(status_counts.items())),
        "per_date": per_date,
        "timing": timing_rows,
        "qualified_symbol_counts": dict(sorted(all_qualified.items())),
    }
    if output_path is not None:
        result["output_file"] = {
            "path": output_path.as_posix(),
            "bytes": output_path.stat().st_size,
            "sha256": file_sha256(output_path),
        }
    return result


def _aggregate_structure(per_date: list[dict[str, Any]], qualified_counts: dict[str, int]) -> dict[str, Any]:
    def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
        candidates = sum(item["candidate_count"] for item in rows)
        a_matches = sum(item["a_match_count"] for item in rows)
        qualified = sum(item["qualified_count"] for item in rows)
        return {
            "sample_date_count": len(rows),
            "candidate_count": candidates,
            "a_match_count": a_matches,
            "qualified_count": qualified,
            "a_match_frequency": a_matches / candidates if candidates else None,
            "qualified_frequency": qualified / candidates if candidates else None,
        }

    by_phase: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_year: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in per_date:
        by_phase[item["phase"]].append(item)
        by_year[item["signal_date"][:4]].append(item)
        by_month[item["signal_date"][:7]].append(item)
    phase_summary = {}
    for phase, rows in sorted(by_phase.items()):
        phase_summary[phase] = summarize(rows)
    year_summary = {year: summarize(rows) for year, rows in sorted(by_year.items())}
    month_summary = {month: summarize(rows) for month, rows in sorted(by_month.items())}

    def frequency_diagnostics(field: str) -> dict[str, Any]:
        values = [(item["signal_date"], float(item[field])) for item in per_date]
        mean = sum(value for _, value in values) / len(values) if values else 0.0
        variance = sum((value - mean) ** 2 for _, value in values) / len(values) if values else 0.0
        stddev = math.sqrt(variance)
        threshold = mean + 3.0 * stddev
        peak_date, peak_value = max(values, key=lambda item: (item[1], item[0])) if values else (None, None)
        anomalies = [
            {"signal_date": signal_date, "frequency": frequency}
            for signal_date, frequency in values
            if frequency > threshold
        ]
        return {
            "mean_frequency": mean,
            "population_stddev": stddev,
            "anomaly_threshold_mean_plus_3_population_stddev": threshold,
            "peak": None if peak_date is None else {"signal_date": peak_date, "frequency": peak_value},
            "anomaly_dates": anomalies,
        }
    total_qualified = sum(qualified_counts.values())
    ordered = sorted(qualified_counts.items(), key=lambda item: (-item[1], item[0]))
    shares = [count / total_qualified for _, count in ordered] if total_qualified else []
    hhi = sum(value * value for value in shares) if shares else None
    return {
        "by_phase": phase_summary,
        "by_year": year_summary,
        "by_month": month_summary,
        "frequency_diagnostics": {
            "rule": "daily frequency > mean + 3 population standard deviations; descriptive only",
            "a_match": frequency_diagnostics("a_match_frequency"),
            "qualified": frequency_diagnostics("qualified_frequency"),
        },
        "qualified_signal_event_count": total_qualified,
        "qualified_unique_symbol_count": len(qualified_counts),
        "top1_symbol_share": shares[0] if shares else None,
        "top5_symbol_share": sum(shares[:5]) if shares else None,
        "qualified_symbol_hhi": hhi,
        "top_symbols": [{"symbol": symbol, "qualified_count": count} for symbol, count in ordered[:10]],
    }


def canonical_source_content_sha256(files: Iterable[dict[str, Any]]) -> str:
    """Hash raw source content without coupling it to a filesystem path."""

    records = []
    seen_identities: set[str] = set()
    for file_metadata in files:
        identity = str(file_metadata["logical_identity"])
        if identity in seen_identities:
            raise RuntimeError(f"duplicate raw input logical identity: {identity}")
        seen_identities.add(identity)
        records.append({
            "logical_identity": identity,
            "bytes": int(file_metadata["bytes"]),
            "sha256": str(file_metadata["sha256"]),
        })
    records.sort(key=lambda item: item["logical_identity"])
    return sha256_json(records)


def _source_metadata(raw_dir: Path) -> dict[str, Any]:
    files = []
    for role, name in REQUIRED_RAW_INPUTS:
        path = raw_dir / name
        if not path.exists():
            raise RuntimeError(f"required raw input is missing: {path}")
        files.append({
            "logical_identity": f"{role}/{name}",
            "role": role,
            "filename": name,
            "path": path.as_posix(),
            "bytes": path.stat().st_size,
            "sha256": file_sha256(path),
        })
    return {"files": files, "content_sha256": canonical_source_content_sha256(files)}


def _stream_summary(path: Path) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError(f"core replay result stream is missing or empty: {path}")
    digest = hashlib.sha256()
    per_date: dict[str, dict[str, Any]] = {}
    qualified_counts: Counter[str] = Counter()
    previous_key: tuple[str, str] | None = None
    row_count = 0
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if set(row) != set(CORE_PROJECTION_FIELDS):
                raise RuntimeError("core result stream contains non-core or missing fields")
            signal_date = row["signal_date"]
            key = (signal_date, row["symbol"])
            if previous_key is not None and key < previous_key:
                raise RuntimeError("core result stream is not sorted by signal_date/symbol")
            previous_key = key
            if row["as_of_date"] != signal_date:
                raise RuntimeError("core result as_of_date differs from signal_date")
            canonical_line = canonical_json(row).encode("utf-8") + b"\n"
            digest.update(canonical_line)
            record = per_date.setdefault(
                signal_date,
                {
                    "candidate_count": 0,
                    "a_match_count": 0,
                    "matched_rejected_count": 0,
                    "qualified_count": 0,
                    "status_counts": Counter(),
                    "earliest_execution_dates": set(),
                },
            )
            record["candidate_count"] += 1
            record["status_counts"][row["status"]] += 1
            record["a_match_count"] += int(set(A_CONDITIONS).issubset(row["matched_conditions"]))
            record["matched_rejected_count"] += int(row["status"] == MATCHED_REJECTED)
            record["qualified_count"] += int(row["status"] == QUALIFIED_LEGACY_BASELINE)
            record["earliest_execution_dates"].add(row["earliest_execution_date"])
            if row["status"] == QUALIFIED_LEGACY_BASELINE:
                qualified_counts[row["symbol"]] += 1
            row_count += 1
    if row_count == 0:
        raise RuntimeError("core result stream has no rows")
    normalized_dates = []
    timing = []
    total_candidates = 0
    statuses: Counter[str] = Counter()
    for signal_date in sorted(per_date):
        record = per_date[signal_date]
        total = record["candidate_count"]
        normalized_dates.append(
            {
                "signal_date": signal_date,
                "phase": _phase(signal_date),
                "candidate_count": total,
                "a_match_count": record["a_match_count"],
                "matched_rejected_count": record["matched_rejected_count"],
                "qualified_count": record["qualified_count"],
                "status_counts": dict(sorted(record["status_counts"].items())),
                "a_match_frequency": record["a_match_count"] / total if total else None,
                "qualified_frequency": record["qualified_count"] / total if total else None,
            }
        )
        statuses.update(record["status_counts"])
        if len(record["earliest_execution_dates"]) != 1:
            raise RuntimeError(f"inconsistent earliest execution date at {signal_date}")
        timing.append(
            {
                "signal_date": signal_date,
                "earliest_execution_date": next(iter(record["earliest_execution_dates"])),
            }
        )
        total_candidates += total
    return {
        "projection_stream_sha256": digest.hexdigest(),
        "total_candidate_evaluations": total_candidates,
        "status_counts": dict(sorted(statuses.items())),
        "per_date": normalized_dates,
        "timing": timing,
        "qualified_symbol_counts": dict(sorted(qualified_counts.items())),
    }


def merge_result_parts(part_paths: list[Path], output_path: Path) -> dict[str, Any]:
    """Merge ordered gzip members without changing their decompressed stream."""

    if not part_paths:
        raise ValueError("at least one result part is required")
    summaries = [_stream_summary(path) for path in part_paths]
    previous_last_date: str | None = None
    for summary in summaries:
        first_date = summary["per_date"][0]["signal_date"]
        last_date = summary["per_date"][-1]["signal_date"]
        if previous_last_date is not None and first_date <= previous_last_date:
            raise RuntimeError("result parts overlap or are out of order")
        previous_last_date = last_date
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as output:
        for path in part_paths:
            with path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    output.write(chunk)
    merged = _stream_summary(output_path)
    return {
        "path": output_path.as_posix(),
        "bytes": output_path.stat().st_size,
        "sha256": file_sha256(output_path),
        "projection_stream_sha256": merged["projection_stream_sha256"],
        "candidate_evaluations": merged["total_candidate_evaluations"],
        "status_counts": merged["status_counts"],
    }


def _coverage_by_date(store: dict[str, Any], signal_dates: list[str], index_dates: dict[str, int]) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for signal_date in signal_dates:
        anchor_ms = index_dates[signal_date]
        raw_count = 0
        eligible_count = 0
        for group_start, group_end in store["bounds"].values():
            dates = store["date_ms"][group_start:group_end]
            end = int(np.searchsorted(dates, anchor_ms, side="right"))
            if end and int(dates[end - 1]) == anchor_ms:
                raw_count += 1
                eligible_count += int(end >= MINIMUM_BARS)
        result[signal_date] = {
            "raw_symbol_count_at_T": raw_count,
            "evaluable_symbol_count": eligible_count,
            "warmup_or_missing_history_count": raw_count - eligible_count,
        }
    return result


def _determinism_sample(
    *,
    signal_dates: list[str],
    store: dict[str, Any],
    events: dict[str, list[tuple[int, float, float, float, float]]],
    index_dates: dict[str, int],
    index_bars: list[dict[str, Any]],
    source_content_sha256: str,
    engine: str = "evaluator",
) -> dict[str, Any]:
    ordered_index_ms = np.array(sorted(index_dates.values()), dtype=np.int64)
    sample_rows = 0
    sample_digest = hashlib.sha256()
    sample_date_counts: dict[str, int] = {}
    for signal_date in signal_dates:
        anchor_ms = index_dates[signal_date]
        eligible = _eligible_symbols_for_date(store, anchor_ms)
        if len(eligible) <= 12:
            selected = eligible
        else:
            selected = sorted(set(eligible[:4] + eligible[len(eligible) // 2 - 2 : len(eligible) // 2 + 2] + eligible[-4:]))
        selected_set = set(selected)
        _, bars_by_symbol = _bars_for_date(store, signal_date, anchor_ms, events, selected_set)
        index_end = int(np.searchsorted(ordered_index_ms, anchor_ms, side="right"))
        index_manifest = IndexManifest(
            symbol=BENCHMARK_SYMBOL,
            as_of_date=signal_date,
            retrieved_at_bjt=REPLAY_RETRIEVED_AT_BJT,
            bars=index_bars[:index_end],
            provider="HiThink Financial-API",
            adjustment_mode="INDEX_UNADJUSTED_AS_OF",
            source="HiThink historical benchmark index K",
            temporal_semantics=POINT_IN_TIME,
        )
        manifest = _manifest_for_chunk(
            signal_date,
            sorted(selected_set),
            bars_by_symbol,
            index_manifest,
            source_content_sha256,
        )
        first = [_core_projection(result) for result in evaluate_universe(manifest)]
        second = [_core_projection(result) for result in evaluate_universe(manifest)]
        if first != second:
            raise RuntimeError(f"determinism sample mismatch at {signal_date}")
        if engine == "formula":
            _, numeric_bars_by_symbol = _numeric_bars_for_date(
                store, signal_date, anchor_ms, events, selected_set
            )
            earliest_execution_date = manifest.earliest_execution_date or ""
            formula_first = [
                _fast_core_projection(
                    symbol=symbol,
                    signal_date=signal_date,
                    earliest_execution_date=earliest_execution_date,
                    bars=numeric_bars_by_symbol[symbol],
                    index_chg5=_index_change(index_bars[:index_end]),
                )
                for symbol in sorted(selected_set)
            ]
            if formula_first != first:
                raise RuntimeError(f"formula core does not match frozen evaluator at {signal_date}")
        for row in first:
            sample_digest.update(canonical_json(row).encode("utf-8") + b"\n")
        sample_rows += len(first)
        sample_date_counts[signal_date] = len(first)
    return {
        "sample_rows": sample_rows,
        "sample_date_counts": sample_date_counts,
        "evaluator_double_pass_hash_parity": True,
        "formula_projection_vs_evaluator_parity": engine == "formula",
        "sample_projection_stream_sha256": sample_digest.hexdigest(),
    }


def run(
    raw_dir: Path,
    output_dir: Path,
    *,
    reuse_existing: bool = False,
    full_double_pass_confirmed: bool = False,
    schedule: str = "quarter_end",
    start_date: str | None = None,
    end_date: str | None = None,
    workers: int = 1,
    chunk_size: int = CHUNK_SIZE,
    engine: str = "evaluator",
) -> dict[str, Any]:
    daily_path = raw_dir / "daily_k.parquet"
    adjustment_path = raw_dir / "adjustment_factors.parquet"
    if not daily_path.exists() or not adjustment_path.exists():
        raise RuntimeError("daily-K or adjustment dump is missing")
    source = _source_metadata(raw_dir)
    # Load a small index first so the date schedule is based on common
    # historical sessions, then load the daily-K series.
    index_dates, index_bars, index_meta = _load_index(raw_dir)
    stock_store, stock_meta = _load_stock_store(daily_path)
    if schedule == "quarter_end":
        signal_dates = _quarter_end_signal_dates(stock_store["date_ms"], set(index_dates))
    elif schedule == "continuous":
        signal_dates = _continuous_signal_dates(index_dates)
    else:
        raise ValueError(f"unsupported signal-date schedule: {schedule!r}")
    if engine not in {"evaluator", "formula"}:
        raise ValueError(f"unsupported replay engine: {engine!r}")
    if start_date is not None or end_date is not None:
        lower = start_date or signal_dates[0]
        upper = end_date or signal_dates[-1]
        if lower > upper:
            raise ValueError("start-date must not be after end-date")
        signal_dates = [value for value in signal_dates if lower <= value <= upper]
    minimum_dates = 12 if schedule == "quarter_end" else 1
    if len(signal_dates) < minimum_dates:
        raise RuntimeError(f"unexpectedly low signal-date coverage: {len(signal_dates)}")
    events, event_meta = _load_events(adjustment_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "core_replay_results.jsonl.gz"
    first = None
    if not reuse_existing:
        first = _replay_once(
            signal_dates=signal_dates,
            stock_store=stock_store,
            events=events,
            index_dates=index_dates,
            index_bars=index_bars,
            source_content_sha256=source["content_sha256"],
            output_path=result_path,
            workers=workers,
            chunk_size=chunk_size,
            engine=engine,
        )
    stream_first = _stream_summary(result_path)
    stream_second = _stream_summary(result_path)
    if first is not None and (
        first["projection_stream_sha256"] != stream_first["projection_stream_sha256"]
        or first["per_date"] != stream_first["per_date"]
        or first["status_counts"] != stream_first["status_counts"]
    ):
        raise RuntimeError("evaluator result stream does not match its canonical audit")
    if stream_first != stream_second:
        raise RuntimeError("deterministic artifact hash/structure parity failed")
    sample = _determinism_sample(
        signal_dates=signal_dates,
        store=stock_store,
        events=events,
        index_dates=index_dates,
        index_bars=index_bars,
        source_content_sha256=source["content_sha256"],
        engine=engine,
    )
    coverage = _coverage_by_date(stock_store, signal_dates, index_dates)
    expected_counts = {key: value["evaluable_symbol_count"] for key, value in coverage.items()}
    observed_counts = {item["signal_date"]: item["candidate_count"] for item in stream_first["per_date"]}
    if expected_counts != observed_counts:
        raise RuntimeError("core replay candidate coverage does not match raw T-day universe")
    structure = _aggregate_structure(stream_first["per_date"], stream_first["qualified_symbol_counts"])
    result_file_metadata = {
        "path": result_path.as_posix(),
        "bytes": result_path.stat().st_size,
        "sha256": file_sha256(result_path),
    }
    manifest_payload: dict[str, Any] = {
        "schema_version": DATASET_SCHEMA_VERSION,
        "dataset_version": (
            QUARTER_END_DATASET_VERSION
            if schedule == "quarter_end"
            else CONTINUOUS_DATASET_VERSION
        ),
        "data_partition": "validation",
        "validation_layer": CORE_SIGNAL_VALIDATION,
        "market": "CN_STOCKS",
        "signal_date_schedule": (
            "quarter_end_common_sessions_plus_latest"
            if schedule == "quarter_end"
            else "continuous_xshg_sessions_within_frozen_validation_interval"
        ),
        "signal_dates": signal_dates,
        "validation_interval": {
            "start": VALIDATION_START,
            "end": VALIDATION_END,
            "selection_rationale": (
                "The original 14 dates were quarter-end common sessions plus the latest available session; "
                "the continuous extension keeps those frozen endpoints and expands only the same validation partition."
            ),
            "final_oos_read": False,
        },
        "raw_data_range": {"start": stock_meta["min_date"], "end": stock_meta["max_date"]},
        "universe_semantics": "historical daily-K rows present at T with >=120 bars through T",
        "sector_semantics": {
            "legacy_taxonomy": "新浪行业",
            "historical_membership_included": False,
            "sector_score_status": "UNVERIFIED",
            "sector_report_status": "UNVERIFIED",
            "neutral_evaluator_sentinel_used": True,
            "taxonomy_substitution": False,
        },
        "adjustment_semantics": {
            "name": CORE_ADJUSTMENT_SEMANTICS,
            "formula": "(price - dividend_per_share + allotment_price*allotment_ratio)/(1 + per_share_bonus + allotment_ratio)",
            "event_filter": "date < ex_date <= T",
            "event_order": "ascending ex_date",
            "price_fields_adjusted": ["open", "high", "low", "close"],
            "volume_semantics": "raw unadjusted volume",
            "provider_forward_used_as_t_anchor": False,
        },
        "provenance": {
            "source": "HiThink Financial-API",
            "acquisition_date": ACQUISITION_DATE,
            "acquisition_at_bjt": ACQUISITION_AT_BJT,
            "raw_inputs": source,
            "stock": stock_meta,
            "corporate_actions": event_meta,
            "benchmark": index_meta,
            "known_at_vintage_proof": False,
            "known_at_limitation": "retrospective official dump has observation dates and acquisition hash, but no per-bar historical vintage timestamp",
        },
        "timing_contract": {
            "signal_uses": "T close only",
            "execution": "not run",
            "earliest_execution": "next XSHG session T+1 recorded per signal date",
            "same_bar_execution": False,
            "future_bar_inputs": False,
        },
        "strategy": {
            "version": STRATEGY_VERSION,
            "spec_sha256": STRATEGY_SPEC_SHA256,
            "protocol_semantic_sha256": PROTOCOL_SEMANTIC_SHA256,
            "strategy_source_modified": False,
        },
        "replay": {
            "candidate_evaluations": stream_first["total_candidate_evaluations"],
            "status_counts": stream_first["status_counts"],
            "projection_stream_sha256": stream_first["projection_stream_sha256"],
            "deterministic_second_pass_sha256": stream_second["projection_stream_sha256"],
            "hash_parity": True,
            "full_evaluator_double_pass_hash_parity": full_double_pass_confirmed,
            "determinism_method": (
                "two independent full evaluator runs plus canonical stream reread and fixed sample double-pass"
                if full_double_pass_confirmed
                else "canonical stream reread plus fixed sample evaluator double-pass"
            ),
            "evaluator_workers": workers,
            "evaluator_chunk_size": chunk_size,
            "engine": engine,
            "results_artifact": result_file_metadata,
            "per_date": stream_first["per_date"],
            "structure": structure,
            "core_output_fields": list(CORE_PROJECTION_FIELDS),
            "score_fields_in_output": False,
            "sample_determinism": sample,
        },
        "coverage_and_correctness": {
            "raw_daily_k_duplicate_keys": stock_meta["duplicate_key_count"],
            "raw_daily_k_null_numeric_fields": stock_meta["null_numeric_count"],
            "raw_daily_k_negative_volume_rows": stock_meta["negative_volume_count"],
            "benchmark_rows": index_meta["row_count"],
            "signal_date_count": len(signal_dates),
            "coverage_by_date": coverage,
            "all_signal_dates_have_benchmark": True,
            "all_evaluable_symbols_have_120_bars": True,
            "all_evaluator_bars_end_at_T": True,
            "all_events_used_have_ex_date_at_or_before_T": True,
            "look_ahead_scan": "PASS_FOR_OBSERVATION_DATES_AND_FILTERED_EVENTS",
            "timing_scan": "PASS_T_CLOSE_TO_NEXT_XSHG_SESSION",
        },
        "forbidden_metrics": ["return", "win_rate", "mfe", "mae", "pnl", "expectancy", "profit_factor"],
        "full_legacy_output_validation": {
            "status": "BLOCKED_HISTORICAL_SINA_MEMBERSHIP",
            "score_85_status": "UNVERIFIED",
            "historical_sina_membership_required": True,
        },
        "status": "CORE_SIGNAL_VALIDATION_COMPLETE_NO_RETURN_METRICS",
        "return_validation_gate": "READY_FOR_EXPLICIT_SCOPE_REVIEW; NO_RETURN_METRICS_COMPUTED",
    }
    manifest_payload["content_sha256"] = sha256_json({
        "source": source,
        "signal_dates": signal_dates,
        "projection_stream_sha256": stream_first["projection_stream_sha256"],
    })
    manifest_payload["manifest_sha256"] = sha256_json(manifest_payload)
    manifest_path = output_dir / "core_signal_validation_manifest.json"
    manifest_path.write_text(json.dumps(manifest_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_payload["manifest_file"] = {
        "path": manifest_path.as_posix(),
        "bytes": manifest_path.stat().st_size,
        "sha256": file_sha256(manifest_path),
    }
    return manifest_payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--reuse-existing", action="store_true")
    parser.add_argument("--full-double-pass-confirmed", action="store_true")
    parser.add_argument("--schedule", choices=("quarter_end", "continuous"), default="quarter_end")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--merge-parts", nargs="+", type=Path)
    parser.add_argument("--merge-output", type=Path)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--chunk-size", type=int, default=CHUNK_SIZE)
    parser.add_argument("--engine", choices=("evaluator", "formula"), default="evaluator")
    args = parser.parse_args()
    if args.merge_parts is not None:
        if args.merge_output is None:
            parser.error("--merge-output is required with --merge-parts")
        print(json.dumps(merge_result_parts(args.merge_parts, args.merge_output), ensure_ascii=False, sort_keys=True))
        return
    if args.raw_dir is None or args.output_dir is None:
        parser.error("--raw-dir and --output-dir are required unless merging result parts")
    print(json.dumps(
        run(
            args.raw_dir,
            args.output_dir,
            reuse_existing=args.reuse_existing,
            full_double_pass_confirmed=args.full_double_pass_confirmed,
            schedule=args.schedule,
            start_date=args.start_date,
            end_date=args.end_date,
            workers=args.workers,
            chunk_size=args.chunk_size,
            engine=args.engine,
        ),
        ensure_ascii=False,
        sort_keys=True,
    ))


if __name__ == "__main__":
    main()
