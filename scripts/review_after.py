#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
"""每日轻量状态查看：canonical watchlist + canonical Tencent quotes。"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from typing import Any

import pandas as pd

from data_paths import DataPaths
from tencent_quotes import QuoteDataError, fetch_quotes, validate_quotes
from trading_calendar import CalendarUnavailable, TradingCalendar, previous_trading_day
from watchlist_schema import WatchlistSchemaError, load_watchlist


def prev_trade_date(now: datetime, calendar: TradingCalendar | None = None) -> str:
    """返回前一 A 股交易日，不把普通工作日默认为交易日。"""

    return previous_trading_day(now, calendar=calendar)


def resolve_review_dates(list_date_arg: str | None, run_at: datetime) -> tuple[str, date]:
    """Resolve the watchlist date separately from the runtime market date.

    ``--date`` selects the watchlist/list date only.  Historical market-data
    replay is intentionally not part of this command yet.
    """

    list_date = list_date_arg or prev_trade_date(run_at)
    return list_date, run_at.date()


def review_watchlist(cands: list[dict[str, Any]], quotes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    validate_quotes(quotes, expected_codes=[c["code"] for c in cands])
    rows = []
    for candidate in cands:
        code = candidate["code"]
        quote = quotes[code]
        price_now = quote["price"]
        trigger = candidate["trigger"]
        stop = candidate["stop"]
        target = candidate["target"]
        status_parts = []
        if quote["low"] <= trigger <= quote["high"]:
            status_parts.append(f"已触发入场(触发价{trigger})")
        elif price_now >= trigger:
            status_parts.append(f"现价≥触发价{trigger}，可介入")
        else:
            status_parts.append(f"未触发(现价{price_now}<触发{trigger})")
        if price_now <= stop:
            status_parts.append(f"⚠️跌破止损{stop}")
        if price_now >= target:
            status_parts.append(f"✅已到目标{target}")
        rows.append({
            "代码": code,
            "名称": quote["name"],
            "买点": candidate["buy_type"],
            "昨日评分": candidate["score"],
            "今日涨跌%": round(quote["chg_pct"], 2),
            "现价": round(price_now, 2),
            "触发价": trigger,
            "止损": stop,
            "目标": target,
            "状态": "；".join(status_parts) if status_parts else "观望",
        })
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["close", "midday"], default="close")
    ap.add_argument(
        "--date",
        default=None,
        help="名单/list 日期 YYYYMMDD；仅选择名单，不是历史行情 as-of 日期，默认前一交易日",
    )
    args = ap.parse_args(argv)
    paths = DataPaths.from_env()
    run_at = datetime.now()
    wl_date, market_date = resolve_review_dates(args.date, run_at)

    try:
        watchlist = load_watchlist(paths.watchlist_file(wl_date))
        candidates = watchlist["candidates"]
        codes = [c["code"] for c in candidates]
        print(f"[1/2] 拉取 {len(codes)} 只股票行情…", flush=True)
        quotes = fetch_quotes(codes, expected_date=market_date)
        wl_rows = review_watchlist(candidates, quotes)
    except (OSError, KeyError, ValueError, CalendarUnavailable, WatchlistSchemaError, QuoteDataError) as exc:
        print(f"数据完整性失败: {exc}", file=sys.stderr)
        return 2

    print(f"[2/2] 每日轻量状态（{watchlist['date']}，{len(candidates)}只）…", flush=True)
    title = "每日轻量状态记录"
    quote_dates = {quote["quote_date"] for quote in quotes.values()}
    quote_date = next(iter(quote_dates), market_date.isoformat())
    lines = [
        f"# {title}（名单日期 {watchlist['date']}）",
        f"> 行情日期：{quote_date}（运行当日行情；--date 仅选择名单，不是 historical replay）",
        "> 本报告只记录当日名单状态；跨日正式绩效由 signal-level tracker 按 XSHG 交易日节点维护。",
        "",
        "## 观察名单状态",
    ]
    lines.append(pd.DataFrame(wl_rows).to_markdown(index=False) if wl_rows else "*无观察名单数据*")

    lines.extend(["", "---", "*量化信号，仅供研究参考，不构成投资建议。*"])
    report = "\n".join(lines)
    print(report)
    output = paths.reports_dir() / f"review_{args.mode}.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(f"\n报告已存：{output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
