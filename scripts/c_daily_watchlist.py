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
#c-daily-research { color: #202c3a; }
#c-daily-research, #c-daily-research * { box-sizing: border-box; }
#c-daily-research .c-daily-header { background: #123047; color: white; padding: 24px; border-radius: 16px; }
#c-daily-research h2, #c-daily-research h3, #c-daily-research h4 { margin: 0 0 8px; }
#c-daily-research p { line-height: 1.6; }
#c-daily-research .c-daily-card { background: white; border: 1px solid #dce5eb; border-radius: 14px; padding: 18px; margin: 18px 0; overflow-wrap: anywhere; }
#c-daily-research .c-daily-rule { border-top: 1px solid #dce5eb; margin-top: 16px; }
#c-daily-research .c-daily-badge { font-size: .76em; background: #e5f1ec; color: #176247; padding: 4px 8px; border-radius: 8px; }
#c-daily-research .c-daily-metrics { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
#c-daily-research .c-daily-metrics > div { background: #f4f7fa; padding: 12px; border-radius: 10px; }
#c-daily-research small { display: block; line-height: 1.5; margin-top: 5px; }
#c-daily-research .c-daily-muted { color: #536579; font-size: .92em; }
#c-daily-research code { overflow-wrap: anywhere; }
#c-daily-research .c-daily-facts { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-top: 14px; }
#c-daily-research .c-daily-facts > div { background: rgba(255,255,255,.12); border-radius: 10px; padding: 10px; }
#c-daily-research .c-daily-facts strong { display: block; margin-top: 3px; font-size: 1.15em; }
#c-daily-research .c-daily-empty { border-style: dashed; }
#c-daily-research .c-daily-notice { background: #fff7e6; border: 1px solid #f0d28c; border-radius: 10px; padding: 12px; }
@media (max-width: 700px) {
  #c-daily-research .c-daily-header { padding: 18px; }
  #c-daily-research .c-daily-facts, #c-daily-research .c-daily-metrics { grid-template-columns: 1fr; }
  #c-daily-research .c-daily-card { padding: 14px; }
}
"""


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
    return f"""<section class="c-daily-rule"><h4>{escape(rule_id)} <span class="c-daily-badge">{status}</span></h4>
      <p>事件身份：<code>{escape(str(rule.get('price_structure_event_identity') or '—'))}</code></p>
      <p>趋势：{_shown(trend.get('status'))}；均线顺序 {_shown(trend.get('ma_order_ok'))}；收盘高于快线 {_shown(trend.get('close_above_fast_average'))}；趋势合格 {_shown(trend.get('trend_qualified'))}。</p>
      <p>回踩：{_shown(pullback.get('status'))}；前高 {_shown(pullback.get('peak_high'))}；两处低点 {_shown(pullback.get('low_one'))} / {_shown(pullback.get('low_two'))}；深度 {_shown(pullback.get('depth'))}。</p>
      <p>反弹确认：{_shown(confirmation.get('confirmation_qualified'))}；支撑参考 {_shown(pullback.get('support_floor'))}–{_shown(pullback.get('support_ceiling'))}；前高阻力 {_shown(resistance.get('stage_prior_high'))}；支撑判定 {_shown(support.get('entry_support_ok'))}。</p>
      <div class="c-daily-metrics"><div><b>确认日 RV_T {_ratio(rv.get('relative_volume_ratio'))}</b><small>T 日成交量相对之前基准期中位量；只描述确认日。</small></div>
      <div><b>回踩/基准量 {_ratio(path.get('pullback_to_reference_median_ratio'))}</b><small>回踩期与此前基准期成交量中位数之比。</small></div>
      <div><b>回踩后半/前半量 {_ratio(half)}</b><small>{half_note}</small></div>
      <div><b>上涨日/下跌日量 {_ratio(path.get('up_to_down_volume_median_ratio'))}</b><small>回踩期上涨日与下跌日成交量中位数之比；不足天数时不计算。上涨日 { _shown(path.get('up_day_count'), 0) } 天，下跌日 { _shown(path.get('down_day_count'), 0) } 天。</small></div></div>
      <p class="c-daily-muted">规则数据质量：{_shown(rule.get('data_quality_status'))}；判定原因：{_shown(rule.get('research_match_reason'))}。量能特征：{_shown(volume.get('feature_status'))}；口径：{_shown(volume.get('status'))}；正式量价确认：false。诊断值不证明机构行为或未来收益。</p>
    </section>"""


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
        return """<article class='c-daily-card c-daily-empty'><h3>C 研究结果待核验</h3>
<p class='c-daily-notice'>部分规则输入仍待核验，当前结果不能解释为零匹配。</p></article>"""
    cards = "".join(
        f"<article class='c-daily-card'><h3>{escape(str(row['symbol']))} {escape(str(row['name']))}</h3>"
        f"<p>匹配规则：{', '.join(escape(rule) for rule in row['matched_rules'])}</p>"
        + "".join(_rule_html(rule, row["rules"][rule]) for rule in RULES)
        + f"<p class='c-daily-muted'>来源：B 同次冻结 HiThink 历史行情；qfq 价格；volume 单位为股，调整影响未核验。ST 名称响应：{escape(str((row['source'].get('t_day_st_evidence') or {}).get('received_at_bjt') or '—'))}；价格响应：{escape(str(row['source'].get('price_response_received_at_bjt') or '—'))}。逐票 K 线 SHA：<code>{escape(str(row['source'].get('b_kline_sha256')))}</code></p></article>"
        for row in rows
    )
    if cards:
        return cards
    return """<article class='c-daily-card c-daily-empty'><h3>今日无 C 研究匹配</h3>
<p>两套规则独立检查；该状态仅表示本次 C 结果明确记录 matched_stock_count=0。</p></article>"""


def render_section(watchlist: Mapping[str, Any], *, c_status: str | None = None) -> str:
    """Render the reusable, fully inline C section for standalone or B+C HTML."""

    status = c_status or classify_c_status(watchlist)
    if status not in {C_SUCCESS_WITH_MATCHES, C_SUCCESS_NO_MATCH, C_DATA_PENDING}:
        raise ValueError(f"unsupported C section status: {status}")
    date = escape(str(watchlist.get("signal_date") or "—"))
    coverage = watchlist.get("coverage_breakdown") or {}
    gaps = "、".join(escape(str(gap)) for gap in watchlist.get("gaps") or []) or "无额外缺口"
    matched_by_rule = watchlist.get("matched_by_rule") or {}
    metric = (lambda value: "待核验") if status == C_DATA_PENDING else (lambda value: _shown(value, 0))
    return f"""<style data-c-daily-inline-style>{_C_STYLE}</style>
<section id="c-daily-research" class="c-daily-section">
  <div class="c-daily-header"><p>INDEPENDENT RESEARCH · C</p><h2>C 策略研究名单</h2>
    <p>信号日期 {date} · 独立研究观察，不属于 Formal B 正式名单，不构成买入建议</p>
    <div class="c-daily-facts">
      <div><span>matched_stock_count</span><strong>{metric(watchlist.get('matched_stock_count'))}</strong></div>
      <div><span>BALANCED_A</span><strong>{metric(matched_by_rule.get('BALANCED_A'))}</strong></div>
      <div><span>CONSERVATIVE_B</span><strong>{metric(matched_by_rule.get('CONSERVATIVE_B'))}</strong></div>
      <div><span>formal_b_signal</span><strong>false</strong></div>
    </div>
  </div>
  <p class="c-daily-notice">C 状态：{escape(status)}；正式量价确认关闭（VOLUME_BASIS_UNVERIFIED）。C 研究观察不属于 Formal B 正式名单。</p>
  {_section_cards(watchlist, status)}
  <article class='c-daily-card'><h3>市场覆盖与数据质量</h3>
    <p>只覆盖 B 冻结输入中实际评估且 C 时间、ST 证据合格的证券，不代表完整主板股票池。</p>
    <p>输入状态：{escape(str(watchlist.get('input_status')))}；覆盖：{escape(str(watchlist.get('coverage_status')))}；B 已评估 {_shown(coverage.get('b_evaluated'),0)}；B 输入隔离 {_shown(coverage.get('b_input_isolated'),0)}；C ST/规则排除 {_shown(coverage.get('c_st_or_rule_excluded'),0)}；C ST 证据待核验 {_shown(coverage.get('c_st_unverified'),0)}；C 价格请求时间待核验 {_shown(coverage.get('c_request_time_unverified'),0)}。BALANCED_A 数据待核验 {_shown((watchlist.get('data_pending_by_rule') or {}).get('BALANCED_A'),0)}；CONSERVATIVE_B 数据待核验 {_shown((watchlist.get('data_pending_by_rule') or {}).get('CONSERVATIVE_B'),0)}；缺口：{gaps}</p>
    <p>package SHA：<code>{escape(str(watchlist.get('package_sha256')))}</code></p>
    <p>量能研究数值可查看，volume 前复权影响仍为 VOLUME_BASIS_UNVERIFIED，formal_b_signal=false；每日名单可查看不等于完整永久前瞻证据集。</p>
  </article>
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
    detail = f"<p class='c-daily-muted'>原因：{bounded_reason}</p>" if bounded_reason else ""
    return f"""<style data-c-daily-inline-style>{_C_STYLE}</style>
<section id="c-daily-research" class="c-daily-section">
  <div class="c-daily-header"><p>INDEPENDENT RESEARCH · C</p><h2>C 策略研究名单</h2>
    <p>信号日期 {escape(str(report_date))} · 独立研究观察，不属于 Formal B 正式名单，不构成买入建议</p>
    <div class="c-daily-facts"><div><span>C 状态</span><strong>{escape(status)}</strong></div><div><span>formal_b_signal</span><strong>false</strong></div></div>
  </div>
  <article class='c-daily-card c-daily-empty'><p class="c-daily-notice">{message}</p>{detail}
    <p class='c-daily-muted'>本日不显示零匹配；只有实际 C 结果明确记录零匹配时才显示零匹配说明。</p>
  </article>
</section>"""


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
    anchor = re.search(r"</main\s*>", text, flags=re.IGNORECASE)
    if anchor is None:
        anchor = re.search(r"</body\s*>", text, flags=re.IGNORECASE)
    if anchor is None:
        raise ValueError("Formal B report has no main or body closing tag")
    composite = text[:anchor.start()] + f"\n{c_section}\n" + text[anchor.start():]
    return composite.encode("utf-8")


def render_html(watchlist: Mapping[str, Any]) -> str:
    c_status = classify_c_status(watchlist)
    section = render_section(watchlist, c_status=c_status)
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>C 每日研究名单 · {escape(str(watchlist.get("signal_date") or "—"))}</title><style>
:root{{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;color:#202c3a;background:#f4f7fa}}*{{box-sizing:border-box}}
body{{margin:0}}main{{max-width:1000px;margin:auto;padding:20px}}
</style></head><body><main>{section}</main></body></html>"""


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
