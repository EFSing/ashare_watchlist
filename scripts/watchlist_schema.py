"""Strict canonical schema and integrity checks for daily watchlists."""

from __future__ import annotations

import copy
import json
import math
import re
from collections.abc import Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any


class WatchlistSchemaError(ValueError):
    """The payload does not match the canonical watchlist schema."""


class WatchlistIntegrityError(WatchlistSchemaError):
    """The payload is valid JSON but violates a cross-file invariant."""


WATCHLIST_FILENAME = re.compile(r"^watchlist_(\d{8})\.json$")
DEFAULT_STRATEGY_VERSION = "watchlist-v1"

INPUT_COVERAGE_SCHEMA = "INPUT_COVERAGE_V1"
INPUT_COVERAGE_COMPLETE = "COMPLETE"
INPUT_COVERAGE_DEGRADED = "DEGRADED"
INPUT_COVERAGE_NO_VALID_INPUT = "NO_VALID_INPUT"
PER_SYMBOL_PROVIDER_FAILURE_ISOLATION_V1 = "PER_SYMBOL_PROVIDER_FAILURE_ISOLATION_V1"
PER_SYMBOL_FAIL_SOFT_PRODUCTION_V1 = "PER_SYMBOL_FAIL_SOFT_PRODUCTION_V1"
_SUPPORTED_INPUT_COVERAGE_POLICIES = {
    PER_SYMBOL_PROVIDER_FAILURE_ISOLATION_V1,
    PER_SYMBOL_FAIL_SOFT_PRODUCTION_V1,
}
EXCLUDED_PROVIDER_STALE = "EXCLUDED_PROVIDER_STALE"
EXCLUDED_INPUT_ANOMALY = "EXCLUDED_INPUT_ANOMALY"
TARGET_DAY_HISTORICAL_STALE = "TARGET_DAY_HISTORICAL_STALE"

_INPUT_COVERAGE_REQUIRED_KEYS = {
    "schema_version",
    "coverage_status",
    "evaluated_symbol_count",
    "excluded_symbol_count",
    "excluded_symbols",
    "policy_version",
}
_INPUT_COVERAGE_OPTIONAL_KEYS = {
    "raw_symbol_count",
    "qualified_symbol_count",
    "excluded_reason_counts",
    "formal_result_valid",
}
_INPUT_COVERAGE_KEYS = _INPUT_COVERAGE_REQUIRED_KEYS | _INPUT_COVERAGE_OPTIONAL_KEYS
_EXCLUDED_SYMBOL_REQUIRED_KEYS = {
    "symbol",
    "provider_symbol",
    "target_date",
    "provider",
    "status",
    "reason",
    "latest_historical_date",
    "quote_trade_state",
    "evidence",
    "policy_version",
}
_EXCLUDED_SYMBOL_OPTIONAL_KEYS = {
    "failure_status",
    "failure_stage",
    "detail",
    "display_name",
}
_EXCLUDED_SYMBOL_KEYS = _EXCLUDED_SYMBOL_REQUIRED_KEYS | _EXCLUDED_SYMBOL_OPTIONAL_KEYS

TOP_LEVEL_ALLOWED = {
    "date",
    "mode",
    "market_env",
    "sectors",
    "candidates",
    "strategy_version",
    "universe_policy",
    "input_coverage",
}
CANDIDATE_REQUIRED = {
    "code",
    "name",
    "buy_type",
    "score",
    "price",
    "trigger",
    "stop",
    "target",
    "rr",
}
CANDIDATE_ALLOWED = CANDIDATE_REQUIRED | {
    "sector",
    "chg",
    "support",
    "stop_dist",
    "vol_ratio",
    "turnover",
    "float_mv",
    "target_type",
    "risk",
    "setup",
    "strategy_version",
    "signal_id",
}
NUMERIC_CANDIDATE_FIELDS = {
    "score",
    "price",
    "chg",
    "trigger",
    "support",
    "stop",
    "target",
    "rr",
    "stop_dist",
    "vol_ratio",
    "turnover",
    "float_mv",
}


def _coverage_date(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise WatchlistSchemaError(f"input coverage {field_name} must be YYYY-MM-DD")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise WatchlistSchemaError(f"input coverage {field_name} must be YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise WatchlistSchemaError(f"input coverage {field_name} must be canonical YYYY-MM-DD")
    return value


def validate_input_coverage(
    value: Any,
    *,
    expected_evaluated_symbol_count: int | None = None,
    expected_target_date: str | None = None,
    allow_no_valid: bool = False,
) -> dict[str, Any]:
    """Validate the production input-coverage contract.

    The field is optional on legacy watchlists.  A formal watchlist may be
    complete or degraded with any finite number of explicitly classified
    per-symbol exclusions.  ``NO_VALID_INPUT`` is accepted only by diagnostic
    callers; it is never a valid formal watchlist coverage value.
    """

    if not isinstance(value, Mapping):
        raise WatchlistSchemaError("input_coverage must be an object")
    unknown = set(value) - _INPUT_COVERAGE_KEYS
    if unknown:
        raise WatchlistSchemaError(f"input_coverage has unknown keys: {sorted(unknown)}")
    if not _INPUT_COVERAGE_REQUIRED_KEYS.issubset(value):
        raise WatchlistSchemaError("input_coverage is missing required keys")
    if value.get("schema_version") != INPUT_COVERAGE_SCHEMA:
        raise WatchlistSchemaError("input_coverage schema_version is unsupported")
    status = value.get("coverage_status")
    supported_statuses = {INPUT_COVERAGE_COMPLETE, INPUT_COVERAGE_DEGRADED}
    if allow_no_valid:
        supported_statuses.add(INPUT_COVERAGE_NO_VALID_INPUT)
    if status not in supported_statuses:
        raise WatchlistSchemaError("input_coverage coverage_status is unsupported")
    evaluated = value.get("evaluated_symbol_count")
    if isinstance(evaluated, bool) or not isinstance(evaluated, int):
        raise WatchlistSchemaError("input_coverage evaluated_symbol_count must be an integer")
    if status == INPUT_COVERAGE_NO_VALID_INPUT:
        if not allow_no_valid:
            raise WatchlistSchemaError("NO_VALID_INPUT coverage is diagnostic-only")
        if evaluated != 0:
            raise WatchlistSchemaError("NO_VALID_INPUT evaluated_symbol_count must be zero")
    elif evaluated <= 0:
        raise WatchlistSchemaError("input_coverage evaluated_symbol_count must be a positive integer")
    if expected_evaluated_symbol_count is not None and evaluated != expected_evaluated_symbol_count:
        raise WatchlistSchemaError(
            "input_coverage evaluated_symbol_count does not match the evaluated universe"
        )
    excluded_count = value.get("excluded_symbol_count")
    excluded = value.get("excluded_symbols")
    if isinstance(excluded_count, bool) or not isinstance(excluded_count, int) or excluded_count < 0:
        raise WatchlistSchemaError("input_coverage excluded_symbol_count must be a non-negative integer")
    if not isinstance(excluded, list) or excluded_count != len(excluded):
        raise WatchlistSchemaError("input_coverage excluded symbol count does not match records")
    if value.get("policy_version") not in _SUPPORTED_INPUT_COVERAGE_POLICIES:
        raise WatchlistSchemaError("input_coverage policy_version is unsupported")
    for field_name in ("raw_symbol_count", "qualified_symbol_count"):
        if field_name in value:
            field_value = value[field_name]
            if isinstance(field_value, bool) or not isinstance(field_value, int) or field_value < 0:
                raise WatchlistSchemaError(f"input_coverage {field_name} must be a non-negative integer")
    if "raw_symbol_count" in value and "qualified_symbol_count" in value:
        if value["qualified_symbol_count"] > value["raw_symbol_count"]:
            raise WatchlistSchemaError("input coverage qualified count cannot exceed raw count")
    if "qualified_symbol_count" in value and value["evaluated_symbol_count"] > value["qualified_symbol_count"]:
        raise WatchlistSchemaError("input coverage evaluated count cannot exceed qualified count")
    if "formal_result_valid" in value and not isinstance(value["formal_result_valid"], bool):
        raise WatchlistSchemaError("input coverage formal_result_valid must be boolean")
    if status in {INPUT_COVERAGE_COMPLETE, INPUT_COVERAGE_DEGRADED}:
        if "formal_result_valid" in value and value["formal_result_valid"] is not True:
            raise WatchlistSchemaError("formal input coverage must mark formal_result_valid=true")
    elif value.get("formal_result_valid") is not False:
        raise WatchlistSchemaError("NO_VALID_INPUT coverage must mark formal_result_valid=false")
    if status == INPUT_COVERAGE_COMPLETE and (excluded_count != 0 or excluded):
        raise WatchlistSchemaError("complete input coverage cannot contain exclusions")
    if status == INPUT_COVERAGE_DEGRADED and excluded_count <= 0:
        raise WatchlistSchemaError("degraded input coverage must contain at least one exclusion")

    normalized_records: list[dict[str, Any]] = []
    seen_symbols: set[str] = set()
    for index, raw_record in enumerate(excluded):
        if not isinstance(raw_record, Mapping):
            raise WatchlistSchemaError(f"input_coverage excluded_symbols[{index}] must be an object")
        unknown_record = set(raw_record) - _EXCLUDED_SYMBOL_KEYS
        if unknown_record:
            raise WatchlistSchemaError(
                f"input_coverage excluded_symbols[{index}] has unknown keys: {sorted(unknown_record)}"
            )
        if not _EXCLUDED_SYMBOL_REQUIRED_KEYS.issubset(raw_record):
            raise WatchlistSchemaError(
                f"input_coverage excluded_symbols[{index}] is missing required keys"
            )
        symbol = raw_record.get("symbol")
        if not isinstance(symbol, str) or not re.fullmatch(r"\d{6}", symbol):
            raise WatchlistSchemaError("input coverage excluded symbol must be six digits")
        if symbol in seen_symbols:
            raise WatchlistSchemaError("input coverage excluded symbols must be unique")
        seen_symbols.add(symbol)
        provider_symbol = raw_record.get("provider_symbol")
        if not isinstance(provider_symbol, str) or not provider_symbol.strip():
            raise WatchlistSchemaError("input coverage provider_symbol must be non-empty")
        target_date = _coverage_date(raw_record.get("target_date"), "target_date")
        if expected_target_date is not None and target_date != expected_target_date:
            raise WatchlistSchemaError("input coverage target date does not match the watchlist date")
        latest_raw = raw_record.get("latest_historical_date")
        latest_date = None if latest_raw is None else _coverage_date(latest_raw, "latest_historical_date")
        if (
            raw_record.get("status") == EXCLUDED_PROVIDER_STALE
            and latest_date is not None
            and latest_date >= target_date
        ):
            raise WatchlistSchemaError("input coverage latest historical date must precede target date")
        for field_name in ("provider", "status", "reason", "quote_trade_state", "policy_version"):
            field_value = raw_record.get(field_name)
            if not isinstance(field_value, str) or not field_value.strip():
                raise WatchlistSchemaError(
                    f"input coverage excluded record {field_name} must be non-empty"
                )
        if raw_record.get("status") not in {EXCLUDED_PROVIDER_STALE, EXCLUDED_INPUT_ANOMALY}:
            raise WatchlistSchemaError("input coverage excluded record status is unsupported")
        if not re.fullmatch(r"[A-Z0-9_]+", raw_record.get("reason", "")):
            raise WatchlistSchemaError("input coverage excluded record reason is unsupported")
        if raw_record.get("quote_trade_state") not in {
            "TRADED",
            "NO_TRADE",
            "UNKNOWN",
            "UNAVAILABLE",
        }:
            raise WatchlistSchemaError("input coverage excluded record quote_trade_state is unsupported")
        if raw_record.get("policy_version") not in _SUPPORTED_INPUT_COVERAGE_POLICIES:
            raise WatchlistSchemaError("input coverage excluded record policy_version is unsupported")
        evidence = raw_record.get("evidence")
        if not isinstance(evidence, Mapping):
            raise WatchlistSchemaError("input coverage excluded record evidence must be an object")
        if not isinstance(evidence.get("quote"), Mapping) or not isinstance(evidence.get("historical"), Mapping):
            raise WatchlistSchemaError("input coverage evidence must include quote and historical objects")
        normalized_records.append(copy.deepcopy(dict(raw_record)))

    if [record.get("symbol") for record in normalized_records] != sorted(
        record.get("symbol") for record in normalized_records
    ):
        raise WatchlistSchemaError("input coverage excluded symbols must be sorted")
    normalized = copy.deepcopy(dict(value))
    normalized["excluded_symbols"] = normalized_records
    if "excluded_reason_counts" in normalized:
        reason_counts = normalized["excluded_reason_counts"]
        if not isinstance(reason_counts, Mapping):
            raise WatchlistSchemaError("input coverage excluded_reason_counts must be an object")
        normalized_counts: dict[str, int] = {}
        for reason, count in reason_counts.items():
            if not isinstance(reason, str) or not re.fullmatch(r"[A-Z0-9_]+", reason):
                raise WatchlistSchemaError("input coverage reason count key is unsupported")
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise WatchlistSchemaError("input coverage reason count must be non-negative integer")
            normalized_counts[reason] = count
        calculated: dict[str, int] = {}
        for record in normalized_records:
            reason = str(record["reason"])
            calculated[reason] = calculated.get(reason, 0) + 1
        if normalized_counts != calculated:
            raise WatchlistSchemaError("input coverage reason counts do not match exclusions")
        normalized["excluded_reason_counts"] = dict(sorted(normalized_counts.items()))
    return normalized


def _date(value: Any) -> date:
    if not isinstance(value, str):
        raise WatchlistSchemaError("date must be an ISO string YYYY-MM-DD")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise WatchlistSchemaError(f"date must be YYYY-MM-DD: {value!r}") from exc
    if parsed.strftime("%Y-%m-%d") != value:
        raise WatchlistSchemaError(f"date must be canonical YYYY-MM-DD: {value!r}")
    return parsed


def _finite_number(value: Any, field: str, code: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise WatchlistSchemaError(f"candidate {code} field {field} must be a finite number")


def stable_signal_id(strategy_version: str, date_value: str, code: str, setup: str) -> str:
    """Build a readable, deterministic identity for one candidate event."""

    return f"{strategy_version}:{date_value}:{code}:{setup}"


def validate_watchlist(payload: Any) -> dict[str, Any]:
    """Validate and normalize a canonical payload without mutating the input."""

    if not isinstance(payload, dict):
        raise WatchlistSchemaError("watchlist payload must be an object")
    if "items" in payload:
        raise WatchlistSchemaError("legacy key 'items' is unsupported; use 'candidates'")
    unknown = set(payload) - TOP_LEVEL_ALLOWED
    if unknown:
        raise WatchlistSchemaError(f"unknown top-level keys: {sorted(unknown)}")
    for key in ("date", "mode", "market_env", "sectors", "candidates"):
        if key not in payload:
            raise WatchlistSchemaError(f"missing required top-level key: {key}")

    parsed_date = _date(payload["date"])
    if not isinstance(payload["mode"], str) or not payload["mode"].strip():
        raise WatchlistSchemaError("mode must be a non-empty string")
    if not isinstance(payload["market_env"], dict):
        raise WatchlistSchemaError("market_env must be an object")
    if not isinstance(payload["sectors"], list):
        raise WatchlistSchemaError("sectors must be an array")
    if not isinstance(payload["candidates"], list):
        raise WatchlistSchemaError("candidates must be an array")

    strategy_version = payload.get("strategy_version", DEFAULT_STRATEGY_VERSION)
    if not isinstance(strategy_version, str) or not strategy_version.strip():
        raise WatchlistSchemaError("strategy_version must be a non-empty string")
    if "universe_policy" in payload and (
        not isinstance(payload["universe_policy"], str) or not payload["universe_policy"].strip()
    ):
        raise WatchlistSchemaError("universe_policy must be a non-empty string")
    if "input_coverage" in payload:
        input_coverage = validate_input_coverage(
            payload["input_coverage"],
            expected_target_date=parsed_date.isoformat(),
        )
    else:
        input_coverage = None

    normalized = copy.deepcopy(payload)
    normalized["strategy_version"] = strategy_version
    if input_coverage is not None:
        normalized["input_coverage"] = input_coverage
    normalized_candidates: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw in payload["candidates"]:
        if not isinstance(raw, dict):
            raise WatchlistSchemaError("each candidate must be an object")
        if "trig" in raw:
            raise WatchlistSchemaError("legacy key 'trig' is unsupported; use 'trigger'")
        missing = CANDIDATE_REQUIRED - set(raw)
        if missing:
            raise WatchlistSchemaError(f"candidate missing required keys: {sorted(missing)}")
        unknown_candidate = set(raw) - CANDIDATE_ALLOWED
        if unknown_candidate:
            raise WatchlistSchemaError(f"unknown candidate keys: {sorted(unknown_candidate)}")

        code = raw["code"]
        if not isinstance(code, str) or not re.fullmatch(r"\d{6}", code):
            raise WatchlistSchemaError(f"candidate code must be six digits: {code!r}")
        if not isinstance(raw["name"], str) or not raw["name"].strip():
            raise WatchlistSchemaError(f"candidate {code} name must be non-empty")
        if not isinstance(raw["buy_type"], str) or not raw["buy_type"].strip():
            raise WatchlistSchemaError(f"candidate {code} buy_type must be non-empty")
        for field in NUMERIC_CANDIDATE_FIELDS & set(raw):
            # Current production does not require turnover-rate semantics.
            # Preserve an explicit missing diagnostic as null; every formal
            # numeric selection field remains strictly finite.
            if field == "turnover" and raw[field] is None:
                continue
            _finite_number(raw[field], field, code)
        for field in ("price", "trigger", "stop", "target", "rr"):
            if float(raw[field]) <= 0:
                raise WatchlistSchemaError(f"candidate {code} field {field} must be positive")

        item = copy.deepcopy(raw)
        setup = item.get("setup", item["buy_type"])
        item_version = item.get("strategy_version", strategy_version)
        if not isinstance(setup, str) or not setup.strip():
            raise WatchlistSchemaError(f"candidate {code} setup must be non-empty")
        if not isinstance(item_version, str) or not item_version.strip():
            raise WatchlistSchemaError(f"candidate {code} strategy_version must be non-empty")
        expected_id = stable_signal_id(item_version, parsed_date.isoformat(), code, setup)
        if "signal_id" in item and item["signal_id"] != expected_id:
            raise WatchlistIntegrityError(
                f"candidate {code} signal_id does not match strategy_version/date/code/setup"
            )
        item["setup"] = setup
        item["strategy_version"] = item_version
        item["signal_id"] = expected_id
        if expected_id in seen_ids:
            raise WatchlistIntegrityError(f"duplicate candidate signal_id: {expected_id}")
        seen_ids.add(expected_id)
        normalized_candidates.append(item)

    normalized["candidates"] = normalized_candidates
    return normalized


def _filename_date(path: Path) -> date:
    match = WATCHLIST_FILENAME.fullmatch(path.name)
    if not match:
        raise WatchlistIntegrityError(
            f"watchlist filename must be watchlist_YYYYMMDD.json: {path.name}"
        )
    try:
        return datetime.strptime(match.group(1), "%Y%m%d").date()
    except ValueError as exc:
        raise WatchlistIntegrityError(f"watchlist filename contains invalid date: {path.name}") from exc


def load_watchlist(path: str | Path) -> dict[str, Any]:
    """Load a watchlist and enforce filename/payload date consistency."""

    watchlist_path = Path(path)
    try:
        payload = json.loads(watchlist_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise WatchlistSchemaError(f"cannot load watchlist {watchlist_path}: {exc}") from exc

    normalized = validate_watchlist(payload)
    filename_date = _filename_date(watchlist_path)
    payload_date = _date(normalized["date"])
    if filename_date != payload_date:
        raise WatchlistIntegrityError(
            f"watchlist filename date {filename_date.isoformat()} != payload date {payload_date.isoformat()}"
        )
    return normalized
