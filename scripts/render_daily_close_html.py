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
        status = signal.get("status") if isinstance(signal, Mapping) else None
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
        row = {
            'code': signal.get('code'), 'name': signal.get('name'),
            'signal_id': signal.get('signal_id'), 'list_date': list_date,
            'score': signal.get('score'), 'original_trigger': signal.get('trigger'),
            'today_open': observation.get('open') if observation else None,
            'today_high': observation.get('high') if observation else None,
            'today_low': observation.get('low') if observation else None,
            'today_close': observation.get('price') if observation else None,
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
    for rows in groups:
        rows.sort(key=lambda row: (row['list_date'], str(row['code']), str(row['signal_id'])))
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
    watchlist_rows = _watchlist_rows(watchlist, tracker)

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
    }
    summary_text = (
        f"今日复盘 {summary['tracked']} 个历史信号，其中新触发 {summary['new_triggered']} 个、"
        f"目标达成 {summary['target_hits']} 个、止损 {summary['stop_hits']} 个、"
        f"仍观察 {summary['active_signals']} 个、已过期 {summary['expired']} 个、"
        f"同日顺序不明 {summary['ambiguous']} 个、数据缺失 {summary['daily_missing']} 个。"
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
        values += [_esc(row.get('sector'))]
        search = ' '.join(str(row.get(k, '')) for k in ('code', 'name', 'sector')).lower()
        body.append(f'<tr data-search="{_esc(search)}">' + ''.join(f'<td>{v}</td>' for v in values) + '</tr>')
    return _simple_table(('排名', '代码', '名称', 'Score', '收盘', 'Trigger', '距 Trigger',
                          'Stop', 'Target', 'RR', '行业'), body, 'watchlist-table')


def _daily_table(rows):
    if not rows:
        return '<p class="note">暂无符合条件的记录。</p>'
    body = []
    for row in rows:
        values = [_esc(row.get(k)) for k in ('code', 'name', 'list_date', 'score')]
        values += [_esc(_number(row.get(k))) for k in
                   ('original_trigger', 'today_open', 'today_high', 'today_low', 'today_close')]
        values += [_esc(_percent(row['close_vs_trigger_pct'], signed=True)
                        if row['close_vs_trigger_pct'] is not None else '—')]
        values += [_ui_badge(row['path_status']), _esc(row.get('observation_source', '数据缺失')), _esc(row['note'])]
        body.append('<tr>' + ''.join(f'<td>{v}</td>' for v in values) + '</tr>')
    return _simple_table(('代码', '名称', '名单日期', 'Score', 'Trigger', '今日开盘',
                          '今日最高', '今日最低', '今日收盘', '收盘较 Trigger %', '今日状态', '记录来源', '结果说明'), body)


def render_html(model: ReportModel) -> str:
    """Render a self-contained UTF-8 HTML document."""

    metadata = model.metadata
    summary = model.daily_summary
    cards = [
        ('今日新名单', metadata['candidate_count']), ('昨日/近期复盘信号数', summary['tracked']),
        ('今日新触发', summary['new_triggered']), ('今日目标', summary['target_hits']),
        ('今日止损', summary['stop_hits']), ('今日仍观察', summary['active_signals']),
        ('T+5 PRIMARY 到期数', summary['t5_count']),
        ('异常数', len([a for a in model.anomalies if a != 'NONE'])),
    ]
    card_html = ''.join(f'<div class="card"><div class="card-label">{label}</div>'
                        f'<div class="card-value">{value}</div></div>' for label, value in cards)
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
    labels = {_MISSING: '数据缺失：历史节点或今日记录缺失',
              'AMBIGUOUS_SAME_BAR': '同日顺序不明', _UNVERIFIED: '数据待核验',
              REVIEW_OBSERVATION_INCOMPLETE: '复盘数据不完整：执行观察或固定节点覆盖不足'}
    anomaly_html = ('<ul>' + ''.join('<li>' + _esc(labels.get(a, '复盘失败：' + a)) + '</li>' for a in issues)
                    + '</ul>') if issues else '<p>数据状态：正常</p>'
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
<section id="daily-review">
<h2>今日复盘</h2>
<h3>昨日名单今日表现 · {metadata['previous_date']}</h3>
{_daily_table(model.previous_signals)}
<h3>历史仍在观察</h3>
{_daily_table(model.active_signals)}
{('<h3>今日结束</h3>' + _daily_table(model.closed_today)) if model.closed_today else ''}
</section>
<section id="tomorrow-watchlist">
<h2>明日观察名单</h2>
<p class="note">共 {metadata['candidate_count']} 个 · 按 Score 从高到低排列。位置标签仅供阅读，不改变筛选或交易规则。</p>
<div class="toolbar"><label for="watchlist-search">搜索：</label><input id="watchlist-search" type="search" placeholder="输入代码、名称或行业" autocomplete="off"></div>
{_watchlist_table(model.watchlist_rows)}
</section>
<section id="formal-review">
<h2>正式节点复盘</h2>
<p class="note">节点收益是固定期限快照，与触发、目标及止损等路径结果分开记录。</p>
{''.join(review_html)}
</section>
<section id="anomalies"><h2>异常</h2>{anomaly_html}</section>
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
