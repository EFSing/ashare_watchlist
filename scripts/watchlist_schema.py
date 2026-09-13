"""Strict canonical schema and integrity checks for daily watchlists."""

from __future__ import annotations

import copy
import json
import math
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any


class WatchlistSchemaError(ValueError):
    """The payload does not match the canonical watchlist schema."""


class WatchlistIntegrityError(WatchlistSchemaError):
    """The payload is valid JSON but violates a cross-file invariant."""


WATCHLIST_FILENAME = re.compile(r"^watchlist_(\d{8})\.json$")
DEFAULT_STRATEGY_VERSION = "watchlist-v1"

TOP_LEVEL_ALLOWED = {
    "date",
    "mode",
    "market_env",
    "sectors",
    "candidates",
    "strategy_version",
    "universe_policy",
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

    normalized = copy.deepcopy(payload)
    normalized["strategy_version"] = strategy_version
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
