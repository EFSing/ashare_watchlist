"""Render a C-only daily research watchlist from a verified frozen B observation."""

from __future__ import annotations

import argparse
from html import escape
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping


REPORT_VERSION = "C_DAILY_RESEARCH_WATCHLIST_V1"
RULES = ("BALANCED_A", "CONSERVATIVE_B")
MAX_REPORT_BYTES = 2_000_000
MAX_MANIFEST_BYTES = 100_000
C_SUCCESS_WITH_MATCHES = "C_SUCCESS_WITH_MATCHES"
C_SUCCESS_NO_MATCH = "C_SUCCESS_NO_MATCH"
C_DATA_PENDING = "C_DATA_PENDING"
C_TIMEOUT = "C_TIMEOUT"
C_FAILED = "C_FAILED"
C_NOT_RUN = "C_NOT_RUN"
C_DELIVERY_STATUSES = frozenset(
    {
        C_SUCCESS_WITH_MATCHES,
        C_SUCCESS_NO_MATCH,
        C_DATA_PENDING,
        C_TIMEOUT,
        C_FAILED,
        C_NOT_RUN,
    }
)

_C_STYLE = """
#c-daily-research { min-width: 0; }
#c-daily-research, #c-daily-research * { box-sizing: border-box; }
#c-daily-research .c-research-summary { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin: 14px 0 0; }
#c-daily-research .c-research-summary > div { min-width: 0; padding: 9px 11px; border: 1px solid var(--border, #d9e0e5); background: var(--surface-2, #f7f9fa); }
#c-daily-research .c-research-summary span { display: block; color: var(--muted, #667581); font-size: 12px; }
#c-daily-research .c-research-summary strong { display: block; margin-top: 4px; font-size: 18px; font-variant-numeric: tabular-nums; }
#c-daily-research .c-stock-card { min-width: 0; margin: 9px 0 0; padding: 13px; border: 1px solid var(--border, #d9e0e5); border-left: 3px solid var(--accent, #28658a); background: var(--surface, #ffffff); }
#c-daily-research .c-stock-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 8px; min-width: 0; }
#c-daily-research .c-stock-symbol, #c-daily-research .c-stock-name { font-size: 15px; font-weight: 700; font-variant-numeric: tabular-nums; }
#c-daily-research .c-stock-name { min-width: 0; overflow-wrap: anywhere; }
#c-daily-research .c-stock-summary { margin: 8px 0 0; color: var(--muted, #667581); font-size: 13px; overflow-wrap: anywhere; }
#c-daily-research .c-stock-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 7px; margin: 11px 0 0; }
#c-daily-research .c-metric { min-width: 0; padding: 9px 10px; border: 1px solid var(--border, #d9e0e5); background: var(--surface-2, #f7f9fa); }
#c-daily-research .c-metric span { display: block; color: var(--muted, #667581); font-size: 12px; }
#c-daily-research .c-metric strong { display: block; margin-top: 3px; font-size: 16px; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
#c-daily-research .c-metric small { display: block; margin-top: 3px; color: var(--muted, #667581); font-size: 11px; line-height: 1.4; overflow-wrap: anywhere; }
#c-daily-research details { margin-top: 11px; border-top: 1px solid var(--border, #d9e0e5); }
#c-daily-research .c-audit-body { margin: 6px 0 0; color: var(--muted, #667581); font-size: 12px; overflow-wrap: anywhere; }
#c-daily-research .c-audit-body p { margin: 0 0 6px; }
#c-daily-research .c-research-notice { margin: 14px 0 0; padding: 11px 13px; border: 1px solid var(--border, #d9e0e5); border-left: 3px solid var(--warning, #a56700); background: var(--surface-2, #f7f9fa); font-size: 13px; }
#c-daily-research .c-research-empty { border-style: dashed; }
#c-daily-research code { overflow-wrap: anywhere; }
@media (max-width: 900px) {
  #c-daily-research .c-stock-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 600px) {
  #c-daily-research .c-stock-card { padding: 11px; }
  #c-daily-research .c-research-summary, #c-daily-research .c-stock-metrics { grid-template-columns: 1fr; }
}
"""

_STANDALONE_STYLE = """
:root { color-scheme: light; --bg: #f3f5f7; --surface: #ffffff; --surface-2: #f7f9fa; --text: #18232d; --muted: #667581; --border: #d9e0e5; --accent: #28658a; --warning: #a56700; --radius: 7px; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; line-height: 1.45; }
main { width: min(1440px, 100%); margin: 0 auto; padding: 18px 24px 34px; }
main > section { min-width: 0; padding: 18px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface); }
h2 { margin: 0; font-size: 20px; letter-spacing: -.01em; }
h3 { margin: 0; font-size: 15px; }
p { margin-top: 0; }
summary { cursor: pointer; color: var(--accent); font-size: 12px; }
.badge { display: inline-block; border: 1px solid currentColor; border-radius: 999px; padding: 2px 7px; color: var(--muted); font-size: 11px; line-height: 1.35; white-space: nowrap; }
.badge.warning { color: var(--warning); }
.badge.positive { color: #23825a; }
.badge.neutral { color: #61727f; }
.section-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; min-width: 0; margin-bottom: 14px; }
.section-kicker { margin: 0 0 2px; color: var(--accent); font-size: 11px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
.section-subtitle { margin: 5px 0 0; color: var(--muted); font-size: 13px; }
@media (max-width: 760px) {
  main { padding: 12px 10px 24px; }
  main > section { padding: 13px; }
  .section-head { display: block; }
}
"""


def _shown(value: Any, digits: int = 2) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:.{digits}f}"
    return "—" if value is None else escape(str(value))


def _ratio(value: Any) -> str:
    return f"{_shown(value)}×" if isinstance(value, (int, float)) else "—"


def _numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _structure_reading(rule: Mapping[str, Any]) -> str:
    """Short reading of existing C fields; direction only, no new thresholds."""

    structure = rule.get("price_structure_observation") or {}
    confirmation = structure.get("confirmation") or {}
    path = (rule.get("volume_observation") or {}).get("pullback_path") or {}
    parts: list[str] = []
    if rule.get("price_structure_match") is True:
        parts.append("价格结构匹配")
    elif rule.get("research_match_status") == "DATA_PENDING_VERIFICATION":
        parts.append("价格结构待核验")
    else:
        parts.append("价格结构未匹配")
    if confirmation.get("confirmation_qualified") is True:
        parts.append("反弹确认成立")
    elif confirmation.get("confirmation_qualified") is False:
        parts.append("反弹确认未成立")
    pullback_ratio = path.get("pullback_to_reference_median_ratio")
    if _numeric(pullback_ratio):
        parts.append("回踩整体缩量" if pullback_ratio < 1 else "回踩整体未缩量")
    half_ratio = path.get("second_to_first_half_median_ratio")
    if _numeric(half_ratio):
        parts.append("后半程继续缩量" if half_ratio < 1 else "后半程量能抬升")
    up_down_ratio = path.get("up_to_down_volume_median_ratio")
    if _numeric(up_down_ratio):
        parts.append("上涨日量能高于下跌日" if up_down_ratio > 1 else
                     "下跌日量能高于上涨日" if up_down_ratio < 1 else "上涨日与下跌日量能相当")
    return " · ".join(parts)


def _metric(label: str, value: str, note: str) -> str:
    """One metric tile. ``value`` and ``note`` must already be HTML-escaped."""

    return (f'<div class="c-metric"><span>{escape(label)}</span>'
            f'<strong>{value}</strong><small>{note}</small></div>')


def _metrics_html(rule: Mapping[str, Any]) -> str:
    structure = rule.get("price_structure_observation") or {}
    pullback = structure.get("structure") or {}
    confirmation = structure.get("confirmation") or {}
    volume = rule.get("volume_observation") or {}
    relative_volume = (volume.get("t_day_relative_volume") or {}).get("relative_volume_ratio")
    path = volume.get("pullback_path") or {}
    low_one, low_two = pullback.get("low_one"), pullback.get("low_two")
    lows = f"{_shown(low_one)} / {_shown(low_two)}" if _numeric(low_one) or _numeric(low_two) else "—"
    confirmed = confirmation.get("confirmation_qualified")
    confirm_text = "已确认" if confirmed is True else "未确认" if confirmed is False else "—"
    half = path.get("second_to_first_half_median_ratio")
    half_note = (f"约为前半程的 {_shown(half * 100, 0)}%，显示继续缩量。" if half < 1
                 else f"约为前半程的 {_shown(half * 100, 0)}%，显示量能增加。") if _numeric(half) \
        else "样本不足，无法比较回踩前后半程。"
    up_day, down_day = path.get("up_day_count"), path.get("down_day_count")
    up_down_note = (f"回踩期上涨日 {_shown(up_day, 0)} 天、下跌日 {_shown(down_day, 0)} 天；"
                    "取两类的成交量中位数之比。") if _numeric(up_day) or _numeric(down_day) \
        else "不足天数时不计算。"
    return "".join((
        _metric("前高", _shown(pullback.get("peak_high")), "回踩前的参考高点。"),
        _metric("回踩低点", lows, "回踩过程中确认的两处低点。"),
        _metric("确认状态", confirm_text, "反弹确认条件是否成立。"),
        _metric("确认日 RV_T", _ratio(relative_volume), "确认日成交量相对此前基准期中位量。"),
        _metric("回踩/基准量", _ratio(path.get("pullback_to_reference_median_ratio")),
                "回踩期与此前基准期成交量中位数之比。"),
        _metric("回踩后半/前半量", _ratio(half), half_note),
        _metric("上涨日/下跌日量", _ratio(path.get("up_to_down_volume_median_ratio")), up_down_note),
    ))


def _rule_detail(rule_id: str, rule: Mapping[str, Any]) -> str:
    """Collapsed machine-level judgement detail for one rule."""

    structure = rule.get("price_structure_observation") or {}
    trend = structure.get("trend") or {}
    pullback = structure.get("structure") or {}
    confirmation = structure.get("confirmation") or {}
    support = structure.get("support") or {}
    resistance = structure.get("stage_resistance") or {}
    volume = rule.get("volume_observation") or {}
    relative_volume = (volume.get("t_day_relative_volume") or {}).get("relative_volume_ratio")
    path = volume.get("pullback_path") or {}
    return (
        f"<p><strong>{escape(rule_id)}</strong> · 事件身份 "
        f"<code>{escape(str(rule.get('price_structure_event_identity') or '—'))}</code></p>"
        f"<p>判定 {escape(str(rule.get('research_match_status') or '—'))}；"
        f"原因 {escape(str(rule.get('research_match_reason') or '—'))}；"
        f"规则数据质量 {escape(str(rule.get('data_quality_status') or '—'))}。</p>"
        f"<p>趋势：{_shown(trend.get('status'))}；均线顺序 {_shown(trend.get('ma_order_ok'))}；"
        f"收盘高于快线 {_shown(trend.get('close_above_fast_average'))}；趋势合格 {_shown(trend.get('trend_qualified'))}。</p>"
        f"<p>回踩：{_shown(pullback.get('status'))}；前高 {_shown(pullback.get('peak_high'))}；"
        f"两处低点 {_shown(pullback.get('low_one'))} / {_shown(pullback.get('low_two'))}；"
        f"深度 {_shown(pullback.get('depth'))}。</p>"
        f"<p>反弹确认：{_shown(confirmation.get('confirmation_qualified'))}；"
        f"支撑参考 {_shown(pullback.get('support_floor'))}–{_shown(pullback.get('support_ceiling'))}；"
        f"前高阻力 {_shown(resistance.get('stage_prior_high'))}；支撑判定 {_shown(support.get('entry_support_ok'))}。</p>"
        f"<p>量能：确认日 RV_T {_ratio(relative_volume)}；"
        f"回踩/基准量 {_ratio(path.get('pullback_to_reference_median_ratio'))}；"
        f"回踩后半/前半量 {_ratio(path.get('second_to_first_half_median_ratio'))}；"
        f"上涨日/下跌日量 {_ratio(path.get('up_to_down_volume_median_ratio'))}。</p>"
        f"<p>量能诊断：特征 {_shown(volume.get('feature_status'))}；口径 {_shown(volume.get('status'))}；"
        f"正式量价确认 {_shown(volume.get('volume_confirmation_valid'))}。诊断值不证明机构行为或未来收益。</p>"
    )


def _stock_card(row: Mapping[str, Any]) -> str:
    rules = row["rules"]
    matched = [rule for rule in RULES if rule in row["matched_rules"]]
    unmatched = [rule for rule in RULES if rule not in matched]
    primary = matched[0] if matched else RULES[0]
    badges = "".join(f'<span class="badge positive">{escape(rule)}</span>' for rule in matched)
    if not badges:
        badges = '<span class="badge neutral">无命中规则</span>'
    other = ""
    if unmatched:
        lines = "".join(
            f"<p><strong>{escape(rule)} · 未匹配</strong>；原因 "
            f"{escape(str((rules[rule] or {}).get('research_match_reason') or '—'))}。"
            f"事件身份 <code>{escape(str((rules[rule] or {}).get('price_structure_event_identity') or '—'))}</code></p>"
            for rule in unmatched
        )
        other = (f'<details class="c-rule-other"><summary>其他规则详情 · '
                 + " · ".join(f"{escape(rule)} · 未匹配" for rule in unmatched)
                 + f'</summary><div class="c-audit-body">{lines}</div></details>')
    source = row.get("source") or {}
    audit = (
        f"<div class=\"c-audit-body\">"
        f"<p>事件身份与判定：</p>{''.join(_rule_detail(rule, rules[rule]) for rule in RULES)}"
        f"<p>来源：B 同次冻结 HiThink 历史行情；qfq 价格；volume 单位为股，调整影响未核验。"
        f"ST 名称响应：{escape(str((source.get('t_day_st_evidence') or {}).get('received_at_bjt') or '—'))}；"
        f"价格响应：{escape(str(source.get('price_response_received_at_bjt') or '—'))}。"
        f"逐票 K 线 SHA：<code>{escape(str(source.get('b_kline_sha256')))}</code>。</p>"
        f"</div>"
    )
    return (
        f'<article class="c-stock-card">'
        f'<div class="c-stock-head"><span class="c-stock-symbol">{escape(str(row["symbol"]))}</span>'
        f'<strong class="c-stock-name">{escape(str(row["name"]))}</strong>{badges}</div>'
        f'<p class="c-stock-summary">{escape(_structure_reading(rules[primary]))}</p>'
        f'<div class="c-stock-metrics">{_metrics_html(rules[primary])}</div>'
        f'{other}'
        f'<details class="c-stock-audit"><summary>技术审计详情</summary>{audit}</details>'
        f'</article>'
    )


def build_watchlist(observation: Mapping[str, Any]) -> dict[str, Any]:
    if observation.get("schema_version") != "C_B_FROZEN_INPUT_READER_V1":
        raise ValueError("C input reader record is required")
    if observation.get("status") == "CAPTURE_FAILED" or not observation.get("observations"):
        raise ValueError("no verified C rule input is available")
    source = observation.get("source") or {}
    groups = source.get("coverage_groups") or {}
    gaps = observation.get("gaps") or []
    coverage_breakdown = {
        "b_evaluated": len(groups.get("b_evaluated_symbols") or []),
        "b_input_isolated": len(groups.get("b_input_isolated") or []),
        "c_st_or_rule_excluded": len(groups.get("c_rule_or_st_excluded") or []),
        "c_st_unverified": len(groups.get("c_st_evidence_unresolved") or []),
        "c_request_time_unverified": sum(str(gap).startswith("B_T_DAY_PRICE_RESPONSE_TIME_UNVERIFIED:") for gap in gaps),
    }
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
            "coverage": source.get("b_input_coverage"), "coverage_breakdown": coverage_breakdown,
            "gaps": gaps,
            "matched_stock_count": len(rows),
            "matched_by_rule": {rule: sum(rule in row["matched_rules"] for row in rows) for rule in RULES},
            "data_pending_by_rule": pending_by_rule,
            "rows": rows, "formal_b_signal": False, "prospective_captured": False}


def classify_c_status(watchlist: Mapping[str, Any]) -> str:
    pending_by_rule = watchlist.get("data_pending_by_rule") or {}
    pending = any(int(pending_by_rule.get(rule) or 0) > 0 for rule in RULES)
    if pending:
        return C_DATA_PENDING
    return (
        C_SUCCESS_WITH_MATCHES
        if int(watchlist.get("matched_stock_count") or 0) > 0
        else C_SUCCESS_NO_MATCH
    )


def _section_cards(watchlist: Mapping[str, Any], c_status: str) -> str:
    rows = watchlist.get("rows") or []
    if c_status == C_DATA_PENDING and not rows:
        return ('<article class="c-stock-card c-research-empty">'
                '<p class="c-research-notice">C 研究结果待核验：部分规则输入仍待核验，'
                '当前结果不能解释为零匹配。</p></article>')
    cards = "".join(_stock_card(row) for row in rows)
    if cards:
        return cards
    return ('<article class="c-stock-card c-research-empty">'
            '<p class="c-research-notice">今日无 C 研究匹配：两套规则独立检查；'
            '该状态仅表示本次 C 结果明确记录 matched_stock_count=0。</p></article>')


def _data_quality_badge(watchlist: Mapping[str, Any], c_status: str) -> str:
    if c_status == C_DATA_PENDING:
        return '<span class="badge warning">结果待核验</span>'
    for row in watchlist.get("rows") or []:
        for rule in (row.get("rules") or {}).values():
            if str((rule.get("volume_observation") or {}).get("status") or "") == "VOLUME_BASIS_UNVERIFIED":
                return '<span class="badge warning">量能口径待核验</span>'
    if str(watchlist.get("coverage_status") or "") not in {"", "COMPLETE"}:
        return '<span class="badge warning">覆盖范围待核验</span>'
    return ""


def _section_audit(watchlist: Mapping[str, Any], c_status: str) -> str:
    """Section-level coverage/provenance detail, collapsed by default."""

    coverage = watchlist.get("coverage_breakdown") or {}
    pending = watchlist.get("data_pending_by_rule") or {}
    gaps = "、".join(escape(str(gap)) for gap in watchlist.get("gaps") or []) or "无额外缺口"
    return f"""<details class="c-research-audit"><summary>研究与数据质量详情</summary>
  <div class="c-audit-body">
    <p>只覆盖 B 冻结输入中实际评估且 C 时间、ST 证据合格的证券，不代表完整主板股票池。C 状态：{escape(c_status)}。</p>
    <p>输入状态 {escape(str(watchlist.get('input_status')))}；覆盖 {escape(str(watchlist.get('coverage_status')))}；B 已评估 {_shown(coverage.get('b_evaluated'), 0)}；B 输入隔离 {_shown(coverage.get('b_input_isolated'), 0)}；C ST/规则排除 {_shown(coverage.get('c_st_or_rule_excluded'), 0)}；C ST 证据待核验 {_shown(coverage.get('c_st_unverified'), 0)}；C 价格请求时间待核验 {_shown(coverage.get('c_request_time_unverified'), 0)}。</p>
    <p>BALANCED_A 数据待核验 {_shown(pending.get('BALANCED_A'), 0)}；CONSERVATIVE_B 数据待核验 {_shown(pending.get('CONSERVATIVE_B'), 0)}；缺口：{gaps}</p>
    <p>量能前复权影响仍为 VOLUME_BASIS_UNVERIFIED，正式量价确认关闭；formal_b_signal=false；prospective_captured=false。每日名单可查看不等于完整永久前瞻证据集。</p>
    <p>package SHA：<code>{escape(str(watchlist.get('package_sha256')))}</code><br>generation fingerprint：<code>{escape(str(watchlist.get('generation_fingerprint')))}</code></p>
  </div>
</details>"""


def render_section(watchlist: Mapping[str, Any], *, c_status: str | None = None) -> str:
    """Render the reusable, fully inline C section for standalone or B+C HTML."""

    status = c_status or classify_c_status(watchlist)
    if status not in {C_SUCCESS_WITH_MATCHES, C_SUCCESS_NO_MATCH, C_DATA_PENDING}:
        raise ValueError(f"unsupported C section status: {status}")
    date = escape(str(watchlist.get("signal_date") or "—"))
    rows = watchlist.get("rows") or []
    matched_by_rule = watchlist.get("matched_by_rule") or {}
    metric = (lambda value: "待核验") if status == C_DATA_PENDING else (lambda value: _shown(value, 0))
    heading = ("C 策略研究名单 · 待核验" if status == C_DATA_PENDING and not rows
               else f"C 策略研究名单 · {_shown(watchlist.get('matched_stock_count'), 0)} 只")
    return f"""<style data-c-daily-inline-style>{_C_STYLE}</style>
<section id="c-daily-research" class="c-research-section">
  <div class="section-head">
    <div><p class="section-kicker">C RESEARCH · 独立研究观察</p><h2>{heading}</h2>
      <p class="section-subtitle">信号日期 {date} · 独立研究观察，不属于 Formal B 正式名单，不构成买入建议。</p></div>
    {_data_quality_badge(watchlist, status)}
  </div>
  <div class="c-research-summary">
    <div><span>命中股票</span><strong>{metric(watchlist.get('matched_stock_count'))}</strong></div>
    <div><span>BALANCED_A</span><strong>{metric(matched_by_rule.get('BALANCED_A'))}</strong></div>
    <div><span>CONSERVATIVE_B</span><strong>{metric(matched_by_rule.get('CONSERVATIVE_B'))}</strong></div>
  </div>
  {_section_cards(watchlist, status)}
  {_section_audit(watchlist, status)}
</section>"""


def render_unavailable_section(report_date: str, status: str, *, reason: str | None = None) -> str:
    """Render an explicit C-unavailable state without fabricating a zero match count."""

    if status not in {C_DATA_PENDING, C_TIMEOUT, C_FAILED, C_NOT_RUN}:
        raise ValueError(f"unsupported unavailable C status: {status}")
    if status == C_DATA_PENDING:
        message = "C 研究结果今日待核验，Formal B 正式名单不受影响。"
    else:
        message = "C 研究结果今日未完成，Formal B 正式名单不受影响。"
    bounded_reason = escape(str(reason or ""))
    detail = f"<p>原因：{bounded_reason}</p>" if bounded_reason else ""
    return f"""<style data-c-daily-inline-style>{_C_STYLE}</style>
<section id="c-daily-research" class="c-research-section">
  <div class="section-head">
    <div><p class="section-kicker">C RESEARCH · 独立研究观察</p><h2>C 策略研究名单 · 待核验</h2>
      <p class="section-subtitle">信号日期 {escape(str(report_date))} · 独立研究观察，不属于 Formal B 正式名单，不构成买入建议。</p></div>
    <span class="badge warning">{escape(status)}</span>
  </div>
  <article class="c-stock-card c-research-empty">
    <p class="c-research-notice">{message}</p>
    <div class="c-audit-body">{detail}
      <p>本日不显示零匹配；只有实际 C 结果明确记录零匹配时才显示零匹配说明。formal_b_signal=false；prospective_captured=false。</p>
    </div>
  </article>
</section>"""


def _research_data_details(c_section: str) -> tuple[str, str]:
    """Convert the standalone C section into a collapsed research/data detail."""

    styles = "".join(re.findall(r"<style\b[^>]*>.*?</style>", c_section, flags=re.IGNORECASE | re.DOTALL))
    body = re.sub(r"\s*<style\b[^>]*>.*?</style>\s*", "\n", c_section, count=0, flags=re.IGNORECASE | re.DOTALL)
    opening = re.search(
        r"<section\b([^>]*\bid=[\"']c-daily-research[\"'][^>]*)>",
        body,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if opening is None:
        raise ValueError("inline C section has no c-daily-research section")
    heading_match = re.search(r"<h2>(.*?)</h2>", body, flags=re.IGNORECASE | re.DOTALL)
    heading = re.sub(r"<[^>]+>", "", heading_match.group(1)).strip() if heading_match else "研究结果"
    details_open = (
        f'<details id="c-daily-research" class="c-research-section research-data-details">'
        f'<summary>C 研究 · {heading}</summary>'
    )
    body = body[:opening.start()] + details_open + body[opening.end():]
    closing = re.search(r"</section\s*>", body, flags=re.IGNORECASE)
    if closing is None:
        raise ValueError("inline C section has no closing section tag")
    body = body[:closing.start()] + "</details>" + body[closing.end():]
    return styles, body.strip()


def compose_delivery_html(formal_html: bytes | str, c_section: str) -> bytes:
    """Inline C into an existing self-contained Formal B document without changing B bytes."""

    text = formal_html.decode("utf-8") if isinstance(formal_html, bytes) else str(formal_html)
    # Forward compatibility for the already-merged #91 shape: remove its external
    # C section/link from the presentation copy before inserting the inline section.
    text = re.sub(
        r"\s*<section\b[^>]*\bid=[\"']c-daily-research[\"'][^>]*>.*?</section>\s*",
        "\n",
        text,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(
        r"<a\b[^>]*\bhref=[\"']c_daily/[^\"']+[\"'][^>]*>.*?</a>",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if re.search(r"(?:href|src)=[\"']c_daily/", text, flags=re.IGNORECASE):
        raise ValueError("Formal B presentation contains an external C dependency")
    if not isinstance(c_section, str) or "id=\"c-daily-research\"" not in c_section:
        raise ValueError("inline C section is invalid")
    text = re.sub(
        r"<a\b[^>]*href=[\"']#c-daily-research[\"'][^>]*>.*?</a>",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    c_style, c_details = _research_data_details(c_section)
    if c_style:
        head = re.search(r"</head\s*>", text, flags=re.IGNORECASE)
        if head is not None:
            text = text[:head.start()] + c_style + "\n" + text[head.start():]
        else:
            text = c_style + text
    research_open = re.search(
        r"<section\b[^>]*id=[\"']research-data[\"'][^>]*>",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if research_open is not None:
        closing = re.search(r"</section\s*>", text[research_open.end():], flags=re.IGNORECASE)
        if closing is None:
            raise ValueError("Research/data section has no closing tag")
        close_at = research_open.end() + closing.start()
        composite = text[:close_at] + f"\n{c_details}\n" + text[close_at:]
    else:
        closing = re.search(r"</main\s*>", text, flags=re.IGNORECASE)
        if closing is None:
            closing = re.search(r"</body\s*>", text, flags=re.IGNORECASE)
        if closing is None:
            raise ValueError("Formal B report has no main or body closing tag")
        composite = text[:closing.start()] + f"\n{c_details}\n" + text[closing.start():]
    return composite.encode("utf-8")


def render_html(watchlist: Mapping[str, Any]) -> str:
    c_status = classify_c_status(watchlist)
    section = render_section(watchlist, c_status=c_status)
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>C 策略研究名单 · {escape(str(watchlist.get("signal_date") or "—"))}</title>
<style>{_STANDALONE_STYLE}</style>
</head><body><main>{section}</main></body></html>"""


def write_report(record_path: Path, output_dir: Path) -> dict[str, Any]:
    observation = json.loads(record_path.read_text(encoding="utf-8"))
    watchlist = build_watchlist(observation)
    if not watchlist["signal_date"] or not watchlist["package_sha256"]:
        raise ValueError("valid C input identity is required")
    digest = hashlib.sha256(json.dumps(watchlist, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    target = output_dir / watchlist["signal_date"].replace("-", "") / digest
    target.mkdir(parents=True, exist_ok=True)
    html = render_html(watchlist).encode("utf-8")
    c_status = classify_c_status(watchlist)
    section = render_section(watchlist, c_status=c_status).encode("utf-8")
    if len(html) > MAX_REPORT_BYTES:
        raise ValueError("C public report exceeds size limit")
    manifest = {
        "schema_version": REPORT_VERSION, "signal_date": watchlist["signal_date"],
        "version_sha256": digest, "package_sha256": watchlist["package_sha256"],
        "html_sha256": hashlib.sha256(html).hexdigest(),
        "matched_stock_count": watchlist["matched_stock_count"],
        "matched_by_rule": watchlist["matched_by_rule"],
        "c_status": c_status,
        "coverage_breakdown": watchlist["coverage_breakdown"],
        "input_status": watchlist["input_status"], "coverage_status": watchlist["coverage_status"],
        "gaps": watchlist["gaps"], "formal_b_signal": False,
        "prospective_captured": False,
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    if len(manifest_bytes) > MAX_MANIFEST_BYTES:
        raise ValueError("C public manifest exceeds size limit")
    path = target / "index.html"
    section_path = target / "section.html"
    manifest_path = target / "manifest.json"
    for destination, content in ((path, html), (section_path, section), (manifest_path, manifest_bytes)):
        if destination.exists() and destination.read_bytes() != content:
            raise ValueError("immutable C report conflict")
    path.write_bytes(html)
    section_path.write_bytes(section)
    manifest_path.write_bytes(manifest_bytes)
    return {"status": "C_DAILY_REPORT_READY", "path": str(path),
            "sha256": manifest["html_sha256"], "manifest_path": str(manifest_path),
            "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "section_path": str(section_path),
            "section_sha256": hashlib.sha256(section).hexdigest(),
            "version_sha256": digest, "signal_date": watchlist["signal_date"],
            "package_sha256": watchlist["package_sha256"],
            "html_bytes": len(html), "manifest_bytes": len(manifest_bytes), "c_status": c_status,
            "matched_stock_count": watchlist["matched_stock_count"]}


def publish_report(report: Mapping[str, Any], state_root: Path) -> dict[str, Any]:
    """Stage only public C report bytes under an independent runtime-state namespace."""
    if report.get("status") != "C_DAILY_REPORT_READY":
        raise ValueError("C report is not ready")
    day = str(report["signal_date"]).replace("-", "")
    version = str(report["version_sha256"])
    if not (len(day) == 8 and day.isdigit() and len(version) == 64
            and all(char in "0123456789abcdef" for char in version)):
        raise ValueError("invalid C report identity")
    html = Path(report["path"]).read_bytes()
    manifest = Path(report["manifest_path"]).read_bytes()
    if (hashlib.sha256(html).hexdigest() != report["sha256"]
            or hashlib.sha256(manifest).hexdigest() != report["manifest_sha256"]
            or len(html) > MAX_REPORT_BYTES or len(manifest) > MAX_MANIFEST_BYTES):
        raise ValueError("C report bytes differ from identity or size limit")
    value = json.loads(manifest)
    if (value.get("signal_date") != report["signal_date"]
            or value.get("version_sha256") != version
            or value.get("package_sha256") != report["package_sha256"]
            or value.get("html_sha256") != report["sha256"]):
        raise ValueError("C manifest identity mismatch")
    root = state_root / "data" / "reports" / "c_daily" / day
    version_root = root / version
    for component in (state_root, state_root / "data", state_root / "data" / "reports",
                      state_root / "data" / "reports" / "c_daily", root, version_root):
        if component.is_symlink():
            raise ValueError("C publication path cannot be a symlink")
    if (root / "index.html").is_symlink() or (root / "manifest.json").is_symlink():
        raise ValueError("C publication file cannot be a symlink")
    version_root.mkdir(parents=True, exist_ok=True)
    for target, content in ((version_root / "index.html", html), (version_root / "manifest.json", manifest)):
        if target.is_symlink():
            raise ValueError("C publication file cannot be a symlink")
        if target.exists() and target.read_bytes() != content:
            raise ValueError("immutable C report version conflict")
        target.write_bytes(content)
    root.mkdir(parents=True, exist_ok=True)
    (root / "index.html").write_bytes(html)
    (root / "manifest.json").write_bytes(manifest)
    paths = [f"data/reports/c_daily/{day}/{version}/{name}" for name in ("index.html", "manifest.json")]
    paths += [f"data/reports/c_daily/{day}/{name}" for name in ("index.html", "manifest.json")]
    return {"status": "C_REPORT_STAGED", "paths": paths, "signal_date": report["signal_date"],
            "version_sha256": version, "html_sha256": report["sha256"],
            "manifest_sha256": report["manifest_sha256"], "matched_stock_count": value["matched_stock_count"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observation-record", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--publish-result", type=Path)
    parser.add_argument("--state-root", type=Path)
    args = parser.parse_args()
    if args.publish_result:
        if not args.state_root:
            parser.error("publishing requires --state-root")
        run_result = json.loads(args.publish_result.read_text(encoding="utf-8"))
        result = publish_report(run_result["report"], args.state_root)
    else:
        if not args.observation_record or not args.output_dir:
            parser.error("generation requires --observation-record and --output-dir")
        result = write_report(args.observation_record, args.output_dir)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
