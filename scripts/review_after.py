#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
"""盘后/午盘复盘：canonical watchlist + canonical Tencent quotes。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from data_paths import DataPaths
from tencent_quotes import QuoteDataError, fetch_quotes, validate_quotes
from trading_calendar import CalendarUnavailable, TradingCalendar, previous_trading_day
from watchlist_schema import WatchlistSchemaError, load_watchlist

import pairs_module


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


def review_positions(positions: list[dict[str, Any]], quotes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    validate_quotes(quotes, expected_codes=[p["code"] for p in positions])
    rows = []
    for position in positions:
        code = position["code"]
        quote = quotes[code]
        cost = position.get("cost")
        stop = position.get("stop")
        pnl_pct = round((quote["price"] / cost - 1) * 100, 2) if cost else None
        status = []
        if position.get("long_term", False):
            status.append("长期持仓·不看浮亏")
        elif stop is not None and quote["price"] <= stop:
            status.append(f"⚠️跌破止损{stop}，离场")
        elif pnl_pct is not None:
            status.append(f"浮{'盈' if pnl_pct >= 0 else '亏'}{abs(pnl_pct)}%")
        rows.append({
            "代码": code,
            "名称": position.get("name", code),
            "类型": "长期" if position.get("long_term", False) else "短线",
            "成本": cost,
            "现价": round(quote["price"], 2),
            "今日涨跌%": round(quote["chg_pct"], 2),
            "止损": stop,
            "浮盈亏%": pnl_pct,
            "状态": "；".join(status),
        })
    return rows


def _load_positions(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"positions file missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    positions = payload.get("positions")
    if not isinstance(positions, list):
        raise ValueError("positions.json must contain an array field 'positions'")
    return positions


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
        positions = _load_positions(paths.positions_file())
        candidates = watchlist["candidates"]
        codes = list(dict.fromkeys([c["code"] for c in candidates] + [p["code"] for p in positions]))
        print(f"[1/3] 拉取 {len(codes)} 只股票行情…", flush=True)
        quotes = fetch_quotes(codes, expected_date=market_date)
        wl_rows = review_watchlist(candidates, quotes)
        pos_rows = review_positions(positions, quotes)
    except (OSError, KeyError, ValueError, CalendarUnavailable, WatchlistSchemaError, QuoteDataError) as exc:
        print(f"数据完整性失败: {exc}", file=sys.stderr)
        return 2

    print(f"[2/3] 复盘观察名单（{watchlist['date']}，{len(candidates)}只）…", flush=True)
    print(f"[3/3] 持仓风控（{len(positions)}只）…", flush=True)
    title = "盘后复盘" if args.mode == "close" else "午盘复盘"
    quote_dates = {quote["quote_date"] for quote in quotes.values()}
    quote_date = next(iter(quote_dates), market_date.isoformat())
    lines = [
        f"# {title}（名单日期 {watchlist['date']}）",
        f"> 行情日期：{quote_date}（运行当日行情；--date 仅表示名单日期，未实现 historical replay）",
        "",
        "## 一、观察名单复盘",
    ]
    lines.append(pd.DataFrame(wl_rows).to_markdown(index=False) if wl_rows else "*无观察名单数据*")
    lines.extend(["", "## 二、持仓风控"])
    lines.append(pd.DataFrame(pos_rows).to_markdown(index=False) if pos_rows else "*无持仓数据*")

    pairs_path = paths.index_pairs_file()
    if pairs_path.exists():
        try:
            chart_path = paths.reports_dir() / f"配对指标每日比值_{watchlist['date']}.html"
            lines.extend(["", pairs_module.render_section_md(
                str(pairs_path), str(chart_path), heading="## 三、配对指标（风格/行业轮动）"
            )])
        except Exception as exc:
            lines.extend(["", f"> 配对指标模块暂不可用：{exc}"])
    else:
        lines.extend(["", "> 配对指标数据缺失（index_pairs.json 未更新），跳过本模块。"])

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
