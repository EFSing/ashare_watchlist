#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
"""
配对指标（pair ratio / 风格·行业轮动）监控模块 —— 增强版
============================================================
用「防御/进攻」「价值/成长」「大盘/小盘」「行业轮动」多组指数比值刻画 A 股风格与行业强弱，
类比美股 VTV/QQQ、CGDV/QQQ 的 pair 思路，扩展到 A 股行业/风格维度。

配对（8 对，数据源均为腾讯 ifzq 前复权日K，已实测可用）：
  A. 风格轮动（3 对）
     1. 上证50 / 创业板指      sh000016 / sz399006  价值 / 成长
     2. 中证红利 / 科创50      sh000922 / sh000688  红利防御 / 硬科技
     3. 沪深300 / 中证1000     sh000300 / sh000852  大盘 / 小盘
  B. 行业/风格轮动（5 对）
     4. 中证金融 / 科创50      sh000934 / sh000688  金融防御 / 科技进攻
     5. 中证消费 / 中证工业    sh000932 / sh000930  消费 / 周期工业
     6. 中证医药 / 科创50      sh000933 / sh000688  医药防御 / 科技进攻
     7. 上证消费 / 上证医药    sh000913 / sh000914  消费 / 医药（防御内部轮动）
     8. 中证材料 / 中证工业    sh000929 / sh000930  上游材料 / 中游工业（周期内部）

数据持久化：指数日线存到 index_pairs.json，每次只增量更新最后一天，避免重复全量拉取触发封控。

数据源：腾讯 ifzq 前复权日K（指数支持 day 数据）。
用法：python3.11 index_pairs.py
"""
import json
import os
import time
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
DATA_FILE = "/root/ashare_monitor/index_pairs.json"

# 指数定义：(代码, 名称, 属性标签)
INDICES = {
    "sh000016": ("上证50", "价值蓝筹"),
    "sz399006": ("创业板指", "成长"),
    "sh000300": ("沪深300", "大盘"),
    "sh000852": ("中证1000", "小盘"),
    "sh000688": ("科创50", "硬科技"),
    "sh000922": ("中证红利", "红利防御"),
    "sh000934": ("中证金融", "金融防御"),
    "sh000932": ("中证消费", "消费"),
    "sh000930": ("中证工业", "周期工业"),
    "sh000933": ("中证医药", "医药防御"),
    "sh000913": ("上证消费", "消费"),
    "sh000914": ("上证医药", "医药"),
    "sh000929": ("中证材料", "上游材料"),
}

# 配对定义：(分子, 分母, 标签, 属性tag, 分组)
PAIRS = [
    # A. 风格轮动
    ("sh000016", "sz399006", "上证50/创业板指", "价值/成长", "风格"),
    ("sh000922", "sh000688", "中证红利/科创50", "红利/硬科技", "风格"),
    ("sh000300", "sh000852", "沪深300/中证1000", "大盘/小盘", "风格"),
    # B. 行业/风格轮动
    ("sh000934", "sh000688", "中证金融/科创50", "金融防御/科技", "行业"),
    ("sh000932", "sh000930", "中证消费/中证工业", "消费/周期", "行业"),
    ("sh000933", "sh000688", "中证医药/科创50", "医药防御/科技", "行业"),
    ("sh000913", "sh000914", "上证消费/上证医药", "消费/医药", "行业"),
    ("sh000929", "sh000930", "中证材料/中证工业", "材料/工业", "行业"),
]


def fetch_index_kline(sym, n=60, retries=3):
    """腾讯指数日K（不复权），返回 [{date, close}]，带重试与健壮容错"""
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={sym},day,,,{n},qfq"
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=10, headers=UA)
            data = r.json().get("data", {})
            # data 字段偶发为字符串/列表等异常结构，需容错
            if not isinstance(data, dict):
                raise ValueError(f"data 非字典: {type(data)}")
            d = data.get(sym, {})
            if not isinstance(d, dict):
                d = {}
            bars = d.get("day") or d.get("qfqday") or []
            if len(bars) < 3:
                raise ValueError(f"K线不足: {len(bars)}")
            return [{"date": b[0], "close": float(b[2])} for b in bars]
        except Exception:
            if attempt < retries - 1:
                time.sleep(1 + attempt)
    return []


def load_data():
    if os.path.exists(DATA_FILE):
        try:
            return json.load(open(DATA_FILE, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_data(data):
    json.dump(data, open(DATA_FILE, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)


def update_data(n=60):
    """增量更新：拉取各指数日K，覆盖写入"""
    data = load_data()
    for sym, (name, tag) in INDICES.items():
        k = fetch_index_kline(sym, n)
        if k:
            data[sym] = {"name": name, "tag": tag, "kline": k}
        time.sleep(0.3)
    data["_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save_data(data)
    return data


def compute_pairs(data, lookback=20):
    """计算配对比值及其近期趋势，输出风格/行业结论"""
    out = []
    for num, den, label, tag, group in PAIRS:
        kn = data.get(num, {}).get("kline", [])
        kd = data.get(den, {}).get("kline", [])
        if not kn or not kd:
            continue
        # 按日期对齐，取共同日期
        close_map = {x["date"]: x["close"] for x in kd}
        ratio_series = []
        for x in kn:
            if x["date"] in close_map:
                ratio_series.append({
                    "date": x["date"],
                    "num_close": x["close"],
                    "den_close": close_map[x["date"]],
                    "ratio": x["close"] / close_map[x["date"]],
                })
        if len(ratio_series) < lookback:
            continue
        cur = ratio_series[-1]
        prev = ratio_series[-1 - lookback]
        chg = (cur["ratio"] / prev["ratio"] - 1) * 100  # 近lookback日比值变化
        r5_prev = ratio_series[-6]["ratio"] if len(ratio_series) >= 6 else ratio_series[0]["ratio"]
        chg5 = (cur["ratio"] / r5_prev - 1) * 100
        # 趋势方向：近20日比值上升 = 分子相对走强
        out.append({
            "label": label, "tag": tag, "group": group,
            "ratio": round(cur["ratio"], 4),
            "chg_lookback_pct": round(chg, 2),
            "chg5_pct": round(chg5, 2),
            "trend": "走强" if chg > 0 else "走弱",
            "num_name": INDICES[num][0], "den_name": INDICES[den][0],
            "num_close": cur["num_close"], "den_close": cur["den_close"],
        })
    return out


def style_conclusion(pairs):
    """根据配对趋势输出风格结论"""
    if not pairs:
        return "数据不足"
    # 核心：红利/科创50（防御/进攻核心）
    core = next((p for p in pairs if p["label"] == "中证红利/科创50"), None)
    if core:
        chg = core["chg_lookback_pct"]
        if chg > 2:
            return "防守占优：红利/防御近20日跑赢硬科技，资金避险，宜配红利、低估值、逆势抗跌"
        elif chg < -2:
            return "进攻占优：硬科技近20日跑赢红利，风险偏好高，宜配成长、题材龙头"
        else:
            return "风格拉锯：红利与硬科技近20日相对均衡，无明确风格，宜均衡配置、控仓观望"
    return "中性"


def industry_rotation(pairs):
    """行业轮动结论：找出近5日比值上升最快的行业配对（分子代表强行业）"""
    industry = [p for p in pairs if p["group"] == "行业" and p["chg5_pct"] is not None]
    if not industry:
        return "数据不足"
    # 近5日分子相对走强排行
    ranked = sorted(industry, key=lambda x: -x["chg5_pct"])
    strong = ranked[0]
    weak = ranked[-1]
    return {
        "最强相对行业": f"{strong['num_name']}（相对{strong['den_name']}近5日 {strong['chg5_pct']:+.1f}%）",
        "最弱相对行业": f"{weak['num_name']}（相对{weak['den_name']}近5日 {weak['chg5_pct']:+.1f}%）",
        "提示": "短线资金近5日正从『最弱』方向撤向『最强』方向，结合主线确认",
    }


def main():
    print("=" * 74)
    print("配对指标监控 · A股风格/行业轮动（防御/进攻 + 行业强弱）")
    print("=" * 74)

    # 1. 增量更新数据
    print("\n[1/3] 更新指数数据（增量，覆盖写入，避免重复拉取）...")
    data = update_data(n=60)
    n_idx = len([k for k in data if k.startswith(("sh", "sz"))])
    print(f"  已更新 {n_idx} 个指数")

    # 2. 计算配对
    print("\n[2/3] 计算配对比值...\n")
    pairs = compute_pairs(data)

    # 分组展示
    for group, title in [("风格", "【A. 风格轮动】价值/成长 · 红利/科技 · 大盘/小盘"),
                          ("行业", "【B. 行业/风格轮动】金融/消费/医药/材料/工业")]:
        sub = [p for p in pairs if p["group"] == group]
        if not sub:
            continue
        print(title)
        print(f"{'配对':<22}{'比值':>10}{'近20日':>9}{'近5日':>8}{'方向':>6}")
        print("-" * 62)
        for p in sub:
            print(f"{p['label']:<22}{p['ratio']:>10.4f}{p['chg_lookback_pct']:>+8.1f}%"
                  f"{p['chg5_pct']:>+7.1f}%{p['trend']:>6}")
        print()

    # 3. 结论
    print("[3/3] 结论\n")
    conclusion = style_conclusion(pairs)
    rot = industry_rotation(pairs)
    print(f"风格结论：{conclusion}")
    if isinstance(rot, dict):
        print(f"行业轮动：{rot['最强相对行业']}")
        print(f"         ：{rot['最弱相对行业']}")
        print(f"         ：{rot['提示']}")
    else:
        print(f"行业轮动：{rot}")

    # 保存结果
    out = {
        "pairs": pairs,
        "conclusion": conclusion,
        "industry_rotation": rot,
        "_note": "量化信号，仅供研究参考，不构成投资建议",
    }
    json.dump(out, open("index_pairs_result.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2, default=str)
    print("\n结果已保存至 index_pairs_result.json，原始数据已持久化至 index_pairs.json")


if __name__ == "__main__":
    main()
