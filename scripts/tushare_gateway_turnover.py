"""Bounded third-party Tushare-compatible turnover acquisition.

This module is intentionally separate from the historical AkShare acquisition.
It uses only ``daily_basic`` through the explicitly classified
``THIRD_PARTY_TUSHARE_COMPATIBLE_GATEWAY`` and never changes B semantics.

All artifacts produced here remain DEVELOPMENT / RECONSTRUCTED_RETROSPECTIVE /
DATE_ANCHORED / NO_VINTAGE_PROOF / THIRD_PARTY_GATEWAY / DIAGNOSTIC_ONLY.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
import numbers
import os
from pathlib import Path
import sqlite3
import tempfile
import time
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

import core_signal_replay as replay
import validate_development_returns as returns_v1
from strategy_development_eligibility import _frozen_timing, _next_execution_date


SCHEMA_VERSION = "B_TURNOVER_X_RELATIVE_VOLUME_INCREMENTAL_DIAGNOSTIC_V1"
SOURCE_CLASSIFICATION = "THIRD_PARTY_TUSHARE_COMPATIBLE_GATEWAY"
GATEWAY_URL = "https://tuaremax.top"
PACKAGE_NAME = "tushare"
PACKAGE_VERSION = "1.4.24"
ENDPOINT = "daily_basic"
FIELDS = "ts_code,trade_date,turnover_rate,float_share"
REQUIRED_COLUMNS = ("ts_code", "trade_date", "turnover_rate", "float_share")
START_DATE = "2023-06-30"
END_DATE = "2026-08-28"
START_DATE_PROVIDER = "20230630"
END_DATE_PROVIDER = "20260828"
EXPECTED_SESSION_COUNT = 769
PILOT_YEAR_DATES = ("2024", "2025", "2026")
PILOT_COUNT = 5
SAMPLE_SIZE = 100
MIN_DATE_COVERAGE = 0.98
MIN_AGGREGATE_COVERAGE = 0.98
MIN_SEMANTICS_MATCH = 0.95
LABELS = (
    "DEVELOPMENT",
    "RECONSTRUCTED_RETROSPECTIVE",
    "DATE_ANCHORED",
    "NO_VINTAGE_PROOF",
    "THIRD_PARTY_GATEWAY",
    "DIAGNOSTIC_ONLY",
)
STOP_SCHEMA = "TUSHARE_GATEWAY_SCHEMA_NOT_RESEARCH_READY"
STOP_COVERAGE = "TUSHARE_GATEWAY_COVERAGE_NOT_RESEARCH_READY"
STOP_SEMANTICS = "TUSHARE_GATEWAY_TURNOVER_SEMANTICS_NOT_RESEARCH_READY"
STOP_FULL = "TUSHARE_GATEWAY_FULL_ACQUISITION_NOT_RESEARCH_READY"
OUTCOME_ACCESS_STATUS = "SCHEMA_SAMPLE_OBSERVED_NOT_USED"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _reject_forbidden(paths: Iterable[Path]) -> None:
    for path in paths:
        lowered = str(path).lower().replace("\\", "/")
        if "continuous_speed_probe" in lowered or "final_oos" in lowered:
            raise RuntimeError(f"forbidden path in Tushare gateway workflow: {path}")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        _canonical_json(payload) + "\n", encoding="utf-8", newline="\n"
    )
    os.replace(temporary, path)


def _canonical_json(value: Any) -> str:
    return __import__("json").dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _exception_class_chain(exc: BaseException) -> list[str]:
    names: list[str] = []
    queue: list[BaseException] = [exc]
    seen: set[int] = set()
    while queue:
        current = queue.pop(0)
        if id(current) in seen:
            continue
        seen.add(id(current))
        names.append(type(current).__name__)
        for attribute in ("__cause__", "__context__", "reason"):
            nested = getattr(current, attribute, None)
            if isinstance(nested, BaseException):
                queue.append(nested)
        for argument in getattr(current, "args", ()):
            if isinstance(argument, BaseException):
                queue.append(argument)
    return names


def _as_json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    try:
        import pandas as pd

        if bool(pd.isna(value)):
            return None
    except (ImportError, TypeError, ValueError):
        pass
    return value


def _frame_payload(frame: Any, trade_date: str) -> dict[str, Any]:
    columns = [str(value) for value in frame.columns]
    rows: list[dict[str, Any]] = []
    for raw in frame.to_dict(orient="records"):
        rows.append({str(key): _as_json_value(value) for key, value in raw.items()})
    return {
        "source_classification": SOURCE_CLASSIFICATION,
        "gateway_url": GATEWAY_URL,
        "package": PACKAGE_NAME,
        "package_version": PACKAGE_VERSION,
        "endpoint": ENDPOINT,
        "request": {"trade_date": trade_date, "fields": FIELDS},
        "response": {"columns": columns, "rows": rows},
        "response_row_count": len(rows),
    }


def _credentialed_client() -> Any:
    token = os.environ.get("TUSHARE_GATEWAY_TOKEN")
    if not token:
        raise RuntimeError("TUSHARE_GATEWAY_CREDENTIAL_NOT_AVAILABLE")
    import tushare as ts

    version = str(getattr(ts, "__version__", ""))
    if version != PACKAGE_VERSION:
        raise RuntimeError(f"{STOP_SCHEMA}: tushare version must be {PACKAGE_VERSION}")
    pro = ts.pro_api(token)
    pro._DataApi__token = token
    pro._DataApi__http_url = GATEWAY_URL
    if pro._DataApi__http_url != GATEWAY_URL:
        raise RuntimeError(f"{STOP_SCHEMA}: gateway URL was not applied")
    return pro


def _board(symbol: str) -> str | None:
    code = str(symbol).split(".", 1)[0].strip().zfill(6)
    suffix = str(symbol).split(".", 1)[1].lower() if "." in str(symbol) else ""
    if suffix not in {"sz", "sh"}:
        return None
    if code.startswith(("00", "60")):
        return "Main"
    if code.startswith("30"):
        return "ChiNext"
    if code.startswith("68"):
        return "STAR"
    return None


def _canonical_symbol(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if "." not in text:
        return None
    code, suffix = text.split(".", 1)
    code = code.strip().zfill(6)
    suffix = suffix.strip().lower()
    if suffix not in {"sz", "sh"} or len(code) != 6 or not code.isdigit():
        return None
    symbol = f"{code}.{suffix}"
    return symbol if _board(symbol) is not None else None


def _date_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        text = text[:10]
    elif len(text) == 8 and text.isdigit():
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    try:
        parsed = np.datetime64(text, "D")
    except (TypeError, ValueError):
        return None
    return str(parsed) if str(parsed) == text else None


def _numeric_or_null(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, numbers.Number):
        return None if str(value).strip().lower() in {"nan", "none", "null", "nat", "<na>"} else float("nan")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return float("nan")
    return number if math.isfinite(number) else None


def _schema_audit(payload: Mapping[str, Any], requested_date: str, *, strict_unique: bool) -> dict[str, Any]:
    response = payload.get("response")
    if not isinstance(response, Mapping):
        raise RuntimeError(f"{STOP_SCHEMA}: response object missing")
    columns = [str(value) for value in response.get("columns", [])]
    rows = response.get("rows")
    if not rows:
        raise RuntimeError(f"{STOP_SCHEMA}: empty response for {requested_date}")
    if not all(column in columns for column in REQUIRED_COLUMNS):
        raise RuntimeError(f"{STOP_SCHEMA}: required columns missing for {requested_date}")
    seen: dict[str, tuple[Any, Any, Any]] = {}
    duplicate_count = 0
    conflicting: list[str] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise RuntimeError(f"{STOP_SCHEMA}: non-object row for {requested_date}")
        row_date = _date_text(row.get("trade_date"))
        if row_date != requested_date:
            raise RuntimeError(f"{STOP_SCHEMA}: trade_date mismatch for {requested_date}")
        symbol = str(row.get("ts_code", "")).strip()
        if not symbol:
            raise RuntimeError(f"{STOP_SCHEMA}: blank ts_code for {requested_date}")
        turnover = _numeric_or_null(row.get("turnover_rate"))
        float_share = _numeric_or_null(row.get("float_share"))
        if isinstance(turnover, float) and math.isnan(turnover):
            raise RuntimeError(f"{STOP_SCHEMA}: non-numeric turnover_rate for {requested_date}")
        if isinstance(float_share, float) and math.isnan(float_share):
            raise RuntimeError(f"{STOP_SCHEMA}: non-numeric float_share for {requested_date}")
        if turnover is not None and turnover < 0:
            raise RuntimeError(f"{STOP_SCHEMA}: negative turnover_rate for {requested_date}")
        if float_share is not None and float_share < 0:
            raise RuntimeError(f"{STOP_SCHEMA}: negative float_share for {requested_date}")
        signature = (turnover, float_share, row_date)
        if symbol in seen:
            duplicate_count += 1
            if seen[symbol] != signature:
                conflicting.append(symbol)
        else:
            seen[symbol] = signature
    if conflicting:
        raise RuntimeError(f"{STOP_SCHEMA}: conflicting duplicate ts_code for {requested_date}")
    if strict_unique and duplicate_count:
        raise RuntimeError(f"{STOP_SCHEMA}: duplicate ts_code for {requested_date}")
    return {
        "status": "PASS",
        "requested_date": requested_date,
        "row_count": len(rows),
        "columns": columns,
        "unique_ts_code_count": len(seen),
        "duplicate_rows": duplicate_count,
        "strict_unique": strict_unique,
        "numeric_null_policy": "numeric or null; non-numeric rejected",
    }


def _session_dates(raw_dir: Path) -> list[str]:
    dates, _bars, _meta = replay._load_index(raw_dir)
    selected = sorted(value for value in dates if START_DATE <= value <= END_DATE)
    if len(selected) != EXPECTED_SESSION_COUNT:
        raise RuntimeError(f"{STOP_SCHEMA}: frozen session count changed")
    return selected


def pilot_dates(raw_dir: Path) -> list[str]:
    sessions = _session_dates(raw_dir)
    result = [sessions[0]]
    for year in PILOT_YEAR_DATES:
        result.append(next(value for value in sessions if value.startswith(year)))
    result.append(sessions[-1])
    if len(result) != PILOT_COUNT or len(set(result)) != PILOT_COUNT:
        raise RuntimeError(f"{STOP_SCHEMA}: pilot date selection is not deterministic")
    return result


def _frozen_date_universe(store: Mapping[str, Any], date_ms: int) -> set[str]:
    result: set[str] = set()
    for symbol in replay._eligible_symbols_for_date(store, date_ms):
        if _board(symbol) is not None:
            result.add(symbol.lower())
    return result


def _frozen_volume(store: Mapping[str, Any], symbol: str, date_ms: int) -> float | None:
    bounds = store["bounds"].get(symbol)
    if bounds is None:
        return None
    start, end = bounds
    dates = store["date_ms"][start:end]
    index = int(np.searchsorted(dates, date_ms, side="left"))
    if index >= len(dates) or int(dates[index]) != date_ms:
        return None
    value = float(store["volume"][start + index])
    return value if math.isfinite(value) and value >= 0 else None


def _provider_rows(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows = payload["response"]["rows"]
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        symbol = _canonical_symbol(row.get("ts_code"))
        if symbol is None:
            continue
        canonical = {
            "symbol": symbol,
            "date": _date_text(row.get("trade_date")),
            "turnover_rate_pct": _numeric_or_null(row.get("turnover_rate")),
            "float_share": _numeric_or_null(row.get("float_share")),
        }
        prior = result.get(symbol)
        if prior is not None and prior != canonical:
            raise RuntimeError(f"{STOP_SCHEMA}: conflicting normalized duplicate for {symbol}")
        result[symbol] = canonical
    return result


def _canonical_rows_from_payload(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return in-scope turnover rows, deterministically deduplicated."""

    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in payload["response"]["rows"]:
        symbol = _canonical_symbol(row.get("ts_code"))
        date = _date_text(row.get("trade_date"))
        if symbol is None or date is None:
            continue
        canonical = {
            "symbol": symbol,
            "date": date,
            "turnover_rate_pct": _numeric_or_null(row.get("turnover_rate")),
        }
        key = (symbol, date)
        prior = by_key.get(key)
        if prior is not None and prior != canonical:
            raise RuntimeError(f"{STOP_SCHEMA}: conflicting duplicate canonical row for {symbol} {date}")
        by_key[key] = canonical
    return [by_key[key] for key in sorted(by_key)]


def _canonical_rows_with_counts(payload: Mapping[str, Any]) -> tuple[list[dict[str, Any]], int]:
    """Return canonical in-scope rows and exact duplicate count."""

    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    duplicate_count = 0
    for row in payload["response"]["rows"]:
        symbol = _canonical_symbol(row.get("ts_code"))
        date = _date_text(row.get("trade_date"))
        if symbol is None or date is None:
            continue
        canonical = {
            "symbol": symbol,
            "date": date,
            "turnover_rate_pct": _numeric_or_null(row.get("turnover_rate")),
        }
        key = (symbol, date)
        prior = by_key.get(key)
        if prior is not None:
            duplicate_count += 1
            if prior != canonical:
                raise RuntimeError(f"{STOP_FULL}: conflicting duplicate canonical row for {symbol} {date}")
        else:
            by_key[key] = canonical
    return [by_key[key] for key in sorted(by_key)], duplicate_count


def write_pilot_canonical(
    *, raw_dir: Path, dates: Sequence[str], canonical_path: Path,
) -> dict[str, Any]:
    """Build the small pilot canonical dataset without another provider call."""

    _reject_forbidden((raw_dir, canonical_path))
    all_rows: dict[tuple[str, str], dict[str, Any]] = {}
    raw_digest = hashlib.sha256()
    for date in dates:
        path = raw_dir / f"daily_basic_{date.replace('-', '')}.json"
        raw_bytes = path.read_bytes()
        raw_digest.update(date.encode("utf-8") + b"\n" + raw_bytes)
        payload = json.loads(raw_bytes.decode("utf-8"))
        _schema_audit(payload, date, strict_unique=True)
        for row in _canonical_rows_from_payload(payload):
            key = (row["symbol"], row["date"])
            if key in all_rows and all_rows[key] != row:
                raise RuntimeError(f"{STOP_SCHEMA}: conflicting duplicate pilot row for {key}")
            all_rows[key] = row
    rows = [all_rows[key] for key in sorted(all_rows)]
    canonical_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = canonical_path.with_name(canonical_path.name + ".tmp")
    temporary.write_text(
        "".join(_canonical_json(row) + "\n" for row in rows),
        encoding="utf-8", newline="\n",
    )
    os.replace(temporary, canonical_path)
    content_digest = hashlib.sha256(canonical_path.read_bytes()).hexdigest()
    return {
        "path": canonical_path.as_posix(),
        "rows": len(rows),
        "bytes": canonical_path.stat().st_size,
        "file_sha256": _sha256_file(canonical_path),
        "content_stream_sha256": content_digest,
        "duplicate_rows_deduplicated": 0,
        "raw_stream_sha256": raw_digest.hexdigest(),
    }


def _coverage_audit(
    payloads: Mapping[str, Mapping[str, Any]], store: Mapping[str, Any], index_dates: Mapping[str, int]
) -> dict[str, Any]:
    by_date: dict[str, Any] = {}
    total_frozen = 0
    total_matched = 0
    for date in payloads:
        frozen = _frozen_date_universe(store, index_dates[date])
        provider = set(_provider_rows(payloads[date]))
        matched = frozen & provider
        coverage = len(matched) / len(frozen) if frozen else 0.0
        by_date[date] = {
            "frozen_universe": len(frozen),
            "provider_in_scope": len(provider),
            "matched": len(matched),
            "coverage": coverage,
            "minimum": MIN_DATE_COVERAGE,
            "status": "PASS" if coverage >= MIN_DATE_COVERAGE else "FAIL",
        }
        total_frozen += len(frozen)
        total_matched += len(matched)
    aggregate = total_matched / total_frozen if total_frozen else 0.0
    result = {
        "dates": by_date,
        "aggregate": {
            "frozen_rows": total_frozen,
            "matched_rows": total_matched,
            "coverage": aggregate,
            "minimum": MIN_AGGREGATE_COVERAGE,
            "status": "PASS" if aggregate >= MIN_AGGREGATE_COVERAGE else "FAIL",
        },
    }
    if any(item["status"] != "PASS" for item in by_date.values()) or result["aggregate"]["status"] != "PASS":
        raise RuntimeError(f"{STOP_COVERAGE}: frozen daily-bar coverage below threshold")
    return result


def _semantics_audit(
    payloads: Mapping[str, Mapping[str, Any]], store: Mapping[str, Any], index_dates: Mapping[str, int]
) -> dict[str, Any]:
    by_date: dict[str, Any] = {}
    all_samples: list[dict[str, Any]] = []
    for date in payloads:
        rows = _provider_rows(payloads[date])
        frozen = _frozen_date_universe(store, index_dates[date])
        eligible: list[dict[str, Any]] = []
        for symbol in sorted(frozen):
            row = rows.get(symbol)
            if row is None or row["turnover_rate_pct"] is None or not row["float_share"] or row["float_share"] <= 0:
                continue
            volume = _frozen_volume(store, symbol, index_dates[date])
            if volume is None:
                continue
            implied = volume / (row["float_share"] * 10000.0) * 100.0
            if not math.isfinite(implied):
                continue
            provider = float(row["turnover_rate_pct"])
            tolerance = max(0.05, 0.02 * abs(implied))
            sample = {
                "symbol": symbol,
                "date": date,
                "provider_turnover_rate_pct": provider,
                "implied_turnover_pct": implied,
                "absolute_error_pct_points": abs(provider - implied),
                "tolerance_pct_points": tolerance,
                "within_tolerance": abs(provider - implied) <= tolerance,
            }
            eligible.append(sample)
        sample = eligible[:SAMPLE_SIZE]
        if len(sample) < SAMPLE_SIZE:
            raise RuntimeError(f"{STOP_SEMANTICS}: fewer than {SAMPLE_SIZE} valid sample rows on {date}")
        ratios = [item["provider_turnover_rate_pct"] / item["implied_turnover_pct"] for item in sample if item["implied_turnover_pct"] > 0]
        median_ratio = float(np.median(np.asarray(ratios, dtype=float))) if ratios else None
        matched = sum(bool(item["within_tolerance"]) for item in sample)
        rate = matched / len(sample)
        date_result = {
            "sample_rows": len(sample),
            "within_tolerance": matched,
            "match_rate": rate,
            "minimum_match_rate": MIN_SEMANTICS_MATCH,
            "median_provider_to_implied_ratio": median_ratio,
            "ten_x_or_hundred_x_systematic_error": bool(
                median_ratio is not None and (0.05 <= median_ratio <= 0.2 or 5.0 <= median_ratio <= 20.0)
            ),
            "status": "PASS" if rate >= MIN_SEMANTICS_MATCH and not (
                median_ratio is not None and (0.05 <= median_ratio <= 0.2 or 5.0 <= median_ratio <= 20.0)
            ) else "FAIL",
        }
        by_date[date] = date_result
        all_samples.extend(sample)
    total_rate = sum(bool(item["within_tolerance"]) for item in all_samples) / len(all_samples)
    ratios = [item["provider_turnover_rate_pct"] / item["implied_turnover_pct"] for item in all_samples if item["implied_turnover_pct"] > 0]
    median_ratio = float(np.median(np.asarray(ratios, dtype=float))) if ratios else None
    systematic = bool(median_ratio is not None and (0.05 <= median_ratio <= 0.2 or 5.0 <= median_ratio <= 20.0))
    result = {
        "by_date": by_date,
        "aggregate": {
            "sample_rows": len(all_samples),
            "within_tolerance": sum(bool(item["within_tolerance"]) for item in all_samples),
            "match_rate": total_rate,
            "minimum_match_rate": MIN_SEMANTICS_MATCH,
            "median_provider_to_implied_ratio": median_ratio,
            "ten_x_or_hundred_x_systematic_error": systematic,
            "status": "PASS" if total_rate >= MIN_SEMANTICS_MATCH and not systematic else "FAIL",
        },
        "formula": "implied_turnover_pct = frozen_volume_shares / (float_share * 10000) * 100",
        "float_share_unit": "万股",
        "frozen_volume_unit": "股",
        "provider_turnover_unit": "percent",
        "provider_turnover_field": "turnover_rate",
        "sample_order": "matched symbols sorted lexicographically; first 100 per date",
    }
    if result["aggregate"]["status"] != "PASS" or any(item["status"] != "PASS" for item in by_date.values()):
        raise RuntimeError(f"{STOP_SEMANTICS}: provider turnover semantics failed")
    return result


def _checkpoint_template(dates: Sequence[str], raw_dir: Path, mode: str) -> dict[str, Any]:
    return {
        "schema_version": "TUSHARE_GATEWAY_DATE_CHECKPOINT_V1",
        "mode": mode,
        "status": "IN_PROGRESS",
        "source_classification": SOURCE_CLASSIFICATION,
        "gateway_url": GATEWAY_URL,
        "package": PACKAGE_NAME,
        "package_version": PACKAGE_VERSION,
        "endpoint": ENDPOINT,
        "fields": FIELDS,
        "requested_dates": list(dates),
        "completed": {},
        "failed": {},
        "pending": list(dates),
        "raw_dir": raw_dir.as_posix(),
        "credential_present": True,
        "token_persisted": False,
    }


def _load_checkpoint(path: Path, dates: Sequence[str], raw_dir: Path, mode: str) -> dict[str, Any]:
    if not path.exists():
        return _checkpoint_template(dates, raw_dir, mode)
    import json

    checkpoint = json.loads(path.read_text(encoding="utf-8"))
    if checkpoint.get("schema_version") != "TUSHARE_GATEWAY_DATE_CHECKPOINT_V1":
        raise RuntimeError(f"{STOP_FULL}: checkpoint schema changed")
    if checkpoint.get("requested_dates") != list(dates) or checkpoint.get("mode") != mode:
        raise RuntimeError(f"{STOP_FULL}: checkpoint date universe or mode changed")
    if checkpoint.get("token_persisted"):
        raise RuntimeError(f"{STOP_FULL}: token persistence flag is invalid")
    return checkpoint


def acquire_dates(
    *, dates: Sequence[str], checkpoint_path: Path, raw_dir: Path, mode: str,
    retry_attempts: int = 3, retry_sleep_seconds: float = 2.0,
) -> dict[str, Any]:
    """Acquire full daily_basic responses with a resumable per-date checkpoint."""

    _reject_forbidden((checkpoint_path, raw_dir))
    if retry_attempts != 3:
        raise ValueError("retry_attempts must remain exactly 3")
    pro = _credentialed_client()
    checkpoint = _load_checkpoint(checkpoint_path, dates, raw_dir, mode)
    raw_dir.mkdir(parents=True, exist_ok=True)
    completed = checkpoint.setdefault("completed", {})
    failed = checkpoint.setdefault("failed", {})
    for date in dates:
        raw_path = raw_dir / f"daily_basic_{date.replace('-', '')}.json"
        prior = completed.get(date)
        if prior and raw_path.exists() and _sha256_file(raw_path) == prior.get("file_sha256"):
            continue
        last_chain: list[str] = []
        response_received = False
        completed_this_date = False
        for attempt in range(1, retry_attempts + 1):
            try:
                frame = pro.daily_basic(trade_date=date.replace("-", ""), fields=FIELDS)
                response_received = True
                payload = _frame_payload(frame, date)
                _schema_audit(payload, date, strict_unique=(mode == "pilot"))
                encoded = (_canonical_json(payload) + "\n").encode("utf-8")
                temporary = raw_path.with_suffix(".json.tmp")
                temporary.write_bytes(encoded)
                os.replace(temporary, raw_path)
                completed[date] = {
                    "status": "COMPLETED",
                    "attempts": attempt,
                    "row_count": payload["response_row_count"],
                    "file_bytes": raw_path.stat().st_size,
                    "file_sha256": _sha256_file(raw_path),
                    "schema_status": "PASS",
                }
                failed.pop(date, None)
                completed_this_date = True
                break
            except Exception as exc:
                last_chain = _exception_class_chain(exc)
                if attempt < retry_attempts:
                    time.sleep(min(30.0, retry_sleep_seconds * (2 ** (attempt - 1))))
        if not completed_this_date:
            failed[date] = {
                "status": "FAILED",
                "attempts": retry_attempts,
                "exception_class_chain": last_chain,
                "provider_response_received": response_received,
            }
            checkpoint["pending"] = [item for item in dates if item not in completed and item not in failed]
            checkpoint["completed"] = completed
            checkpoint["failed"] = failed
            checkpoint["status"] = "PARTIAL_FAILED"
            checkpoint["updated_at_utc"] = _utc_now()
            _write_json_atomic(checkpoint_path, checkpoint)
            raise RuntimeError(f"{STOP_FULL}: date acquisition failed for {date}")
        checkpoint["pending"] = [item for item in dates if item not in completed and item not in failed]
        checkpoint["completed"] = completed
        checkpoint["failed"] = failed
        checkpoint["updated_at_utc"] = _utc_now()
        _write_json_atomic(checkpoint_path, checkpoint)
        print(f"tushare date={date} completed={len(completed)} pending={len(checkpoint['pending'])}", flush=True)
    checkpoint["status"] = "COMPLETE" if len(completed) == len(dates) and not failed else "PARTIAL_FAILED"
    checkpoint["completed_date_count"] = len(completed)
    checkpoint["failed_date_count"] = len(failed)
    checkpoint["pending_date_count"] = len(checkpoint["pending"])
    checkpoint["updated_at_utc"] = _utc_now()
    _write_json_atomic(checkpoint_path, checkpoint)
    return checkpoint


def build_full_canonical(
    *, checkpoint_path: Path, raw_dir: Path, canonical_path: Path, manifest_path: Path,
) -> dict[str, Any]:
    """Validate all full raw responses and write sorted canonical turnover rows."""

    _reject_forbidden((checkpoint_path, raw_dir, canonical_path, manifest_path))
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    dates = list(checkpoint.get("requested_dates", []))
    if checkpoint.get("status") != "COMPLETE" or len(dates) != EXPECTED_SESSION_COUNT:
        raise RuntimeError(f"{STOP_FULL}: full checkpoint is not complete")
    expected_identity = {
        "source_classification": SOURCE_CLASSIFICATION,
        "gateway_url": GATEWAY_URL,
        "package": PACKAGE_NAME,
        "package_version": PACKAGE_VERSION,
        "endpoint": ENDPOINT,
    }
    raw_digest = hashlib.sha256()
    total_rows = 0
    duplicate_rows = 0
    excluded_rows = 0
    temporary_dir = Path(tempfile.mkdtemp(prefix="tushare-canonical-"))
    sqlite_path = temporary_dir / "rows.sqlite3"
    temporary_output = temporary_dir / "canonical.parquet"
    try:
        connection = sqlite3.connect(sqlite_path)
        try:
            connection.execute("PRAGMA journal_mode=OFF")
            connection.execute("PRAGMA synchronous=OFF")
            connection.execute(
                "CREATE TABLE rows (symbol TEXT NOT NULL, date TEXT NOT NULL, "
                "turnover_rate_pct REAL, PRIMARY KEY(symbol, date))"
            )
            for date in dates:
                raw_path = raw_dir / f"daily_basic_{date.replace('-', '')}.json"
                if not raw_path.exists():
                    raise RuntimeError(f"{STOP_FULL}: raw response missing for {date}")
                raw_bytes = raw_path.read_bytes()
                raw_digest.update(date.encode("utf-8") + b"\n" + raw_bytes)
                payload = json.loads(raw_bytes.decode("utf-8"))
                if any(payload.get(key) != value for key, value in expected_identity.items()):
                    raise RuntimeError(f"{STOP_FULL}: source identity changed for {date}")
                if payload.get("request") != {"trade_date": date, "fields": FIELDS}:
                    raise RuntimeError(f"{STOP_FULL}: request identity changed for {date}")
                _schema_audit(payload, date, strict_unique=False)
                rows, duplicates = _canonical_rows_with_counts(payload)
                duplicate_rows += duplicates
                excluded_rows += int(payload["response_row_count"]) - len(rows)
                try:
                    connection.executemany(
                        "INSERT INTO rows(symbol, date, turnover_rate_pct) VALUES (?, ?, ?)",
                        [(row["symbol"], row["date"], row["turnover_rate_pct"]) for row in rows],
                    )
                except sqlite3.IntegrityError as exc:
                    raise RuntimeError(f"{STOP_FULL}: conflicting canonical duplicate") from exc
                total_rows += len(rows)
            connection.commit()
            import pyarrow as pa
            import pyarrow.parquet as pq

            schema = pa.schema([
                pa.field("symbol", pa.string(), nullable=False),
                pa.field("date", pa.string(), nullable=False),
                pa.field("turnover_rate_pct", pa.float64(), nullable=True),
            ])
            writer = pq.ParquetWriter(temporary_output, schema=schema, compression="zstd")
            content_digest = hashlib.sha256()
            written = 0
            try:
                cursor = connection.execute(
                    "SELECT symbol, date, turnover_rate_pct FROM rows ORDER BY symbol, date"
                )
                while True:
                    batch = cursor.fetchmany(10000)
                    if not batch:
                        break
                    rows = [
                        {"symbol": symbol, "date": date, "turnover_rate_pct": turnover}
                        for symbol, date, turnover in batch
                    ]
                    for row in rows:
                        content_digest.update((_canonical_json(row) + "\n").encode("utf-8"))
                    writer.write_table(pa.Table.from_pylist(rows, schema=schema))
                    written += len(rows)
            finally:
                writer.close()
            if written != total_rows:
                raise RuntimeError(f"{STOP_FULL}: canonical row count changed during write")
        finally:
            connection.close()
        canonical_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary_output, canonical_path)
        result = {
            "schema_version": SCHEMA_VERSION,
            "status": "COMPLETE",
            "labels": list(LABELS),
            "source_classification": SOURCE_CLASSIFICATION,
            "gateway_url": GATEWAY_URL,
            "package": PACKAGE_NAME,
            "package_version": PACKAGE_VERSION,
            "endpoint": ENDPOINT,
            "fields": FIELDS,
            "requested_dates": dates,
            "completed_dates": len(dates),
            "credential_present": True,
            "token_persisted": False,
            "raw_acquisition": {
                "raw_dir": raw_dir.as_posix(),
                "date_files": len(dates),
                "raw_stream_sha256": raw_digest.hexdigest(),
            },
            "canonical_dataset": {
                "path": canonical_path.as_posix(),
                "rows": total_rows,
                "bytes": canonical_path.stat().st_size,
                "file_sha256": _sha256_file(canonical_path),
                "content_stream_sha256": content_digest.hexdigest(),
                "duplicate_rows_deduplicated": duplicate_rows,
                "excluded_provider_rows": excluded_rows,
                "sort": ["symbol", "date"],
            },
            "duplicate_policy": "conflicting duplicates fail closed; exact duplicates deterministically deduplicated and counted",
            "missing_policy": "null turnover retained; no imputation",
            "outcome_access": {
                "status": OUTCOME_ACCESS_STATUS,
                "outcome_values_used": False,
            },
        }
        _write_json_atomic(manifest_path, result)
        return result
    finally:
        for item in sorted(temporary_dir.glob("*"), reverse=True):
            item.unlink(missing_ok=True)
        temporary_dir.rmdir()


def _load_cohort_rows(path: Path) -> Iterable[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        for line in handle:
            yield json.loads(line)


def audit_inputs(
    *, frozen_raw_dir: Path, cohort_path: Path, cohort_manifest_path: Path,
    canonical_path: Path, full_manifest_path: Path, output_manifest_path: Path,
) -> dict[str, Any]:
    """Audit in-scope turnover coverage against the frozen no-outcome cohort."""

    _reject_forbidden((frozen_raw_dir, cohort_path, cohort_manifest_path, canonical_path, full_manifest_path, output_manifest_path))
    full_manifest = json.loads(full_manifest_path.read_text(encoding="utf-8"))
    if full_manifest.get("status") != "COMPLETE":
        raise RuntimeError(f"{STOP_FULL}: full acquisition manifest is not complete")
    import pandas as pd

    frame = pd.read_parquet(canonical_path, columns=["symbol", "date", "turnover_rate_pct"])
    if frame.duplicated(["symbol", "date"]).any():
        raise RuntimeError("TURNOVER_RATE_ACQUISITION_NOT_RESEARCH_READY: canonical duplicate remains")
    frame["key"] = frame["symbol"].astype(str) + "|" + frame["date"].astype(str)
    lookup = frame.set_index("key")["turnover_rate_pct"]
    earliest_by_symbol = frame.groupby("symbol")["date"].min().to_dict()
    frozen_dates, _index_bars, _index_meta = replay._load_index(frozen_raw_dir)
    store, _store_meta = replay._load_stock_store(frozen_raw_dir / "daily_k.parquet")
    cohort_manifest = json.loads(cohort_manifest_path.read_text(encoding="utf-8"))
    exact_structural = int(cohort_manifest["cohorts"]["structural_rows"])
    exact_qualified = int(cohort_manifest["cohorts"]["qualified_rows"])
    structural = 0
    qualified = 0
    in_scope_structural = 0
    in_scope_qualified = 0
    matched_structural = 0
    matched_qualified = 0
    missing_structural = 0
    missing_qualified = 0
    null_structural = 0
    null_qualified = 0
    negative_structural = 0
    zero_volume_structural = 0
    newly_listed_symbols: set[str] = set()
    structural_years: Counter[str] = Counter()
    qualified_years: Counter[str] = Counter()
    structural_boards: Counter[str] = Counter()
    qualified_boards: Counter[str] = Counter()
    matched_structural_years: Counter[str] = Counter()
    matched_qualified_years: Counter[str] = Counter()
    matched_structural_boards: Counter[str] = Counter()
    matched_qualified_boards: Counter[str] = Counter()
    extreme_gt_100 = 0
    extreme_gt_1000 = 0

    for row in _load_cohort_rows(cohort_path):
        structural += 1
        is_qualified = bool(row["final_b_qualified"])
        if is_qualified:
            qualified += 1
        board = row.get("board") or _board(row["symbol"])
        if board not in {"Main", "ChiNext", "STAR"}:
            continue
        in_scope_structural += 1
        structural_years[row["year"]] += 1
        structural_boards[board] += 1
        if is_qualified:
            in_scope_qualified += 1
            qualified_years[row["year"]] += 1
            qualified_boards[board] += 1
        key = f"{str(row['symbol']).lower()}|{row['signal_date']}"
        found = key in lookup.index
        value = lookup.get(key) if found else None
        valid = found and value is not None and not bool(pd.isna(value))
        numeric = None
        if valid:
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                valid = False
        if valid and (not math.isfinite(numeric) or numeric < 0):
            negative_structural += 1
            valid = False
        if not found:
            missing_structural += 1
            if is_qualified:
                missing_qualified += 1
        elif not valid:
            null_structural += 1
            if is_qualified:
                null_qualified += 1
        else:
            matched_structural += 1
            matched_structural_years[row["year"]] += 1
            matched_structural_boards[board] += 1
            if numeric > 100:
                extreme_gt_100 += 1
            if numeric > 1000:
                extreme_gt_1000 += 1
            if is_qualified:
                matched_qualified += 1
                matched_qualified_years[row["year"]] += 1
                matched_qualified_boards[board] += 1
        volume = _frozen_volume(store, row["symbol"], frozen_dates[row["signal_date"]])
        if volume == 0:
            zero_volume_structural += 1
        earliest = earliest_by_symbol.get(str(row["symbol"]).lower())
        if earliest and earliest > START_DATE:
            newly_listed_symbols.add(str(row["symbol"]).lower())

    if structural != exact_structural or qualified != exact_qualified:
        raise RuntimeError("TURNOVER_RATE_ACQUISITION_NOT_RESEARCH_READY: cohort counts changed")

    def ratio(matches: int, total: int) -> float:
        return matches / total if total else 0.0

    qualified_coverage = ratio(matched_qualified, in_scope_qualified)
    structural_coverage = ratio(matched_structural, in_scope_structural)
    strata: dict[str, dict[str, Any]] = {"year": {}, "board": {}}
    for group, totals, matches in (
        ("year", qualified_years, matched_qualified_years),
        ("board", qualified_boards, matched_qualified_boards),
    ):
        for key, total in sorted(totals.items()):
            strata[group][key] = {"rows": total, "matched": matches[key], "coverage": ratio(matches[key], total)}
    structural_strata: dict[str, dict[str, Any]] = {"year": {}, "board": {}}
    for group, totals, matches in (
        ("year", structural_years, matched_structural_years),
        ("board", structural_boards, matched_structural_boards),
    ):
        for key, total in sorted(totals.items()):
            structural_strata[group][key] = {"rows": total, "matched": matches[key], "coverage": ratio(matches[key], total)}
    major = list(strata["year"].values()) + [strata["board"].get(board, {"coverage": 0.0}) for board in ("Main", "ChiNext", "STAR")]
    structural_major = list(structural_strata["year"].values()) + [structural_strata["board"].get(board, {"coverage": 0.0}) for board in ("Main", "ChiNext", "STAR")]
    coverage_ready = (
        qualified_coverage >= 0.99 and structural_coverage >= 0.98
        and all(item["coverage"] >= 0.95 for item in major)
        and all(item["coverage"] >= 0.95 for item in structural_major)
    )
    canonical_negative = int((frame["turnover_rate_pct"].dropna() < 0).sum())
    result = {
        "schema_version": SCHEMA_VERSION,
        "status": "RESEARCH_READY" if coverage_ready and canonical_negative == 0 else "TURNOVER_RATE_ACQUISITION_NOT_RESEARCH_READY",
        "labels": list(LABELS),
        "source_classification": SOURCE_CLASSIFICATION,
        "gateway_url": GATEWAY_URL,
        "package": PACKAGE_NAME,
        "package_version": PACKAGE_VERSION,
        "endpoint": ENDPOINT,
        "fields": FIELDS,
        "cohort_reconciliation": {
            "exact_structural_rows": structural,
            "exact_qualified_rows": qualified,
            "in_scope_structural_rows": in_scope_structural,
            "in_scope_qualified_rows": in_scope_qualified,
            "out_of_scope_structural_rows_excluded": structural - in_scope_structural,
            "out_of_scope_qualified_rows_excluded": qualified - in_scope_qualified,
            "out_of_scope_policy": "exclude non-Main/ChiNext/STAR rows; do not expand universe",
        },
        "coverage": {
            "qualified": {"matched": matched_qualified, "total": in_scope_qualified, "coverage": qualified_coverage, "minimum": 0.99},
            "structural": {"matched": matched_structural, "total": in_scope_structural, "coverage": structural_coverage, "minimum": 0.98},
            "qualified_strata": strata,
            "structural_strata": structural_strata,
            "status": "PASS" if coverage_ready else "FAIL",
        },
        "data_quality": {
            "missing_structural_at_t": missing_structural,
            "missing_qualified_at_t": missing_qualified,
            "null_structural_at_t": null_structural,
            "null_qualified_at_t": null_qualified,
            "negative_canonical_rows": canonical_negative,
            "negative_structural_at_t": negative_structural,
            "extreme_gt_100_pct_rows": extreme_gt_100,
            "extreme_gt_1000_pct_rows": extreme_gt_1000,
            "newly_listed_symbol_count": len(newly_listed_symbols),
            "newly_listed_symbols": sorted(newly_listed_symbols),
            "suspension_or_no_trade_proxy_rows": zero_volume_structural,
            "no_trade_proxy_definition": "frozen daily_k volume == 0 on T; exact suspension status not inferred",
            "duplicate_policy": "canonical symbol/date uniqueness checked; conflicting duplicates fail closed",
            "imputation": False,
        },
        "canonical_dataset": full_manifest["canonical_dataset"],
        "outcome_access": {"status": OUTCOME_ACCESS_STATUS, "outcome_values_used": False},
        "boundary": {
            "b_unchanged": True,
            "universe_unchanged": True,
            "frozen_daily_k_unchanged": True,
            "frozen_registry_unchanged": True,
            "final_oos_read": False,
            "turnover_rate_f_used": False,
            "no_vintage_proof": True,
            "diagnostic_only": True,
        },
        "audited_at_utc": _utc_now(),
    }
    _write_json_atomic(output_manifest_path, result)
    if result["status"] != "RESEARCH_READY":
        raise RuntimeError("TURNOVER_RATE_ACQUISITION_NOT_RESEARCH_READY")
    return result


def _available_outcome_metrics(records: Sequence[Mapping[str, Any]], horizon: str) -> dict[str, Any]:
    values = [
        record["outcomes"][horizon]
        for record in records
        if record.get("outcomes", {}).get(horizon, {}).get("status") == "AVAILABLE"
    ]
    returns = np.asarray([float(value["return_pct"]) for value in values], dtype=float)
    mfes = np.asarray([float(value["mfe_pct"]) for value in values], dtype=float)
    maes = np.asarray([float(value["mae_pct"]) for value in values], dtype=float)
    return {
        "n": int(len(values)),
        "mean_return_pct": float(np.mean(returns)) if len(values) else None,
        "median_return_pct": float(np.median(returns)) if len(values) else None,
        "positive_rate": float(np.mean(returns > 0)) if len(values) else None,
        "mean_mfe_pct": float(np.mean(mfes)) if len(values) else None,
        "median_mfe_pct": float(np.median(mfes)) if len(values) else None,
        "mean_mae_pct": float(np.mean(maes)) if len(values) else None,
        "median_mae_pct": float(np.median(maes)) if len(values) else None,
    }


def _assign_quintiles(records: Sequence[Mapping[str, Any]], feature: str, bins: int = 5) -> dict[int, int]:
    available = [
        (index, float(record[feature]), str(record["symbol"]), str(record["signal_date"]))
        for index, record in enumerate(records)
        if record.get(feature) is not None and math.isfinite(float(record[feature]))
    ]
    available.sort(key=lambda item: (item[1], item[2], item[3], item[0]))
    count = len(available)
    return {
        index: min(bins, int(position * bins / count) + 1)
        for position, (index, _value, _symbol, _date) in enumerate(available)
    } if count else {}


def _spearman(records: Sequence[Mapping[str, Any]], feature: str, horizon: str) -> dict[str, Any]:
    pairs = [
        (float(record[feature]), float(record["outcomes"][horizon]["return_pct"]))
        for record in records
        if record.get(feature) is not None
        and record.get("outcomes", {}).get(horizon, {}).get("status") == "AVAILABLE"
    ]
    if len(pairs) < 2:
        return {"n": len(pairs), "rho": None}
    x = np.asarray([pair[0] for pair in pairs], dtype=float)
    y = np.asarray([pair[1] for pair in pairs], dtype=float)
    def ranks(values: np.ndarray) -> np.ndarray:
        order = np.argsort(values, kind="mergesort")
        output = np.empty(len(values), dtype=float)
        position = 0
        while position < len(values):
            end = position + 1
            while end < len(values) and values[order[end]] == values[order[position]]:
                end += 1
            output[order[position:end]] = (position + end - 1) / 2.0 + 1.0
            position = end
        return output
    x_rank, y_rank = ranks(x), ranks(y)
    if np.std(x_rank) == 0 or np.std(y_rank) == 0:
        return {"n": len(pairs), "rho": None}
    return {"n": len(pairs), "rho": float(np.corrcoef(x_rank, y_rank)[0, 1])}


def _feature_quintile_summary(records: Sequence[Mapping[str, Any]], feature: str) -> dict[str, Any]:
    assignments = _assign_quintiles(records, feature)
    rows: list[dict[str, Any]] = []
    for quintile in range(1, 6):
        group = [records[index] for index, value in assignments.items() if value == quintile]
        values = [float(record[feature]) for record in group]
        rows.append({
            "quintile": quintile,
            "row_n": len(group),
            "feature_min": min(values) if values else None,
            "feature_max": max(values) if values else None,
            "5D": _available_outcome_metrics(group, "5D"),
            "10D": _available_outcome_metrics(group, "10D"),
        })
    result: dict[str, Any] = {"rows": rows}
    for horizon in ("5D", "10D"):
        low, high = rows[0][horizon], rows[-1][horizon]
        result[horizon] = {
            "spearman": _spearman(records, feature, horizon),
            "high_minus_low_mean_return_pct": (
                high["mean_return_pct"] - low["mean_return_pct"]
                if high["mean_return_pct"] is not None and low["mean_return_pct"] is not None else None
            ),
            "high_minus_low_median_return_pct": (
                high["median_return_pct"] - low["median_return_pct"]
                if high["median_return_pct"] is not None and low["median_return_pct"] is not None else None
            ),
        }
    return result


def _conditional_and_matrix(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    pair_records = [
        record for record in records
        if record.get("turnover_rate_pct") is not None and record.get("relative_volume") is not None
    ]
    turnover_bins = _assign_quintiles(pair_records, "turnover_rate_pct")
    rv_bins = _assign_quintiles(pair_records, "relative_volume")
    matrix: list[dict[str, Any]] = []
    for turnover_quintile in range(1, 6):
        for rv_quintile in range(1, 6):
            group = [
                pair_records[index]
                for index in set(turnover_bins) & set(rv_bins)
                if turnover_bins[index] == turnover_quintile and rv_bins[index] == rv_quintile
            ]
            matrix.append({
                "turnover_quintile": turnover_quintile,
                "relative_volume_quintile": rv_quintile,
                "row_n": len(group),
                "5D": _available_outcome_metrics(group, "5D"),
                "10D": _available_outcome_metrics(group, "10D"),
            })

    def conditional(feature: str, condition: str, assignments: dict[int, int], condition_assignments: dict[int, int]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for condition_quintile in range(1, 6):
            low = [
                pair_records[index]
                for index in set(assignments) & set(condition_assignments)
                if condition_assignments[index] == condition_quintile and assignments[index] == 1
            ]
            high = [
                pair_records[index]
                for index in set(assignments) & set(condition_assignments)
                if condition_assignments[index] == condition_quintile and assignments[index] == 5
            ]
            item: dict[str, Any] = {
                "condition": condition,
                "condition_quintile": condition_quintile,
                "low_feature_quintile": 1,
                "high_feature_quintile": 5,
                "low": {horizon: _available_outcome_metrics(low, horizon) for horizon in ("5D", "10D")},
                "high": {horizon: _available_outcome_metrics(high, horizon) for horizon in ("5D", "10D")},
            }
            for horizon in ("5D", "10D"):
                low_mean = item["low"][horizon]["mean_return_pct"]
                high_mean = item["high"][horizon]["mean_return_pct"]
                item[horizon + "_high_minus_low_mean_return_pct"] = (
                    high_mean - low_mean if high_mean is not None and low_mean is not None else None
                )
            result.append(item)
        return result

    corner_lookup = {
        (item["turnover_quintile"], item["relative_volume_quintile"]): item
        for item in matrix
    }
    interaction: dict[str, Any] = {}
    for horizon in ("5D", "10D"):
        values = []
        for key in ((5, 5), (5, 1), (1, 5), (1, 1)):
            values.append(corner_lookup[key][horizon]["mean_return_pct"])
        interaction[horizon + "_corner_contrast"] = (
            values[0] - values[1] - values[2] + values[3]
            if all(value is not None for value in values) else None
        )
    return {
        "pair_complete_rows": len(pair_records),
        "matrix_5x5": matrix,
        "turnover_conditional_on_relative_volume": conditional(
            "turnover_rate_pct", "relative_volume", turnover_bins, rv_bins,
        ),
        "relative_volume_conditional_on_turnover": conditional(
            "relative_volume", "turnover_rate_pct", rv_bins, turnover_bins,
        ),
        "corner_interaction_contrast": interaction,
    }


def _strata_summary(records: Sequence[Mapping[str, Any]], feature: str) -> dict[str, Any]:
    assignments = _assign_quintiles(records, feature)
    result: dict[str, Any] = {"year": {}, "board": {}}
    for field, values in (("year", ("2023", "2024", "2025", "2026")), ("board", ("Main", "ChiNext", "STAR"))):
        for value in values:
            low = [records[index] for index, quintile in assignments.items() if quintile == 1 and str(records[index][field]) == value]
            high = [records[index] for index, quintile in assignments.items() if quintile == 5 and str(records[index][field]) == value]
            item: dict[str, Any] = {"group": value}
            for horizon in ("5D", "10D"):
                low_metrics = _available_outcome_metrics(low, horizon)
                high_metrics = _available_outcome_metrics(high, horizon)
                item[horizon] = {
                    "low": low_metrics,
                    "high": high_metrics,
                    "high_minus_low_mean_return_pct": (
                        high_metrics["mean_return_pct"] - low_metrics["mean_return_pct"]
                        if high_metrics["mean_return_pct"] is not None and low_metrics["mean_return_pct"] is not None else None
                    ),
                }
            result[field][value] = item
    return result


def _episode_deduplicated(records: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    selected: dict[tuple[str, str], tuple[str, int, Mapping[str, Any]]] = {}
    for index, record in enumerate(records):
        key = (str(record["symbol"]), str(record["breakout_date"]))
        candidate = (str(record["signal_date"]), index, record)
        prior = selected.get(key)
        if prior is None or candidate[:2] < prior[:2]:
            selected[key] = candidate
    return [item[2] for item in sorted(selected.values(), key=lambda item: item[:2])]


def _top_one_percent(records: Sequence[Mapping[str, Any]], feature: str) -> dict[str, Any]:
    available = [record for record in records if record.get(feature) is not None]
    ordered = sorted(available, key=lambda record: (float(record[feature]), str(record["symbol"]), str(record["signal_date"])))
    top_n = max(1, int(math.ceil(len(ordered) * 0.01))) if ordered else 0
    top = ordered[-top_n:] if top_n else []
    non_top = ordered[:-top_n] if top_n else []
    return {
        "eligible_rows": len(ordered),
        "top_rows": len(top),
        "top_feature_min": min((float(record[feature]) for record in top), default=None),
        "top": {horizon: _available_outcome_metrics(top, horizon) for horizon in ("5D", "10D")},
        "non_top": {horizon: _available_outcome_metrics(non_top, horizon) for horizon in ("5D", "10D")},
        "top_minus_non_top_mean_return_pct": {
            horizon: (
                _available_outcome_metrics(top, horizon)["mean_return_pct"]
                - _available_outcome_metrics(non_top, horizon)["mean_return_pct"]
                if _available_outcome_metrics(top, horizon)["mean_return_pct"] is not None
                and _available_outcome_metrics(non_top, horizon)["mean_return_pct"] is not None else None
            )
            for horizon in ("5D", "10D")
        },
    }


def _diagnostic_record(
    row: Mapping[str, Any], turnover_value: float | None, outcomes: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "symbol": row["symbol"],
        "signal_date": row["signal_date"],
        "year": row["year"],
        "board": row["board"],
        "breakout_date": row["breakout_date"],
        "pullback_stage": row["pullback_stage"],
        "final_b_qualified": bool(row["final_b_qualified"]),
        "turnover_rate_pct": turnover_value,
        "relative_volume": row.get("relative_volume"),
        "outcomes": outcomes,
    }


def _write_diagnostic_events(path: Path, records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    _reject_forbidden((path,))
    digest = hashlib.sha256()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw_handle:
        with __import__("gzip").GzipFile(fileobj=raw_handle, mode="wb", filename="", mtime=0) as handle:
            for record in records:
                line = (_canonical_json(record) + "\n").encode("utf-8")
                digest.update(line)
                handle.write(line)
    return {"path": path.as_posix(), "rows": len(records), "bytes": path.stat().st_size, "file_sha256": _sha256_file(path), "content_stream_sha256": digest.hexdigest()}


def run_diagnostic(
    *, frozen_raw_dir: Path, core_output: Path, cohort_path: Path, canonical_path: Path,
    input_audit_manifest_path: Path, protocol_path: Path, protocol_commit: str,
    output_dir: Path, summary_path: Path, report_path: Path,
) -> dict[str, Any]:
    """Run the fixed post-protocol turnover x RV diagnostic."""

    _reject_forbidden((frozen_raw_dir, core_output, cohort_path, canonical_path, input_audit_manifest_path, protocol_path, output_dir, summary_path, report_path))
    if not protocol_commit or replay.file_sha256(protocol_path) == "":
        raise RuntimeError("TURNOVER_X_RELATIVE_VOLUME_NEEDS_MORE_EVIDENCE: protocol identity missing")
    audit = json.loads(input_audit_manifest_path.read_text(encoding="utf-8"))
    if audit.get("status") != "RESEARCH_READY":
        raise RuntimeError("TURNOVER_RATE_ACQUISITION_NOT_RESEARCH_READY")
    import pandas as pd

    turnover_frame = pd.read_parquet(canonical_path, columns=["symbol", "date", "turnover_rate_pct"])
    if turnover_frame.duplicated(["symbol", "date"]).any():
        raise RuntimeError("TURNOVER_RATE_ACQUISITION_NOT_RESEARCH_READY: canonical duplicate")
    turnover_frame["key"] = turnover_frame["symbol"].astype(str) + "|" + turnover_frame["date"].astype(str)
    turnover_lookup = turnover_frame.set_index("key")["turnover_rate_pct"]
    index_dates, index_bars, _index_meta = replay._load_index(frozen_raw_dir)
    session_dates = sorted(index_dates)
    session_ms = np.asarray([index_dates[value] for value in session_dates], dtype=np.int64)
    session_index = {value: index for index, value in enumerate(session_dates)}
    store, _store_meta = replay._load_stock_store(frozen_raw_dir / "daily_k.parquet")
    frozen_timing = _frozen_timing(core_output)
    structural: list[dict[str, Any]] = []
    exact_structural = 0
    exact_qualified = 0
    for row in _load_cohort_rows(cohort_path):
        exact_structural += 1
        if row["final_b_qualified"]:
            exact_qualified += 1
        if row.get("board") not in {"Main", "ChiNext", "STAR"}:
            continue
        symbol = str(row["symbol"]).lower()
        signal_date = str(row["signal_date"])
        key = f"{symbol}|{signal_date}"
        value = turnover_lookup.get(key)
        turnover_value = None if value is None or bool(pd.isna(value)) else float(value)
        projection = {
            "as_of_date": signal_date,
            "signal_date": signal_date,
            "earliest_execution_date": _next_execution_date(signal_date, session_dates, session_index, frozen_timing),
            "symbol": symbol,
            "setup_id": "B_BREAKOUT_RETEST",
        }
        outcome_record = returns_v1._build_event_record(
            row=projection, store=store, session_dates=session_dates,
            session_ms=session_ms, session_index=session_index,
        )
        structural.append(_diagnostic_record(row, turnover_value, outcome_record["outcomes"]))
    if exact_structural != 573586 or exact_qualified != 17714:
        raise RuntimeError("TURNOVER_RATE_ACQUISITION_NOT_RESEARCH_READY: cohort reconciliation changed")
    qualified = [record for record in structural if record["final_b_qualified"]]
    if len(qualified) != audit["cohort_reconciliation"]["in_scope_qualified_rows"]:
        raise RuntimeError("TURNOVER_RATE_ACQUISITION_NOT_RESEARCH_READY: in-scope qualified count changed")
    feature_complete = [record for record in qualified if record.get("turnover_rate_pct") is not None and record.get("relative_volume") is not None]
    feature_summaries = {
        feature: _feature_quintile_summary(qualified, feature)
        for feature in ("turnover_rate_pct", "relative_volume")
    }
    matrix_and_conditional = _conditional_and_matrix(qualified)
    structural_summaries = {
        feature: _feature_quintile_summary(structural, feature)
        for feature in ("turnover_rate_pct", "relative_volume")
    }
    strata = {
        feature: _strata_summary(qualified, feature)
        for feature in ("turnover_rate_pct", "relative_volume")
    }
    episode_records = _episode_deduplicated(qualified)
    episode_summaries = {
        feature: _feature_quintile_summary(episode_records, feature)
        for feature in ("turnover_rate_pct", "relative_volume")
    }
    top_one_percent = {
        feature: _top_one_percent(qualified, feature)
        for feature in ("turnover_rate_pct", "relative_volume")
    }
    turnover_5d = feature_summaries["turnover_rate_pct"]["5D"]["high_minus_low_mean_return_pct"]
    turnover_5d_median = feature_summaries["turnover_rate_pct"]["5D"]["high_minus_low_median_return_pct"]
    direction = 1 if turnover_5d and turnover_5d > 0 else -1 if turnover_5d and turnover_5d < 0 else 0
    conditional_spreads = [
        item["5D_high_minus_low_mean_return_pct"]
        for item in matrix_and_conditional["turnover_conditional_on_relative_volume"]
    ]
    conditional_coherent = bool(direction and conditional_spreads and all(value is not None and (1 if value > 0 else -1 if value < 0 else 0) == direction for value in conditional_spreads))
    strata_spreads = [
        item["5D"]["high_minus_low_mean_return_pct"]
        for group in (strata["turnover_rate_pct"]["year"], strata["turnover_rate_pct"]["board"])
        for item in group.values()
    ]
    strata_coherent = bool(direction and strata_spreads and all(value is not None and (1 if value > 0 else -1 if value < 0 else 0) == direction for value in strata_spreads))
    episode_spread = episode_summaries["turnover_rate_pct"]["5D"]["high_minus_low_mean_return_pct"]
    top_spread = top_one_percent["turnover_rate_pct"]["top_minus_non_top_mean_return_pct"]["5D"]
    sign_checks = [
        conditional_coherent,
        strata_coherent,
        episode_spread is not None and (1 if episode_spread > 0 else -1 if episode_spread < 0 else 0) == direction,
        top_spread is not None and (1 if top_spread > 0 else -1 if top_spread < 0 else 0) == direction,
        structural_summaries["turnover_rate_pct"]["5D"]["spearman"]["rho"] is not None
        and (1 if structural_summaries["turnover_rate_pct"]["5D"]["spearman"]["rho"] > 0 else -1 if structural_summaries["turnover_rate_pct"]["5D"]["spearman"]["rho"] < 0 else 0) == direction,
    ]
    visible = direction != 0 and turnover_5d_median is not None and (1 if turnover_5d_median > 0 else -1 if turnover_5d_median < 0 else 0) == direction
    if all(sign_checks) and visible:
        decision = "TURNOVER_X_RELATIVE_VOLUME_INCREMENTAL_SUPPORTED_FOR_FURTHER_VALIDATION"
        explanation = "The fixed turnover relationship remains directionally coherent after conditioning on relative volume and across the pre-registered sensitivity checks."
    elif visible or any(sign_checks):
        decision = "TURNOVER_X_RELATIVE_VOLUME_NEEDS_MORE_EVIDENCE"
        explanation = "A fixed turnover relationship is visible in part of the pre-registered diagnostic, but complete conditioned, strata and sensitivity coherence is not established."
    else:
        decision = "TURNOVER_X_RELATIVE_VOLUME_NO_CLEAR_INCREMENTAL_SIGNAL"
        explanation = "The fixed turnover relationship does not show aligned endpoint evidence in the pre-registered diagnostic."
    event_artifact = _write_diagnostic_events(output_dir / "events.jsonl.gz", structural)
    summary: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "COMPLETE",
        "labels": list(LABELS),
        "source_classification": SOURCE_CLASSIFICATION,
        "gateway_url": GATEWAY_URL,
        "package": PACKAGE_NAME,
        "package_version": PACKAGE_VERSION,
        "endpoint": ENDPOINT,
        "strategy": {"version": "B_BREAKOUT_RETEST_LEGACY_V1_1", "modified": False},
        "protocol": {"path": protocol_path.as_posix(), "commit_sha": protocol_commit, "file_sha256": replay.file_sha256(protocol_path), "frozen_before_outcome_read": True},
        "input_audit_manifest": input_audit_manifest_path.as_posix(),
        "cohort_reconciliation": {
            "exact_structural_rows": exact_structural,
            "exact_qualified_rows": exact_qualified,
            "in_scope_structural_rows": len(structural),
            "in_scope_qualified_rows": len(qualified),
            "feature_pair_complete_qualified_rows": len(feature_complete),
            "unique_breakout_episode_count": len(episode_records),
            "episode_deduplicated_qualified_rows": len(episode_records),
        },
        "features": {
            "primary_pair": ["turnover_rate_pct", "relative_volume"],
            "turnover_rate_pct": "daily_basic.turnover_rate percent; T-day",
            "relative_volume": "volume_T / mean(volume[T-20:T-1]) using raw frozen daily_k volume",
            "quintile_method": "stable ascending rank by feature, symbol, signal_date, original row index",
        },
        "feature_quintiles": feature_summaries,
        "conditional_and_matrix": matrix_and_conditional,
        "structural_quintiles": structural_summaries,
        "year_board_strata": strata,
        "episode_deduplicated": episode_summaries,
        "top_one_percent": top_one_percent,
        "decision_audit": {
            "turnover_5D_high_minus_low_mean_return_pct": turnover_5d,
            "turnover_5D_high_minus_low_median_return_pct": turnover_5d_median,
            "direction": direction,
            "turnover_conditional_on_relative_volume_coherent": conditional_coherent,
            "year_board_coherent": strata_coherent,
            "episode_deduplicated_coherent": sign_checks[2],
            "top_one_percent_coherent": sign_checks[3],
            "structural_coherent": sign_checks[4],
            "all_fixed_checks_pass": bool(all(sign_checks) and visible),
        },
        "decision": decision,
        "decision_explanation": explanation,
        "artifacts": {"events": event_artifact},
        "outcome_access": {
            "status": "OUTCOME_ANALYSIS_AFTER_PROTOCOL_COMMIT",
            "pre_protocol_status": OUTCOME_ACCESS_STATUS,
            "outcome_values_used": True,
        },
        "boundaries": {
            "b_spec_unchanged": True,
            "b_score_unchanged": True,
            "threshold_unchanged": True,
            "hard_gate_unchanged": True,
            "top_n_unchanged": True,
            "prospective_pipeline_unchanged": True,
            "universe_unchanged": True,
            "frozen_dataset_unchanged": True,
            "final_oos_read": False,
            "phase_2f": False,
            "c": False,
            "threshold_search": False,
            "parameter_sweep": False,
            "model_fitting": False,
            "turnover_rate_f_fished": False,
        },
        "completed_at_utc": _utc_now(),
    }
    summary["content_sha256"] = hashlib.sha256(
        (_canonical_json({key: value for key, value in summary.items() if key != "content_sha256"}) + "\n").encode("utf-8")
    ).hexdigest()
    _write_json_atomic(summary_path, summary)
    lines = [
        "# B Turnover × Relative Volume Incremental Diagnostic V1 — Tushare gateway",
        "",
        "Labels: `DEVELOPMENT` / `RECONSTRUCTED_RETROSPECTIVE` / `DATE_ANCHORED` / `NO_VINTAGE_PROOF` / `THIRD_PARTY_GATEWAY` / `DIAGNOSTIC_ONLY`",
        "",
        "## Decision",
        "",
        f"`{decision}`",
        "",
        explanation,
        "",
        "## Provenance",
        "",
        f"- source: `{SOURCE_CLASSIFICATION}` at `{GATEWAY_URL}`; `tushare=={PACKAGE_VERSION}`; endpoint `{ENDPOINT}`",
        f"- input audit: `{input_audit_manifest_path.as_posix()}`; status `RESEARCH_READY`",
        f"- pre-outcome protocol commit: `{protocol_commit}`",
        f"- exact cohort: `{exact_qualified}` qualified / `{exact_structural}` structural; in-scope: `{len(qualified)}` / `{len(structural)}`",
        f"- pair-complete qualified rows: `{len(feature_complete)}`; episode-deduplicated qualified rows: `{len(episode_records)}`",
        "",
        "## Fixed checks",
        "",
        f"- turnover 5D Q5-Q1 mean return: `{turnover_5d}` percentage points",
        f"- turnover 5D Q5-Q1 median return: `{turnover_5d_median}` percentage points",
        f"- turnover conditional on RV coherent: `{conditional_coherent}`",
        f"- year/board coherent: `{strata_coherent}`",
        f"- episode-deduplicated coherent: `{sign_checks[2]}`",
        f"- top-1% coherent: `{sign_checks[3]}`",
        f"- structural coherent: `{sign_checks[4]}`",
        "",
        "## 5×5 matrix",
        "",
        "| TQ | RVQ | N | 5D mean | 5D median | 10D mean | 5D MFE | 5D MAE |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in matrix_and_conditional["matrix_5x5"]:
        lines.append("| {turnover_quintile} | {relative_volume_quintile} | {row_n} | {m5} | {med5} | {m10} | {mfe} | {mae} |".format(
            turnover_quintile=item["turnover_quintile"], relative_volume_quintile=item["relative_volume_quintile"], row_n=item["row_n"],
            m5=item["5D"]["mean_return_pct"], med5=item["5D"]["median_return_pct"], m10=item["10D"]["mean_return_pct"], mfe=item["5D"]["mean_mfe_pct"], mae=item["5D"]["mean_mae_pct"],
        ))
    lines += [
        "",
        "## Boundaries",
        "",
        "B/spec/score/threshold/hard gate/Top-N/prospective pipeline/universe/frozen dataset were unchanged. Final OOS was not read; C and Phase 2F were not run; no threshold search, parameter sweep, model fitting, promotion or freeze occurred. `turnover_rate_f` was not used.",
        "",
        f"Event detail: `{event_artifact['path']}` (local-only deterministic artifact). Summary SHA-256: `{summary['content_sha256']}`.",
    ]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return summary


def run_pilot(
    *, raw_dir: Path, pilot_dir: Path, checkpoint_path: Path, raw_output_dir: Path,
    canonical_path: Path, manifest_path: Path, retry_sleep_seconds: float = 2.0,
) -> dict[str, Any]:
    """Run the five-date pilot without reading any outcome artifact."""

    _reject_forbidden((raw_dir, pilot_dir, checkpoint_path, raw_output_dir, manifest_path))
    pro = _credentialed_client()
    del pro  # client construction is the credential/gateway contract assertion
    dates = pilot_dates(raw_dir)
    index_dates, _bars, _meta = replay._load_index(raw_dir)
    store, _store_meta = replay._load_stock_store(raw_dir / "daily_k.parquet")
    checkpoint = acquire_dates(
        dates=dates, checkpoint_path=checkpoint_path, raw_dir=raw_output_dir,
        mode="pilot", retry_attempts=3, retry_sleep_seconds=retry_sleep_seconds,
    )
    if checkpoint.get("status") != "COMPLETE":
        raise RuntimeError(f"{STOP_FULL}: pilot checkpoint incomplete")
    import json

    payloads: dict[str, dict[str, Any]] = {}
    schema: dict[str, Any] = {}
    raw_digest = hashlib.sha256()
    for date in dates:
        path = raw_output_dir / f"daily_basic_{date.replace('-', '')}.json"
        raw_bytes = path.read_bytes()
        raw_digest.update(date.encode("utf-8") + b"\n" + raw_bytes)
        payload = json.loads(raw_bytes.decode("utf-8"))
        schema[date] = _schema_audit(payload, date, strict_unique=True)
        payloads[date] = payload
    coverage = _coverage_audit(payloads, store, index_dates)
    semantics = _semantics_audit(payloads, store, index_dates)
    canonical = write_pilot_canonical(
        raw_dir=raw_output_dir, dates=dates, canonical_path=canonical_path,
    )
    result = {
        "schema_version": SCHEMA_VERSION,
        "status": "PILOT_RESEARCH_READY",
        "labels": list(LABELS),
        "source_classification": SOURCE_CLASSIFICATION,
        "gateway_url": GATEWAY_URL,
        "package": PACKAGE_NAME,
        "package_version": PACKAGE_VERSION,
        "endpoint": ENDPOINT,
        "fields": FIELDS,
        "pilot_dates": dates,
        "schema_audit": schema,
        "coverage_audit": coverage,
        "turnover_semantics_audit": semantics,
        "raw": {
            "directory": raw_output_dir.as_posix(),
            "date_file_count": len(dates),
            "raw_stream_sha256": raw_digest.hexdigest(),
        },
        "canonical": canonical,
        "credential_present": True,
        "credential_leaked": False,
        "token_persisted": False,
        "outcome_access": {
            "status": OUTCOME_ACCESS_STATUS,
            "outcome_values_used": False,
        },
        "research_boundary": {
            "universe": "frozen daily-K date universe; Main/ChiNext/STAR only",
            "turnover_rate_f_only": False,
            "turnover_rate_f_used": False,
            "no_vintage_proof": True,
            "diagnostic_only": True,
        },
        "completed_at_utc": _utc_now(),
    }
    pilot_dir.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(manifest_path, result)
    return result


__all__ = [
    "END_DATE",
    "FIELDS",
    "GATEWAY_URL",
    "LABELS",
    "PACKAGE_VERSION",
    "PILOT_COUNT",
    "START_DATE",
    "_canonical_symbol",
    "_date_text",
    "_schema_audit",
    "_semantics_audit",
    "pilot_dates",
    "build_full_canonical",
    "audit_inputs",
    "run_diagnostic",
    "run_pilot",
    "write_pilot_canonical",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    base = Path("data/validation/b_turnover_x_relative_volume_incremental_v1/tushare_gateway")
    raw_frozen = Path("data/validation/core_signal_validation/raw")
    pilot = subparsers.add_parser("pilot")
    pilot.add_argument("--sleep", type=float, default=2.0)
    full = subparsers.add_parser("full-acquire")
    full.add_argument("--sleep", type=float, default=2.0)
    canonical = subparsers.add_parser("build-canonical")
    audit = subparsers.add_parser("audit-inputs")
    diagnostic = subparsers.add_parser("diagnostic")
    diagnostic.add_argument("--protocol-commit", required=True)
    args = parser.parse_args()
    if args.command == "pilot":
        result = run_pilot(
            raw_dir=raw_frozen, pilot_dir=base / "pilot",
            checkpoint_path=base / "checkpoint/pilot_checkpoint.json",
            raw_output_dir=base / "raw/pilot",
            canonical_path=base / "canonical/pilot_turnover.jsonl",
            manifest_path=base / "manifest/pilot_manifest.json",
            retry_sleep_seconds=args.sleep,
        )
    elif args.command == "full-acquire":
        result = acquire_dates(
            dates=_session_dates(raw_frozen),
            checkpoint_path=base / "checkpoint/full_acquisition_checkpoint.json",
            raw_dir=base / "raw/full", mode="full", retry_attempts=3,
            retry_sleep_seconds=args.sleep,
        )
    elif args.command == "build-canonical":
        result = build_full_canonical(
            checkpoint_path=base / "checkpoint/full_acquisition_checkpoint.json",
            raw_dir=base / "raw/full", canonical_path=base / "canonical/full_turnover.parquet",
            manifest_path=base / "manifest/full_acquisition_manifest.json",
        )
    elif args.command == "audit-inputs":
        result = audit_inputs(
            frozen_raw_dir=raw_frozen,
            cohort_path=Path("data/validation/b_turnover_x_relative_volume_incremental_v1/cohort_features.jsonl.gz"),
            cohort_manifest_path=Path("data/validation/b_turnover_x_relative_volume_incremental_v1/cohort_manifest.json"),
            canonical_path=base / "canonical/full_turnover.parquet",
            full_manifest_path=base / "manifest/full_acquisition_manifest.json",
            output_manifest_path=base / "manifest/input_audit_manifest.json",
        )
    else:
        result = run_diagnostic(
            frozen_raw_dir=raw_frozen,
            core_output=Path("data/validation/core_signal_validation_continuous_parts/core_replay_results.jsonl.gz"),
            cohort_path=Path("data/validation/b_turnover_x_relative_volume_incremental_v1/cohort_features.jsonl.gz"),
            canonical_path=base / "canonical/full_turnover.parquet",
            input_audit_manifest_path=base / "manifest/input_audit_manifest.json",
            protocol_path=Path("docs/research/b_turnover_x_relative_volume_incremental_v1_protocol.md"),
            protocol_commit=args.protocol_commit,
            output_dir=base / "diagnostic",
            summary_path=base / "manifest/diagnostic_summary.json",
            report_path=Path("docs/research/b_turnover_x_relative_volume_incremental_v1_tushare_gateway_report.md"),
        )
    print(_canonical_json({
        "status": result.get("status"),
        "decision": result.get("decision"),
        "content_sha256": result.get("content_sha256"),
    }))


if __name__ == "__main__":
    main()
