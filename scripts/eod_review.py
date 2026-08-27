#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
"""收盘复盘：大盘环境与持仓收盘体检。"""

from __future__ import annotations

import json
import sys
import time
import warnings
from datetime import date
from typing import Any

import numpy as np
import requests

from data_paths import DataPaths
from tencent_quotes import QuoteDataError, fetch_quotes

import pairs_module


warnings.filterwarnings("ignore")
PATHS = DataPaths.from_env()
BASE = PATHS.root
POS_FILE = PATHS.positions_file()


def fetch_kline(sym: str, n: int = 60) -> list[dict[str, Any]]:
    try:
        response = requests.get(
            f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={sym},day,,,{n},qfq",
            timeout=10,
        )
        data = response.json().get("data", {})
        record = data.get(sym, {})
        bars = record.get("qfqday") or record.get("day") or []
        return [{"date": bar[0], "close": float(bar[2]), "volume": float(bar[5])} for bar in bars]
    except Exception:
        return []


def market_env() -> dict[str, Any]:
    index = fetch_kline("sh000001", 60)
    if not index:
        return {"grade": "?", "score": 0, "detail": {}}
    closes = np.array([item["close"] for item in index])
    volumes = np.array([item["volume"] for item in index])
    close, ma5, ma20 = closes[-1], closes[-5:].mean(), closes[-20:].mean()
    chg5 = (close / closes[-6] - 1) * 100 if len(closes) > 6 else 0
    vol_ratio = volumes[-1] / volumes[-21:-1].mean() if len(volumes) > 21 else 1
    above_ma5, above_ma20 = close >= ma5, close >= ma20
    score = 3 * int(above_ma5) + 3 * int(above_ma20) + int(chg5 > 0) + int(vol_ratio >= 0.8)
    grade = "A" if score >= 6 else ("B" if score >= 4 else "C")
    return {"grade": grade, "score": score, "detail": {
        "上证收盘": round(close, 2), "站MA5": above_ma5, "站MA20": above_ma20,
        "5日涨跌幅%": round(chg5, 2), "量能比": round(vol_ratio, 2),
    }}


def main() -> int:
    try:
        payload = json.loads(POS_FILE.read_text(encoding="utf-8"))
        positions = payload["positions"]
        if not isinstance(positions, list):
            raise ValueError("positions.json must contain an array field 'positions'")
        codes = [position["code"] for position in positions]
        quotes = fetch_quotes(codes, expected_date=date.today())
    except (OSError, KeyError, ValueError, QuoteDataError) as exc:
        print(f"数据完整性失败: {exc}", file=sys.stderr)
        return 2

    env = market_env()
    lines = [f"# 收盘复盘（{time.strftime('%Y-%m-%d')}）— 大盘 & 持仓", "",
             f"## 一、大盘环境：**{env['grade']}级**（{env['score']}/8）", ""]
    lines += [f"- {key}：{value}" for key, value in env["detail"].items()]
    lines += ["", f"## 二、持仓收盘体检（{len(positions)}只）", "",
              "| 名称 | 现价 | 盈亏% | 距止损% | 状态 |", "|---|---|---|---|---|"]
    for position in positions:
        quote = quotes[position["code"]]
        price, cost, stop = quote["price"], position.get("cost"), position.get("stop")
        pnl = (price / cost - 1) * 100 if cost else 0
        distance_to_stop = (price / stop - 1) * 100 if stop else 0
        if position.get("long_term"):
            status = "长期持仓·不预警"
        elif stop and price <= stop:
            status = "⚠️止损触发"
        elif distance_to_stop < 2:
            status = "逼近止损"
        else:
            status = "正常"
        lines.append(f"| {position['name']} | {price} | {pnl:+.1f}% | {distance_to_stop:+.1f}% | {status} |")
    lines += ["", "## 三、次日要点",
              "- 观察名单已于 14:45 发布，次日 09:25 将做竞价重分析",
              "- 持仓按体系纪律：止损触发即离场，不扩大止损",
              "- 大盘若转 C 级，主动降仓", ""]

    pairs_path = PATHS.index_pairs_file()
    if pairs_path.exists():
        try:
            chart_path = PATHS.reports_dir() / f"配对指标每日比值_{time.strftime('%Y-%m-%d')}.html"
            lines.extend(["", pairs_module.render_section_md(str(pairs_path), str(chart_path))])
        except Exception as exc:
            lines.extend(["", f"> 配对指标模块暂不可用：{exc}"])
    else:
        lines += ["", "> 配对指标数据缺失（index_pairs.json 未更新），跳过本模块。"]
    lines += ["", "---", "*量化信号，仅供研究参考，不构成投资建议。*"]
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
