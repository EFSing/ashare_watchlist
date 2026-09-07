#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
"""观察名单验证闭环跟踪器。

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
TRACK_DAYS = REVIEW_HORIZONS[-1][1]
REVIEW_POINT_PENDING = "PENDING"
REVIEW_POINT_CAPTURED = "CAPTURED"
REVIEW_POINT_NOT_CAPTURED = "NOT_CAPTURED"


class TrackerSchemaError(ValueError):
    """The tracker is neither the supported v2 model nor migratable v1."""


def new_tracker() -> dict[str, Any]:
    return {"version": 2, "signals": {}, "updated": None}


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


def _new_review_points(signal_date: str, calendar: TradingCalendar) -> dict[str, dict[str, Any]]:
    return {
        label: {
            "offset": offset,
            "scheduled_date": review_date(signal_date, offset, calendar),
            "status": REVIEW_POINT_PENDING,
            "quote_date": None,
            "price": None,
            "high": None,
            "low": None,
            "signal_status": None,
            "reason": None,
        }
        for label, offset in REVIEW_HORIZONS
    }


def _ensure_review_points(signal: dict[str, Any], calendar: TradingCalendar) -> dict[str, dict[str, Any]]:
    """Add/validate fixed review dates without rewriting captured outcomes."""

    points = signal.get("review_points")
    if not isinstance(points, dict):
        points = {}
        signal["review_points"] = points
    for label, offset in REVIEW_HORIZONS:
        expected_date = review_date(signal["date"], offset, calendar)
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
        point.setdefault("offset", offset)
        point.setdefault("scheduled_date", expected_date)
        point.setdefault("status", REVIEW_POINT_PENDING)
        point.setdefault("quote_date", None)
        point.setdefault("price", None)
        point.setdefault("high", None)
        point.setdefault("low", None)
        point.setdefault("signal_status", None)
        point.setdefault("reason", None)
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
            raise TrackerSchemaError(f"signal key mismatch: {key}")
        for field in ("strategy_version", "date", "code", "setup"):
            if not signal.get(field):
                raise TrackerSchemaError(f"signal {key} missing {field}")
    data.setdefault("updated", None)
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
    tracker_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


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
        "review_points": _new_review_points(signal_date, calendar),
    }


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
    for path in resolver.watchlist_files():
        watchlist = load_watchlist(path)
        for candidate in watchlist["candidates"]:
            signal_id = candidate["signal_id"]
            if signal_id in tracker["signals"]:
                continue
            tracker["signals"][signal_id] = _signal_from_candidate(watchlist, candidate, cal)
            added += 1
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


def _append_observation(signal: dict[str, Any], quote: dict[str, Any]) -> None:
    observation = {
        "date": quote["quote_date"],
        "price": quote["price"],
        "high": quote["high"],
        "low": quote["low"],
    }
    for index, old in enumerate(signal.setdefault("observations", [])):
        if old.get("date") == observation["date"]:
            signal["observations"][index] = observation
            return
    signal["observations"].append(observation)


def _capture_review_points(
    signal: dict[str, Any],
    quote: dict[str, Any],
    today_date: date,
    calendar: TradingCalendar,
) -> int:
    """Capture due fixed-point snapshots without historical backfill."""

    points = _ensure_review_points(signal, calendar)
    changed = 0
    today_text = today_date.isoformat()
    for point in points.values():
        if point["status"] != REVIEW_POINT_PENDING:
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
        point.update({
            "status": REVIEW_POINT_CAPTURED,
            "quote_date": quote["quote_date"],
            "price": quote["price"],
            "high": quote["high"],
            "low": quote["low"],
            "signal_status": signal["status"],
            "reason": None,
        })
        changed += 1
    return changed


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

    signals = list(tracker["signals"].values())
    for signal in signals:
        _ensure_review_points(signal, cal)
    due_or_active = [
        signal
        for signal in signals
        if signal["status"] in ("pending", "triggered")
        or any(
            point["status"] == REVIEW_POINT_PENDING
            and today_date >= parse_date(point["scheduled_date"])
            for point in signal["review_points"].values()
        )
    ]
    if not due_or_active:
        return 0
    codes = list(dict.fromkeys(signal["code"] for signal in due_or_active))
    if quotes is None:
        quotes = fetch_quotes(codes, expected_date=today_date)
    else:
        validate_quotes(quotes, expected_codes=codes, expected_date=today_date)

    changed = 0
    today_text = today_date.isoformat()
    for signal in due_or_active:
        quote = quotes[signal["code"]]
        if signal["status"] in ("pending", "triggered"):
            list_date = parse_date(signal["date"])
            signal["days_tracked"] = trading_days_after(list_date, today_date, calendar=cal)
            _append_observation(signal, quote)
            decision = classify_signal_bar(
                status=signal["status"],
                trigger=signal.get("trigger"),
                stop=signal.get("stop"),
                target=signal.get("target"),
                high=quote.get("high"),
                low=quote.get("low"),
                price=quote.get("price"),
            )
            next_status = decision["status"]
            if next_status == "triggered" and signal["status"] == "pending":
                signal["status"] = "triggered"
                signal["entry_price"] = signal.get("trigger")
                signal["first_trigger_date"] = today_text
                changed += 1
                if signal["days_tracked"] >= TRACK_DAYS:
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
            elif signal["days_tracked"] >= TRACK_DAYS:
                signal["status"] = "expired"
                signal["close_date"] = today_text
                if next_status == "triggered":
                    signal["result_price"] = quote["price"]
                changed += 1
        changed += _capture_review_points(signal, quote, today_date, cal)
    tracker["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return changed


def _review_point_text(signal: dict[str, Any], label: str) -> str:
    point = signal.get("review_points", {}).get(label)
    if not isinstance(point, dict):
        return "未初始化"
    status = point.get("status", REVIEW_POINT_PENDING)
    if status == REVIEW_POINT_CAPTURED:
        return f"已采集 {point.get('quote_date')} / {point.get('price')} / {point.get('signal_status')}"
    if status == REVIEW_POINT_NOT_CAPTURED:
        return "未采集（不回填）"
    return f"待 {point.get('scheduled_date', '—')}"


def report(tracker: dict[str, Any], calendar: TradingCalendar | None = None) -> str:
    """Render the formal signal-level review cadence without outcome overclaiming."""

    _validate_tracker(tracker)
    cal = calendar or default_calendar()
    signals = list(tracker["signals"].values())
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
        "> 每交易日由 tracker 维护状态；T+3 为短线评价，T+5 为主评价，T+10 为延伸观察并结案。",
        "> 节点按信号日 T 后第 3/5/10 个真实 XSHG session 计算，不按自然日；历史节点不做行情回填。",
        "",
        "## 一、节点状态",
    ]
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
            f"{_review_point_text(signal, 'T+3')} | {_review_point_text(signal, 'T+5')} | "
            f"{_review_point_text(signal, 'T+10')} | {signal['status']} | {signal.get('close_date') or ''} |"
        )
    if not signals:
        lines.append("*暂无样本*")
    lines += ["", "---", "*量化信号，仅供研究参考；本报告不构成策略有效性或生产结论。*"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", nargs="?", default="all", choices=["ingest", "update", "report", "all"])
    args = parser.parse_args(argv)
    try:
        tracker = load_tracker()
        if args.action in ("ingest", "all"):
            print(f"[ingest] 新增入库 {ingest(tracker)} 个信号", flush=True)
        if args.action in ("update", "all"):
            print(f"[update] 状态变更 {update(tracker)} 个", flush=True)
        text = None
        if args.action in ("report", "all"):
            text = report(tracker)
            print(text)
            REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
            REPORT_FILE.write_text(text, encoding="utf-8")
            print(f"\n报表已存：{REPORT_FILE}", flush=True)
        save_tracker(tracker)
    except (OSError, ValueError, CalendarUnavailable, WatchlistSchemaError, QuoteDataError, TrackerSchemaError) as exc:
        print(f"数据完整性失败: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
