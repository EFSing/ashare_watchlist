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
import warnings
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from data_paths import DataPaths
from tencent_quotes import QuoteDataError, fetch_quotes, validate_quotes
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
SKIP_LEGACY_OR_OUT_OF_SCOPE_WATCHLIST = "SKIP_LEGACY_OR_OUT_OF_SCOPE_WATCHLIST"
SOURCE_MODE_LIVE_DAILY_TRACKER_QUOTE = "LIVE_DAILY_TRACKER_QUOTE"
SOURCE_MODE_EXACT_DATE_IMMUTABLE_EVIDENCE_RECOVERY_V1 = (
    "EXACT_DATE_IMMUTABLE_EVIDENCE_RECOVERY_V1"
)
PATH_UNVERIFIED_MISSING_PRIOR_EXECUTION_PATH = "UNVERIFIED_MISSING_PRIOR_EXECUTION_PATH"
CONFIRMED_ENTRY_UNAVAILABLE = "CONFIRMED_ENTRY_UNAVAILABLE"
REVIEW_OBSERVATION_INCOMPLETE = "REVIEW_OBSERVATION_INCOMPLETE"


class TrackerSchemaError(ValueError):
    """The tracker is neither the supported v2 model nor migratable v1."""


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
        "entry_price": None,
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


def _apply_execution_bar(
    signal: dict[str, Any],
    quote: dict[str, Any],
    today_date: date,
    calendar: TradingCalendar,
    *,
    source_mode: str = SOURCE_MODE_LIVE_DAILY_TRACKER_QUOTE,
    provenance: dict[str, Any] | None = None,
) -> int:
    """Apply one dated quote to the execution path using existing semantics."""

    if signal["status"] not in ("pending", "triggered"):
        return 0
    changed = 0
    list_date = parse_date(signal["date"])
    days_tracked = trading_days_after(list_date, today_date, calendar=calendar)
    if signal.get("days_tracked") != days_tracked:
        signal["days_tracked"] = days_tracked
        changed += 1
    changed += int(_append_observation(
        signal,
        quote,
        source_mode=source_mode,
        provenance=provenance,
    ))
    decision = classify_signal_bar(
        status=signal["status"],
        trigger=signal.get("trigger"),
        stop=signal.get("stop"),
        target=signal.get("target"),
        high=quote.get("high"),
        low=quote.get("low"),
        price=quote.get("price"),
    )
    today_text = today_date.isoformat()
    next_status = decision["status"]
    if next_status == "triggered" and signal["status"] == "pending":
        signal["status"] = "triggered"
        signal["entry_price"] = signal.get("trigger")
        signal["first_trigger_date"] = today_text
        changed += 1
        if days_tracked >= TRACK_DAYS:
            signal["status"] = "expired"
            signal["result_price"] = quote["price"]
            signal["close_date"] = today_text
            changed += 1
    elif next_status in ("win", "loss", "AMBIGUOUS_SAME_BAR"):
        signal["status"] = next_status
        signal["close_date"] = today_text
        signal["ambiguity_reason"] = decision.get("reason") if next_status == "AMBIGUOUS_SAME_BAR" else None
        if next_status == "win":
            signal["result_price"] = signal.get("target")
        elif next_status == "loss":
            signal["result_price"] = signal.get("stop")
        changed += 1
    elif days_tracked >= TRACK_DAYS:
        signal["status"] = "expired"
        signal["close_date"] = today_text
        if next_status == "triggered":
            signal["result_price"] = quote["price"]
        changed += 1
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
        validate_quotes(quotes, expected_codes=codes, expected_date=today_date)

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
        "## 三、逐信号节点明细",
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
