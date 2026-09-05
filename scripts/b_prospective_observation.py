"""Append-only prospective observation for the unchanged B V1_1 candidate.

This module is deliberately downstream of the existing T-close generation path.
It consumes a successful canonical watchlist and its immutable development run
manifest, records every published B signal, and appends future outcome states
without rewriting signal-time bytes.  It never evaluates a new strategy and
never uses an outcome while ingesting a signal.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping

from b_breakout_retest_v1_1 import STRATEGY_SPEC_SHA256, STRATEGY_VERSION
from data_paths import DataPaths
from generation_contract import READY_FOR_STRATEGY_EVALUATION, next_execution_date
from trading_calendar import TradingCalendar, default_calendar
from watchlist_schema import WatchlistSchemaError, load_watchlist


PROTOCOL_VERSION = "B_V1_1_PROSPECTIVE_OBSERVATION_PROTOCOL_V1"
OBSERVATION_SCHEMA = "B_PROSPECTIVE_OBSERVATION_EVENT_V1"
PROTOCOL_MANIFEST_SCHEMA = "B_PROSPECTIVE_OBSERVATION_MANIFEST_V1"
EPISODE_IDENTITY_VERSION = "B_V1_1_BREAKOUT_EPISODE_ID_V1"

# Filled in by the post-protocol bookkeeping commit.  Keeping a hard value in
# the module prevents a future operator from accidentally starting a stream
# before the semantics have been committed.
PROTOCOL_COMMIT_SHA = "3dd7d51a6341a60540c26db2aa4f18367520d95b"

LABELS = (
    "DEVELOPMENT",
    "PROSPECTIVE_OBSERVATION",
    "DATE_ANCHORED",
    "APPEND_ONLY",
    "NO_RULE_CHANGE",
    "NOT_FROZEN",
    "NOT_PRODUCTION",
    "FINAL_OOS_UNREAD",
)
HORIZONS = (1, 3, 5, 10)
PRIMARY_HORIZON = 10
MINIMUM_SIGNAL_SESSIONS = 60
MINIMUM_MATURE_INDEPENDENT_EPISODES = 200
MAXIMUM_SIGNAL_SESSIONS = 120
REFERENCE_EXECUTION_NOT_ACTUAL_FILL = "REFERENCE_EXECUTION_NOT_ACTUAL_FILL"

EXECUTABLE_REFERENCE_OPEN = "EXECUTABLE_REFERENCE_OPEN"
SUSPENDED = "SUSPENDED"
LIMIT_STATE_EXECUTION_UNCERTAIN = "LIMIT_STATE_EXECUTION_UNCERTAIN"
MISSING_OPEN = "MISSING_OPEN"
DATA_FAILURE = "DATA_FAILURE"
OTHER_EXPLICIT_NON_EXECUTABLE = "OTHER_EXPLICIT_NON_EXECUTABLE"
PENDING_REFERENCE_OPEN = "PENDING_REFERENCE_OPEN"
EXECUTION_CLASSIFICATIONS = {
    EXECUTABLE_REFERENCE_OPEN,
    SUSPENDED,
    LIMIT_STATE_EXECUTION_UNCERTAIN,
    MISSING_OPEN,
    DATA_FAILURE,
    OTHER_EXPLICIT_NON_EXECUTABLE,
    PENDING_REFERENCE_OPEN,
}
NON_EXECUTABLE_CLASSIFICATIONS = {
    SUSPENDED,
    MISSING_OPEN,
    DATA_FAILURE,
    OTHER_EXPLICIT_NON_EXECUTABLE,
}
UNCERTAIN_CLASSIFICATIONS = {LIMIT_STATE_EXECUTION_UNCERTAIN}
OUTCOME_UNAVAILABLE_STATUSES = {
    "NOT_MATURED",
    "NO_T_PLUS_1_OPEN",
    "SYMBOL_NOT_IN_RAW_STORE",
    "INCOMPLETE_STOCK_WINDOW",
    "INSUFFICIENT_FORWARD_COVERAGE",
    "DATA_FAILURE",
}

_BJT = timezone(timedelta(hours=8))
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class ObservationError(ValueError):
    """Fail-closed observation protocol or append-only store error."""

    def __init__(self, status: str, message: str) -> None:
        self.status = status
        super().__init__(f"{status}: {message}")


def _canonical_bytes(value: Any) -> bytes:
    try:
        text = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ObservationError("OBSERVATION_NON_CANONICAL_VALUE", str(exc)) from exc
    return (text + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256_bytes(_canonical_bytes(value))


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ObservationError("OBSERVATION_SOURCE_READ_FAILURE", f"{path}: {exc}") from exc
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ObservationError("OBSERVATION_SOURCE_READ_FAILURE", f"{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ObservationError("OBSERVATION_SOURCE_INVALID", f"expected object: {path}")
    return value


def _canonical_date(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ObservationError("OBSERVATION_DATE_INVALID", f"{field_name} must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ObservationError("OBSERVATION_DATE_INVALID", f"{field_name}={value!r}") from exc
    if parsed.isoformat() != value:
        raise ObservationError("OBSERVATION_DATE_INVALID", f"{field_name}={value!r}")
    return value


def _require_sha(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ObservationError("OBSERVATION_IDENTITY_INVALID", f"{field_name} is not a SHA-256")
    return value


def _require_git_sha(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not _GIT_SHA_RE.fullmatch(value):
        raise ObservationError("OBSERVATION_PROTOCOL_NOT_COMMITTED", f"{field_name} is not a full Git SHA")
    return value


def _code(value: Any) -> str:
    text = str(value).strip().lower()
    if text[:2] in {"sh", "sz", "bj"}:
        text = text[2:]
    if not re.fullmatch(r"\d{6}", text):
        raise ObservationError("OBSERVATION_SOURCE_INVALID", f"invalid six-digit symbol: {value!r}")
    return text


def _finite(value: Any, field_name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ObservationError("OBSERVATION_OUTCOME_INVALID", f"{field_name} must be finite")
    result = float(value)
    if positive and result <= 0:
        raise ObservationError("OBSERVATION_OUTCOME_INVALID", f"{field_name} must be positive")
    return result


def _safe_path(path: Path) -> None:
    normalized = str(path).replace("\\", "/").lower()
    if "/data/validation/continuous_speed_probe/" in f"{normalized}/":
        raise ObservationError("FORBIDDEN_DIRECTORY_REFUSED", "continuous speed probe directory is out of scope")


def _git_is_ancestor(ancestor_sha: str, descendant_sha: str) -> bool:
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor_sha, descendant_sha],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode == 0


def _protocol_manifest(protocol_commit_sha: str) -> dict[str, Any]:
    _require_git_sha(protocol_commit_sha, "protocol_commit_sha")
    return {
        "schema_version": PROTOCOL_MANIFEST_SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "protocol_commit_sha": protocol_commit_sha,
        "strategy": {
            "version": STRATEGY_VERSION,
            "spec_sha256": STRATEGY_SPEC_SHA256,
            "rules_unchanged": True,
            "score_cutoff": None,
            "top_n": None,
        },
        "labels": list(LABELS),
        "signal_semantics": {
            "generation": "existing canonical B V1_1 T-close path; all published qualified candidates",
            "primary_cohort": "first real XSHG T-close signal date generated after protocol commit; no backfill",
            "reference_entry": "T+1 XSHG open",
            "horizons": [f"{horizon}D" for horizon in HORIZONS],
            "primary_horizon": "10D",
            "future_outcomes_do_not_affect_generation": True,
        },
        "episode_identity": {
            "version": EPISODE_IDENTITY_VERSION,
            "components": ["symbol", "breakout_date", "breakout_index", "base_hi", "strategy_spec_sha256"],
            "deduplication": "same symbol and same breakout episode: first qualified signal is independent; repeats retained",
        },
        "execution": {
            "classifications": sorted(EXECUTION_CLASSIFICATIONS),
            "reference_semantics": REFERENCE_EXECUTION_NOT_ACTUAL_FILL,
            "next_available_price_substitution": False,
            "suspension_forward_fill": False,
            "limit_up_fill_assumption": False,
        },
        "outcomes": {
            "entry": "T+1 XSHG open",
            "target": "corresponding future XSHG close",
            "corporate_actions": "outcome measurement only; never signal input",
            "mfe_mae": "future adjusted high/low path relative to adjusted reference open",
        },
        "checkpoint": {
            "minimum_completed_xshg_signal_sessions": MINIMUM_SIGNAL_SESSIONS,
            "minimum_mature_independent_breakout_episodes": MINIMUM_MATURE_INDEPENDENT_EPISODES,
            "maximum_xshg_signal_sessions": MAXIMUM_SIGNAL_SESSIONS,
            "early_stop_for_good_performance": False,
            "allowed_conclusions": [
                "B_PROSPECTIVE_OBSERVATION_SUPPORTIVE",
                "B_PROSPECTIVE_OBSERVATION_NEEDS_MORE_EVIDENCE",
                "B_PROSPECTIVE_OBSERVATION_CONTRADICTORY",
            ],
            "automatic_promotion": False,
        },
    }


def _record_with_hash(payload: Mapping[str, Any]) -> dict[str, Any]:
    record = dict(payload)
    record["record_sha256"] = _sha256_json(record)
    return record


def _validate_record(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ObservationError("OBSERVATION_STORE_CORRUPT", "event is not an object")
    claimed = record.get("record_sha256")
    if not isinstance(claimed, str):
        raise ObservationError("OBSERVATION_STORE_CORRUPT", "event hash is missing")
    payload = dict(record)
    payload.pop("record_sha256", None)
    if _sha256_json(payload) != claimed:
        raise ObservationError("OBSERVATION_STORE_CORRUPT", "event hash mismatch")
    if record.get("schema_version") != OBSERVATION_SCHEMA:
        raise ObservationError("OBSERVATION_STORE_CORRUPT", "unsupported event schema")
    return record


def _bar_values(bars: list[Mapping[str, Any]]) -> tuple[list[float], list[float], list[str]]:
    closes: list[float] = []
    volumes: list[float] = []
    dates: list[str] = []
    for index, bar in enumerate(bars):
        if not isinstance(bar, Mapping):
            raise ObservationError("OBSERVATION_EPISODE_ID_UNAVAILABLE", f"bar {index} is not an object")
        dates.append(_canonical_date(bar.get("date"), f"bar[{index}].date"))
        closes.append(_finite(bar.get("close"), f"bar[{index}].close", positive=True))
        volumes.append(_finite(bar.get("volume"), f"bar[{index}].volume"))
    return closes, volumes, dates


def _first_qualifying_breakout(bars: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Derive identity only; this does not qualify or reject a signal.

    The expression mirrors the already-frozen B match semantics solely to
    recover the event provenance that the canonical candidate schema omits.
    """

    if len(bars) < 120:
        raise ObservationError("OBSERVATION_EPISODE_ID_UNAVAILABLE", "B input has fewer than 120 bars")
    closes, volumes, bar_dates = _bar_values(bars)
    n = len(closes)
    ma5 = sum(closes[-5:]) / 5.0
    final_close = closes[-1]
    for index in range(max(61, n - 15), n - 1):
        base_hi = max(closes[index - 60:index])
        breakout_ok = (
            closes[index] > base_hi
            and volumes[index] >= 1.8 * (sum(volumes[index - 20:index]) / 20.0)
            and (closes[index] / closes[index - 1] - 1.0) >= 0.03
        )
        if not breakout_ok:
            continue
        pull_volume_values = volumes[index + 1:] if n - 1 > index + 1 else [volumes[-1]]
        pull_volume = sum(pull_volume_values) / len(pull_volume_values)
        pullback_ok = (
            final_close >= base_hi * 0.97
            and (abs(final_close / base_hi - 1.0) <= 0.04 or base_hi * 0.97 <= final_close <= base_hi * 1.04)
            and pull_volume < volumes[index] * 0.7
            and (final_close >= closes[-2] or final_close >= ma5)
        )
        if not pullback_ok:
            raise ObservationError(
                "OBSERVATION_EPISODE_ID_UNAVAILABLE",
                "first qualifying breakout failed its pullback; refusing an inferred later episode",
            )
        return {"breakout_index": index, "breakout_date": bar_dates[index], "base_hi": base_hi}
    raise ObservationError("OBSERVATION_EPISODE_ID_UNAVAILABLE", "qualified B candidate has no recoverable breakout")


def breakout_episode_id(symbol: str, breakout: Mapping[str, Any]) -> str:
    payload = {
        "identity_version": EPISODE_IDENTITY_VERSION,
        "symbol": _code(symbol),
        "breakout_date": _canonical_date(breakout.get("breakout_date"), "breakout_date"),
        "breakout_index": breakout.get("breakout_index"),
        "base_hi": _finite(breakout.get("base_hi"), "base_hi", positive=True),
        "strategy_spec_sha256": STRATEGY_SPEC_SHA256,
    }
    if isinstance(payload["breakout_index"], bool) or not isinstance(payload["breakout_index"], int) or payload["breakout_index"] < 0:
        raise ObservationError("OBSERVATION_EPISODE_ID_UNAVAILABLE", "breakout_index is invalid")
    return f"{EPISODE_IDENTITY_VERSION}:{_sha256_json(payload)}"


def _next_horizon_date(signal_date: str, horizon: int, calendar: TradingCalendar) -> str:
    current = signal_date
    for _ in range(horizon):
        current = next_execution_date(current, calendar)
    return current


def _source_identity(watchlist_path: Path, run_manifest_path: Path, watchlist: Mapping[str, Any], run: Mapping[str, Any]) -> dict[str, Any]:
    output = run.get("output")
    if not isinstance(output, Mapping):
        raise ObservationError("OBSERVATION_SOURCE_INVALID", "successful run manifest has no output identity")
    watchlist_sha = _file_sha256(watchlist_path)
    if output.get("file_sha256") != watchlist_sha:
        raise ObservationError("OBSERVATION_SOURCE_IDENTITY_MISMATCH", "watchlist bytes differ from run manifest output SHA")
    generation = _require_sha(run.get("generation_fingerprint"), "generation_fingerprint")
    input_fingerprint = _require_sha(run.get("input_fingerprint"), "input_fingerprint")
    run_sha = _file_sha256(run_manifest_path)
    return {
        "watchlist_path": watchlist_path.as_posix(),
        "watchlist_sha256": watchlist_sha,
        "run_manifest_path": run_manifest_path.as_posix(),
        "run_manifest_sha256": run_sha,
        "generation_fingerprint": generation,
        "input_fingerprint": input_fingerprint,
        "output_logical_identity": output.get("logical_identity"),
    }


def _source_validation(
    watchlist: Mapping[str, Any],
    run: Mapping[str, Any],
    *,
    calendar: TradingCalendar,
) -> tuple[str, str, dict[str, Any], dict[str, Mapping[str, Any]]]:
    if watchlist.get("strategy_version") != STRATEGY_VERSION:
        raise ObservationError("OBSERVATION_SOURCE_INVALID", "watchlist strategy is not corrected B V1_1")
    if run.get("status") != "SUCCESS":
        raise ObservationError("OBSERVATION_SOURCE_INVALID", "run manifest is not a successful generation")
    if run.get("strategy_version") != STRATEGY_VERSION or run.get("strategy_spec_sha256") != STRATEGY_SPEC_SHA256:
        raise ObservationError("OBSERVATION_SOURCE_IDENTITY_MISMATCH", "run manifest strategy identity is not B V1_1")
    signal_date = _canonical_date(watchlist.get("date"), "watchlist.date")
    if run.get("signal_date") != signal_date or run.get("as_of_date") != signal_date:
        raise ObservationError("OBSERVATION_SOURCE_IDENTITY_MISMATCH", "run manifest date differs from watchlist date")
    input_manifest = run.get("input_manifest")
    if not isinstance(input_manifest, Mapping) or input_manifest.get("status") != READY_FOR_STRATEGY_EVALUATION:
        raise ObservationError("OBSERVATION_SOURCE_INVALID", "complete generation input manifest is missing")
    if input_manifest.get("signal_date") != signal_date or input_manifest.get("earliest_execution_date") != run.get("earliest_execution_date"):
        raise ObservationError("OBSERVATION_T_PLUS_ONE_MISMATCH", "input manifest T/T+1 identity is inconsistent")
    context = input_manifest.get("run_context")
    if not isinstance(context, Mapping) or context.get("mode") != "close" or context.get("historical") is True:
        raise ObservationError("OBSERVATION_SOURCE_INVALID", "observation requires non-historical close generation")
    try:
        if not calendar.is_trading_day(signal_date):
            raise ObservationError("OBSERVATION_T_PLUS_ONE_MISMATCH", "signal date is not an XSHG session")
        expected_entry = next_execution_date(signal_date, calendar)
    except ObservationError:
        raise
    except Exception as exc:
        raise ObservationError("OBSERVATION_T_PLUS_ONE_MISMATCH", str(exc)) from exc
    if input_manifest.get("earliest_execution_date") != expected_entry:
        raise ObservationError("OBSERVATION_T_PLUS_ONE_MISMATCH", "earliest execution date is not the next XSHG session")
    stock_klines = input_manifest.get("stock_klines")
    if not isinstance(stock_klines, list):
        raise ObservationError("OBSERVATION_SOURCE_INVALID", "input manifest stock_klines are missing")
    bars_by_code: dict[str, Mapping[str, Any]] = {}
    for item in stock_klines:
        if isinstance(item, Mapping):
            try:
                bars_by_code[_code(item.get("symbol"))] = item
            except ObservationError:
                continue
    return signal_date, expected_entry, dict(input_manifest), bars_by_code


def _market_regime(market_env: Mapping[str, Any]) -> str:
    for key in ("regime", "level", "market_regime"):
        value = market_env.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "UNKNOWN"


class AppendOnlyObservationStore:
    """One immutable protocol manifest and one append-only event stream."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        _safe_path(self.root)
        self.protocol_path = self.root / "protocol_manifest.json"
        self.events_path = self.root / "events.jsonl"

    def ensure_protocol(self, protocol_commit_sha: str = PROTOCOL_COMMIT_SHA) -> dict[str, Any]:
        if protocol_commit_sha == "PENDING_PRE_OUTCOME_PROTOCOL_COMMIT":
            raise ObservationError("OBSERVATION_PROTOCOL_NOT_COMMITTED", "protocol commit SHA is not recorded")
        payload = _protocol_manifest(protocol_commit_sha)
        content = _canonical_bytes(payload)
        if self.protocol_path.exists():
            try:
                existing = self.protocol_path.read_bytes()
            except OSError as exc:
                raise ObservationError("OBSERVATION_STORE_READ_FAILURE", str(exc)) from exc
            if existing != content:
                raise ObservationError("OBSERVATION_PROTOCOL_CONFLICT", "protocol manifest is immutable")
            return payload
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            with self.protocol_path.open("xb") as handle:
                handle.write(content)
                handle.flush()
        except FileExistsError:
            if self.protocol_path.read_bytes() != content:
                raise ObservationError("OBSERVATION_PROTOCOL_CONFLICT", "protocol manifest was concurrently changed")
        except OSError as exc:
            raise ObservationError("OBSERVATION_STORE_WRITE_FAILURE", str(exc)) from exc
        return payload

    def _events(self) -> list[dict[str, Any]]:
        if not self.events_path.exists():
            return []
        try:
            lines = self.events_path.read_bytes().splitlines()
        except OSError as exc:
            raise ObservationError("OBSERVATION_STORE_READ_FAILURE", str(exc)) from exc
        events: list[dict[str, Any]] = []
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                raise ObservationError("OBSERVATION_STORE_CORRUPT", f"blank event line {line_number}")
            try:
                record = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ObservationError("OBSERVATION_STORE_CORRUPT", f"event line {line_number}: {exc}") from exc
            events.append(_validate_record(record))
        return events

    def _append(self, records: list[Mapping[str, Any]]) -> None:
        if not records:
            return
        self.root.mkdir(parents=True, exist_ok=True)
        content = b"".join(_canonical_bytes(record) for record in records)
        try:
            with self.events_path.open("ab") as handle:
                handle.write(content)
                handle.flush()
        except OSError as exc:
            raise ObservationError("OBSERVATION_STORE_WRITE_FAILURE", str(exc)) from exc

    def record_watchlist(
        self,
        watchlist_path: str | Path,
        run_manifest_path: str | Path,
        *,
        generation_commit_sha: str,
        recorded_at_bjt: str | None = None,
        protocol_commit_sha: str = PROTOCOL_COMMIT_SHA,
        calendar: TradingCalendar | None = None,
    ) -> dict[str, Any]:
        """Append one completed T-close session and all its B signals.

        ``generation_commit_sha`` is supplied by the existing T-close runner's
        result.  The ancestry check is the no-backfill proof that this source
        was generated by code at or after the committed protocol.
        """

        self.ensure_protocol(protocol_commit_sha)
        generation_commit_sha = _require_git_sha(generation_commit_sha, "generation_commit_sha")
        if not _git_is_ancestor(protocol_commit_sha, generation_commit_sha):
            raise ObservationError(
                "OBSERVATION_BACKFILL_FORBIDDEN",
                "source generation commit is not a descendant of the pre-outcome protocol commit",
            )
        watch_path, run_path = Path(watchlist_path).expanduser().resolve(), Path(run_manifest_path).expanduser().resolve()
        _safe_path(watch_path)
        _safe_path(run_path)
        try:
            watchlist = load_watchlist(watch_path)
        except (FileNotFoundError, WatchlistSchemaError) as exc:
            raise ObservationError("OBSERVATION_SOURCE_INVALID", str(exc)) from exc
        run = _read_json(run_path)
        cal = calendar or default_calendar()
        signal_date, entry_date, input_manifest, bars_by_code = _source_validation(watchlist, run, calendar=cal)
        source = _source_identity(watch_path, run_path, watchlist, run)
        run_manifest_sha = source["run_manifest_sha256"]
        recorded = recorded_at_bjt or datetime.now(_BJT).isoformat()
        market_env = watchlist.get("market_env")
        if not isinstance(market_env, Mapping):
            raise ObservationError("OBSERVATION_SOURCE_INVALID", "watchlist market_env is missing")
        events = self._events()
        session_events = [item for item in events if item.get("record_type") == "SESSION_OBSERVED"]
        signal_events = [item for item in events if item.get("record_type") == "SIGNAL"]
        existing_session = next((item for item in session_events if item.get("signal_date") == signal_date), None)
        if existing_session is not None:
            if existing_session.get("source") != source or existing_session.get("generation_commit_sha") != generation_commit_sha:
                raise ObservationError("OBSERVATION_SESSION_CONFLICT", f"session already has another source: {signal_date}")
            return {"status": "ALREADY_RECORDED", "signal_date": signal_date, "signal_count": existing_session.get("signal_count", 0)}
        prior_dates = sorted({item["signal_date"] for item in session_events if isinstance(item.get("signal_date"), str)})
        if prior_dates and signal_date < prior_dates[-1]:
            raise ObservationError("OBSERVATION_BACKFILL_FORBIDDEN", f"{signal_date} precedes last observed session {prior_dates[-1]}")

        candidates = watchlist.get("candidates")
        if not isinstance(candidates, list):
            raise ObservationError("OBSERVATION_SOURCE_INVALID", "watchlist candidates are missing")
        candidates = sorted(candidates, key=lambda item: str(item.get("code", "")))
        existing_signal_ids = {item.get("signal_id") for item in signal_events}
        existing_episode_ids = {item.get("breakout_episode_id") for item in signal_events if item.get("first_signal_in_episode")}
        new_records: list[dict[str, Any]] = []
        session = _record_with_hash({
            "schema_version": OBSERVATION_SCHEMA,
            "record_type": "SESSION_OBSERVED",
            "protocol_version": PROTOCOL_VERSION,
            "protocol_commit_sha": protocol_commit_sha,
            "labels": list(LABELS),
            "signal_date": signal_date,
            "reference_entry_date": entry_date,
            "generation_commit_sha": generation_commit_sha,
            "source": source,
            "signal_count": len(candidates),
            "market_regime": _market_regime(market_env),
            "recorded_at_bjt": recorded,
        })
        new_records.append(session)

        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                raise ObservationError("OBSERVATION_SOURCE_INVALID", "candidate is not an object")
            signal_id = candidate.get("signal_id")
            code = _code(candidate.get("code"))
            if not isinstance(signal_id, str) or not signal_id:
                raise ObservationError("OBSERVATION_SOURCE_INVALID", f"{code} signal_id is missing")
            if signal_id in existing_signal_ids:
                raise ObservationError("OBSERVATION_SESSION_CONFLICT", f"signal already exists in another session: {signal_id}")
            item = bars_by_code.get(code)
            if not isinstance(item, Mapping) or not isinstance(item.get("bars"), list):
                raise ObservationError("OBSERVATION_EPISODE_ID_UNAVAILABLE", f"bars unavailable for {code}")
            breakout = _first_qualifying_breakout(item["bars"])
            episode_id = breakout_episode_id(code, breakout)
            first_signal = episode_id not in existing_episode_ids
            if first_signal:
                existing_episode_ids.add(episode_id)
            signal_payload = {
                "schema_version": OBSERVATION_SCHEMA,
                "record_type": "SIGNAL",
                "protocol_version": PROTOCOL_VERSION,
                "protocol_commit_sha": protocol_commit_sha,
                "labels": list(LABELS),
                "signal_id": signal_id,
                "strategy_version": STRATEGY_VERSION,
                "spec_sha256": STRATEGY_SPEC_SHA256,
                "signal_date": signal_date,
                "breakout_episode_id": episode_id,
                "breakout_date": breakout["breakout_date"],
                "breakout_index": breakout["breakout_index"],
                "base_hi": breakout["base_hi"],
                "first_signal_in_episode": first_signal,
                "episode_repeat": not first_signal,
                "reference_entry_date": entry_date,
                "reference_entry_open": None,
                "execution_classification": PENDING_REFERENCE_OPEN,
                "reference_execution_semantics": REFERENCE_EXECUTION_NOT_ACTUAL_FILL,
                "outcome_maturity_status": "NOT_MATURED",
                "candidate": json.loads(json.dumps(candidate, ensure_ascii=False, allow_nan=False)),
                "sector": candidate.get("sector"),
                "market_regime": _market_regime(market_env),
                "market_env": json.loads(json.dumps(market_env, ensure_ascii=False, allow_nan=False)),
                "input_output_identity": {
                    "strategy_version": STRATEGY_VERSION,
                    "spec_sha256": STRATEGY_SPEC_SHA256,
                    "input_fingerprint": source["input_fingerprint"],
                    "generation_fingerprint": source["generation_fingerprint"],
                    "watchlist_sha256": source["watchlist_sha256"],
                    "run_manifest_sha256": run_manifest_sha,
                },
                "source": source,
                "generation_commit_sha": generation_commit_sha,
                "recorded_at_bjt": recorded,
            }
            new_records.append(_record_with_hash(signal_payload))
        self._append(new_records)
        return {
            "status": "RECORDED",
            "signal_date": signal_date,
            "signal_count": len(candidates),
            "episode_independent_count": sum(1 for item in new_records if item.get("record_type") == "SIGNAL" and item.get("first_signal_in_episode")),
            "events_appended": len(new_records),
        }

    def append_outcome(
        self,
        signal_id: str,
        *,
        observed_date: str,
        reference_open: float | None,
        execution_classification: str,
        outcomes: Mapping[str, Mapping[str, Any]],
        corporate_action_treatment: Mapping[str, Any],
        outcome_source_identity: Mapping[str, Any],
        protocol_commit_sha: str = PROTOCOL_COMMIT_SHA,
        calendar: TradingCalendar | None = None,
    ) -> dict[str, Any]:
        """Append a future outcome state; never mutate the matching signal."""

        self.ensure_protocol(protocol_commit_sha)
        observed_date = _canonical_date(observed_date, "observed_date")
        if execution_classification not in EXECUTION_CLASSIFICATIONS - {PENDING_REFERENCE_OPEN}:
            raise ObservationError("OBSERVATION_EXECUTION_CLASSIFICATION_INVALID", execution_classification)
        events = self._events()
        signals = [item for item in events if item.get("record_type") == "SIGNAL" and item.get("signal_id") == signal_id]
        if len(signals) != 1:
            raise ObservationError("OBSERVATION_SIGNAL_NOT_FOUND", signal_id)
        signal = signals[0]
        if signal.get("protocol_commit_sha") != protocol_commit_sha:
            raise ObservationError("OBSERVATION_PROTOCOL_CONFLICT", "signal belongs to another protocol")
        signal_date = signal["signal_date"]
        if observed_date < signal_date:
            raise ObservationError("OBSERVATION_OUTCOME_INVALID", "outcome observed date precedes signal date")
        if execution_classification == EXECUTABLE_REFERENCE_OPEN:
            reference_open = _finite(reference_open, "reference_open", positive=True)
        elif execution_classification == LIMIT_STATE_EXECUTION_UNCERTAIN:
            if reference_open is not None:
                reference_open = _finite(reference_open, "reference_open", positive=True)
        elif reference_open is not None:
            raise ObservationError("OBSERVATION_OUTCOME_INVALID", "non-executable classification cannot have a reference open")
        expected_entry = signal.get("reference_entry_date")
        cal = calendar or default_calendar()
        if expected_entry != _next_horizon_date(signal_date, 1, cal):
            raise ObservationError("OBSERVATION_T_PLUS_ONE_MISMATCH", "signal reference entry is not T+1")
        if not isinstance(outcomes, Mapping):
            raise ObservationError("OBSERVATION_OUTCOME_INVALID", "outcomes must be a mapping")
        normalized_outcomes: dict[str, dict[str, Any]] = {}
        for horizon in HORIZONS:
            key = f"{horizon}D"
            raw = outcomes.get(key)
            if not isinstance(raw, Mapping):
                raise ObservationError("OBSERVATION_OUTCOME_INVALID", f"missing {key} outcome")
            status = raw.get("status")
            if not isinstance(status, str) or not status:
                raise ObservationError("OBSERVATION_OUTCOME_INVALID", f"{key}.status is missing")
            target_date = raw.get("target_date")
            if target_date is not None:
                target_date = _canonical_date(target_date, f"{key}.target_date")
                if target_date != _next_horizon_date(signal_date, horizon, cal):
                    raise ObservationError("OBSERVATION_T_PLUS_ONE_MISMATCH", f"{key}.target_date is not the XSHG target")
                if target_date > observed_date:
                    raise ObservationError("OBSERVATION_OUTCOME_NOT_MATURE", f"{key} target is not mature")
            values: dict[str, Any] = {"status": status, "target_date": target_date}
            for field_name in ("target_close", "return_pct", "mfe_pct", "mae_pct"):
                value = raw.get(field_name)
                if status == "AVAILABLE":
                    values[field_name] = _finite(value, f"{key}.{field_name}")
                else:
                    if value is not None:
                        raise ObservationError("OBSERVATION_OUTCOME_INVALID", f"{key}.{field_name} must be null for {status}")
                    values[field_name] = None
            values["corporate_actions"] = json.loads(json.dumps(raw.get("corporate_actions", []), ensure_ascii=False, allow_nan=False))
            normalized_outcomes[key] = values
        maturity = "MATURED_10D" if normalized_outcomes["10D"]["status"] != "NOT_MATURED" else "PARTIAL_NOT_MATURED"
        if maturity == "MATURED_10D" and normalized_outcomes["10D"]["target_date"] is None:
            raise ObservationError("OBSERVATION_OUTCOME_INVALID", "mature 10D outcome needs a target date")
        if not isinstance(corporate_action_treatment, Mapping) or corporate_action_treatment.get("mode") != "ADJUSTED_OUTCOME_ONLY_EX_POST":
            raise ObservationError("OBSERVATION_OUTCOME_INVALID", "corporate-action treatment must be outcome-only ex-post")
        if not isinstance(outcome_source_identity, Mapping):
            raise ObservationError("OBSERVATION_OUTCOME_INVALID", "outcome source identity is missing")
        payload = {
            "schema_version": OBSERVATION_SCHEMA,
            "record_type": "OUTCOME_UPDATE",
            "protocol_version": PROTOCOL_VERSION,
            "protocol_commit_sha": protocol_commit_sha,
            "labels": list(LABELS),
            "signal_id": signal_id,
            "strategy_version": STRATEGY_VERSION,
            "spec_sha256": STRATEGY_SPEC_SHA256,
            "signal_date": signal_date,
            "breakout_episode_id": signal["breakout_episode_id"],
            "reference_entry_date": expected_entry,
            "reference_entry_open": reference_open,
            "execution_classification": execution_classification,
            "reference_execution_semantics": REFERENCE_EXECUTION_NOT_ACTUAL_FILL,
            "outcome_maturity_status": maturity,
            "observed_date": observed_date,
            "outcomes": normalized_outcomes,
            "corporate_action_treatment": json.loads(json.dumps(corporate_action_treatment, ensure_ascii=False, allow_nan=False)),
            "outcome_source_identity": json.loads(json.dumps(outcome_source_identity, ensure_ascii=False, allow_nan=False)),
        }
        record = _record_with_hash(payload)
        if any(item == record for item in events if item.get("record_type") == "OUTCOME_UPDATE"):
            return {"status": "ALREADY_RECORDED", "signal_id": signal_id, "outcome_maturity_status": maturity}
        self._append([record])
        return {"status": "OUTCOME_APPENDED", "signal_id": signal_id, "outcome_maturity_status": maturity}

    def summary(self) -> dict[str, Any]:
        events = self._events()
        sessions = [item for item in events if item.get("record_type") == "SESSION_OBSERVED"]
        signals = [item for item in events if item.get("record_type") == "SIGNAL"]
        outcomes: dict[str, dict[str, Any]] = {}
        for item in events:
            if item.get("record_type") == "OUTCOME_UPDATE":
                outcomes[item["signal_id"]] = item
        signal_dates = sorted({item["signal_date"] for item in sessions})
        first_signal_date = min((item["signal_date"] for item in signals), default=None)
        cohort_sessions = [value for value in signal_dates if first_signal_date is not None and value >= first_signal_date]
        independent = [item for item in signals if item.get("first_signal_in_episode") is True]
        mature_independent = [item for item in independent if outcomes.get(item["signal_id"], {}).get("outcome_maturity_status") == "MATURED_10D"]
        primary_rows = []
        for item in mature_independent:
            outcome = outcomes.get(item["signal_id"], {}).get("outcomes", {}).get("10D", {})
            if outcome.get("status") == "AVAILABLE":
                primary_rows.append({
                    "signal_id": item["signal_id"],
                    "symbol": item["candidate"]["code"],
                    "signal_date": item["signal_date"],
                    "sector": item.get("sector"),
                    "market_regime": item.get("market_regime", "UNKNOWN"),
                    "return_pct": float(outcome["return_pct"]),
                    "mfe_pct": float(outcome["mfe_pct"]),
                    "mae_pct": float(outcome["mae_pct"]),
                })
        execution_counts = Counter(
            outcomes[item["signal_id"]]["execution_classification"]
            for item in signals
            if item["signal_id"] in outcomes
        )
        total_signals = len(signals)
        executable = execution_counts[EXECUTABLE_REFERENCE_OPEN]
        uncertain = execution_counts["LIMIT_STATE_EXECUTION_UNCERTAIN"]
        non_executable = sum(execution_counts[value] for value in NON_EXECUTABLE_CLASSIFICATIONS)
        metrics = _metric_summary(primary_rows)
        checkpoint = {
            "status": "CHECKPOINT_NOT_REACHED",
            "minimum_completed_xshg_signal_sessions": MINIMUM_SIGNAL_SESSIONS,
            "completed_xshg_signal_sessions": len(cohort_sessions),
            "minimum_mature_independent_breakout_episodes": MINIMUM_MATURE_INDEPENDENT_EPISODES,
            "mature_independent_breakout_episodes": len(mature_independent),
            "maximum_xshg_signal_sessions": MAXIMUM_SIGNAL_SESSIONS,
            "maximum_window_reached": len(cohort_sessions) >= MAXIMUM_SIGNAL_SESSIONS,
            "no_early_stop_for_good_performance": True,
        }
        if len(cohort_sessions) >= MINIMUM_SIGNAL_SESSIONS and len(mature_independent) >= MINIMUM_MATURE_INDEPENDENT_EPISODES:
            checkpoint["status"] = "CHECKPOINT_READY_FOR_USER_REVIEW"
        elif len(cohort_sessions) >= MAXIMUM_SIGNAL_SESSIONS:
            checkpoint["status"] = "MAXIMUM_WINDOW_REACHED_NEEDS_USER_REVIEW"
        return {
            "schema_version": PROTOCOL_MANIFEST_SCHEMA,
            "protocol_version": PROTOCOL_VERSION,
            "protocol_commit_sha": self._protocol_commit_sha(),
            "labels": list(LABELS),
            "primary_cohort_start_signal_date": first_signal_date,
            "raw_signal_level_count": total_signals,
            "episode_deduplicated_count": len({item["breakout_episode_id"] for item in signals}),
            "independent_episode_count": len(independent),
            "mature_independent_episode_count": len(mature_independent),
            "execution": {
                "total_signals": total_signals,
                "executable_reference_count": executable,
                "execution_uncertain_count": uncertain,
                "non_executable_count": non_executable,
                "pending_reference_count": total_signals - executable - uncertain - non_executable,
                "execution_coverage_rate": executable / total_signals if total_signals else None,
                "classification_counts": dict(sorted(execution_counts.items())),
                "reference_execution_semantics": REFERENCE_EXECUTION_NOT_ACTUAL_FILL,
            },
            "primary_10d_episode_metrics": metrics,
            "diagnostics": _diagnostics(primary_rows, signals, mature_independent),
            "checkpoint": checkpoint,
            "allowed_conclusions": [
                "B_PROSPECTIVE_OBSERVATION_SUPPORTIVE",
                "B_PROSPECTIVE_OBSERVATION_NEEDS_MORE_EVIDENCE",
                "B_PROSPECTIVE_OBSERVATION_CONTRADICTORY",
            ],
            "automatic_promotion": False,
        }

    def _protocol_commit_sha(self) -> str:
        if not self.protocol_path.exists():
            return PROTOCOL_COMMIT_SHA
        return _read_json(self.protocol_path).get("protocol_commit_sha", PROTOCOL_COMMIT_SHA)


def _metric_summary(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    returns = [float(row["return_pct"]) for row in rows]
    mfes = [float(row["mfe_pct"]) for row in rows]
    maes = [float(row["mae_pct"]) for row in rows]
    if not returns:
        return {"N": 0, "mean": None, "median": None, "positive_rate": None, "mean_ci_95": None, "positive_rate_wilson_ci_95": None, "mean_mfe": None, "mean_mae": None}
    ordered = sorted(returns)
    median = ordered[len(ordered) // 2] if len(ordered) % 2 else (ordered[len(ordered) // 2 - 1] + ordered[len(ordered) // 2]) / 2.0
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1) if len(returns) > 1 else 0.0
    standard_error = math.sqrt(variance / len(returns))
    positive = sum(value > 0 for value in returns)
    p = positive / len(returns)
    z = 1.96
    denominator = 1 + z * z / len(returns)
    centre = (p + z * z / (2 * len(returns))) / denominator
    radius = z * math.sqrt((p * (1 - p) + z * z / (4 * len(returns))) / len(returns)) / denominator
    return {
        "N": len(returns),
        "mean": mean,
        "median": median,
        "positive_rate": p,
        "mean_ci_95": [mean - z * standard_error, mean + z * standard_error],
        "positive_rate_wilson_ci_95": [max(0.0, centre - radius), min(1.0, centre + radius)],
        "mean_mfe": sum(mfes) / len(mfes),
        "mean_mae": sum(maes) / len(maes),
    }


def _diagnostics(rows: list[Mapping[str, Any]], signals: list[Mapping[str, Any]], independent: list[Mapping[str, Any]]) -> dict[str, Any]:
    by_date = sorted({row["signal_date"] for row in independent})
    midpoint = len(by_date) // 2
    first_dates, second_dates = set(by_date[:midpoint]), set(by_date[midpoint:])
    by_month = Counter(row["signal_date"][:7] for row in independent)
    by_symbol = Counter(row["candidate"]["code"] for row in independent)
    by_sector = Counter(str(row.get("sector") or "UNKNOWN") for row in independent)
    by_regime = Counter(str(row.get("market_regime") or "UNKNOWN") for row in rows)
    top = sorted(rows, key=lambda row: (-float(row["return_pct"]), row["signal_id"]))[:10]
    return {
        "raw_signal_level_vs_episode_level": {"raw_signal_level_count": len(signals), "independent_episode_count": len(independent)},
        "first_half_calendar_period": _metric_summary([row for row in rows if row["signal_date"] in first_dates]),
        "second_half_calendar_period": _metric_summary([row for row in rows if row["signal_date"] in second_dates]),
        "monthly_concentration": [{"month": month, "count": count, "share": count / len(independent) if independent else None} for month, count in sorted(by_month.items())],
        "top_contributors": [dict(row) for row in top],
        "symbol_concentration": [{"symbol": symbol, "count": count, "share": count / len(independent) if independent else None} for symbol, count in by_symbol.most_common()],
        "sector_concentration": [{"sector": sector, "count": count, "share": count / len(independent) if independent else None} for sector, count in by_sector.most_common()],
        "market_regime_descriptive_split": dict(sorted(by_regime.items())),
    }


def record_t_close_result(result: Mapping[str, Any], store_root: str | Path) -> dict[str, Any]:
    """Post-process a successful existing ``t_close_runner`` result."""

    if not isinstance(result, Mapping):
        raise ObservationError("OBSERVATION_SOURCE_INVALID", "T-close result must be a mapping")
    input_package = result.get("input_package")
    watchlist = result.get("watchlist")
    generation_commit_sha = result.get("code_git_sha")
    if not isinstance(input_package, Mapping) or not isinstance(watchlist, Mapping) or not isinstance(generation_commit_sha, str):
        raise ObservationError("OBSERVATION_SOURCE_INVALID", "T-close result lacks package/watchlist/code identity")
    return AppendOnlyObservationStore(store_root).record_watchlist(
        watchlist["path"],
        watchlist["run_manifest_path"],
        generation_commit_sha=generation_commit_sha,
    )


def _default_store_root() -> Path:
    return DataPaths.from_env().root / "prospective_observation" / "b_v1_1"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    record = subparsers.add_parser("record")
    record.add_argument("--watchlist", type=Path, required=True)
    record.add_argument("--run-manifest", type=Path, required=True)
    record.add_argument("--generation-commit", required=True)
    record.add_argument("--store-root", type=Path, default=None)
    record.add_argument("--recorded-at-bjt", default=None)
    summary = subparsers.add_parser("summary")
    summary.add_argument("--store-root", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        store = AppendOnlyObservationStore(args.store_root or _default_store_root())
        if args.command == "record":
            result = store.record_watchlist(
                args.watchlist,
                args.run_manifest,
                generation_commit_sha=args.generation_commit,
                recorded_at_bjt=args.recorded_at_bjt,
            )
        else:
            result = store.summary()
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except ObservationError as exc:
        print(json.dumps({"status": exc.status, "error": str(exc)}, ensure_ascii=False, sort_keys=True))
        return 2


__all__ = [
    "AppendOnlyObservationStore",
    "DATA_FAILURE",
    "EXECUTABLE_REFERENCE_OPEN",
    "HORIZONS",
    "LIMIT_STATE_EXECUTION_UNCERTAIN",
    "MISSING_OPEN",
    "NON_EXECUTABLE_CLASSIFICATIONS",
    "ObservationError",
    "OTHER_EXPLICIT_NON_EXECUTABLE",
    "PENDING_REFERENCE_OPEN",
    "PRIMARY_HORIZON",
    "PROTOCOL_COMMIT_SHA",
    "PROTOCOL_VERSION",
    "REFERENCE_EXECUTION_NOT_ACTUAL_FILL",
    "STRATEGY_SPEC_SHA256",
    "STRATEGY_VERSION",
    "SUSPENDED",
    "breakout_episode_id",
    "record_t_close_result",
]


if __name__ == "__main__":
    raise SystemExit(main())
