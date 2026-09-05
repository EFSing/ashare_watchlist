"""Bounded third-party Tushare-compatible turnover acquisition.

This module is intentionally separate from the historical AkShare acquisition.
It uses only ``daily_basic`` through the explicitly classified
``THIRD_PARTY_TUSHARE_COMPATIBLE_GATEWAY`` and never changes B semantics.

All artifacts produced here remain DEVELOPMENT / RECONSTRUCTED_RETROSPECTIVE /
DATE_ANCHORED / NO_VINTAGE_PROOF / THIRD_PARTY_GATEWAY / DIAGNOSTIC_ONLY.
"""

from __future__ import annotations

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
    "run_pilot",
    "write_pilot_canonical",
]
