#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
"""Render one self-contained offline daily close bundle.

The renderer is deliberately a read-only consumer of the canonical watchlist
and the signal-level tracker.  It never evaluates a strategy, fetches quotes,
or reconstructs a historical path from a current quote.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from data_paths import DataPaths
from track_perf import (
    REVIEW_HORIZONS,
    REVIEW_POINT_CAPTURED,
    REVIEW_POINT_NOT_CAPTURED,
    REVIEW_OBSERVATION_INCOMPLETE,
    EXECUTION_MODEL_DAILY_OHLC_T1_V1,
    EXECUTION_T_PLUS_1_PENDING,
    UNVERIFIED_MISSING_EXECUTION_OBSERVATION,
    EXIT_REASON_AMBIGUOUS,
    build_trade_performance_summary,
    load_tracker,
    parse_date,
    review_date,
    current_prospective_tracker,
    is_current_prospective_signal,
    CURRENT_PROSPECTIVE_STRATEGY,
    PATH_UNVERIFIED_MISSING_PRIOR_EXECUTION_PATH,
    SOURCE_MODE_EXACT_DATE_IMMUTABLE_EVIDENCE_RECOVERY_V1,
)
from trading_calendar import TradingCalendar, default_calendar, previous_trading_day
from watchlist_schema import load_watchlist


_BJT = timezone(timedelta(hours=8))
_FROZEN_STRATEGY = "B_BREAKOUT_RETEST_LEGACY_V1_1"
_UNVERIFIED = "UNVERIFIED"
_MISSING = "MISSING_HISTORICAL_OBSERVATION"
_REVIEW_FAILURE = "REVIEW_FAILED"
_T1_PENDING = "T_PLUS_1_OBSERVATION_PENDING"
_CLOUD_VERIFIED = "CLOUD_CHECKPOINT_VERIFIED"
_HORIZON_OFFSETS = dict(REVIEW_HORIZONS)


@dataclass(frozen=True)
class ReportModel:
    """Deterministic data model used by the HTML renderer."""

    metadata: dict[str, Any]
    watchlist_rows: list[dict[str, Any]]
    daily_summary: dict[str, int | str]
    review_sections: dict[str, list[dict[str, Any]]]
    active_signals: list[dict[str, Any]]
    previous_signals: list[dict[str, Any]]
    closed_today: list[dict[str, Any]]
    anomalies: list[str]
    summary_text: str
    review_status: str
    review_coverage: dict[str, Any] | None = None
    overview: dict[str, Any] | None = None
    data_quality: list[dict[str, Any]] | None = None
    rolling_review: dict[str, Any] | None = None
    trade_performance: dict[str, Any] | None = None


def _normalize_date(value: date | datetime | str) -> str:
    return parse_date(value).isoformat()


def _date_token(value: str) -> str:
    return value.replace("-", "")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dedupe(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _text(value: Any, fallback: str = "—") -> str:
    if value is None or value == "":
        return fallback
    return str(value)


def _number(value: Any, digits: int = 2, fallback: str = "—") -> str:
    if value is None or value == "":
        return fallback
    try:
        number = float(value)
    except (TypeError, ValueError):
        return _text(value, fallback)
    return f"{number:.{digits}f}"


def _percent(value: Any, signed: bool = False) -> str:
    if value is None or value == "":
        return _UNVERIFIED
    try:
        number = float(value)
    except (TypeError, ValueError):
        return _UNVERIFIED
    prefix = "+" if signed and number > 0 else ""
    return f"{prefix}{number:.2f}%"


def _distance_to_trigger(trigger: Any, close: Any) -> float | None:
    try:
        trigger_value = float(trigger)
        close_value = float(close)
    except (TypeError, ValueError):
        return None
    if close_value == 0:
        return None
    return (trigger_value / close_value - 1.0) * 100.0


def _status_text(status: Any) -> str:
    mapping = {
        "pending": "PENDING",
        "triggered": "TRIGGERED",
        "win": "WIN / TARGET_HIT",
        "loss": "LOSS / STOP_HIT",
        "expired": "EXPIRED",
        "AMBIGUOUS_SAME_BAR": "AMBIGUOUS_SAME_BAR",
        EXECUTION_MODEL_DAILY_OHLC_T1_V1: EXECUTION_MODEL_DAILY_OHLC_T1_V1,
        EXECUTION_T_PLUS_1_PENDING: EXECUTION_T_PLUS_1_PENDING,
        UNVERIFIED_MISSING_EXECUTION_OBSERVATION: UNVERIFIED_MISSING_EXECUTION_OBSERVATION,
        "STOP_GAP": "STOP_GAP",
        "TARGET_GAP": "TARGET_GAP",
        "STOP": "STOP",
        "TARGET": "TARGET",
        "TIME_EXIT": "TIME_EXIT",
        "TIME_EXIT_PENDING_T1": "TIME_EXIT_PENDING_T1",
        "TIME_EXIT_T1_DEFERRED": "TIME_EXIT_T1_DEFERRED",
        "EXPIRED_UNTRIGGERED": "EXPIRED_UNTRIGGERED",
        "UNTRIGGERED_ACTIVE": "未触发",
        "VERIFIED": "VERIFIED",
        PATH_UNVERIFIED_MISSING_PRIOR_EXECUTION_PATH: "UNVERIFIED_MISSING_PRIOR_EXECUTION_PATH",
        REVIEW_POINT_CAPTURED: "CAPTURED",
        REVIEW_POINT_NOT_CAPTURED: _MISSING,
    }
    if status is None or status == "":
        return _UNVERIFIED
    return mapping.get(str(status), str(status))


def _status_class(status: Any) -> str:
    value = str(status or "").upper()
    if "MISSING" in value or "UNVERIFIED" in value or "FAILED" in value:
        return "missing"
    if "AMBIGUOUS" in value or value in {"PENDING", "TRIGGERED", "EXPIRED"}:
        return "warning"
    if "STOP" in value or value == "LOSS":
        return "loss"
    if "TARGET" in value or value in {"WIN", "CAPTURED"}:
        return "target"
    return "normal"


def _package_metadata(paths: DataPaths, list_date: str) -> tuple[str, str]:
    """Return the package file SHA and fingerprint without parsing the huge package."""

    package_dir = paths.root / "prospective_inputs" / _date_token(list_date)
    candidates = sorted(
        path
        for path in package_dir.glob(f"{list_date}_*.json")
        if path.is_file()
    ) if package_dir.exists() else []
    if len(candidates) != 1:
        if not candidates:
            return "UNAVAILABLE", "UNAVAILABLE"
        return f"UNVERIFIED ({len(candidates)} packages)", "UNVERIFIED"

    package = candidates[0]
    stem_prefix = f"{list_date}_"
    fingerprint = package.stem[len(stem_prefix):] if package.stem.startswith(stem_prefix) else "UNVERIFIED"
    return _sha256_file(package), fingerprint or "UNVERIFIED"


def _acquisition_status(paths: DataPaths, list_date: str) -> str:
    """Read only the existing evidence sidecars to expose capture completeness."""

    evidence_root = paths.root / "t_close_evidence" / _date_token(list_date)
    sidecars = sorted(evidence_root.rglob("*.json")) if evidence_root.exists() else []
    if not sidecars:
        return _UNVERIFIED
    for sidecar in sidecars:
        raw_path = sidecar.with_suffix(".raw")
        if not raw_path.is_file():
            return _UNVERIFIED
        try:
            metadata = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return _UNVERIFIED
        if not isinstance(metadata, Mapping):
            return _UNVERIFIED
        if metadata.get("target_date") != list_date or metadata.get("completeness_status") != "COMPLETE":
            return _UNVERIFIED
    return "COMPLETE"


def _cloud_checkpoint_status(paths: DataPaths, list_date: str) -> str:
    """Expose verified cloud state only when the existing manifest says so."""

    manifest_path = paths.root / "checkpoints" / f"daily_checkpoint_{_date_token(list_date)}.json"
    if not manifest_path.is_file():
        return _UNVERIFIED
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return _UNVERIFIED
    if not isinstance(manifest, Mapping) or manifest.get("list_date") != list_date:
        return _UNVERIFIED
    status = str(manifest.get("verification_status") or "")
    if status in {_CLOUD_VERIFIED, "UPLOADED_AND_VERIFIED", "NO_OP_ALREADY_VERIFIED"}:
        return "VERIFIED"
    if status == "LOCAL_INPUTS_VERIFIED":
        return "LOCAL_INPUTS_VERIFIED"
    return _UNVERIFIED


def _point_for_signal(
    signal: Mapping[str, Any],
    horizon: str,
    calendar: TradingCalendar,
) -> dict[str, Any]:
    points = signal.get("review_points")
    raw = points.get(horizon) if isinstance(points, Mapping) else None
    point = dict(raw) if isinstance(raw, Mapping) else {}
    signal_date = _normalize_date(signal["date"])
    scheduled = point.get("review_trading_date") or point.get("scheduled_date")
    if scheduled is None:
        scheduled = review_date(signal_date, _HORIZON_OFFSETS[horizon], calendar)
    scheduled = _normalize_date(scheduled)
    point.setdefault("signal_id", signal.get("signal_id"))
    point.setdefault("signal_date", signal_date)
    point.setdefault("horizon", horizon)
    point.setdefault("review_trading_date", scheduled)
    point.setdefault("scheduled_date", scheduled)
    point.setdefault("status", "PENDING")
    return point


def _observation_for_date(signal: Mapping[str, Any], target_date: str) -> Mapping[str, Any] | None:
    observations = signal.get("observations")
    if not isinstance(observations, list):
        return None
    for observation in reversed(observations):
        if isinstance(observation, Mapping) and observation.get("date") == target_date:
            return observation
    return None


def _load_review_tracker(
    paths: DataPaths,
    supplied_failure: str | None,
) -> tuple[dict[str, Any] | None, list[str]]:
    failures: list[str] = []
    tracker_path = paths.perf_tracker_file()
    if supplied_failure:
        failures.append(f"{_REVIEW_FAILURE}: {supplied_failure}")
    if not tracker_path.exists():
        failures.append(f"{_REVIEW_FAILURE}: tracker file missing: {tracker_path}")
        return None, failures
    try:
        return current_prospective_tracker(load_tracker(tracker_path), paths), failures
    except Exception as exc:  # renderer must preserve the canonical list on review failure
        failures.append(f"{_REVIEW_FAILURE}: {type(exc).__name__}: {exc}")
        return None, failures


def _watchlist_rows(
    watchlist: Mapping[str, Any],
    tracker: Mapping[str, Any] | None,
    report_date: str,
) -> list[dict[str, Any]]:
    signals = tracker.get("signals", {}) if isinstance(tracker, Mapping) else {}
    signals = signals if isinstance(signals, Mapping) else {}
    candidates = sorted(
        watchlist["candidates"],
        key=lambda item: (-float(item.get("score", float("-inf"))), str(item.get("code", ""))),
    )
    rows: list[dict[str, Any]] = []
    for rank, candidate in enumerate(candidates, start=1):
        signal = signals.get(candidate.get("signal_id"))
        is_new_signal = str(watchlist.get("date")) == report_date
        # A historical/current-date report must not expose a state derived
        # from observations after the report date.  New-list rows explicitly
        # wait for T+1 even when the operational tracker has since advanced.
        status = "pending" if is_new_signal else signal.get("status") if isinstance(signal, Mapping) else None
        observation_status = _T1_PENDING if is_new_signal else _UNVERIFIED
        status_explanation = "今日新信号，等待下一交易日观察" if is_new_signal else "状态待核验"
        if not is_new_signal and status is not None:
            observation_status = "已记录"
            status_explanation = "按已有 tracker 状态展示"
        rows.append(
            {
                "rank": rank,
                "code": candidate.get("code"),
                "name": candidate.get("name"),
                "score": candidate.get("score"),
                "close": candidate.get("price"),
                "trigger": candidate.get("trigger"),
                "stop": candidate.get("stop"),
                "target": candidate.get("target"),
                "rr": candidate.get("rr"),
                "distance_to_trigger_pct": _distance_to_trigger(candidate.get("trigger"), candidate.get("price")),
                "setup": candidate.get("setup", candidate.get("buy_type")),
                "sector": candidate.get("sector", "-"),
                "status": _status_text(status),
                "observation_status": observation_status,
                "status_explanation": status_explanation,
                "signal_id": candidate.get("signal_id"),
            }
        )
    return rows


def _review_rows(
    tracker: Mapping[str, Any] | None,
    report_date: str,
    calendar: TradingCalendar,
) -> tuple[dict[str, list[dict[str, Any]]], list[str], int]:
    sections = {label: [] for label, _ in REVIEW_HORIZONS}
    issues: list[str] = []
    missing_count = 0
    signals = tracker.get("signals", {}) if isinstance(tracker, Mapping) else {}
    signals = signals if isinstance(signals, Mapping) else {}
    for signal in signals.values():
        if not isinstance(signal, Mapping):
            continue
        for horizon, _offset in REVIEW_HORIZONS:
            point = _point_for_signal(signal, horizon, calendar)
            scheduled = _normalize_date(point["review_trading_date"])
            status = str(point.get("status") or "PENDING")
            if parse_date(scheduled) <= parse_date(report_date) and status != REVIEW_POINT_CAPTURED:
                missing_count += 1
                issues.append(_MISSING)
            if scheduled != report_date:
                continue
            captured = status == REVIEW_POINT_CAPTURED
            return_value = point.get("return_pct") if captured else None
            path_status = point.get("path_status") if captured else None
            snapshot_status = _status_text(status) if captured else _MISSING
            source_mode = point.get("source_mode")
            if source_mode is None and isinstance(point.get("provenance"), Mapping):
                source_mode = point["provenance"].get("source_mode")
            if status != REVIEW_POINT_CAPTURED:
                snapshot_source = "数据缺失"
            elif source_mode == SOURCE_MODE_EXACT_DATE_IMMUTABLE_EVIDENCE_RECOVERY_V1:
                snapshot_source = "已恢复（不可变证据）"
            else:
                snapshot_source = "已记录"
            if captured and return_value is None:
                issues.append(_UNVERIFIED)
            if status == REVIEW_POINT_NOT_CAPTURED:
                issues.append(_MISSING)
            sections[horizon].append(
                {
                    "code": signal.get("code"),
                    "name": signal.get("name"),
                    "signal_id": signal.get("signal_id"),
                    "list_date": signal.get("date"),
                    "review_date": scheduled,
                    "horizon_return": _percent(return_value, signed=True),
                    "path_status": _status_text(path_status),
                    "snapshot_status": snapshot_status,
                    "node_open": point.get("open"),
                    "node_high": point.get("high"),
                    "node_low": point.get("low"),
                    "node_close": point.get("price"),
                    "snapshot_source": snapshot_source,
                    "source_mode": source_mode,
                }
            )
    for rows in sections.values():
        rows.sort(key=lambda row: (str(row.get("code", "")), str(row.get("signal_id", ""))))
    return sections, issues, missing_count


def _daily_collections(tracker, report_date, previous_date, paths, failures):
    """Join yesterday's complete identities; use only dated tracker evidence.

    Earlier signals closed today remain visible in their own section. They must
    not disappear merely because today's tracker update made them terminal.
    """
    signals = dict(tracker.get('signals', {})) if tracker else {}
    previous_path = paths.watchlist_file(previous_date)
    if previous_path.exists():
        try:
            previous = load_watchlist(previous_path)
        except Exception as exc:
            failures.append(f'{_REVIEW_FAILURE}: previous watchlist: {type(exc).__name__}: {exc}')
            previous = {'candidates': []}
        for candidate in previous['candidates']:
            if (is_current_prospective_signal(previous)
                    and candidate['strategy_version'] == CURRENT_PROSPECTIVE_STRATEGY):
                signals.setdefault(candidate['signal_id'], {**candidate, 'date': previous_date})
    groups = ([], [], [])
    for signal in signals.values():
        list_date = _normalize_date(signal['date'])
        if list_date >= report_date:
            continue
        observation = _observation_for_date(signal, report_date)
        raw_status = signal.get('status')
        # A later terminal/entry state cannot be asserted for an earlier report.
        future_state = any(signal.get(key) and signal[key] > report_date
                           for key in ('close_date', 'first_trigger_date'))
        verified = observation is not None and not future_state
        status = raw_status if verified else _MISSING
        closed_today = verified and signal.get('close_date') == report_date
        ambiguity_reason = signal.get('ambiguity_reason')
        if verified and raw_status == 'AMBIGUOUS_SAME_BAR':
            observation_status = 'AMBIGUOUS_SAME_BAR'
            status_explanation = f"同日顺序不明；{ambiguity_reason}" if ambiguity_reason else '同日顺序不明'
        elif not verified:
            observation_status = _MISSING
            status_explanation = '历史 observation 缺失或状态未核验；保持 UNVERIFIED'
        else:
            observation_status = 'CAPTURED'
            status_explanation = '正常已记录' if raw_status == 'pending' else f"正常已记录；canonical status={raw_status}"
        row = {
            'code': signal.get('code'), 'name': signal.get('name'),
            'signal_id': signal.get('signal_id'), 'list_date': list_date,
            'score': signal.get('score'), 'original_trigger': signal.get('trigger'),
            'today_open': observation.get('open') if observation else None,
            'today_high': observation.get('high') if observation else None,
            'today_low': observation.get('low') if observation else None,
            'today_close': observation.get('price') if observation else None,
            'daily_change_pct': observation.get('change_pct') if observation else None,
            'observation_source_mode': observation.get('source_mode') if observation else None,
            'source_mode': observation.get('source_mode') if observation else None,
            'observation_source': (
                '已恢复（不可变证据）'
                if observation and (
                    observation.get('source_mode') == SOURCE_MODE_EXACT_DATE_IMMUTABLE_EVIDENCE_RECOVERY_V1
                    or (
                        isinstance(observation.get('provenance'), Mapping)
                        and observation['provenance'].get('source_mode') == SOURCE_MODE_EXACT_DATE_IMMUTABLE_EVIDENCE_RECOVERY_V1
                    )
                )
                else '已记录' if observation else '数据缺失'
            ),
            'close_vs_trigger_pct': (
                (observation['price'] / signal['trigger'] - 1) * 100
                if observation and observation.get('price') is not None and signal.get('trigger') else None
            ),
            'path_status': status, 'raw_status': raw_status, 'observed': verified,
            'observation_status': observation_status,
            'status_explanation': status_explanation,
            'new_triggered': verified and signal.get('first_trigger_date') == report_date,
            'closed_today': closed_today,
            'note': ('缺少当日真实记录或当日状态未核验' if not verified else
                     '日内先后顺序无法确认' if raw_status == 'AMBIGUOUS_SAME_BAR' else
                     '今日结束跟踪' if closed_today else '按当日真实记录展示'),
        }
        if row['observation_source'] == '已恢复（不可变证据）' and verified:
            row['note'] = '当日不可变证据恢复；按原有路径规则展示'
        if list_date == previous_date:
            groups[0].append(row)
        elif raw_status in {'pending', 'triggered'}:
            groups[1].append(row)
        elif closed_today:
            groups[2].append(row)
    def sort_key(row: Mapping[str, Any]) -> tuple[int, float, str, str]:
        attention = (
            0 if row.get('raw_status') == 'AMBIGUOUS_SAME_BAR' or not row.get('observed')
            else 1 if row.get('raw_status') == 'triggered'
            else 2
        )
        try:
            score = -float(row.get('score'))
        except (TypeError, ValueError):
            score = float('inf')
        return attention, score, str(row.get('code', '')), str(row.get('signal_id', ''))

    for rows in groups:
        rows.sort(key=sort_key)
    return groups


def build_report_model(
    report_date: date | datetime | str,
    *,
    paths: DataPaths | None = None,
    review_failure: str | None = None,
    generated_at: datetime | None = None,
    calendar: TradingCalendar | None = None,
) -> ReportModel:
    """Load canonical inputs and build a report without writing any files."""

    resolver = paths or DataPaths.from_env()
    normalized_date = _normalize_date(report_date)
    watchlist_path = resolver.watchlist_file(normalized_date)
    watchlist_bytes = watchlist_path.read_bytes()
    watchlist = load_watchlist(watchlist_path)
    if (not is_current_prospective_signal(watchlist)
            or any(c['strategy_version'] != CURRENT_PROSPECTIVE_STRATEGY for c in watchlist['candidates'])):
        raise ValueError('SKIP_LEGACY_OR_OUT_OF_SCOPE_WATCHLIST: report requires current prospective canonical')
    if watchlist["date"] != normalized_date:
        raise ValueError(f"watchlist date {watchlist['date']} != report date {normalized_date}")

    cal = calendar or default_calendar()
    tracker, review_failures = _load_review_tracker(resolver, review_failure)
    performance_tracker = tracker if tracker is not None else {"version": 2, "signals": {}}
    trade_performance = build_trade_performance_summary(
        performance_tracker,
        normalized_date,
        calendar=cal,
    )
    review_sections, review_issues, missing_count = _review_rows(tracker, normalized_date, cal)
    review_coverage = (
        tracker.get('review_coverage')
        if isinstance(tracker, Mapping)
        and isinstance(tracker.get('review_coverage'), Mapping)
        and tracker['review_coverage'].get('report_date') == normalized_date
        else None
    )
    previous_date = _normalize_date(previous_trading_day(normalized_date, cal))
    previous_signals, active_signals, closed_today = _daily_collections(
        tracker, normalized_date, previous_date, resolver, review_failures
    )
    watchlist_rows = _watchlist_rows(watchlist, tracker, normalized_date)

    anomalies = list(review_failures)
    anomalies.extend(review_issues)
    daily_rows = previous_signals + active_signals + closed_today
    if any(row['path_status'] == _MISSING for row in daily_rows):
        anomalies.append(_MISSING)
    if tracker is not None:
        for signal in tracker.get("signals", {}).values():
            if not isinstance(signal, Mapping):
                continue
            if signal.get("status") == "AMBIGUOUS_SAME_BAR" or signal.get("ambiguity_reason"):
                anomalies.append("AMBIGUOUS_SAME_BAR")
    if review_coverage and review_coverage.get('status') == REVIEW_OBSERVATION_INCOMPLETE:
        anomalies.append(REVIEW_OBSERVATION_INCOMPLETE)
    anomalies = _dedupe(anomalies)
    display_anomalies = anomalies or ["NONE"]

    package_sha, generation_fingerprint = _package_metadata(resolver, normalized_date)
    earliest_execution = review_date(normalized_date, 1, cal)
    generated = generated_at or datetime.now(_BJT)
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=_BJT)
    generated = generated.astimezone(_BJT)
    if review_failures:
        review_status = _REVIEW_FAILURE
    elif review_coverage and review_coverage.get('status') == REVIEW_OBSERVATION_INCOMPLETE:
        review_status = REVIEW_OBSERVATION_INCOMPLETE
    else:
        review_status = "READY"
    previous_triggered = sum(row['raw_status'] == 'triggered' for row in previous_signals)
    previous_pending = sum(row['raw_status'] == 'pending' for row in previous_signals)
    previous_ambiguous = sum(row['raw_status'] == 'AMBIGUOUS_SAME_BAR' for row in previous_signals)
    today_t1_pending = sum(row.get('observation_status') == _T1_PENDING for row in watchlist_rows)
    unverified_count = review_issues.count(_UNVERIFIED)
    ambiguity_dates: dict[str, int] = {}
    historical_missing_dates: dict[str, int] = {}
    unverified_dates: dict[str, int] = {}
    if isinstance(tracker, Mapping):
        for signal in tracker.get("signals", {}).values():
            if not isinstance(signal, Mapping):
                continue
            if signal.get("status") == "AMBIGUOUS_SAME_BAR":
                signal_date = _normalize_date(signal.get("date"))
                ambiguity_dates[signal_date] = ambiguity_dates.get(signal_date, 0) + 1
            for point in (signal.get("review_points") or {}).values():
                if not isinstance(point, Mapping):
                    continue
                scheduled = point.get("review_trading_date") or point.get("scheduled_date")
                if not scheduled or parse_date(scheduled) > parse_date(normalized_date):
                    continue
                signal_date = _normalize_date(signal.get("date"))
                if point.get("status") == REVIEW_POINT_NOT_CAPTURED:
                    historical_missing_dates[signal_date] = historical_missing_dates.get(signal_date, 0) + 1
                elif point.get("status") == REVIEW_POINT_CAPTURED and point.get("return_pct") is None:
                    unverified_dates[signal_date] = unverified_dates.get(signal_date, 0) + 1
    acquisition_status = _acquisition_status(resolver, normalized_date)
    cloud_checkpoint_status = _cloud_checkpoint_status(resolver, normalized_date)
    quality_exception_count = (
        missing_count
        + unverified_count
        + sum(ambiguity_dates.values())
        + (1 if acquisition_status != "COMPLETE" else 0)
        + (1 if cloud_checkpoint_status != "VERIFIED" else 0)
        + sum(item != "NONE" for item in review_failures)
    )
    data_quality = [
        {
            "category": "历史节点缺失",
            "count": missing_count,
            "status": f"{_MISSING} / {_UNVERIFIED}",
            "reason": "节点未采集，不回填；保持历史路径 UNVERIFIED",
            "signal_dates": ", ".join(f"{d} ({n})" for d, n in sorted(historical_missing_dates.items())) or "—",
        },
        {
            "category": "收益待核验",
            "count": unverified_count,
            "status": _UNVERIFIED,
            "reason": "confirmed entry unavailable; return is unverified",
            "signal_dates": ", ".join(f"{d} ({n})" for d, n in sorted(unverified_dates.items())) or "—",
        },
        {
            "category": "同日顺序不明",
            "count": sum(ambiguity_dates.values()),
            "status": "AMBIGUOUS_SAME_BAR",
            "reason": "保留 fail-safe，不猜测日内先后顺序",
            "signal_dates": ", ".join(f"{d} ({n})" for d, n in sorted(ambiguity_dates.items())) or "—",
        },
        {
            "category": "今日新信号等待 T+1",
            "count": today_t1_pending,
            "status": _T1_PENDING,
            "reason": "正常状态：今日新信号尚未进入下一交易日 observation",
            "signal_dates": normalized_date if today_t1_pending else "—",
        },
        {
            "category": "acquisition",
            "count": 0 if acquisition_status == "COMPLETE" else 1,
            "status": acquisition_status,
            "reason": "T-close evidence sidecars complete" if acquisition_status == "COMPLETE" else "capture completeness is not verified",
            "signal_dates": normalized_date,
        },
        {
            "category": "cloud checkpoint",
            "count": 0 if cloud_checkpoint_status == "VERIFIED" else 1,
            "status": cloud_checkpoint_status,
            "reason": "dated checkpoint verified" if cloud_checkpoint_status == "VERIFIED" else "local manifest is not proof of remote cloud verification",
            "signal_dates": normalized_date,
        },
    ]
    summary = {
        'tracked': len(daily_rows),
        'active_signals': sum(row['raw_status'] in {'pending', 'triggered'} and row['observed'] for row in daily_rows),
        'new_triggered': sum(row['new_triggered'] for row in daily_rows),
        'target_hits': sum(row['closed_today'] and row['raw_status'] == 'win' for row in daily_rows),
        'stop_hits': sum(row['closed_today'] and row['raw_status'] == 'loss' for row in daily_rows),
        'ambiguous': sum(row['closed_today'] and row['raw_status'] == 'AMBIGUOUS_SAME_BAR' for row in daily_rows),
        'expired': sum(row['closed_today'] and row['raw_status'] == 'expired' for row in daily_rows),
        'daily_missing': sum(not row['observed'] for row in daily_rows),
        'missing_observations': missing_count,
        't3_count': len(review_sections['T+3']),
        't5_count': len(review_sections['T+5']),
        't10_count': len(review_sections['T+10']),
        'previous_total': len(previous_signals),
        'previous_triggered': previous_triggered,
        'previous_pending': previous_pending,
        'previous_ambiguous': previous_ambiguous,
        'today_t1_pending': today_t1_pending,
        'quality_exception_count': quality_exception_count,
    }
    summary_text = (
        f"昨日 {previous_date} 共 {previous_triggered + previous_pending + previous_ambiguous} 个信号："
        f"triggered {previous_triggered}、pending {previous_pending}、same-bar {previous_ambiguous}。"
        f"今日新信号 {today_t1_pending} 个，正常等待下一交易日 observation。"
        f"历史数据质量例外 {quality_exception_count} 个；"
        f"acquisition={acquisition_status}、review={review_status}、cloud={cloud_checkpoint_status}。"
        + (f"今日 T+5 PRIMARY 到期 {summary['t5_count']} 个。" if summary['t5_count'] else "今日无 T+5 PRIMARY 到期信号。")
    )
    if review_coverage and review_coverage.get('status') == REVIEW_OBSERVATION_INCOMPLETE:
        summary_text = (
            f"复盘数据不完整：execution expected={review_coverage.get('execution_expected', 0)}, "
            f"captured={review_coverage.get('execution_captured', 0)}, "
            f"missing={review_coverage.get('execution_missing', 0)}；horizon "
            f"expected={review_coverage.get('horizon_expected', 0)}, "
            f"captured={review_coverage.get('horizon_captured', 0)}, "
            f"missing={review_coverage.get('horizon_missing', 0)}。"
            + summary_text
        )
    metadata = {
        "list_date": normalized_date,
        "previous_date": previous_date,
        "review_date": normalized_date,
        "earliest_execution": earliest_execution,
        "strategy": watchlist.get("strategy_version", "UNVERIFIED"),
        "frozen_candidate": "YES" if watchlist.get("strategy_version") == _FROZEN_STRATEGY else "UNVERIFIED",
        "package_sha": package_sha,
        "generation_fingerprint": generation_fingerprint,
        "watchlist_sha": hashlib.sha256(watchlist_bytes).hexdigest(),
        "candidate_count": len(watchlist_rows),
        "report_generated_at": generated.isoformat(),
    }
    if review_coverage:
        metadata.update({
            "review_guard": review_coverage.get("status", "UNVERIFIED"),
            "execution_coverage": (
                f"expected={review_coverage.get('execution_expected', 0)};"
                f"captured={review_coverage.get('execution_captured', 0)};"
                f"missing={review_coverage.get('execution_missing', 0)}"
            ),
            "horizon_coverage": (
                f"expected={review_coverage.get('horizon_expected', 0)};"
                f"captured={review_coverage.get('horizon_captured', 0)};"
                f"missing={review_coverage.get('horizon_missing', 0)}"
            ),
        })
    if isinstance(tracker, Mapping) and isinstance(tracker.get('recovery_audit'), Mapping):
        recovery_audit = tracker['recovery_audit']
        metadata.update({
            "recovery_policy": recovery_audit.get("policy", "UNVERIFIED"),
            "recovery_evidence_root": recovery_audit.get("evidence_root", "UNVERIFIED"),
            "recovery_integrity": recovery_audit.get("integrity_status", "UNVERIFIED"),
            "recovery_provider_calls": recovery_audit.get("provider_calls", "UNVERIFIED"),
        })
    overview = {
        "t_close_date": normalized_date,
        "new_watchlist_count": len(watchlist_rows),
        "previous_signal_count": len(previous_signals),
        "triggered_count": previous_triggered,
        "pending_count": previous_pending,
        "ambiguous_count": previous_ambiguous,
        "quality_exception_count": quality_exception_count,
        "acquisition_status": acquisition_status,
        "review_status": review_status,
        "cloud_checkpoint_status": cloud_checkpoint_status,
    }
    rolling_review = {
        "status": review_coverage.get("status", _UNVERIFIED) if review_coverage else _UNVERIFIED,
        "strategy": metadata["strategy"],
        "execution_expected": review_coverage.get("execution_expected", 0) if review_coverage else 0,
        "execution_captured": review_coverage.get("execution_captured", 0) if review_coverage else 0,
        "execution_missing": review_coverage.get("execution_missing", 0) if review_coverage else 0,
        "horizon_expected": review_coverage.get("horizon_expected", 0) if review_coverage else 0,
        "horizon_captured": review_coverage.get("horizon_captured", 0) if review_coverage else 0,
        "horizon_missing": review_coverage.get("horizon_missing", 0) if review_coverage else 0,
        "unverified_excluded": unverified_count,
        "ambiguous_excluded": sum(ambiguity_dates.values()),
    }
    return ReportModel(
        metadata=metadata,
        watchlist_rows=watchlist_rows,
        daily_summary=summary,
        review_sections={label: list(rows) for label, rows in review_sections.items()},
        active_signals=active_signals,
        previous_signals=previous_signals,
        closed_today=closed_today,
        anomalies=display_anomalies,
        summary_text=summary_text,
        review_status=review_status,
        review_coverage=dict(review_coverage) if review_coverage else None,
        overview=overview,
        data_quality=data_quality,
        rolling_review=rolling_review,
        trade_performance=trade_performance,
    )


def _esc(value: Any) -> str:
    return html.escape(_text(value), quote=True)


def _display_status(value):
    return {
        'pending': '未触发', 'PENDING': '未触发',
        'triggered': '已触发', 'TRIGGERED': '已触发',
        'win': '目标达成', 'WIN / TARGET_HIT': '目标达成',
        'loss': '止损', 'LOSS / STOP_HIT': '止损',
        'expired': '已过期', 'EXPIRED': '已过期',
        'AMBIGUOUS_SAME_BAR': '同日顺序不明',
        PATH_UNVERIFIED_MISSING_PRIOR_EXECUTION_PATH: '路径未完整验证',
        'CAPTURED': '已记录', 'NOT_CAPTURED': '数据缺失',
        _T1_PENDING: '等待下一交易日观察', 'VERIFIED': 'VERIFIED',
        'COMPLETE': 'COMPLETE', 'LOCAL_INPUTS_VERIFIED': '本地输入已验证',
        _MISSING: '数据缺失', _UNVERIFIED: '待核验',
    }.get(value, value or '数据缺失')


def _ui_badge(value):
    return f'<span class="badge {_status_class(value)}">{_esc(_display_status(value))}</span>'


def _simple_table(headers, body, table_id=''):
    return (f'<div class="table-wrap"><table id="{table_id}"><thead><tr>'
            + ''.join(f'<th>{_esc(h)}</th>' for h in headers)
            + '</tr></thead><tbody>' + ''.join(body) + '</tbody></table></div>')


def _review_table(rows):
    body = []
    for row in rows:
        values = [_esc(row.get(k)) for k in ('code', 'name', 'list_date')]
        node_ohlc = row.get('node_ohlc')
        if node_ohlc is None:
            node_ohlc = (
                f"O={_number(row.get('node_open'))} "
                f"H={_number(row.get('node_high'))} "
                f"L={_number(row.get('node_low'))} "
                f"C={_number(row.get('node_close'))}"
                if any(row.get(key) is not None for key in ('node_open', 'node_high', 'node_low', 'node_close'))
                else _UNVERIFIED
            )
        values += [_esc(node_ohlc), _esc(row.get('horizon_return', _UNVERIFIED)),
                   _ui_badge(row.get('path_status')), _ui_badge(row.get('snapshot_status')),
                   _esc(row.get('snapshot_source', '已记录'))]
        body.append('<tr>' + ''.join(f'<td>{v}</td>' for v in values) + '</tr>')
    return _simple_table(('代码', '名称', '名单日期', '节点 O/H/L/C', '节点收益', '路径结果', '节点快照状态', '节点来源'), body)


def _position(distance):
    if distance is None:
        return '—'
    if distance < 0:
        return '已在 Trigger 上方'
    if abs(distance) <= 1:
        return '贴近 Trigger'
    return '等待触发'


def _watchlist_table(rows):
    body = []
    for row in rows:
        values = [_esc(row.get(k)) for k in ('rank', 'code', 'name', 'score')]
        values += [_esc(_number(row.get(k))) for k in ('close', 'trigger')]
        distance = row['distance_to_trigger_pct']
        values += [_esc(_percent(distance, signed=True) if distance is not None else '—')
                   + '<br><small>' + _esc(_position(distance)) + '</small>']
        values += [_esc(_number(row.get(k))) for k in ('stop', 'target', 'rr')]
        values += [_ui_badge(row.get('status')), _ui_badge(row.get('observation_status')),
                   _esc(row.get('status_explanation')), _esc(row.get('sector'))]
        search = ' '.join(str(row.get(k, '')) for k in ('code', 'name', 'sector')).lower()
        body.append(f'<tr data-search="{_esc(search)}">' + ''.join(f'<td>{v}</td>' for v in values) + '</tr>')
    return _simple_table(('排名', '代码', '名称', 'Score', '收盘', 'Trigger', '距 Trigger',
                          'Stop', 'Target', 'RR', '当前状态', '观察状态', '状态解释', '行业'), body, 'watchlist-table')


def _daily_table(rows):
    if not rows:
        return '<p class="note">暂无符合条件的记录。</p>'
    body = []
    for row in rows:
        values = [_esc(row.get(k)) for k in ('code', 'name', 'list_date', 'score')]
        values += [_esc(_number(row.get(k))) for k in
                   ('original_trigger', 'today_open', 'today_high', 'today_low', 'today_close')]
        values += [_esc(_percent(row.get('daily_change_pct'), signed=True))]
        values += [_esc(_percent(row['close_vs_trigger_pct'], signed=True)
                        if row['close_vs_trigger_pct'] is not None else '—')]
        values += [_ui_badge(row['path_status']), _ui_badge(row.get('observation_status')),
                   _esc(row.get('observation_source', '数据缺失')), _esc(row.get('status_explanation'))]
        body.append('<tr>' + ''.join(f'<td>{v}</td>' for v in values) + '</tr>')
    return _simple_table(('代码', '名称', '名单日期', 'Score', 'Trigger', '今日开盘',
                          '今日最高', '今日最低', '今日收盘', '当日涨跌', '收盘较 Trigger %',
                          'Trigger 状态', 'Observation 状态', '记录来源', '状态解释'), body)


def _quality_table(rows):
    body = []
    for row in rows:
        values = [
            _esc(row.get("category")),
            _esc(row.get("count")),
            _ui_badge(row.get("status")),
            _esc(row.get("reason")),
            _esc(row.get("signal_dates")),
        ]
        body.append("<tr>" + "".join(f"<td>{value}</td>" for value in values) + "</tr>")
    return _simple_table(("类别", "数量", "状态", "解释", "Signal date"), body)


def _rolling_review_html(review: Mapping[str, Any]) -> str:
    rows = [
        ("策略", review.get("strategy")),
        ("Review guard", review.get("status")),
        ("已验证 execution", f"{review.get('execution_captured', 0)} / {review.get('execution_expected', 0)}"),
        ("已验证 fixed horizon", f"{review.get('horizon_captured', 0)} / {review.get('horizon_expected', 0)}"),
        ("execution missing", review.get("execution_missing", 0)),
        ("horizon missing", review.get("horizon_missing", 0)),
        ("排除 UNVERIFIED", review.get("unverified_excluded", 0)),
        ("排除 same-bar", review.get("ambiguous_excluded", 0)),
    ]
    body = [f"<tr><td>{_esc(label)}</td><td>{_esc(value)}</td></tr>" for label, value in rows]
    return _simple_table(("现有正式计数", "值"), body)


def _performance_value(
    performance: Mapping[str, Any],
    key: str,
    *,
    percent: bool = False,
    signed: bool = False,
) -> str:
    value = performance.get(key)
    if value is None:
        sample = performance.get("confirmed_closed_count", 0)
        return f"N/A / sample={sample}" if sample == 0 else "N/A"
    if percent:
        return _percent(value, signed=signed)
    return _number(value)


def _performance_cards(performance: Mapping[str, Any]) -> str:
    cards = [
        ("可执行信号", performance.get("eligible_signals")),
        ("已进入观察期", performance.get("observation_period_signals")),
        ("已入场", performance.get("entered")),
        ("触发率", _performance_value(performance, "trigger_rate", percent=True, signed=True)),
        ("已确认结案", performance.get("confirmed_closed_count")),
        ("当前持仓", performance.get("open_positions_count")),
        ("胜率", _performance_value(performance, "win_rate", percent=True)),
        ("平均收益", _performance_value(performance, "avg_return_pct", percent=True, signed=True)),
        ("平均盈利", _performance_value(performance, "avg_win_pct", percent=True, signed=True)),
        ("平均亏损", _performance_value(performance, "avg_loss_pct", percent=True, signed=True)),
        ("盈亏比", _performance_value(performance, "payoff_ratio")),
        ("Profit Factor", _performance_value(performance, "profit_factor")),
        ("期望收益/笔", _performance_value(performance, "expectancy_pct", percent=True, signed=True)),
        ("平均 R", _performance_value(performance, "avg_r", signed=True)),
        ("平均持有交易日", _performance_value(performance, "avg_holding_sessions")),
        ("平均 MFE", _performance_value(performance, "avg_mfe_pct", percent=True, signed=True)),
        ("平均 MAE", _performance_value(performance, "avg_mae_pct", percent=True, signed=True)),
    ]
    return ''.join(
        f'<div class="card"><div class="card-label">{_esc(label)}</div>'
        f'<div class="card-value">{_esc(value)}</div></div>'
        for label, value in cards
    )


def _performance_detail_table(performance: Mapping[str, Any]) -> str:
    rows = [
        ("Median return", _performance_value(performance, "median_return_pct", percent=True, signed=True)),
        ("Median R", _performance_value(performance, "median_r", signed=True)),
        ("Target exits / hit rate", f'{_esc(performance.get("target_exit_count", 0))} / {_esc(_performance_value(performance, "target_hit_rate", percent=True))}'),
        ("Stop exits / hit rate", f'{_esc(performance.get("stop_exit_count", 0))} / {_esc(_performance_value(performance, "stop_hit_rate", percent=True))}'),
        ("Time exits / rate", f'{_esc(performance.get("time_exit_count", 0))} / {_esc(_performance_value(performance, "time_exit_rate", percent=True))}'),
        ("Median holding sessions", _performance_value(performance, "median_holding_sessions")),
        ("Median MFE", _performance_value(performance, "median_mfe_pct", percent=True, signed=True)),
        ("Median MAE", _performance_value(performance, "median_mae_pct", percent=True, signed=True)),
        ("Open MTM average", _performance_value(performance, "open_mtm_avg_return_pct", percent=True, signed=True)),
        ("Execution verified / unverified / T+1 pending",
         f'{_esc(performance.get("execution_verified", 0))} / '
         f'{_esc(performance.get("execution_unverified", 0))} / '
         f'{_esc(performance.get("execution_pending", 0))}'),
    ]
    body = [f"<tr><td>{_esc(label)}</td><td>{value if '<' in str(value) else _esc(value)}</td></tr>" for label, value in rows]
    return _simple_table(("详细交易绩效指标", "值"), body)


def _trade_closed_table(rows: list[Mapping[str, Any]]) -> str:
    headers = (
        "信号日", "代码", "名称", "入场日", "入场价", "可卖日", "出场日", "出场价",
        "出场原因", "毛收益 %", "R", "持有交易日", "MFE", "MAE",
    )
    if not rows:
        return _simple_table(headers, [f'<tr><td colspan="{len(headers)}">暂无已确认结案交易。</td></tr>'])
    body = []
    for row in rows:
        values = [_esc(row.get("signal_date")), _esc(row.get("code")), _esc(row.get("name")),
                  _esc(row.get("entry_date")), _esc(_number(row.get("entry_price"))),
                  _esc(row.get("sellable_from")), _esc(row.get("exit_date")),
                  _esc(_number(row.get("exit_price"))), _esc(row.get("exit_reason")),
                  _esc(_percent(row.get("realized_return_pct"), signed=True)),
                  _esc(_number(row.get("realized_r"))), _esc(_number(row.get("holding_sessions"))),
                  _esc(_percent(row.get("mfe_pct"), signed=True)), _esc(_percent(row.get("mae_pct"), signed=True))]
        body.append("<tr>" + "".join(f"<td>{value}</td>" for value in values) + "</tr>")
    return _simple_table(headers, body)


def _trade_open_table(rows: list[Mapping[str, Any]]) -> str:
    headers = (
        "信号日", "代码", "名称", "入场日", "入场价", "可卖日", "最新观察日", "最新收盘",
        "未实现 %", "未实现 R", "MFE", "MAE",
    )
    if not rows:
        return _simple_table(headers, [f'<tr><td colspan="{len(headers)}">暂无已核验当前持仓。</td></tr>'])
    body = []
    for row in rows:
        values = [_esc(row.get("signal_date")), _esc(row.get("code")), _esc(row.get("name")),
                  _esc(row.get("entry_date")), _esc(_number(row.get("entry_price"))),
                  _esc(row.get("sellable_from")), _esc(row.get("latest_observation_date")),
                  _esc(_number(row.get("latest_mark_price"))),
                  _esc(_percent(row.get("unrealized_return_pct"), signed=True)),
                  _esc(_number(row.get("unrealized_r"))),
                  _esc(_percent(row.get("mfe_pct"), signed=True)), _esc(_percent(row.get("mae_pct"), signed=True))]
        body.append("<tr>" + "".join(f"<td>{value}</td>" for value in values) + "</tr>")
    return _simple_table(headers, body)


def _trade_excluded_table(rows: list[Mapping[str, Any]]) -> str:
    headers = ("signal_id", "代码", "名称", "reason", "状态", "execution verification")
    if not rows:
        return _simple_table(headers, [f'<tr><td colspan="{len(headers)}">暂无排除或未核验记录。</td></tr>'])
    body = []
    for row in rows:
        values = [_esc(row.get("signal_id")), _esc(row.get("code")), _esc(row.get("name")),
                  _esc(row.get("reason")), _ui_badge(row.get("status")),
                  _ui_badge(row.get("execution_verification_status"))]
        body.append("<tr>" + "".join(f"<td>{value}</td>" for value in values) + "</tr>")
    return _simple_table(headers, body)


def _trade_performance_html(performance: Mapping[str, Any]) -> str:
    sample_label = "SAMPLE_SMALL" if performance.get("sample_small") else "SAMPLE_READY"
    closed_count = performance.get("confirmed_closed_count", 0)
    return (
        f'<p class="callout warning"><strong>{_esc(sample_label)}</strong>：'
        f'confirmed closed sample = {_esc(closed_count)}；数字仍展示，'
        f'但不足以代表稳定统计。口径：{_esc(performance.get("return_basis"))}。</p>'
        f'<div class="cards">{_performance_cards(performance)}</div>'
        f'<p class="note">样本漏斗：总信号 { _esc(performance.get("total_signals")) } · '
        f'已进入可执行观察期 { _esc(performance.get("observation_period_signals")) } · '
        f'execution-path verified 分母 { _esc(performance.get("eligible_signals")) } · '
        f'已入场 { _esc(performance.get("entered")) } · '
        f'未触发到期 { _esc(performance.get("untriggered_expired")) } · '
        f'当前持仓 { _esc(performance.get("open_positions_count")) } · '
        f'ambiguous { _esc(performance.get("ambiguous")) } · '
        f'unverified { _esc(performance.get("unverified")) }。</p>'
        '<p class="note">触发率分母只含已进入至少一个可执行 XSHG session 且 execution path verified 的信号；'
        'fixed-horizon T+3/T+5/T+10 是 snapshot research return，不是 realized trade P&amp;L。</p>'
        '<h3>指标明细</h3>'
        f'{_performance_detail_table(performance)}'
        '<h3>已结案交易</h3>'
        f'{_trade_closed_table(performance.get("closed_trades", []))}'
        '<h3>当前持仓</h3>'
        f'{_trade_open_table(performance.get("open_position_rows", []))}'
        '<h3>排除 / 未核验</h3>'
        f'{_trade_excluded_table(performance.get("excluded_rows", []))}'
    )


def render_html(model: ReportModel) -> str:
    """Render a self-contained UTF-8 HTML document."""

    metadata = model.metadata
    summary = model.daily_summary
    overview = model.overview or {}
    quality_rows = model.data_quality or []
    rolling_review = model.rolling_review or {}
    trade_performance = model.trade_performance or build_trade_performance_summary(
        {"version": 2, "signals": {}},
        metadata.get("review_date", date.today().isoformat()),
    )
    cards = [
        ('T-close 日期', overview.get('t_close_date', metadata['review_date'])),
        ('今日新名单', overview.get('new_watchlist_count', metadata['candidate_count'])),
        ('昨日信号', overview.get('previous_signal_count', 0)),
        ('昨日 triggered', overview.get('triggered_count', 0)),
        ('昨日 pending / 未触发', overview.get('pending_count', 0)),
        ('昨日 same-bar', overview.get('ambiguous_count', 0)),
        ('UNVERIFIED / 数据质量例外', overview.get('quality_exception_count', 0)),
        ('acquisition', overview.get('acquisition_status', _UNVERIFIED)),
        ('review', overview.get('review_status', _UNVERIFIED)),
        ('cloud checkpoint', overview.get('cloud_checkpoint_status', _UNVERIFIED)),
    ]
    card_html = ''.join(f'<div class="card"><div class="card-label">{label}</div>'
                        f'<div class="card-value">{_esc(value)}</div></div>' for label, value in cards)
    metadata_html = ''.join(f'<div class="meta-item"><span>{_esc(k)}</span>'
                            f'<strong>{_esc(v)}</strong></div>' for k, v in metadata.items())
    audit_rows = model.watchlist_rows + model.previous_signals + model.active_signals + model.closed_today
    audit_rows += [r for rows in model.review_sections.values() for r in rows]
    audit_by_id = {}
    for row in audit_rows:
        audit_by_id.setdefault(row['signal_id'], {}).update({k: v for k, v in row.items() if v is not None})
    audit_rows = list(audit_by_id.values())
    audit_html = ''.join('<tr>' + ''.join(f'<td>{_esc(row.get(k))}</td>' for k in
                        ('code', 'signal_id', 'setup', 'status', 'raw_status', 'path_status',
                         'snapshot_status', 'snapshot_source', 'observation_source', 'source_mode'))
                        + '</tr>' for row in audit_rows)
    audit_html = _simple_table(('代码', 'signal_id', 'Setup', 'technical status', 'raw status',
                               'Execution / Path Result', 'Fixed Horizon Snapshot', 'Snapshot Source',
                               'Execution Source', 'Source Mode'), [audit_html])
    issues = [a for a in model.anomalies if a != 'NONE']
    anomaly_html = (
        '<p class="note">其他异常：' + _esc('；'.join(issues)) + '</p>'
        if issues else '<p class="note">其他异常：无</p>'
    )
    review_html = []
    for horizon, label in (('T+5', 'T+5 PRIMARY REVIEW'), ('T+3', 'T+3 短期复盘'),
                           ('T+10', 'T+10 EXTENSION / CLOSURE')):
        rows = model.review_sections[horizon]
        if rows:
            review_html.append(f'<div class="horizon {"primary" if horizon == "T+5" else ""}">'
                               f'<h3>{label}</h3>{_review_table(rows)}</div>')
        else:
            review_html.append(f'<p class="note" aria-label="{label}">今日无 {horizon} 到期信号</p>')

    callout_class = (
        ' warning'
        if model.review_status == REVIEW_OBSERVATION_INCOMPLETE
        or (model.review_coverage and model.review_coverage.get('status') == REVIEW_OBSERVATION_INCOMPLETE)
        else ''
    )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>A股交易系统 — 每日收盘报告</title>
<style>
:root {{ color-scheme: light; --ink:#17212b; --muted:#5d6b78; --line:#dce3e8; --surface:#fff; --bg:#f4f7f9; --accent:#1f6feb; --warn:#9a6700; --loss:#b42318; --target:#087443; --missing:#7a3e00; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font-family:Arial,"Microsoft YaHei",sans-serif; line-height:1.45; }}
main {{ max-width:1500px; margin:0 auto; padding:24px; }}
h1 {{ margin:0 0 6px; font-size:clamp(24px,4vw,36px); }}
h2 {{ margin:28px 0 8px; font-size:22px; }}
h3 {{ margin:18px 0 8px; }}
.subtitle,.note {{ color:var(--muted); margin:4px 0 14px; }}
.section-summary {{ margin:8px 0 14px; font-weight:600; }}
.meta-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:8px; margin:20px 0; }}
.meta-item {{ background:var(--surface); border:1px solid var(--line); border-radius:8px; padding:10px 12px; min-width:0; }}
.meta-item span {{ display:block; color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }}
.meta-item strong {{ display:block; overflow-wrap:anywhere; font-size:13px; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:10px; margin:14px 0 28px; }}
.card {{ background:var(--surface); border:1px solid var(--line); border-top:4px solid var(--accent); border-radius:8px; padding:12px; }}
.card.warning {{ border-top-color:var(--warn); }} .card.loss {{ border-top-color:var(--loss); }} .card.target {{ border-top-color:var(--target); }} .card.missing {{ border-top-color:var(--missing); }}
.card-label {{ color:var(--muted); font-size:12px; }} .card-value {{ font-size:24px; font-weight:700; margin-top:4px; overflow-wrap:anywhere; }}
section {{ background:var(--surface); border:1px solid var(--line); border-radius:10px; padding:16px; margin:18px 0; overflow:hidden; }}
.toolbar {{ display:flex; flex-wrap:wrap; gap:10px; align-items:center; margin:12px 0; }}
input[type=search] {{ width:min(420px,100%); padding:10px 12px; border:1px solid #aebbc5; border-radius:6px; font-size:15px; }}
.table-wrap {{ overflow-x:auto; }}
td {{ font-variant-numeric:tabular-nums; }}
.primary {{ border-left:4px solid var(--accent); padding-left:14px; }}
summary {{ cursor:pointer; padding:14px 0; }}
table {{ border-collapse:collapse; width:100%; min-width:1050px; font-size:13px; }}
th,td {{ border-bottom:1px solid var(--line); padding:8px 9px; text-align:left; vertical-align:top; white-space:nowrap; }}
th {{ background:#eef3f6; color:#33404c; position:sticky; top:0; z-index:1; cursor:pointer; }}
th:hover {{ background:#e2ebf0; }}
.review-table,.active-table {{ min-width:1250px; }}
.signal-id {{ font-family:Consolas,monospace; font-size:12px; white-space:normal; min-width:250px; overflow-wrap:anywhere; }}
.badge {{ display:inline-block; border-radius:999px; border:1px solid currentColor; padding:2px 7px; font-size:12px; line-height:1.4; }}
.badge.normal {{ color:#38546b; }} .badge.warning {{ color:var(--warn); }} .badge.loss {{ color:var(--loss); }} .badge.target {{ color:var(--target); }} .badge.missing {{ color:var(--missing); }}
.callout {{ padding:12px 14px; border-left:4px solid var(--accent); background:#edf5ff; margin:12px 0; }}
.callout.warning {{ border-left-color:var(--warn); background:#fff8e1; }}
.anomalies {{ margin:0; padding-left:20px; }} .anomalies li {{ margin:5px 0; }}
.empty {{ color:var(--muted); text-align:center; padding:18px; }}
code {{ overflow-wrap:anywhere; }}
footer {{ color:var(--muted); font-size:12px; padding:18px 0 4px; }}
@media (max-width:700px) {{ main {{ padding:12px; }} section {{ padding:11px; }} th,td {{ padding:7px; }} }}
</style>
</head>
<body>
<main>
<header>
<h1>A股交易系统 · {metadata['review_date']} 收盘</h1>
<p class="subtitle">明日执行日：{metadata['earliest_execution']}</p>
<p class="note">策略：{_esc(metadata['strategy'])} · {'FROZEN CANDIDATE' if metadata['frozen_candidate'] == 'YES' else '状态待核验'}</p>
</header>
<h2>今日总览</h2>
<div class="cards">{card_html}</div>
<p class="callout{callout_class}">{_esc(model.summary_text)}</p>
<section id="trade-performance">
<h2>交易绩效 · T+1 可执行口径</h2>
<p class="note">execution model：{_esc(trade_performance.get('execution_model'))} · 只统计 { _esc(trade_performance.get('strategy')) } · 返回为毛收益，未扣费用与滑点。</p>
{_trade_performance_html(trade_performance)}
</section>
<section id="daily-review">
<h2>昨日信号复盘 · {metadata['previous_date']}</h2>
<p class="section-summary">总信号 {summary['previous_total']} · triggered {summary['previous_triggered']} · pending / 未触发 {summary['previous_pending']} · same-bar {summary['previous_ambiguous']}。默认按需注意、triggered、pending 排序。</p>
<h3>昨日名单今日表现 · {metadata['previous_date']}</h3>
{_daily_table(model.previous_signals)}
<h3>历史仍在观察</h3>
{_daily_table(model.active_signals)}
{('<h3>今日结束</h3>' + _daily_table(model.closed_today)) if model.closed_today else ''}
</section>
<section id="tomorrow-watchlist">
<h2>今日新名单 / 明日观察</h2>
<p class="note">共 {metadata['candidate_count']} 个 · 按 Score 从高到低排列。位置标签仅供阅读，不改变筛选或交易规则。</p>
<div class="toolbar"><label for="watchlist-search">搜索：</label><input id="watchlist-search" type="search" placeholder="输入代码、名称或行业" autocomplete="off"></div>
{_watchlist_table(model.watchlist_rows)}
</section>
<section id="formal-review">
<h2>策略滚动复盘</h2>
<p class="note">只展示 tracker 已定义且已验证的 execution / fixed-horizon coverage；UNVERIFIED、未成熟窗口和 same-bar 结果不被临时归类或计算新指标。</p>
{_rolling_review_html(rolling_review)}
<h3>正式节点明细</h3>
<p class="note">节点收益是固定期限快照，与触发、目标及止损等路径结果分开记录。</p>
{''.join(review_html)}
</section>
<section id="anomalies"><h2>异常与数据质量</h2>
<p class="note">“今日新信号等待 T+1”是正常状态，不计入缺失；历史缺口、UNVERIFIED、same-bar 和云端/采集状态分别列出。</p>
{_quality_table(quality_rows)}
{anomaly_html}
</section>
<details id="audit"><summary>审计详情</summary>
<div class="meta-grid">{metadata_html}</div>
<p>review status: {_esc(model.review_status)}</p>
<p>{_esc('；'.join(model.anomalies))}</p>
{audit_html}
</details>
<footer>本报告仅整理正式观察名单与 tracker 的真实记录。缺少记录显示 —，不回填历史行情。</footer>
</main>
<script>
(function () {{
  const search = document.getElementById('watchlist-search');
  const table = document.getElementById('watchlist-table');
  if (!search || !table) return;
  const body = table.querySelector('tbody');
  const rows = () => Array.from(body.querySelectorAll('tr'));
  search.addEventListener('input', function () {{
    const query = search.value.trim().toLowerCase();
    rows().forEach(function (row) {{
      row.hidden = query !== '' && !(row.dataset.search || '').includes(query);
    }});
  }});
}})();
</script>
</body>
</html>
"""


def atomic_write_text(path: str | Path, content: str) -> None:
    """Atomically replace one UTF-8 text file, leaving old content intact on failure."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except Exception:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
        raise


def render_daily_close(
    report_date: date | datetime | str,
    *,
    paths: DataPaths | None = None,
    review_failure: str | None = None,
    generated_at: datetime | None = None,
    calendar: TradingCalendar | None = None,
) -> tuple[ReportModel, Path, Path]:
    """Build and atomically write the dated report and complete latest copy."""

    resolver = paths or DataPaths.from_env()
    model = build_report_model(
        report_date,
        paths=resolver,
        review_failure=review_failure,
        generated_at=generated_at,
        calendar=calendar,
    )
    content = render_html(model)
    date_path = resolver.reports_dir() / f"daily_close_{_date_token(model.metadata['list_date'])}.html"
    latest_path = resolver.reports_dir() / "latest.html"
    atomic_write_text(date_path, content)
    atomic_write_text(latest_path, content)
    return model, date_path, latest_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="canonical watchlist/report date, YYYYMMDD or YYYY-MM-DD")
    parser.add_argument(
        "--review-failure",
        default=None,
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        model, dated, latest = render_daily_close(
            args.date,
            review_failure=args.review_failure,
        )
    except Exception as exc:
        print(f"DAILY_CLOSE_RENDER_FAILED: {type(exc).__name__}: {exc}")
        return 2
    summary = model.daily_summary
    print(f"dated_html={dated}")
    print(f"latest_html={latest}")
    print(f"candidate_count={model.metadata['candidate_count']}")
    print(
        "review_summary="
        f"active={summary['active_signals']},new_triggered={summary['new_triggered']},"
        f"target_hits={summary['target_hits']},stop_hits={summary['stop_hits']},"
        f"ambiguous={summary['ambiguous']},missing={summary['missing_observations']}"
    )
    print(f"t3_count={summary['t3_count']}")
    print(f"t5_primary_count={summary['t5_count']}")
    print(f"t10_count={summary['t10_count']}")
    print(f"anomalies={' | '.join(model.anomalies)}")
    print(f"watchlist_sha={model.metadata['watchlist_sha']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
