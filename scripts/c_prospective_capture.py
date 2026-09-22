"""Independent, outcome-blind prospective capture for the new C research stream.

The capture contract is deliberately narrower than the existing B production
chain.  A caller supplies one normalized provider snapshot containing the
provider request/receive metadata, T-day OHLCV, the historical prefix, security
identity, T-known ST status, and adjustment basis.  This module validates that
the snapshot was actually received after the T close on the same calendar day,
computes only the pre-registered C observations, and persists an immutable,
C-only evidence namespace.

There is intentionally no network client, scheduler, B evaluator, B shadow,
return tracker, canonical watchlist, daily report, or runtime-state import in
this module.  A future C-specific provider adapter may produce the normalized
snapshot, but a missing adapter or missing evidence fails closed and is never
represented as ``PROSPECTIVE_CAPTURED``.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

from c_pre_outcome_design import (
    C_RESEARCH_NAMESPACE,
    C_STRATEGY_VERSION,
    RULE_CANDIDATES,
    build_entry_observation,
    canonical_json,
    classify_c_universe_row,
    validate_ohlcv_bars,
)
from trading_calendar import CalendarUnavailable, TradingCalendar, default_calendar


C_CAPTURE_NAMESPACE = "C_PROSPECTIVE_CAPTURE_V1"
C_PROVIDER_SNAPSHOT_SCHEMA = "C_PROVIDER_SNAPSHOT_V1"
C_CAPTURE_MANIFEST_SCHEMA = "C_PROSPECTIVE_CAPTURE_MANIFEST_V1"
C_CAPTURE_LOG_SCHEMA = "C_PROSPECTIVE_CAPTURE_LOG_V1"
C_OBSERVATION_SCHEMA = "C_PROSPECTIVE_RESEARCH_OBSERVATION_V1"
C_OUTPUT_ROOT = Path("data/research/c_prospective_capture_v1")
C_INPUT_SNAPSHOT_DIR = "input_snapshots"
C_OBSERVATION_DIR = "observations"
C_MANIFEST_DIR = "manifests"
C_CAPTURE_INDEX_DIR = "captures"
C_LOG_DIR = "logs"
C_FAILURE_DIR = "failures"

C_CAPTURE_MODE = "SAME_DAY_T_CLOSE"
C_CAPTURED = "PROSPECTIVE_CAPTURED"
C_ALREADY_CAPTURED = "ALREADY_CAPTURED"
C_PARTIAL_UNVERIFIED = "CAPTURE_PARTIAL_UNVERIFIED"
C_CAPTURE_FAILED = "CAPTURE_FAILED"
C_INPUT_CONFLICT = "INPUT_CONFLICT"
C_NOT_PROSPECTIVE_BACKFILL = "NOT_PROSPECTIVE_BACKFILL"
C_NOT_AFTER_CLOSE = "NOT_AFTER_T_CLOSE"
C_INPUT_SCHEMA_INVALID = "INPUT_SCHEMA_INVALID"
C_IMMUTABILITY_CONFLICT = "IMMUTABILITY_CONFLICT"

_BJT = timezone(timedelta(hours=8))
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CODE_RE = re.compile(r"^(?:SH|SZ|BJ)?(\d{6})(?:\.(?:SH|SZ|BJ))?$", re.IGNORECASE)
_REQUIRED_ADJUSTMENT_FIELDS = ("price_basis", "volume_basis", "source")
_EXPLICIT_ST_VALUES = {"ST", "STAR_ST", "*ST"}
_NON_ST_VALUES = {"NOT_ST", "NON_ST", "NON-ST", "NOT-ST"}
_MIN_HISTORY_BARS = max(config.slow_average_window for config in RULE_CANDIDATES.values())


class CaptureError(ValueError):
    """A fail-closed C capture validation or persistence error."""

    def __init__(self, status: str, reason: str, *, details: Mapping[str, Any] | None = None) -> None:
        self.status = status
        self.reason = reason
        self.details = dict(details or {})
        super().__init__(f"{status}: {reason}")


def _canonical_bytes(value: Any) -> bytes:
    try:
        return (canonical_json(value) + "\n").encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CaptureError(C_INPUT_SCHEMA_INVALID, f"value is not canonical JSON: {exc}") from exc


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(_canonical_bytes(value))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise CaptureError("CAPTURE_STORAGE_READ_FAILURE", f"{path}: {exc}") from exc
    return digest.hexdigest()


def _canonical_date(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise CaptureError(C_INPUT_SCHEMA_INVALID, f"{field_name} must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise CaptureError(C_INPUT_SCHEMA_INVALID, f"{field_name}={value!r} is not a date") from exc
    if parsed.isoformat() != value:
        raise CaptureError(C_INPUT_SCHEMA_INVALID, f"{field_name}={value!r} is not canonical")
    return value


def _timestamp(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise CaptureError(C_INPUT_SCHEMA_INVALID, f"{field_name} must be an aware ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CaptureError(C_INPUT_SCHEMA_INVALID, f"{field_name}={value!r} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CaptureError(C_INPUT_SCHEMA_INVALID, f"{field_name} must include a timezone")
    return parsed.astimezone(_BJT)


def _timestamp_text(value: datetime) -> str:
    return value.astimezone(_BJT).isoformat()


def _nonempty_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CaptureError(C_INPUT_SCHEMA_INVALID, f"{field_name} is required")
    return value.strip()


def _safe_output_root(root: Path) -> Path:
    resolved = root.expanduser().resolve()
    normalized = resolved.as_posix().lower()
    if "continuous_speed_probe" in normalized or "final_oos" in normalized:
        raise CaptureError("FORBIDDEN_DIRECTORY_REFUSED", "C output root is outside the allowed research namespace")
    return resolved


def _write_immutable_json(path: Path, payload: Any) -> str:
    content = _canonical_bytes(payload)
    digest = sha256_bytes(content)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            existing = path.read_bytes()
        except OSError as exc:
            raise CaptureError("CAPTURE_STORAGE_READ_FAILURE", f"{path}: {exc}") from exc
        if existing != content:
            raise CaptureError(C_IMMUTABILITY_CONFLICT, f"immutable file differs: {path}")
        return digest
    try:
        with path.open("xb") as handle:
            handle.write(content)
            handle.flush()
    except FileExistsError:
        try:
            existing = path.read_bytes()
        except OSError as exc:
            raise CaptureError("CAPTURE_STORAGE_READ_FAILURE", f"{path}: {exc}") from exc
        if existing != content:
            raise CaptureError(C_IMMUTABILITY_CONFLICT, f"immutable file changed concurrently: {path}")
    except OSError as exc:
        raise CaptureError("CAPTURE_STORAGE_WRITE_FAILURE", f"{path}: {exc}") from exc
    return digest


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CaptureError("CAPTURE_STORAGE_READ_FAILURE", f"{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CaptureError("CAPTURE_STORAGE_READ_FAILURE", f"{path} is not a JSON object")
    return value


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _date_dir(target_date: str) -> str:
    return target_date.replace("-", "")


def _normalise_code(value: Any, field_name: str) -> str:
    text = _nonempty_text(value, field_name).upper()
    match = _CODE_RE.fullmatch(text)
    if not match:
        raise CaptureError(C_INPUT_SCHEMA_INVALID, f"{field_name} is not a six-digit A-share identity")
    return match.group(1)


def _normalise_symbol(value: Any, code: str, field_name: str) -> str:
    text = _nonempty_text(value, field_name).upper()
    if not re.fullmatch(r"\d{6}\.(?:SH|SZ|BJ)", text):
        raise CaptureError(C_INPUT_SCHEMA_INVALID, f"{field_name} must be like 600001.SH")
    if text[:6] != code:
        raise CaptureError(C_INPUT_SCHEMA_INVALID, f"{field_name} code does not match security identity")
    return text


def _normalise_requests(
    snapshot: Mapping[str, Any],
    *,
    target_date: str,
    session_close: datetime,
    now_bjt: datetime,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    capture = snapshot.get("capture")
    if not isinstance(capture, Mapping):
        raise CaptureError(C_INPUT_SCHEMA_INVALID, "capture metadata is missing")
    if capture.get("mode") != C_CAPTURE_MODE:
        raise CaptureError(C_INPUT_SCHEMA_INVALID, f"capture.mode must be {C_CAPTURE_MODE}")
    provider = _nonempty_text(capture.get("provider"), "capture.provider")
    provider_version = _nonempty_text(capture.get("provider_version"), "capture.provider_version")
    raw_requests = capture.get("requests")
    if not isinstance(raw_requests, Sequence) or isinstance(raw_requests, (str, bytes)) or not raw_requests:
        raise CaptureError(C_INPUT_SCHEMA_INVALID, "capture.requests must be a non-empty list")

    requests: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(raw_requests):
        if not isinstance(raw, Mapping):
            raise CaptureError(C_INPUT_SCHEMA_INVALID, f"capture.requests[{index}] is not an object")
        request_id = _nonempty_text(raw.get("request_id"), f"capture.requests[{index}].request_id")
        if request_id in by_id:
            raise CaptureError(C_INPUT_SCHEMA_INVALID, f"duplicate request_id: {request_id}")
        source = _nonempty_text(raw.get("source", provider), f"capture.requests[{index}].source")
        endpoint = _nonempty_text(raw.get("endpoint"), f"capture.requests[{index}].endpoint")
        requested_at = _timestamp(raw.get("requested_at"), f"capture.requests[{index}].requested_at")
        received_at = _timestamp(raw.get("received_at"), f"capture.requests[{index}].received_at")
        if requested_at > received_at:
            raise CaptureError(C_INPUT_SCHEMA_INVALID, f"request {request_id} received before it was requested")
        if requested_at.date().isoformat() != target_date or received_at.date().isoformat() != target_date:
            raise CaptureError(
                C_NOT_PROSPECTIVE_BACKFILL,
                f"request {request_id} was not requested and received on target date",
            )
        if requested_at < session_close or received_at < session_close:
            raise CaptureError(C_NOT_AFTER_CLOSE, f"request {request_id} is before the T session close")
        if received_at > now_bjt:
            raise CaptureError(C_INPUT_SCHEMA_INVALID, f"request {request_id} was received after runner time")
        normalized = dict(raw)
        normalized.update(
            {
                "request_id": request_id,
                "source": source,
                "endpoint": endpoint,
                "requested_at": _timestamp_text(requested_at),
                "received_at": _timestamp_text(received_at),
                "provider": provider,
                "provider_version": provider_version,
            }
        )
        response_sha = normalized.get("response_sha256")
        if response_sha is not None and (not isinstance(response_sha, str) or not _SHA256_RE.fullmatch(response_sha)):
            raise CaptureError(C_INPUT_SCHEMA_INVALID, f"request {request_id}.response_sha256 is invalid")
        response_bytes = normalized.get("response_bytes")
        if response_bytes is not None and (
            isinstance(response_bytes, bool) or not isinstance(response_bytes, int) or response_bytes < 0
        ):
            raise CaptureError(C_INPUT_SCHEMA_INVALID, f"request {request_id}.response_bytes is invalid")
        requests.append(normalized)
        by_id[request_id] = normalized
    return requests, by_id


def _adjustment_basis(raw: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise CaptureError(C_INPUT_SCHEMA_INVALID, f"{field_name} is missing")
    missing = [field for field in _REQUIRED_ADJUSTMENT_FIELDS if not isinstance(raw.get(field), str) or not raw.get(field).strip()]
    if missing:
        raise CaptureError(C_INPUT_SCHEMA_INVALID, f"{field_name} missing: {', '.join(missing)}")
    normalized = dict(raw)
    normalized["price_basis"] = str(raw["price_basis"]).strip()
    normalized["volume_basis"] = str(raw["volume_basis"]).strip()
    normalized["source"] = str(raw["source"]).strip()
    return normalized


def _st_status(raw: Any, *, target_date: str, field_name: str) -> tuple[dict[str, Any], str | None]:
    if not isinstance(raw, Mapping):
        return {"status": "UNKNOWN", "known_at_t": False, "reason": "missing ST status object"}, "UNRESOLVED_ST_STATUS"
    status = str(raw.get("status", "UNKNOWN")).strip().upper()
    known_at_t = raw.get("known_at_t") is True
    source = raw.get("source")
    known_at = raw.get("known_at")
    result: dict[str, Any] = {
        "status": status,
        "known_at_t": known_at_t,
        "source": source,
    }
    if known_at is not None:
        parsed_known_at = _timestamp(known_at, f"{field_name}.known_at")
        result["known_at"] = _timestamp_text(parsed_known_at)
    if raw.get("as_of_date") is not None:
        result["as_of_date"] = _canonical_date(raw.get("as_of_date"), f"{field_name}.as_of_date")
    reasons: list[str] = []
    if not known_at_t:
        reasons.append("UNRESOLVED_ST_STATUS")
    if status not in _NON_ST_VALUES and status not in _EXPLICIT_ST_VALUES:
        reasons.append("UNKNOWN_ST_STATUS_VALUE")
    if not isinstance(source, str) or not source.strip():
        reasons.append("ST_STATUS_SOURCE_MISSING")
    if result.get("as_of_date") not in {None, target_date}:
        reasons.append("ST_STATUS_NOT_AS_OF_T")
    if "known_at" in result and result["known_at"][:10] > target_date:
        reasons.append("ST_STATUS_KNOWN_AFTER_T")
    return result, (";".join(reasons) if reasons else None)


def _identity(raw: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise CaptureError(C_INPUT_SCHEMA_INVALID, f"{field_name} is missing")
    code = _normalise_code(raw.get("code"), f"{field_name}.code")
    symbol = _normalise_symbol(raw.get("symbol"), code, f"{field_name}.symbol")
    exchange = _nonempty_text(raw.get("exchange"), f"{field_name}.exchange").upper()
    name = _nonempty_text(raw.get("name"), f"{field_name}.name")
    security_id = _nonempty_text(raw.get("security_id", symbol), f"{field_name}.security_id")
    normalized = dict(raw)
    normalized.update({"code": code, "symbol": symbol, "exchange": exchange, "name": name, "security_id": security_id})
    return normalized


def _event_identity(symbol: str, target_date: str, rule_id: str, bars: Sequence[Mapping[str, Any]], entry: Mapping[str, Any]) -> str | None:
    structure = entry.get("structure")
    if not isinstance(structure, Mapping) or structure.get("status") != "OK":
        return None
    indices = {
        "stage_prior_high_date": int(structure["stage_prior_high_index"]),
        "low_one_date": int(structure["low_one_index"]),
        "low_two_date": int(structure["low_two_index"]),
        "confirmation_date": target_date,
    }
    try:
        payload = {
            "identity_version": "C_PULLBACK_EPISODE_ID_V1",
            "symbol": symbol,
            "target_date": target_date,
            "rule_id": rule_id,
            "entry_definition": "C_PRICE_STRUCTURE_V1",
            "stage_prior_high_date": bars[indices["stage_prior_high_date"]]["date"],
            "low_one_date": bars[indices["low_one_date"]]["date"],
            "low_two_date": bars[indices["low_two_date"]]["date"],
            "confirmation_date": target_date,
        }
    except (KeyError, IndexError, TypeError) as exc:
        raise CaptureError("OBSERVATION_IDENTITY_UNAVAILABLE", f"cannot construct C event identity: {exc}") from exc
    return f"C_PULLBACK_EPISODE_ID_V1:{sha256_json(payload)}"


def _rule_observation(
    *,
    symbol: str,
    target_date: str,
    bars: Sequence[Mapping[str, Any]],
    rule_id: str,
) -> dict[str, Any]:
    try:
        entry = build_entry_observation(bars, rule_id=rule_id)
    except (TypeError, ValueError, KeyError) as exc:
        return {
            "schema_version": C_OBSERVATION_SCHEMA,
            "namespace": C_CAPTURE_NAMESPACE,
            "strategy_version": C_STRATEGY_VERSION,
            "rule_id": rule_id,
            "symbol": symbol,
            "signal_date": target_date,
            "status": "OBSERVATION_FAILED",
            "data_quality_status": "PARTIAL_UNVERIFIED",
            "reason": f"{type(exc).__name__}: {exc}",
            "future_data_used": False,
        }

    structure = entry.get("structure", {})
    trend = entry.get("trend", {})
    if trend.get("status") == "INSUFFICIENT_HISTORY" or structure.get("status") == "INSUFFICIENT_HISTORY":
        observation_status = "OBSERVATION_INSUFFICIENT_HISTORY"
        quality_status = "PARTIAL_UNVERIFIED"
    else:
        observation_status = "OBSERVATION_RECORDED"
        quality_status = "COMPLETE"
    volume = dict(entry.get("volume", {}))
    t_volume = volume.get("t_day_relative_volume")
    if isinstance(t_volume, Mapping):
        t_volume = dict(t_volume)
        t_volume.update(
            {
                "scope": "CONFIRMATION_DAY_ONLY",
                "does_not_represent_complete_pullback_volume_path": True,
            }
        )
        volume["t_day_relative_volume"] = t_volume
    volume.update(
        {
            "rv_t_scope": "CONFIRMATION_DAY_ONLY",
            "rv_t_does_not_represent_complete_pullback_volume_path": True,
        }
    )
    event_id = _event_identity(symbol, target_date, rule_id, bars, entry)
    return {
        "schema_version": C_OBSERVATION_SCHEMA,
        "namespace": C_CAPTURE_NAMESPACE,
        "strategy_version": C_STRATEGY_VERSION,
        "rule_id": rule_id,
        "symbol": symbol,
        "signal_date": target_date,
        "status": observation_status,
        "data_quality_status": quality_status,
        "entry_candidate": bool(entry.get("entry_candidate", False)),
        "event_identity": event_id if entry.get("entry_candidate") else None,
        "entry_definition": "C_PRICE_STRUCTURE_V1",
        "price_structure_observation": {
            "trend": entry.get("trend"),
            "structure": entry.get("structure"),
            "confirmation": entry.get("confirmation"),
            "support": entry.get("support"),
            "stage_resistance": entry.get("stage_resistance"),
        },
        "volume_observation": volume,
        "observation_day": {
            "date": target_date,
            "t_close": bars[-1]["close"],
            "floating_pnl_semantics": "OBSERVATION_DAY_MARK_TO_MARK_ONLY; NOT_T_PLUS_ONE_REFERENCE_PNL",
            "pnl_value": None,
        },
        "execution_boundary": {
            "signal_timing": "T_CLOSE_SIGNAL",
            "earliest_reference_execution": "T_PLUS_ONE_XSHG_OPEN",
            "reference_execution_semantics": "REFERENCE_EXECUTION_NOT_ACTUAL_FILL",
            "t_plus_one_reference_pnl": None,
            "pnl_status": "NOT_COMPUTED_IN_PRE_OUTCOME_CAPTURE",
            "same_day_sell": "PROHIBITED_FOR_NEW_POSITION",
        },
        "future_data_used": entry.get("future_data_used") is True,
        "outcome_accessed": False,
        "return_accessed": False,
    }


def _security_record(
    raw: Any,
    *,
    target_date: str,
    request_map: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        return {
            "security_id": None,
            "quality_status": "PARTIAL_UNVERIFIED",
            "failure_reasons": ["SECURITY_ROW_NOT_OBJECT"],
            "observations": {},
        }
    record: dict[str, Any] = {"observations": {}}
    reasons: list[str] = []
    try:
        identity = _identity(raw.get("security_identity"), "security_identity")
        record["security_identity"] = identity
    except CaptureError as exc:
        identity = None
        reasons.append(exc.reason)
        record["security_identity"] = raw.get("security_identity")

    request_id = raw.get("request_id")
    if not isinstance(request_id, str) or request_id not in request_map:
        reasons.append("SECURITY_REQUEST_ID_MISSING_OR_UNKNOWN")
        request = None
    else:
        request = request_map[request_id]
        record["source"] = {
            "request_id": request_id,
            "market_source": request["source"],
            "provider": request["provider"],
            "provider_version": request["provider_version"],
            "endpoint": request["endpoint"],
            "requested_at": request["requested_at"],
            "received_at": request["received_at"],
        }
    st, st_reason = _st_status(raw.get("st_status"), target_date=target_date, field_name="st_status")
    record["st_status"] = st
    if st_reason:
        reasons.extend(st_reason.split(";"))
    try:
        adjustment = _adjustment_basis(raw.get("adjustment_basis"), "adjustment_basis")
        record["adjustment_basis"] = adjustment
    except CaptureError as exc:
        adjustment = None
        reasons.append("ADJUSTMENT_BASIS_UNVERIFIED")
        record["adjustment_basis"] = raw.get("adjustment_basis")

    prefix = raw.get("historical_prefix")
    t_ohlcv = raw.get("t_ohlcv")
    bars: tuple[dict[str, Any], ...] = ()
    if not isinstance(prefix, Sequence) or isinstance(prefix, (str, bytes)):
        reasons.append("HISTORICAL_PREFIX_MISSING")
    elif not isinstance(t_ohlcv, Mapping):
        reasons.append("T_DAY_OHLCV_MISSING")
    else:
        try:
            bars = validate_ohlcv_bars([*prefix, t_ohlcv])
            if bars[-1]["date"] != target_date:
                reasons.append("T_DAY_OHLCV_DATE_MISMATCH")
            if any(row["date"] >= target_date for row in bars[:-1]):
                reasons.append("FUTURE_OR_NON_PREFIX_BAR")
            if len(bars) < _MIN_HISTORY_BARS:
                reasons.append("INSUFFICIENT_HISTORY_PREFIX")
            record["historical_prefix"] = [dict(row) for row in bars[:-1]]
            record["t_ohlcv"] = dict(bars[-1])
            record["trade_state"] = "TRADED" if float(bars[-1]["volume"]) > 0 else "NO_TRADE_OR_ZERO_VOLUME"
        except (TypeError, ValueError, IndexError) as exc:
            reasons.append(f"OHLCV_INVALID:{type(exc).__name__}")
            record["historical_prefix"] = prefix
            record["t_ohlcv"] = t_ohlcv

    universe_status = "UNRESOLVED_ST_STATUS"
    if identity is not None:
        if st["status"] in _EXPLICIT_ST_VALUES:
            universe_status = "EXCLUDED_ST_OR_STAR_ST"
        else:
            classification = classify_c_universe_row(
                {
                    "symbol": identity["symbol"],
                    "name": identity["name"],
                    "st_status_known_at_t": st.get("known_at_t") is True,
                }
            )
            universe_status = str(classification.get("status"))
            if st["status"] in _NON_ST_VALUES and universe_status == "EXCLUDED_ST_OR_STAR_ST":
                reasons.append("ST_STATUS_AND_SECURITY_NAME_CONFLICT")
    record["universe_status"] = universe_status

    if reasons:
        record["quality_status"] = C_PARTIAL_UNVERIFIED
        record["failure_reasons"] = sorted(set(reasons))
        return record
    if identity is None or not bars:
        record["quality_status"] = C_PARTIAL_UNVERIFIED
        record["failure_reasons"] = ["SECURITY_EVIDENCE_INCOMPLETE"]
        return record

    record["quality_status"] = "COMPLETE"
    if universe_status == "ELIGIBLE":
        for rule_id in RULE_CANDIDATES:
            record["observations"][rule_id] = _rule_observation(
                symbol=identity["symbol"],
                target_date=target_date,
                bars=bars,
                rule_id=rule_id,
            )
        if any(
            observation.get("data_quality_status") != "COMPLETE"
            for observation in record["observations"].values()
        ):
            record["quality_status"] = C_PARTIAL_UNVERIFIED
            record["failure_reasons"] = ["OBSERVATION_EVIDENCE_INSUFFICIENT"]
    return record


def _capture_boundary() -> dict[str, Any]:
    return {
        "b_evaluator_called": False,
        "b_shadow_called": False,
        "b_return_tracker_called": False,
        "b_formal_watchlist_written": False,
        "b_daily_report_written": False,
        "b_production_scheduler_changed": False,
        "b_runtime_state_written": False,
        "automatic_ordering": False,
        "formal_historical_return_research_run": False,
        "final_oos_read": False,
        "c_output_namespace_only": True,
    }


def _canonical_existing_capture(root: Path, target_date: str) -> Path:
    return root / C_CAPTURE_INDEX_DIR / _date_dir(target_date) / "canonical.json"


def _failure_log(
    root: Path,
    *,
    target_date: str,
    status: str,
    reason: str,
    input_sha256: str | None,
    attempted_at: datetime,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "schema_version": C_CAPTURE_LOG_SCHEMA,
        "namespace": C_CAPTURE_NAMESPACE,
        "target_date": target_date,
        "capture_mode": C_CAPTURE_MODE,
        "status": status,
        "reason": reason,
        "input_sha256": input_sha256,
        "attempted_at": _timestamp_text(attempted_at),
        "details": dict(details or {}),
        "boundary": _capture_boundary(),
    }
    key = input_sha256 or sha256_json({"target_date": target_date, "reason": reason, "attempted_at": payload["attempted_at"]})
    stamp = attempted_at.strftime("%Y%m%dT%H%M%S%z")
    path = root / C_FAILURE_DIR / _date_dir(target_date) / f"failure_{key}_{stamp}.json"
    digest = _write_immutable_json(path, payload)
    return {"path": _relative(root, path), "sha256": digest, "payload": payload}


def _load_snapshot(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CaptureError(C_INPUT_SCHEMA_INVALID, f"cannot read provider snapshot {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CaptureError(C_INPUT_SCHEMA_INVALID, "provider snapshot must be a JSON object")
    return value


def _capture_context(
    snapshot: Mapping[str, Any],
    *,
    target_date: str,
    now_bjt: datetime,
    calendar: TradingCalendar,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], datetime]:
    if snapshot.get("schema_version") != C_PROVIDER_SNAPSHOT_SCHEMA:
        raise CaptureError(C_INPUT_SCHEMA_INVALID, f"snapshot.schema_version must be {C_PROVIDER_SNAPSHOT_SCHEMA}")
    snapshot_date = _canonical_date(snapshot.get("target_date"), "snapshot.target_date")
    if snapshot_date != target_date:
        raise CaptureError(C_INPUT_SCHEMA_INVALID, "snapshot target_date differs from CLI target date")
    if not calendar.is_trading_day(target_date):
        raise CaptureError("NON_TRADING_SESSION", f"{target_date} is not an XSHG trading session")
    try:
        session_close = calendar.session_close(target_date).astimezone(_BJT)
    except CalendarUnavailable as exc:
        raise CaptureError("CALENDAR_UNAVAILABLE", str(exc)) from exc
    if now_bjt.date().isoformat() != target_date:
        raise CaptureError(C_NOT_PROSPECTIVE_BACKFILL, "runner date differs from target T; later retrieval is not prospective capture")
    if now_bjt < session_close:
        raise CaptureError(C_NOT_AFTER_CLOSE, "runner is not executing after the target session close on T")
    return (*_normalise_requests(snapshot, target_date=target_date, session_close=session_close, now_bjt=now_bjt), session_close)


def capture_t_close_snapshot(
    snapshot: Mapping[str, Any],
    *,
    target_date: str,
    output_root: str | Path = C_OUTPUT_ROOT,
    now_bjt: datetime | None = None,
    calendar: TradingCalendar | None = None,
) -> dict[str, Any]:
    """Validate and persist one same-day C T-close capture.

    The normalized provider packet is the only acquisition input.  The method
    never calls a provider and never reads a future bar.  It returns an
    immutable identity even for partial/failure cases so the reason remains
    auditable without fabricating a complete prospective record.
    """

    target_date = _canonical_date(target_date, "target_date")
    root = _safe_output_root(Path(output_root))
    runner_now = (now_bjt or datetime.now(_BJT)).astimezone(_BJT)
    if runner_now.tzinfo is None:
        raise CaptureError(C_INPUT_SCHEMA_INVALID, "now_bjt must be timezone aware")
    try:
        input_bytes = _canonical_bytes(snapshot)
    except CaptureError as exc:
        failure = _failure_log(
            root,
            target_date=target_date,
            status=exc.status,
            reason=exc.reason,
            input_sha256=None,
            attempted_at=runner_now,
            details=exc.details,
        )
        return {"status": C_CAPTURE_FAILED, "reason": exc.reason, "failure_log": failure["path"]}
    input_sha256 = sha256_bytes(input_bytes)
    input_path = root / C_INPUT_SNAPSHOT_DIR / _date_dir(target_date) / f"input_{input_sha256}.json"
    try:
        input_digest = _write_immutable_json(input_path, snapshot)
    except CaptureError as exc:
        failure = _failure_log(
            root,
            target_date=target_date,
            status=exc.status,
            reason=exc.reason,
            input_sha256=input_sha256,
            attempted_at=runner_now,
            details=exc.details,
        )
        return {
            "status": C_CAPTURE_FAILED,
            "reason": exc.reason,
            "input_sha256": input_sha256,
            "failure_log": failure["path"],
        }

    canonical_path = _canonical_existing_capture(root, target_date)
    if canonical_path.exists():
        existing = _read_json(canonical_path)
        if existing.get("input_sha256") == input_sha256:
            manifest_path = root / str(existing.get("manifest_path", ""))
            if not manifest_path.is_file():
                failure = _failure_log(
                    root,
                    target_date=target_date,
                    status="CANONICAL_CAPTURE_CORRUPT",
                    reason="canonical capture manifest is missing",
                    input_sha256=input_sha256,
                    attempted_at=runner_now,
                )
                return {"status": C_CAPTURE_FAILED, "reason": "canonical capture manifest is missing", "failure_log": failure["path"]}
            return {
                "status": C_ALREADY_CAPTURED,
                "capture_status": existing.get("capture_status"),
                "target_date": target_date,
                "input_sha256": input_sha256,
                "input_snapshot": _relative(root, input_path),
                "manifest": existing.get("manifest_path"),
                "observation": existing.get("observation_path"),
                "canonical": _relative(root, canonical_path),
            }
        failure = _failure_log(
            root,
            target_date=target_date,
            status=C_INPUT_CONFLICT,
            reason="a different immutable input snapshot already owns this T date",
            input_sha256=input_sha256,
            attempted_at=runner_now,
            details={"existing_input_sha256": existing.get("input_sha256")},
        )
        return {
            "status": C_INPUT_CONFLICT,
            "reason": "a different immutable input snapshot already owns this T date",
            "input_sha256": input_sha256,
            "failure_log": failure["path"],
        }

    try:
        cal = calendar or default_calendar()
        requests, request_map, session_close = _capture_context(
            snapshot,
            target_date=target_date,
            now_bjt=runner_now,
            calendar=cal,
        )
        raw_securities = snapshot.get("securities")
        if not isinstance(raw_securities, Sequence) or isinstance(raw_securities, (str, bytes)) or not raw_securities:
            raise CaptureError(C_INPUT_SCHEMA_INVALID, "snapshot.securities must be a non-empty list")
        security_records = [
            _security_record(raw, target_date=target_date, request_map=request_map)
            for raw in raw_securities
        ]
        if not security_records:
            raise CaptureError(C_INPUT_SCHEMA_INVALID, "snapshot has no security records")
        quality_failures = [
            {
                "security_id": record.get("security_identity", {}).get("security_id")
                if isinstance(record.get("security_identity"), Mapping)
                else record.get("security_id"),
                "symbol": record.get("security_identity", {}).get("symbol")
                if isinstance(record.get("security_identity"), Mapping)
                else None,
                "status": record.get("quality_status"),
                "reasons": list(record.get("failure_reasons", [])),
            }
            for record in security_records
            if record.get("quality_status") != "COMPLETE"
        ]
        eligible_records = [
            record
            for record in security_records
            if record.get("quality_status") == "COMPLETE" and record.get("universe_status") == "ELIGIBLE"
        ]
        full_universe = {
            "scope": "FULL_COMPARABLE_UNIVERSE",
            "definition": "C_MAIN_BOARD_NON_ST_V1",
            "rule_matching_applied": False,
            "cohort_claim": "all complete eligible security-date observations before rule-specific event matching",
            "security_ids": [record["security_identity"]["security_id"] for record in eligible_records],
            "symbols": [record["security_identity"]["symbol"] for record in eligible_records],
            "count": len(eligible_records),
        }
        matched: dict[str, dict[str, Any]] = {}
        for rule_id in RULE_CANDIDATES:
            events: list[dict[str, Any]] = []
            for record in eligible_records:
                observation = record.get("observations", {}).get(rule_id, {})
                if observation.get("entry_candidate") is True and observation.get("event_identity"):
                    events.append(
                        {
                            "event_identity": observation["event_identity"],
                            "security_id": record["security_identity"]["security_id"],
                            "symbol": record["security_identity"]["symbol"],
                            "signal_date": target_date,
                            "rule_id": rule_id,
                            "entry_definition": "C_PRICE_STRUCTURE_V1",
                        }
                    )
            matched[rule_id] = {
                "scope": "MATCHED_EVENT_SAMPLE",
                "rule_id": rule_id,
                "same_as_full_universe": False,
                "cohort_claim": "rule-specific matched event sample; no automatic same-entry-cohort claim across rules",
                "events": events,
                "count": len(events),
            }
        capture_status = C_PARTIAL_UNVERIFIED if quality_failures else C_CAPTURED
        observation_payload = {
            "schema_version": C_OBSERVATION_SCHEMA,
            "namespace": C_CAPTURE_NAMESPACE,
            "strategy_namespace": C_RESEARCH_NAMESPACE,
            "strategy_version": C_STRATEGY_VERSION,
            "target_date": target_date,
            "capture_mode": C_CAPTURE_MODE,
            "capture_status": capture_status,
            "source_requests": requests,
            "session_close_bjt": _timestamp_text(session_close),
            "full_comparable_universe": full_universe,
            "matched_event_samples": matched,
            "securities": security_records,
            "cost_model": {
                "status": "NOT_USED_IN_PRE_OUTCOME_OBSERVATION",
                "formal_research_gate": "TRANSACTION_COST_MODEL_MUST_BE_PINNED_BEFORE_FORMAL_RETURN_RESEARCH",
                "source": None,
            },
            "observation_pnl_boundary": {
                "t_close_observation_day_floating_pnl": "NOT_A_T_PLUS_ONE_REFERENCE_PNL",
                "t_plus_one_reference_execution_pnl": "NOT_COMPUTED_IN_THIS_CAPTURE",
                "actual_fill": "NOT_OBSERVED",
            },
            "input_snapshot_sha256": input_digest,
            "outcome_accessed": False,
            "return_accessed": False,
            "formal_historical_return_research_run": False,
            "boundary": _capture_boundary(),
        }
        observation_path = root / C_OBSERVATION_DIR / _date_dir(target_date) / f"observation_{input_sha256}.json"
        observation_digest = _write_immutable_json(observation_path, observation_payload)
        manifest_payload = {
            "schema_version": C_CAPTURE_MANIFEST_SCHEMA,
            "namespace": C_CAPTURE_NAMESPACE,
            "strategy_namespace": C_RESEARCH_NAMESPACE,
            "strategy_version": C_STRATEGY_VERSION,
            "target_date": target_date,
            "capture_mode": C_CAPTURE_MODE,
            "capture_status": capture_status,
            "source": {
                "provider": snapshot["capture"]["provider"],
                "provider_version": snapshot["capture"]["provider_version"],
                "request_count": len(requests),
                "requested_at": min(request["requested_at"] for request in requests),
                "received_at": max(request["received_at"] for request in requests),
                "session_close_bjt": _timestamp_text(session_close),
                "same_calendar_date": True,
                "backfill": False,
            },
            "input_snapshot": {
                "path": _relative(root, input_path),
                "sha256": input_digest,
                "bytes": len(input_bytes),
            },
            "research_observation": {
                "path": _relative(root, observation_path),
                "sha256": observation_digest,
            },
            "full_comparable_universe": full_universe,
            "matched_event_sample_counts": {rule_id: value["count"] for rule_id, value in matched.items()},
            "quality_failures": quality_failures,
            "only_same_day_capture_may_be_prospective_captured": True,
            "later_historical_retrieval_is_not_prospective_evidence": True,
            "boundary": _capture_boundary(),
        }
        manifest_path = root / C_MANIFEST_DIR / _date_dir(target_date) / f"capture_{input_sha256}.json"
        manifest_digest = _write_immutable_json(manifest_path, manifest_payload)
        log_payload = {
            "schema_version": C_CAPTURE_LOG_SCHEMA,
            "namespace": C_CAPTURE_NAMESPACE,
            "target_date": target_date,
            "capture_mode": C_CAPTURE_MODE,
            "status": capture_status,
            "input_sha256": input_digest,
            "observation_sha256": observation_digest,
            "manifest_sha256": manifest_digest,
            "runner_observed_at": _timestamp_text(runner_now),
            "quality_failure_count": len(quality_failures),
            "quality_failures": quality_failures,
            "boundary": _capture_boundary(),
        }
        log_path = root / C_LOG_DIR / _date_dir(target_date) / f"capture_{input_sha256}.json"
        log_digest = _write_immutable_json(log_path, log_payload)
        canonical_payload = {
            "schema_version": C_CAPTURE_MANIFEST_SCHEMA,
            "namespace": C_CAPTURE_NAMESPACE,
            "target_date": target_date,
            "capture_status": capture_status,
            "input_sha256": input_digest,
            "observation_path": _relative(root, observation_path),
            "manifest_path": _relative(root, manifest_path),
            "log_path": _relative(root, log_path),
            "log_sha256": log_digest,
            "same_day_capture": True,
            "immutable": True,
        }
        _write_immutable_json(canonical_path, canonical_payload)
        return {
            "status": capture_status,
            "target_date": target_date,
            "input_sha256": input_digest,
            "observation_sha256": observation_digest,
            "manifest_sha256": manifest_digest,
            "log_sha256": log_digest,
            "input_snapshot": _relative(root, input_path),
            "observation": _relative(root, observation_path),
            "manifest": _relative(root, manifest_path),
            "log": _relative(root, log_path),
            "canonical": _relative(root, canonical_path),
            "quality_failure_count": len(quality_failures),
            "full_comparable_universe_count": full_universe["count"],
            "matched_event_sample_counts": {rule_id: value["count"] for rule_id, value in matched.items()},
        }
    except (CaptureError, CalendarUnavailable, OSError, TypeError, ValueError) as exc:
        if isinstance(exc, CaptureError):
            status, reason, details = exc.status, exc.reason, exc.details
        else:
            status, reason, details = C_CAPTURE_FAILED, f"{type(exc).__name__}: {exc}", {}
        failure = _failure_log(
            root,
            target_date=target_date,
            status=status,
            reason=reason,
            input_sha256=input_sha256,
            attempted_at=runner_now,
            details=details,
        )
        return {
            "status": status if status in {C_INPUT_CONFLICT, C_NOT_PROSPECTIVE_BACKFILL, C_NOT_AFTER_CLOSE} else C_CAPTURE_FAILED,
            "reason": reason,
            "target_date": target_date,
            "input_sha256": input_sha256,
            "input_snapshot": _relative(root, input_path),
            "failure_log": failure["path"],
        }


def verify_persisted_capture(manifest_path: str | Path, *, output_root: str | Path = C_OUTPUT_ROOT) -> dict[str, Any]:
    """Verify input/observation hashes and C-only boundary flags."""

    root = _safe_output_root(Path(output_root))
    manifest_file = Path(manifest_path)
    if not manifest_file.is_absolute():
        manifest_file = root / manifest_file
    manifest = _read_json(manifest_file)
    if manifest.get("namespace") != C_CAPTURE_NAMESPACE:
        raise CaptureError("CAPTURE_IDENTITY_MISMATCH", "manifest is not in the C prospective namespace")
    input_info = manifest.get("input_snapshot")
    observation_info = manifest.get("research_observation")
    if not isinstance(input_info, Mapping) or not isinstance(observation_info, Mapping):
        raise CaptureError("CAPTURE_IDENTITY_MISMATCH", "manifest lacks input/observation identity")
    input_file = root / str(input_info["path"])
    observation_file = root / str(observation_info["path"])
    input_actual = file_sha256(input_file)
    observation_actual = file_sha256(observation_file)
    if input_actual != input_info.get("sha256"):
        raise CaptureError("CAPTURE_HASH_MISMATCH", "input snapshot SHA-256 mismatch")
    if observation_actual != observation_info.get("sha256"):
        raise CaptureError("CAPTURE_HASH_MISMATCH", "research observation SHA-256 mismatch")
    boundary = manifest.get("boundary")
    if boundary != _capture_boundary():
        raise CaptureError("CAPTURE_BOUNDARY_MISMATCH", "manifest boundary is not C-only")
    return {
        "status": "PASS",
        "manifest_sha256": file_sha256(manifest_file),
        "input_sha256": input_actual,
        "observation_sha256": observation_actual,
        "boundary": boundary,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    capture = subparsers.add_parser("capture", help="persist one normalized same-day C T-close provider snapshot")
    capture.add_argument("--date", required=True, help="T trading date, YYYY-MM-DD")
    capture.add_argument("--input-snapshot", type=Path, required=True, help="C_PROVIDER_SNAPSHOT_V1 JSON packet")
    capture.add_argument("--output-root", type=Path, default=C_OUTPUT_ROOT)
    capture.add_argument("--now-bjt", default=None, help="aware timestamp for controlled execution tests")
    verify = subparsers.add_parser("verify", help="verify one persisted C capture")
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--output-root", type=Path, default=C_OUTPUT_ROOT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "verify":
        result = verify_persisted_capture(args.manifest, output_root=args.output_root)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    snapshot = _load_snapshot(args.input_snapshot)
    now_bjt = _timestamp(args.now_bjt, "now_bjt") if args.now_bjt else None
    result = capture_t_close_snapshot(
        snapshot,
        target_date=args.date,
        output_root=args.output_root,
        now_bjt=now_bjt,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") in {C_CAPTURED, C_ALREADY_CAPTURED} else 1


__all__ = [
    "C_ALREADY_CAPTURED",
    "C_CAPTURED",
    "C_CAPTURE_MANIFEST_SCHEMA",
    "C_CAPTURE_MODE",
    "C_CAPTURE_NAMESPACE",
    "C_CAPTURE_FAILED",
    "C_INPUT_CONFLICT",
    "C_INPUT_SCHEMA_INVALID",
    "C_NOT_AFTER_CLOSE",
    "C_NOT_PROSPECTIVE_BACKFILL",
    "C_OBSERVATION_SCHEMA",
    "C_OUTPUT_ROOT",
    "C_PARTIAL_UNVERIFIED",
    "C_PROVIDER_SNAPSHOT_SCHEMA",
    "CaptureError",
    "capture_t_close_snapshot",
    "file_sha256",
    "main",
    "sha256_bytes",
    "sha256_json",
    "verify_persisted_capture",
]


if __name__ == "__main__":
    raise SystemExit(main())
