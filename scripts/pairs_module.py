#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
"""配对指标标准模块（框架共用）。

对外提供两个能力，供「复盘报告(eod_review.py)」「重点观察名单(review_after.py)」调用：
  1) pairs_table_md(data_path, days=5)      -> markdown 表格（最近 N 个交易日逐日比值 + 区间变化）
  2) pairs_chart_html(data_path, out_html)  -> 独立 HTML 文件（每对一张拆分小图，仅最近5天，关工具栏）

数据来源：/root/ashare_monitor/index_pairs.json（由 index_pairs.py 每日更新）。

健壮性说明：
  各指数每日刷新可能因网络/源站偶发失败而停在较早日期，导致「日期并集」里出现某指数没有的日期。
  本模块按「每个配对各自可用的日期」渲染：缺失日期填 '—'，绝不因单个配对缺值而让整段崩溃。
"""
import json
from plotly.subplots import make_subplots
import plotly.graph_objects as go

# 8 对配对（与框架 index_pairs.py 完全一致）
PAIRS = [
    ("sh000016", "sz399006", "上证50/创业板指", "价值/成长"),
    ("sh000922", "sh000688", "中证红利/科创50", "红利/硬科技"),
    ("sh000300", "sh000852", "沪深300/中证1000", "大盘/小盘"),
    ("sh000934", "sh000688", "中证金融/科创50", "金融防御/科技"),
    ("sh000932", "sh000930", "中证消费/中证工业", "消费/周期"),
    ("sh000933", "sh000688", "中证医药/科创50", "医药防御/科技"),
    ("sh000913", "sh000914", "上证消费/上证医药", "消费/医药"),
    ("sh000929", "sh000930", "中证材料/中证工业", "材料/工业"),
]


def load_ratios(data_path):
    d = json.load(open(data_path, encoding="utf-8"))

    def series(sym):
        # 缺指数时返回空 dict，而不是抛 KeyError，保证整段不崩
        return {x["date"]: x["close"] for x in d.get(sym, {}).get("kline", [])}

    ratios = {}
    for num, den, label, tag in PAIRS:
        kn, kd = series(num), series(den)
        common = sorted(set(kn) & set(kd))
        ratios[label] = (tag, [(dt, kn[dt] / kd[dt]) for dt in common])
    all_dates = sorted(set().union(*[set(p[0] for p in ratios[label][1]) for label in ratios])) \
        if ratios else []
    return ratios, all_dates


def pairs_conclusion_md(data_path, days=5):
    """返回 3 行简短结论（风格 + 行业轮动），供报告在表格后直接引用。

    基于 index_pairs.json 现场计算，不依赖 index_pairs_result.json，避免多一份文件同步。
    结论口径与框架 index_pairs.py 的 style_conclusion() / industry_rotation() 一致。
    """
    d = json.load(open(data_path, encoding="utf-8"))

    def name_of(sym):
        return d.get(sym, {}).get("name", sym)

    ratios, all_dates = load_ratios(data_path)
    # 计算每个配对在最近 days 天的比值变化（分子相对分母）
    perf = {}  # label -> (num_name, den_name, chg5_pct)
    for num, den, label, tag in PAIRS:
        rs = dict(ratios[label][1])
        last = all_dates[-days:] if len(all_dates) >= days else all_dates
        vals = [rs.get(dt) for dt in last if dt in rs]
        vals = [v for v in vals if v is not None]
        if len(vals) >= 2:
            chg5 = (vals[-1] / vals[0] - 1) * 100
        else:
            chg5 = None
        perf[label] = (name_of(num), name_of(den), chg5)

    lines = []

    # 1) 风格动作：以「中证红利/科创50」为核心（防御 vs 进攻），直接给"宜配"方向
    core = perf.get("中证红利/科创50")
    if core and core[2] is not None:
        c = core[2]
        if c > 2:
            lines.append(f"**今日宜配：红利/防御**（红利对科创50近5日 {c:+.1f}%，资金避险）——"
                         "加仓低估值、红利、逆势抗跌品种。")
        elif c < -2:
            lines.append(f"**今日宜配：成长/进攻**（科创50对红利近5日 {-c:+.1f}%，风险偏好升温）——"
                         "加仓成长、题材龙头。")
        else:
            lines.append("**今日宜配：均衡**（红利与科创50近5日拉锯，无明确主线）——"
                         "维持均衡、控仓观望。")
    else:
        lines.append("**今日宜配：数据不足**。")

    # 2) 行业动作：近5日相对最强/最弱（仅行业组 5 对），直接给"加/减"方向
    industry_labels = ("中证金融/科创50", "中证消费/中证工业", "中证医药/科创50",
                       "上证消费/上证医药", "中证材料/中证工业")
    ind = [(lbl, perf[lbl][0], perf[lbl][1], perf[lbl][2])
           for lbl in industry_labels if perf.get(lbl) and perf[lbl][2] is not None]
    if ind:
        strong = max(ind, key=lambda x: x[3])
        weak = min(ind, key=lambda x: x[3])
        lines.append(f"**可加：{strong[1]}**（对{strong[2]}近5日 {strong[3]:+.1f}%，资金在流入）；"
                     f"**宜减：{weak[1]}**（对{weak[2]}近5日 {weak[3]:+.1f}%，资金在流出）。")
    else:
        lines.append("**行业动作：数据不足**。")

    # 3) 一句话收尾（动作汇总）
    if core and core[2] is not None and ind:
        style_word = ("防守" if core[2] > 2 else ("进攻" if core[2] < -2 else "均衡"))
        lines.append(f"👉 **一句话：今日偏{style_word}，加{strong[1]}、减{weak[1]}。**")

    return "\n".join(lines)


def render_section_md(data_path, out_html, days=5, heading="## 四、配对指标（风格/行业轮动）"):
    """返回一段 markdown 章节（结论 + 表格 + 小图链接），供复盘/名单报告直接拼接。

    heading 可传，用于适配不同报告已有的章节编号（如复盘报告用"四"、观察名单用"三"）。
    用法： report_lines += pairs_module.render_section_md(data_path, out_html).splitlines()
    """
    md = pairs_table_md(data_path, days)
    conclusion = pairs_conclusion_md(data_path, days)
    chart = pairs_chart_html(data_path, out_html, days)
    fname = chart if isinstance(chart, str) else out_html
    return (f"{heading}\n\n"
            f"{conclusion}\n\n"
            "最近 5 个交易日逐日比值 + 每对独立拆分小图（绿=走强 / 红=走弱；— 表示该指数当日数据缺失）：\n\n"
            f"{md}\n\n"
            f"📊 拆分小图（独立打开查看）：`{fname}`")


def pairs_table_md(data_path, days=5):
    """返回 markdown 表格：最近 days 个交易日逐日比值 + 区间变化%"""
    ratios, all_dates = load_ratios(data_path)
    last = all_dates[-days:] if len(all_dates) >= 1 else []
    header = ["配对", "方向"] + [dt[5:] for dt in last] + ["区间变化%"]
    lines = ["| " + " | ".join(header) + " |",
             "|" + "|".join(["---"] * len(header)) + "|"]
    for num, den, label, tag in PAIRS:
        rs = dict(ratios[label][1])
        # 按全局 last 取列，缺失填 None（渲染为 —），不再 KeyError
        vals = [rs.get(dt) for dt in last]
        non_none = [v for v in vals if v is not None]
        chg = (non_none[-1] / non_none[0] - 1) * 100 if len(non_none) >= 2 else 0
        arrow = "▲" if chg > 0 else ("▼" if chg < 0 else "─")
        cells = [f"{v:.4f}" if v is not None else "—" for v in vals]
        row = [label, tag] + cells + [f"{arrow}{chg:+.2f}"]
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def pairs_chart_html(data_path, out_html, days=5):
    """生成独立 HTML：每对一张拆分小图（独立Y轴真实比值，仅最近 days 天，无背景，关工具栏）"""
    ratios, all_dates = load_ratios(data_path)
    last = all_dates[-days:] if len(all_dates) >= 1 else []

    n_cols, n_rows = 4, 2
    sub_titles = []
    sub_info = []
    # 先收集每个配对在 last 窗口内实际可用的日期与比值
    per_pair = {}
    for num, den, label, tag in PAIRS:
        rs = dict(ratios[label][1])
        xs = [dt for dt in last if dt in rs]
        ys = [rs[dt] for dt in xs]
        per_pair[label] = (xs, ys)
        chg = (ys[-1] / ys[0] - 1) * 100 if len(ys) >= 2 else 0
        sub_titles.append(label)
        sub_info.append((label, tag, chg))

    fig = make_subplots(rows=n_rows, cols=n_cols, subplot_titles=sub_titles,
                        vertical_spacing=0.18, horizontal_spacing=0.07,
                        specs=[[{"type": "scatter"}] * n_cols] * n_rows)

    for i, (num, den, label, tag) in enumerate(PAIRS):
        r, c = i // n_cols + 1, i % n_cols + 1
        xs, ys = per_pair[label]
        if not ys:  # 该配对在窗口内无可用数据：留空小图
            continue
        chg = (ys[-1] / ys[0] - 1) * 100
        color = "#d62728" if chg < 0 else "#2ca02c"
        text_labels = [f"{ys[0]:.3f}", "", "", "", f"{ys[-1]:.3f}"]
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="lines+markers+text",
            line=dict(color=color, width=3),
            marker=dict(size=11, color=color, line=dict(width=1.5, color="white")),
            text=text_labels, textposition=["bottom center"] + ["top center"] * 4,
            textfont=dict(size=12, color=color),
            showlegend=False, name=label,
            hovertemplate="%{x}<br>" + label + "<br>比值 %{y:.4f}<extra></extra>",
        ), row=r, col=c)
        ymin, ymax = min(ys), max(ys)
        pad = (ymax - ymin) * 0.22 + 1e-9
        fig.update_yaxes(range=[ymin - pad, ymax + pad], row=r, col=c,
                         tickformat=".2f", title_text="", showgrid=False,
                         zeroline=False, showline=False, ticks="")
        fig.update_xaxes(row=r, col=c,
                         tickvals=[xs[0], xs[-1]],
                         ticktext=[xs[0][5:], xs[-1][5:]],
                         tickfont=dict(size=10, color="#666"),
                         showgrid=False, zeroline=False, showline=False, ticks="")

    fig.update_layout(
        title="配对比值 · 最近 5 个交易日逐日变化（每对独立坐标）",
        height=680, template="plotly_white",
        margin=dict(l=30, r=15, t=60, b=30), showlegend=False,
    )
    chart_html = fig.to_html(include_plotlyjs=True, full_html=False,
                             config={"displayModeBar": False, "displaylogo": False})

    chips = []
    for label, tag, chg in sub_info:
        color = "#2ca02c" if chg >= 0 else "#d62728"
        arrow = "▲" if chg > 0 else ("▼" if chg < 0 else "─")
        chips.append(f'<div class="chip"><span class="cn">{label}</span>'
                     f'<span class="tag">{tag}</span>'
                     f'<span class="chg" style="color:{color}">{arrow}{chg:+.1f}%</span></div>')
    chips_html = '<div class="chips">' + "".join(chips) + '</div>'

    table_md = pairs_table_md(data_path, days)
    table_html = ("<table><thead><tr>" +
                  "".join(f"<th>{h}</th>" for h in table_md.splitlines()[0].strip("|").split("|")) +
                  "</tr></thead><tbody>" +
                  "".join("<tr>" + "".join(f"<td>{c}</td>" for c in ln.strip("|").split("|")) + "</tr>"
                          for ln in table_md.splitlines()[2:]) +
                  "</tbody></table>")

    d0 = last[0] if last else "?"
    d1 = last[-1] if last else "?"
    html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>配对指标每日比值 · {d1}</title>
<style>
body{{font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;margin:32px;color:#222;}}
h1{{font-size:22px;}} h2{{font-size:17px;margin-top:28px;}}
.note{{color:#666;font-size:13px;line-height:1.7;}}
table{{border-collapse:collapse;margin-top:12px;font-size:13px;}}
th,td{{border:1px solid #ddd;padding:7px 10px;text-align:center;}}
th{{background:#f5f7fa;}}
td:first-child,th:first-child{{text-align:left;font-weight:600;}}
.legend b.g{{color:#2ca02c}} .legend b.r{{color:#d62728}}
.chips{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:10px;}}
.chip{{border:1px solid #e0e0e0;border-radius:6px;padding:8px 10px;font-size:12px;display:flex;flex-direction:column;gap:2px;}}
.chip .cn{{font-weight:600;color:#222;}} .chip .tag{{color:#888;font-size:11px;}} .chip .chg{{font-weight:600;font-size:13px;}}
</style></head><body>
<h1>配对指标 · 每日比值明细（{d0} → {d1}）</h1>
<p class="note">最近 5 个交易日逐日比值 + 每对独立小图（粗线+圆点，绿=走强/红=走弱；— 表示该指数当日数据缺失）。</p>
<h2>一、最近 5 个交易日 · 逐日比值表</h2>
{table_html}
<h2>二、最近 5 日逐日变化 · 拆分小图</h2>
{chart_html}
{chips_html}
</body></html>"""
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(html)
    return out_html


if __name__ == "__main__":
    import os
    dp = "/root/ashare_monitor/index_pairs.json"
    out = "/workspace/配对指标每日比值_测试.html"
    print(pairs_table_md(dp))
    print("HTML ->", pairs_chart_html(dp, out))
