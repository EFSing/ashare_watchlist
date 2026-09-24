"""C_RAW_T_ANCHOR_LIMITED_EXPLORATION_V1 — evidence-limited historical exploration.

Research identity ``C_RAW_T_ANCHOR_LIMITED_EXPLORATION_V1`` with input identity
``RAW_DAILY_K_DECLARED_T_ANCHOR_V1``.

This module reconstructs a T-anchor price series from the frozen *unadjusted*
daily-K dump plus the frozen corporate-action table using the transformation the
project already declared in ``docs/phase2e_pit_source_audit.md`` and in the frozen
validation manifest ``adjustment_semantics``::

    price <- (price - dividend_per_share + allotment_price * allotment_ratio)
             / (1 + per_share_bonus + allotment_ratio)

applied in ascending ``ex_date`` order to every bar with
``bar_date < ex_date <= T`` for anchor ``T``.  ``volume`` stays raw.

It is NOT ``C_QFQ_INPUT_V1`` (the frozen per-day provider qfq snapshot), NOT a
Formal B path, NOT the C daily watchlist, and NOT a PIT claim.  It calls no
provider, writes no canonical state, and never reads Final OOS.

Frozen protocol (written and committed before any outcome access):
    docs/research/c_raw_t_anchor_limited_exploration_v1_protocol.md
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from c_pre_outcome_design import RULE_CANDIDATES, build_entry_observation
from universe_policy import BOARD_MAIN, classify_board


STUDY_ID = "C_RAW_T_ANCHOR_LIMITED_EXPLORATION_V1"
INPUT_IDENTITY = "RAW_DAILY_K_DECLARED_T_ANCHOR_V1"
OUTPUT_ROOT = Path("data/research/c_raw_t_anchor_limited_exploration_v1")
SAMPLE_IDENTITY = "MAIN_BOARD_ST_UNVERIFIED_CANDIDATE_SAMPLE"
RULES = ("BALANCED_A", "CONSERVATIVE_B")
WINDOWS = (3, 5, 10)
MIN_BARS = 120
PREFIX_BARS = 120
BJT = timezone(timedelta(hours=8))

DAILY_K_LOGICAL_PATH = "data/validation/core_signal_validation/raw/daily_k.parquet"
ADJUSTMENT_LOGICAL_PATH = "data/validation/core_signal_validation/raw/adjustment_factors.parquet"
MANIFEST_LOGICAL_PATH = (
    "data/validation/core_signal_validation_continuous_parts/core_signal_validation_manifest.json"
)
DECLARED_FORMULA = (
    "(price - dividend_per_share + allotment_price*allotment_ratio)/(1 + per_share_bonus + allotment_ratio)"
)
EVENT_FILTER = "date < ex_date <= T"
PRICE_FIELDS = ("open", "high", "low", "close")
COST_DECISION = "NOT_CALCULABLE_COST_MODEL_NOT_PREEXISTING"

EXPECTED_INPUTS: dict[str, dict[str, Any]] = {
    "daily_k": {
        "logical_path": DAILY_K_LOGICAL_PATH,
        "bytes": 180_203_424,
        "sha256": "61189a4850e2eb157453e28e5375e502e20d214508bbe70ea71066ca3e05e426",
        "registry_artifact": "phase2e.raw.daily_k",
        "role": "raw_unadjusted_daily_k",
    },
    "adjustment_factors": {
        "logical_path": ADJUSTMENT_LOGICAL_PATH,
        "bytes": 295_284,
        "sha256": "a1b7d63c5826ccd3610dc9bdd949d82eeb0ba84ffad451bfb8bb30ca74962716",
        "registry_artifact": "phase2e.raw.adjustment_factors",
        "role": "corporate_action_table",
    },
    "manifest": {
        "logical_path": MANIFEST_LOGICAL_PATH,
        "bytes": None,
        "sha256": "008643a64e0070433f3d63dca8243f8dad294b049a7accb5d49af3597aae17b0",
        "registry_artifact": None,
        "role": "frozen_dataset_manifest",
        "text_identity": True,
    },
}


class InputIdentityError(RuntimeError):
    """Raised when a frozen input does not match its declared identity."""


# --------------------------------------------------------------------------- #
# identity, calendar and IO
# --------------------------------------------------------------------------- #
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_text_sha256(path: Path) -> tuple[str, int]:
    """SHA-256 of the LF-normalised text, per FROZEN_ARTIFACT_POLICY CRLF rule."""

    raw = path.read_bytes()
    normalised = raw.replace(b"\r\n", b"\n")
    return hashlib.sha256(normalised).hexdigest(), len(normalised)


def ms_to_date(value: int) -> str:
    """Daily-K timestamps are Beijing-time midnight; never convert via UTC."""

    return datetime.fromtimestamp(int(value) / 1000, tz=BJT).date().isoformat()


def date_to_ms(date_text: str) -> int:
    year, month, day = (int(part) for part in str(date_text).split("-"))
    return int(datetime(year, month, day, tzinfo=BJT).timestamp() * 1000)


def _normalise_formula(value: Any) -> str:
    return "".join(str(value or "").split())


def verify_inputs(raw_dir: Path, manifest_path: Path) -> dict[str, Any]:
    """Verify frozen byte identity and the declared transformation contract."""

    resolved = {
        "daily_k": raw_dir / "daily_k.parquet",
        "adjustment_factors": raw_dir / "adjustment_factors.parquet",
        "manifest": manifest_path,
    }
    files: dict[str, Any] = {}
    blocking: list[str] = []
    for key, path in resolved.items():
        expected = EXPECTED_INPUTS[key]
        if not path.is_file():
            files[key] = {"logical_path": expected["logical_path"], "status": "MISSING"}
            blocking.append(f"{key}:MISSING")
            continue
        size = path.stat().st_size
        digest = sha256_file(path)
        record = {
            "logical_path": expected["logical_path"],
            "role": expected["role"],
            "registry_artifact": expected["registry_artifact"],
            "bytes": size,
            "sha256": digest,
            "declared_sha256": expected["sha256"],
            "status": "HASH_VERIFIED",
        }
        matched = digest == expected["sha256"] and expected["bytes"] in (None, size)
        if not matched and expected.get("text_identity"):
            canonical_digest, canonical_size = canonical_text_sha256(path)
            record["canonical_text_sha256"] = canonical_digest
            record["canonical_text_bytes"] = canonical_size
            record["crlf_normalised"] = canonical_digest != digest
            matched = canonical_digest == expected["sha256"]
            if matched:
                record["identity_source"] = (
                    "LF-normalised text bytes; Windows checkout stores CRLF "
                    "(FROZEN_ARTIFACT_POLICY)"
                )
        if not matched:
            record["status"] = "HASH_MISMATCH"
        files[key] = record
        if not matched:
            blocking.append(f"{key}:HASH_MISMATCH")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    adjustment = manifest.get("adjustment_semantics", {})
    if adjustment.get("event_filter") != EVENT_FILTER:
        blocking.append("manifest:EVENT_FILTER_NOT_AS_DECLARED")
    if _normalise_formula(adjustment.get("formula")) != _normalise_formula(DECLARED_FORMULA):
        blocking.append("manifest:T_ANCHOR_FORMULA_NOT_AS_DECLARED")
    if adjustment.get("provider_forward_used_as_t_anchor") is not False:
        blocking.append("manifest:PROVIDER_FORWARD_USED_AS_T_ANCHOR")
    return {
        "schema_version": "C_RAW_T_ANCHOR_INPUT_VERIFICATION_V1",
        "study_id": STUDY_ID,
        "input_identity": INPUT_IDENTITY,
        "not_the_identity": "C_QFQ_INPUT_V1",
        "files": files,
        "declared_contract": {
            "name": adjustment.get("name"),
            "formula": adjustment.get("formula"),
            "event_filter": adjustment.get("event_filter"),
            "event_order": adjustment.get("event_order"),
            "price_fields_adjusted": adjustment.get("price_fields_adjusted"),
            "volume_semantics": adjustment.get("volume_semantics"),
            "provider_forward_used_as_t_anchor": adjustment.get("provider_forward_used_as_t_anchor"),
        },
        "manifest_provenance": {
            "known_at_vintage_proof": manifest.get("provenance", {}).get("known_at_vintage_proof"),
            "known_at_limitation": manifest.get("provenance", {}).get("known_at_limitation"),
            "acquisition_date": manifest.get("provenance", {}).get("acquisition_date"),
            "final_oos_read": manifest.get("validation_interval", {}).get("final_oos_read"),
            "forbidden_metrics": manifest.get("forbidden_metrics"),
            "return_validation_gate": manifest.get("return_validation_gate"),
        },
        "status": "HASH_VERIFIED" if not blocking else "BLOCKED_BY_INPUT_IDENTITY_GAP",
        "blocking_reasons": blocking,
    }


def load_frozen_contract(manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dates = [str(value) for value in manifest.get("signal_dates") or []]
    if len(dates) != 769 or dates != sorted(dates) or len(set(dates)) != len(dates):
        raise InputIdentityError(f"unexpected frozen signal-date series: {len(dates)} entries")
    return {
        "signal_dates": dates,
        "signal_ms": [date_to_ms(value) for value in dates],
        "validation_interval": manifest.get("validation_interval", {}),
        "universe_semantics": manifest.get("universe_semantics"),
    }


def load_corporate_actions(path: Path) -> tuple[dict[str, list[tuple[float, ...]]], dict[str, int]]:
    import pyarrow.parquet as pq  # optional 'research' dependency: import lazily

    table = pq.read_table(
        path,
        columns=["thscode", "ex_date_ms", "dividend_per_share", "per_share_bonus",
                 "allotment_ratio", "allotment_price"],
    )
    codes = table.column("thscode").to_pylist()
    ex_dates = table.column("ex_date_ms").to_numpy()
    dividends = table.column("dividend_per_share").to_numpy()
    bonuses = table.column("per_share_bonus").to_numpy()
    ratios = table.column("allotment_ratio").to_numpy()
    allotment_prices = table.column("allotment_price").to_numpy()
    del table
    gc.collect()
    events: dict[str, list[tuple[float, ...]]] = {}
    counters: Counter[str] = Counter()
    for index, code in enumerate(codes):
        values = (float(ex_dates[index]), float(dividends[index]), float(bonuses[index]),
                  float(ratios[index]), float(allotment_prices[index]))
        denominator = 1.0 + values[2] + values[3]
        if not all(math.isfinite(value) for value in values):
            counters["non_finite_rows"] += 1
            continue
        if not math.isfinite(denominator) or denominator <= 0:
            counters["invalid_denominator_rows"] += 1
            continue
        events.setdefault(str(code), []).append(values)
    for code in events:
        events[code].sort(key=lambda item: item[0])
    counters["corporate_action_rows"] = len(codes)
    counters["symbols_with_events"] = len(events)
    del codes
    gc.collect()
    return events, dict(counters)


def load_daily_bars(path: Path) -> dict[str, Any]:
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    table = pq.read_table(
        path,
        columns=["thscode", "date_ms", "open_price", "high_price", "low_price",
                 "close_price", "volume"],
    )
    encoded = pc.dictionary_encode(table.column("thscode").combine_chunks())
    indices = np.asarray(encoded.indices.to_numpy(zero_copy_only=False), dtype=np.int64)
    codes = [str(value) for value in encoded.dictionary.to_pylist()]
    dates = table.column("date_ms").to_numpy().astype(np.int64, copy=True)
    arrays = {
        "open": table.column("open_price").to_numpy().astype(np.float64, copy=True),
        "high": table.column("high_price").to_numpy().astype(np.float64, copy=True),
        "low": table.column("low_price").to_numpy().astype(np.float64, copy=True),
        "close": table.column("close_price").to_numpy().astype(np.float64, copy=True),
    }
    volume = table.column("volume").to_numpy().astype(np.float64, copy=True)
    del table, encoded
    gc.collect()
    order = np.lexsort((dates, indices))
    store = {
        "codes": codes,
        "code_index": indices[order],
        "date_ms": dates[order],
        "volume": volume[order],
    }
    for field in PRICE_FIELDS:
        store[field] = arrays[field][order]
    del arrays, volume, dates, indices, order
    gc.collect()
    return store


# --------------------------------------------------------------------------- #
# declared T-anchor transformation
# --------------------------------------------------------------------------- #
def apply_event_values(values: np.ndarray, dividend: float, bonus: float, ratio: float,
                       allotment_price: float) -> np.ndarray:
    denominator = 1.0 + bonus + ratio
    if not math.isfinite(denominator) or denominator <= 0:
        raise InputIdentityError(f"invalid corporate-action denominator: {denominator}")
    return (values - dividend + allotment_price * ratio) / denominator


def anchor_arrays_for_range(
    store: Mapping[str, Any],
    events: Sequence[tuple[float, ...]],
    start: int,
    stop: int,
    anchor_ms: int,
) -> dict[str, np.ndarray]:
    """T-anchor ``open/high/low/close`` for symbol indices ``[start, stop)``.

    Applies every event with ``bar_date < ex_date <= anchor_ms`` in ascending
    ``ex_date`` order.  The anchor bar itself keeps its raw price.  ``volume`` is
    deliberately not returned because the frozen semantics are raw/unadjusted.
    """

    dates = store["date_ms"][start:stop]
    window = {field: store[field][start:stop].astype(np.float64, copy=True) for field in PRICE_FIELDS}
    for ex_date_ms, dividend, bonus, ratio, allotment_price in events:
        if ex_date_ms > anchor_ms:
            break
        mask = dates < ex_date_ms
        if not mask.any():
            continue
        for field in PRICE_FIELDS:
            window[field][mask] = apply_event_values(window[field][mask], dividend, bonus, ratio,
                                                      allotment_price)
    return window


def count_events_in_window(events: Sequence[tuple[float, ...]], first_ms: int, last_ms: int) -> int:
    return sum(1 for item in events if first_ms < item[0] <= last_ms)


def symbol_bounds(store: Mapping[str, Any], code_position: int) -> tuple[int, int]:
    codes = store["code_index"]
    return (int(np.searchsorted(codes, code_position, side="left")),
            int(np.searchsorted(codes, code_position, side="right")))


# --------------------------------------------------------------------------- #
# necessary-condition prefilter (must be a provable superset)
# --------------------------------------------------------------------------- #
def rolling_sum(values: np.ndarray, window: int) -> np.ndarray:
    out = np.full(len(values), np.nan)
    if window < 1 or len(values) < window:
        return out
    cumulative = np.concatenate(([0.0], np.cumsum(values)))
    out[window - 1:] = cumulative[window:] - cumulative[:-window]
    return out


def trend_prefilter(close: np.ndarray, config: Any) -> np.ndarray:
    """Necessary conditions of ``entry_candidate`` (never an outcome filter).

    Mirrors ``c_pre_outcome_design.trend_features``: ``close_T > MA_fast > MA_slow``,
    positive log-close slope over the trend window and the up-close fraction floor.
    """

    length = len(close)
    window = int(config.trend_window)
    result = np.zeros(length, dtype=bool)
    if length < max(MIN_BARS, window):
        return result
    index = np.arange(length, dtype=np.float64)
    fast = rolling_sum(close, int(config.fast_average_window)) / int(config.fast_average_window)
    slow = rolling_sum(close, int(config.slow_average_window)) / int(config.slow_average_window)
    window_sum = rolling_sum(close, window)
    weighted_sum = rolling_sum(index * close, window)
    # sum((x - x_mean) * (y - y_mean)) with x = 0..window-1 inside each window
    numerator = (weighted_sum
                 - (index - window + 1.0) * window_sum
                 - ((window - 1) / 2.0) * window_sum)
    up_flags = (close[1:] > close[:-1]).astype(np.float64)
    up_counts = rolling_sum(up_flags, window - 1)
    up_fraction = np.full(length, np.nan)
    up_fraction[window - 1:] = up_counts[window - 2:] / (window - 1)
    with np.errstate(invalid="ignore"):
        qualified = ((close > fast) & (fast > slow) & (numerator > 0)
                     & (up_fraction >= config.minimum_up_close_fraction))
    result[window - 1:] = qualified[window - 1:]
    return result


def strong_up_close_mask(open_: np.ndarray, high: np.ndarray, low: np.ndarray,
                         close: np.ndarray) -> np.ndarray:
    """Necessary T-bar conditions: positive body, higher close and CLV >= 0.60."""

    span = high - low
    with np.errstate(invalid="ignore", divide="ignore"):
        close_location = np.where(span > 0, (close - low) / np.where(span > 0, span, 1.0), 0.0)
    mask = np.zeros(len(close), dtype=bool)
    mask[1:] = ((close[1:] > open_[1:]) & (close[1:] > close[:-1])
                & (span[1:] > 0) & (close_location[1:] >= 0.60))
    return mask


# --------------------------------------------------------------------------- #
# evaluation
# --------------------------------------------------------------------------- #
def bars_payload(dates: np.ndarray, arrays: Mapping[str, np.ndarray], volume: np.ndarray,
                 start: int, stop: int) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for position in range(start, stop):
        payload.append({
            "date": ms_to_date(int(dates[position])),
            "open": float(arrays["open"][position]),
            "high": float(arrays["high"][position]),
            "low": float(arrays["low"][position]),
            "close": float(arrays["close"][position]),
            "volume": float(volume[position]),
        })
    return payload


def evaluate_symbol_rule(
    store: Mapping[str, Any],
    symbol_events: Sequence[tuple[float, ...]],
    code_position: int,
    rule_id: str,
    signal_ms: set[int],
) -> dict[str, Any]:
    """Enumerate C rule events for one (symbol, rule) pair."""

    start, stop = symbol_bounds(store, code_position)
    symbol = store["codes"][code_position]
    dates = store["date_ms"][start:stop]
    volume = store["volume"][start:stop]
    config = RULE_CANDIDATES[rule_id]
    candidates = [position for position in range(len(dates))
                  if position >= MIN_BARS - 1 and int(dates[position]) in signal_ms]
    diagnostics: Counter[str] = Counter()
    found: list[dict[str, Any]] = []
    if not candidates:
        return {"events": found, "diagnostics": dict(diagnostics), "candidates": 0}
    base_arrays = {field: store[field][start:stop] for field in PRICE_FIELDS}
    adjusted = {field: base_arrays[field].astype(np.float64, copy=True) for field in PRICE_FIELDS}
    event_dates = (np.asarray([item[0] for item in symbol_events], dtype=np.int64)
                   if symbol_events else np.zeros(0, dtype=np.int64))
    event_bounds = (np.searchsorted(event_dates, dates, side="right") if len(event_dates)
                    else np.zeros(len(dates), dtype=np.int64))
    applied = 0
    states: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for position in candidates:
        needed = int(event_bounds[position])
        while applied < needed:
            ex_date_ms, dividend, bonus, ratio, allotment_price = symbol_events[applied]
            mask = dates < ex_date_ms
            if mask.any():
                for field in PRICE_FIELDS:
                    adjusted[field][mask] = apply_event_values(
                        adjusted[field][mask], dividend, bonus, ratio, allotment_price)
            applied += 1
        state = states.get(applied)
        if state is None:
            state = (
                trend_prefilter(adjusted["close"], config),
                strong_up_close_mask(adjusted["open"], adjusted["high"], adjusted["low"],
                                     adjusted["close"]),
            )
            states[applied] = state
        if not (state[0][position] and state[1][position]):
            diagnostics["prefilter_rejected"] += 1
            continue
        diagnostics["prefilter_passed"] += 1
        prefix_start = max(0, position - PREFIX_BARS + 1)
        payload = bars_payload(dates, adjusted, volume, prefix_start, position + 1)
        try:
            observation = build_entry_observation(payload, rule_id=rule_id)
        except ValueError:
            diagnostics["rule_input_rejected"] += 1
            continue
        if not observation.get("entry_candidate"):
            diagnostics["rule_rejected"] += 1
            continue
        diagnostics["entry_candidates"] += 1
        structure = observation["structure"]
        volume_block = observation.get("volume") or {}
        resistance = observation.get("stage_resistance") or {}
        found.append({
            "symbol": symbol,
            "rule_id": rule_id,
            "signal_date": ms_to_date(int(dates[position])),
            "signal_index": start + position,
            "stage_prior_high_date": ms_to_date(int(dates[prefix_start + int(structure["peak_index"])])),
            "low_one_date": ms_to_date(int(dates[prefix_start + int(structure["low_one_index"])])),
            "low_two_date": ms_to_date(int(dates[prefix_start + int(structure["low_two_index"])])),
            "stage_prior_high": float(structure["stage_prior_high"]),
            "depth": float(structure["depth"]),
            "rebound_size": float(structure["rebound_size"]),
            "close_t": float(adjusted["close"][position]),
            "resistance_distance": resistance.get("distance_from_close"),
            "relative_volume_t": (volume_block.get("t_day_relative_volume") or {}).get(
                "relative_volume_ratio"),
        })
    return {"events": found, "diagnostics": dict(diagnostics), "candidates": len(candidates)}


def horizon_record(
    store: Mapping[str, Any],
    symbol_events: Sequence[tuple[float, ...]],
    calendar_index: Mapping[int, int],
    calendar_ms: Sequence[int],
    signal_index: int,
    signal_date: str,
    horizon: int,
    symbol_bounds_: tuple[int, int],
) -> dict[str, Any]:
    # Search inside the symbol's own contiguous slab: the global date array is
    # sorted by (symbol, date), so a global searchsorted would return a foreign
    # index and silently compare unrelated bars.
    slab_start, slab_stop = symbol_bounds_
    dates = store["date_ms"][slab_start:slab_stop]
    slab_signal = signal_index - slab_start
    signal_ms = int(dates[slab_signal])
    position = calendar_index.get(signal_ms)
    if position is None or position + horizon >= len(calendar_ms):
        return {"status": "HORIZON_OUTSIDE_FROZEN_CALENDAR"}
    target_ms = int(calendar_ms[position + horizon])
    local = int(np.searchsorted(dates, target_ms, side="left"))
    if local >= len(dates) or int(dates[local]) != target_ms or local <= slab_signal:
        return {"status": "MISSING_SESSION_AT_HORIZON", "missing_date": ms_to_date(target_ms)}
    values = anchor_arrays_for_range(store, symbol_events, signal_index, slab_start + local + 1, target_ms)
    closes = values["close"]
    record: dict[str, Any] = {
        "status": "OK",
        "horizon_sessions": horizon,
        "signal_date": signal_date,
        "horizon_date": ms_to_date(target_ms),
        "observation_return": float(closes[-1] / closes[0] - 1.0),
        "intervening_corporate_actions": count_events_in_window(symbol_events, signal_ms, target_ms),
    }
    if len(closes) > 1 and float(values["open"][1]) > 0:
        reference = float(values["open"][1])
        record["t_plus_one_reference_return"] = float(closes[-1] / reference - 1.0)
        record["mfe"] = float(np.max(values["high"][1:]) / reference - 1.0)
        record["mae"] = float(np.min(values["low"][1:]) / reference - 1.0)
    else:
        record["t_plus_one_reference_return"] = None
        record["mfe"] = None
        record["mae"] = None
    record["cost_after_return"] = COST_DECISION
    return record


def series_summary(values: Iterable[float | None]) -> dict[str, Any]:
    clean = [float(value) for value in values
             if value is not None and math.isfinite(float(value))]
    if not clean:
        return {"valid_n": 0, "status": "INSUFFICIENT_DATA"}
    array = np.asarray(clean, dtype=np.float64)
    return {
        "valid_n": int(array.size),
        "positive_n": int((array > 0).sum()),
        "positive_rate": float((array > 0).mean()),
        "mean": float(array.mean()),
        "median": float(np.median(array)),
        "min": float(array.min()),
        "max": float(array.max()),
        "status": "OK",
    }


def aggregate(records: Sequence[Mapping[str, Any]], observations: Mapping[int, Mapping[str, Any]],
              diagnostics: Mapping[str, int]) -> dict[str, Any]:
    """Aggregate per rule and window with explicit numerators and denominators."""

    result: dict[str, Any] = {}
    for rule_id in RULES:
        rule_records = [item for item in records if item["rule_id"] == rule_id]
        episodes: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = {}
        for item in rule_records:
            episodes.setdefault((item["symbol"], item["stage_prior_high_date"],
                                 item["low_one_date"], item["low_two_date"]), []).append(item)
        per_window: dict[str, Any] = {}
        for horizon in WINDOWS:
            key = f"T+{horizon}"
            rows = [observations[item["signal_index"]][key] for item in rule_records]
            computed = [row for row in rows if row.get("status") == "OK"]
            episode_rows: list[Mapping[str, Any]] = []
            for members in episodes.values():
                first = min(members, key=lambda item: item["signal_date"])
                episode_rows.append(observations[first["signal_index"]][key])
            per_window[key] = {
                "events": len(rows),
                "computed_events": len(computed),
                "missing_session_at_horizon": sum(
                    1 for row in rows if row.get("status") == "MISSING_SESSION_AT_HORIZON"),
                "horizon_outside_frozen_calendar": sum(
                    1 for row in rows if row.get("status") == "HORIZON_OUTSIDE_FROZEN_CALENDAR"),
                "observation_return": {
                    **series_summary(row.get("observation_return") for row in computed),
                    "denominator": "valid computed window observation returns",
                },
                "t_plus_one_reference_return": {
                    **series_summary(row.get("t_plus_one_reference_return") for row in computed),
                    "denominator": "valid computed T+1-open reference returns",
                },
                "mfe": series_summary(row.get("mfe") for row in computed),
                "mae": series_summary(row.get("mae") for row in computed),
                "episode_deduplicated_observation_return": series_summary(
                    row.get("observation_return") if row.get("status") == "OK" else None
                    for row in episode_rows),
                "intervening_corporate_action_events": sum(
                    1 for row in computed if row.get("intervening_corporate_actions")),
                "cost_after_return": {"status": COST_DECISION},
                "actual_trade_win_rate": {"status": "NOT_AVAILABLE_NO_ACTUAL_FILL_EVIDENCE"},
            }
        by_symbol = Counter(item["symbol"] for item in rule_records)
        per_window["corporate_action_events_applied_total"] = sum(
            item.get("intervening_corporate_actions", 0) or 0 for item in rule_records)
        year_windows: dict[str, Any] = {}
        for year in sorted({item["signal_date"][:4] for item in rule_records}):
            year_records = [item for item in rule_records if item["signal_date"].startswith(year)]
            year_windows[year] = {
                f"T+{horizon}": series_summary(
                    observations[item["signal_index"]][f"T+{horizon}"].get("observation_return")
                    if observations[item["signal_index"]][f"T+{horizon}"].get("status") == "OK"
                    else None
                    for item in year_records)
                for horizon in WINDOWS
            }
        result[rule_id] = {
            "rule_id": rule_id,
            "raw_event_count": len(rule_records),
            "deduplicated_episode_count": len(episodes),
            "repeated_confirmation_degree": {
                "max_confirmations_in_one_episode": max((len(value) for value in episodes.values()),
                                                        default=0),
                "episodes_with_multiple_confirmations": sum(
                    1 for value in episodes.values() if len(value) > 1),
            },
            "symbol_concentration": {
                "symbols_with_events": len(by_symbol),
                "max_events_for_one_symbol": max(by_symbol.values(), default=0),
                "top_symbol_event_share": (max(by_symbol.values()) / len(rule_records))
                if rule_records else None,
            },
            "year_distribution": dict(sorted(Counter(item["signal_date"][:4]
                                                     for item in rule_records).items())),
            "month_distribution": dict(sorted(Counter(item["signal_date"][:7]
                                                      for item in rule_records).items())),
            "year_window_observation_returns": year_windows,
            "volume_description": {
                "status": "DESCRIPTIVE_ONLY_VOLUME_BASIS_UNVERIFIED",
                "t_day_relative_volume": series_summary(item.get("relative_volume_t")
                                                        for item in rule_records),
            },
            "prefilter_counts": {name: value for name, value in diagnostics.items()
                                 if name.endswith(rule_id)},
            "windows": per_window,
        }
    return result


# --------------------------------------------------------------------------- #
# verification helpers
# --------------------------------------------------------------------------- #
def structure_signature(observation: Mapping[str, Any], offset: int) -> tuple[Any, ...]:
    structure = observation.get("structure") or {}
    def shift(value: Any) -> Any:
        return None if value is None else int(value) + offset
    return (
        bool(observation.get("entry_candidate")),
        structure.get("status"),
        shift(structure.get("peak_index")),
        shift(structure.get("low_one_index")),
        shift(structure.get("low_two_index")),
    )


def verify_prefix_invariance(store: Mapping[str, Any],
                             events: Mapping[str, Sequence[tuple[float, ...]]],
                             signal_ms: set[int], samples: int, seed: int = 20260924) -> dict[str, Any]:
    """Prove the 120-bar prefix does not truncate history the rule depends on."""

    rng = np.random.default_rng(seed)
    codes = store["codes"]
    # The compared prefixes are all valid rule inputs.  A full-history prefix is
    # probed separately because decades of cumulative cash dividends can drive the
    # reconstructed T-anchor price to <= 0, which the frozen pure functions reject
    # as invalid input (a rejected input is not a rule result).
    spans: tuple[int, ...] = (PREFIX_BARS, 250, 500)
    checks = 0
    mismatches: list[dict[str, Any]] = []
    full_history_rejections = 0
    full_history_checks = 0
    attempts = 0
    while checks < samples and attempts < samples * 60:
        attempts += 1
        code_position = int(rng.integers(0, len(codes)))
        symbol_events = events.get(codes[code_position], [])
        start, stop = symbol_bounds(store, code_position)
        length = stop - start
        if length <= MIN_BARS:
            continue
        position = int(rng.integers(MIN_BARS - 1, length))
        anchor = int(store["date_ms"][start + position])
        if anchor not in signal_ms:
            continue
        checks += 1
        rule_id = RULES[checks % len(RULES)]
        signatures: list[tuple[Any, ...]] = []
        for span in spans:
            prefix_start = max(0, position - span + 1)
            values = anchor_arrays_for_range(store, symbol_events, start + prefix_start,
                                             start + position + 1, anchor)
            payload = bars_payload(store["date_ms"][start + prefix_start:start + position + 1],
                                   values, store["volume"][start + prefix_start:start + position + 1],
                                   0, position + 1 - prefix_start)
            try:
                observation = build_entry_observation(payload, rule_id=rule_id)
                signatures.append(structure_signature(observation, prefix_start))
            except ValueError:
                signatures.append(("RULE_INPUT_REJECTED", None, None, None, None))
        if len(set(signatures)) != 1:
            mismatches.append({
                "symbol": codes[code_position],
                "signal_date": ms_to_date(anchor),
                "rule_id": rule_id,
                "signatures": [list(item) for item in signatures],
            })
        if (
            store["date_ms"][start] < anchor
            and len(store["date_ms"][start:start + position + 1]) > PREFIX_BARS
        ):
            full_history_checks += 1
            full_values = anchor_arrays_for_range(store, symbol_events, start, start + position + 1, anchor)
            full_payload = bars_payload(store["date_ms"][start:start + position + 1], full_values,
                                        store["volume"][start:start + position + 1], 0, position + 1)
            try:
                build_entry_observation(full_payload, rule_id=rule_id)
            except ValueError:
                full_history_rejections += 1
    return {
        "status": "PASS" if not mismatches else "FAIL",
        "checks": checks,
        "spans_compared": list(spans),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches[:20],
        "full_history_probe": {
            "checked": full_history_checks,
            "rule_input_rejected": full_history_rejections,
            "note": "full-history T-anchor prefixes can contain non-positive reconstructed "
                    "prices that the frozen pure functions reject; those are invalid inputs, "
                    "not rule results, so they are reported separately",
        },
    }


def verify_prefilter_superset(store: Mapping[str, Any],
                              events: Mapping[str, Sequence[tuple[float, ...]]],
                              signal_ms: set[int], samples: int,
                              seed: int = 20260925) -> dict[str, Any]:
    """Randomised check that prefilter-negative rows are never entry candidates."""

    rng = np.random.default_rng(seed)
    codes = store["codes"]
    inspected = 0
    false_negatives: list[dict[str, Any]] = []
    attempts = 0
    while inspected < samples and attempts < samples * 60:
        attempts += 1
        code_position = int(rng.integers(0, len(codes)))
        symbol_events = events.get(codes[code_position], [])
        start, stop = symbol_bounds(store, code_position)
        length = stop - start
        if length <= MIN_BARS:
            continue
        position = int(rng.integers(MIN_BARS - 1, length))
        anchor = int(store["date_ms"][start + position])
        if anchor not in signal_ms:
            continue
        rule_id = RULES[inspected % len(RULES)]
        values = anchor_arrays_for_range(store, symbol_events, start, stop, anchor)
        if (trend_prefilter(values["close"], RULE_CANDIDATES[rule_id])[position]
                and strong_up_close_mask(values["open"], values["high"], values["low"],
                                         values["close"])[position]):
            continue
        inspected += 1
        payload_start = position - PREFIX_BARS + 1
        payload = bars_payload(store["date_ms"][start:stop], values, store["volume"][start:stop],
                               payload_start, position + 1)
        try:
            observation = build_entry_observation(payload, rule_id=rule_id)
        except ValueError:
            continue
        if observation.get("entry_candidate"):
            false_negatives.append({
                "symbol": codes[code_position],
                "signal_date": ms_to_date(anchor),
                "rule_id": rule_id,
            })
    return {
        "status": "PASS" if not false_negatives else "FAIL",
        "prefilter_negative_rows_inspected": inspected,
        "false_negative_count": len(false_negatives),
        "false_negatives": false_negatives[:20],
    }


def continuity_diagnostics(store: Mapping[str, Any],
                           events: Mapping[str, Sequence[tuple[float, ...]]],
                           sample_limit: int = 5) -> dict[str, Any]:
    """Compare raw versus T-anchor close-to-close moves across ex-dates."""

    worst_raw = (0.0, None)
    worst_anchor = (0.0, None)
    samples: list[dict[str, Any]] = []
    ex_date_hits = 0
    raw_abs_total = 0.0
    anchor_abs_total = 0.0
    raw_gaps_over_two_pct = 0
    anchor_gaps_over_two_pct = 0
    for code_position, code in enumerate(store["codes"]):
        symbol_events = events.get(code)
        if not symbol_events:
            continue
        start, stop = symbol_bounds(store, code_position)
        dates = store["date_ms"][start:stop]
        closes = store["close"][start:stop]
        for ex_date_ms, *_ in symbol_events:
            local = int(np.searchsorted(dates, int(ex_date_ms), side="left"))
            if local <= 0 or local >= len(dates) or int(dates[local]) != int(ex_date_ms):
                continue
            ex_date_hits += 1
            raw_jump = float(closes[local] / closes[local - 1] - 1.0)
            anchored = anchor_arrays_for_range(store, symbol_events, start + local - 1, start + local + 1,
                                               int(ex_date_ms))
            anchor_jump = float(anchored["close"][1] / anchored["close"][0] - 1.0)
            raw_abs_total += abs(raw_jump)
            anchor_abs_total += abs(anchor_jump)
            raw_gaps_over_two_pct += int(abs(raw_jump) >= 0.02)
            anchor_gaps_over_two_pct += int(abs(anchor_jump) >= 0.02)
            if abs(raw_jump) > abs(worst_raw[0]):
                worst_raw = (raw_jump, {"symbol": code, "ex_date": ms_to_date(int(ex_date_ms))})
            if abs(anchor_jump) > abs(worst_anchor[0]):
                worst_anchor = (anchor_jump, {"symbol": code, "ex_date": ms_to_date(int(ex_date_ms))})
            if abs(raw_jump) >= 0.02 and len(samples) < sample_limit:
                samples.append({
                    "symbol": code,
                    "ex_date": ms_to_date(int(ex_date_ms)),
                    "raw_close_to_close": raw_jump,
                    "anchor_close_to_close": anchor_jump,
                })
    return {
        "ex_date_observations": ex_date_hits,
        "mean_abs_raw_jump": (raw_abs_total / ex_date_hits) if ex_date_hits else None,
        "mean_abs_anchor_jump": (anchor_abs_total / ex_date_hits) if ex_date_hits else None,
        "raw_gaps_over_2pct": raw_gaps_over_two_pct,
        "anchor_gaps_over_2pct": anchor_gaps_over_two_pct,
        "largest_abs_raw_jump": {"return": worst_raw[0], **(worst_raw[1] or {})},
        "largest_abs_anchor_jump": {"return": worst_anchor[0], **(worst_anchor[1] or {})},
        "sample_rows": samples,
        "interpretation": "T-anchor reconstruction removes the mechanical ex-date gap; "
                          "this is a numeric property check, not a PIT claim.",
    }


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #
def run_exploration(raw_dir: Path, manifest_path: Path, output_root: Path, *,
                    prefix_checks: int = 400, prefilter_checks: int = 2000,
                    symbol_limit: int | None = None) -> dict[str, Any]:
    verification = verify_inputs(raw_dir, manifest_path)
    if verification["status"] != "HASH_VERIFIED":
        blocked = {"terminal_status": "C_RAW_T_ANCHOR_EXPLORATION_BLOCKED_BY_INPUT_IDENTITY_GAP",
                   "input_verification": verification}
        write_json(output_root / "blocked_diagnostics.json", blocked)
        return blocked
    contract = load_frozen_contract(manifest_path)
    signal_ms_list = contract["signal_ms"]
    signal_ms = set(signal_ms_list)
    calendar_index = {value: index for index, value in enumerate(signal_ms_list)}
    events, event_counters = load_corporate_actions(raw_dir / "adjustment_factors.parquet")
    store = load_daily_bars(raw_dir / "daily_k.parquet")
    codes = store["codes"]
    main_board = [position for position, code in enumerate(codes) if classify_board(code) == BOARD_MAIN]
    if symbol_limit is not None:
        main_board = main_board[:symbol_limit]
    prefix_check = verify_prefix_invariance(store, events, signal_ms, prefix_checks)
    prefilter_check = verify_prefilter_superset(store, events, signal_ms, prefilter_checks)
    if prefix_check["status"] != "PASS" or prefilter_check["status"] != "PASS":
        blocked = {"terminal_status": "C_RAW_T_ANCHOR_EXPLORATION_BLOCKED_BY_RULE_REPRODUCIBILITY",
                   "input_verification": verification,
                   "prefix_invariance": prefix_check,
                   "prefilter_superset": prefilter_check}
        write_json(output_root / "blocked_diagnostics.json", blocked)
        return blocked
    diagnostics: Counter[str] = Counter()
    records: list[dict[str, Any]] = []
    for processed, code_position in enumerate(main_board, start=1):
        code = codes[code_position]
        start, stop = symbol_bounds(store, code_position)
        diagnostics["main_board_symbols"] += 1
        if stop - start < MIN_BARS:
            diagnostics["symbols_below_min_bars"] += 1
            continue
        symbol_events = events.get(code, [])
        for rule_id in RULES:
            outcome = evaluate_symbol_rule(store, symbol_events, code_position, rule_id, signal_ms)
            diagnostics[f"rule_bar_candidates_{rule_id}"] += outcome["candidates"]
            for name, value in outcome["diagnostics"].items():
                diagnostics[f"{name}_{rule_id}"] += value
            records.extend(outcome["events"])
            del outcome
        if processed % 500 == 0:
            print(f"[progress] symbols={processed}/{len(main_board)} events={len(records)}", flush=True)
    observations: dict[int, dict[str, Any]] = {}
    bounds_by_symbol = {code: symbol_bounds(store, position)
                        for position, code in enumerate(codes)}
    for record in records:
        observations[record["signal_index"]] = {
            f"T+{horizon}": horizon_record(store, events.get(record["symbol"], []), calendar_index,
                                           signal_ms_list, record["signal_index"],
                                           record["signal_date"], horizon,
                                           bounds_by_symbol[record["symbol"]])
            for horizon in WINDOWS
        }
    summary = {
        "schema_version": "C_RAW_T_ANCHOR_LIMITED_EXPLORATION_SUMMARY_V1",
        "study_id": STUDY_ID,
        "terminal_status": "C_RAW_T_ANCHOR_EXPLORATION_COMPLETED",
        "input_identity": INPUT_IDENTITY,
        "sample_identity": SAMPLE_IDENTITY,
        "not_the_identity": "C_QFQ_INPUT_V1",
        "input_verification": verification,
        "corporate_action_counters": event_counters,
        "calendar": {
            "signal_dates": len(signal_ms_list),
            "first": contract["signal_dates"][0],
            "last": contract["signal_dates"][-1],
            "universe_semantics": contract["universe_semantics"],
        },
        "evaluation": {
            "rules": list(RULES),
            "windows": [f"T+{value}" for value in WINDOWS],
            "minimum_bars": MIN_BARS,
            "prefix_bars": PREFIX_BARS,
            "universe": "Main Board 00/60 only; ST status UNVERIFIED (not formal C universe)",
            "cost_model": COST_DECISION,
        },
        "verification": {
            "prefix_invariance": prefix_check,
            "prefilter_superset": prefilter_check,
            "continuity": continuity_diagnostics(store, events),
        },
        "diagnostics": dict(diagnostics),
        "results": aggregate(records, observations, diagnostics),
        "evidence_gaps": {
            "historical_t_known_st": "UNRESOLVED; sample is ST_STATUS_UNVERIFIED and is not the "
                                     "formal C universe",
            "per_bar_known_at_or_vintage": "MISSING; T-anchor reconstruction stays "
                                           "PARTIAL_UNVERIFIED",
            "c_qfq_input": "NOT_APPLICABLE; this exploration is not C_QFQ_INPUT_V1",
            "execution_and_fill": "UNAVAILABLE; T+1 open is a reference price only",
            "transaction_cost_model": COST_DECISION,
            "volume_basis": "VOLUME_BASIS_UNVERIFIED; descriptive only, never a gate",
            "intraday_limit_or_break_sequence": "UNAVAILABLE; daily OHLCV cannot establish "
                                                "intraday order",
        },
        "final_oos": "SEALED / UNREAD",
        "formal_b_changed": False,
        "runtime_state_modified": False,
        "provider_calls": 0,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    write_json(output_root / "input_verification.json", verification)
    write_json(output_root / "events.json", {
        "schema_version": "C_RAW_T_ANCHOR_EVENTS_V1",
        "study_id": STUDY_ID,
        "rules": list(RULES),
        "event_count": len(records),
        "events": [{**record, "windows": observations[record["signal_index"]]} for record in records],
    })
    write_json(output_root / "summary.json", summary)
    return summary


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Explicit LF keeps the working-tree bytes identical to the Git blob so the
    # recorded SHA-256 stays stable across devices (FROZEN_ARTIFACT_POLICY).
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8",
                    newline="\n")


def _pct(value: Any, digits: int = 2) -> str:
    return "n/a" if value is None or isinstance(value, str) else f"{value * 100:.{digits}f}%"


def _num(value: Any, digits: int = 4) -> str:
    return "n/a" if value is None or isinstance(value, str) else f"{value:.{digits}f}"


def render_report(summary: Mapping[str, Any]) -> str:
    """Render the human-readable report strictly from the machine-readable summary."""

    lines: list[str] = []
    results = summary.get("results", {})
    verification = summary.get("verification", {})
    lines.append("# C_RAW_T_ANCHOR_LIMITED_EXPLORATION_V1 — 证据受限历史探索报告\n")
    lines.append(f"- 研究身份：`{summary['study_id']}` / 输入身份 `{summary['input_identity']}`")
    lines.append(f"- 样本身份：`{summary['sample_identity']}`（**不是** formal C universe）")
    lines.append(f"- **不是** `C_QFQ_INPUT_V1` 结果；#87 的原始阻断结论保持有效，未被重新解释")
    lines.append(f"- 最终状态：`{summary.get('terminal_status', 'C_RAW_T_ANCHOR_EXPLORATION_COMPLETED')}`")
    calendar = summary.get("calendar", {})
    lines.append(f"- 日历：{calendar.get('signal_dates')} 个 XSHG session "
                 f"({calendar.get('first')} – {calendar.get('last')})")
    lines.append(f"- Formal B 变更：`{summary.get('formal_b_changed')}`；"
                 f"runtime-state 变更：`{summary.get('runtime_state_modified')}`；"
                 f"provider calls：`{summary.get('provider_calls')}`；"
                 f"Final OOS：`{summary.get('final_oos')}`\n")
    lines.append("## 1. 输入身份与转换规则核验\n")
    files = summary.get("input_verification", {}).get("files", {})
    lines.append("| 输入 | 字节 | SHA-256 | 状态 |")
    lines.append("| --- | ---: | --- | --- |")
    for key, record in files.items():
        digest = record.get("sha256", "")
        if record.get("canonical_text_sha256"):
            digest = f"{record['canonical_text_sha256']} (LF-normalised)"
        lines.append(f"| `{record.get('logical_path')}` | {record.get('bytes')} | `{digest}` "
                     f"| `{record.get('status')}` |")
    contract = summary.get("input_verification", {}).get("declared_contract", {})
    lines.append(f"\n声明公式：`{contract.get('formula')}`；事件过滤：`{contract.get('event_filter')}`；"
                 f"顺序：`{contract.get('event_order')}`；volume：`{contract.get('volume_semantics')}`。")
    continuity = verification.get("continuity", {})
    lines.append(f"\n除权日连续性核验：观察 `{continuity.get('ex_date_observations')}` 个 ex-date；"
                 f"平均绝对跳变 raw `{_pct(continuity.get('mean_abs_raw_jump'))}` → "
                 f"T-anchor `{_pct(continuity.get('mean_abs_anchor_jump'))}`；"
                 f"|跳变|≥2% 的 ex-date 数 raw `{continuity.get('raw_gaps_over_2pct')}` → "
                 f"T-anchor `{continuity.get('anchor_gaps_over_2pct')}`；"
                 f"最大 raw 跳变 `{_pct(continuity.get('largest_abs_raw_jump', {}).get('return'))}`，"
                 f"最大 T-anchor 重建跳变 "
                 f"`{_pct(continuity.get('largest_abs_anchor_jump', {}).get('return'))}`。")
    prefix = verification.get("prefix_invariance", {})
    lines.append(f"\n前缀不变性：`{prefix.get('status')}`，比较跨度 {prefix.get('spans_compared')}，"
                 f"检查 {prefix.get('checks')} 个 (symbol, T)，不一致 {prefix.get('mismatch_count')}。")
    probe = prefix.get("full_history_probe", {})
    if probe:
        lines.append(f"全历史对照探针：{probe.get('checked')} 次中 "
                     f"{probe.get('rule_input_rejected')} 次因重建价格非正被冻结纯函数判为非法输入。")
    prefilter = verification.get("prefilter_superset", {})
    lines.append(f"\n预筛超集验证：`{prefilter.get('status')}`，检查 "
                 f"{prefilter.get('prefilter_negative_rows_inspected')} 个被预筛拒绝的 (symbol, T)，"
                 f"假阴性 {prefilter.get('false_negative_count')}。\n")
    lines.append("## 2. 事件数量与样本\n")
    lines.append("| rule | 原始事件 | 去重 episode | 涉及股票 | 单股票最大事件 | 同一 episode 多次确认 |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    for rule_id in RULES:
        block = results.get(rule_id, {})
        concentration = block.get("symbol_concentration", {})
        repeated = block.get("repeated_confirmation_degree", {})
        lines.append(f"| `{rule_id}` | {block.get('raw_event_count')} | "
                     f"{block.get('deduplicated_episode_count')} | "
                     f"{concentration.get('symbols_with_events')} | "
                     f"{concentration.get('max_events_for_one_symbol')} | "
                     f"{repeated.get('episodes_with_multiple_confirmations')} |")
    lines.append("\n枚举口径：`entry_candidate=True`，universe 为沪深 00/60 主板、"
                 "ST 状态未核验；预筛只是必要条件的加速，已验证为超集。\n")
    lines.append("## 3. T+3 / T+5 / T+10 观察统计\n")
    for rule_id in RULES:
        block = results.get(rule_id, {})
        lines.append(f"### {rule_id}\n")
        lines.append("| 窗口 | 事件 | 可计算 | 缺失 session | 正收益比例 | 平均 | 中位 | "
                     "T+1 开盘参考正比例 | 参考平均 | MFE 均值 | MAE 均值 |")
        lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
        for horizon in WINDOWS:
            key = f"T+{horizon}"
            window = block.get("windows", {}).get(key, {})
            observation = window.get("observation_return", {})
            reference = window.get("t_plus_one_reference_return", {})
            lines.append(
                f"| {key} | {window.get('events')} | {window.get('computed_events')} | "
                f"{window.get('missing_session_at_horizon')} | "
                f"{_pct(observation.get('positive_rate'))} "
                f"({observation.get('positive_n')}/{observation.get('valid_n')}) | "
                f"{_num(observation.get('mean'))} | {_num(observation.get('median'))} | "
                f"{_pct(reference.get('positive_rate'))} "
                f"({reference.get('positive_n')}/{reference.get('valid_n')}) | "
                f"{_num(reference.get('mean'))} | {_num(window.get('mfe', {}).get('mean'))} | "
                f"{_num(window.get('mae', {}).get('mean'))} |")
        episode_cells = []
        for horizon in WINDOWS:
            episode = block.get("windows", {}).get(f"T+{horizon}", {}).get(
                "episode_deduplicated_observation_return", {})
            episode_cells.append(f"{_pct(episode.get('positive_rate'))} "
                                 f"({episode.get('positive_n')}/{episode.get('valid_n')})")
        lines.append(f"\nepisode 去重后的正收益比例（T+3 / T+5 / T+10）：{' / '.join(episode_cells)}。")
        lines.append(f"\n成本边界：`{COST_DECISION}`；实际成交胜率："
                     f"`NOT_AVAILABLE_NO_ACTUAL_FILL_EVIDENCE`。")
        year_block = block.get("year_distribution", {})
        if year_block:
            lines.append("\n按年事件数：" + "，".join(f"{year} {count}"
                                                    for year, count in year_block.items()) + "。")
        year_windows = block.get("year_window_observation_returns", {})
        if year_windows:
            lines.append("\n按年正收益观察比例（T+3 / T+5 / T+10，分子/分母）：\n")
            lines.append("| 年份 | T+3 | T+5 | T+10 |")
            lines.append("| --- | --- | --- | --- |")
            for year, windows in year_windows.items():
                cells = []
                for horizon in WINDOWS:
                    value = windows.get(f"T+{horizon}", {})
                    cells.append(f"{_pct(value.get('positive_rate'))} "
                                 f"({value.get('positive_n')}/{value.get('valid_n')})")
                lines.append(f"| {year} | {' | '.join(cells)} |")
        volume = block.get("volume_description", {})
        relative = volume.get("t_day_relative_volume", {})
        lines.append(f"\n量能描述（`{volume.get('status')}`，仅描述、不作 gate）：T 日 RV 有效 "
                     f"{relative.get('valid_n')}，中位 {_num(relative.get('median'))}，"
                     f"均值 {_num(relative.get('mean'))}。")
        month_block = block.get("month_distribution", {})
        if len(month_block) > 12:
            busiest = sorted(month_block.items(), key=lambda item: -item[1])[:5]
            lines.append("事件最多的月份：" + "，".join(f"{month} {count}"
                                                       for month, count in busiest) + "。")
        lines.append("")
    lines.append("## 4. 不能计算的项目与证据缺口\n")
    gaps = summary.get("evidence_gaps", {})
    lines.append("| 缺口 | 状态 |")
    lines.append("| --- | --- |")
    for name, value in gaps.items():
        lines.append(f"| `{name}` | {value} |")
    lines.append("\n## 5. 诊断计数\n")
    for name, value in sorted(summary.get("diagnostics", {}).items()):
        lines.append(f"- `{name}` = {value}")
    lines.append("\n## 6. 判读边界\n")
    lines.append("- 这些正收益比例是**观察统计**，不是策略胜率、不是 OOS 证据、不是可执行收益。")
    lines.append("- 样本未核验历史 ST/*ST，因此**不满足** formal `C_MAIN_BOARD_NON_ST_V1` 的 PIT 有效样本条件。")
    lines.append("- T-anchor 重建缺逐 bar vintage 证明，状态保持 `PARTIAL_UNVERIFIED`。")
    lines.append("- 量能语义未核验，仅作描述，不构成确认。")
    lines.append("- 本报告不得被引用为 `C_QFQ_INPUT_V1` 的正式回测结论，也不改变 #87 的原始阻断结论。")
    return "\n".join(lines) + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="C raw T-anchor limited exploration")
    parser.add_argument("--raw-dir", default="data/validation/core_signal_validation/raw")
    parser.add_argument("--manifest", default=MANIFEST_LOGICAL_PATH)
    parser.add_argument("--output-root", default=str(OUTPUT_ROOT))
    parser.add_argument("--prefix-checks", type=int, default=400)
    parser.add_argument("--prefilter-checks", type=int, default=2000)
    parser.add_argument("--symbol-limit", type=int, default=None)
    parser.add_argument("--verify-inputs-only", action="store_true")
    parser.add_argument("--render-from", default=None,
                        help="render report.md from an existing summary.json without re-running")
    parser.add_argument("--report-path", default=None,
                        help="report destination; defaults to <output-root>/report.md")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.render_from:
        summary = json.loads(Path(args.render_from).read_text(encoding="utf-8"))
        report_path = Path(args.report_path) if args.report_path else Path(args.output_root) / "report.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(render_report(summary), encoding="utf-8", newline="\n")
        print(f"wrote {report_path}")
        return 0
    if args.verify_inputs_only:
        print(json.dumps(verify_inputs(Path(args.raw_dir), Path(args.manifest)),
                         ensure_ascii=False, indent=1))
        return 0
    summary = run_exploration(
        Path(args.raw_dir), Path(args.manifest), Path(args.output_root),
        prefix_checks=args.prefix_checks, prefilter_checks=args.prefilter_checks,
        symbol_limit=args.symbol_limit,
    )
    print(json.dumps({
        "terminal_status": summary.get("terminal_status", "C_RAW_T_ANCHOR_EXPLORATION_COMPLETED"),
        "verification": summary.get("verification", {}).get("prefix_invariance"),
        "prefilter": summary.get("verification", {}).get("prefilter_superset"),
        "diagnostics": summary.get("diagnostics"),
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
