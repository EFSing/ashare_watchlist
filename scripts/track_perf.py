#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
"""
观察名单「验证闭环」跟踪器 —— 把选股信号变成可统计的胜率/盈亏比数据。

解决的问题：
  复盘脚本只做「当天涨跌 + 是否触发」，从不跟踪「触发入场后的最终结局」，
  导致永远算不出真实胜率、盈亏比、期望值。本脚本补齐这一环。

核心机制（每只候选股一个状态机）：
  pending    等待触发（现价 < 触发价）
  triggered  已触发入场（现价 >= 触发价 或 盘中最高触及触发价）
  win        已到目标（入场后 现价/最高 >= 目标价）
  loss       已止损出局（入场后 现价/最低 <= 止损价）
  expired    到期未决（超过 TRACK_DAYS 仍未触发，或触发后未分出胜负）

数据文件：
  /root/ashare_monitor/perf_tracker.json  跟踪库（逐日累积，永不覆盖丢失）
  /root/ashare_monitor/reports/perf_report.md  统计报表

用法：
  python3.11 track_perf.py ingest            # 吸收 watchlist/*.json 里尚未入库的候选股
  python3.11 track_perf.py update            # 拉当日行情，更新每只跟踪股的状态
  python3.11 track_perf.py report            # 输出胜率/盈亏比/期望值统计报表
  python3.11 track_perf.py --all             # ingest + update + report 一键跑
"""
import argparse, json, os, sys, time
from datetime import datetime, timedelta
from pathlib import Path
import requests

BASE = Path("/root/ashare_monitor")
WATCH_DIR = BASE / "watchlist"
TRACK_FILE = BASE / "perf_tracker.json"
REPORT_FILE = BASE / "reports" / "perf_report.md"

# 从名单日期起，跟踪多少个交易日未出结果即标记为 expired
TRACK_DAYS = 10

# 腾讯行情快照接口（GBK）
QUOTE_URL = "https://qt.gtimg.cn/q="


def to_symbol(code: str) -> str:
    return ("sh" if code.startswith(("60", "68", "5", "9")) else "sz") + code


def fetch_quotes(codes):
    """拉取一批股票的实时快照。返回 {code: {price, high, low, name, chg_pct}}"""
    symbols = [to_symbol(c) for c in codes]
    out = {}
    for i in range(0, len(symbols), 50):
        url = QUOTE_URL + ",".join(symbols[i:i + 50])
        text = ""
        for attempt in range(3):
            try:
                r = requests.get(url, timeout=15)
                r.encoding = "gbk"
                text = r.text
                break
            except Exception:
                time.sleep(1 + attempt)
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
                    "high": float(p[33]) if p[33] else None,
                    "low": float(p[34]) if p[34] else None,
                    "chg_pct": float(p[32]),
                }
            except (ValueError, IndexError):
                continue
        time.sleep(0.1)
    return out


def load_tracker():
    if TRACK_FILE.exists():
        try:
            return json.loads(TRACK_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"version": 1, "stocks": {}, "updated": None}


def save_tracker(data):
    TRACK_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_date(s):
    """兼容 2026-08-20 与 20260820 两种格式，返回 datetime.date"""
    s = str(s).replace("-", "")
    return datetime.strptime(s[:8], "%Y%m%d").date()


def trade_days_between(start: datetime.date, end: datetime.date):
    """返回 [start, end] 闭区间内的交易日天数（跳过周六周日）。"""
    if end < start:
        return 0
    n = 0
    d = start
    while d <= end:
        if d.weekday() < 5:
            n += 1
        d += timedelta(days=1)
    return n


def ingest(tracker):
    """扫描 watchlist 目录，把尚未入库的候选股吸收进跟踪库。返回新增数量。"""
    added = 0
    for f in sorted(WATCH_DIR.glob("watchlist_*.json")):
        try:
            wl = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        wl_date = parse_date(wl.get("date", ""))
        for c in wl.get("candidates", []):
            code = c.get("code", "")
            if not code:
                continue
            if code in tracker["stocks"]:
                continue  # 已入库，不覆盖
            tracker["stocks"][code] = {
                "code": code,
                "name": c.get("name", ""),
                "buy_type": c.get("buy_type", ""),
                "score": c.get("score"),
                "list_date": wl_date.strftime("%Y-%m-%d"),
                "trigger": c.get("trigger"),
                "stop": c.get("stop"),
                "target": c.get("target"),
                "rr": c.get("rr"),
                "status": "pending",
                "entry_price": None,
                "result_price": None,
                "days_tracked": 0,
                "first_trigger_date": None,
                "close_date": None,
            }
            added += 1
    return added


def update(tracker):
    """拉行情，更新所有未结清（pending/triggered）股票的状态。"""
    active = [c for c in tracker["stocks"].values()
              if c["status"] in ("pending", "triggered")]
    if not active:
        return 0
    codes = [c["code"] for c in active]
    quotes = fetch_quotes(codes)
    changed = 0
    today = datetime.now().date()
    for st in active:
        q = quotes.get(st["code"])
        if not q:
            continue
        # 跟踪天数 = 名单日到今天的实际交易日数（幂等，重复运行不虚增）
        list_d = parse_date(st["list_date"])
        st["days_tracked"] = trade_days_between(list_d, today)
        status = st["status"]
        trig = st["trigger"]
        stop = st["stop"]
        tgt = st["target"]
        price = q["price"]
        high = q["high"]
        low = q["low"]

        if status == "pending":
            # 触发判断：现价达到触发价，或盘中最高触及触发价
            hit = False
            if trig is not None:
                if high is not None and low is not None and low <= trig <= high:
                    hit = True
                elif price >= trig:
                    hit = True
            if hit:
                st["status"] = "triggered"
                st["entry_price"] = trig
                st["first_trigger_date"] = datetime.now().strftime("%Y-%m-%d")
                status = "triggered"
                changed += 1
            else:
                # 未触发，检查是否超期
                if st["days_tracked"] >= TRACK_DAYS:
                    st["status"] = "expired"
                    st["close_date"] = datetime.now().strftime("%Y-%m-%d")
                    changed += 1

        if status == "triggered":
            # 触发后判断结局：优先判止损（风控优先），再判目标
            if stop is not None and (price <= stop or (low is not None and low <= stop)):
                st["status"] = "loss"
                st["result_price"] = stop
                st["close_date"] = datetime.now().strftime("%Y-%m-%d")
                changed += 1
            elif tgt is not None and (price >= tgt or (high is not None and high >= tgt)):
                st["status"] = "win"
                st["result_price"] = tgt
                st["close_date"] = datetime.now().strftime("%Y-%m-%d")
                changed += 1
            elif st["days_tracked"] >= TRACK_DAYS:
                st["status"] = "expired"
                st["result_price"] = price
                st["close_date"] = datetime.now().strftime("%Y-%m-%d")
                changed += 1

    tracker["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return changed


def report(tracker):
    """生成统计报表并返回文本。"""
    stocks = list(tracker["stocks"].values())
    total = len(stocks)
    triggered = [s for s in stocks if s["status"] in ("triggered", "win", "loss")]
    closed = [s for s in stocks if s["status"] in ("win", "loss")]
    wins = [s for s in stocks if s["status"] == "win"]
    losses = [s for s in stocks if s["status"] == "loss"]
    pending = [s for s in stocks if s["status"] == "pending"]
    expired = [s for s in stocks if s["status"] == "expired"]

    lines = ["# 观察名单验证闭环 · 胜率统计报表", ""]
    lines.append(f"> 数据更新：{tracker.get('updated', '—')}　|　跟踪库样本：{total} 只",
                 )
    lines.append("")

    # 概览
    lines.append("## 一、概览")
    lines.append(f"- 累计入库：**{total}** 只")
    lines.append(f"- 已触发入场：**{len(triggered)}** 只（触发率 {len(triggered)/total*100:.1f}%）" if total else "- 已触发入场：0")
    lines.append(f"- 已分胜负：**{len(closed)}** 只")
    lines.append(f"- 仍在跟踪：{len(pending)} 只　|　到期未决：{len(expired)} 只")
    lines.append("")

    # 胜率 / 盈亏比 / 期望值
    lines.append("## 二、核心指标")
    if closed:
        win_rate = len(wins) / len(closed) * 100
        lines.append(f"- **触发后胜率**：{len(wins)}/{len(closed)} = **{win_rate:.1f}%**")
        # 用 rr（理论盈亏比）近似每笔盈亏：win 赚 rr-1 倍风险，loss 亏 1 倍风险
        tot_rr = sum((s.get("rr") or 0) for s in wins)
        # 用 rr 计算：win 每笔按 (rr) 计（含本金），loss 每笔 -1
        if len(wins):
            avg_rr_win = tot_rr / len(wins)
            lines.append(f"- 盈利端平均 RR（理论盈亏比）：**{avg_rr_win:.2f}**")
        # 期望值 EV（以「1 单位风险」为基准）：胜率×平均盈利RR − 败率×1
        p_win = len(wins) / len(closed)
        p_loss = len(losses) / len(closed)
        avg_win_rr = (tot_rr / len(wins)) if wins else 0
        ev = p_win * avg_win_rr - p_loss * 1.0
        lines.append(f"- **期望值 EV**（每承担 1 单位风险）：**{ev:+.2f}**")
        verdict = "正期望，体系可盈利" if ev > 0 else "负期望，体系需优化"
        lines.append(f"- 结论：**{verdict}**")
    else:
        lines.append("> 尚无已分胜负的样本，胜率/期望值待积累。")
    lines.append("")

    # 明细表
    lines.append("## 三、逐股跟踪明细")
    if stocks:
        header = "| 代码 | 名称 | 买点 | 评分 | 名单日 | 触发价 | 止损 | 目标 | RR | 状态 | 结果价 | 跟踪天数 |"
        sep = "|---|---|---|---|---|---|---|---|---|---|---|---|"
        lines.append(header)
        lines.append(sep)
        for s in sorted(stocks, key=lambda x: x["list_date"]):
            status_cn = {
                "pending": "待触发", "triggered": "已入场",
                "win": "✅到目标", "loss": "⚠️止损", "expired": "到期未决",
            }.get(s["status"], s["status"])
            lines.append(
                f"| {s['code']} | {s['name']} | {s['buy_type']} | {s.get('score','')} | "
                f"{s['list_date']} | {s['trigger']} | {s['stop']} | {s['target']} | "
                f"{s.get('rr','')} | {status_cn} | {s.get('result_price','')} | {s['days_tracked']} |"
            )
    else:
        lines.append("*暂无样本*")
    lines.append("")
    lines.append("---")
    lines.append("*量化信号，仅供研究参考，不构成投资建议。*")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", nargs="?", default="all",
                    choices=["ingest", "update", "report", "all"])
    args = ap.parse_args()

    tracker = load_tracker()

    if args.action in ("ingest", "all"):
        n = ingest(tracker)
        print(f"[ingest] 新增入库 {n} 只候选股", flush=True)

    if args.action in ("update", "all"):
        n = update(tracker)
        print(f"[update] 状态变更 {n} 只", flush=True)

    save_tracker(tracker)

    if args.action in ("report", "all"):
        txt = report(tracker)
        print(txt)
        REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
        REPORT_FILE.write_text(txt, encoding="utf-8")
        print(f"\n报表已存：{REPORT_FILE}", flush=True)


if __name__ == "__main__":
    main()
