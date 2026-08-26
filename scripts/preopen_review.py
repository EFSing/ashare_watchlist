#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
"""
preopen_review.py —— 竞价重分析（盘前/早盘观察名单复核）

用途：在 9:25 集合竞价结束后（或盘中任意时点），对昨日收盘筛选出的观察名单
      逐只拉取实时行情，结合「入场触发价」做二次复核，输出四类标签。

用法：
    python3.11 preopen_review.py watchlist/<日期>.json

输出字段（每只）：
    今开涨%    今日开盘相对昨收的涨跌幅
    现价       当前实时价
    vs 入场触发 现价相对触发价的偏离（%）
    量比       当日量比（>=1.5 视为量能配合）
    重分析标签  ✅触发可介入 / ⛔破位移出 / 🔻低开偏弱 / ⏳站上待量能

标签判定逻辑（T日收盘名单 → T+1日竞价/早盘复核）：
    ✅触发可介入  今开高开站上触发价（开>=触发*0.99）且 量比 >= 1.2
    ⛔破位移出    现价跌破昨收（低开且走弱，短线信号作废，移出）
    🔻低开偏弱    今开涨% < -3（低开超 3%，弱势，放弃）
    ⏳站上待量能  站上触发价 但量比不足（<1.2），等待放量再介入
    🔍保持观察    其余（未站上触发价、未低开破位）→ 不急于介入

说明：观察名单尚未买入，破位判定基于「昨收」而非止损价（止损价仅对已买入持仓生效）。

免责声明：量化筛选信号，仅供研究参考，不构成投资建议。
"""

import json
import os
import sys
import time
import requests

# ---------------- 配置 ----------------
QT_URL = "https://qt.gtimg.cn/q="
TIMEOUT = 8

# 标签优先级：破位 > 低开 > 触发可介入 > 站上待量能 > 保持观察
# （先判破位/低开等硬性风控，再判介入机会）


def fetch_realtime(codes):
    """批量拉取腾讯实时行情。

    参数 codes: list[str]，形如 ['002156', '600519']，会自动补市场前缀。
    返回 dict: {code: {name, prev_close, open, price, volume, vol_ratio, time}}
    """
    result = {}
    if not codes:
        return result

    # 腾讯需要市场前缀：6xx=sh, 0xx/3xx=sz, 688=sh, 8xx/4xx=bj
    def prefixed(c):
        if c.startswith(("6", "9")):
            return "sh" + c
        if c.startswith(("0", "3")):
            return "sz" + c
        if c.startswith(("8", "4")):
            return "bj" + c
        return "sz" + c

    # 分批，每批最多 50 只
    BATCH = 50
    for i in range(0, len(codes), BATCH):
        batch = codes[i:i + BATCH]
        syms = ",".join(prefixed(c) for c in batch)
        url = QT_URL + syms
        try:
            r = requests.get(url, timeout=TIMEOUT)
            r.encoding = "gbk"
            text = r.text
        except Exception as e:
            print(f"  [请求失败] {e}", file=sys.stderr)
            continue

        # 解析每一行 v_sz002156="..."
        for line in text.strip().split("\n"):
            if "=" not in line or '"' not in line:
                continue
            body = line.split('"', 1)[1].rstrip('";')
            f = body.split("~")
            if len(f) < 50:
                continue
            try:
                code = f[2]
                name = f[1]
                prev_close = float(f[3])
                open_price = float(f[4])
                price = float(f[5])
                volume = float(f[6])          # 成交量（手）
                vol_ratio = float(f[38]) if f[38] else 0.0
                t = f[30] if len(f) > 30 else ""
                result[code] = {
                    "name": name,
                    "prev_close": prev_close,
                    "open": open_price,
                    "price": price,
                    "volume": volume,
                    "vol_ratio": vol_ratio,
                    "time": t,
                }
            except (ValueError, IndexError):
                continue

        if i + BATCH < len(codes):
            time.sleep(0.3)

    return result


def review_one(item, q):
    """对单只个股做竞价重分析，返回一行结果 dict。"""
    code = item.get("code", "")
    name = item.get("name", "")
    trig = item.get("trig")
    stop = item.get("stop")

    if code not in q:
        return {
            "code": code, "name": name, "今开涨%": None, "现价": None,
            "vs 入场触发": None, "量比": None, "重分析标签": "❓无行情",
            "_reason": "未获取到实时行情",
        }

    d = q[code]
    prev_close = d["prev_close"]
    open_price = d["open"]
    price = d["price"]
    vol_ratio = d["vol_ratio"]

    # 今开涨%
    open_pct = round((open_price / prev_close - 1) * 100, 2) if prev_close else None

    # vs 入场触发
    dist = None
    if trig and price:
        dist = round((price / trig - 1) * 100, 2)

    # 标签判定（破位基于昨收，非止损价——名单未买入）
    label = ""
    reason = ""

    if price and prev_close and price < prev_close * 0.985:
        # 现价跌破昨收且走弱（低开并继续下探）
        label = "⛔破位移出"
        reason = f"现价{price} < 昨收{prev_close}×0.985"
    elif open_pct is not None and open_pct < -3:
        label = "🔻低开偏弱"
        reason = f"今开 {open_pct}% < -3%"
    elif trig and open_price and open_price >= trig * 0.99:
        # 高开站上触发价
        if vol_ratio >= 1.2:
            label = "✅触发可介入"
            reason = f"高开站上触发{trig}，量比{vol_ratio}配合"
        else:
            label = "⏳站上待量能"
            reason = f"站上触发{trig}，但量比{vol_ratio}<1.2"
    elif trig and price and price >= trig:
        # 盘中已上穿触发价
        if vol_ratio >= 1.2:
            label = "✅触发可介入"
            reason = f"现价{price}上穿触发{trig}，量比{vol_ratio}配合"
        else:
            label = "⏳站上待量能"
            reason = f"现价{price}站上触发{trig}，量比{vol_ratio}<1.2"
    else:
        label = "🔍保持观察"
        reason = f"未站上触发价{trig}，未破位"

    return {
        "code": code, "name": name,
        "今开涨%": open_pct,
        "现价": price,
        "vs 入场触发": dist,
        "量比": vol_ratio,
        "重分析标签": label,
        "_reason": reason,
    }


def main():
    if len(sys.argv) < 2:
        print("用法: python3.11 preopen_review.py watchlist/<日期>.json")
        sys.exit(1)

    path = sys.argv[1]
    if not os.path.exists(path):
        print(f"文件不存在: {path}")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    date = data.get("date", os.path.basename(path).replace(".json", ""))
    emotion = data.get("emotion", "")
    items = data.get("items", [])

    print(f"========== 竞价重分析 · {date} ==========")
    if emotion:
        print(f"昨日情绪：{emotion}")
    print(f"名单数量：{len(items)}")
    print()

    codes = [it.get("code", "") for it in items if it.get("code")]
    q = fetch_realtime(codes)

    if not q:
        print("❌ 未获取到任何实时行情，请检查网络。")
        sys.exit(1)

    # 拉取时间
    sample_time = next(iter(q.values()))["time"]
    if sample_time:
        print(f"行情时间：{sample_time[:4]}-{sample_time[4:6]}-{sample_time[6:8]} "
              f"{sample_time[8:10]}:{sample_time[10:12]}:{sample_time[12:14]}")
    print()

    # 输出表格
    header = f"{'代码':<8}{'名称':<10}{'今开涨%':>8}{'现价':>8}{'vs触发%':>9}{'量比':>7}  {'重分析标签'}"
    print(header)
    print("-" * len(header))

    results = []
    for it in items:
        r = review_one(it, q)
        results.append(r)
        line = (
            f"{r['code']:<8}{r['name']:<10}"
            f"{_fmt(r['今开涨%']):>8}{_fmt(r['现价']):>8}{_fmt(r['vs 入场触发']):>9}"
            f"{_fmt(r['量比']):>7}  {r['重分析标签']}"
        )
        print(line)

    print()
    # 汇总统计
    from collections import Counter
    cnt = Counter(r["重分析标签"] for r in results)
    print("---------- 汇总 ----------")
    for label, n in cnt.most_common():
        print(f"  {label}: {n} 只")

    print()
    print("量化筛选信号，仅供研究参考，不构成投资建议。")

    # 存结果
    out_path = path.replace(".json", "_review.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"date": date, "emotion": emotion, "results": results},
                  f, ensure_ascii=False, indent=2)
    print(f"结果已保存: {out_path}")


def _fmt(x):
    if x is None:
        return "-"
    if isinstance(x, float):
        return f"{x:.2f}"
    return str(x)


if __name__ == "__main__":
    main()
