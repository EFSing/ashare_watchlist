#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
"""
盘后/午盘复盘脚本 —— 复盘「前一交易日观察名单」+「持仓股票」
数据源：腾讯行情快照 qt.gtimg.cn（GBK）
输入：
  - /root/ashare_monitor/watchlist_{YYYYMMDD}.json （前一交易日 14:35 产出的名单，从云盘下载）
  - /root/ashare_monitor/positions.json （内嵌持仓）
输出：
  - 观察名单逐股复盘（昨日买点/触发/止损/目标 vs 今日实际走势）
  - 持仓股风控（现价 vs 成本/止损，浮盈浮亏，离场信号）
用法：python3.11 review_after.py --mode close|midday [--date YYYYMMDD]
      不传 --date 时自动取「前一交易日」（跳过周末）。
"""
import argparse, json, sys, time, os
from datetime import datetime, timedelta
import pandas as pd
import requests
from pathlib import Path

# 配对指标标准模块（同目录）：复盘/名单报告共用「逐日比值表 + 拆分小图」
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import pairs_module
except Exception:
    pairs_module = None

BASE = Path("/root/ashare_monitor")
WATCH_DIR = BASE / "watchlist"
POS = BASE / "positions.json"
# index_pairs.py 默认输出目录（配对数据）
PAIRS_DATA = Path("/root/ashare_monitor/index_pairs.json")

def prev_trade_date(now: datetime) -> str:
    """返回「前一交易日」的 YYYYMMDD（跳过周六周日）。"""
    d = now.date() - timedelta(days=1)
    while d.weekday() >= 5:  # 5=周六, 6=周日
        d -= timedelta(days=1)
    return d.strftime("%Y%m%d")

def to_symbol(code: str) -> str:
    return ("sh" if code.startswith(("60", "68", "5", "9")) else "sz") + code

def fetch_quotes(codes):
    symbols = [to_symbol(c) for c in codes]
    out = {}
    for i in range(0, len(symbols), 50):
        url = "https://qt.gtimg.cn/q=" + ",".join(symbols[i:i+50])
        for attempt in range(3):
            try:
                r = requests.get(url, timeout=15)
                r.encoding = "gbk"
                text = r.text
                break
            except Exception:
                time.sleep(1 + attempt)
        else:
            text = ""
        for line in text.strip().split(";"):
            line = line.strip()
            if not line or "=" not in line or "~" not in line:
                continue
            p = line.split("~")
            if len(p) < 50:
                continue
            code = line.split("=")[0].replace("v_", "").strip()
            try:
                out[code[2:]] = {
                    "name": p[1],
                    "price": float(p[3]),
                    "chg_pct": float(p[32]),
                    "open": float(p[5]) if p[5] else None,
                    "high": float(p[33]) if p[33] else None,
                    "low": float(p[34]) if p[34] else None,
                    "turnover": float(p[38]) if p[38] else 0.0,
                    "vol_ratio": float(p[49]) if p[49] else 0.0,
                }
            except (ValueError, IndexError):
                continue
        time.sleep(0.1)
    return out

def review_watchlist(cands, quotes):
    rows = []
    for c in cands:
        code = c.get("code", "")
        q = quotes.get(code)
        if not q:
            rows.append({"代码": code, "名称": c.get("name",""), "状态": "行情获取失败"})
            continue
        price_now = q["price"]
        chg = q["chg_pct"]
        trigger = c.get("trigger")
        stop = c.get("stop")
        target = c.get("target")
        # 触发判断
        status_parts = []
        if trigger is not None:
            if q.get("low") is not None and q["low"] <= trigger <= q.get("high", trigger):
                status_parts.append(f"已触发入场(触发价{trigger})")
            elif price_now >= trigger:
                status_parts.append(f"现价≥触发价{trigger}，可介入")
            else:
                status_parts.append(f"未触发(现价{price_now}<触发{trigger})")
        if stop is not None and price_now <= stop:
            status_parts.append(f"⚠️跌破止损{stop}")
        if target is not None and price_now >= target:
            status_parts.append(f"✅已到目标{target}")
        rows.append({
            "代码": code,
            "名称": q["name"],
            "买点": c.get("buy_type",""),
            "昨日评分": c.get("score",""),
            "今日涨跌%": round(chg, 2),
            "现价": round(price_now, 2),
            "触发价": trigger,
            "止损": stop,
            "目标": target,
            "状态": "；".join(status_parts) if status_parts else "观望",
        })
    return rows

def review_positions(positions, quotes):
    rows = []
    for p in positions:
        code = p.get("code", "")
        q = quotes.get(code)
        name = p.get("name", code)
        long_term = p.get("long_term", False)
        if not q:
            rows.append({"代码": code, "名称": name, "类型": "长期" if long_term else "短线", "状态": "行情获取失败"})
            continue
        cost = p.get("cost")
        stop = p.get("stop")
        pnl_pct = round((q["price"] / cost - 1) * 100, 2) if cost else None
        status = []
        if long_term:
            status.append("长期持仓·不看浮亏")
        else:
            if stop is not None and q["price"] <= stop:
                status.append(f"⚠️跌破止损{stop}，离场")
            elif pnl_pct is not None:
                status.append(f"浮{'盈' if pnl_pct>=0 else '亏'}{abs(pnl_pct)}%")
        rows.append({
            "代码": code,
            "名称": name,
            "类型": "长期" if long_term else "短线",
            "成本": cost,
            "现价": round(q["price"], 2),
            "今日涨跌%": round(q["chg_pct"], 2),
            "止损": stop,
            "浮盈亏%": pnl_pct,
            "状态": "；".join(status),
        })
    return rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["close", "midday"], default="close")
    ap.add_argument("--date", default=None, help="名单日期 YYYYMMDD，默认前一交易日")
    args = ap.parse_args()

    wl_date = args.date or prev_trade_date(datetime.now())
    WL = WATCH_DIR / f"watchlist_{wl_date}.json"

    cands = []
    if WL.exists():
        wl = json.loads(WL.read_text(encoding="utf-8"))
        cands = wl.get("candidates", [])
        wl_date = wl.get("date", wl_date)
    else:
        wl_date = f"{wl_date}(名单缺失)"

    positions = []
    if POS.exists():
        positions = json.loads(POS.read_text(encoding="utf-8")).get("positions", [])

    codes = [c.get("code","") for c in cands] + [p.get("code","") for p in positions]
    codes = [c for c in dict.fromkeys(codes) if c]
    print(f"[1/3] 拉取 {len(codes)} 只股票行情…", flush=True)
    quotes = fetch_quotes(codes)

    print(f"[2/3] 复盘观察名单（{wl_date}，{len(cands)}只）…", flush=True)
    wl_rows = review_watchlist(cands, quotes) if cands else []

    print(f"[3/3] 持仓风控（{len(positions)}只）…", flush=True)
    pos_rows = review_positions(positions, quotes)

    # 输出报告
    title = "盘后复盘" if args.mode == "close" else "午盘复盘"
    lines = [f"# {title}（名单日期 {wl_date}）", ""]
    lines.append("## 一、观察名单复盘")
    if wl_rows:
        df = pd.DataFrame(wl_rows)
        lines.append(df.to_markdown(index=False))
    else:
        lines.append("*无观察名单数据*")
    lines.append("")
    lines.append("## 二、持仓风控")
    if pos_rows:
        df2 = pd.DataFrame(pos_rows)
        lines.append(df2.to_markdown(index=False))
    else:
        lines.append("*无持仓数据*")
    lines.append("")
    # 三、配对指标（风格/行业轮动）—— 固定模块：逐日比值表 + 拆分小图
    if pairs_module and PAIRS_DATA.exists():
        try:
            (BASE / "reports").mkdir(parents=True, exist_ok=True)
            chart_path = BASE / "reports" / f"配对指标每日比值_{wl_date}.html"
            sec = pairs_module.render_section_md(
                str(PAIRS_DATA), str(chart_path),
                heading="## 三、配对指标（风格/行业轮动）")
            lines += [""] + sec.splitlines()
        except Exception as e:
            lines += ["", f"> 配对指标模块暂不可用：{e}"]
    else:
        lines += ["", "> 配对指标数据缺失（index_pairs.json 未更新），跳过本模块。"]
    lines.append("")
    lines.append("---")
    lines.append("*量化信号，仅供研究参考，不构成投资建议。*")
    report = "\n".join(lines)
    print(report)
    # 存报告
    out = BASE / "reports" / f"review_{args.mode}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"\n报告已存：{out}", flush=True)

if __name__ == "__main__":
    main()
