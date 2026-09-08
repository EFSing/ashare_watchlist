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
    load_tracker,
    parse_date,
    review_date,
)
from trading_calendar import TradingCalendar, default_calendar
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
    anomalies: list[str]
    summary_text: str
    review_status: str


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
        return load_tracker(tracker_path), failures
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
            snapshot_status = _status_text(status)
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
                }
            )
    for rows in sections.values():
        rows.sort(key=lambda row: (str(row.get("code", "")), str(row.get("signal_id", ""))))
    return sections, issues, missing_count


def _active_signal_rows(
    tracker: Mapping[str, Any] | None,
    report_date: str,
    calendar: TradingCalendar,
) -> list[dict[str, Any]]:
    signals = tracker.get("signals", {}) if isinstance(tracker, Mapping) else {}
    signals = signals if isinstance(signals, Mapping) else {}
    rows: list[dict[str, Any]] = []
    for signal in signals.values():
        if not isinstance(signal, Mapping) or signal.get("status") not in {"pending", "triggered"}:
            continue
        if parse_date(signal["date"]) > parse_date(report_date):
            continue
        observation = _observation_for_date(signal, report_date)
        next_horizon = "CLOSED"
        for horizon, _offset in REVIEW_HORIZONS:
            point = _point_for_signal(signal, horizon, calendar)
            if str(point.get("status")) == "PENDING" and parse_date(point["review_trading_date"]) > parse_date(report_date):
                next_horizon = f"{horizon} ({point['review_trading_date']})"
                break
        rows.append(
            {
                "code": signal.get("code"),
                "name": signal.get("name"),
                "signal_id": signal.get("signal_id"),
                "list_date": signal.get("date"),
                "original_trigger": signal.get("trigger"),
                "stop": signal.get("stop"),
                "target": signal.get("target"),
                "today_close": observation.get("price") if observation else None,
                "today_high": observation.get("high") if observation else None,
                "today_low": observation.get("low") if observation else None,
                "path_status": _status_text(signal.get("status")),
                "days_tracked": signal.get("days_tracked"),
                "next_formal_horizon": next_horizon,
            }
        )
    rows.sort(key=lambda row: (str(row.get("code", "")), str(row.get("signal_id", ""))))
    return rows


def _daily_summary(
    tracker: Mapping[str, Any] | None,
    report_date: str,
    review_sections: Mapping[str, list[Mapping[str, Any]]],
    missing_count: int,
) -> dict[str, int | str]:
    signals = tracker.get("signals", {}) if isinstance(tracker, Mapping) else {}
    signals = signals if isinstance(signals, Mapping) else {}
    values = [signal for signal in signals.values() if isinstance(signal, Mapping)]
    active = [
        signal for signal in values
        if signal.get("status") in {"pending", "triggered"}
        and parse_date(signal["date"]) <= parse_date(report_date)
    ]
    return {
        "active_signals": len(active),
        "new_triggered": sum(1 for signal in values if signal.get("first_trigger_date") == report_date),
        "target_hits": sum(1 for signal in values if signal.get("status") == "win" and signal.get("close_date") == report_date),
        "stop_hits": sum(1 for signal in values if signal.get("status") == "loss" and signal.get("close_date") == report_date),
        "ambiguous": sum(
            1 for signal in values
            if signal.get("status") == "AMBIGUOUS_SAME_BAR" and signal.get("close_date") == report_date
        ),
        "missing_observations": missing_count,
        "t3_count": len(review_sections.get("T+3", [])),
        "t5_count": len(review_sections.get("T+5", [])),
        "t10_count": len(review_sections.get("T+10", [])),
    }


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
    if watchlist["date"] != normalized_date:
        raise ValueError(f"watchlist date {watchlist['date']} != report date {normalized_date}")

    cal = calendar or default_calendar()
    tracker, review_failures = _load_review_tracker(resolver, review_failure)
    review_sections, review_issues, missing_count = _review_rows(tracker, normalized_date, cal)
    active_signals = _active_signal_rows(tracker, normalized_date, cal)
    watchlist_rows = _watchlist_rows(watchlist, tracker)

    anomalies = list(review_failures)
    anomalies.extend(review_issues)
    if tracker is not None:
        for signal in tracker.get("signals", {}).values():
            if not isinstance(signal, Mapping):
                continue
            if signal.get("status") == "AMBIGUOUS_SAME_BAR" or signal.get("ambiguity_reason"):
                anomalies.append("AMBIGUOUS_SAME_BAR")
    anomalies = _dedupe(anomalies)
    display_anomalies = anomalies or ["NONE"]

    package_sha, generation_fingerprint = _package_metadata(resolver, normalized_date)
    earliest_execution = review_date(normalized_date, 1, cal)
    generated = generated_at or datetime.now(_BJT)
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=_BJT)
    generated = generated.astimezone(_BJT)
    review_status = _REVIEW_FAILURE if review_failures else "READY"
    summary = _daily_summary(tracker, normalized_date, review_sections, missing_count)
    summary_text = (
        f"今日新名单 {len(watchlist_rows)} 个；最高 score "
        f"{watchlist_rows[0]['score'] if watchlist_rows else '—'}；"
        f"active signal {summary['active_signals']} 个；"
        f"target / stop {summary['target_hits']} / {summary['stop_hits']}；"
        f"今日到期 T+5 {summary['t5_count']} 个；"
        f"missing {summary['missing_observations']}。"
    )
    metadata = {
        "list_date": normalized_date,
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
    return ReportModel(
        metadata=metadata,
        watchlist_rows=watchlist_rows,
        daily_summary=summary,
        review_sections={label: list(rows) for label, rows in review_sections.items()},
        active_signals=active_signals,
        anomalies=display_anomalies,
        summary_text=summary_text,
        review_status=review_status,
    )


def _esc(value: Any) -> str:
    return html.escape(_text(value), quote=True)


def _badge(value: Any) -> str:
    text = _status_text(value)
    return f'<span class="badge { _status_class(text) }">{_esc(text)}</span>'


def _table_empty(colspan: int) -> str:
    return f'<tr><td class="empty" colspan="{colspan}">NONE / 当前报告日没有到期记录</td></tr>'


def _review_table(rows: list[Mapping[str, Any]]) -> str:
    if not rows:
        return f"<table class=\"review-table\"><thead><tr><th>Code</th><th>Name</th><th>Signal ID</th><th>List Date</th><th>Review Date</th><th>Fixed Horizon Snapshot Return</th><th>Execution / Path Result</th><th>Fixed Horizon Snapshot Status</th></tr></thead><tbody>{_table_empty(8)}</tbody></table>"
    body = []
    for row in rows:
        body.append(
            "<tr>"
            f"<td>{_esc(row.get('code'))}</td>"
            f"<td>{_esc(row.get('name'))}</td>"
            f"<td class=\"signal-id\">{_esc(row.get('signal_id'))}</td>"
            f"<td>{_esc(row.get('list_date'))}</td>"
            f"<td>{_esc(row.get('review_date'))}</td>"
            f"<td>{_esc(row.get('horizon_return'))}</td>"
            f"<td>{_badge(row.get('path_status'))}</td>"
            f"<td>{_badge(row.get('snapshot_status'))}</td>"
            "</tr>"
        )
    return (
        '<table class="review-table"><thead><tr>'
        "<th>Code</th><th>Name</th><th>Signal ID</th><th>List Date</th><th>Review Date</th>"
        "<th>Fixed Horizon Snapshot Return</th><th>Execution / Path Result</th>"
        "<th>Fixed Horizon Snapshot Status</th>"
        f"</tr></thead><tbody>{''.join(body)}</tbody></table>"
    )


def _watchlist_table(rows: list[Mapping[str, Any]]) -> str:
    body = []
    for row in rows:
        search = " ".join(str(row.get(key, "")) for key in ("code", "name", "sector")).lower()
        body.append(
            f'<tr data-search="{_esc(search)}">'
            f'<td data-sort-value="{row["rank"]}">{row["rank"]}</td>'
            f'<td data-sort-value="{_esc(row.get("code"))}">{_esc(row.get("code"))}</td>'
            f'<td data-sort-value="{_esc(row.get("name"))}">{_esc(row.get("name"))}</td>'
            f'<td data-sort-value="{row.get("score", "")}">{_esc(row.get("score"))}</td>'
            f'<td data-sort-value="{row.get("close", "")}">{_esc(_number(row.get("close")))}</td>'
            f'<td data-sort-value="{row.get("trigger", "")}">{_esc(_number(row.get("trigger")))}</td>'
            f'<td data-sort-value="{row.get("stop", "")}">{_esc(_number(row.get("stop")))}</td>'
            f'<td data-sort-value="{row.get("target", "")}">{_esc(_number(row.get("target")))}</td>'
            f'<td data-sort-value="{row.get("rr", "")}">{_esc(_number(row.get("rr")))}</td>'
            f'<td data-sort-value="{row.get("distance_to_trigger_pct", "")}">{_esc(_percent(row.get("distance_to_trigger_pct"), signed=True))}</td>'
            f'<td data-sort-value="{_esc(row.get("setup"))}">{_esc(row.get("setup"))}</td>'
            f'<td data-sort-value="{_esc(row.get("sector"))}">{_esc(row.get("sector"))}</td>'
            f'<td>{_badge(row.get("status"))}</td>'
            "</tr>"
        )
    return (
        '<table id="watchlist-table"><thead><tr>'
        '<th data-sort-key="rank">Rank</th><th data-sort-key="code">Code</th>'
        '<th data-sort-key="name">Name</th><th data-sort-key="score">Score</th>'
        '<th data-sort-key="close">今日收盘</th><th data-sort-key="trigger">Trigger</th>'
        '<th data-sort-key="stop">Stop</th><th data-sort-key="target">Target</th>'
        '<th data-sort-key="rr">RR</th><th data-sort-key="distance">距 Trigger %</th>'
        '<th data-sort-key="setup">Setup</th><th data-sort-key="sector">Sector</th><th>Status</th>'
        f"</tr></thead><tbody>{''.join(body)}</tbody></table>"
    )


def _active_table(rows: list[Mapping[str, Any]]) -> str:
    headers = (
        "Code", "Name", "Signal ID", "List Date", "Original Trigger", "Stop", "Target",
        "Today Close", "Today High", "Today Low", "Path Status", "Days Tracked", "Next Formal Horizon",
    )
    if not rows:
        return f'<table class="active-table"><thead><tr>{"".join(f"<th>{header}</th>" for header in headers)}</tr></thead><tbody>{_table_empty(len(headers))}</tbody></table>'
    body = []
    for row in rows:
        body.append(
            "<tr>"
            f"<td>{_esc(row.get('code'))}</td><td>{_esc(row.get('name'))}</td>"
            f"<td class=\"signal-id\">{_esc(row.get('signal_id'))}</td><td>{_esc(row.get('list_date'))}</td>"
            f"<td>{_esc(_number(row.get('original_trigger')))}</td><td>{_esc(_number(row.get('stop')))}</td>"
            f"<td>{_esc(_number(row.get('target')))}</td><td>{_esc(_number(row.get('today_close'), fallback=_UNVERIFIED))}</td>"
            f"<td>{_esc(_number(row.get('today_high'), fallback=_UNVERIFIED))}</td><td>{_esc(_number(row.get('today_low'), fallback=_UNVERIFIED))}</td>"
            f"<td>{_badge(row.get('path_status'))}</td><td>{_esc(row.get('days_tracked'))}</td>"
            f"<td>{_esc(row.get('next_formal_horizon'))}</td>"
            "</tr>"
        )
    return f'<table class="active-table"><thead><tr>{"".join(f"<th>{header}</th>" for header in headers)}</tr></thead><tbody>{"".join(body)}</tbody></table>'


def render_html(model: ReportModel) -> str:
    """Render a self-contained UTF-8 HTML document."""

    metadata = model.metadata
    summary = model.daily_summary
    cards = [
        ("Candidates", metadata["candidate_count"], "normal"),
        ("Active Signals", summary["active_signals"], "warning"),
        ("New Triggered", summary["new_triggered"], "target"),
        ("Target Hits", summary["target_hits"], "target"),
        ("Stop Hits", summary["stop_hits"], "loss"),
        ("Ambiguous", summary["ambiguous"], "warning"),
        ("Missing Observations", summary["missing_observations"], "missing"),
        ("Review Status", model.review_status, _status_class(model.review_status)),
    ]
    card_html = "".join(
        f'<div class="card {kind}"><div class="card-label">{_esc(label)}</div><div class="card-value">{_esc(value)}</div></div>'
        for label, value, kind in cards
    )
    metadata_html = "".join(
        f'<div class="meta-item"><span>{_esc(label)}</span><strong>{_esc(value)}</strong></div>'
        for label, value in (
            ("list date", metadata["list_date"]),
            ("review date", metadata["review_date"]),
            ("earliest execution", metadata["earliest_execution"]),
            ("strategy", metadata["strategy"]),
            ("frozen candidate", metadata["frozen_candidate"]),
            ("package SHA", metadata["package_sha"]),
            ("generation fingerprint", metadata["generation_fingerprint"]),
            ("watchlist SHA", metadata["watchlist_sha"]),
            ("candidate count", metadata["candidate_count"]),
            ("report generated_at", metadata["report_generated_at"]),
        )
    )
    anomaly_html = "".join(
        f'<li class="{_status_class(item)}"><code>{_esc(item)}</code></li>' for item in model.anomalies
    )
    failure_html = ""
    failures = [item for item in model.anomalies if item.startswith(f"{_REVIEW_FAILURE}:")]
    if failures:
        failure_html = (
            '<div class="callout warning"><strong>REVIEW_FAILED</strong>'
            f"<p>{_esc('；'.join(failures))}</p></div>"
        )
    horizon_notes = {
        "T+3": "T+3 · short-term evaluation",
        "T+5": "T+5 PRIMARY REVIEW · primary review horizon",
        "T+10": "T+10 EXTENSION / CLOSURE · routine extension and closure",
    }
    review_html = []
    for horizon, _offset in REVIEW_HORIZONS:
        review_html.append(
            f'<section><h2>{_esc(horizon_notes[horizon])}</h2>'
            '<p class="note">只显示 review_trading_date 等于本报告 review date 的正式节点；'
            'Execution / Path Result 与 Fixed Horizon Snapshot 分开。</p>'
            f"{_review_table(model.review_sections[horizon])}</section>"
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
main {{ max-width:1700px; margin:0 auto; padding:24px; }}
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
<h1>A股交易系统 — 每日收盘报告</h1>
<p class="subtitle">明日观察名单 + 今日复盘 · offline self-contained report</p>
<div class="meta-grid">{metadata_html}</div>
</header>
<div class="cards">{card_html}</div>
<section>
<h2>明日观察名单</h2>
<p class="note">数据源：正式 canonical watchlist；默认 Score DESC。距 Trigger % = (trigger / close - 1) × 100%，仅用于展示，不改变 frozen B semantics。</p>
<div class="toolbar"><label for="watchlist-search">搜索 code / name / sector：</label><input id="watchlist-search" type="search" placeholder="输入代码、名称或行业" autocomplete="off"></div>
<div class="table-wrap">{_watchlist_table(model.watchlist_rows)}</div>
</section>
<section>
<h2>今日复盘总览</h2>
<p class="note">Summary 只来自 tracker 状态；不使用当前 quote 反推过去路径。</p>
{failure_html}
<div class="table-wrap"><table class="summary-table"><thead><tr><th>Active Signals</th><th>New Triggered</th><th>Target Hits</th><th>Stop Hits</th><th>Ambiguous</th><th>Missing Observations</th><th>T+3</th><th>T+5 PRIMARY</th><th>T+10</th></tr></thead><tbody><tr><td>{summary['active_signals']}</td><td>{summary['new_triggered']}</td><td>{summary['target_hits']}</td><td>{summary['stop_hits']}</td><td>{summary['ambiguous']}</td><td>{summary['missing_observations']}</td><td>{summary['t3_count']}</td><td>{summary['t5_count']}</td><td>{summary['t10_count']}</td></tr></tbody></table></div>
</section>
{''.join(review_html)}
<section>
<h2>Active Signals 今日状态</h2>
<p class="note">today close / high / low 只接受 tracker 中 quote_date 等于本报告 review date 的真实 observation；缺失显示 UNVERIFIED。</p>
<div class="table-wrap">{_active_table(model.active_signals)}</div>
</section>
<section>
<h2>异常 / 数据缺失</h2>
<ul class="anomalies">{anomaly_html}</ul>
</section>
<section>
<h2>今日总结</h2>
<p>{_esc(model.summary_text)}</p>
</section>
<footer>本报告仅整理 canonical watchlist 与正式 tracker 数据；不包含主观荐股、新闻解释或未经 formal contract 定义的市场判断。</footer>
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
  table.querySelectorAll('th[data-sort-key]').forEach(function (header, index) {{
    let direction = index === 3 ? -1 : 1;
    header.addEventListener('click', function () {{
      const sorted = rows().sort(function (left, right) {{
        const a = left.cells[index].dataset.sortValue || left.cells[index].textContent.trim();
        const b = right.cells[index].dataset.sortValue || right.cells[index].textContent.trim();
        const na = Number(a), nb = Number(b);
        if (Number.isFinite(na) && Number.isFinite(nb)) return (na - nb) * direction;
        return a.localeCompare(b, 'zh-Hans-CN') * direction;
      }});
      sorted.forEach(function (row) {{ body.appendChild(row); }});
      direction *= -1;
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
