#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
"""
收盘复盘（15:30）：只复盘当日大盘环境 + 持仓收盘体检。
观察名单由 14:45 任务单独发布，此处不再扫描/复盘名单（按用户要求分工）。

用法：python3.11 eod_review.py
"""
import json, time, warnings, sys, os
from pathlib import Path
import requests
import numpy as np

# 配对指标标准模块（同目录）：复盘/名单报告共用「逐日比值表 + 拆分小图」
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import pairs_module
except Exception:
    pairs_module = None

warnings.filterwarnings("ignore")

BASE = None
for _c in (Path("/workspace/ashare_monitor"), Path("/root/ashare_monitor")):
    if (_c / "positions.json").exists():
        BASE = _c
        break
BASE = BASE or Path("/workspace/ashare_monitor")
POS_FILE = BASE / "positions.json"
# index_pairs.py 默认输出目录（配对数据）
PAIRS_DATA = Path("/root/ashare_monitor/index_pairs.json")


def to_symbol(code: str) -> str:
    return ("sh" if code.startswith(("60", "68", "51", "58")) else "sz") + code


def fetch_quotes(syms):
    try:
        r = requests.get("https://qt.gtimg.cn/q=" + ",".join(syms), timeout=15)
        r.encoding = "gbk"
    except Exception:
        return {}
    out = {}
    for line in r.text.strip().split(";"):
        if "=" not in line:
            continue
        raw = line.split("=")[1].strip()
        if not raw.startswith('"'):
            continue
        p = raw[1:].rstrip('"').split("~")
        if len(p) < 50:
            continue
        sym = line.split("=")[0].replace("v_", "").strip()
        try:
            out[sym] = {"名称": p[1], "现价": float(p[3]), "昨收": float(p[4]),
                        "涨跌幅": float(p[32]), "换手": float(p[38]) if p[38] else 0,
                        "量比": float(p[49]) if p[49] else 0, "时间": p[30]}
        except Exception:
            pass
    return out


def fetch_kline(sym, n=60):
    try:
        r = requests.get(f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={sym},day,,,{n},qfq", timeout=10)
        d = r.json()["data"].get(sym, {})
        bars = d.get("qfqday") or d.get("day") or []
        return [{"date": b[0], "close": float(b[2]), "volume": float(b[5])} for b in bars]
    except Exception:
        return []


def market_env():
    idx = fetch_kline("sh000001", 60)
    if not idx:
        return {"grade": "?", "score": 0, "detail": {}}
    c = np.array([x["close"] for x in idx])
    v = np.array([x["volume"] for x in idx])
    close, ma5, ma20 = c[-1], c[-5:].mean(), c[-20:].mean()
    chg5 = (close / c[-6] - 1) * 100 if len(c) > 6 else 0
    vol_ratio = v[-1] / v[-21:-1].mean() if len(v) > 21 else 1
    above_ma5, above_ma20 = close >= ma5, close >= ma20
    score = 0
    if above_ma5: score += 3
    if above_ma20: score += 3
    if chg5 > 0: score += 1
    if vol_ratio >= 0.8: score += 1
    grade = "A" if score >= 6 else ("B" if score >= 4 else "C")
    return {"grade": grade, "score": score, "detail": {
        "上证收盘": round(close, 2), "站MA5": above_ma5, "站MA20": above_ma20,
        "5日涨跌幅%": round(chg5, 2), "量能比": round(vol_ratio, 2)}}


def main():
    env = market_env()
    pos = json.loads(POS_FILE.read_text(encoding="utf-8"))["positions"]
    syms = [to_symbol(p["code"]) for p in pos]
    q = fetch_quotes(syms)
    L = [f"# 收盘复盘（{time.strftime('%Y-%m-%d')}）— 大盘 & 持仓", "",
         f"## 一、大盘环境：**{env['grade']}级**（{env['score']}/8）", ""]
    L += [f"- {k}：{v}" for k, v in env["detail"].items()]
    L += ["", f"## 二、持仓收盘体检（{len(pos)}只）", "",
          "| 名称 | 现价 | 盈亏% | 距止损% | 状态 |", "|---|---|---|---|---|"]
    for p in pos:
        sym = to_symbol(p["code"])
        qq = q.get(sym)
        if not qq:
            L.append(f"| {p['name']} | - | - | - | 行情缺失 |")
            continue
        price, cost, stop = qq["现价"], p.get("cost"), p.get("stop")
        pnl = (price / cost - 1) * 100 if cost else 0
        d_stop = (price / stop - 1) * 100 if stop else 0
        if p.get("long_term"):
            status = "长期持仓·不预警"
        elif stop and price <= stop:
            status = "⚠️止损触发"
        elif d_stop < 2:
            status = "逼近止损"
        else:
            status = "正常"
        L.append(f"| {p['name']} | {price} | {pnl:+.1f}% | {d_stop:+.1f}% | {status} |")
    L += ["", "## 三、次日要点",
          "- 观察名单已于 14:45 发布，次日 09:25 将做竞价重分析",
          "- 持仓按体系纪律：止损触发即离场，不扩大止损",
          "- 大盘若转 C 级，主动降仓", ""]
    # 四、配对指标（风格/行业轮动）—— 固定模块：逐日比值表 + 拆分小图
    if pairs_module and PAIRS_DATA.exists():
        try:
            sec = pairs_module.render_section_md(
                str(PAIRS_DATA),
                str(BASE / f"配对指标每日比值_{time.strftime('%Y-%m-%d')}.html"))
            L += [""] + sec.splitlines()
        except Exception as e:
            L += ["", f"> 配对指标模块暂不可用：{e}"]
    else:
        L += ["", "> 配对指标数据缺失（index_pairs.json 未更新），跳过本模块。"]
    L += ["", "---", "*量化信号，仅供研究参考，不构成投资建议。*"]
    print("\n".join(L))


if __name__ == "__main__":
    main()
