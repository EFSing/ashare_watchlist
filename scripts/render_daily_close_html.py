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
from b_shadow_monitor import ShadowMonitorError, build_report_view, load_store
from track_perf import (
    REVIEW_HORIZONS,
    REVIEW_POINT_CAPTURED,
    REVIEW_POINT_NOT_CAPTURED,
    REVIEW_OBSERVATION_INCOMPLETE,
    EXECUTION_MODEL_DAILY_OHLC_T1_V1,
    EXECUTION_T_PLUS_1_PENDING,
    UNVERIFIED_MISSING_EXECUTION_OBSERVATION,
    EXIT_REASON_AMBIGUOUS,
    STRATEGY_RULE_PERFORMANCE_MODEL,
    PERFORMANCE_DATA_INCOMPLETE,
    STRATEGY_RULE_CONFIG_ERROR,
    build_trade_performance_summary,
    build_strategy_rule_performance,
    load_strategy_rule_historical_ohlc,
    load_tracker,
    parse_date,
    review_date,
    current_prospective_watchlists,
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
    execution_audit: dict[str, Any] | None = None
    shadow_monitor: dict[str, Any] | None = None


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
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
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
        return "warning"
    if "AMBIGUOUS" in value or value in {"PENDING", "TRIGGERED", "EXPIRED"}:
        return "warning"
    if "STOP" in value or value == "LOSS":
        return "negative"
    if "TARGET" in value or value in {"WIN", "CAPTURED"}:
        return "positive"
    return "neutral"


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


def _load_shadow_monitor(
    paths: DataPaths,
    report_date: str,
    watchlist: Mapping[str, Any],
) -> dict[str, Any]:
    """Read shadow state fail-soft; formal report rendering remains available."""

    shadow_path = paths.root / "shadow_monitor" / "b_shadow_monitor.json"
    if not shadow_path.exists():
        return build_report_view(None, report_date, watchlist=watchlist)
    try:
        store = load_store(shadow_path.parent, missing_ok=False)
        return build_report_view(store, report_date, watchlist=watchlist)
    except (OSError, ValueError, ShadowMonitorError) as exc:
        expected = len(watchlist.get("candidates", [])) if isinstance(watchlist, Mapping) else 0
        return {
            "status": "SHADOW_CAPTURE_INCOMPLETE",
            "epoch_start": None,
            "as_of_date": report_date,
            "empty": expected == 0,
            "overall": {
                "signals": 0, "eligible": 0, "triggered": 0, "resolved": 0,
                "target": 0, "stop": 0, "open": 0, "untriggered": 0,
                "ambiguous": 0, "fast_stop_count": 0, "fast_stop_rate": None,
                "profit_factor": None, "expectancy": None, "avg_r": None,
            },
            "trend_rows": [],
            "vol_rows": [],
            "reactivation_rows": [],
            "reactivation_mode": "CONTINUOUS_MEDIAN_NO_FROZEN_BINS",
            "current_regime": "—",
            "current_signal_context": {},
            "reference_only": {},
            "capture": {"expected": expected, "complete": 0, "incomplete": expected, "status": "SHADOW_CAPTURE_INCOMPLETE"},
            "error": f"{type(exc).__name__}: {exc}",
        }


def _watchlist_rows(
    watchlist: Mapping[str, Any],
    tracker: Mapping[str, Any] | None,
    report_date: str,
    shadow_monitor: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    signals = tracker.get("signals", {}) if isinstance(tracker, Mapping) else {}
    signals = signals if isinstance(signals, Mapping) else {}
    candidates = sorted(
        watchlist["candidates"],
        key=lambda item: (-float(item.get("score", float("-inf"))), str(item.get("code", ""))),
    )
    rows: list[dict[str, Any]] = []
    shadow_context = shadow_monitor.get("current_signal_context", {}) if isinstance(shadow_monitor, Mapping) else {}
    shadow_context = shadow_context if isinstance(shadow_context, Mapping) else {}
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
                "shadow_context": dict(shadow_context.get(candidate.get("signal_id"), {}))
                if isinstance(shadow_context.get(candidate.get("signal_id")), Mapping)
                else {},
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
                    "horizon_return": _percent(return_value, signed=True) if return_value is not None else _UNVERIFIED,
                    "horizon_return_value": return_value,
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
    canonical_watchlists = current_prospective_watchlists(resolver)
    historical_ohlc, historical_provenance = load_strategy_rule_historical_ohlc(
        canonical_watchlists,
        normalized_date,
        paths=resolver,
        calendar=cal,
    )
    trade_performance = build_strategy_rule_performance(
        canonical_watchlists,
        historical_ohlc,
        normalized_date,
        calendar=cal,
        historical_provenance=historical_provenance,
    )
    shadow_monitor = _load_shadow_monitor(resolver, normalized_date, watchlist)
    execution_audit = build_trade_performance_summary(
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
    watchlist_rows = _watchlist_rows(watchlist, tracker, normalized_date, shadow_monitor)

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
        + int(trade_performance.get("performance_data_incomplete") or 0)
        + int(trade_performance.get("strategy_config_errors") or 0)
    )
    data_quality = [
        {
            "category": "策略规则复算数据缺失",
            "count": trade_performance.get("performance_data_incomplete", 0),
            "status": PERFORMANCE_DATA_INCOMPLETE,
            "reason": "历史 daily OHLC 不完整，不猜测触发或退出结果",
            "signal_dates": ", ".join(
                f"{row.get('signal_date')} ({row.get('code')})"
                for row in trade_performance.get("performance_data_incomplete_rows", [])
            ) or "—",
        },
        {
            "category": "策略规则配置错误",
            "count": trade_performance.get("strategy_config_errors", 0),
            "status": STRATEGY_RULE_CONFIG_ERROR,
            "reason": "trigger / stop / target 不满足多头规则约束，不进入绩效统计",
            "signal_dates": ", ".join(
                f"{row.get('signal_date')} ({row.get('code')})"
                for row in trade_performance.get("config_error_rows", [])
            ) or "—",
        },
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
            "category": "prospective observation 缺失",
            "count": execution_audit.get("execution_unverified", 0),
            "status": UNVERIFIED_MISSING_EXECUTION_OBSERVATION,
            "reason": "实时 prospective 跟踪不完整；不影响独立规则价策略绩效复算",
            "signal_dates": "—",
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
    shadow_capture = shadow_monitor.get("capture", {}) if isinstance(shadow_monitor, Mapping) else {}
    if shadow_capture.get("status") == "SHADOW_CAPTURE_INCOMPLETE":
        data_quality.append({
            "category": "Prospective Shadow Monitor",
            "count": shadow_capture.get("incomplete", 0),
            "status": "SHADOW_CAPTURE_INCOMPLETE",
            "reason": f"Shadow monitor data incomplete: {shadow_capture.get('complete', 0)}/{shadow_capture.get('expected', 0)}",
            "signal_dates": normalized_date,
        })
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
        "strategy_rule_performance_model": STRATEGY_RULE_PERFORMANCE_MODEL,
        "strategy_rule_performance_source": trade_performance.get("historical_data_source"),
        "strategy_rule_performance_provider_calls": trade_performance.get("historical_provider_calls", 0),
        "shadow_monitor_status": shadow_monitor.get("status", "UNVERIFIED"),
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
        execution_audit=execution_audit,
        shadow_monitor=shadow_monitor,
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
        _T1_PENDING: '等待下一交易日观察',
        'VERIFIED': '已核验', 'COMPLETE': '完整',
        'LOCAL_INPUTS_VERIFIED': '本地输入已核验',
        'UPLOADED_AND_VERIFIED': '已验证', 'NO_OP_ALREADY_VERIFIED': '已验证',
        'EXECUTION_VERIFIED': '已核验',
        EXECUTION_MODEL_DAILY_OHLC_T1_V1: 'T+1 日线执行模型',
        UNVERIFIED_MISSING_EXECUTION_OBSERVATION: '执行路径待核验',
        PATH_UNVERIFIED_MISSING_PRIOR_EXECUTION_PATH: '路径未完整验证',
        'MISSING_HISTORICAL_OBSERVATION': '历史数据缺失',
        'MISSING_HISTORICAL_OBSERVATION / UNVERIFIED': '历史路径待核验',
        'REVIEW_OBSERVATION_INCOMPLETE': '复盘覆盖不完整',
        'REVIEW_FAILED': '复盘读取异常',
        'EXPIRED_UNTRIGGERED': '到期未触发', 'UNTRIGGERED_ACTIVE': '仍待触发',
        'NOT_A_CONFIRMED_CLOSED_TRADE': '未纳入正式结案',
        'TIME_EXIT': '到期退出', 'TIME_EXIT_PENDING_T1': '等待 T+1 退出',
        'TIME_EXIT_T1_DEFERRED': 'T+1 延后退出',
        'STOP': '止损', 'TARGET': '目标达成', 'STOP_GAP': '跳空止损',
        'TARGET_GAP': '跳空达标',
        'SAMPLE_SMALL': '样本不足', 'SAMPLE_READY': '样本可用',
        _MISSING: '数据缺失', _UNVERIFIED: '待核验',
    }.get(value, value or '数据缺失')


def _ui_badge(value):
    return f'<span class="badge {_status_class(value)}">{_esc(_display_status(value))}</span>'


def _integer(value: Any, fallback: str = '—') -> str:
    if value is None or value == '':
        return fallback
    try:
        number = float(value)
    except (TypeError, ValueError):
        return _text(value, fallback)
    if number.is_integer():
        return str(int(number))
    return f'{number:.2f}'


def _signed_number(value: Any, digits: int = 2, fallback: str = '—') -> str:
    if value is None or value == '':
        return fallback
    try:
        number = float(value)
    except (TypeError, ValueError):
        return _text(value, fallback)
    prefix = '+' if number > 0 else ''
    return f'{prefix}{number:.{digits}f}'


def _numeric_tone(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 'neutral'
    if number > 0:
        return 'positive'
    if number < 0:
        return 'negative'
    return 'neutral'


def _simple_table(headers, body, table_id='', table_class=''):
    table_id_attr = f' id="{_esc(table_id)}"' if table_id else ''
    class_attr = f' class="{_esc(table_class)}"' if table_class else ''
    return (f'<div class="table-scroll"><table{table_id_attr}{class_attr}><thead><tr>'
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
                else '—'
            )
        horizon_return = row.get('horizon_return', _UNVERIFIED)
        if horizon_return in {_UNVERIFIED, _MISSING, 'N/A'}:
            horizon_return = '—'
        values += [_esc(node_ohlc), _esc(horizon_return),
                   _ui_badge(row.get('path_status')), _ui_badge(row.get('snapshot_status')),
                   _esc(row.get('snapshot_source', '已记录'))]
        body.append('<tr>' + ''.join(f'<td>{v}</td>' for v in values) + '</tr>')
    return _simple_table(('代码', '名称', '名单日期', '节点 O/H/L/C', '节点收益', '路径结果', '节点快照状态', '节点来源'), body, table_class='review-table')


def _position(distance):
    if distance is None:
        return '—'
    if distance < 0:
        return '已在 Trigger 上方'
    if abs(distance) <= 1:
        return '贴近 Trigger'
    return '等待触发'


def _watchlist_table(rows, earliest_execution=None):
    body = []
    for row in rows:
        distance = row['distance_to_trigger_pct']
        search = ' '.join(str(row.get(k, '')) for k in ('code', 'name', 'sector')).lower()
        distance_value = _percent(distance, signed=True) if distance is not None else '—'
        distance_tone = _numeric_tone(distance)
        status = row.get('status')
        observation_status = row.get('observation_status')
        shadow = row.get('shadow_context') if isinstance(row.get('shadow_context'), Mapping) else {}
        shadow_market = shadow.get('market') or '—'
        shadow_reactivation = _number(shadow.get('reactivation_vs_breakout_ratio'), 2)
        body.append(
            f'<article class="watch-row" data-search="{_esc(search)}">'
            f'<div class="watch-primary">'
            f'<span class="watch-rank">{_esc(_integer(row.get("rank"), ""))}</span>'
            f'<div class="security"><strong>{_esc(row.get("code"))}</strong>'
            f'<span>{_esc(row.get("name"))}</span></div>'
            f'<div class="watch-score"><span>Score</span><strong>{_esc(_integer(row.get("score")))}</strong></div>'
            f'<div class="watch-state">{_ui_badge(observation_status)}'
            f'<small>{_esc(_display_status(status))}</small></div>'
            f'</div>'
            f'<div class="watch-facts">'
            f'<span><label>触发</label><strong>{_esc(_number(row.get("trigger")))}</strong></span>'
            f'<span><label>止损</label><strong class="negative">{_esc(_number(row.get("stop")))}</strong></span>'
            f'<span><label>目标</label><strong class="positive">{_esc(_number(row.get("target")))}</strong></span>'
            f'<span><label>RR</label><strong>{_esc(_number(row.get("rr")))}</strong></span>'
            f'<span><label>距触发</label><strong class="{distance_tone}">{_esc(distance_value)}</strong>'
            f'<small>{_esc(_position(distance))}</small></span>'
            f'<span><label>T+1</label><strong>{_esc(earliest_execution)}</strong></span>'
            f'<span><label>市场</label><strong>{_esc(shadow_market)}</strong></span>'
            f'<span><label>再启动量能</label><strong>{_esc(shadow_reactivation)}× breakout</strong></span>'
            f'</div>'
            f'<div class="watch-meta"><span>{_esc(row.get("sector"))}</span>'
            f'<span>{_esc(row.get("status_explanation"))}</span></div>'
            f'</article>'
        )
    if not body:
        return '<div id="watchlist-table" class="empty-state">今日暂无新名单。</div>'
    return f'<div id="watchlist-table" class="watchlist-list">{"".join(body)}</div>'


def _daily_note(row: Mapping[str, Any]) -> str:
    raw_status = row.get('raw_status')
    if not row.get('observed'):
        return '当日观察缺失，暂不作交易结论'
    if raw_status == 'AMBIGUOUS_SAME_BAR':
        return '同日触及条件，先后顺序无法确认'
    if row.get('closed_today'):
        if raw_status == 'win':
            return '今日目标达成，交易结束'
        if raw_status == 'loss':
            return '今日止损，交易结束'
        if raw_status == 'expired':
            return '今日到期未触发，交易结束'
        return '今日结束跟踪'
    if row.get('new_triggered'):
        return '今日新触发，进入持仓观察'
    if raw_status == 'triggered':
        return '已触发，继续观察'
    if raw_status == 'pending':
        return '继续等待触发'
    return '按当日已记录状态展示'


def _daily_tone(row: Mapping[str, Any]) -> str:
    if row.get('raw_status') in {'win', 'loss'}:
        return _status_class(row.get('raw_status'))
    if not row.get('observed') or row.get('raw_status') == 'AMBIGUOUS_SAME_BAR':
        return 'warning'
    return 'neutral'


def _daily_table(rows):
    if not rows:
        return '<div class="empty-state">暂无需要处理的已核验事件。</div>'
    body = []
    for row in rows:
        change = row.get('daily_change_pct')
        close_vs_trigger = row.get('close_vs_trigger_pct')
        body.append(
            f'<article class="action-row {_daily_tone(row)}">'
            f'<div class="action-top"><div class="security"><strong>{_esc(row.get("code"))}</strong>'
            f'<span>{_esc(row.get("name"))}</span></div>'
            f'<div class="action-status">{_ui_badge(row.get("path_status"))}'
            f'{_ui_badge(row.get("observation_status"))}</div></div>'
            f'<div class="action-facts">'
            f'<span><label>今日开盘</label><strong>{_esc(_number(row.get("today_open")))}</strong></span>'
            f'<span><label>今日最高</label><strong>{_esc(_number(row.get("today_high")))}</strong></span>'
            f'<span><label>今日最低</label><strong>{_esc(_number(row.get("today_low")))}</strong></span>'
            f'<span><label>今日收盘</label><strong>{_esc(_number(row.get("today_close")))}</strong></span>'
            f'<span><label>当日涨跌</label><strong class="{_numeric_tone(change)}">{_esc(_percent(change, signed=True))}</strong></span>'
            f'<span><label>收盘较 Trigger %</label><strong class="{_numeric_tone(close_vs_trigger)}">'
            f'{_esc(_percent(close_vs_trigger, signed=True) if close_vs_trigger is not None else "—")}</strong></span>'
            f'</div>'
            f'<div class="action-bottom"><span>{_esc(_daily_note(row))}</span>'
            f'<small>{_esc(row.get("observation_source", "数据缺失"))}</small></div>'
            f'</article>'
        )
    return f'<div class="action-list">{"".join(body)}</div>'


def _active_review_html(rows: list[Mapping[str, Any]]) -> str:
    """Keep a large passive active-signal inventory out of the first view."""

    if not rows:
        return _daily_table(rows)
    if len(rows) <= 8:
        return _daily_table(rows)
    return (
        f'<details class="active-details"><summary>继续观察 · { _integer(len(rows), "0") } 个'
        '<span class="note">（默认收起）</span></summary>'
        f'{_daily_table(rows)}</details>'
    )


def _quality_table(
    rows,
    *,
    performance: Mapping[str, Any] | None = None,
    audit_performance: Mapping[str, Any] | None = None,
    summary: Mapping[str, Any] | None = None,
    acquisition_status: str = 'COMPLETE',
    review_status: str = 'READY',
    shadow_monitor: Mapping[str, Any] | None = None,
):
    """Render strategy reconstruction quality separately from prospective audit quality."""

    if performance is not None:
        summary = summary or {}
        audit_performance = audit_performance or {}
        items = [
            ('策略规则复算数据缺失', performance.get('performance_data_incomplete', 0),
             PERFORMANCE_DATA_INCOMPLETE,
             '历史 daily OHLC 不完整，不猜测策略规则路径。'),
            ('策略规则配置错误', performance.get('strategy_config_errors', 0),
             STRATEGY_RULE_CONFIG_ERROR,
             'trigger / stop / target 配置不满足多头规则约束。'),
            ('同日顺序不明', performance.get('ambiguous', 0),
             'AMBIGUOUS_SAME_BAR',
             '保留安全口径，不猜测日内先后顺序。'),
            ('prospective observation 缺失', audit_performance.get('execution_unverified', 0),
             UNVERIFIED_MISSING_EXECUTION_OBSERVATION,
             '实时 prospective 跟踪不完整；不影响规则价策略绩效复算。'),
            ('prospective T+1 等待', audit_performance.get('execution_pending', 0),
             EXECUTION_T_PLUS_1_PENDING,
             '正常状态：新信号等待下一交易日 observation。'),
            ('历史节点 / 当日数据缺失', summary.get('daily_missing', 0) + summary.get('missing_observations', 0),
             _MISSING,
             'prospective review observation 缺失，不回填历史节点。'),
        ]
        shadow_capture = shadow_monitor.get('capture', {}) if isinstance(shadow_monitor, Mapping) else {}
        if shadow_capture.get('status') == 'SHADOW_CAPTURE_INCOMPLETE':
            items.append((
                'Prospective Shadow Monitor',
                shadow_capture.get('incomplete', 0),
                'SHADOW_CAPTURE_INCOMPLETE',
                f"Shadow monitor data incomplete: {shadow_capture.get('complete', 0)}/{shadow_capture.get('expected', 0)}",
            ))
        if acquisition_status != 'COMPLETE':
            items.append(('行情证据', 1, acquisition_status, '行情证据采集状态待确认。'))
        if review_status == 'REVIEW_FAILED':
            items.append(('复盘读取', 1, review_status, '复盘读取未完成，名单仍可查看。'))
        visible = [(label, count, status, reason) for label, count, status, reason in items if count]
        ok_html = (
            '<div class="quality-ok"><span class="badge positive">质量分层正常</span>'
            '<span>规则价绩效与 prospective observation audit 已分开。</span></div>'
            if acquisition_status == 'COMPLETE' else ''
        )
    else:
        visible = [
            (row.get('category'), row.get('count'), row.get('status'), row.get('reason'))
            for row in rows if row.get('count')
        ]
        ok_html = ''

    if not visible:
        return ok_html or '<div class="quality-ok"><span class="badge positive">质量分层正常</span><span>未发现新的数据质量异常。</span></div>'

    body = []
    for label, count, status, reason in visible:
        body.append(
            f'<div class="quality-item"><span>{_esc(label)}</span>'
            f'<strong>{_esc(_integer(count))}</strong>{_ui_badge(status)}'
            f'<small>{_esc(reason)}</small></div>'
        )
    return ok_html + f'<div class="quality-grid">{"".join(body)}</div>'


def _rolling_review_html(review: Mapping[str, Any]) -> str:
    items = [
        ('执行记录', f"{_integer(review.get('execution_captured'), '0')} / {_integer(review.get('execution_expected'), '0')}"),
        ('节点快照', f"{_integer(review.get('horizon_captured'), '0')} / {_integer(review.get('horizon_expected'), '0')}"),
        ('历史路径待核验', _integer(review.get('unverified_excluded'), '0')),
        ('同日顺序不明', _integer(review.get('ambiguous_excluded'), '0')),
    ]
    return '<div class="coverage-strip">' + ''.join(
        f'<div><span>{_esc(label)}</span><strong>{_esc(value)}</strong></div>'
        for label, value in items
    ) + '</div>'


def _performance_value(
    performance: Mapping[str, Any],
    key: str,
    *,
    percent: bool = False,
    signed: bool = False,
) -> str:
    value = performance.get(key)
    if value is None:
        return '—'
    if percent:
        return _percent(value, signed=signed)
    if signed:
        return _signed_number(value)
    return _number(value)


def _performance_cards(performance: Mapping[str, Any]) -> str:
    cards = [
        ("胜率", "win_rate", True, False, ""),
        ("平均收益", "avg_return_pct", True, True, ""),
        ("盈亏比", "payoff_ratio", False, False, ""),
        ("Profit Factor", "profit_factor", False, False, "盈利因子"),
        ("已结案交易", "resolved_closed_trades", False, False, "TARGET / STOP"),
        ("当前理论持仓（当前持仓）", "open_rule_trades", False, False, "不代表账户实际持仓"),
    ]
    integer_keys = {"resolved_closed_trades", "open_rule_trades"}
    return ''.join(
        f'<article class="kpi-card primary-kpi" data-kpi="primary">'
        f'<div class="kpi-label">{_esc(label)}</div>'
        f'<div class="kpi-value {_numeric_tone(performance.get(key))}">'
        f'{_esc(_integer(performance.get(key)) if key in integer_keys else _performance_value(performance, key, percent=percent, signed=signed))}</div>'
        f'{f"<small>{_esc(note)}</small>" if note else ""}</article>'
        for label, key, percent, signed, note in cards
    )


def _performance_metric_strip(performance: Mapping[str, Any]) -> str:
    metrics = [
        ("触发率", "trigger_rate", True, True),
        ("已触发", "triggered", False, False),
        ("平均盈利", "avg_win_pct", True, True),
        ("平均亏损", "avg_loss_pct", True, True),
        ("期望收益", "expectancy_pct", True, True),
        ("平均 R", "avg_r", False, True),
        ("平均持有", "avg_holding_sessions", False, False),
        ("平均 MFE", "avg_mfe_pct", True, True),
        ("平均 MAE", "avg_mae_pct", True, True),
    ]
    return '<div class="metric-strip" aria-label="次级绩效指标">' + ''.join(
        f'<div class="metric-item"><span>{_esc(label)}</span>'
        f'<strong class="{_numeric_tone(performance.get(key))}">'
        f'{_esc(_integer(performance.get(key), "0") if key == "triggered" else _performance_value(performance, key, percent=percent, signed=signed))}'
        f'</strong>{"<small>交易日</small>" if key == "avg_holding_sessions" else ""}</div>'
        for label, key, percent, signed in metrics
    ) + '</div>'


def _entered_has_unverified_path(performance: Mapping[str, Any]) -> bool:
    try:
        entered = int(performance.get('entered') or 0)
        eligible = int(performance.get('eligible_signals') or 0)
        unverified = int(performance.get('execution_unverified') or 0)
    except (TypeError, ValueError):
        return False
    return entered > 0 and unverified > 0 and entered > eligible


def _performance_funnel(performance: Mapping[str, Any]) -> str:
    eligible = performance.get('signals_with_t1_opportunity', performance.get('eligible_signals'))
    triggered_value = performance.get('triggered', performance.get('entered'))
    if 'triggered' not in performance and _entered_has_unverified_path(performance):
        triggered_value = f'{_integer(triggered_value, "0")}*'
    items = [
        ('总信号', performance.get('total_signals')),
        ('T+1 可机会', eligible),
        ('已触发', triggered_value),
        ('已结案', performance.get('resolved_closed_trades', performance.get('confirmed_closed_count'))),
        ('当前理论持仓', performance.get('open_rule_trades', performance.get('open_positions_count'))),
        ('未触发', performance.get('untriggered', performance.get('untriggered_expired'))),
        ('同日顺序不明', performance.get('ambiguous')),
        ('行情不完整', performance.get('performance_data_incomplete')),
    ]
    return '<div class="funnel">' + ''.join(
        f'<div class="funnel-item"><span>{_esc(label)}</span><strong>{_esc(value)}</strong></div>'
        for label, value in items
    ) + '</div>'


def _performance_detail_table(performance: Mapping[str, Any]) -> str:
    rows = [
        ("中位收益", _performance_value(performance, "median_return_pct", percent=True, signed=True)),
        ("中位 R", _performance_value(performance, "median_r", signed=True)),
        ("止盈次数 / resolved", _integer(performance.get("resolved_target"), "0")),
        ("止损次数 / resolved", _integer(performance.get("resolved_stop"), "0")),
        ("中位持有交易日", _performance_value(performance, "median_holding_sessions")),
        ("中位 MFE", _performance_value(performance, "median_mfe_pct", percent=True, signed=True)),
        ("中位 MAE", _performance_value(performance, "median_mae_pct", percent=True, signed=True)),
        ("当前理论持仓平均浮动收益", _performance_value(performance, "open_mtm_avg_return_pct", percent=True, signed=True)),
        ("历史日线来源", _text(performance.get("historical_data_source"))),
        ("策略绩效 provider calls", _integer(performance.get("historical_provider_calls"), "0")),
    ]
    body = [f"<tr><td>{_esc(label)}</td><td>{value if '<' in str(value) else _esc(value)}</td></tr>" for label, value in rows]
    return _simple_table(("补充交易绩效指标", "值"), body, table_class='metric-detail-table')


def _trade_closed_table(rows: list[Mapping[str, Any]]) -> str:
    headers = (
        "信号日", "代码", "名称", "触发日", "trigger", "最早可卖日", "退出日", "exit price",
        "退出类型", "return %", "R", "holding sessions", "MFE", "MAE",
    )
    if not rows:
        return '<div class="empty-state">暂无已结案策略交易。</div>'
    body = []
    for row in rows:
        values = [_esc(row.get("signal_date")), _esc(row.get("code")), _esc(row.get("name")),
                  _esc(row.get("entry_date")), _esc(_number(row.get("entry_price"))),
                  _esc(row.get("sellable_from")), _esc(row.get("exit_date")),
                   _esc(_number(row.get("exit_price"))), _ui_badge(row.get("exit_reason")),
                   f'<span class="number {_numeric_tone(row.get("realized_return_pct"))}">{_esc(_percent(row.get("realized_return_pct"), signed=True))}</span>',
                   _esc(_signed_number(row.get("realized_r"))), _esc(_number(row.get("holding_sessions"))),
                   _esc(_percent(row.get("mfe_pct"), signed=True)), _esc(_percent(row.get("mae_pct"), signed=True))]
        body.append("<tr>" + "".join(f"<td>{value}</td>" for value in values) + "</tr>")
    return _simple_table(headers, body, table_class='trade-table')


def _trade_open_table(rows: list[Mapping[str, Any]]) -> str:
    headers = (
        "信号日", "代码", "名称", "触发日", "trigger", "stop", "target", "当前 close",
        "浮动收益 %", "MFE", "MAE",
    )
    if not rows:
        return '<div class="empty-state">当前无策略理论持仓（当前持仓不代表账户实际持仓）。</div>'
    body = []
    for row in rows:
        values = [_esc(row.get("signal_date")), _esc(row.get("code")), _esc(row.get("name")),
                  _esc(row.get("trigger_date")), _esc(_number(row.get("trigger"))),
                  _esc(_number(row.get("stop"))), _esc(_number(row.get("target"))),
                  _esc(_number(row.get("latest_close"))),
                   f'<span class="number {_numeric_tone(row.get("mark_return_pct"))}">{_esc(_percent(row.get("mark_return_pct"), signed=True))}</span>',
                   _esc(_percent(row.get("mfe_pct"), signed=True)), _esc(_percent(row.get("mae_pct"), signed=True))]
        body.append("<tr>" + "".join(f"<td>{value}</td>" for value in values) + "</tr>")
    return _simple_table(headers, body, table_class='trade-table')


def _trade_ambiguous_table(rows: list[Mapping[str, Any]]) -> str:
    headers = ("date", "code", "名称", "stop", "target", "daily low", "daily high")
    if not rows:
        return '<div class="empty-state">暂无同日顺序不明策略交易。</div>'
    body = []
    for row in rows:
        values = [
            _esc(row.get("exit_date")), _esc(row.get("code")), _esc(row.get("name")),
            _esc(_number(row.get("stop"))), _esc(_number(row.get("target"))),
            _esc(_number(row.get("ambiguous_low"))), _esc(_number(row.get("ambiguous_high"))),
        ]
        body.append("<tr>" + "".join(f"<td>{value}</td>" for value in values) + "</tr>")
    return _simple_table(headers, body, table_class='trade-table')


def _trade_excluded_table(rows: list[Mapping[str, Any]]) -> str:
    headers = ("技术 ID", "代码", "名称", "排除原因", "状态", "执行路径")
    if not rows:
        return '<div class="empty-state">暂无排除或待核验记录。</div>'
    body = []
    for row in rows:
        values = [_esc(row.get("signal_id")), _esc(row.get("code")), _esc(row.get("name")),
                  _ui_badge(row.get("reason")), _ui_badge(row.get("status")),
                  _ui_badge(row.get("execution_verification_status"))]
        body.append("<tr>" + "".join(f"<td>{value}</td>" for value in values) + "</tr>")
    return _simple_table(headers, body, table_class='audit-table')


def _trade_performance_html(
    performance: Mapping[str, Any],
    *,
    new_signal_count: int = 0,
    list_date: str = '—',
    earliest_execution: str = '—',
) -> str:
    closed_count = int(performance.get('resolved_closed_trades') or 0)
    if closed_count == 0:
        status_html = (
            '<div class="performance-status warning">'
            '<span class="badge warning">样本不足</span>'
            '<div><strong>当前暂无可用于正式绩效统计的已结案策略交易。</strong>'
            '<small>指标只基于 resolved TARGET / STOP；OPEN、UNTRIGGERED、歧义和数据缺失不进入已结案统计。</small></div>'
            '</div>'
        )
    elif closed_count < 10:
        status_html = (
            f'<div class="performance-status warning"><span class="badge warning">样本较小</span>'
            f'<div><strong>当前已结案策略交易 {closed_count} 笔，结果仅供阶段性参考。</strong>'
            '<small>规则价模拟只使用 resolved TARGET / STOP。</small></div></div>'
        )
    else:
        status_html = (
            f'<div class="performance-status ready"><span class="badge positive">统计可用</span>'
            f'<div><strong>当前已结案策略交易 {closed_count} 笔。</strong>'
            '<small>结果按 trigger / stop / target 规则价与 A 股 T+1 展示。</small></div></div>'
    )

    closed_empty = _trade_closed_table(performance.get('closed_trades', []))
    excluded_rows = performance.get('excluded_rows', [])
    ambiguous_rows = performance.get('ambiguous_rows', [])
    return (
        status_html +
        f'<div class="primary-kpis">{_performance_cards(performance)}</div>'
        f'<div class="secondary-label"><span>辅助绩效指标</span><small>只对 resolved TARGET / STOP 计算；没有样本时显示 —</small></div>'
        f'{_performance_metric_strip(performance)}'
        '<div class="subsection-head"><h3>样本漏斗</h3><small>prospective observation 完整性不作为规则绩效样本准入门槛。</small></div>'
        f'{_performance_funnel(performance)}'
        '<details class="metric-details"><summary>查看补充统计</summary>'
        f'{_performance_detail_table(performance)}'
        '</details>'
        '<div class="performance-block"><div class="subsection-head"><h3>当前策略理论持仓</h3>'
        f'<span class="count-label">{_integer(performance.get("open_rule_trades"), "0")} 笔 · 不代表账户实际持仓</span></div>'
        f'{_trade_open_table(performance.get("open_position_rows", []))}</div>'
        '<div class="performance-block"><div class="subsection-head"><h3>已结案策略交易</h3>'
        f'<span class="count-label">{_integer(performance.get("resolved_closed_trades"), "0")} 笔</span></div>'
        f'{closed_empty}</div>'
        '<div class="performance-block"><div class="subsection-head"><h3>同日顺序不明</h3>'
        f'<span class="count-label">{_integer(performance.get("ambiguous"), "0")} 笔</span></div>'
        f'{_trade_ambiguous_table(ambiguous_rows)}</div>'
        f'<details id="unverified-excluded" class="subtle-details"><summary>规则复算未纳入统计 · { _integer(len(excluded_rows), "0") }<span class="sr-only">排除 / 未核验</span></summary>'
        '<p class="note">以下是 UNTRIGGERED、数据缺失、配置错误或 T+1 尚未到达的规则复算记录；不改写 prospective tracker。</p>'
        f'{_trade_excluded_table([])}'
        '</details>'
    )


def _average_horizon_return(rows: list[Mapping[str, Any]]) -> str:
    values = []
    for row in rows:
        value = row.get('horizon_return_value')
        if value is None:
            rendered = str(row.get('horizon_return') or '')
            if rendered.endswith('%'):
                rendered = rendered[:-1]
            try:
                value = float(rendered)
            except (TypeError, ValueError):
                value = None
        if isinstance(value, (int, float)):
            values.append(float(value))
    return _percent(sum(values) / len(values), signed=True) if values else '—'


def _research_panel(horizon: str, title: str, rows: list[Mapping[str, Any]]) -> str:
    captured = sum(row.get('snapshot_status') == 'CAPTURED' for row in rows)
    detail = _review_table(rows) if rows else '<p class="empty-state">今日无该节点到期信号。</p>'
    return (
        f'<article class="research-panel"><div class="research-panel-head">'
        f'<div><span class="research-horizon">{_esc(horizon)}</span><h3>{_esc(title)}</h3></div>'
        f'<span class="badge {"positive" if captured else "neutral"}">{_esc(_integer(captured, "0"))} 已采集</span></div>'
        f'<div class="research-stats"><div><span>到期</span><strong>{_esc(_integer(len(rows), "0"))}</strong></div>'
        f'<div><span>已采集</span><strong>{_esc(_integer(captured, "0"))}</strong></div>'
        f'<div><span>平均收益</span><strong class="{_numeric_tone(_average_horizon_return(rows))}">{_esc(_average_horizon_return(rows))}</strong></div></div>'
        f'<details class="research-detail"><summary>查看 { _esc(horizon) } 明细</summary>{detail}</details>'
        '</article>'
    )


def _action_summary(summary: Mapping[str, Any]) -> str:
    actions = []
    if summary.get('new_triggered'):
        actions.append(f"今日新触发 {summary['new_triggered']} 个")
    if summary.get('target_hits'):
        actions.append(f"今日止盈 {summary['target_hits']} 个")
    if summary.get('stop_hits'):
        actions.append(f"今日止损 {summary['stop_hits']} 个")
    if summary.get('active_signals'):
        actions.append(f"当前持仓观察 {summary['active_signals']} 个")
    if summary.get('previous_pending'):
        actions.append(f"继续等待 {summary['previous_pending']} 个")
    return '；'.join(actions) if actions else '昨日无需要执行的已核验交易事件'


def _friendly_data_state(model: ReportModel, overview: Mapping[str, Any]) -> str:
    if model.review_status == 'REVIEW_FAILED':
        return '待处理'
    if model.review_status == REVIEW_OBSERVATION_INCOMPLETE:
        return '覆盖不完整'
    if overview.get('acquisition_status') != 'COMPLETE':
        return '待核验'
    return 'READY'


def _status_pill(label: str, value: str, tone: str = 'neutral') -> str:
    return f'<span class="status-pill {tone}"><span>{_esc(label)}</span><strong>{_esc(value)}</strong></span>'


def _audit_metadata_html(metadata: Mapping[str, Any]) -> str:
    labels = {
        'list_date': '名单日期', 'review_date': '报告日期', 'previous_date': '上一交易日',
        'earliest_execution': '最早执行日', 'strategy': '策略版本',
        'frozen_candidate': '候选身份冻结', 'package_sha': '输入包 SHA',
        'generation_fingerprint': '生成 fingerprint', 'watchlist_sha': 'watchlist SHA',
        'candidate_count': '候选数量', 'report_generated_at': '生成时间',
        'review_guard': '复盘 guard', 'execution_coverage': '执行覆盖',
        'horizon_coverage': '节点覆盖', 'recovery_policy': '恢复策略',
        'recovery_evidence_root': '恢复证据根目录', 'recovery_integrity': '恢复完整性',
        'recovery_provider_calls': '恢复 provider calls',
    }
    return '<dl class="audit-metadata">' + ''.join(
        f'<div><dt>{_esc(labels.get(key, key))}</dt><dd><code>{_esc(value)}</code></dd></div>'
        for key, value in metadata.items()
    ) + '</dl>'


def _shadow_monitor_html(shadow: Mapping[str, Any]) -> str:
    """Render the observational panel without recommendation language."""

    overall = shadow.get("overall", {}) if isinstance(shadow.get("overall"), Mapping) else {}
    capture = shadow.get("capture", {}) if isinstance(shadow.get("capture"), Mapping) else {}
    if shadow.get("empty") and not capture.get("incomplete"):
        return (
            '<div class="empty-state"><strong>暂无 prospective shadow 样本</strong>'
            '<p>监控已接入，等待实际部署后的新 canonical B signal；历史信号不回填为 prospective snapshot。</p></div>'
        )
    cards = [
        ("Shadow epoch 起始日", shadow.get("epoch_start") or "—"),
        ("累计信号", _integer(overall.get("signals"), "0")),
        ("已触发", _integer(overall.get("triggered"), "0")),
        ("FAST_STOP", _integer(overall.get("fast_stop_count"), "0")),
        ("当前 regime", shadow.get("current_regime") or "—"),
    ]
    stats = '<div class="metric-strip">' + ''.join(
        f'<div class="metric-item"><span>{_esc(label)}</span><strong>{_esc(value)}</strong></div>'
        for label, value in cards
    ) + '</div>'
    if capture.get("status") == "SHADOW_CAPTURE_INCOMPLETE":
        stats += (
            '<div class="review-callout warning">'
            f'Shadow monitor data incomplete: {_esc(_integer(capture.get("complete"), "0"))}/'
            f'{_esc(_integer(capture.get("expected"), "0"))}'
            '</div>'
        )

    def market_rows(rows: Any) -> str:
        if not isinstance(rows, list) or not rows:
            return '<div class="empty-state">暂无可分层的 market regime 样本。</div>'
        body = []
        for row in rows:
            body.append([
                _text(row.get("environment")),
                _integer(row.get("n"), "0"),
                _integer(row.get("fast_stop_count"), "0"),
                _percent(row.get("fast_stop_rate")),
                _number(row.get("profit_factor")),
                _percent(row.get("expectancy"), signed=True),
            ])
        return _simple_table(
            ("环境", "样本", "FAST_STOP", "FAST_STOP rate", "PF", "Expectancy"),
            ['<tr>' + ''.join(f'<td>{_esc(cell)}</td>' for cell in row) + '</tr>' for row in body],
            table_class="metric-detail-table",
        )

    reactivation_rows = shadow.get("reactivation_rows")
    if isinstance(reactivation_rows, list) and reactivation_rows:
        reactivation_body = []
        for row in reactivation_rows:
            reactivation_body.append([
                _text(row.get("bucket")),
                _integer(row.get("sample"), "0"),
                _number(row.get("median_reactivation_vs_breakout_ratio")),
            ])
        reactivation_html = _simple_table(
            ("Outcome", "样本", "median reactivation / breakout"),
            ['<tr>' + ''.join(f'<td>{_esc(cell)}</td>' for cell in row) + '</tr>' for row in reactivation_body],
            table_class="metric-detail-table",
        )
    else:
        reactivation_html = '<div class="empty-state">暂无 reactivation 描述统计。</div>'

    return (
        stats
        + '<div class="secondary-label"><span>Market regime</span><small>仅描述，不参与正式 signal path</small></div>'
        + '<div class="table-scroll">' + market_rows(shadow.get("trend_rows")) + '</div>'
        + '<div class="secondary-label"><span>Volatility regime</span><small>固定定义版本 ' + _esc(shadow.get("definition_version", "—")) + '</small></div>'
        + '<div class="table-scroll">' + market_rows(shadow.get("vol_rows")) + '</div>'
        + '<div class="secondary-label"><span>Reactivation</span><small>continuous median；无 frozen bins</small></div>'
        + '<div class="table-scroll">' + reactivation_html + '</div>'
    )


def render_html(model: ReportModel) -> str:
    """Render a self-contained UTF-8 HTML document."""

    metadata = model.metadata
    summary = model.daily_summary
    overview = model.overview or {}
    quality_rows = model.data_quality or []
    rolling_review = model.rolling_review or {}
    trade_performance = model.trade_performance or build_strategy_rule_performance(
        [],
        {},
        metadata.get("review_date", date.today().isoformat()),
    )
    audit_performance = model.execution_audit or {}

    audit_rows = model.watchlist_rows + model.previous_signals + model.active_signals + model.closed_today
    audit_rows += [r for rows in model.review_sections.values() for r in rows]
    audit_by_id = {}
    for row in audit_rows:
        key = row.get('signal_id') or f"{row.get('code', 'unknown')}:{row.get('list_date', '')}"
        audit_by_id.setdefault(key, {}).update({k: v for k, v in row.items() if v is not None})
    audit_rows = list(audit_by_id.values())
    audit_body = [
        '<tr>' + ''.join(f'<td>{_esc(row.get(k))}</td>' for k in
                         ('code', 'signal_id', 'setup', 'status', 'raw_status', 'path_status',
                          'snapshot_status', 'snapshot_source', 'observation_source', 'source_mode'))
        + '</tr>' for row in audit_rows
    ]
    audit_html = _simple_table(
        ('代码', 'signal_id', 'Setup', 'technical status', 'raw status',
         'Execution / Path Result', 'Fixed Horizon Snapshot', 'Snapshot Source',
         'Execution Source', 'Source Mode'),
        audit_body,
        table_class='audit-table',
    )
    rule_excluded_audit_html = (
        '<details class="audit-details"><summary>规则复算未纳入统计 · '
        f'{_esc(_integer(len(trade_performance.get("excluded_rows", [])), "0"))}</summary>'
        '<div class="audit-content">'
        f'{_trade_excluded_table(trade_performance.get("excluded_rows", []))}'
        '</div></details>'
    )
    sample_label = 'SAMPLE_SMALL' if trade_performance.get('resolved_closed_trades', 0) < 10 else 'SAMPLE_READY'
    empty_sample_label = 'N/A / sample=0' if not trade_performance.get('resolved_closed_trades') else 'N/A'
    technical_audit = (
        '<div class="audit-technical"><div><span>内部样本状态</span><code>'
        f'{_esc(sample_label)}</code></div><div><span>空样本兼容标记</span><code>'
        f'{_esc(empty_sample_label)}</code></div><div><span>执行模型</span><code>'
        f'{_esc(EXECUTION_MODEL_DAILY_OHLC_T1_V1)}</code></div><div><span>缺失执行状态</span><code>'
        f'{_esc(UNVERIFIED_MISSING_EXECUTION_OBSERVATION)}</code></div><div><span>节点标签（内部）</span><code>'
        'T+5 PRIMARY REVIEW · T+10 EXTENSION / CLOSURE</code></div>'
        f'<div><span>策略规则绩效模型</span><code>{_esc(STRATEGY_RULE_PERFORMANCE_MODEL)}</code></div>'
        f'<div><span>策略绩效历史日线来源</span><code>{_esc(trade_performance.get("historical_data_source"))}</code></div>'
        f'<div><span>策略绩效 provider calls</span><code>{_esc(trade_performance.get("historical_provider_calls", 0))}</code></div></div>'
    )
    audit_summary = _esc(model.summary_text)
    issue_summary = _esc('；'.join(model.anomalies))
    acquisition_complete = overview.get('acquisition_status') == 'COMPLETE'
    cloud_verified = overview.get('cloud_checkpoint_status') == 'VERIFIED'
    review_ready = model.review_status == 'READY'
    data_state = _friendly_data_state(model, overview)
    visible_review_note = (
        '复盘读取未完成，名单仍可查看；待核验记录不会被当作正式交易。'
        if model.review_status == 'REVIEW_FAILED' else
        'prospective observation 尚未完整覆盖；策略规则绩效仍按 canonical 参数与历史日线独立复算。'
        if model.review_status == REVIEW_OBSERVATION_INCOMPLETE else
        _action_summary(summary)
    )
    review_callout_class = (
        ' warning' if model.review_status in {'REVIEW_FAILED', REVIEW_OBSERVATION_INCOMPLETE} else ''
    )
    watchlist_count = len(model.watchlist_rows)
    shadow_monitor = model.shadow_monitor or {}
    shadow_html = _shadow_monitor_html(shadow_monitor)
    research_panels = ''.join([
        _research_panel('T+3', '短期观察', model.review_sections['T+3']),
        _research_panel('T+5', '主评价', model.review_sections['T+5']),
        _research_panel('T+10', '延伸观察', model.review_sections['T+10']),
    ])

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>A股策略复盘 · { _esc(metadata.get('review_date')) }</title>
<style>
:root {{
  color-scheme: light;
  --bg: #f3f5f7;
  --surface: #ffffff;
  --surface-2: #f7f9fa;
  --text: #18232d;
  --muted: #667581;
  --border: #d9e0e5;
  --positive: #c43e3e;
  --negative: #23825a;
  --warning: #a56700;
  --accent: #28658a;
  --radius: 7px;
}}
* {{ box-sizing: border-box; }}
html {{ scroll-behavior: smooth; }}
body {{ margin: 0; background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; line-height: 1.45; }}
main {{ width: min(1440px, 100%); margin: 0 auto; padding: 18px 24px 34px; }}
h1, h2, h3, p {{ margin-top: 0; }}
h1 {{ margin-bottom: 4px; font-size: clamp(24px, 3vw, 32px); letter-spacing: -.02em; }}
h2 {{ margin-bottom: 0; font-size: 20px; letter-spacing: -.01em; }}
h3 {{ margin-bottom: 0; font-size: 15px; }}
.site-header {{ padding: 2px 0 0; }}
.header-main {{ display: flex; align-items: flex-start; justify-content: space-between; gap: 28px; padding: 2px 0 14px; }}
.eyebrow, .section-kicker, .research-horizon {{ color: var(--accent); font-size: 11px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }}
.eyebrow {{ margin-bottom: 5px; }}
.header-strategy {{ color: var(--muted); font-size: 13px; }}
.header-aside {{ display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 6px 18px; color: var(--muted); font-size: 13px; text-align: right; }}
.header-aside strong {{ color: var(--text); font-size: 17px; font-variant-numeric: tabular-nums; }}
.status-pills {{ display: flex; flex-wrap: wrap; gap: 6px; padding: 8px 0 12px; }}
.status-pill {{ display: inline-flex; align-items: center; gap: 5px; border: 1px solid var(--border); border-radius: 999px; padding: 3px 9px; background: var(--surface); color: var(--muted); font-size: 12px; white-space: nowrap; }}
.status-pill strong {{ color: var(--text); font-weight: 650; }}
.status-pill.positive {{ border-color: #d8b0b0; color: var(--positive); }}
.status-pill.positive strong {{ color: var(--positive); }}
.status-pill.warning {{ border-color: #e4c990; color: var(--warning); }}
.status-pill.warning strong {{ color: var(--warning); }}
.section-nav {{ position: sticky; top: 0; z-index: 10; display: flex; gap: 2px; overflow-x: auto; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); background: color-mix(in srgb, var(--bg) 94%, transparent); backdrop-filter: blur(8px); }}
.section-nav a {{ flex: 0 0 auto; padding: 9px 12px; color: var(--muted); font-size: 13px; text-decoration: none; white-space: nowrap; }}
.section-nav a:hover, .section-nav a:focus {{ color: var(--accent); background: var(--surface); outline: none; }}
section {{ margin: 18px 0; padding: 18px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface); }}
.toolbar {{ display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 12px 0; }}
input[type=search] {{ width: min(360px, 100%); padding: 8px 10px; border: 1px solid #b7c3cb; border-radius: 5px; background: var(--surface); color: var(--text); font: inherit; font-size: 13px; }}
.section-head {{ display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; margin-bottom: 14px; }}
.section-kicker {{ margin: 0 0 2px; }}
.section-subtitle, .note {{ margin: 5px 0 0; color: var(--muted); font-size: 13px; }}
.overview-grid {{ display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(340px, 1fr); gap: 1px; border: 1px solid var(--border); background: var(--border); }}
.overview-lead, .overview-facts {{ padding: 16px; background: var(--surface-2); }}
.overview-lead strong {{ display: block; margin: 2px 0 4px; font-size: 20px; }}
.overview-lead p:last-child {{ margin-bottom: 0; color: var(--muted); font-size: 13px; }}
.overview-facts {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; background: var(--surface); }}
.overview-facts span, .metric-item span, .funnel-item span, .research-stats span, .watch-facts label {{ display: block; color: var(--muted); font-size: 12px; }}
.overview-facts strong {{ display: block; margin-top: 4px; font-size: 14px; font-variant-numeric: tabular-nums; }}
.review-callout {{ margin: 14px 0 0; padding: 11px 13px; border-left: 3px solid var(--accent); background: #eef5f9; color: var(--text); font-size: 14px; }}
.review-callout.warning {{ border-left-color: var(--warning); background: #fff8e8; }}
.primary-kpis {{ display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 8px; }}
.kpi-card {{ min-width: 0; padding: 13px 13px 12px; border: 1px solid var(--border); border-top: 2px solid var(--accent); border-radius: var(--radius); background: var(--surface); }}
.kpi-label {{ color: var(--muted); font-size: 12px; }}
.kpi-value {{ margin-top: 7px; color: var(--text); font-size: 25px; font-weight: 720; font-variant-numeric: tabular-nums; letter-spacing: -.02em; }}
.kpi-value.positive, .number.positive, .metric-item strong.positive, .watch-facts strong.positive, .research-stats strong.positive {{ color: var(--positive); }}
.kpi-value.negative, .number.negative, .metric-item strong.negative, .watch-facts strong.negative, .research-stats strong.negative {{ color: var(--negative); }}
.kpi-value.neutral, .number.neutral, .metric-item strong.neutral {{ color: var(--text); }}
.kpi-card small, .performance-status small {{ display: block; margin-top: 5px; color: var(--muted); font-size: 11px; }}
.performance-status {{ display: flex; align-items: flex-start; gap: 10px; margin-bottom: 14px; padding: 11px 13px; border: 1px solid var(--border); border-left: 3px solid var(--accent); background: var(--surface-2); }}
.performance-status.warning {{ border-left-color: var(--warning); background: #fff8e8; }}
.performance-status strong {{ display: block; font-size: 14px; }}
.badge {{ display: inline-block; border: 1px solid currentColor; border-radius: 999px; padding: 2px 7px; color: var(--muted); font-size: 11px; line-height: 1.35; white-space: nowrap; }}
.badge.positive {{ color: var(--positive); }}
.badge.negative {{ color: var(--negative); }}
.badge.warning {{ color: var(--warning); }}
.badge.neutral {{ color: #61727f; }}
.secondary-label, .subsection-head {{ display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin: 17px 0 7px; }}
.secondary-label {{ color: var(--text); font-size: 13px; font-weight: 650; }}
.secondary-label small, .subsection-head small, .count-label {{ color: var(--muted); font-size: 11px; font-weight: 400; }}
.metric-strip {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); border: 1px solid var(--border); background: var(--border); gap: 1px; }}
.metric-item {{ min-width: 0; padding: 9px 11px; background: var(--surface-2); }}
.metric-item strong {{ display: inline-block; margin-top: 3px; font-size: 16px; font-variant-numeric: tabular-nums; }}
.metric-item small {{ margin-left: 3px; color: var(--muted); font-size: 10px; }}
.funnel {{ display: grid; grid-template-columns: repeat(8, minmax(0, 1fr)); gap: 1px; border: 1px solid var(--border); background: var(--border); }}
.funnel-item {{ min-width: 0; padding: 9px 10px; background: var(--surface-2); }}
.funnel-item strong {{ display: block; margin-top: 3px; font-size: 17px; font-variant-numeric: tabular-nums; }}
.performance-block {{ margin-top: 18px; }}
.empty-state {{ padding: 20px 15px; border: 1px dashed var(--border); background: var(--surface-2); color: var(--muted); text-align: center; }}
.empty-state strong {{ display: block; color: var(--text); font-size: 15px; }}
.empty-state p {{ max-width: 680px; margin: 7px auto 0; font-size: 13px; }}
.empty-state a {{ display: inline-block; margin-top: 10px; color: var(--accent); font-size: 13px; }}
.watchlist-list {{ display: grid; gap: 7px; }}
.watch-row {{ padding: 12px 13px; border: 1px solid var(--border); border-left: 3px solid var(--accent); background: var(--surface); }}
.watch-row:hover, .action-row:hover {{ background: #fbfcfd; border-color: #bdcbd4; }}
.watch-primary {{ display: grid; grid-template-columns: 28px minmax(170px, 1fr) 90px minmax(150px, auto); align-items: center; gap: 10px; }}
.watch-rank {{ color: var(--muted); font-size: 12px; font-variant-numeric: tabular-nums; text-align: center; }}
.security {{ display: flex; align-items: baseline; gap: 8px; min-width: 0; }}
.security strong {{ color: var(--text); font-size: 15px; font-variant-numeric: tabular-nums; white-space: nowrap; }}
.security span {{ min-width: 0; overflow: hidden; color: var(--muted); font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }}
.watch-score {{ text-align: right; }}
.watch-score span {{ color: var(--muted); font-size: 11px; }}
.watch-score strong {{ display: block; color: var(--accent); font-size: 19px; font-variant-numeric: tabular-nums; }}
.watch-state {{ display: flex; align-items: center; justify-content: flex-end; gap: 7px; }}
.watch-state small {{ color: var(--muted); font-size: 11px; }}
.watch-facts {{ display: flex; flex-wrap: wrap; gap: 5px 24px; margin: 10px 0 0 38px; }}
.watch-facts span {{ min-width: 54px; }}
.watch-facts strong {{ display: block; margin-top: 2px; font-size: 14px; font-variant-numeric: tabular-nums; }}
.watch-facts span:last-child strong {{ color: var(--text); }}
.watch-facts small {{ display: block; color: var(--muted); font-size: 10px; }}
.watch-meta {{ display: flex; flex-wrap: wrap; gap: 4px 18px; margin: 7px 0 0 38px; color: var(--muted); font-size: 11px; }}
.action-list {{ display: grid; gap: 7px; }}
.action-row {{ padding: 12px 13px; border: 1px solid var(--border); border-left: 3px solid var(--accent); background: var(--surface); }}
.action-row.positive {{ border-left-color: var(--positive); }}
.action-row.negative {{ border-left-color: var(--negative); }}
.action-row.warning {{ border-left-color: var(--warning); }}
.action-top {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; }}
.action-status {{ display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 5px; }}
.action-facts {{ display: grid; grid-template-columns: repeat(6, minmax(90px, 1fr)); gap: 10px; margin-top: 10px; }}
.action-facts strong {{ display: block; margin-top: 2px; font-size: 13px; font-variant-numeric: tabular-nums; }}
.action-bottom {{ display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; margin-top: 9px; color: var(--muted); font-size: 12px; }}
.action-bottom small {{ font-size: 11px; }}
.research-panels {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 9px; }}
.research-panel {{ min-width: 0; padding: 13px; border: 1px solid var(--border); background: var(--surface-2); }}
.research-panel-head {{ display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }}
.research-horizon {{ display: block; margin-bottom: 2px; }}
.research-stats {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 7px; margin: 14px 0; }}
.research-stats strong {{ display: block; margin-top: 3px; font-size: 15px; font-variant-numeric: tabular-nums; }}
.research-detail {{ border-top: 1px solid var(--border); }}
summary {{ cursor: pointer; padding: 9px 0 2px; color: var(--accent); font-size: 12px; }}
summary:focus {{ outline: 2px solid #9bc0d6; outline-offset: 2px; }}
.table-scroll {{ width: 100%; overflow-x: auto; }}
table {{ width: 100%; min-width: 1020px; border-collapse: collapse; font-size: 12px; }}
th, td {{ padding: 7px 8px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: top; white-space: nowrap; }}
th {{ position: sticky; top: 0; z-index: 1; background: #edf2f5; color: #40515e; font-weight: 650; }}
tbody tr:nth-child(even) {{ background: #fbfcfd; }}
tbody tr:hover {{ background: #f1f6f8; }}
td:nth-child(n+4) {{ font-variant-numeric: tabular-nums; }}
.metric-details {{ margin-top: 12px; }}
.metric-detail-table {{ min-width: 560px; }}
.trade-table {{ min-width: 1260px; }}
.audit-table {{ min-width: 1180px; }}
.quality-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 7px; }}
.quality-item {{ display: grid; grid-template-columns: 1fr auto; gap: 2px 8px; padding: 10px 11px; border: 1px solid var(--border); background: var(--surface-2); }}
.quality-item > span {{ color: var(--muted); font-size: 12px; }}
.quality-item > strong {{ font-size: 18px; font-variant-numeric: tabular-nums; }}
.quality-item .badge {{ grid-column: 1 / -1; justify-self: start; }}
.quality-item small {{ grid-column: 1 / -1; color: var(--muted); font-size: 11px; }}
.quality-ok {{ display: flex; align-items: center; gap: 9px; padding: 11px 12px; border: 1px solid var(--border); background: var(--surface-2); color: var(--muted); font-size: 13px; }}
.coverage-strip {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 1px; border: 1px solid var(--border); background: var(--border); }}
.coverage-strip div {{ padding: 9px 10px; background: var(--surface-2); }}
.coverage-strip strong {{ display: block; margin-top: 3px; font-variant-numeric: tabular-nums; }}
.subtle-details {{ margin-top: 18px; border-top: 1px solid var(--border); }}
.subtle-details > summary {{ color: var(--text); font-weight: 650; }}
#audit, .audit-details {{ margin: 18px 0 0; border: 1px solid var(--border); background: var(--surface-2); }}
#audit > summary, .audit-details > summary {{ padding: 12px 14px; color: var(--text); font-weight: 650; }}
.audit-content {{ padding: 0 14px 14px; }}
.audit-metadata {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1px; margin: 0 0 14px; border: 1px solid var(--border); background: var(--border); }}
.audit-metadata div {{ min-width: 0; padding: 8px 10px; background: var(--surface); }}
.audit-metadata dt {{ color: var(--muted); font-size: 11px; }}
.audit-metadata dd {{ margin: 3px 0 0; overflow-wrap: anywhere; font-size: 12px; }}
.audit-technical {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 7px; margin: 0 0 14px; }}
.audit-technical div {{ min-width: 0; padding: 8px 10px; border: 1px solid var(--border); background: var(--surface); }}
.audit-technical span {{ display: block; color: var(--muted); font-size: 11px; }}
.audit-technical code {{ display: block; margin-top: 3px; overflow-wrap: anywhere; font-size: 11px; }}
.audit-text {{ max-height: 170px; overflow: auto; padding: 9px; border: 1px solid var(--border); background: var(--surface); color: var(--muted); font: 11px/1.45 Consolas, "SFMono-Regular", monospace; white-space: pre-wrap; }}
code {{ overflow-wrap: anywhere; }}
footer {{ padding: 10px 0 0; color: var(--muted); font-size: 11px; }}
.sr-only {{ position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }}
@media (max-width: 1050px) {{
  .primary-kpis {{ grid-template-columns: repeat(3, 1fr); }}
  .funnel {{ grid-template-columns: repeat(4, 1fr); }}
  .quality-grid {{ grid-template-columns: repeat(2, 1fr); }}
}}
@media (max-width: 760px) {{
  main {{ padding: 12px 10px 24px; }}
  .header-main, .section-head {{ display: block; }}
  .header-aside {{ justify-content: flex-start; margin-top: 12px; text-align: left; }}
  section {{ padding: 13px; }}
  .overview-grid {{ grid-template-columns: 1fr; }}
  .overview-facts {{ grid-template-columns: repeat(3, 1fr); }}
  .primary-kpis {{ grid-template-columns: repeat(2, 1fr); }}
  .metric-strip {{ grid-template-columns: repeat(3, 1fr); }}
  .funnel {{ grid-template-columns: repeat(2, 1fr); }}
  .watch-primary {{ grid-template-columns: 24px minmax(0, 1fr) auto; }}
  .watch-state {{ grid-column: 2 / -1; justify-content: flex-start; }}
  .watch-facts, .watch-meta {{ margin-left: 32px; }}
  .action-facts {{ grid-template-columns: repeat(3, 1fr); }}
  .research-panels {{ grid-template-columns: 1fr; }}
  .coverage-strip {{ grid-template-columns: repeat(2, 1fr); }}
  .audit-metadata, .audit-technical {{ grid-template-columns: 1fr; }}
}}
@media (max-width: 460px) {{
  .overview-facts {{ grid-template-columns: 1fr; gap: 8px; }}
  .metric-strip, .action-facts {{ grid-template-columns: repeat(2, 1fr); }}
  .watch-facts {{ gap: 5px 15px; }}
}}
</style>
</head>
<body>
<main>
<header class="site-header">
  <div class="eyebrow">A 股策略复盘</div>
  <div class="header-main">
    <div><h1>{_esc(metadata.get('review_date'))} · {_esc(metadata.get('strategy'))}</h1>
      <div class="header-strategy">{_esc(metadata.get('review_date'))} {_esc('周' + '一二三四五六日'[parse_date(metadata.get('review_date')).weekday()])} · T-close</div></div>
    <div class="header-aside"><span>新名单 <strong>{_esc(_integer(watchlist_count, '0'))}</strong> 只</span><span>最早执行 <strong>{_esc(metadata.get('earliest_execution'))}</strong></span></div>
  </div>
  <div class="status-pills">
    {_status_pill('T+1', '日线', 'neutral')}
    {_status_pill('证据', '完整' if acquisition_complete else '待核验', 'positive' if acquisition_complete else 'warning')}
    {_status_pill('复盘', '就绪' if review_ready else '待处理', 'positive' if review_ready else 'warning')}
    {_status_pill('云端', '已验证' if cloud_verified else '仅本地', 'positive' if cloud_verified else 'neutral')}
  </div>
  <nav class="section-nav" aria-label="报告章节导航">
    <a href="#overview">总览</a><a href="#trade-performance">绩效</a><a href="#tomorrow-watchlist">新名单</a><a href="#shadow-monitor">Shadow Monitor</a><a href="#daily-review">复盘</a><a href="#formal-review">节点研究</a><a href="#anomalies">数据质量</a>
  </nav>
</header>

<section id="overview">
  <div class="section-head"><div><p class="section-kicker">01 · OVERVIEW</p><h2>今日总览</h2><p class="section-subtitle">先看行动信息，再看交易结果；技术细节收纳在审计区。</p></div><span class="badge {_status_class(data_state)}">数据状态：{_esc(data_state)}</span></div>
  <div class="overview-grid"><div class="overview-lead"><span class="eyebrow">当前阅读重点</span><strong>{_esc(visible_review_note)}</strong><p>策略规则绩效按 canonical trigger / stop / target 与历史 daily OHLC 理论复算；不代表真实成交。</p></div><div class="overview-facts"><div><span>名单日期</span><strong>{_esc(metadata.get('list_date'))}</strong></div><div><span>最早执行</span><strong>{_esc(metadata.get('earliest_execution'))}</strong></div><div><span>候选数量</span><strong>{_esc(_integer(watchlist_count, '0'))}</strong></div></div></div>
  <div class="review-callout{review_callout_class}">{_esc(visible_review_note)}</div>
</section>

<section id="trade-performance">
  <div class="section-head"><div><p class="section-kicker">02 · PERFORMANCE · 交易绩效</p><h2>策略规则绩效</h2><p class="section-subtitle">假设每个信号严格按 trigger 入场、stop / target 规则价退出；买入当日不可卖出，遵守 A 股 T+1。规则价模拟不代表用户真实成交。</p></div></div>
  {_trade_performance_html(trade_performance, new_signal_count=watchlist_count, list_date=metadata.get('list_date', '—'), earliest_execution=metadata.get('earliest_execution', '—'))}
</section>

<section id="tomorrow-watchlist">
  <div class="section-head"><div><p class="section-kicker">03 · WATCHLIST</p><h2>今日新名单 · {watchlist_count}</h2><p class="section-subtitle">按 Score 从高到低；触发、止损、目标和 RR 为计划参数。</p></div></div>
  <div class="toolbar"><label for="watchlist-search" class="note">搜索名单：</label><input id="watchlist-search" type="search" placeholder="输入代码、名称或行业" autocomplete="off"></div>
  {_watchlist_table(model.watchlist_rows, metadata.get('earliest_execution'))}
</section>

<section id="shadow-monitor">
  <div class="section-head"><div><p class="section-kicker">04 · PROSPECTIVE SHADOW MONITOR</p><h2>Prospective Shadow Monitor</h2><p class="section-subtitle">仅记录市场环境、再启动量能与后续结果；不参与正式名单、评分、排序或交易参数。</p></div></div>
  {shadow_html}
</section>

<section id="daily-review">
  <div class="section-head"><div><p class="section-kicker">05 · REVIEW</p><h2>昨日 / 活跃信号复盘</h2><p class="section-subtitle">优先显示今日新触发、止盈、止损、持仓与等待事项。</p></div></div>
  <p class="section-summary">昨日名单今日表现 · {_esc(metadata.get('previous_date'))} · 共 {_esc(_integer(summary.get('previous_total'), '0'))} 个信号</p>
  <h3>昨日名单今日表现 · {_esc(metadata.get('previous_date'))}</h3>
  {_daily_table(model.previous_signals)}
  <h3 class="subsection-title">历史仍在观察 · {_esc(_integer(len(model.active_signals), '0'))}</h3>
  {_active_review_html(model.active_signals)}
  {('<h3 class="subsection-title">今日结束 · ' + _esc(_integer(len(model.closed_today), '0')) + '</h3>' + _daily_table(model.closed_today)) if model.closed_today else ''}
</section>

<section id="formal-review">
  <div class="section-head"><div><p class="section-kicker">06 · RESEARCH</p><h2>固定节点研究</h2><p class="section-subtitle">T+3 / T+5 / T+10 为研究快照，不等同于真实交易盈亏。</p></div></div>
  <div class="research-panels">{research_panels}</div>
  <details class="metric-details"><summary>查看节点覆盖</summary>{_rolling_review_html(rolling_review)}</details>
</section>

<section id="anomalies">
  <div class="section-head"><div><p class="section-kicker">07 · DATA QUALITY</p><h2>数据质量</h2><p class="section-subtitle">只显示需要关注的异常；正常采集状态合并为单一提示。</p></div></div>
  {_quality_table(quality_rows, performance=trade_performance, audit_performance=audit_performance, summary=summary, acquisition_status=overview.get('acquisition_status', _UNVERIFIED), review_status=model.review_status, shadow_monitor=shadow_monitor)}
</section>

<details id="audit">
  <summary>技术与审计信息</summary>
  <div class="audit-content">
    {_audit_metadata_html(metadata)}
    {technical_audit}
    <p class="note">内部复盘摘要</p><pre class="audit-text">{audit_summary}</pre>
    <p class="note">内部异常记录</p><pre class="audit-text">{issue_summary}</pre>
    {audit_html}
    {rule_excluded_audit_html}
  </div>
</details>
<footer>本报告仅整理正式观察名单与 tracker 的真实记录。缺少记录统一显示为 —，不回填历史行情。</footer>
</main>
<script>
(function () {{
  const search = document.getElementById('watchlist-search');
  const list = document.getElementById('watchlist-table');
  if (!search || !list) return;
  const rows = () => Array.from(list.querySelectorAll('.watch-row'));
  search.addEventListener('input', function () {{
    const query = search.value.trim().toLowerCase();
    rows().forEach(function (row) {{ row.hidden = query !== '' && !(row.dataset.search || '').includes(query); }});
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
