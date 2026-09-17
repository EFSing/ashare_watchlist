#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
"""Prospective watchlist signal-level review tracker。

Tracker v2 stores one record per candidate event in ``signals``.  A code is
never used as the identity of a signal, so the same stock can be measured
again on a later signal date.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import warnings
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable, Mapping

import requests

from data_paths import DataPaths
from trading_calendar import CalendarUnavailable, TradingCalendar, default_calendar
from watchlist_schema import (
    WatchlistSchemaError,
    load_watchlist,
    stable_signal_id,
)


PATHS = DataPaths.from_env()
BASE = PATHS.root
WATCH_DIR = PATHS.root
TRACK_FILE = PATHS.perf_tracker_file()
REPORT_FILE = PATHS.reports_dir() / "perf_report.md"
REVIEW_HORIZONS = (("T+3", 3), ("T+5", 5), ("T+10", 10))
PRIMARY_REVIEW_HORIZON = "T+5"
TRACK_DAYS = REVIEW_HORIZONS[-1][1]
REVIEW_POINT_PENDING = "PENDING"
REVIEW_POINT_CAPTURED = "CAPTURED"
REVIEW_POINT_NOT_CAPTURED = "NOT_CAPTURED"
CURRENT_PROSPECTIVE_EPOCH_START = "2026-09-03"
CURRENT_PROSPECTIVE_STRATEGY = "B_BREAKOUT_RETEST_LEGACY_V1_1"
EXECUTION_MODEL_DAILY_OHLC_T1_V1 = "EXECUTION_MODEL_DAILY_OHLC_T1_V1"
EXECUTION_VERIFIED = "VERIFIED"
EXECUTION_T_PLUS_1_PENDING = "T_PLUS_1_OBSERVATION_PENDING"
UNVERIFIED_MISSING_EXECUTION_OBSERVATION = "UNVERIFIED_MISSING_EXECUTION_OBSERVATION"
EXIT_REASON_STOP_GAP = "STOP_GAP"
EXIT_REASON_TARGET_GAP = "TARGET_GAP"
EXIT_REASON_STOP = "STOP"
EXIT_REASON_TARGET = "TARGET"
EXIT_REASON_TIME = "TIME_EXIT"
EXIT_REASON_TIME_PENDING_T1 = "TIME_EXIT_PENDING_T1"
EXIT_REASON_TIME_DEFERRED_T1 = "TIME_EXIT_T1_DEFERRED"
EXIT_REASON_EXPIRED_UNTRIGGERED = "EXPIRED_UNTRIGGERED"
EXIT_REASON_AMBIGUOUS = "AMBIGUOUS_SAME_BAR"
RETURN_BASIS_GROSS = "GROSS / BEFORE_FEES_AND_SLIPPAGE"
STRATEGY_RULE_PERFORMANCE_MODEL = "STRATEGY_RULE_PERFORMANCE_TRIGGER_STOP_TARGET_T1_V1"
PERFORMANCE_DATA_INCOMPLETE = "PERFORMANCE_DATA_INCOMPLETE"
STRATEGY_RULE_CONFIG_ERROR = "STRATEGY_RULE_CONFIG_ERROR"
RULE_STATUS_NOT_YET_ELIGIBLE = "NOT_YET_ELIGIBLE"
RULE_STATUS_UNTRIGGERED = "UNTRIGGERED"
RULE_STATUS_OPEN = "OPEN"
RULE_STATUS_CLOSED = "CLOSED"
RULE_STATUS_AMBIGUOUS = EXIT_REASON_AMBIGUOUS
SKIP_LEGACY_OR_OUT_OF_SCOPE_WATCHLIST = "SKIP_LEGACY_OR_OUT_OF_SCOPE_WATCHLIST"
SOURCE_MODE_LIVE_DAILY_TRACKER_QUOTE = "LIVE_DAILY_TRACKER_QUOTE"
SOURCE_MODE_EXACT_DATE_IMMUTABLE_EVIDENCE_RECOVERY_V1 = (
    "EXACT_DATE_IMMUTABLE_EVIDENCE_RECOVERY_V1"
)
PATH_UNVERIFIED_MISSING_PRIOR_EXECUTION_PATH = "UNVERIFIED_MISSING_PRIOR_EXECUTION_PATH"
CONFIRMED_ENTRY_UNAVAILABLE = "CONFIRMED_ENTRY_UNAVAILABLE"
REVIEW_OBSERVATION_INCOMPLETE = "REVIEW_OBSERVATION_INCOMPLETE"
EPHEMERAL_RULE_PERFORMANCE_RECONSTRUCTION_ENV = (
    "ASHARE_EPHEMERAL_RULE_PERFORMANCE_RECONSTRUCTION"
)
EPHEMERAL_RULE_PERFORMANCE_RECONSTRUCTION = (
    "EPHEMERAL_PROVIDER_RULE_PERFORMANCE_RECONSTRUCTION"
)


class TrackerSchemaError(ValueError):
    """The tracker is neither the supported v2 model nor migratable v1."""


class QuoteDataError(RuntimeError):
    """Provider-neutral tracker observation error."""


def new_tracker() -> dict[str, Any]:
    return {"version": 2, "signals": {}, "updated": None, "review_coverage": None}


def parse_date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip().replace("-", "")
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"invalid date: {value!r}")
    return datetime.strptime(text, "%Y%m%d").date()


def _tracker_number(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or value is None:
        raise QuoteDataError(f"tracker quote {field_name} is missing")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise QuoteDataError(f"tracker quote {field_name} is not numeric") from exc
    if not math.isfinite(number):
        raise QuoteDataError(f"tracker quote {field_name} is not finite")
    return number


def _validate_tracker_quotes(
    quotes: Mapping[str, Mapping[str, Any]],
    *,
    expected_codes: Iterable[str],
    expected_date: date | datetime | str,
) -> None:
    expected = {str(code).strip().lower().zfill(6) for code in expected_codes}
    actual = {str(code).strip().lower().zfill(6) for code in quotes}
    if expected != actual:
        raise QuoteDataError(
            f"HiThink tracker quote coverage mismatch; missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )
    expected_date_text = parse_date(expected_date).isoformat()
    for raw_code, quote in quotes.items():
        code = str(raw_code).strip().lower().zfill(6)
        if not isinstance(quote, Mapping) or str(quote.get("code", code)).strip().lower().zfill(6) != code:
            raise QuoteDataError(f"tracker quote map key {code!r} does not match quote code")
        if quote.get("quote_date") != expected_date_text:
            raise QuoteDataError(
                f"stale HiThink tracker quote for {code}: {quote.get('quote_date')} != {expected_date_text}"
            )
        opening = _tracker_number(quote.get("open"), f"{code}.open")
        price = _tracker_number(quote.get("price"), f"{code}.price")
        high = _tracker_number(quote.get("high"), f"{code}.high")
        low = _tracker_number(quote.get("low"), f"{code}.low")
        # The tracker preserves the existing observation semantics.  It only
        # needs finite numeric OHLC inputs; the close-generation adapter is
        # the boundary that enforces provider bar geometry.
        if min(opening, price, high, low) <= 0:
            raise QuoteDataError(f"tracker quote OHLC conflict for {code}")


def fetch_quotes(
    codes: Iterable[str],
    expected_date: date | datetime | str,
    *,
    timeout: float = 15.0,
    retries: int = 3,
    request_get: Any | None = None,
    **_ignored: Any,
) -> dict[str, dict[str, Any]]:
    """Fetch daily tracker observations from HiThink historical bars only.

    The name is retained because the tracker tests and call sites inject a
    function with this seam.  It is no longer a Tencent adapter and does not
    synthesize turnover-rate fields.
    """

    del retries, request_get, _ignored
    from live_acquisition import HiThinkClient, _resolve_market_bars

    target = parse_date(expected_date).isoformat()
    normalized_codes = [str(code).strip().lower().zfill(6) for code in codes]
    client = HiThinkClient()
    quotes: dict[str, dict[str, Any]] = {}
    for code in normalized_codes:
        try:
            bars, resolution = _resolve_market_bars(
                client,
                code,
                requested_count=260,
                minimum_acceptable_history=2,
                as_of_date=target,
                timeout=timeout,
                request_get=requests.get,
                retries=3,
                index=False,
                allow_tencent_fallback=False,
                allow_stale_as_of=False,
            )
        except Exception as exc:
            raise QuoteDataError(
                f"HiThink tracker historical quote unavailable for {code}: {type(exc).__name__}: {exc}"
            ) from exc
        if not bars or bars[-1].get("date") != target:
            latest = bars[-1].get("date") if bars else None
            raise QuoteDataError(
                f"HiThink tracker historical quote for {code} is stale: {latest} != {target}"
            )
        current = bars[-1]
        previous = bars[-2]
        quote = {
            "code": code,
            "quote_date": target,
            "price": current["close"],
            "prev_close": previous["close"],
            "open": current["open"],
            "high": current["high"],
            "low": current["low"],
            "volume": current.get("volume"),
            "chg_pct": (
                (float(current["close"]) / float(previous["close"]) - 1.0) * 100.0
                if float(previous["close"]) > 0
                else None
            ),
            "turnover_amount": current.get("turnover"),
            "provider": resolution.get("provider"),
            "source": resolution.get("source"),
        }
        _validate_tracker_quotes(
            {code: quote},
            expected_codes=[code],
            expected_date=target,
        )
        quotes[code] = quote
    return quotes


def trading_days_after(
    start: date | datetime | str,
    end: date | datetime | str,
    calendar: TradingCalendar,
) -> int:
    """Count XSHG sessions strictly after ``start`` and through ``end``."""

    first, last = parse_date(start), parse_date(end)
    if last <= first:
        return 0
    current = first + timedelta(days=1)
    count = 0
    while current <= last:
        if calendar.is_trading_day(current):
            count += 1
        current += timedelta(days=1)
    return count


def review_date(
    signal_date: date | datetime | str,
    offset: int,
    calendar: TradingCalendar,
) -> str:
    """Return the XSHG session ``offset`` sessions after the signal date."""

    if offset <= 0:
        raise ValueError("review horizon offset must be positive")
    current = parse_date(signal_date)
    remaining = offset
    while remaining:
        current += timedelta(days=1)
        if calendar.is_trading_day(current):
            remaining -= 1
    return current.isoformat()


def review_snapshot_id(signal_id: str, horizon: str, review_trading_date: date | datetime | str) -> str:
    """Return the deterministic identity for one signal/horizon observation."""

    known_horizons = dict(REVIEW_HORIZONS)
    if horizon not in known_horizons:
        raise ValueError(f"unsupported review horizon: {horizon!r}")
    return f"{signal_id}|{horizon}|{parse_date(review_trading_date).isoformat()}"


def _new_review_points(
    signal_id: str,
    signal_date: str,
    calendar: TradingCalendar,
) -> dict[str, dict[str, Any]]:
    normalized_signal_date = parse_date(signal_date).isoformat()
    return {
        label: {
            "signal_id": signal_id,
            "signal_date": normalized_signal_date,
            "horizon": label,
            "offset": offset,
            "scheduled_date": review_date(normalized_signal_date, offset, calendar),
            "review_trading_date": review_date(normalized_signal_date, offset, calendar),
            "snapshot_id": review_snapshot_id(
                signal_id,
                label,
                review_date(normalized_signal_date, offset, calendar),
            ),
            "status": REVIEW_POINT_PENDING,
            "quote_date": None,
            "open": None,
            "price": None,
            "high": None,
            "low": None,
            "return_pct": None,
            "path_status": None,
            "signal_status": None,
            "reason": None,
            "source_mode": None,
            "provenance": None,
        }
        for label, offset in REVIEW_HORIZONS
    }


def _ensure_review_points(
    signal: dict[str, Any],
    calendar: TradingCalendar,
) -> dict[str, dict[str, Any]]:
    """Add/validate fixed review dates without rewriting captured outcomes."""

    signal_id = str(signal["signal_id"])
    signal_date = parse_date(signal["date"]).isoformat()
    points = signal.get("review_points")
    if not isinstance(points, dict):
        points = {}
        signal["review_points"] = points
    for label, offset in REVIEW_HORIZONS:
        expected_date = review_date(signal_date, offset, calendar)
        expected_snapshot_id = review_snapshot_id(signal_id, label, expected_date)
        point = points.get(label)
        if not isinstance(point, dict):
            point = {}
            points[label] = point
        existing_date = point.get("scheduled_date")
        if existing_date is not None and parse_date(existing_date) != parse_date(expected_date):
            raise TrackerSchemaError(
                f"signal {signal['signal_id']} review date mismatch for {label}: "
                f"{existing_date!r} != {expected_date!r}"
            )
        for field, expected in (
            ("signal_id", signal_id),
            ("signal_date", signal_date),
            ("horizon", label),
            ("offset", offset),
            ("review_trading_date", expected_date),
            ("snapshot_id", expected_snapshot_id),
        ):
            existing = point.get(field)
            if existing is not None and existing != expected:
                raise TrackerSchemaError(
                    f"signal {signal_id} review identity mismatch for {label}: "
                    f"{field}={existing!r} != {expected!r}"
                )
            point.setdefault(field, expected)
        point.setdefault("scheduled_date", expected_date)
        point.setdefault("status", REVIEW_POINT_PENDING)
        point.setdefault("quote_date", None)
        point.setdefault("open", None)
        point.setdefault("price", None)
        point.setdefault("high", None)
        point.setdefault("low", None)
        point.setdefault("return_pct", None)
        point.setdefault("path_status", point.get("signal_status"))
        point.setdefault("signal_status", None)
        point.setdefault("reason", None)
        point.setdefault("source_mode", None)
        point.setdefault("provenance", None)
    return points


def migrate_legacy_tracker(legacy: dict[str, Any]) -> dict[str, Any]:
    """Migrate v1 code-keyed rows without changing their historical outcomes."""

    if legacy.get("version") != 1 or not isinstance(legacy.get("stocks"), dict):
        raise TrackerSchemaError("unsupported tracker schema; expected version 2 signals")
    migrated = new_tracker()
    for code, old in legacy["stocks"].items():
        if not isinstance(old, dict):
            raise TrackerSchemaError(f"legacy stock {code} is not an object")
        list_date = parse_date(old.get("list_date"))
        setup = old.get("setup") or old.get("buy_type") or "legacy"
        strategy_version = old.get("strategy_version") or "legacy-v1"
        signal_id = stable_signal_id(strategy_version, list_date.isoformat(), str(code), str(setup))
        if signal_id in migrated["signals"]:
            raise TrackerSchemaError(f"legacy tracker contains duplicate signal identity: {signal_id}")
        record = dict(old)
        record.update({
            "signal_id": signal_id,
            "strategy_version": strategy_version,
            "date": list_date.isoformat(),
            "code": str(code),
            "setup": str(setup),
            "observations": old.get("observations", []),
            "ambiguity_reason": old.get("ambiguity_reason"),
        })
        migrated["signals"][signal_id] = record
    migrated["updated"] = legacy.get("updated")
    warnings.warn(
        "migrated legacy code-keyed perf tracker in memory; it will be written as v2 on save",
        RuntimeWarning,
        stacklevel=2,
    )
    return migrated


def _validate_tracker(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get("version") != 2:
        raise TrackerSchemaError("tracker must be an object with version=2")
    if not isinstance(data.get("signals"), dict):
        raise TrackerSchemaError("tracker signals must be an object keyed by signal_id")
    for key, signal in data["signals"].items():
        if not isinstance(signal, dict) or signal.get("signal_id") != key:
            raise TrackerSchemaError(f"TRACKER_IDENTITY_CONFLICT: signal key mismatch: {key}")
        for field in ("strategy_version", "date", "code", "setup"):
            if not signal.get(field):
                raise TrackerSchemaError(f"signal {key} missing {field}")
        expected = stable_signal_id(signal['strategy_version'], signal['date'], signal['code'], signal['setup'])
        if key != expected:
            raise TrackerSchemaError(f"TRACKER_IDENTITY_CONFLICT: {key} != {expected}")
        if is_current_prospective_signal(signal):
            signal_date = parse_date(signal['date'])
            for field in ('first_trigger_date', 'close_date'):
                if signal.get(field) and parse_date(signal[field]) <= signal_date:
                    raise TrackerSchemaError(f'PRE_T_PLUS_1_STATE_VIOLATION: {key}: {field}')
            for observation in signal.get('observations', []):
                if parse_date(observation['date']) <= signal_date:
                    raise TrackerSchemaError(f'PRE_T_PLUS_1_STATE_VIOLATION: {key}: observation.date')
    data.setdefault("updated", None)
    data.setdefault("review_coverage", None)
    return data


def load_tracker(path: str | Path | None = None) -> dict[str, Any]:
    tracker_path = Path(path) if path is not None else TRACK_FILE
    if not tracker_path.exists():
        return new_tracker()
    try:
        data = json.loads(tracker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TrackerSchemaError(f"cannot load tracker {tracker_path}: {exc}") from exc
    if data.get("version") == 1:
        return migrate_legacy_tracker(data)
    return _validate_tracker(data)


def save_tracker(data: dict[str, Any], path: str | Path | None = None) -> None:
    tracker_path = Path(path) if path is not None else TRACK_FILE
    _validate_tracker(data)
    tracker_path.parent.mkdir(parents=True, exist_ok=True)
    tracker_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def _signal_from_candidate(
    watchlist: dict[str, Any],
    candidate: dict[str, Any],
    calendar: TradingCalendar,
) -> dict[str, Any]:
    signal_id = candidate["signal_id"]
    signal_date = watchlist["date"]
    return {
        "signal_id": signal_id,
        "strategy_version": candidate["strategy_version"],
        "date": signal_date,
        "code": candidate["code"],
        "setup": candidate["setup"],
        "name": candidate["name"],
        "buy_type": candidate["buy_type"],
        "score": candidate["score"],
        "trigger": candidate["trigger"],
        "stop": candidate["stop"],
        "target": candidate["target"],
        "rr": candidate["rr"],
        "status": "pending",
        "execution_model": EXECUTION_MODEL_DAILY_OHLC_T1_V1,
        "execution_verification_status": EXECUTION_T_PLUS_1_PENDING,
        "execution_verification_reason": None,
        "entry_date": None,
        "entry_price": None,
        "sellable_from": None,
        "exit_date": None,
        "exit_price": None,
        "exit_reason": None,
        "realized_return_pct": None,
        "realized_r": None,
        "holding_sessions": None,
        "entry_day_stop_touched": False,
        "entry_day_target_touched": False,
        "mfe_pct": None,
        "mae_pct": None,
        "mfe_mae_verification_status": None,
        "latest_observation_date": None,
        "latest_mark_price": None,
        "unrealized_return_pct": None,
        "unrealized_r": None,
        "return_basis": RETURN_BASIS_GROSS,
        "result_price": None,
        "days_tracked": 0,
        "first_trigger_date": None,
        "close_date": None,
        "ambiguity_reason": None,
        "observations": [],
        "review_points": _new_review_points(signal_id, signal_date, calendar),
    }


def is_current_prospective_signal(signal: dict[str, Any]) -> bool:
    return (parse_date(signal['date']).isoformat() >= CURRENT_PROSPECTIVE_EPOCH_START
            and signal.get('strategy_version') == CURRENT_PROSPECTIVE_STRATEGY)


def current_prospective_watchlists(paths: DataPaths) -> list[dict[str, Any]]:
    """Only schema-valid, exact-strategy canonical lists belong to this epoch."""
    result = []
    for path in paths.watchlist_files():
        try:
            watchlist = load_watchlist(path)
        except WatchlistSchemaError as exc:
            warnings.warn(f'{SKIP_LEGACY_OR_OUT_OF_SCOPE_WATCHLIST}: {path.name}: {exc}', RuntimeWarning)
            continue
        if (not is_current_prospective_signal(watchlist)
                or any(c['strategy_version'] != CURRENT_PROSPECTIVE_STRATEGY for c in watchlist['candidates'])):
            warnings.warn(f'{SKIP_LEGACY_OR_OUT_OF_SCOPE_WATCHLIST}: {path.name}', RuntimeWarning)
            continue
        result.append(watchlist)
    return result


def current_prospective_tracker(
    tracker: dict[str, Any], paths: DataPaths | None = None,
) -> dict[str, Any]:
    """Read-only eligible view; every retained identity must have canonical evidence."""
    _validate_tracker(tracker)
    canonical = {c['signal_id']: c for w in current_prospective_watchlists(paths or PATHS)
                 for c in w['candidates']}
    signals = {}
    for key, signal in tracker['signals'].items():
        if not is_current_prospective_signal(signal):
            continue
        candidate = canonical.get(key)
        if candidate is None or any(signal.get(k) != candidate[k] for k in
                                    ('code', 'setup', 'strategy_version', 'trigger', 'stop', 'target')):
            raise TrackerSchemaError(f'CURRENT_PROSPECTIVE_TRACKER_IDENTITY_MISMATCH: {key}')
        signals[key] = signal
    return {**tracker, 'signals': signals}


def current_tracker_cleanup_plan(tracker: dict[str, Any], paths: DataPaths | None = None) -> dict[str, Any]:
    """Validate KEEP first and produce a deterministic plan without mutation."""
    eligible = current_prospective_tracker(tracker, paths)['signals']
    return {
        'epoch_start': CURRENT_PROSPECTIVE_EPOCH_START,
        'strategy_version': CURRENT_PROSPECTIVE_STRATEGY,
        'KEEP': sorted(eligible),
        'REMOVE_FROM_CURRENT_TRACKER': sorted(set(tracker['signals']) - set(eligible)),
    }


def cleanup_current_tracker(tracker: dict[str, Any], paths: DataPaths | None = None) -> dict[str, Any]:
    plan = current_tracker_cleanup_plan(tracker, paths)
    for key in plan['REMOVE_FROM_CURRENT_TRACKER']:
        del tracker['signals'][key]
    return plan


def ingest(
    tracker: dict[str, Any],
    paths: DataPaths | None = None,
    calendar: TradingCalendar | None = None,
) -> int:
    """Ingest validated daily watchlists into one record per signal event."""

    _validate_tracker(tracker)
    resolver = paths or PATHS
    cal = calendar or default_calendar()
    added = 0
    current_prospective_tracker(tracker, resolver)
    additions = {}
    for watchlist in current_prospective_watchlists(resolver):
        for candidate in watchlist["candidates"]:
            signal_id = candidate["signal_id"]
            if signal_id in tracker["signals"]:
                continue
            additions[signal_id] = _signal_from_candidate(watchlist, candidate, cal)
            added += 1
    tracker['signals'].update(additions)
    return added


def _touches(value: float | None, level: float | None, direction: str) -> bool:
    if value is None or level is None:
        return False
    return value <= level if direction == "down" else value >= level


def classify_signal_bar(
    *,
    status: str,
    trigger: float | None,
    stop: float | None,
    target: float | None,
    high: float | None,
    low: float | None,
    price: float | None = None,
) -> dict[str, Any]:
    """Classify one bar and expose same-bar ordering ambiguity explicitly."""

    trigger_hit = _touches(high, trigger, "up") or _touches(price, trigger, "up")
    stop_hit = _touches(low, stop, "down") or _touches(price, stop, "down")
    target_hit = _touches(high, target, "up") or _touches(price, target, "up")

    if status == "pending":
        if trigger_hit and (stop_hit or target_hit):
            touched = [name for name, hit in (("trigger", trigger_hit), ("stop", stop_hit), ("target", target_hit)) if hit]
            return {
                "status": "AMBIGUOUS_SAME_BAR",
                "reason": "same bar touched " + ", ".join(touched) + "; intrabar order is unavailable",
                "trigger_hit": trigger_hit,
                "stop_hit": stop_hit,
                "target_hit": target_hit,
            }
        if trigger_hit:
            return {"status": "triggered", "reason": "trigger touched", "trigger_hit": True}
        return {"status": "pending", "reason": "trigger not touched", "trigger_hit": False}

    if status == "triggered":
        if stop_hit and target_hit:
            return {
                "status": "AMBIGUOUS_SAME_BAR",
                "reason": "same bar touched stop and target; intrabar order is unavailable",
                "stop_hit": True,
                "target_hit": True,
            }
        if stop_hit:
            return {"status": "loss", "reason": "stop touched", "stop_hit": True}
        if target_hit:
            return {"status": "win", "reason": "target touched", "target_hit": True}
        return {"status": "triggered", "reason": "neither stop nor target touched"}

    return {"status": status, "reason": "signal is already closed"}


def _provenance_fields(
    source_mode: str | None,
    provenance: dict[str, Any] | None,
) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if source_mode:
        fields["source_mode"] = source_mode
    if provenance:
        fields["provenance"] = dict(provenance)
    return fields


def _append_observation(
    signal: dict[str, Any],
    quote: dict[str, Any],
    *,
    source_mode: str = SOURCE_MODE_LIVE_DAILY_TRACKER_QUOTE,
    provenance: dict[str, Any] | None = None,
) -> bool:
    observation = {
        "date": quote["quote_date"],
        "open": quote.get("open"),
        "price": quote["price"],
        "high": quote["high"],
        "low": quote["low"],
    }
    observation.update(_provenance_fields(source_mode, provenance))
    for index, old in enumerate(signal.setdefault("observations", [])):
        if old.get("date") == observation["date"]:
            if old == observation:
                return False
            signal["observations"][index] = observation
            return True
    signal["observations"].append(observation)
    return True


def _snapshot_return_pct(signal: dict[str, Any], price: float | None) -> float | None:
    """Calculate a fixed-point return only when a confirmed entry exists."""

    entry_price = signal.get("entry_price")
    if entry_price is None or price is None:
        return None
    try:
        entry_value = float(entry_price)
        price_value = float(price)
    except (TypeError, ValueError):
        return None
    if entry_value <= 0:
        return None
    return round((price_value / entry_value - 1.0) * 100.0, 6)


def _capture_review_points(
    signal: dict[str, Any],
    quote: dict[str, Any],
    today_date: date,
    calendar: TradingCalendar,
    *,
    source_mode: str = SOURCE_MODE_LIVE_DAILY_TRACKER_QUOTE,
    provenance: dict[str, Any] | None = None,
) -> int:
    """Capture due fixed-point snapshots without historical backfill."""

    points = _ensure_review_points(signal, calendar)
    changed = 0
    for point in points.values():
        if point["status"] != REVIEW_POINT_PENDING and not (
            point["status"] == REVIEW_POINT_NOT_CAPTURED
            and point.get("reason") == REVIEW_OBSERVATION_INCOMPLETE
        ):
            continue
        scheduled = parse_date(point["scheduled_date"])
        if today_date < scheduled:
            continue
        if today_date > scheduled:
            point.update({
                "status": REVIEW_POINT_NOT_CAPTURED,
                "reason": "scheduled XSHG session was missed; historical backfill is forbidden",
            })
            changed += 1
            continue
        return_pct = _snapshot_return_pct(signal, quote["price"])
        point.update({
            "status": REVIEW_POINT_CAPTURED,
            "quote_date": quote["quote_date"],
            "open": quote.get("open"),
            "price": quote["price"],
            "high": quote["high"],
            "low": quote["low"],
            "return_pct": return_pct,
            "path_status": signal["status"],
            "signal_status": signal["status"],
            "reason": None if return_pct is not None else "confirmed entry unavailable; return is unverified",
        })
        point.update(_provenance_fields(source_mode, provenance))
        changed += 1
    return changed


def _mark_expected_horizon_failures(
    tracker: dict[str, Any],
    expected: dict[str, Any],
) -> None:
    """Record an exact same-date failure without pretending a quote was captured."""

    expected_point_ids = set(expected.get("horizon_point_ids", []))
    for signal in tracker.get("signals", {}).values():
        if not isinstance(signal, dict):
            continue
        for point in (signal.get("review_points") or {}).values():
            if not isinstance(point, dict) or point.get("snapshot_id") not in expected_point_ids:
                continue
            point["status"] = REVIEW_POINT_NOT_CAPTURED
            point["reason"] = REVIEW_OBSERVATION_INCOMPLETE


def _capture_exact_review_point(
    signal: dict[str, Any],
    horizon: str,
    quote: dict[str, Any],
    calendar: TradingCalendar,
    *,
    path_status: str | None,
    reason: str | None,
    source_mode: str,
    provenance: dict[str, Any] | None = None,
) -> bool:
    """Write one exact-date fixed point, including its immutable provenance."""

    points = _ensure_review_points(signal, calendar)
    if horizon not in points:
        raise TrackerSchemaError(f"unsupported review horizon: {horizon!r}")
    point = points[horizon]
    return_pct = _snapshot_return_pct(signal, quote.get("price"))
    expected = {
        "status": REVIEW_POINT_CAPTURED,
        "quote_date": quote.get("quote_date"),
        "open": quote.get("open"),
        "price": quote.get("price"),
        "high": quote.get("high"),
        "low": quote.get("low"),
        "return_pct": return_pct,
        "path_status": path_status,
        "signal_status": signal.get("status"),
        "reason": reason,
    }
    expected.update(_provenance_fields(source_mode, provenance))
    if all(point.get(key) == value for key, value in expected.items()):
        return False
    point.update(expected)
    return True


def _as_number(value: Any) -> float | None:
    """Return a finite numeric value when a stored OHLC field is usable."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _next_session_after(value: date | datetime | str, calendar: TradingCalendar) -> date:
    current = parse_date(value) + timedelta(days=1)
    while not calendar.is_trading_day(current):
        current += timedelta(days=1)
    return current


def _session_span(
    start: date | datetime | str,
    end: date | datetime | str,
    calendar: TradingCalendar,
) -> int:
    first, last = parse_date(start), parse_date(end)
    if last < first:
        return 0
    current = first
    count = 0
    while current <= last:
        if calendar.is_trading_day(current):
            count += 1
        current += timedelta(days=1)
    return count


def _execution_horizon_sessions(
    signal_date: date,
    calendar: TradingCalendar,
) -> list[date]:
    sessions: list[date] = []
    current = signal_date
    while len(sessions) < TRACK_DAYS:
        current = _next_session_after(current, calendar)
        sessions.append(current)
    return sessions


def _execution_state_defaults() -> dict[str, Any]:
    return {
        "status": "pending",
        "execution_model": EXECUTION_MODEL_DAILY_OHLC_T1_V1,
        "execution_verification_status": EXECUTION_T_PLUS_1_PENDING,
        "execution_verification_reason": None,
        "entry_date": None,
        "entry_price": None,
        "sellable_from": None,
        "exit_date": None,
        "exit_price": None,
        "exit_reason": None,
        "realized_return_pct": None,
        "realized_r": None,
        "holding_sessions": None,
        "entry_day_stop_touched": False,
        "entry_day_target_touched": False,
        "mfe_pct": None,
        "mae_pct": None,
        "mfe_mae_verification_status": None,
        "latest_observation_date": None,
        "latest_mark_price": None,
        "unrealized_return_pct": None,
        "unrealized_r": None,
        "return_basis": RETURN_BASIS_GROSS,
        # Existing v2 compatibility fields are always synchronized below.
        "result_price": None,
        "days_tracked": 0,
        "first_trigger_date": None,
        "close_date": None,
        "ambiguity_reason": None,
    }


def _entry_fill_price(signal: Mapping[str, Any], observation: Mapping[str, Any]) -> float | None:
    trigger = _as_number(signal.get("trigger"))
    if trigger is None:
        return None
    opening = _as_number(observation.get("open"))
    if opening is not None and opening >= trigger:
        return opening
    high = _as_number(observation.get("high"))
    if high is not None and high >= trigger:
        return trigger
    return None


def _sellable_exit_decision(
    signal: Mapping[str, Any],
    observation: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Resolve a sellable daily bar using open-first gap semantics."""

    stop = _as_number(signal.get("stop"))
    target = _as_number(signal.get("target"))
    opening = _as_number(observation.get("open"))
    if opening is not None and stop is not None and opening <= stop:
        return {"exit_reason": EXIT_REASON_STOP_GAP, "exit_price": opening}
    if opening is not None and target is not None and opening >= target:
        return {"exit_reason": EXIT_REASON_TARGET_GAP, "exit_price": opening}

    low = _as_number(observation.get("low"))
    high = _as_number(observation.get("high"))
    stop_hit = low is not None and stop is not None and low <= stop
    target_hit = high is not None and target is not None and high >= target
    if stop_hit and target_hit:
        return {
            "exit_reason": EXIT_REASON_AMBIGUOUS,
            "exit_price": None,
            "reason": "same sellable bar touched stop and target; intrabar order is unavailable",
        }
    if stop_hit:
        return {"exit_reason": EXIT_REASON_STOP, "exit_price": stop}
    if target_hit:
        return {"exit_reason": EXIT_REASON_TARGET, "exit_price": target}
    return None


def _time_exit_t1_decision(signal: Mapping[str, Any], observation: Mapping[str, Any]) -> dict[str, Any] | None:
    """Exit a T+10 entry on its first legal sellable session."""

    opening = _as_number(observation.get("open"))
    stop = _as_number(signal.get("stop"))
    target = _as_number(signal.get("target"))
    if opening is None:
        return {"invalid": True, "reason": "sellable T+1 observation has no usable open"}
    if stop is not None and opening <= stop:
        return {"exit_reason": EXIT_REASON_STOP_GAP, "exit_price": opening}
    if target is not None and opening >= target:
        return {"exit_reason": EXIT_REASON_TARGET_GAP, "exit_price": opening}
    return {"exit_reason": EXIT_REASON_TIME_DEFERRED_T1, "exit_price": opening}


def _apply_replay_exit(state: dict[str, Any], day: date, decision: Mapping[str, Any]) -> None:
    reason = str(decision["exit_reason"])
    state["exit_date"] = day.isoformat()
    state["exit_price"] = decision.get("exit_price")
    state["exit_reason"] = reason
    state["close_date"] = state["exit_date"]
    state["result_price"] = state["exit_price"]
    if reason == EXIT_REASON_AMBIGUOUS:
        state["status"] = "AMBIGUOUS_SAME_BAR"
        state["ambiguity_reason"] = decision.get("reason")
    elif reason in {EXIT_REASON_TARGET, EXIT_REASON_TARGET_GAP}:
        state["status"] = "win"
        state["ambiguity_reason"] = None
    elif reason in {EXIT_REASON_STOP, EXIT_REASON_STOP_GAP}:
        state["status"] = "loss"
        state["ambiguity_reason"] = None
    elif reason in {EXIT_REASON_TIME, EXIT_REASON_TIME_DEFERRED_T1, EXIT_REASON_EXPIRED_UNTRIGGERED}:
        state["status"] = "expired"
        state["ambiguity_reason"] = None


def _set_trade_returns(state: dict[str, Any], signal: Mapping[str, Any]) -> None:
    entry = _as_number(state.get("entry_price"))
    exit_price = _as_number(state.get("exit_price"))
    if state.get("exit_reason") == EXIT_REASON_AMBIGUOUS:
        state["realized_return_pct"] = "UNVERIFIED"
        state["realized_r"] = "UNVERIFIED"
        return
    if entry is None or exit_price is None or entry <= 0:
        state["realized_return_pct"] = None
        state["realized_r"] = None
        return
    state["realized_return_pct"] = round((exit_price / entry - 1.0) * 100.0, 6)
    stop = _as_number(signal.get("stop"))
    risk = entry - stop if stop is not None else None
    state["realized_r"] = round((exit_price - entry) / risk, 6) if risk and risk > 0 else None


def _set_excursions(
    state: dict[str, Any],
    observations: Mapping[date, Mapping[str, Any]],
    signal: Mapping[str, Any],
    as_of_date: date,
    calendar: TradingCalendar,
    *,
    path_end: date | None,
    incomplete: bool,
) -> None:
    entry_date_text = state.get("entry_date")
    entry = _as_number(state.get("entry_price"))
    if entry_date_text is None or entry is None or entry <= 0:
        state["mfe_mae_verification_status"] = None
        return
    entry_date = parse_date(entry_date_text)
    end = path_end or as_of_date
    expected = []
    current = entry_date
    while current <= end:
        if calendar.is_trading_day(current):
            expected.append(current)
        current += timedelta(days=1)
    if incomplete or any(day not in observations for day in expected):
        state["mfe_pct"] = None
        state["mae_pct"] = None
        state["mfe_mae_verification_status"] = UNVERIFIED_MISSING_EXECUTION_OBSERVATION
        return
    highs = [_as_number(observations[day].get("high")) for day in expected]
    lows = [_as_number(observations[day].get("low")) for day in expected]
    if any(value is None for value in highs + lows):
        state["mfe_pct"] = None
        state["mae_pct"] = None
        state["mfe_mae_verification_status"] = UNVERIFIED_MISSING_EXECUTION_OBSERVATION
        return
    state["mfe_pct"] = round(max(0.0, max((value / entry - 1.0) * 100.0 for value in highs if value is not None)), 6)
    state["mae_pct"] = round(min(0.0, min((value / entry - 1.0) * 100.0 for value in lows if value is not None)), 6)
    state["mfe_mae_verification_status"] = EXECUTION_VERIFIED


def rebuild_execution_state_from_observations(
    signal: Mapping[str, Any],
    calendar: TradingCalendar | None = None,
    as_of: date | datetime | str | None = None,
) -> dict[str, Any]:
    """Replay one signal from stored daily OHLC observations under A-share T+1.

    This function is deliberately provider-free and does not mutate ``signal``
    or its fixed-horizon review points.  A missing required XSHG session makes
    the execution path unverified; later observations cannot silently repair
    that gap.
    """

    cal = calendar or default_calendar()
    signal_date = parse_date(signal["date"])
    raw_observations = signal.get("observations")
    raw_observations = raw_observations if isinstance(raw_observations, list) else []
    parsed_observations: dict[date, Mapping[str, Any]] = {}
    observed_dates: list[date] = []
    for observation in raw_observations:
        if not isinstance(observation, Mapping) or observation.get("date") is None:
            continue
        observation_date = parse_date(observation["date"])
        observed_dates.append(observation_date)
        parsed_observations[observation_date] = observation

    as_of_date = parse_date(as_of) if as_of is not None else max(observed_dates or [signal_date])
    visible_observations = {
        day: observation
        for day, observation in parsed_observations.items()
        if signal_date < day <= as_of_date
    }
    state = _execution_state_defaults()
    if as_of_date <= signal_date:
        state["execution_verification_reason"] = "waiting for the next XSHG session"
        return state

    horizon = _execution_horizon_sessions(signal_date, cal)
    first_execution = horizon[0]
    if as_of_date < first_execution:
        state["execution_verification_reason"] = "waiting for the next XSHG session"
        return state

    terminal = False
    missing_day: date | None = None
    missing_reason: str | None = None
    last_processed = signal_date
    entry_date: date | None = None

    for day in horizon:
        if day > as_of_date:
            break
        observation = visible_observations.get(day)
        if observation is None:
            missing_day = day
            missing_reason = f"missing required XSHG execution observation: {day.isoformat()}"
            break
        last_processed = day
        if state["status"] == "pending":
            fill = _entry_fill_price(signal, observation)
            if fill is not None:
                entry_date = day
                state["status"] = "triggered"
                state["entry_date"] = day.isoformat()
                state["entry_price"] = fill
                state["first_trigger_date"] = day.isoformat()
                state["sellable_from"] = _next_session_after(day, cal).isoformat()
                low = _as_number(observation.get("low"))
                high = _as_number(observation.get("high"))
                stop = _as_number(signal.get("stop"))
                target = _as_number(signal.get("target"))
                state["entry_day_stop_touched"] = low is not None and stop is not None and low <= stop
                state["entry_day_target_touched"] = high is not None and target is not None and high >= target
                if day == horizon[-1]:
                    state["exit_reason"] = EXIT_REASON_TIME_PENDING_T1
            elif day == horizon[-1]:
                _apply_replay_exit(
                    state,
                    day,
                    {"exit_reason": EXIT_REASON_EXPIRED_UNTRIGGERED, "exit_price": None},
                )
                terminal = True
            continue

        if state["status"] != "triggered":
            terminal = True
            break
        if entry_date is None:
            entry_date = parse_date(state["entry_date"])
        sellable_from = parse_date(state["sellable_from"])
        if day < sellable_from:
            continue
        decision = _sellable_exit_decision(signal, observation)
        if decision is not None:
            _apply_replay_exit(state, day, decision)
            terminal = True
            break
        if day == horizon[-1]:
            close = _as_number(observation.get("price"))
            if close is None:
                missing_day = day
                missing_reason = f"T+10 observation has no usable close: {day.isoformat()}"
                break
            _apply_replay_exit(
                state,
                day,
                {"exit_reason": EXIT_REASON_TIME, "exit_price": close},
            )
            terminal = True
            break

    # A signal entering on T+10 can only be closed on the following XSHG
    # session.  It is never sold on the entry day.
    if (
        not terminal
        and missing_day is None
        and state["status"] == "triggered"
        and entry_date == horizon[-1]
    ):
        sellable_from = parse_date(state["sellable_from"])
        state["exit_reason"] = EXIT_REASON_TIME_PENDING_T1
        if as_of_date >= sellable_from:
            observation = visible_observations.get(sellable_from)
            if observation is None:
                missing_day = sellable_from
                missing_reason = f"missing required T+1 exit observation: {sellable_from.isoformat()}"
            else:
                last_processed = sellable_from
                decision = _time_exit_t1_decision(signal, observation)
                if decision and decision.get("invalid"):
                    missing_day = sellable_from
                    missing_reason = str(decision.get("reason"))
                elif decision:
                    _apply_replay_exit(state, sellable_from, decision)
                    terminal = True

    if missing_day is not None:
        state["execution_verification_status"] = UNVERIFIED_MISSING_EXECUTION_OBSERVATION
        state["execution_verification_reason"] = missing_reason
        # Keep a proven entry, but never retain an unverified later exit.
        if not terminal:
            state["exit_date"] = None
            state["exit_price"] = None
            state["realized_return_pct"] = None
            state["realized_r"] = None
            state["close_date"] = None
            state["result_price"] = None
            state["ambiguity_reason"] = None
            if state["status"] != "triggered":
                state["entry_date"] = None
                state["entry_price"] = None
                state["first_trigger_date"] = None
                state["sellable_from"] = None
                state["entry_day_stop_touched"] = False
                state["entry_day_target_touched"] = False
            state["exit_reason"] = (
                EXIT_REASON_TIME_PENDING_T1
                if state["status"] == "triggered" and entry_date == horizon[-1]
                else None
            )
    else:
        state["execution_verification_status"] = EXECUTION_VERIFIED
        state["execution_verification_reason"] = None

    if state.get("entry_date"):
        entry_date = parse_date(state["entry_date"])
        end_date = parse_date(state["exit_date"]) if state.get("exit_date") else last_processed
        state["holding_sessions"] = _session_span(entry_date, end_date, cal)
    else:
        state["holding_sessions"] = None

    tracked_through = parse_date(state["exit_date"]) if state.get("exit_date") else last_processed
    state["days_tracked"] = trading_days_after(signal_date, tracked_through, calendar=cal)
    if state.get("entry_date"):
        _set_trade_returns(state, signal)
        path_end = parse_date(state["exit_date"]) if state.get("exit_date") else last_processed
        _set_excursions(
            state,
            visible_observations,
            signal,
            as_of_date,
            cal,
            path_end=path_end,
            incomplete=missing_day is not None,
        )
        visible_after_entry = [day for day in visible_observations if day >= parse_date(state["entry_date"])]
        if visible_after_entry:
            latest_day = max(visible_after_entry)
            latest_price = _as_number(visible_observations[latest_day].get("price"))
            state["latest_observation_date"] = latest_day.isoformat()
            state["latest_mark_price"] = latest_price
            if state["status"] == "triggered" and latest_price is not None:
                entry = _as_number(state["entry_price"])
                stop = _as_number(signal.get("stop"))
                state["unrealized_return_pct"] = round((latest_price / entry - 1.0) * 100.0, 6) if entry else None
                risk = entry - stop if entry is not None and stop is not None else None
                state["unrealized_r"] = round((latest_price - entry) / risk, 6) if risk and risk > 0 else None
    if state.get("exit_reason") == EXIT_REASON_AMBIGUOUS:
        state["realized_return_pct"] = "UNVERIFIED"
        state["realized_r"] = "UNVERIFIED"

    state["first_trigger_date"] = state.get("entry_date")
    state["close_date"] = state.get("exit_date")
    state["result_price"] = state.get("exit_price")
    return state


_REPLAY_COMPATIBILITY_FIELDS = (
    "status", "execution_model", "execution_verification_status", "execution_verification_reason",
    "entry_date", "entry_price", "sellable_from", "exit_date", "exit_price", "exit_reason",
    "realized_return_pct", "realized_r", "holding_sessions", "entry_day_stop_touched",
    "entry_day_target_touched", "mfe_pct", "mae_pct", "mfe_mae_verification_status",
    "latest_observation_date", "latest_mark_price", "unrealized_return_pct", "unrealized_r",
    "return_basis", "result_price", "days_tracked", "first_trigger_date", "close_date",
    "ambiguity_reason",
)


def _apply_rebuilt_execution_state(signal: dict[str, Any], state: Mapping[str, Any]) -> int:
    changed = 0
    for field in _REPLAY_COMPATIBILITY_FIELDS:
        value = state.get(field)
        if signal.get(field) != value:
            signal[field] = value
            changed += 1
    return changed


def build_execution_reconciliation_audit(
    tracker: Mapping[str, Any],
    as_of_date: date | datetime | str,
    calendar: TradingCalendar | None = None,
) -> dict[str, Any]:
    """Return a read-only old-versus-new execution audit."""

    cal = calendar or default_calendar()
    report_date = parse_date(as_of_date)
    signals = [
        signal for signal in (tracker.get("signals", {}) or {}).values()
        if isinstance(signal, Mapping)
        and is_current_prospective_signal(signal)
        and parse_date(signal["date"]) <= report_date
    ]
    status_changes: Counter[str] = Counter()
    entry_date_changes = 0
    close_date_changes = 0
    states = []
    for signal in signals:
        state = rebuild_execution_state_from_observations(signal, calendar=cal, as_of=report_date)
        old_status = signal.get("status")
        new_status = state.get("status")
        if old_status != new_status:
            status_changes[f"{old_status} -> {new_status}"] += 1
        if signal.get("first_trigger_date") != state.get("entry_date"):
            entry_date_changes += 1
        if signal.get("close_date") != state.get("exit_date"):
            close_date_changes += 1
        states.append(state)
    verified = sum(state.get("execution_verification_status") == EXECUTION_VERIFIED for state in states)
    unverified = sum(state.get("execution_verification_status") == UNVERIFIED_MISSING_EXECUTION_OBSERVATION for state in states)
    entered = sum(state.get("entry_date") is not None for state in states)
    closed_confirmed = sum(
        state.get("execution_verification_status") == EXECUTION_VERIFIED
        and isinstance(state.get("realized_return_pct"), (int, float))
        and state.get("exit_price") is not None
        for state in states
    )
    open_positions = sum(
        state.get("execution_verification_status") == EXECUTION_VERIFIED
        and state.get("status") == "triggered"
        and state.get("entry_date") is not None
        for state in states
    )
    return {
        "as_of_date": report_date.isoformat(),
        "execution_model": EXECUTION_MODEL_DAILY_OHLC_T1_V1,
        "provider_calls": 0,
        "signals_total": len(signals),
        "execution_verified": verified,
        "execution_unverified": unverified,
        "entered": entered,
        "closed_confirmed": closed_confirmed,
        "open_positions": open_positions,
        "untriggered_expired": sum(state.get("exit_reason") == EXIT_REASON_EXPIRED_UNTRIGGERED for state in states),
        "ambiguous_exits": sum(state.get("exit_reason") == EXIT_REASON_AMBIGUOUS for state in states),
        "status_changed_count": sum(status_changes.values()),
        "status_changes": dict(sorted(status_changes.items())),
        "entry_date_changed_count": entry_date_changes,
        "close_date_changed_count": close_date_changes,
    }


def reconcile_tracker_execution(
    tracker: dict[str, Any],
    as_of_date: date | datetime | str,
    calendar: TradingCalendar | None = None,
) -> dict[str, Any]:
    """Apply deterministic T+1 replay to current prospective signals only."""

    _validate_tracker(tracker)
    cal = calendar or default_calendar()
    report_date = parse_date(as_of_date)
    audit = build_execution_reconciliation_audit(tracker, report_date, cal)
    changed = 0
    for signal in tracker["signals"].values():
        if not isinstance(signal, dict):
            continue
        if not is_current_prospective_signal(signal) or parse_date(signal["date"]) > report_date:
            continue
        state = rebuild_execution_state_from_observations(signal, calendar=cal, as_of=report_date)
        changed += _apply_rebuilt_execution_state(signal, state)
    tracker["execution_reconciliation"] = {
        "as_of_date": report_date.isoformat(),
        "execution_model": EXECUTION_MODEL_DAILY_OHLC_T1_V1,
        "source": "canonical watchlist identity + stored tracker observations + XSHG calendar",
        "provider_calls": 0,
        "status": "LOCAL_DETERMINISTIC_REPLAY",
        "signals_reconciled": audit["signals_total"],
        "fields_changed": changed,
    }
    return {**audit, "fields_changed": changed}


def _numeric_values(values: list[Any]) -> list[float]:
    return [value for value in (_as_number(item) for item in values) if value is not None]


def _mean_or_none(values: list[Any]) -> float | None:
    numbers = _numeric_values(values)
    return round(mean(numbers), 6) if numbers else None


def _median_or_none(values: list[Any]) -> float | None:
    numbers = _numeric_values(values)
    return round(median(numbers), 6) if numbers else None


def _canonical_rule_signal_records(source: Any) -> list[dict[str, Any]]:
    """Return immutable signal-shaped views of canonical watchlists or signals."""

    if isinstance(source, Mapping):
        if "candidates" in source:
            items: list[Any] = [source]
        elif "signals" in source and isinstance(source.get("signals"), Mapping):
            items = list(source["signals"].values())
        else:
            items = [source]
    elif isinstance(source, (list, tuple)):
        items = list(source)
    else:
        items = list(source) if isinstance(source, Iterable) else []

    records: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        candidates = item.get("candidates")
        if isinstance(candidates, list):
            list_date = item.get("date")
            list_strategy = item.get("strategy_version")
            for candidate in candidates:
                if not isinstance(candidate, Mapping):
                    continue
                strategy = candidate.get("strategy_version", list_strategy)
                setup = candidate.get("setup") or candidate.get("buy_type")
                signal_date = candidate.get("date", list_date)
                if signal_date is None or strategy is None or setup is None:
                    continue
                signal_date = parse_date(signal_date).isoformat()
                code = str(candidate.get("code", ""))
                records.append({
                    "signal_id": candidate.get("signal_id") or stable_signal_id(
                        str(strategy), signal_date, code, str(setup)
                    ),
                    "strategy_version": str(strategy),
                    "date": signal_date,
                    "code": code,
                    "setup": str(setup),
                    "name": candidate.get("name"),
                    "buy_type": candidate.get("buy_type"),
                    "score": candidate.get("score"),
                    "trigger": candidate.get("trigger"),
                    "stop": candidate.get("stop"),
                    "target": candidate.get("target"),
                    "rr": candidate.get("rr"),
                })
            continue
        if item.get("date") is None or item.get("strategy_version") is None:
            continue
        records.append({
            "signal_id": item.get("signal_id"),
            "strategy_version": item.get("strategy_version"),
            "date": parse_date(item["date"]).isoformat(),
            "code": str(item.get("code", "")),
            "setup": item.get("setup") or item.get("buy_type"),
            "name": item.get("name"),
            "buy_type": item.get("buy_type"),
            "score": item.get("score"),
            "trigger": item.get("trigger"),
            "stop": item.get("stop"),
            "target": item.get("target"),
            "rr": item.get("rr"),
        })
    return records


def _canonical_rule_signals(source: Any, report_date: date) -> list[dict[str, Any]]:
    """Filter canonical signal identity at the report as-of boundary."""

    by_id: dict[str, dict[str, Any]] = {}
    for record in _canonical_rule_signal_records(source):
        if record.get("strategy_version") != CURRENT_PROSPECTIVE_STRATEGY:
            continue
        if not record.get("signal_id"):
            setup = record.get("setup") or record.get("buy_type") or "UNKNOWN_SETUP"
            record["signal_id"] = stable_signal_id(
                str(record["strategy_version"]), str(record["date"]),
                str(record.get("code", "")), str(setup),
            )
        if parse_date(record["date"]) <= report_date:
            by_id[str(record["signal_id"])] = record
    return sorted(by_id.values(), key=lambda item: (str(item["date"]), str(item["signal_id"])))


def _rule_history_value(historical_ohlc: Mapping[str, Any] | None, code: str) -> Any:
    if not isinstance(historical_ohlc, Mapping):
        return None
    for key in (code, code.upper(), f"{code}.SH", f"{code}.SZ"):
        if key in historical_ohlc:
            return historical_ohlc[key]
    return None


def _rule_provenance_value(
    historical_ohlc: Mapping[str, Any] | None,
    historical_provenance: Mapping[str, Any] | None,
    code: str,
) -> Any:
    if isinstance(historical_provenance, Mapping):
        by_code = historical_provenance.get("by_code")
        if isinstance(by_code, Mapping):
            for key in (code, code.upper(), f"{code}.SH", f"{code}.SZ"):
                if key in by_code:
                    return by_code[key]
        for key in (code, code.upper(), f"{code}.SH", f"{code}.SZ"):
            if key in historical_provenance:
                return historical_provenance[key]
    raw = _rule_history_value(historical_ohlc, code)
    if isinstance(raw, Mapping):
        return raw.get("provenance")
    return None


def _finite_rule_number(value: Any) -> float | None:
    number = _as_number(value)
    return number if number is not None and math.isfinite(number) else None


def _rule_history_bars(
    raw_history: Any,
    as_of_date: date,
) -> tuple[dict[date, dict[str, float | None]], set[date], list[str]]:
    """Normalize daily OHLC while ignoring bars after the report as-of date."""

    if isinstance(raw_history, Mapping):
        if "bars" in raw_history:
            raw_bars = raw_history.get("bars")
        elif "ohlc" in raw_history:
            raw_bars = raw_history.get("ohlc")
        elif "data" in raw_history:
            raw_bars = raw_history.get("data")
        else:
            raw_bars = None
    else:
        raw_bars = raw_history
    if not isinstance(raw_bars, (list, tuple)):
        return {}, set(), ["historical daily OHLC is missing"]

    bars: dict[date, dict[str, float | None]] = {}
    invalid_days: set[date] = set()
    errors: list[str] = []
    for index, raw_bar in enumerate(raw_bars):
        if not isinstance(raw_bar, Mapping):
            errors.append(f"bar[{index}] is not an object")
            continue
        try:
            bar_date = parse_date(raw_bar["date"])
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"bar[{index}] has an invalid date: {type(exc).__name__}")
            continue
        if bar_date > as_of_date:
            continue
        opening = _finite_rule_number(raw_bar.get("open"))
        high = _finite_rule_number(raw_bar.get("high"))
        low = _finite_rule_number(raw_bar.get("low"))
        closing = _finite_rule_number(raw_bar.get("close"))
        if closing is None:
            closing = _finite_rule_number(raw_bar.get("price"))
        if high is None or low is None or closing is None:
            invalid_days.add(bar_date)
            errors.append(f"{bar_date.isoformat()} is missing usable high/low/close")
            continue
        if high < low or high < closing or low > closing:
            invalid_days.add(bar_date)
            errors.append(f"{bar_date.isoformat()} has conflicting OHLC")
            continue
        if bar_date in bars:
            invalid_days.add(bar_date)
            bars.pop(bar_date, None)
            errors.append(f"duplicate historical bar: {bar_date.isoformat()}")
            continue
        bars[bar_date] = {
            "open": opening,
            "high": high,
            "low": low,
            "close": closing,
        }
    return bars, invalid_days, errors


def _rule_history_source_label(provenance: Any, has_history: bool) -> str:
    if isinstance(provenance, Mapping):
        source = provenance.get("source") or provenance.get("source_identity") or provenance.get("provider")
        if source:
            return str(source)
    elif provenance:
        return str(provenance)
    return "INJECTED_HISTORICAL_DAILY_OHLC" if has_history else "MISSING_HISTORICAL_DAILY_OHLC"


def _rule_sessions_after(
    signal_date: date,
    report_date: date,
    calendar: TradingCalendar,
) -> list[date]:
    sessions: list[date] = []
    current = _next_session_after(signal_date, calendar)
    while current <= report_date:
        sessions.append(current)
        current = _next_session_after(current, calendar)
    return sessions


def _strategy_rule_trade_row(
    signal: Mapping[str, Any],
    historical_ohlc: Mapping[str, Any] | None,
    historical_provenance: Mapping[str, Any] | None,
    report_date: date,
    calendar: TradingCalendar,
) -> dict[str, Any]:
    signal_date = parse_date(signal["date"])
    code = str(signal.get("code", ""))
    provenance = _rule_provenance_value(historical_ohlc, historical_provenance, code)
    raw_history = _rule_history_value(historical_ohlc, code)
    has_history = raw_history is not None
    source_label = _rule_history_source_label(provenance, has_history)
    row: dict[str, Any] = {
        "signal_id": signal.get("signal_id"),
        "strategy_version": signal.get("strategy_version"),
        "signal_date": signal_date.isoformat(),
        "code": code,
        "name": signal.get("name"),
        "setup": signal.get("setup"),
        "score": signal.get("score"),
        "trigger": signal.get("trigger"),
        "stop": signal.get("stop"),
        "target": signal.get("target"),
        "rr": signal.get("rr"),
        "entry_date": None,
        "trigger_date": None,
        "entry_price": None,
        "sellable_from": None,
        "exit_date": None,
        "exit_price": None,
        "exit_reason": None,
        "exit_type": None,
        "ambiguous_low": None,
        "ambiguous_high": None,
        "realized_return_pct": None,
        "return_pct": None,
        "realized_r": None,
        "r": None,
        "holding_sessions": None,
        "entry_day_stop_touched": False,
        "entry_day_target_touched": False,
        "mfe_pct": None,
        "mae_pct": None,
        "latest_bar_date": None,
        "latest_close": None,
        "mark_return_pct": None,
        "unrealized_return_pct": None,
        "unrealized_r": None,
        "status": RULE_STATUS_NOT_YET_ELIGIBLE,
        "reason": None,
        "historical_data_status": "NOT_REQUIRED",
        "historical_source": source_label,
        "historical_provenance": provenance,
    }
    expected_sessions = _rule_sessions_after(signal_date, report_date, calendar)
    if not expected_sessions:
        row["reason"] = "signal has no T+1 opportunity by report_date"
        return row

    trigger = _finite_rule_number(signal.get("trigger"))
    stop = _finite_rule_number(signal.get("stop"))
    target = _finite_rule_number(signal.get("target"))
    if trigger is None or stop is None or target is None or trigger <= stop or target <= trigger:
        row["status"] = STRATEGY_RULE_CONFIG_ERROR
        row["historical_data_status"] = "NOT_REQUIRED"
        row["reason"] = "trigger/stop/target configuration is not a valid long rule"
        return row

    bars, invalid_days, history_errors = _rule_history_bars(raw_history, report_date)
    row["historical_data_status"] = "COMPLETE"
    entry_date: date | None = None
    sellable_from: date | None = None
    path_bars: list[dict[str, float | None]] = []
    path_dates: list[date] = []
    incomplete_reason: str | None = None
    terminal = False

    for day in expected_sessions:
        if day in invalid_days or day not in bars:
            incomplete_reason = (
                f"missing or unusable historical daily OHLC: {day.isoformat()}"
            )
            if history_errors:
                incomplete_reason += f" ({history_errors[0]})"
            break
        bar = bars[day]
        if entry_date is None:
            high = bar["high"]
            low = bar["low"]
            if high is not None and high >= trigger:
                entry_date = day
                sellable_from = _next_session_after(day, calendar)
                path_bars.append(bar)
                path_dates.append(day)
                row["entry_date"] = day.isoformat()
                row["trigger_date"] = day.isoformat()
                row["entry_price"] = trigger
                row["sellable_from"] = sellable_from.isoformat()
                row["entry_day_stop_touched"] = low is not None and low <= stop
                row["entry_day_target_touched"] = high >= target
            continue

        path_bars.append(bar)
        path_dates.append(day)
        if sellable_from is None or day < sellable_from:
            continue
        low = bar["low"]
        high = bar["high"]
        stop_hit = low is not None and low <= stop
        target_hit = high is not None and high >= target
        if stop_hit and target_hit:
            row["status"] = RULE_STATUS_AMBIGUOUS
            row["exit_date"] = day.isoformat()
            row["exit_reason"] = EXIT_REASON_AMBIGUOUS
            row["exit_type"] = EXIT_REASON_AMBIGUOUS
            row["ambiguous_low"] = low
            row["ambiguous_high"] = high
            row["reason"] = "same sellable daily bar touched stop and target; intraday order unavailable"
            terminal = True
            break
        if stop_hit:
            row["status"] = RULE_STATUS_CLOSED
            row["exit_date"] = day.isoformat()
            row["exit_price"] = stop
            row["exit_reason"] = EXIT_REASON_STOP
            row["exit_type"] = EXIT_REASON_STOP
            terminal = True
            break
        if target_hit:
            row["status"] = RULE_STATUS_CLOSED
            row["exit_date"] = day.isoformat()
            row["exit_price"] = target
            row["exit_reason"] = EXIT_REASON_TARGET
            row["exit_type"] = EXIT_REASON_TARGET
            terminal = True
            break

    if incomplete_reason is not None and not terminal:
        row["status"] = PERFORMANCE_DATA_INCOMPLETE
        row["historical_data_status"] = "INCOMPLETE"
        row["reason"] = incomplete_reason
    elif not terminal:
        row["status"] = RULE_STATUS_OPEN if entry_date is not None else RULE_STATUS_UNTRIGGERED
        if entry_date is None:
            row["reason"] = "no post-signal daily high reached trigger by report_date"

    if entry_date is not None and path_bars and row["historical_data_status"] == "COMPLETE":
        highs = [bar["high"] for bar in path_bars if bar["high"] is not None]
        lows = [bar["low"] for bar in path_bars if bar["low"] is not None]
        row["mfe_pct"] = round(max((value / trigger - 1.0) * 100.0 for value in highs), 6)
        row["mae_pct"] = round(min((value / trigger - 1.0) * 100.0 for value in lows), 6)

    if row["status"] == RULE_STATUS_CLOSED:
        exit_date = parse_date(row["exit_date"])
        exit_price = _finite_rule_number(row["exit_price"])
        row["holding_sessions"] = _session_span(entry_date, exit_date, calendar)
        row["realized_return_pct"] = round((exit_price / trigger - 1.0) * 100.0, 6) if exit_price is not None else None
        row["return_pct"] = row["realized_return_pct"]
        row["realized_r"] = round((exit_price - trigger) / (trigger - stop), 6) if exit_price is not None else None
        row["r"] = row["realized_r"]
    elif row["status"] == RULE_STATUS_OPEN and path_bars:
        latest_day = path_dates[-1]
        latest_bar = path_bars[-1]
        latest_close = latest_bar["close"]
        row["latest_bar_date"] = latest_day.isoformat()
        row["latest_close"] = latest_close
        row["mark_return_pct"] = round((latest_close / trigger - 1.0) * 100.0, 6) if latest_close is not None else None
        row["unrealized_return_pct"] = row["mark_return_pct"]
        row["unrealized_r"] = round((latest_close - trigger) / (trigger - stop), 6) if latest_close is not None else None
    if row["status"] == RULE_STATUS_AMBIGUOUS:
        row["realized_return_pct"] = None
        row["realized_r"] = None
    return row


def build_strategy_rule_performance(
    canonical_watchlists: Any,
    historical_ohlc: Mapping[str, Any] | None,
    as_of_date: date | datetime | str,
    calendar: TradingCalendar | None = None,
    *,
    historical_provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Reconstruct theoretical trigger/stop/target performance from daily OHLC.

    This is intentionally independent from prospective observations and from
    :func:`build_trade_performance_summary`.  It uses the canonical signal
    identity supplied by ``canonical_watchlists`` and only bars dated after
    signal date and no later than ``as_of_date``.  Entry and exit prices are
    always the canonical rule prices; daily ``open`` is never used as a fill.
    """

    cal = calendar or default_calendar()
    report_date = parse_date(as_of_date)
    signals = _canonical_rule_signals(canonical_watchlists, report_date)
    rows = [
        _strategy_rule_trade_row(signal, historical_ohlc, historical_provenance, report_date, cal)
        for signal in signals
    ]
    eligible_rows = [row for row in rows if row["status"] != RULE_STATUS_NOT_YET_ELIGIBLE]
    triggered_rows = [row for row in rows if row.get("entry_date") is not None]
    target_rows = [row for row in rows if row["status"] == RULE_STATUS_CLOSED and row["exit_reason"] == EXIT_REASON_TARGET]
    stop_rows = [row for row in rows if row["status"] == RULE_STATUS_CLOSED and row["exit_reason"] == EXIT_REASON_STOP]
    closed_rows = target_rows + stop_rows
    open_rows = [row for row in rows if row["status"] == RULE_STATUS_OPEN]
    ambiguous_rows = [row for row in rows if row["status"] == RULE_STATUS_AMBIGUOUS]
    incomplete_rows = [row for row in rows if row["status"] == PERFORMANCE_DATA_INCOMPLETE]
    config_rows = [row for row in rows if row["status"] == STRATEGY_RULE_CONFIG_ERROR]
    untriggered_rows = [row for row in rows if row["status"] == RULE_STATUS_UNTRIGGERED]
    returns = [row["realized_return_pct"] for row in closed_rows]
    r_values = [row["realized_r"] for row in closed_rows]
    wins = [row["realized_return_pct"] for row in target_rows]
    losses = [row["realized_return_pct"] for row in stop_rows]
    mean_win = _mean_or_none(wins)
    mean_loss = _mean_or_none(losses)
    positive_sum = sum(_numeric_values(wins))
    negative_sum = sum(_numeric_values(losses))
    source_labels = sorted({
        str(row["historical_source"])
        for row in rows
        if row.get("historical_source") and row["status"] != RULE_STATUS_NOT_YET_ELIGIBLE
    })
    by_code = (historical_provenance or {}).get("by_code", {}) if isinstance(historical_provenance, Mapping) else {}
    cache_meta = (historical_provenance or {}).get("__meta__", {}) if isinstance(historical_provenance, Mapping) else {}
    resolved_count = len(closed_rows)
    return {
        "as_of_date": report_date.isoformat(),
        "strategy": CURRENT_PROSPECTIVE_STRATEGY,
        "performance_model": STRATEGY_RULE_PERFORMANCE_MODEL,
        "return_basis": RETURN_BASIS_GROSS,
        "theoretical_rule_price": True,
        "entry_rule": "first post-signal XSHG session with high >= canonical trigger; entry_price=canonical trigger",
        "exit_rule": "sellable sessions only; low <= stop or high >= target at canonical rule price; same-bar both=AMBIGUOUS_SAME_BAR",
        "t1_rule": "entry day cannot exit; sellable_from=next XSHG session",
        "time_exit": False,
        "total_signals": len(rows),
        "signals_with_t1_opportunity": len(eligible_rows),
        "eligible_signals": len(eligible_rows),
        "triggered": len(triggered_rows),
        "entered": len(triggered_rows),
        "trigger_rate": round(len(triggered_rows) / len(eligible_rows) * 100.0, 6) if eligible_rows else None,
        "resolved_target": len(target_rows),
        "resolved_stop": len(stop_rows),
        "target_wins": len(target_rows),
        "stop_losses": len(stop_rows),
        "resolved_closed_trades": resolved_count,
        "confirmed_closed_count": resolved_count,
        "open_rule_trades": len(open_rows),
        "open_positions_count": len(open_rows),
        "open_positions": len(open_rows),
        "untriggered": len(untriggered_rows),
        "ambiguous": len(ambiguous_rows),
        "performance_data_incomplete": len(incomplete_rows),
        "strategy_config_errors": len(config_rows),
        "win_count": len(target_rows),
        "loss_count": len(stop_rows),
        "flat_count": 0,
        "win_rate": round(len(target_rows) / resolved_count * 100.0, 6) if resolved_count else None,
        "avg_return_pct": _mean_or_none(returns),
        "median_return_pct": _median_or_none(returns),
        "avg_win_pct": mean_win,
        "avg_loss_pct": mean_loss,
        "payoff_ratio": round(mean_win / abs(mean_loss), 6) if mean_win is not None and mean_loss not in (None, 0) else None,
        "profit_factor": round(positive_sum / abs(negative_sum), 6) if negative_sum < 0 else None,
        "expectancy_pct": _mean_or_none(returns),
        "avg_r": _mean_or_none(r_values),
        "median_r": _median_or_none(r_values),
        "expectancy_r": _mean_or_none(r_values),
        "target_exit_count": len(target_rows),
        "stop_exit_count": len(stop_rows),
        "time_exit_count": 0,
        "target_hit_rate": round(len(target_rows) / resolved_count * 100.0, 6) if resolved_count else None,
        "stop_hit_rate": round(len(stop_rows) / resolved_count * 100.0, 6) if resolved_count else None,
        "time_exit_rate": None,
        "avg_holding_sessions": _mean_or_none([row["holding_sessions"] for row in closed_rows]),
        "median_holding_sessions": _median_or_none([row["holding_sessions"] for row in closed_rows]),
        "avg_mfe_pct": _mean_or_none([row["mfe_pct"] for row in closed_rows]),
        "avg_mae_pct": _mean_or_none([row["mae_pct"] for row in closed_rows]),
        "median_mfe_pct": _median_or_none([row["mfe_pct"] for row in closed_rows]),
        "median_mae_pct": _median_or_none([row["mae_pct"] for row in closed_rows]),
        "open_mtm_avg_return_pct": _mean_or_none([row["mark_return_pct"] for row in open_rows]),
        "historical_data_source": source_labels[0] if len(source_labels) == 1 else ("MIXED_OR_PARTIAL" if source_labels else "NO_HISTORICAL_SOURCE"),
        "historical_provider_calls": cache_meta.get("provider_calls", 0),
        "historical_cache_hits": cache_meta.get("cache_hits", len(by_code) if isinstance(by_code, Mapping) else 0),
        "historical_symbols_loaded": len({
            row["code"]
            for row in rows
            if row["status"] != RULE_STATUS_NOT_YET_ELIGIBLE
            and row.get("historical_data_status") == "COMPLETE"
        }),
        "closed_trades": closed_rows,
        "open_position_rows": open_rows,
        "ambiguous_rows": ambiguous_rows,
        "untriggered_rows": untriggered_rows,
        "performance_data_incomplete_rows": incomplete_rows,
        "config_error_rows": config_rows,
        "excluded_rows": [
            row for row in rows
            if row not in closed_rows and row not in open_rows
        ],
        "all_rows": rows,
    }


def load_strategy_rule_historical_ohlc(
    canonical_watchlists: Any,
    as_of_date: date | datetime | str,
    *,
    paths: DataPaths | None = None,
    calendar: TradingCalendar | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Read or temporarily reconstruct daily K-lines for rule performance.

    The default local behavior is unchanged: the existing immutable T-close
    K-line capture is the only historical source, and a missing bar is a
    performance data gap.  Cloud production explicitly enables the
    ``ASHARE_EPHEMERAL_RULE_PERFORMANCE_RECONSTRUCTION`` switch.  In that
    mode, missing symbols are read through the existing HiThink adapter into
    memory only; no raw response, bar, tracker observation, or
    prospective input is persisted.
    """

    resolver = paths or PATHS
    cal = calendar or default_calendar()
    report_date = parse_date(as_of_date)
    signals = _canonical_rule_signals(canonical_watchlists, report_date)
    eligible_codes = sorted({
        str(signal.get("code", ""))
        for signal in signals
        if _rule_sessions_after(parse_date(signal["date"]), report_date, cal)
    })
    bars_by_code: dict[str, list[dict[str, Any]]] = {}
    provenance_by_code: dict[str, Any] = {}
    cache_hits = 0
    cache_misses = 0
    errors: list[str] = []
    try:
        from live_acquisition import (
            ALLOW_TENCENT_KLINE_FALLBACK,
            DEFAULT_STOCK_BAR_COUNT,
            HiThinkClient,
            TCloseEvidenceStore,
            _resolve_market_bars,
            _history_capture_spec,
            _load_captured_market_bars,
        )
    except Exception as exc:
        errors.append(f"historical cache adapter unavailable: {type(exc).__name__}")
        DEFAULT_STOCK_BAR_COUNT = 260
        ALLOW_TENCENT_KLINE_FALLBACK = False
        HiThinkClient = None  # type: ignore[assignment]
        TCloseEvidenceStore = None  # type: ignore[assignment]
        _resolve_market_bars = None  # type: ignore[assignment]
        _history_capture_spec = None  # type: ignore[assignment]
        _load_captured_market_bars = None  # type: ignore[assignment]

    ephemeral_enabled = os.environ.get(
        EPHEMERAL_RULE_PERFORMANCE_RECONSTRUCTION_ENV, ""
    ).strip().lower() in {"1", "true", "yes"}
    ephemeral_client: Any | None = None
    provider_calls = 0
    if ephemeral_enabled and eligible_codes:
        if HiThinkClient is None or _resolve_market_bars is None:
            raise TrackerSchemaError(
                f"{EPHEMERAL_RULE_PERFORMANCE_RECONSTRUCTION}: "
                "provider adapter unavailable"
            )
        try:
            from requests import get as request_get

            ephemeral_client = HiThinkClient(capture_store=None)
        except Exception as exc:
            raise TrackerSchemaError(
                f"{EPHEMERAL_RULE_PERFORMANCE_RECONSTRUCTION}: "
                f"provider client unavailable: {type(exc).__name__}: {exc}"
            ) from exc

    evidence_base = resolver.root / "t_close_evidence"
    root_candidates = [evidence_base, evidence_base / report_date.strftime("%Y%m%d")]
    seen_roots: set[Path] = set()
    unique_roots: list[Path] = []
    for root in root_candidates:
        if root not in seen_roots:
            seen_roots.add(root)
            unique_roots.append(root)
    root_candidates = unique_roots
    for code in eligible_codes:
        loaded = False
        last_error: str | None = None
        if TCloseEvidenceStore is not None and _history_capture_spec is not None and _load_captured_market_bars is not None:
            logical_identity, thscode, _start_ms, _end_ms = _history_capture_spec(
                code,
                requested_count=DEFAULT_STOCK_BAR_COUNT,
                as_of_date=report_date.isoformat(),
                index=False,
            )
            for root in root_candidates:
                if not root.exists():
                    continue
                store = TCloseEvidenceStore(root, report_date)
                try:
                    result = _load_captured_market_bars(
                        store,
                        logical_identity,
                        thscode,
                        minimum_acceptable_history=1,
                        as_of_date=report_date.isoformat(),
                        require_last_bar_date=False,
                    )
                except Exception as exc:
                    last_error = f"{type(exc).__name__}: {str(exc)[:240]}"
                    break
                if result is None:
                    continue
                bars, resolution = result
                record = store.latest("hithink_kline")
                metadata = dict(record.metadata) if record is not None else {}
                bars_by_code[code] = bars
                provenance_by_code[code] = {
                    "status": "COMPLETE",
                    "provider": resolution.get("provider"),
                    "source": resolution.get("source"),
                    "source_identity": resolution.get("source"),
                    "provider_version": metadata.get("provider_version"),
                    "adjustment_mode": resolution.get("adjustment_mode"),
                    "selection": resolution.get("selection"),
                    "target_date": metadata.get("target_date", report_date.isoformat()),
                    "effective_trading_date": metadata.get("effective_trading_date"),
                    "logical_component_identity": logical_identity,
                    "file_sha256": metadata.get("file_sha256"),
                    "code_git_sha": metadata.get("code_git_sha"),
                    "cache": "T_CLOSE_IMMUTABLE_KLINE_CAPTURE",
                }
                cache_hits += 1
                loaded = True
                break
        if not loaded and ephemeral_enabled:
            assert ephemeral_client is not None
            assert _resolve_market_bars is not None
            try:
                bars, resolution = _resolve_market_bars(
                    ephemeral_client,
                    code,
                    requested_count=DEFAULT_STOCK_BAR_COUNT,
                    minimum_acceptable_history=1,
                    as_of_date=report_date.isoformat(),
                    timeout=15.0,
                    request_get=request_get,
                    retries=3,
                    index=False,
                    allow_tencent_fallback=ALLOW_TENCENT_KLINE_FALLBACK,
                    allow_stale_as_of=False,
                )
            except Exception as exc:
                raise TrackerSchemaError(
                    f"{EPHEMERAL_RULE_PERFORMANCE_RECONSTRUCTION}: "
                    f"historical bars unavailable for {code}: "
                    f"{type(exc).__name__}: {exc}"
                ) from exc
            bars_by_code[code] = bars
            provenance_by_code[code] = {
                "status": "COMPLETE",
                "source": EPHEMERAL_RULE_PERFORMANCE_RECONSTRUCTION,
                "source_identity": resolution.get("source"),
                "provider_source": resolution.get("source"),
                "provider": resolution.get("provider"),
                "adjustment_mode": resolution.get("adjustment_mode"),
                "selection": resolution.get("selection"),
                "target_date": report_date.isoformat(),
                "read_only": True,
                "persisted": False,
                "bars_persisted": False,
                "prospective_tracker_mutated": False,
                "cache": EPHEMERAL_RULE_PERFORMANCE_RECONSTRUCTION,
                "provenance_contract": EPHEMERAL_RULE_PERFORMANCE_RECONSTRUCTION,
            }
            provider_calls += 1
            loaded = True
        if not loaded:
            cache_misses += 1
            provenance_by_code[code] = {
                "status": "MISSING_OR_INVALID",
                "source": "T_CLOSE_IMMUTABLE_KLINE_CAPTURE",
                "reason": last_error or "no matching immutable daily K-line capture",
            }
            if last_error:
                errors.append(f"{code}: {last_error}")
    return bars_by_code, {
        "by_code": provenance_by_code,
        "__meta__": {
            "source": (
                EPHEMERAL_RULE_PERFORMANCE_RECONSTRUCTION
                if ephemeral_enabled
                else "T_CLOSE_IMMUTABLE_KLINE_CAPTURE"
            ),
            "provider_calls": provider_calls,
            "cache_hits": cache_hits,
            "cache_misses": cache_misses,
            "errors": errors,
            "as_of_date": report_date.isoformat(),
            "read_only": True,
            "bars_persisted": False,
            "prospective_tracker_mutated": False,
        },
    }


def _trade_row(signal: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "signal_id": signal.get("signal_id"),
        "signal_date": signal.get("date"),
        "code": signal.get("code"),
        "name": signal.get("name"),
        "entry_date": state.get("entry_date"),
        "entry_price": state.get("entry_price"),
        "sellable_from": state.get("sellable_from"),
        "exit_date": state.get("exit_date"),
        "exit_price": state.get("exit_price"),
        "exit_reason": state.get("exit_reason"),
        "realized_return_pct": state.get("realized_return_pct"),
        "realized_r": state.get("realized_r"),
        "holding_sessions": state.get("holding_sessions"),
        "mfe_pct": state.get("mfe_pct"),
        "mae_pct": state.get("mae_pct"),
        "latest_observation_date": state.get("latest_observation_date"),
        "latest_mark_price": state.get("latest_mark_price"),
        "unrealized_return_pct": state.get("unrealized_return_pct"),
        "unrealized_r": state.get("unrealized_r"),
        "status": state.get("status"),
        "execution_verification_status": state.get("execution_verification_status"),
        "execution_verification_reason": state.get("execution_verification_reason"),
        "return_basis": state.get("return_basis", RETURN_BASIS_GROSS),
    }


def build_trade_performance_summary(
    tracker: Mapping[str, Any],
    as_of_date: date | datetime | str,
    calendar: TradingCalendar | None = None,
) -> dict[str, Any]:
    """Build confirmed T+1 trade metrics from a strict as-of local replay."""

    cal = calendar or default_calendar()
    report_date = parse_date(as_of_date)
    if isinstance(tracker, dict):
        _validate_tracker(tracker)
    raw_signals = tracker.get("signals", {}) if isinstance(tracker, Mapping) else {}
    signals = [
        signal for signal in raw_signals.values()
        if isinstance(signal, Mapping)
        and signal.get("strategy_version") == CURRENT_PROSPECTIVE_STRATEGY
        and parse_date(signal["date"]) <= report_date
    ]
    signals.sort(key=lambda signal: (str(signal.get("date")), str(signal.get("signal_id"))))

    state_rows: list[tuple[Mapping[str, Any], dict[str, Any], bool]] = []
    for signal in signals:
        state = rebuild_execution_state_from_observations(signal, calendar=cal, as_of=report_date)
        first_execution = _next_session_after(parse_date(signal["date"]), cal)
        mature = first_execution <= report_date
        state_rows.append((signal, state, mature))

    execution_verified = sum(
        state.get("execution_verification_status") == EXECUTION_VERIFIED
        for _signal, state, _mature in state_rows
    )
    execution_unverified = sum(
        state.get("execution_verification_status") == UNVERIFIED_MISSING_EXECUTION_OBSERVATION
        for _signal, state, mature in state_rows
        if mature
    )
    execution_pending = sum(
        state.get("execution_verification_status") == EXECUTION_T_PLUS_1_PENDING
        for _signal, state, _mature in state_rows
    )
    observation_period_signals = sum(mature for _signal, _state, mature in state_rows)
    eligible_rows = [
        (signal, state) for signal, state, mature in state_rows
        if mature and state.get("execution_verification_status") == EXECUTION_VERIFIED
    ]
    entered_rows = [
        (signal, state) for signal, state, mature in state_rows
        if mature and state.get("entry_date") is not None
    ]
    closed_rows = [
        (signal, state) for signal, state, mature in state_rows
        if mature
        and state.get("execution_verification_status") == EXECUTION_VERIFIED
        and state.get("exit_price") is not None
        and isinstance(state.get("realized_return_pct"), (int, float))
        and state.get("exit_reason") != EXIT_REASON_AMBIGUOUS
    ]
    open_rows = [
        (signal, state) for signal, state, mature in state_rows
        if mature
        and state.get("execution_verification_status") == EXECUTION_VERIFIED
        and state.get("status") == "triggered"
        and state.get("entry_date") is not None
        and state.get("exit_date") is None
    ]
    ambiguous_rows = [
        (signal, state) for signal, state, mature in state_rows
        if mature and state.get("exit_reason") == EXIT_REASON_AMBIGUOUS
    ]
    untriggered_expired_rows = [
        (signal, state) for signal, state, mature in state_rows
        if mature and state.get("exit_reason") == EXIT_REASON_EXPIRED_UNTRIGGERED
    ]

    closed_returns = [state.get("realized_return_pct") for _signal, state in closed_rows]
    closed_r = [state.get("realized_r") for _signal, state in closed_rows]
    positive_returns = [value for value in _numeric_values(closed_returns) if value > 0]
    negative_returns = [value for value in _numeric_values(closed_returns) if value < 0]
    flat_count = sum(value == 0 for value in _numeric_values(closed_returns))
    average_win = _mean_or_none(positive_returns)
    average_loss = _mean_or_none(negative_returns)
    negative_sum = sum(negative_returns)
    positive_sum = sum(positive_returns)
    confirmed_count = len(closed_rows)
    payoff_ratio = (
        round(average_win / abs(average_loss), 6)
        if average_win is not None and average_loss is not None and average_loss != 0
        else None
    )
    profit_factor = round(positive_sum / abs(negative_sum), 6) if negative_sum < 0 else None
    holding_values = [state.get("holding_sessions") for _signal, state in closed_rows]
    mfe_rows = [
        state for _signal, state, mature in state_rows
        if mature
        and state.get("execution_verification_status") == EXECUTION_VERIFIED
        and state.get("entry_date") is not None
        and state.get("exit_reason") != EXIT_REASON_AMBIGUOUS
        and _as_number(state.get("mfe_pct")) is not None
        and _as_number(state.get("mae_pct")) is not None
    ]
    target_reasons = {EXIT_REASON_TARGET, EXIT_REASON_TARGET_GAP}
    stop_reasons = {EXIT_REASON_STOP, EXIT_REASON_STOP_GAP}
    time_reasons = {EXIT_REASON_TIME, EXIT_REASON_TIME_DEFERRED_T1}
    target_exit_count = sum(state.get("exit_reason") in target_reasons for _signal, state in closed_rows)
    stop_exit_count = sum(state.get("exit_reason") in stop_reasons for _signal, state in closed_rows)
    time_exit_count = sum(state.get("exit_reason") in time_reasons for _signal, state in closed_rows)
    open_mtm = [state.get("unrealized_return_pct") for _signal, state in open_rows]

    excluded_rows: list[dict[str, Any]] = []
    for signal, state, mature in state_rows:
        if not mature:
            reason = state.get("execution_verification_status") or EXECUTION_T_PLUS_1_PENDING
        elif state.get("execution_verification_status") != EXECUTION_VERIFIED:
            reason = state.get("execution_verification_status") or UNVERIFIED_MISSING_EXECUTION_OBSERVATION
        elif state.get("exit_reason") == EXIT_REASON_AMBIGUOUS:
            reason = EXIT_REASON_AMBIGUOUS
        elif state.get("exit_reason") == EXIT_REASON_EXPIRED_UNTRIGGERED:
            reason = EXIT_REASON_EXPIRED_UNTRIGGERED
        elif state.get("status") == "pending":
            reason = "UNTRIGGERED_ACTIVE"
        else:
            reason = "NOT_A_CONFIRMED_CLOSED_TRADE"
        if (signal, state) not in closed_rows and (signal, state) not in open_rows:
            row = _trade_row(signal, state)
            row["reason"] = reason
            excluded_rows.append(row)

    trigger_rate = round(len([row for row in entered_rows if row[1].get("execution_verification_status") == EXECUTION_VERIFIED]) / len(eligible_rows) * 100.0, 6) if eligible_rows else None
    win_count = sum(value > 0 for value in _numeric_values(closed_returns))
    loss_count = sum(value < 0 for value in _numeric_values(closed_returns))
    return {
        "as_of_date": report_date.isoformat(),
        "strategy": CURRENT_PROSPECTIVE_STRATEGY,
        "execution_model": EXECUTION_MODEL_DAILY_OHLC_T1_V1,
        "return_basis": RETURN_BASIS_GROSS,
        "sample_small": confirmed_count < 10,
        "total_signals": len(signals),
        "observation_period_signals": observation_period_signals,
        "eligible_signals": len(eligible_rows),
        "execution_verified": execution_verified,
        "execution_unverified": execution_unverified,
        "execution_pending": execution_pending,
        "entered": len(entered_rows),
        "untriggered_expired": len(untriggered_expired_rows),
        "open_positions": len(open_rows),
        "ambiguous": len(ambiguous_rows),
        "unverified": execution_unverified,
        "trigger_rate": trigger_rate,
        "confirmed_closed_count": confirmed_count,
        "win_count": win_count,
        "loss_count": loss_count,
        "flat_count": flat_count,
        "win_rate": round(win_count / confirmed_count * 100.0, 6) if confirmed_count else None,
        "avg_return_pct": _mean_or_none(closed_returns),
        "median_return_pct": _median_or_none(closed_returns),
        "avg_win_pct": average_win,
        "avg_loss_pct": average_loss,
        "payoff_ratio": payoff_ratio,
        "profit_factor": profit_factor,
        "expectancy_pct": _mean_or_none(closed_returns),
        "avg_r": _mean_or_none(closed_r),
        "median_r": _median_or_none(closed_r),
        "expectancy_r": _mean_or_none(closed_r),
        "target_exit_count": target_exit_count,
        "stop_exit_count": stop_exit_count,
        "time_exit_count": time_exit_count,
        "target_hit_rate": round(target_exit_count / confirmed_count * 100.0, 6) if confirmed_count else None,
        "stop_hit_rate": round(stop_exit_count / confirmed_count * 100.0, 6) if confirmed_count else None,
        "time_exit_rate": round(time_exit_count / confirmed_count * 100.0, 6) if confirmed_count else None,
        "avg_holding_sessions": _mean_or_none(holding_values),
        "median_holding_sessions": _median_or_none(holding_values),
        "avg_mfe_pct": _mean_or_none([state.get("mfe_pct") for state in mfe_rows]),
        "avg_mae_pct": _mean_or_none([state.get("mae_pct") for state in mfe_rows]),
        "median_mfe_pct": _median_or_none([state.get("mfe_pct") for state in mfe_rows]),
        "median_mae_pct": _median_or_none([state.get("mae_pct") for state in mfe_rows]),
        "open_positions_count": len(open_rows),
        "open_mtm_avg_return_pct": _mean_or_none(open_mtm),
        "closed_trades": [_trade_row(signal, state) for signal, state in closed_rows],
        "open_position_rows": [_trade_row(signal, state) for signal, state in open_rows],
        "excluded_rows": excluded_rows,
    }


def _apply_execution_bar(
    signal: dict[str, Any],
    quote: dict[str, Any],
    today_date: date,
    calendar: TradingCalendar,
    *,
    source_mode: str = SOURCE_MODE_LIVE_DAILY_TRACKER_QUOTE,
    provenance: dict[str, Any] | None = None,
) -> int:
    """Append one quote, then replay the complete stored path under T+1."""

    if signal["status"] not in ("pending", "triggered"):
        return 0
    changed = int(_append_observation(
        signal,
        quote,
        source_mode=source_mode,
        provenance=provenance,
    ))
    state = rebuild_execution_state_from_observations(signal, calendar=calendar, as_of=today_date)
    changed += _apply_rebuilt_execution_state(signal, state)
    return changed


def expected_review_set(
    tracker: dict[str, Any],
    report_date: date | datetime | str,
    calendar: TradingCalendar | None = None,
) -> dict[str, Any]:
    """Freeze the execution and fixed-horizon obligations before a daily update."""

    _validate_tracker(tracker)
    cal = calendar or default_calendar()
    report_date_text = parse_date(report_date).isoformat()
    report_day = parse_date(report_date_text)
    execution_signal_ids: list[str] = []
    horizon_point_ids: list[str] = []
    horizon_signal_ids: list[str] = []
    for signal_id, signal in tracker["signals"].items():
        if not is_current_prospective_signal(signal):
            continue
        signal_day = parse_date(signal["date"])
        points = _ensure_review_points(signal, cal)
        if signal_day < report_day and signal.get("status") in ("pending", "triggered"):
            execution_signal_ids.append(signal_id)
        for point in points.values():
            if point.get("scheduled_date") == report_date_text:
                horizon_point_ids.append(str(point["snapshot_id"]))
                horizon_signal_ids.append(signal_id)
    return {
        "report_date": report_date_text,
        "execution_signal_ids": sorted(execution_signal_ids),
        "horizon_point_ids": sorted(horizon_point_ids),
        "horizon_signal_ids": sorted(set(horizon_signal_ids)),
    }


def verify_review_coverage(
    tracker: dict[str, Any],
    report_date: date | datetime | str,
    *,
    expected: dict[str, Any] | None = None,
    failure_reason: str | None = None,
    calendar: TradingCalendar | None = None,
) -> dict[str, Any]:
    """Verify that every pre-update obligation has a same-date result."""

    _validate_tracker(tracker)
    cal = calendar or default_calendar()
    report_date_text = parse_date(report_date).isoformat()
    expected = expected or expected_review_set(tracker, report_date_text, cal)
    signals = tracker["signals"]
    execution_captured: list[str] = []
    execution_missing: list[str] = []
    for signal_id in expected.get("execution_signal_ids", []):
        signal = signals.get(signal_id, {})
        observations = signal.get("observations", []) if isinstance(signal, dict) else []
        captured = any(
            isinstance(observation, dict) and observation.get("date") == report_date_text
            for observation in observations
        )
        (execution_captured if captured else execution_missing).append(signal_id)

    horizon_captured: list[str] = []
    horizon_missing: list[dict[str, Any]] = []
    for point_id in expected.get("horizon_point_ids", []):
        point: dict[str, Any] | None = None
        signal_id = None
        for candidate_id, signal in signals.items():
            if not isinstance(signal, dict):
                continue
            for candidate in (signal.get("review_points") or {}).values():
                if isinstance(candidate, dict) and candidate.get("snapshot_id") == point_id:
                    point = candidate
                    signal_id = candidate_id
                    break
            if point is not None:
                break
        captured = bool(
            point
            and point.get("status") == REVIEW_POINT_CAPTURED
            and point.get("quote_date") == report_date_text
        )
        acceptable_failure = bool(
            point
            and point.get("status") == REVIEW_POINT_NOT_CAPTURED
            and isinstance(point.get("reason"), str)
            and point.get("reason", "").strip()
        )
        if captured:
            horizon_captured.append(point_id)
        else:
            horizon_missing.append({
                "snapshot_id": point_id,
                "signal_id": signal_id,
                "reason": (point or {}).get("reason") if point else None,
                "failure_recorded": acceptable_failure,
            })

    missing = bool(execution_missing or horizon_missing)
    return {
        "status": REVIEW_OBSERVATION_INCOMPLETE if missing else "READY",
        "report_date": report_date_text,
        "failure_reason": failure_reason if failure_reason else (
            REVIEW_OBSERVATION_INCOMPLETE if missing else None
        ),
        "execution_expected": len(expected.get("execution_signal_ids", [])),
        "execution_captured": len(execution_captured),
        "execution_missing": len(execution_missing),
        "execution_expected_signal_ids": list(expected.get("execution_signal_ids", [])),
        "execution_captured_signal_ids": execution_captured,
        "execution_missing_signal_ids": execution_missing,
        "horizon_expected": len(expected.get("horizon_point_ids", [])),
        "horizon_captured": len(horizon_captured),
        "horizon_missing": len(horizon_missing),
        "horizon_expected_point_ids": list(expected.get("horizon_point_ids", [])),
        "horizon_captured_point_ids": horizon_captured,
        "horizon_missing_points": horizon_missing,
        "horizon_expected_signal_ids": list(expected.get("horizon_signal_ids", [])),
    }


def run_daily_review(
    tracker: dict[str, Any],
    quotes: dict[str, dict[str, Any]] | None = None,
    today: date | datetime | str | None = None,
    calendar: TradingCalendar | None = None,
) -> tuple[int, dict[str, Any]]:
    """Run one update under the fail-soft execution/horizon completeness guard."""

    cal = calendar or default_calendar()
    report_date = parse_date(today or datetime.now().date())
    expected = expected_review_set(tracker, report_date, cal)
    try:
        changed = update(tracker, quotes=quotes, today=report_date, calendar=cal)
    except Exception as exc:
        _mark_expected_horizon_failures(tracker, expected)
        coverage = verify_review_coverage(
            tracker,
            report_date,
            expected=expected,
            failure_reason=f"{type(exc).__name__}: {exc}",
            calendar=cal,
        )
        tracker["review_coverage"] = coverage
        tracker["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        raise
    coverage = verify_review_coverage(tracker, report_date, expected=expected, calendar=cal)
    tracker["review_coverage"] = coverage
    return changed, coverage


def update(
    tracker: dict[str, Any],
    quotes: dict[str, dict[str, Any]] | None = None,
    today: date | datetime | str | None = None,
    calendar: TradingCalendar | None = None,
) -> int:
    """Update signals and due XSHG review points with validated quote data."""

    _validate_tracker(tracker)
    cal = calendar or default_calendar()

    if today is None and quotes:
        dates = {quote.get("quote_date") for quote in quotes.values()}
        if len(dates) != 1 or None in dates:
            raise QuoteDataError("injected quotes must have exactly one quote_date")
        today = next(iter(dates))
    today_date = parse_date(today or datetime.now().date())
    if not cal.is_trading_day(today_date):
        raise CalendarUnavailable(f"{today_date} is not an XSHG trading session")

    signals = [s for s in tracker["signals"].values() if is_current_prospective_signal(s)]
    for signal in signals:
        if parse_date(signal['date']) >= today_date:
            continue
        _ensure_review_points(signal, cal)
    due_or_active = [
        signal
        for signal in signals
        if parse_date(signal['date']) < today_date
        and (signal["status"] in ("pending", "triggered")
        or any(
            point["status"] == REVIEW_POINT_PENDING
            and today_date >= parse_date(point["scheduled_date"])
            for point in signal["review_points"].values()
        ))
    ]
    if not due_or_active:
        return 0
    codes = list(dict.fromkeys(signal["code"] for signal in due_or_active))
    if quotes is None:
        quotes = fetch_quotes(codes, expected_date=today_date)
    else:
        _validate_tracker_quotes(
            quotes,
            expected_codes=codes,
            expected_date=today_date,
        )

    changed = 0
    for signal in due_or_active:
        quote = quotes[signal["code"]]
        if signal["status"] in ("pending", "triggered"):
            changed += _apply_execution_bar(signal, quote, today_date, cal)
        changed += _capture_review_points(signal, quote, today_date, cal)
    tracker["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return changed


def _review_point_text(
    signal: dict[str, Any],
    label: str,
    as_of_date: date | datetime | str | None = None,
) -> str:
    point = signal.get("review_points", {}).get(label)
    if not isinstance(point, dict):
        return "未初始化"
    status = point.get("status", REVIEW_POINT_PENDING)
    if status == REVIEW_POINT_CAPTURED:
        return_pct = point.get("return_pct")
        return_text = f"{return_pct:.2f}%" if isinstance(return_pct, (int, float)) else "UNVERIFIED"
        path_status = point.get("path_status") or point.get("signal_status") or "UNVERIFIED"
        source_mode = point.get("source_mode") or "UNVERIFIED"
        reason = point.get("reason")
        reason_text = f" / reason={reason}" if reason else ""
        return (
            f"已采集 {point.get('quote_date')} / return={return_text} / path={path_status}"
            f" / source={source_mode}{reason_text}"
        )
    scheduled_date = point.get("review_trading_date") or point.get("scheduled_date")
    if status == REVIEW_POINT_NOT_CAPTURED:
        return "MISSING_HISTORICAL_OBSERVATION（节点未采集，不回填）"
    if (
        as_of_date is not None
        and scheduled_date is not None
        and parse_date(as_of_date) >= parse_date(scheduled_date)
    ):
        return "MISSING_HISTORICAL_OBSERVATION（节点未采集，不回填）"
    return f"待 {point.get('scheduled_date', '—')}"


def _performance_markdown(
    performance: Mapping[str, Any],
    audit_performance: Mapping[str, Any] | None = None,
) -> list[str]:
    audit_performance = audit_performance or {}
    def value(key: str, *, percent: bool = False) -> str:
        item = performance.get(key)
        if item is None:
            return f"— / sample={performance.get('resolved_closed_trades', 0)}"
        return f"{float(item):.2f}%" if percent else f"{float(item):.2f}"

    return [
        "## 三、策略规则绩效 · 交易绩效",
        f"> performance model：{performance.get('performance_model')}；收益口径：{performance.get('return_basis')}。",
        "> 理论规则价模拟：严格按 canonical trigger 入场、stop / target 规则价退出；买入当日不可卖出，遵守 A 股 T+1；不代表真实成交。",
        f"> 总信号 **{performance.get('total_signals', 0)}**；T+1 可机会 **{performance.get('signals_with_t1_opportunity', 0)}**；"
        f"已触发 **{performance.get('triggered', 0)}**；触发率 **{value('trigger_rate', percent=True)}**。",
        f"> resolved target **{performance.get('resolved_target', 0)}**；resolved stop **{performance.get('resolved_stop', 0)}**；"
        f"已结案 **{performance.get('resolved_closed_trades', 0)}**；当前持仓 **{performance.get('open_rule_trades', 0)}**；"
        f"untriggered **{performance.get('untriggered', 0)}**；ambiguous **{performance.get('ambiguous', 0)}**。",
        f"> 胜率 **{value('win_rate', percent=True)}**；平均收益 **{value('avg_return_pct', percent=True)}**；"
        f"平均盈利 **{value('avg_win_pct', percent=True)}**；平均亏损 **{value('avg_loss_pct', percent=True)}**；"
        f"盈亏比 **{value('payoff_ratio')}**；Profit Factor **{value('profit_factor')}**。",
        f"> 期望收益/笔 **{value('expectancy_pct', percent=True)}**；平均 R **{value('avg_r')}**；"
        f"平均持有交易日 **{value('avg_holding_sessions')}**；平均 MFE **{value('avg_mfe_pct', percent=True)}**；"
        f"平均 MAE **{value('avg_mae_pct', percent=True)}**。",
        f"> 策略绩效历史行情缺失 **{performance.get('performance_data_incomplete', 0)}**；"
        f"prospective observation 缺失 **{audit_performance.get('execution_unverified', 0)}**（仅数据质量审计，不是策略绩效准入门槛）。",
        "> confirmed metrics 不包含 OPEN、UNTRIGGERED、AMBIGUOUS_SAME_BAR、PERFORMANCE_DATA_INCOMPLETE；"
        "T+3/T+5/T+10 仍是 fixed-horizon snapshot research，不是 realized trade P&L。",
        "",
    ]


def report(
    tracker: dict[str, Any],
    calendar: TradingCalendar | None = None,
    as_of: date | datetime | str | None = None,
) -> str:
    """Render the formal signal-level review cadence without outcome overclaiming."""

    _validate_tracker(tracker)
    cal = calendar or default_calendar()
    as_of_date = parse_date(as_of or datetime.now().date())
    signals = [s for s in tracker["signals"].values() if is_current_prospective_signal(s)]
    for signal in signals:
        _ensure_review_points(signal, cal)
    total = len(signals)
    triggered = [s for s in signals if s["status"] in ("triggered", "win", "loss", "AMBIGUOUS_SAME_BAR")]
    closed = [s for s in signals if s["status"] in ("win", "loss", "expired")]
    pending = [s for s in signals if s["status"] in ("pending", "triggered")]
    ambiguous = [s for s in signals if s["status"] == "AMBIGUOUS_SAME_BAR"]
    canonical_watchlists = current_prospective_watchlists(PATHS)
    historical_ohlc, historical_provenance = load_strategy_rule_historical_ohlc(
        canonical_watchlists,
        as_of_date,
        paths=PATHS,
        calendar=cal,
    )
    performance = build_strategy_rule_performance(
        canonical_watchlists,
        historical_ohlc,
        as_of_date,
        calendar=cal,
        historical_provenance=historical_provenance,
    )
    audit_performance = build_trade_performance_summary(tracker, as_of_date, calendar=cal)

    lines = [
        "# 信号复盘 · XSHG 交易日节点",
        "",
        f"> 数据更新：{tracker.get('updated', '—')}　|　signal-level 信号：{total}",
        "> 每交易日由 tracker 维护状态；T+3 为短线评价，T+5 为 PRIMARY REVIEW "
        "HORIZON（主评价），T+10 为延伸观察并结案。",
        "> 节点按信号日 T 后第 3/5/10 个真实 XSHG session 计算，不按自然日；历史节点不做行情回填。",
        "> fixed-horizon snapshot 与 execution/path result 分离；缺少真实节点 observation "
        "或确认入场价时标记 MISSING_HISTORICAL_OBSERVATION / UNVERIFIED。",
        "",
        "## 一、节点状态",
    ]
    coverage = tracker.get("review_coverage")
    if isinstance(coverage, dict):
        guard_label = (
            REVIEW_OBSERVATION_INCOMPLETE
            if coverage.get("status") == REVIEW_OBSERVATION_INCOMPLETE
            else "REVIEW_COVERAGE"
        )
        lines.insert(
            4,
            f"> {guard_label} guard：execution "
            f"expected={coverage.get('execution_expected', 0)} / captured={coverage.get('execution_captured', 0)} / "
            f"missing={coverage.get('execution_missing', 0)}；horizon "
            f"expected={coverage.get('horizon_expected', 0)} / captured={coverage.get('horizon_captured', 0)} / "
            f"missing={coverage.get('horizon_missing', 0)}；status={coverage.get('status', 'UNVERIFIED')}",
        )
    for label, _ in REVIEW_HORIZONS:
        counts = {status: 0 for status in (REVIEW_POINT_PENDING, REVIEW_POINT_CAPTURED, REVIEW_POINT_NOT_CAPTURED)}
        for signal in signals:
            point = signal.get("review_points", {}).get(label, {})
            counts[point.get("status", REVIEW_POINT_PENDING)] = counts.get(
                point.get("status", REVIEW_POINT_PENDING), 0
            ) + 1
        lines.append(
            f"- **{label}**：已采集 {counts[REVIEW_POINT_CAPTURED]}，待到期 {counts[REVIEW_POINT_PENDING]}，"
            f"未采集 {counts[REVIEW_POINT_NOT_CAPTURED]}。"
        )

    lines += [
        "",
        "## 二、信号状态摘要",
        f"- 累计入库：**{total}** 个；已触发：**{len(triggered)}** 个。",
        f"- 已结案：**{len(closed)}** 个；仍在跟踪：**{len(pending)}** 个。",
        f"- same-bar 歧义：**{len(ambiguous)}** 个；保持 `AMBIGUOUS_SAME_BAR`，不猜测盘中顺序。",
        "",
        *_performance_markdown(performance, audit_performance),
        "## 四、逐信号节点明细",
        "| 信号ID | 策略版本 | 信号日 T | 代码 | setup | 触发价 | 止损 | 目标 | T+3 | T+5 | T+10 | 当前状态 | 结案日 |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for signal in sorted(signals, key=lambda item: (item["date"], item["signal_id"])):
        lines.append(
            f"| {signal['signal_id']} | {signal['strategy_version']} | {signal['date']} | {signal['code']} | "
            f"{signal['setup']} | {signal.get('trigger')} | {signal.get('stop')} | {signal.get('target')} | "
            f"{_review_point_text(signal, 'T+3', as_of_date)} | "
            f"{_review_point_text(signal, 'T+5', as_of_date)} | "
            f"{_review_point_text(signal, 'T+10', as_of_date)} | "
            f"{signal['status']} | {signal.get('close_date') or ''} |"
        )
    if not signals:
        lines.append("*暂无样本*")
    lines += ["", "---", "*量化信号，仅供研究参考；本报告不构成策略有效性或生产结论。*"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        nargs="?",
        default="all",
        choices=["ingest", "update", "report", "recover", "all"],
    )
    parser.add_argument("--date", default=None, help="report/update date, YYYY-MM-DD or YYYYMMDD")
    parser.add_argument("--evidence-root", type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    tracker: dict[str, Any] | None = None
    try:
        tracker = load_tracker()
        if args.action == "recover":
            resolver = PATHS
            plan = cleanup_current_tracker(tracker, resolver)
            if plan["REMOVE_FROM_CURRENT_TRACKER"]:
                print("[cleanup] " + json.dumps(plan, ensure_ascii=False, sort_keys=True), flush=True)
            print(f"[ingest] 新增入库 {ingest(tracker, paths=resolver)} 个信号", flush=True)
            from exact_date_review_recovery import recover_exact_date_review

            result = recover_exact_date_review(
                tracker,
                paths=resolver,
                evidence_root=args.evidence_root or (resolver.root / "t_close_evidence"),
                target_date=args.date or "2026-09-08",
            )
            save_tracker(tracker)
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0

        plan = cleanup_current_tracker(tracker)
        if plan['REMOVE_FROM_CURRENT_TRACKER']:
            print('[cleanup] ' + json.dumps(plan, ensure_ascii=False, sort_keys=True), flush=True)
        if args.action in ("ingest", "all"):
            print(f"[ingest] 新增入库 {ingest(tracker)} 个信号", flush=True)
        if args.action in ("update", "all"):
            changed, coverage = run_daily_review(tracker, today=args.date)
            print(
                f"[update] 状态变更 {changed} 个；"
                f"execution={coverage['execution_captured']}/{coverage['execution_expected']}，"
                f"horizon={coverage['horizon_captured']}/{coverage['horizon_expected']}，"
                f"status={coverage['status']}",
                flush=True,
            )
        text = None
        if args.action in ("report", "all"):
            text = report(tracker, as_of=args.date)
            print(text)
            REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
            REPORT_FILE.write_text(text, encoding="utf-8")
            print(f"\n报表已存：{REPORT_FILE}", flush=True)
        save_tracker(tracker)
    except (OSError, ValueError, CalendarUnavailable, WatchlistSchemaError, QuoteDataError, TrackerSchemaError) as exc:
        if tracker is not None and tracker.get("review_coverage"):
            try:
                save_tracker(tracker)
            except OSError:
                pass
        print(f"数据完整性失败: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
