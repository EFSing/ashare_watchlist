"""Independent, outcome-blind prospective capture for the new C research stream.

The capture contract is deliberately narrower than the existing B production
chain. The separate C provider adapter supplies a normalized provider packet
with exact response-body references, request identities, T-day OHLCV, the
historical prefix, security identity, T-day ST source and adjustment basis.
This module validates and persists that packet in an immutable C-only namespace.

There is intentionally no B acquisition client, scheduler, B evaluator, B
shadow, return tracker, canonical watchlist, daily report, or runtime-state
import in this module. A missing adapter or missing evidence fails closed and
is never represented as ``PROSPECTIVE_CAPTURED``.
"""

from __future__ import annotations

import argparse
import base64
import binascii
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import hashlib
import gzip
import json
import math
import os
from pathlib import Path
import re
import tempfile
import threading
import time
from typing import Any
from urllib.parse import parse_qs, urlsplit
import uuid
import zlib

from c_pre_outcome_design import (
    C_RESEARCH_NAMESPACE,
    C_STRATEGY_VERSION,
    RULE_CANDIDATES,
    build_entry_observation,
    canonical_json,
    classify_c_universe_row,
    validate_ohlcv_bars,
)
from universe_policy import BOARD_MAIN, classify_board
from trading_calendar import CalendarUnavailable, TradingCalendar, default_calendar


C_CAPTURE_NAMESPACE = "C_PROSPECTIVE_CAPTURE_V1"
C_PROVIDER_SNAPSHOT_SCHEMA = "C_PROVIDER_SNAPSHOT_V2"
C_PROVIDER_NAME = "HiThink Financial-API"
C_PROVIDER_HOST = "fuyao.aicubes.cn"
C_PROVIDER_VERSION = "FINANCIAL_API_REST_V1"
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
C_CAPTURE_READY = "CAPTURE_READY_FOR_FINALIZE"
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
_C_OUTPUT_SUFFIX = Path("data/research/c_prospective_capture_v1")
_FORBIDDEN_OUTPUT_SEGMENTS = {
    "runtime-state", "runtime_state", "reports", "watchlist", "watchlists",
    "formal", "production", "validation", "final_oos", "continuous_speed_probe", "shadow_monitor",
}
_LOCKS_GUARD = threading.Lock()
_DATE_LOCKS: dict[str, threading.Lock] = {}
_C_PROVIDER_ADAPTER_TOKEN = object()


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


def _safe_output_root() -> Path:
    root = Path(C_OUTPUT_ROOT).expanduser().resolve()
    suffix = tuple(part.lower() for part in _C_OUTPUT_SUFFIX.parts)
    if (
        tuple(part.lower() for part in root.parts[-len(suffix) :]) != suffix
        or _FORBIDDEN_OUTPUT_SEGMENTS.intersection(part.lower() for part in root.parts)
    ):
        raise CaptureError("FORBIDDEN_DIRECTORY_REFUSED", "C output root must be data/research/c_prospective_capture_v1")
    return root


def _safe_store_path(root: Path, relative: str | Path) -> Path:
    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        raise CaptureError("FORBIDDEN_DIRECTORY_REFUSED", "C artifact path escapes the independent C research root")
    return candidate


def _provider_response_bytes(raw: Mapping[str, Any], root: Path) -> bytes:
    body_path = raw.get("response_body_path")
    if isinstance(body_path, str) and body_path:
        stored_path = _safe_store_path(root, body_path)
        try:
            envelope = json.loads(stored_path.read_text(encoding="utf-8"))
            body = base64.b64decode(envelope["response_body_gzip_base64"], validate=True)
            return gzip.decompress(body)
        except (OSError, EOFError, gzip.BadGzipFile, zlib.error, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, binascii.Error) as exc:
            raise CaptureError("PROVIDER_RESPONSE_BODY_INVALID", f"cannot read compressed provider response: {exc}") from exc
    response_body_b64 = raw.get("response_body_base64")
    if isinstance(response_body_b64, str) and response_body_b64:
        try:
            return base64.b64decode(response_body_b64, validate=True)
        except binascii.Error as exc:
            raise CaptureError("PROVIDER_RESPONSE_BODY_INVALID", "inline provider response is not valid base64") from exc
    raise CaptureError("PROVIDER_RESPONSE_BODY_MISSING", "request lacks an immutable raw response body reference")


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
    temp_name: str | None = None
    try:
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temp_name, path)
        except FileExistsError:
            existing = path.read_bytes()
            if existing != content:
                raise CaptureError(C_IMMUTABILITY_CONFLICT, f"immutable file changed concurrently: {path}")
    except FileExistsError:
        try:
            existing = path.read_bytes()
        except OSError as exc:
            raise CaptureError("CAPTURE_STORAGE_READ_FAILURE", f"{path}: {exc}") from exc
        if existing != content:
            raise CaptureError(C_IMMUTABILITY_CONFLICT, f"immutable file changed concurrently: {path}")
    except CaptureError:
        raise
    except OSError as exc:
        raise CaptureError("CAPTURE_STORAGE_WRITE_FAILURE", f"{path}: {exc}") from exc
    finally:
        if temp_name:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
    return digest


@contextmanager
def _capture_lock(root: Path, target_date: str):
    lock_key = f"{root.resolve()}:{target_date}"
    with _LOCKS_GUARD:
        local_lock = _DATE_LOCKS.setdefault(lock_key, threading.Lock())
    local_lock.acquire()
    handle = None
    locked = False
    try:
        lock_path = root / ".locks" / f"{_date_dir(target_date)}.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with lock_path.open("xb") as created:
                created.write(b"0")
                created.flush()
        except FileExistsError:
            pass
        handle = lock_path.open("r+b")
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            while True:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        locked = True
        yield
    finally:
        try:
            if handle is not None and locked:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            try:
                if handle is not None:
                    handle.close()
            finally:
                local_lock.release()


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
    root: Path,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    capture = snapshot.get("capture")
    if not isinstance(capture, Mapping):
        raise CaptureError(C_INPUT_SCHEMA_INVALID, "capture metadata is missing")
    if capture.get("mode") != C_CAPTURE_MODE:
        raise CaptureError(C_INPUT_SCHEMA_INVALID, f"capture.mode must be {C_CAPTURE_MODE}")
    provider = _nonempty_text(capture.get("provider"), "capture.provider")
    if provider != C_PROVIDER_NAME:
        raise CaptureError(C_INPUT_SCHEMA_INVALID, f"capture.provider must be {C_PROVIDER_NAME}")
    provider_version = _nonempty_text(capture.get("provider_version"), "capture.provider_version")
    if provider_version != C_PROVIDER_VERSION:
        raise CaptureError(C_INPUT_SCHEMA_INVALID, f"capture.provider_version must be {C_PROVIDER_VERSION}")
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
        if source != provider:
            raise CaptureError(C_INPUT_SCHEMA_INVALID, f"request {request_id} source differs from the configured provider")
        endpoint = _nonempty_text(raw.get("endpoint"), f"capture.requests[{index}].endpoint")
        if endpoint not in {"/api/meta/tickers/list", "/api/a-share/prices/historical"}:
            raise CaptureError(C_INPUT_SCHEMA_INVALID, f"request {request_id} uses an unsupported C provider endpoint")
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
        method = _nonempty_text(raw.get("method"), f"request {request_id}.method").upper()
        request_url = _nonempty_text(raw.get("url"), f"request {request_id}.url")
        parsed_url = urlsplit(request_url)
        if (
            method != "GET"
            or parsed_url.scheme != "https"
            or parsed_url.hostname != C_PROVIDER_HOST
            or parsed_url.port not in {None, 443}
            or parsed_url.username is not None
            or parsed_url.password is not None
            or parsed_url.fragment
            or parsed_url.path != endpoint
        ):
            raise CaptureError(C_INPUT_SCHEMA_INVALID, f"request {request_id} method/url/endpoint identity is invalid")
        http_status = raw.get("http_status")
        if isinstance(http_status, bool) or not isinstance(http_status, int) or http_status != 200:
            raise CaptureError("PROVIDER_RESPONSE_NOT_SUCCESSFUL", f"request {request_id} did not return HTTP 200")
        try:
            response_body = _provider_response_bytes(raw, root)
            response_document = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CaptureError("PROVIDER_RESPONSE_BODY_INVALID", f"request {request_id} raw response is not valid JSON") from exc
        if not isinstance(response_document, Mapping):
            raise CaptureError("PROVIDER_RESPONSE_BODY_INVALID", f"request {request_id} response envelope is not an object")
        if response_document.get("request_id") != request_id or response_document.get("code") != 0:
            raise CaptureError("PROVIDER_RESPONSE_IDENTITY_MISMATCH", f"request {request_id} does not match its response envelope")
        actual_response_sha = sha256_bytes(response_body)
        supplied_response_sha = raw.get("response_sha256")
        supplied_response_bytes = raw.get("response_bytes")
        if supplied_response_sha != actual_response_sha:
            raise CaptureError("PROVIDER_RESPONSE_HASH_MISMATCH", f"request {request_id} response SHA-256 does not match raw bytes")
        if isinstance(supplied_response_bytes, bool) or supplied_response_bytes != len(response_body):
            raise CaptureError("PROVIDER_RESPONSE_LENGTH_MISMATCH", f"request {request_id} response length does not match raw bytes")

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
                "method": method,
                "url": request_url,
                "http_status": http_status,
                "response_bytes": len(response_body),
                "response_sha256": actual_response_sha,
                "query_params": {key: values[-1] for key, values in parse_qs(parsed_url.query, keep_blank_values=True).items()},
                "_response_document": response_document,
                "response_identity": {
                    "provider_request_id": request_id,
                    "method": method,
                    "url": request_url,
                    "endpoint": endpoint,
                    "http_status": http_status,
                    "response_bytes": len(response_body),
                    "response_sha256": actual_response_sha,
                },
            }
        )
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


def _st_status(
    raw: Any,
    *,
    target_date: str,
    field_name: str,
    request_map: Mapping[str, Mapping[str, Any]],
    source_row: Mapping[str, Any] | None,
    source_request_id_for_row: str | None,
    source_as_of_date: str | None,
    source_known_at: str | None,
    symbol: str | None,
    runner_now: datetime,
) -> tuple[dict[str, Any], str | None]:
    if not isinstance(raw, Mapping):
        return {"status": "UNKNOWN", "known_at_t": False, "reason": "missing ST status object"}, "UNRESOLVED_ST_STATUS"
    status = str(raw.get("status", "UNKNOWN")).strip().upper()
    source = raw.get("source")
    source_request_id = raw.get("source_request_id")
    reasons: list[str] = []
    request = request_map.get(source_request_id) if isinstance(source_request_id, str) else None
    if request is None:
        reasons.append("ST_STATUS_SOURCE_REQUEST_MISSING")
    as_of_date = None
    if raw.get("as_of_date") is not None:
        as_of_date = _canonical_date(raw.get("as_of_date"), f"{field_name}.as_of_date")
    else:
        reasons.append("ST_STATUS_AS_OF_DATE_MISSING")
    known_at: datetime | None = None
    if raw.get("known_at") is not None:
        known_at = _timestamp(raw.get("known_at"), f"{field_name}.known_at")
    else:
        reasons.append("ST_STATUS_KNOWN_AT_MISSING")
    result: dict[str, Any] = {
        "status": status,
        "known_at_t": False,
        "source": source,
        "source_request_id": source_request_id,
        "as_of_date": as_of_date,
    }
    if status not in _NON_ST_VALUES and status not in _EXPLICIT_ST_VALUES:
        reasons.append("UNKNOWN_ST_STATUS_VALUE")
    if not isinstance(source, str) or not source.strip() or request is None:
        reasons.append("ST_STATUS_SOURCE_MISSING")
    elif source != f"{request['source']}:{request['endpoint']}":
        reasons.append("ST_STATUS_SOURCE_IDENTITY_MISMATCH")
    if as_of_date != target_date:
        reasons.append("ST_STATUS_NOT_AS_OF_T")
    if request is not None:
        if request.get("endpoint") != "/api/meta/tickers/list":
            reasons.append("ST_STATUS_SOURCE_NOT_TICKER_LIST")
        if source_row is None or request.get("request_id") != source_request_id:
            reasons.append("ST_STATUS_SOURCE_ROW_MISSING")
        if source_request_id_for_row != source_request_id:
            reasons.append("ST_STATUS_SOURCE_REQUEST_MISMATCH")
        if as_of_date != source_as_of_date or source_as_of_date != target_date:
            reasons.append("ST_STATUS_SOURCE_AS_OF_DATE_UNVERIFIED")
        if isinstance(source_row, Mapping):
            source_symbol = str(source_row.get("thscode", "")).strip().upper()
            source_name = source_row.get("name")
            if source_symbol != symbol or not isinstance(source_name, str) or not source_name.strip():
                reasons.append("ST_STATUS_SOURCE_ROW_IDENTITY_MISMATCH")
            elif isinstance(symbol, str):
                source_classification = classify_c_universe_row(
                    {"symbol": symbol, "name": source_name, "st_status_known_at_t": True}
                )
                if source_classification.get("status") == "EXCLUDED_ST_OR_STAR_ST":
                    expected_status = "ST"
                elif source_classification.get("status") == "ELIGIBLE":
                    expected_status = "NOT_ST"
                else:
                    expected_status = "UNKNOWN"
                if expected_status == "UNKNOWN" or (
                    (status in _EXPLICIT_ST_VALUES) != (expected_status == "ST")
                ):
                    reasons.append("ST_STATUS_VALUE_DOES_NOT_MATCH_SOURCE_NAME")
        if known_at is not None:
            request_received_at = _timestamp(request.get("received_at"), "request.received_at")
            if known_at != request_received_at or source_known_at != _timestamp_text(request_received_at):
                reasons.append("ST_STATUS_KNOWN_AT_NOT_BOUND_TO_RESPONSE")
            if known_at > runner_now:
                reasons.append("ST_STATUS_KNOWN_AFTER_RUNNER_TIME")
            if known_at.date().isoformat() != target_date:
                reasons.append("ST_STATUS_KNOWN_AT_NOT_ON_T")
            result["known_at"] = _timestamp_text(known_at)
    if reasons:
        reasons.append("UNRESOLVED_ST_STATUS")
    else:
        result["known_at_t"] = True
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


def _provider_history_bars(request: Mapping[str, Any], *, symbol: str, target_date: str) -> list[dict[str, Any]]:
    if request.get("endpoint") != "/api/a-share/prices/historical":
        raise CaptureError("PROVIDER_HISTORY_SOURCE_UNVERIFIED", "security history must come from the C historical-K endpoint")
    params = request.get("query_params")
    if (
        not isinstance(params, Mapping)
        or params.get("thscode") != symbol
        or params.get("interval") != "1d"
        or params.get("adjust") != "none"
    ):
        raise CaptureError("PROVIDER_HISTORY_REQUEST_IDENTITY_MISMATCH", f"historical request does not identify {symbol} daily bars")
    try:
        start_ms = int(params["start"])
        end_ms = int(params["end"])
        start_date = datetime.fromtimestamp(start_ms / 1000, timezone.utc).astimezone(_BJT).date().isoformat()
        end_date = datetime.fromtimestamp(end_ms / 1000, timezone.utc).astimezone(_BJT).date().isoformat()
    except (KeyError, TypeError, ValueError, OverflowError, OSError) as exc:
        raise CaptureError("PROVIDER_HISTORY_REQUEST_IDENTITY_MISMATCH", f"historical request has invalid start/end: {exc}") from exc
    if start_date >= target_date or end_date != target_date:
        raise CaptureError("PROVIDER_HISTORY_REQUEST_IDENTITY_MISMATCH", "historical request must cover a prefix and end on T")
    document = request.get("_response_document")
    data = document.get("data") if isinstance(document, Mapping) else None
    items = data.get("item") if isinstance(data, Mapping) else None
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
        raise CaptureError("PROVIDER_HISTORY_RESPONSE_INVALID", f"historical response for {symbol} lacks data.item")
    bars: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise CaptureError("PROVIDER_HISTORY_RESPONSE_INVALID", f"historical row {index} for {symbol} is not an object")
        date_ms = item.get("date_ms")
        if isinstance(date_ms, bool) or not isinstance(date_ms, (int, float)):
            raise CaptureError("PROVIDER_HISTORY_RESPONSE_INVALID", f"historical row {index} for {symbol} lacks date_ms")
        bar_date = datetime.fromtimestamp(float(date_ms) / 1000, timezone.utc).astimezone(_BJT).date().isoformat()
        bars.append(
            {
                "date": bar_date,
                "open": item.get("open_price"),
                "high": item.get("high_price"),
                "low": item.get("low_price"),
                "close": item.get("close_price"),
                "volume": item.get("volume"),
            }
        )
    if any(bar["date"] > target_date for bar in bars):
        raise CaptureError("FUTURE_OR_NON_PREFIX_BAR", f"provider response for {symbol} contains a bar after T")
    return bars


def _security_record(
    raw: Any,
    *,
    target_date: str,
    request_map: Mapping[str, Mapping[str, Any]],
    universe_rows: Mapping[str, tuple[Mapping[str, Any], str]],
    runner_now: datetime,
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

    source_row_info = universe_rows.get(identity["symbol"]) if identity is not None else None
    if identity is not None:
        if source_row_info is None:
            reasons.append("SECURITY_IDENTITY_NOT_IN_VERIFIED_UNIVERSE")
        else:
            source_row, _source_request_id, _source_as_of_date, _source_known_at = source_row_info
            if identity.get("name") != source_row.get("name") or identity.get("exchange") != source_row.get("exchange"):
                reasons.append("SECURITY_IDENTITY_DIFFERS_FROM_PROVIDER_UNIVERSE")

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
            "response_identity": request["response_identity"],
        }
    st_source_row = None
    st_source_as_of_date = None
    st_source_known_at = None
    st_source_request_id = None
    if identity is not None and source_row_info is not None:
        st_source_row, st_source_request_id, st_source_as_of_date, st_source_known_at = source_row_info
    st, st_reason = _st_status(
        raw.get("st_status"),
        target_date=target_date,
        field_name="st_status",
        request_map=request_map,
        source_row=st_source_row,
        source_request_id_for_row=st_source_request_id,
        source_as_of_date=st_source_as_of_date,
        source_known_at=st_source_known_at,
        symbol=identity["symbol"] if identity is not None else None,
        runner_now=runner_now,
    )
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
            if request is None or identity is None:
                raise CaptureError("PROVIDER_HISTORY_REQUEST_MISSING", "security has no verified historical response")
            provider_bars = _provider_history_bars(request, symbol=identity["symbol"], target_date=target_date)
            submitted = [*prefix, t_ohlcv]
            parsed_submitted = validate_ohlcv_bars(submitted)
            parsed_provider = validate_ohlcv_bars(provider_bars)
            if parsed_submitted != parsed_provider:
                raise CaptureError("PROVIDER_HISTORY_CONTENT_MISMATCH", "normalized bars differ from the hashed provider response")
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
        except CaptureError as exc:
            reasons.append(exc.status)
            record["historical_prefix"] = prefix
            record["t_ohlcv"] = t_ohlcv
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


def _capture_index_path(root: Path, target_date: str) -> Path:
    return _safe_store_path(root, Path(C_CAPTURE_INDEX_DIR) / _date_dir(target_date) / "captured.json")


def _attempt_history(root: Path, target_date: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    finalized_index_exists = _capture_index_path(root, target_date).exists()
    for directory in (C_LOG_DIR, C_FAILURE_DIR):
        folder = _safe_store_path(root, Path(directory) / _date_dir(target_date))
        if not folder.exists():
            continue
        for path in sorted(folder.glob("*.json")):
            try:
                payload = _read_json(path)
            except CaptureError as exc:
                raise CaptureError("PERSISTED_STATE_CORRUPT", f"cannot read prior attempt record {path}: {exc}") from exc
            status = payload.get("status")
            reason = payload.get("reason")
            if status == C_CAPTURE_READY and not finalized_index_exists and not reason:
                reason = "FINAL_CAPTURE_INDEX_MISSING_OR_PROCESS_INTERRUPTED"
            result.append(
                {
                    "path": _relative(root, path),
                    "sha256": file_sha256(path),
                    "status": status,
                    "input_sha256": payload.get("input_sha256"),
                    "attempted_at": payload.get("attempted_at", payload.get("runner_observed_at")),
                    "reason": reason,
                    "failure_reasons": payload.get("failure_reasons", []),
                }
            )
    return result


def _attempt_log(
    root: Path,
    *,
    target_date: str,
    attempt_id: str,
    status: str,
    input_sha256: str | None,
    attempted_at: datetime,
    prior_attempts: Sequence[Mapping[str, Any]],
    manifest_sha256: str | None = None,
    observation_sha256: str | None = None,
    failure_reasons: Sequence[str] = (),
) -> dict[str, Any]:
    payload = {
        "schema_version": C_CAPTURE_LOG_SCHEMA,
        "namespace": C_CAPTURE_NAMESPACE,
        "target_date": target_date,
        "capture_mode": C_CAPTURE_MODE,
        "attempt_id": attempt_id,
        "status": status,
        "input_sha256": input_sha256,
        "manifest_sha256": manifest_sha256,
        "observation_sha256": observation_sha256,
        "attempted_at": _timestamp_text(attempted_at),
        "failure_reasons": list(failure_reasons),
        "prior_attempts": list(prior_attempts),
        "boundary": _capture_boundary(),
    }
    path = _safe_store_path(root, Path(C_LOG_DIR) / _date_dir(target_date) / f"attempt_{attempt_id}.json")
    digest = _write_immutable_json(path, payload)
    return {"path": _relative(root, path), "sha256": digest, "payload": payload}


def _failure_log(
    root: Path,
    *,
    target_date: str,
    status: str,
    reason: str,
    input_sha256: str | None,
    attempted_at: datetime,
    attempt_id: str,
    prior_attempts: Sequence[Mapping[str, Any]] = (),
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "schema_version": C_CAPTURE_LOG_SCHEMA,
        "namespace": C_CAPTURE_NAMESPACE,
        "target_date": target_date,
        "capture_mode": C_CAPTURE_MODE,
        "attempt_id": attempt_id,
        "status": status,
        "reason": reason,
        "input_sha256": input_sha256,
        "attempted_at": _timestamp_text(attempted_at),
        "details": dict(details or {}),
        "prior_attempts": list(prior_attempts),
        "boundary": _capture_boundary(),
    }
    path = _safe_store_path(root, Path(C_FAILURE_DIR) / _date_dir(target_date) / f"failure_{attempt_id}.json")
    digest = _write_immutable_json(path, payload)
    return {"path": _relative(root, path), "sha256": digest, "payload": payload}


def _capture_context(
    snapshot: Mapping[str, Any],
    *,
    target_date: str,
    now_bjt: datetime,
    calendar: TradingCalendar,
    root: Path,
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
    return (
        *_normalise_requests(
            snapshot,
            target_date=target_date,
            session_close=session_close,
            now_bjt=now_bjt,
            root=root,
        ),
        session_close,
    )


def _verified_universe(
    snapshot: Mapping[str, Any],
    *,
    request_map: Mapping[str, Mapping[str, Any]],
    target_date: str,
) -> tuple[dict[str, tuple[Mapping[str, Any], str, str | None, str | None]], list[str], list[dict[str, Any]]]:
    universe = snapshot.get("universe")
    if not isinstance(universe, Mapping):
        raise CaptureError(C_INPUT_SCHEMA_INVALID, "snapshot.universe source coverage is missing")
    request_ids = universe.get("request_ids")
    if not isinstance(request_ids, Sequence) or isinstance(request_ids, (str, bytes)) or not request_ids:
        raise CaptureError(C_INPUT_SCHEMA_INVALID, "snapshot.universe.request_ids must be a non-empty list")
    if len(request_ids) != len(set(request_ids)):
        raise CaptureError(C_INPUT_SCHEMA_INVALID, "snapshot.universe.request_ids contains duplicates")
    expected_rows: dict[str, tuple[Mapping[str, Any], str, str | None, str | None]] = {}
    coverage_failures: list[dict[str, Any]] = []
    page_offsets: list[int] = []
    page_lengths: list[int] = []
    page_limits: list[int] = []
    for request_id in request_ids:
        request = request_map.get(request_id) if isinstance(request_id, str) else None
        if request is None or request.get("endpoint") != "/api/meta/tickers/list":
            raise CaptureError("UNIVERSE_SOURCE_UNVERIFIED", "universe request must identify a verified ticker-list response")
        params = request.get("query_params")
        if not isinstance(params, Mapping) or params.get("asset_type") != "a-share":
            raise CaptureError("UNIVERSE_SOURCE_UNVERIFIED", "ticker-list request must explicitly select A-share stocks")
        try:
            page_limit = int(params["limit"])
            page_offset = int(params["offset"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CaptureError("UNIVERSE_SOURCE_UNVERIFIED", "ticker-list request lacks valid pagination identity") from exc
        if page_limit <= 0 or page_limit > 10000 or page_offset < 0:
            raise CaptureError("UNIVERSE_SOURCE_UNVERIFIED", "ticker-list pagination is outside provider bounds")
        page_offsets.append(page_offset)
        page_limits.append(page_limit)
        document = request.get("_response_document")
        data = document.get("data") if isinstance(document, Mapping) else None
        items = data.get("item") if isinstance(data, Mapping) else None
        if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
            raise CaptureError("UNIVERSE_SOURCE_UNVERIFIED", f"ticker-list response {request_id} lacks data.item")
        page_lengths.append(len(items))
        provider_timestamp = data.get("timestamp") if isinstance(data, Mapping) else None
        provider_as_of_date: str | None = None
        if isinstance(provider_timestamp, bool) or not isinstance(provider_timestamp, (int, float)):
            coverage_failures.append({"reason": "TICKER_SNAPSHOT_TIMESTAMP_MISSING", "source_request_id": request_id})
        else:
            try:
                provider_as_of_date = (
                    datetime.fromtimestamp(float(provider_timestamp) / 1000, timezone.utc)
                    .astimezone(_BJT)
                    .date()
                    .isoformat()
                )
            except (ValueError, OverflowError, OSError):
                coverage_failures.append({"reason": "TICKER_SNAPSHOT_TIMESTAMP_INVALID", "source_request_id": request_id})
            if provider_as_of_date != target_date:
                coverage_failures.append({"reason": "TICKER_SNAPSHOT_NOT_AS_OF_T", "source_request_id": request_id})
        known_at = str(request.get("received_at"))
        for item in items:
            if not isinstance(item, Mapping):
                coverage_failures.append({"reason": "TICKER_ROW_NOT_OBJECT", "source_request_id": request_id})
                continue
            raw_symbol = item.get("thscode")
            try:
                code = _normalise_code(raw_symbol, "ticker.thscode")
                symbol = _normalise_symbol(raw_symbol, code, "ticker.thscode")
            except CaptureError:
                coverage_failures.append({"reason": "TICKER_IDENTITY_INVALID", "source_request_id": request_id})
                continue
            if classify_board(symbol) != BOARD_MAIN:
                continue
            if item.get("asset_type") != "a-share":
                coverage_failures.append({"reason": "TICKER_ASSET_TYPE_UNVERIFIED", "symbol": symbol})
            expected_exchange = symbol.rsplit(".", 1)[1]
            if item.get("exchange") != expected_exchange:
                coverage_failures.append({"reason": "TICKER_EXCHANGE_IDENTITY_MISMATCH", "symbol": symbol})
            if not isinstance(item.get("name"), str) or not item.get("name", "").strip():
                coverage_failures.append({"reason": "TICKER_NAME_MISSING", "symbol": symbol})
            if symbol in expected_rows:
                coverage_failures.append({"reason": "DUPLICATE_UNIVERSE_SYMBOL", "symbol": symbol})
                continue
            expected_rows[symbol] = (item, request_id, provider_as_of_date, known_at)

    if len(set(page_limits)) != 1 or page_offsets != [index * page_limits[0] for index in range(len(page_offsets))]:
        coverage_failures.append({"reason": "UNIVERSE_PAGINATION_SEQUENCE_INVALID", "offsets": page_offsets})
    if page_lengths[-1] >= page_limits[-1] or any(length < page_limits[-1] for length in page_lengths[:-1]):
        coverage_failures.append({"reason": "UNIVERSE_PAGINATION_NOT_TERMINATED"})

    declared = universe.get("symbols")
    if not isinstance(declared, Sequence) or isinstance(declared, (str, bytes)):
        raise CaptureError(C_INPUT_SCHEMA_INVALID, "snapshot.universe.symbols must be a list")
    declared_symbols: list[str] = []
    for index, raw_symbol in enumerate(declared):
        code = _normalise_code(raw_symbol, f"snapshot.universe.symbols[{index}]")
        declared_symbols.append(_normalise_symbol(raw_symbol, code, f"snapshot.universe.symbols[{index}]"))
    if len(declared_symbols) != len(set(declared_symbols)) or sorted(declared_symbols) != sorted(expected_rows):
        coverage_failures.append({
            "reason": "DECLARED_UNIVERSE_DIFFERS_FROM_PROVIDER_RESPONSES",
            "provider_count": len(expected_rows),
            "declared_count": len(declared_symbols),
        })

    raw_securities = snapshot.get("securities")
    if not isinstance(raw_securities, Sequence) or isinstance(raw_securities, (str, bytes)):
        raise CaptureError(C_INPUT_SCHEMA_INVALID, "snapshot.securities must be a list")
    supplied: list[str] = []
    for raw in raw_securities:
        identity = raw.get("security_identity") if isinstance(raw, Mapping) else None
        if not isinstance(identity, Mapping):
            coverage_failures.append({"reason": "SECURITY_IDENTITY_MISSING"})
            continue
        try:
            code = _normalise_code(identity.get("code"), "security_identity.code")
            supplied.append(_normalise_symbol(identity.get("symbol"), code, "security_identity.symbol"))
        except CaptureError:
            coverage_failures.append({"reason": "SECURITY_IDENTITY_INVALID"})
    if len(supplied) != len(set(supplied)):
        coverage_failures.append({"reason": "DUPLICATE_SECURITY_RECORD"})
    supplied_set = set(supplied)
    expected_set = set(expected_rows)
    for symbol in sorted(expected_set - supplied_set):
        coverage_failures.append({"reason": "UNIVERSE_SECURITY_CAPTURE_MISSING", "symbol": symbol})
    for symbol in sorted(supplied_set - expected_set):
        coverage_failures.append({"reason": "SECURITY_NOT_IN_PROVIDER_UNIVERSE", "symbol": symbol})
    return expected_rows, sorted(expected_rows), coverage_failures


def capture_t_close_snapshot(
    snapshot: Mapping[str, Any],
    *,
    target_date: str,
    calendar: TradingCalendar | None = None,
    _provider_adapter_token: object | None = None,
) -> dict[str, Any]:
    if _provider_adapter_token is not _C_PROVIDER_ADAPTER_TOKEN:
        raise CaptureError("C_LIVE_ADAPTER_REQUIRED", "only the dedicated C provider adapter may start a live capture")
    return _capture_snapshot_at(
        snapshot,
        target_date=target_date,
        runner_now=datetime.now(_BJT),
        calendar=calendar,
    )


def _capture_snapshot_at(
    snapshot: Mapping[str, Any],
    *,
    target_date: str,
    runner_now: datetime,
    calendar: TradingCalendar | None = None,
) -> dict[str, Any]:
    """Private clock seam used by deterministic tests; the live API exposes no clock override."""

    target_date = _canonical_date(target_date, "target_date")
    if runner_now.tzinfo is None:
        raise CaptureError(C_INPUT_SCHEMA_INVALID, "test runner clock must be timezone aware")
    runner_now = runner_now.astimezone(_BJT)
    root = _safe_output_root()
    attempt_id = uuid.uuid4().hex
    try:
        input_bytes = _canonical_bytes(snapshot)
        input_sha256 = sha256_bytes(input_bytes)
    except CaptureError as exc:
        with _capture_lock(root, target_date):
            try:
                prior = _attempt_history(root, target_date)
            except CaptureError:
                prior = []
            failure = _failure_log(
                root,
                target_date=target_date,
                status=exc.status,
                reason=exc.reason,
                input_sha256=None,
                attempted_at=runner_now,
                attempt_id=attempt_id,
                prior_attempts=prior,
                details=exc.details,
            )
        return {"status": C_CAPTURE_FAILED, "failure_code": exc.status, "reason": exc.reason, "failure_log": failure["path"]}

    input_path = _safe_store_path(
        root,
        Path(C_INPUT_SNAPSHOT_DIR) / _date_dir(target_date) / f"input_{input_sha256}.json",
    )
    with _capture_lock(root, target_date):
        try:
            prior_attempts = _attempt_history(root, target_date)
        except CaptureError as exc:
            failure = _failure_log(
                root,
                target_date=target_date,
                status=exc.status,
                reason=exc.reason,
                input_sha256=input_sha256,
                attempted_at=runner_now,
                attempt_id=attempt_id,
            )
            return {"status": C_CAPTURE_FAILED, "failure_code": exc.status, "reason": exc.reason, "input_sha256": input_sha256, "failure_log": failure["path"]}

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
                attempt_id=attempt_id,
                prior_attempts=prior_attempts,
                details=exc.details,
            )
            return {"status": C_CAPTURE_FAILED, "failure_code": exc.status, "reason": exc.reason, "input_sha256": input_sha256, "failure_log": failure["path"]}

        index_path = _capture_index_path(root, target_date)
        if index_path.exists():
            try:
                existing = _verify_capture_index(root, index_path)
            except CaptureError as exc:
                failure = _failure_log(
                    root,
                    target_date=target_date,
                    status="PERSISTED_CAPTURE_CORRUPT",
                    reason=exc.reason,
                    input_sha256=input_sha256,
                    attempted_at=runner_now,
                    attempt_id=attempt_id,
                    prior_attempts=prior_attempts,
                    details={"cause": exc.status},
                )
                return {"status": C_CAPTURE_FAILED, "failure_code": exc.status, "reason": exc.reason, "input_sha256": input_sha256, "failure_log": failure["path"]}
            if existing["index"].get("input_snapshot", {}).get("sha256") == input_sha256:
                duplicate_log = _attempt_log(
                    root,
                    target_date=target_date,
                    attempt_id=attempt_id,
                    status=C_ALREADY_CAPTURED,
                    input_sha256=input_sha256,
                    attempted_at=runner_now,
                    prior_attempts=prior_attempts,
                    manifest_sha256=existing["manifest_sha256"],
                    observation_sha256=existing["observation_sha256"],
                )
                return {
                    "status": C_ALREADY_CAPTURED,
                    "capture_status": C_CAPTURED,
                    "target_date": target_date,
                    "input_sha256": input_sha256,
                    "manifest": existing["index"]["manifest"]["path"],
                    "observation": existing["index"]["observation"]["path"],
                    "captured_index": _relative(root, index_path),
                    "log": duplicate_log["path"],
                }
            failure = _failure_log(
                root,
                target_date=target_date,
                status=C_INPUT_CONFLICT,
                reason="a different verified immutable input already owns this T date",
                input_sha256=input_sha256,
                attempted_at=runner_now,
                attempt_id=attempt_id,
                prior_attempts=prior_attempts,
                details={"existing_input_sha256": existing["index"].get("input_snapshot", {}).get("sha256")},
            )
            return {"status": C_INPUT_CONFLICT, "reason": "a different verified immutable input already owns this T date", "input_sha256": input_sha256, "failure_log": failure["path"]}

        prepared: dict[str, Any] = {}
        try:
            cal = calendar or default_calendar()
            requests, request_map, session_close = _capture_context(
                snapshot,
                target_date=target_date,
                now_bjt=runner_now,
                calendar=cal,
                root=root,
            )
            universe_rows, expected_symbols, coverage_failures = _verified_universe(
                snapshot,
                request_map=request_map,
                target_date=target_date,
            )
            raw_securities = snapshot.get("securities")
            if not isinstance(raw_securities, Sequence) or isinstance(raw_securities, (str, bytes)):
                raise CaptureError(C_INPUT_SCHEMA_INVALID, "snapshot.securities must be a list")
            security_records = [
                _security_record(
                    raw,
                    target_date=target_date,
                    request_map=request_map,
                    universe_rows=universe_rows,
                    runner_now=runner_now,
                )
                for raw in raw_securities
            ]
            quality_failures = list(coverage_failures)
            capture_meta = snapshot.get("capture")
            if isinstance(capture_meta, Mapping):
                provider_failures = capture_meta.get("failures", [])
                if isinstance(provider_failures, Sequence) and not isinstance(provider_failures, (str, bytes)):
                    failure_fields = (
                        "endpoint",
                        "url",
                        "requested_at",
                        "failed_at",
                        "http_status",
                        "provider_request_id",
                        "response_bytes",
                        "response_sha256",
                        "reason",
                    )
                    quality_failures.extend(
                        {
                            "reason": "PROVIDER_REQUEST_FAILED",
                            "provider_failure": {
                                key: item[key] for key in failure_fields if key in item
                            } if isinstance(item, Mapping) else str(item),
                        }
                        for item in provider_failures
                    )
                plan = capture_meta.get("plan")
                if isinstance(plan, Mapping) and plan.get("history_requests_completed") != plan.get("history_requests_required"):
                    quality_failures.append({
                        "reason": "HISTORY_REQUEST_COVERAGE_INCOMPLETE",
                        "completed": plan.get("history_requests_completed"),
                        "required": plan.get("history_requests_required"),
                    })
            quality_failures.extend(
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
            )
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
                "expected_provider_symbols": expected_symbols,
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

            complete_inputs_verified = not quality_failures
            capture_status = C_PARTIAL_UNVERIFIED if not complete_inputs_verified else C_CAPTURE_READY
            public_requests = [
                {key: value for key, value in request.items() if key not in {"_response_document", "response_body_base64"}}
                for request in requests
            ]
            observation_payload = {
                "schema_version": C_OBSERVATION_SCHEMA,
                "namespace": C_CAPTURE_NAMESPACE,
                "strategy_namespace": C_RESEARCH_NAMESPACE,
                "strategy_version": C_STRATEGY_VERSION,
                "target_date": target_date,
                "capture_mode": C_CAPTURE_MODE,
                "capture_status": capture_status,
                "attempt_id": attempt_id,
                "source_requests": public_requests,
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
            observation_path = _safe_store_path(
                root,
                Path(C_OBSERVATION_DIR) / _date_dir(target_date) / f"observation_{attempt_id}.json",
            )
            observation_digest = _write_immutable_json(observation_path, observation_payload)
            prepared.update({"observation": _relative(root, observation_path), "observation_sha256": observation_digest})
            manifest_payload = {
                "schema_version": C_CAPTURE_MANIFEST_SCHEMA,
                "namespace": C_CAPTURE_NAMESPACE,
                "strategy_namespace": C_RESEARCH_NAMESPACE,
                "strategy_version": C_STRATEGY_VERSION,
                "target_date": target_date,
                "capture_mode": C_CAPTURE_MODE,
                "capture_status": capture_status,
                "attempt_id": attempt_id,
                "runner_observed_at": _timestamp_text(runner_now),
                "prior_attempts": prior_attempts,
                "source": {
                    "provider": snapshot["capture"]["provider"],
                    "provider_version": snapshot["capture"]["provider_version"],
                    "provider_quota": snapshot["capture"].get("provider_quota"),
                    "request_count": len(requests),
                    "request_ids": [request["request_id"] for request in requests],
                    "response_identities": [request["response_identity"] for request in requests],
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
            manifest_path = _safe_store_path(
                root,
                Path(C_MANIFEST_DIR) / _date_dir(target_date) / f"capture_{attempt_id}.json",
            )
            manifest_digest = _write_immutable_json(manifest_path, manifest_payload)
            prepared.update({"manifest": _relative(root, manifest_path), "manifest_sha256": manifest_digest})
            attempt_log = _attempt_log(
                root,
                target_date=target_date,
                attempt_id=attempt_id,
                status=capture_status,
                input_sha256=input_digest,
                attempted_at=runner_now,
                prior_attempts=prior_attempts,
                manifest_sha256=manifest_digest,
                observation_sha256=observation_digest,
                failure_reasons=[
                    str(item["reason"])
                    if item.get("reason")
                    else str(reason)
                    for item in quality_failures
                    for reason in (item.get("reasons") if isinstance(item.get("reasons"), list) and item.get("reasons") else [None])
                ],
            )
            prepared.update({"log": attempt_log["path"], "log_sha256": attempt_log["sha256"]})
            result = {
                "status": capture_status,
                "target_date": target_date,
                "attempt_id": attempt_id,
                "input_sha256": input_digest,
                "observation_sha256": observation_digest,
                "manifest_sha256": manifest_digest,
                "log_sha256": attempt_log["sha256"],
                "input_snapshot": _relative(root, input_path),
                "observation": _relative(root, observation_path),
                "manifest": _relative(root, manifest_path),
                "log": attempt_log["path"],
                "quality_failure_count": len(quality_failures),
                "quality_failures": quality_failures,
                "full_comparable_universe_count": full_universe["count"],
                "matched_event_sample_counts": {rule_id: value["count"] for rule_id, value in matched.items()},
            }
            if complete_inputs_verified:
                index_payload = {
                    "schema_version": C_CAPTURE_MANIFEST_SCHEMA,
                    "namespace": C_CAPTURE_NAMESPACE,
                    "target_date": target_date,
                    "status": C_CAPTURED,
                    "attempt_id": attempt_id,
                    "attempted_at": _timestamp_text(runner_now),
                    "input_snapshot": manifest_payload["input_snapshot"],
                    "manifest": {"path": _relative(root, manifest_path), "sha256": manifest_digest},
                    "observation": manifest_payload["research_observation"],
                    "log": {"path": attempt_log["path"], "sha256": attempt_log["sha256"]},
                    "prior_attempts": prior_attempts,
                    "boundary": _capture_boundary(),
                }
                index_digest = _write_immutable_json(index_path, index_payload)
                _verify_capture_index(root, index_path)
                result["status"] = C_CAPTURED
                result["captured_index"] = _relative(root, index_path)
                result["captured_index_sha256"] = index_digest
            return result
        except (CaptureError, CalendarUnavailable, OSError, TypeError, ValueError, KeyError) as exc:
            if isinstance(exc, CaptureError):
                status, reason, details = exc.status, exc.reason, exc.details
            else:
                status, reason, details = C_CAPTURE_FAILED, f"{type(exc).__name__}: {exc}", {}
            details = {**dict(details), "prepared_artifacts": prepared}
            failure = _failure_log(
                root,
                target_date=target_date,
                status=status,
                reason=reason,
                input_sha256=input_sha256,
                attempted_at=runner_now,
                attempt_id=attempt_id,
                prior_attempts=prior_attempts,
                details=details,
            )
            public_status = status if status in {C_INPUT_CONFLICT, C_NOT_PROSPECTIVE_BACKFILL, C_NOT_AFTER_CLOSE} else C_CAPTURE_FAILED
            return {
                "status": public_status,
                "failure_code": status,
                "reason": reason,
                "target_date": target_date,
                "input_sha256": input_sha256,
                "input_snapshot": _relative(root, input_path),
                "failure_log": failure["path"],
                **prepared,
            }


def _verify_capture_index(root: Path, index_path: Path) -> dict[str, Any]:
    index_path = _safe_store_path(root, index_path.resolve().relative_to(root.resolve()))
    index = _read_json(index_path)
    if index.get("namespace") != C_CAPTURE_NAMESPACE or index.get("status") != C_CAPTURED:
        raise CaptureError("CAPTURE_IDENTITY_MISMATCH", "captured index is not a finalized C prospective capture")
    if index.get("boundary") != _capture_boundary():
        raise CaptureError("CAPTURE_BOUNDARY_MISMATCH", "captured index is not C-only")
    for key, label in (("input_snapshot", "input"), ("manifest", "manifest"), ("observation", "observation"), ("log", "attempt log")):
        info = index.get(key)
        if not isinstance(info, Mapping) or not isinstance(info.get("path"), str) or not isinstance(info.get("sha256"), str):
            raise CaptureError("CAPTURE_IDENTITY_MISMATCH", f"captured index lacks {label} identity")
        path = _safe_store_path(root, str(info["path"]))
        try:
            actual = file_sha256(path)
        except CaptureError as exc:
            raise CaptureError("CAPTURE_ARTIFACT_MISSING", f"{label} artifact is missing: {path}") from exc
        if actual != info["sha256"]:
            raise CaptureError("CAPTURE_HASH_MISMATCH", f"{label} artifact SHA-256 mismatch")
    manifest = _read_json(_safe_store_path(root, index["manifest"]["path"]))
    observation = _read_json(_safe_store_path(root, index["observation"]["path"]))
    log = _read_json(_safe_store_path(root, index["log"]["path"]))
    if manifest.get("namespace") != C_CAPTURE_NAMESPACE or manifest.get("capture_status") != C_CAPTURE_READY:
        raise CaptureError("CAPTURE_IDENTITY_MISMATCH", "manifest is not a complete pre-finalization capture")
    if manifest.get("target_date") != index.get("target_date") or manifest.get("attempt_id") != index.get("attempt_id"):
        raise CaptureError("CAPTURE_IDENTITY_MISMATCH", "manifest and captured index identities differ")
    if manifest.get("input_snapshot") != index.get("input_snapshot") or manifest.get("research_observation") != index.get("observation"):
        raise CaptureError("CAPTURE_IDENTITY_MISMATCH", "manifest and captured index artifact identities differ")
    if manifest.get("quality_failures") or observation.get("capture_status") != C_CAPTURE_READY:
        raise CaptureError("CAPTURE_INPUT_INCOMPLETE", "capture has unresolved quality or universe failures")
    if log.get("input_sha256") != index["input_snapshot"]["sha256"] or log.get("manifest_sha256") != index["manifest"]["sha256"]:
        raise CaptureError("CAPTURE_IDENTITY_MISMATCH", "attempt log does not identify this capture chain")
    if log.get("status") != C_CAPTURE_READY or log.get("attempt_id") != index.get("attempt_id"):
        raise CaptureError("CAPTURE_IDENTITY_MISMATCH", "attempt log is not the verified pre-finalization attempt")
    snapshot = _read_json(_safe_store_path(root, index["input_snapshot"]["path"]))
    source = manifest.get("source")
    if not isinstance(source, Mapping):
        raise CaptureError("CAPTURE_IDENTITY_MISMATCH", "manifest lacks verified provider source metadata")
    runner_time = _timestamp(index.get("attempted_at"), "captured_index.attempted_at")
    close_time = _timestamp(source.get("session_close_bjt"), "manifest.source.session_close_bjt")
    requests, request_map = _normalise_requests(
        snapshot,
        target_date=str(index.get("target_date")),
        session_close=close_time,
        now_bjt=runner_time,
        root=root,
    )
    _universe_rows, _symbols, coverage_failures = _verified_universe(
        snapshot,
        request_map=request_map,
        target_date=str(index.get("target_date")),
    )
    capture_meta = snapshot.get("capture")
    if not isinstance(capture_meta, Mapping) or capture_meta.get("failures"):
        raise CaptureError("CAPTURE_INPUT_INCOMPLETE", "provider acquisition contains failure records")
    if coverage_failures:
        raise CaptureError("CAPTURE_INPUT_INCOMPLETE", "provider universe coverage no longer verifies")
    if source.get("request_ids") != [request["request_id"] for request in requests]:
        raise CaptureError("CAPTURE_IDENTITY_MISMATCH", "manifest request ids differ from immutable provider input")
    if source.get("response_identities") != [request["response_identity"] for request in requests]:
        raise CaptureError("CAPTURE_IDENTITY_MISMATCH", "manifest provider response identities differ from exact raw responses")
    return {
        "index": index,
        "manifest": manifest,
        "manifest_sha256": index["manifest"]["sha256"],
        "observation": observation,
        "observation_sha256": index["observation"]["sha256"],
        "log": log,
        "input_sha256": index["input_snapshot"]["sha256"],
    }


def verify_persisted_capture(manifest_path: str | Path) -> dict[str, Any]:
    """Verify a finalized capture's complete immutable input/observation/log chain."""

    root = _safe_output_root()
    supplied = Path(manifest_path)
    manifest_file = supplied.resolve() if supplied.is_absolute() else _safe_store_path(root, supplied)
    if root != manifest_file and root not in manifest_file.parents:
        raise CaptureError("FORBIDDEN_DIRECTORY_REFUSED", "manifest path must remain inside the independent C research root")
    manifest = _read_json(manifest_file)
    target_date = _canonical_date(manifest.get("target_date"), "manifest.target_date")
    index_path = _capture_index_path(root, target_date)
    if not index_path.is_file():
        raise CaptureError("CAPTURE_NOT_FINALIZED", "no immutable PROSPECTIVE_CAPTURED index exists for this date")
    verified = _verify_capture_index(root, index_path)
    if _safe_store_path(root, verified["index"]["manifest"]["path"]) != manifest_file:
        raise CaptureError("CAPTURE_IDENTITY_MISMATCH", "manifest is not the one referenced by the finalized capture")
    return {
        "status": "PASS",
        "captured_index_sha256": file_sha256(index_path),
        "manifest_sha256": verified["manifest_sha256"],
        "input_sha256": verified["input_sha256"],
        "observation_sha256": verified["observation_sha256"],
        "boundary": verified["index"]["boundary"],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    verify = parser.add_subparsers(dest="command", required=True).add_parser("verify", help="verify one finalized C capture")
    verify.add_argument("--manifest", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = verify_persisted_capture(args.manifest)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


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
