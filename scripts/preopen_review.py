#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
"""盘前/早盘观察名单复核。"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from data_paths import DataPaths
from tencent_quotes import QuoteDataError, fetch_quotes
from watchlist_schema import WatchlistSchemaError, load_watchlist


def review_one(item: dict[str, Any], quote: dict[str, Any]) -> dict[str, Any]:
    """对单只个股做竞价重分析，返回一行结果 dict。"""

    code = item["code"]
    name = item["name"]
    trigger = item["trigger"]

    prev_close = quote["prev_close"]
    open_price = quote["open"]
    price = quote["price"]
    vol_ratio = quote["vol_ratio"]

    open_pct = round((open_price / prev_close - 1) * 100, 2) if prev_close else None
    dist = round((price / trigger - 1) * 100, 2) if trigger else None

    # 保留原有复核阈值和标签优先级；这里只替换为 canonical quote 字段。
    if price and prev_close and price < prev_close * 0.985:
        label = "⛔破位移出"
        reason = f"现价{price} < 昨收{prev_close}×0.985"
    elif open_pct is not None and open_pct < -3:
        label = "🔻低开偏弱"
        reason = f"今开 {open_pct}% < -3%"
    elif trigger and open_price and open_price >= trigger * 0.99:
        if vol_ratio >= 1.2:
            label = "✅触发可介入"
            reason = f"高开站上触发{trigger}，量比{vol_ratio}配合"
        else:
            label = "⏳站上待量能"
            reason = f"站上触发{trigger}，但量比{vol_ratio}<1.2"
    elif trigger and price and price >= trigger:
        if vol_ratio >= 1.2:
            label = "✅触发可介入"
            reason = f"现价{price}上穿触发{trigger}，量比{vol_ratio}配合"
        else:
            label = "⏳站上待量能"
            reason = f"现价{price}站上触发{trigger}，量比{vol_ratio}<1.2"
    else:
        label = "🔍保持观察"
        reason = f"未站上触发价{trigger}，未破位"

    return {
        "code": code,
        "name": name,
        "今开涨%": open_pct,
        "现价": price,
        "vs 入场触发": dist,
        "量比": vol_ratio,
        "重分析标签": label,
        "_reason": reason,
    }


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("用法: python3.11 preopen_review.py watchlist_YYYYMMDD.json", file=sys.stderr)
        return 2

    paths = DataPaths.from_env()
    requested = Path(args[0])
    path = requested if requested.is_absolute() else paths.root / requested
    try:
        watchlist = load_watchlist(path)
    except (OSError, WatchlistSchemaError) as exc:
        print(f"名单完整性失败: {exc}", file=sys.stderr)
        return 2

    candidates = watchlist["candidates"]
    print(f"========== 竞价重分析 · {watchlist['date']} ==========")
    print(f"名单数量：{len(candidates)}")
    print()

    codes = [candidate["code"] for candidate in candidates]
    try:
        quotes = fetch_quotes(codes, expected_date=date.today()) if codes else {}
    except (QuoteDataError, ValueError) as exc:
        print(f"行情完整性失败: {exc}", file=sys.stderr)
        return 2

    if quotes:
        sample_time = next(iter(quotes.values()))["timestamp"]
        print(
            f"行情时间：{sample_time[:4]}-{sample_time[4:6]}-{sample_time[6:8]} "
            f"{sample_time[8:10]}:{sample_time[10:12]}:{sample_time[12:14]}"
        )
    print()

    header = f"{'代码':<8}{'名称':<10}{'今开涨%':>8}{'现价':>8}{'vs触发%':>9}{'量比':>7}  {'重分析标签'}"
    print(header)
    print("-" * len(header))

    results = []
    for candidate in candidates:
        result = review_one(candidate, quotes[candidate["code"]])
        results.append(result)
        print(
            f"{result['code']:<8}{result['name']:<10}"
            f"{_fmt(result['今开涨%']):>8}{_fmt(result['现价']):>8}"
            f"{_fmt(result['vs 入场触发']):>9}{_fmt(result['量比']):>7}"
            f"  {result['重分析标签']}"
        )

    print()
    print("---------- 汇总 ----------")
    for label, count in Counter(result["重分析标签"] for result in results).most_common():
        print(f"  {label}: {count} 只")
    print()
    print("量化筛选信号，仅供研究参考，不构成投资建议。")

    output = paths.watchlist_review_file(watchlist["date"])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {"date": watchlist["date"], "results": results},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"结果已保存: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
