"""Render a C-only daily research watchlist from a verified frozen B observation."""

from __future__ import annotations

import argparse
from html import escape
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


REPORT_VERSION = "C_DAILY_RESEARCH_WATCHLIST_V1"
RULES = ("BALANCED_A", "CONSERVATIVE_B")


def _shown(value: Any, digits: int = 2) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:.{digits}f}"
    return "—" if value is None else escape(str(value))


def _ratio(value: Any) -> str:
    return f"{_shown(value)}×" if isinstance(value, (int, float)) else "—"


def _rule_html(rule_id: str, rule: Mapping[str, Any]) -> str:
    structure = rule.get("price_structure_observation") or {}
    trend = structure.get("trend") or {}
    pullback = structure.get("structure") or {}
    confirmation = structure.get("confirmation") or {}
    support = structure.get("support") or {}
    resistance = structure.get("stage_resistance") or {}
    volume = rule.get("volume_observation") or {}
    rv = volume.get("t_day_relative_volume") or {}
    path = volume.get("pullback_path") or {}
    match = rule.get("price_structure_match") is True
    pending = rule.get("research_match_status") == "DATA_PENDING_VERIFICATION"
    status = ("价格结构研究匹配；量能口径待核验" if match else
              "数据待核验" if pending else "不满足该规则")
    half = path.get("second_to_first_half_median_ratio")
    half_note = (f"回踩后半程日成交量中位数约为前半程的 {_shown(half * 100, 0)}%，"
                 + ("显示继续缩量。" if half < 1 else "显示量能增加。")) if isinstance(half, (int, float)) else "样本不足，无法比较回踩前后半程。"
    return f"""<section class="rule"><h4>{escape(rule_id)} <span class="badge">{status}</span></h4>
      <p>事件身份：<code>{escape(str(rule.get('price_structure_event_identity') or '—'))}</code></p>
      <p>趋势：{_shown(trend.get('status'))}；均线顺序 {_shown(trend.get('ma_order_ok'))}；收盘高于快线 {_shown(trend.get('close_above_fast_average'))}；趋势合格 {_shown(trend.get('trend_qualified'))}。</p>
      <p>回踩：{_shown(pullback.get('status'))}；前高 {_shown(pullback.get('peak_high'))}；两处低点 {_shown(pullback.get('low_one'))} / {_shown(pullback.get('low_two'))}；深度 {_shown(pullback.get('depth'))}。</p>
      <p>反弹确认：{_shown(confirmation.get('confirmation_qualified'))}；支撑参考 {_shown(pullback.get('support_floor'))}–{_shown(pullback.get('support_ceiling'))}；前高阻力 {_shown(resistance.get('stage_prior_high'))}；支撑判定 {_shown(support.get('entry_support_ok'))}。</p>
      <div class="metrics"><div><b>确认日 RV_T {_ratio(rv.get('relative_volume_ratio'))}</b><small>T 日成交量相对之前基准期中位量；只描述确认日。</small></div>
      <div><b>回踩/基准量 {_ratio(path.get('pullback_to_reference_median_ratio'))}</b><small>回踩期与此前基准期成交量中位数之比。</small></div>
      <div><b>回踩后半/前半量 {_ratio(half)}</b><small>{half_note}</small></div>
      <div><b>上涨日/下跌日量 {_ratio(path.get('up_to_down_volume_median_ratio'))}</b><small>回踩期上涨日与下跌日成交量中位数之比；不足天数时不计算。上涨日 { _shown(path.get('up_day_count'), 0) } 天，下跌日 { _shown(path.get('down_day_count'), 0) } 天。</small></div></div>
      <p class="muted">规则数据质量：{_shown(rule.get('data_quality_status'))}；判定原因：{_shown(rule.get('research_match_reason'))}。量能特征：{_shown(volume.get('feature_status'))}；口径：{_shown(volume.get('status'))}；正式量价确认：false。诊断值不证明机构行为或未来收益。</p>
    </section>"""


def build_watchlist(observation: Mapping[str, Any]) -> dict[str, Any]:
    if observation.get("schema_version") != "C_B_FROZEN_INPUT_READER_V1":
        raise ValueError("C input reader record is required")
    if observation.get("status") == "CAPTURE_FAILED" or not observation.get("observations"):
        raise ValueError("no verified C rule input is available")
    source = observation.get("source") or {}
    rows = []
    pending_by_rule = {rule: 0 for rule in RULES}
    for item in observation.get("observations") or []:
        rules = item.get("rules") or {}
        if set(rules) != set(RULES):
            raise ValueError("both frozen C rules are required")
        for rule in RULES:
            pending_by_rule[rule] += rules[rule].get("research_match_status") == "DATA_PENDING_VERIFICATION"
        matched = [rule for rule in RULES if rules[rule].get("price_structure_match") is True]
        if matched:
            rows.append({"symbol": item["symbol"], "name": item["name"],
                         "matched_rules": matched, "rules": rules,
                         "source": {key: item.get(key) for key in
                                    ("price_protocol", "price_basis", "volume_basis",
                                     "b_kline_sha256", "t_day_st_evidence",
                                     "price_response_received_at_bjt")}})
    rows.sort(key=lambda row: row["symbol"])
    return {"schema_version": REPORT_VERSION, "signal_date": source.get("target_date"),
            "input_status": observation.get("status"), "package_sha256": source.get("b_package_actual_sha256"),
            "generation_fingerprint": source.get("b_generation_fingerprint"),
            "coverage_status": source.get("coverage_status", "PARTIAL_UNVERIFIED"),
            "coverage": source.get("b_input_coverage"), "gaps": observation.get("gaps") or [],
            "matched_stock_count": len(rows),
            "matched_by_rule": {rule: sum(rule in row["matched_rules"] for row in rows) for rule in RULES},
            "data_pending_by_rule": pending_by_rule,
            "rows": rows, "formal_b_signal": False, "prospective_captured": False}


def render_html(watchlist: Mapping[str, Any]) -> str:
    date = escape(str(watchlist.get("signal_date") or "—"))
    rows = watchlist.get("rows") or []
    cards = "".join(
        f"<article class='card'><h3>{escape(str(row['symbol']))} {escape(str(row['name']))}</h3>"
        f"<p>匹配规则：{', '.join(escape(rule) for rule in row['matched_rules'])}</p>"
        + "".join(_rule_html(rule, row["rules"][rule]) for rule in RULES)
        + f"<p class='muted'>来源：B 同次冻结 HiThink 历史行情；qfq 价格；volume 单位为股，调整影响未核验。ST 名称响应：{escape(str((row['source'].get('t_day_st_evidence') or {}).get('received_at_bjt') or '—'))}；价格响应：{escape(str(row['source'].get('price_response_received_at_bjt') or '—'))}。逐票 K 线 SHA：<code>{escape(str(row['source'].get('b_kline_sha256')))}</code></p></article>"
        for row in rows)
    if not cards:
        cards = "<article class='card empty'><h2>今日无 C 研究匹配</h2><p>两套规则独立检查；数据待核验或无有效输入时不推断为规则不匹配。</p></article>"
    gaps = "、".join(escape(str(gap)) for gap in watchlist.get("gaps") or []) or "无额外缺口"
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>C 每日研究名单 · {date}</title><style>
:root{{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;color:#202c3a;background:#f4f7fa}}*{{box-sizing:border-box}}
body{{margin:0}}main{{max-width:1000px;margin:auto;padding:20px}}header{{background:#123047;color:white;padding:24px;border-radius:16px}}
h1{{margin:0 0 8px}}h2,h3,h4{{margin-bottom:8px}}p{{line-height:1.6}}.card{{background:white;border:1px solid #dce5eb;border-radius:14px;padding:18px;margin:18px 0;overflow-wrap:anywhere}}
.rule{{border-top:1px solid #dce5eb;margin-top:16px}}.badge{{font-size:.76em;background:#e5f1ec;color:#176247;padding:4px 8px;border-radius:8px}}
.metrics{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}}.metrics div{{background:#f4f7fa;padding:12px;border-radius:10px}}small{{display:block;line-height:1.5;margin-top:5px}}
.muted{{color:#536579;font-size:.92em}}code{{overflow-wrap:anywhere}}@media(max-width:640px){{main{{padding:10px}}header{{padding:18px}}.metrics{{grid-template-columns:1fr}}.card{{padding:14px}}}}
</style></head><body><main><header><h1>C 每日研究名单</h1><p>信号日期 {date} · 独立研究观察，非 Formal B 名单或买入建议</p>
<p>BALANCED_A 匹配 {_shown(watchlist['matched_by_rule']['BALANCED_A'],0)} · CONSERVATIVE_B 匹配 {_shown(watchlist['matched_by_rule']['CONSERVATIVE_B'],0)} · 去重股票 {_shown(watchlist['matched_stock_count'],0)}</p></header>
{cards}<section class='card'><h2>市场覆盖与数据质量</h2><p>只覆盖 B 冻结输入中实际评估且 C 时间、ST 证据合格的证券，不代表完整主板股票池。</p>
<p>输入状态：{escape(str(watchlist.get('input_status')))}；覆盖：{escape(str(watchlist.get('coverage_status')))}；BALANCED_A 数据待核验 {_shown(watchlist['data_pending_by_rule']['BALANCED_A'],0)}；CONSERVATIVE_B 数据待核验 {_shown(watchlist['data_pending_by_rule']['CONSERVATIVE_B'],0)}；缺口：{gaps}</p>
<p>package SHA：<code>{escape(str(watchlist.get('package_sha256')))}</code></p>
<p>量能研究数值可查看，volume 前复权影响仍为 VOLUME_BASIS_UNVERIFIED，正式量价确认保持关闭。每日名单可查看不等于完整永久前瞻证据集。</p></section></main></body></html>"""


def write_report(record_path: Path, output_dir: Path) -> dict[str, Any]:
    observation = json.loads(record_path.read_text(encoding="utf-8"))
    watchlist = build_watchlist(observation)
    if not watchlist["signal_date"] or not watchlist["package_sha256"]:
        raise ValueError("valid C input identity is required")
    digest = hashlib.sha256(json.dumps(watchlist, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    target = output_dir / watchlist["signal_date"].replace("-", "") / digest
    target.mkdir(parents=True, exist_ok=True)
    html = render_html(watchlist).encode("utf-8")
    path = target / "index.html"
    if path.exists() and path.read_bytes() != html:
        raise ValueError("immutable C report conflict")
    path.write_bytes(html)
    return {"status": "C_DAILY_REPORT_READY", "path": str(path),
            "sha256": hashlib.sha256(html).hexdigest(), "matched_stock_count": watchlist["matched_stock_count"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observation-record", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(write_report(args.observation_record, args.output_dir), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
