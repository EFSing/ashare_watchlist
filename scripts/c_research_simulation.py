"""Apply the daily report's B theoretical execution model to frozen C signals."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
from html import escape
import json
import math
from pathlib import Path
from statistics import mean
from typing import Any, Mapping

from c_daily_watchlist import build_watchlist
from c_pre_outcome_design import canonical_json
from generation_contract import AUTHORIZED_WEEKEND_BACKFILL
from preview_b_shortlist import _position_metrics
from track_perf import (
    PERFORMANCE_DATA_INCOMPLETE,
    RULE_STATUS_AMBIGUOUS,
    RULE_STATUS_CLOSED,
    RULE_STATUS_NOT_YET_ELIGIBLE,
    RULE_STATUS_OPEN,
    RULE_STATUS_UNTRIGGERED,
    STRATEGY_RULE_CONFIG_ERROR,
    STRATEGY_RULE_PERFORMANCE_MODEL,
    _strategy_rule_trade_row,
    parse_date,
    stable_signal_id,
)
from trading_calendar import default_calendar


VERSION = "C_RESEARCH_SIMULATION_V1"
STATE_PATH = Path("data/research/c_simulation_v1")
_BJT = timezone(timedelta(hours=8))
_STATUS = {
    RULE_STATUS_NOT_YET_ELIGIBLE: "待次一交易日",
    RULE_STATUS_UNTRIGGERED: "未触发",
    RULE_STATUS_OPEN: "模拟持有",
    RULE_STATUS_CLOSED: "已结案",
    RULE_STATUS_AMBIGUOUS: "同日顺序不明",
    PERFORMANCE_DATA_INCOMPLETE: "行情不足",
    STRATEGY_RULE_CONFIG_ERROR: "价位不成立",
}
_SETTLED_FIELDS = (
    "signal_id", "signal_date", "code", "name", "setup", "trigger", "stop", "target",
    "status", "entry_date", "entry_price", "exit_date", "exit_price", "exit_reason",
    "realized_return_pct", "realized_r", "historical_provenance",
)


def _digest(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _read(path: Path, digest: str) -> dict[str, Any]:
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != digest:
        raise ValueError("C simulation input SHA mismatch")
    return json.loads(raw)


def _price_identity(bar: Mapping[str, Any]) -> str:
    return _digest([bar[key] for key in ("date", "open", "high", "low", "close")])


def _matches_price_anchor(signal: Mapping[str, Any], bars: list[dict[str, Any]]) -> bool:
    anchor = next((bar for bar in bars if bar["date"] == signal["date"]), None)
    return anchor is not None and _price_identity(anchor) == signal["price_anchor_sha256"]


def _signals(watchlist: Mapping[str, Any], histories: Mapping[str, Any]) -> list[dict[str, Any]]:
    day = watchlist["signal_date"]
    signals = []
    for candidate in watchlist["rows"]:
        code = candidate["symbol"]
        bars = histories[code]["bars"]
        if bars[-1]["date"] != day:
            raise ValueError("C research candidate lacks its signal-day price bar")
        close = bars[-1]["close"]
        ma5 = mean(bar["close"] for bar in bars[-5:])
        for rule_name in candidate["matched_rules"]:
            rules = candidate.get("rules")
            rule = rules.get(rule_name) if isinstance(rules, Mapping) else None
            observation = rule.get("price_structure_observation") if isinstance(rule, Mapping) else None
            structure = observation.get("structure") if isinstance(observation, Mapping) else None
            if not isinstance(structure, Mapping):
                raise ValueError(
                    f"C research candidate {code}/{rule_name} lacks price_structure_observation.structure"
                )
            for field in ("rebound_high", "support_floor", "stage_prior_high"):
                value = structure.get(field)
                if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
                    raise ValueError(
                        f"C research candidate {code}/{rule_name} lacks numeric structure.{field}"
                    )
            trigger = round(max(structure["rebound_high"], ma5), 2)
            stop = round(structure["support_floor"] * .98, 2)
            pressure = structure["stage_prior_high"]
            ref_entry = Decimal(str(max(close, trigger)))
            risk = ref_entry - Decimal(str(stop))
            if risk <= 0:
                target = round(close + 2.5 * (close - stop), 2)
            elif Decimal(str(pressure)) - ref_entry >= 2 * risk:
                target = round(pressure, 2)
            else:
                target = float((ref_entry + Decimal("2.5") * risk).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                ))
            signals.append({
                "signal_id": stable_signal_id(VERSION, day, code, rule_name),
                "strategy_version": VERSION, "date": day, "code": code,
                "name": candidate["name"], "setup": rule_name,
                "trigger": trigger, "stop": stop, "target": target,
                "price_anchor_sha256": _price_identity(bars[-1]),
            })
    return signals


def _simulate(signal: Mapping[str, Any], histories: Mapping[str, Any], day: str, calendar: Any) -> dict[str, Any]:
    code = signal["code"]
    history = histories.get(code, {})
    bars = history.get("bars", [])
    comparable = _matches_price_anchor(signal, bars)
    provenance = {"by_code": {code: {"source": "SAME_RUNNER_QFQ_PREFIX",
                                     "normalized_data_sha256": history.get("normalized_data_sha256")}}}
    row = _strategy_rule_trade_row(signal, {code: bars} if comparable else {}, provenance, parse_date(day), calendar)
    if row["status"] == PERFORMANCE_DATA_INCOMPLETE and not comparable:
        row["reason"] = "信号日价格基准缺失或已变化"
    return row


def capture(b_result: Mapping[str, Any], consumed: Mapping[str, Any], record: Path,
            state_root: Path, report: Mapping[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """Freeze today's C plans and compute the report using the existing runner's inputs."""
    day = b_result["as_of_date"]
    current = (now or datetime.now(_BJT)).astimezone(_BJT)
    calendar = default_calendar()
    if (current.date().isoformat() != day or current < calendar.session_close(day)
            or b_result.get("acquisition_timing") == AUTHORIZED_WEEKEND_BACKFILL):
        raise ValueError("C simulation requires a genuine current-day close")
    package_info = b_result["input_package"]
    observation = _read(record, consumed["record_sha256"])
    source = observation["source"]
    acquired, read_at = (datetime.fromisoformat(source[key]) for key in ("b_acquired_at_bjt", "c_read_at_bjt"))
    if (source["target_date"] != day or source["b_package_actual_sha256"] != package_info["file_sha256"]
            or source["handoff"]["mode"] != "SAME_RUNNER_READ_ONLY"
            or acquired.tzinfo is None or read_at.tzinfo is None
            or acquired.astimezone(_BJT).date().isoformat() != day
            or not calendar.session_close(day) <= acquired <= read_at <= current):
        raise ValueError("C simulation same-day source mismatch")
    package = _read(Path(package_info["path"]), package_info["file_sha256"])
    watchlist = build_watchlist(observation)
    manifest = _read(Path(report["manifest_path"]), report["manifest_sha256"])
    if (manifest["version_sha256"] != sha256(json.dumps(watchlist, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            or manifest["signal_date"] != day or manifest["package_sha256"] != package_info["file_sha256"]):
        raise ValueError("C simulation report identity mismatch")
    histories = {
        item["symbol"]: item for item in package["generation_input_manifest"]["stock_klines"]
        if item["adjustment_mode"] == "PROVIDER_QFQ_SNAPSHOT"
    }
    fresh = _signals(watchlist, histories)
    token = day.replace("-", "")
    signals, settled = {}, {}
    for path in sorted((state_root / STATE_PATH).glob("????????.json")):
        if path.stem >= token:
            if path.stem == token:
                raise ValueError("C simulation already published for this day")
            raise ValueError("C simulation would precede a published session")
        previous = json.loads(path.read_bytes())
        if previous["version"] != VERSION or previous["date"].replace("-", "") != path.stem:
            raise ValueError("C simulation history identity mismatch")
        signals.update((row["signal_id"], row) for row in previous["signals"])
        settled.update((row["signal_id"], row) for row in previous["settled"])
    signals.update((row["signal_id"], row) for row in fresh)
    rows = [
        settled[identity] if identity in settled else _simulate(signal, histories, day, calendar)
        for identity, signal in signals.items()
    ]
    positions = {}
    for identity, signal in signals.items():
        bars = histories.get(signal["code"], {}).get("bars", [])
        if _matches_price_anchor(signal, bars):
            signal_day = signal["date"]
            prefix = [bar for bar in bars if bar["date"] <= signal_day]
            positions[identity] = _position_metrics(prefix, signal_day)
    payload = {
        "version": VERSION, "date": day, "c_manifest_sha256": report["manifest_sha256"],
        "c_observation_sha256": consumed["record_sha256"], "package_sha256": package_info["file_sha256"],
        "execution_model": STRATEGY_RULE_PERFORMANCE_MODEL,
        "execution_source_sha256": sha256(Path(_strategy_rule_trade_row.__code__.co_filename).read_bytes()).hexdigest(),
        "signals": fresh,
        "settled": [
            {key: row[key] for key in _SETTLED_FIELDS} for row in rows
            if row["signal_id"] not in settled and row["status"] in {RULE_STATUS_CLOSED, RULE_STATUS_AMBIGUOUS}
        ],
    }
    directory = Path(report["manifest_path"]).parent
    ledger = directory / "c-simulation.json"
    ledger.write_bytes((canonical_json(payload) + "\n").encode("utf-8"))
    section = directory / "c-simulation.html"
    section.write_bytes(render_section(day, rows, positions=positions).encode("utf-8"))
    return {"ledger": str(ledger), "ledger_sha256": sha256(ledger.read_bytes()).hexdigest(),
            "section": str(section), "section_sha256": sha256(section.read_bytes()).hexdigest()}


_RULE_LABELS = {
    "BALANCED_A": "平衡版",
    "CONSERVATIVE_B": "保守版",
}
_POSITION_BADGES = {
    "BOTTOM_250D": ("一年底部区", "bottom"),
    "LOW_MID_250D": ("一年中低位", "low-mid"),
    "HIGH_250D": ("一年中高位", "high"),
}
_SIM_STYLE = """
#c-research-simulation { min-width: 0; margin: 14px 0 0; padding: 14px; border: 1px solid var(--border, #d9e0e5); border-top: 3px solid var(--accent, #28658a); border-radius: var(--radius, 7px); background: var(--surface, #ffffff); }
#c-research-simulation, #c-research-simulation * { box-sizing: border-box; }
#c-research-simulation .c-sim-kpi-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin: 12px 0 0; }
#c-research-simulation .c-sim-kpi { min-width: 0; padding: 10px 11px; border: 1px solid var(--border, #d9e0e5); background: var(--surface-2, #f7f9fa); }
#c-research-simulation .c-sim-kpi span { display: block; color: var(--muted, #667581); font-size: 12px; }
#c-research-simulation .c-sim-kpi strong { display: block; margin-top: 4px; font-size: 18px; font-variant-numeric: tabular-nums; }
#c-research-simulation .c-sim-kpi small { display: block; margin-top: 3px; color: var(--muted, #667581); font-size: 11px; line-height: 1.35; overflow-wrap: anywhere; }
#c-research-simulation .c-sim-status-line { margin: 10px 0 0; color: var(--muted, #667581); font-size: 12px; overflow-wrap: anywhere; }
#c-research-simulation .c-sim-holdings { margin: 14px 0 0; }
#c-research-simulation .c-sim-holdings-head { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 4px 12px; margin-bottom: 8px; }
#c-research-simulation .c-sim-holdings-head strong { font-size: 13px; color: var(--text, #18232d); }
#c-research-simulation .c-sim-holdings-head small { color: var(--muted, #667581); font-size: 11px; }
#c-research-simulation .c-sim-holding-list { display: grid; gap: 8px; }
#c-research-simulation .c-sim-holding-card { min-width: 0; padding: 11px 12px; border: 1px solid var(--border, #d9e0e5); border-left: 3px solid var(--accent, #28658a); background: var(--surface-2, #f7f9fa); }
#c-research-simulation .c-sim-holding-top { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 6px 10px; min-width: 0; }
#c-research-simulation .c-sim-holding-title { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 8px; min-width: 0; }
#c-research-simulation .c-sim-holding-title strong { font-size: 14px; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
#c-research-simulation .c-sim-holding-badges { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
#c-research-simulation .c-sim-holding-facts { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 8px 12px; margin-top: 9px; }
#c-research-simulation .c-sim-holding-facts > div { min-width: 0; }
#c-research-simulation .c-sim-holding-facts span { display: block; color: var(--muted, #667581); font-size: 11px; }
#c-research-simulation .c-sim-holding-facts strong { display: block; margin-top: 2px; font-size: 13px; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
#c-research-simulation .c-sim-rules { margin-top: 10px; border: 1px solid var(--border, #d9e0e5); border-radius: var(--radius, 7px); background: var(--surface-2, #f7f9fa); }
#c-research-simulation .c-sim-rules > summary { padding: 9px 11px; color: var(--accent, #28658a); font-size: 12px; font-weight: 650; cursor: pointer; }
#c-research-simulation .c-sim-rules ul { margin: 0; padding: 0 14px 11px 28px; color: var(--text, #18232d); font-size: 12px; line-height: 1.55; }
#c-research-simulation .c-sim-rules li + li { margin-top: 5px; }
#c-research-simulation .c-sim-detail { margin-top: 10px; }
#c-research-simulation .c-sim-detail > .table-scroll { padding: 0 10px 10px; }
#c-research-simulation table { min-width: 780px; }
#c-research-simulation .c-sim-pnl { font-weight: 650; font-variant-numeric: tabular-nums; }
#c-research-simulation .c-sim-pnl.positive { color: var(--positive, #c43e3e); }
#c-research-simulation .c-sim-pnl.negative { color: var(--negative, #23825a); }
#c-research-simulation .c-sim-pnl.neutral { color: var(--text, #18232d); }
#c-research-simulation .badge.c-sim-open { color: var(--accent, #28658a); }
#c-research-simulation .position-badge { display: inline-block; border-radius: 999px; padding: 3px 8px; font-size: 11px; font-weight: 650; }
#c-research-simulation .position-badge.bottom { color: #176044; background: #e3f4ea; }
#c-research-simulation .position-badge.low-mid { color: #27516d; background: #e7eff5; }
#c-research-simulation .position-badge.high { color: #765121; background: #f7efdf; }
#c-research-simulation td .position-badge { margin-inline-start: 4px; }
#c-research-simulation .c-sim-rule-gloss { margin-left: 4px; color: var(--muted, #667581); font-size: 11px; }
@media (max-width: 900px) {
  #c-research-simulation .c-sim-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  #c-research-simulation .c-sim-holding-facts { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@media (max-width: 600px) {
  #c-research-simulation { padding: 11px; }
  #c-research-simulation .c-sim-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 7px; }
  #c-research-simulation .c-sim-holding-facts { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px 10px; }
}
"""


def _pnl_tone(value: Any) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        if value > 0:
            return "positive"
        if value < 0:
            return "negative"
    return "neutral"


def _status_presentation(row: Mapping[str, Any]) -> tuple[str, str]:
    exit_reason = row.get("exit_reason")
    if exit_reason == "TARGET":
        return "模拟止盈", "positive"
    if exit_reason == "STOP":
        return "模拟止损", "negative"
    raw_status = row.get("status")
    label = _STATUS.get(raw_status, str(raw_status or "—"))
    reason = row.get("reason")
    if raw_status in {PERFORMANCE_DATA_INCOMPLETE, STRATEGY_RULE_CONFIG_ERROR} and reason:
        label += f"（{reason}）"
    if raw_status == RULE_STATUS_OPEN:
        return label, "c-sim-open"
    if raw_status in {RULE_STATUS_AMBIGUOUS, PERFORMANCE_DATA_INCOMPLETE, STRATEGY_RULE_CONFIG_ERROR}:
        return label, "warning"
    return label, "neutral"


def _rule_cell_html(setup: Any) -> str:
    code = str(setup or "—")
    gloss = _RULE_LABELS.get(code)
    if gloss:
        return f'{escape(code)}<span class="c-sim-rule-gloss">{escape(gloss)}</span>'
    return escape(code)


def _format_price(value: Any) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return f"{value:.2f}"
    return "—"


def _format_pnl(row: Mapping[str, Any]) -> tuple[str, str]:
    result = row.get("realized_return_pct")
    if isinstance(result, (int, float)) and not isinstance(result, bool) and math.isfinite(result):
        return f"{result:+.2f}%", _pnl_tone(result)
    mark = row.get("mark_return_pct")
    if isinstance(mark, (int, float)) and not isinstance(mark, bool) and math.isfinite(mark):
        return f"浮动 {mark:+.2f}%", _pnl_tone(mark)
    return "—", "neutral"


def _rules_details_html() -> str:
    return (
        '<details class="c-sim-rules">'
        '<summary>一分钟看懂 C 模拟规则（不限时规则模拟 · 与主策略 B 隔离）</summary>'
        '<ul>'
        '<li><strong>独立口径</strong>：复用主策略 B 的不限时理论规则模拟，仅使用 C 信号的价位与日线计算，不影响主策略 B 正式名单与绩效。</li>'
        '<li><strong>模拟买卖</strong>：从信号次一交易日起，盘中触及触发价即按触发价模拟买入；买入次一交易日起触及目标价记「模拟止盈」、触及止损价记「模拟止损」，无固定到期日。</li>'
        '<li><strong>边界与重复信号</strong>：同日同时触及止损与目标价记「同日顺序不明」并留空收益；同一股票跨日或跨 C 规则重复入选时，按「信号日 + C 规则」独立记录。</li>'
        '<li><strong>收益说明</strong>：浮动与已结案收益均为毛收益，未扣除手续费、印花税与滑点，不代表真实单账户持仓或实盘收益。</li>'
        '</ul></details>'
    )


def _position_badge_html(position: Mapping[str, Any]) -> str:
    zone = _POSITION_BADGES.get(position.get("position_zone"))
    pos250 = position.get("pos250")
    if zone is None or pos250 is None:
        return ""
    label, tone = zone
    return f'<span class="position-badge {tone}">{label} · 位置 {pos250:.1%}</span>'


def _open_holdings_html(rows: list[dict[str, Any]], positions: Mapping[str, Mapping[str, Any]]) -> str:
    open_rows = [row for row in rows if row.get("status") == RULE_STATUS_OPEN]
    if not open_rows:
        return ""
    cards = []
    for row in sorted(open_rows, key=lambda item: (item.get("signal_date") or "", item.get("code") or ""), reverse=True):
        pnl_text, pnl_tone = _format_pnl(row)
        setup = str(row.get("setup") or "—")
        setup_label = f"{setup} · {_RULE_LABELS[setup]}" if setup in _RULE_LABELS else setup
        entry_price = _format_price(row.get("entry_price") if row.get("entry_price") is not None else row.get("trigger"))
        cards.append(
            '<article class="c-sim-holding-card">'
            '<div class="c-sim-holding-top">'
            f'<div class="c-sim-holding-title"><strong>{escape(str(row.get("code") or "—"))} {escape(str(row.get("name") or ""))}</strong>'
            f'<span class="badge neutral">{escape(setup_label)}</span></div>'
            '<div class="c-sim-holding-badges">'
            '<span class="badge c-sim-open">模拟持有</span>'
            f'{_position_badge_html(positions.get(row.get("signal_id"), {}))}'
            f'<span class="c-sim-pnl {pnl_tone}">{escape(pnl_text)}</span>'
            '</div></div>'
            '<div class="c-sim-holding-facts">'
            f'<div><span>信号日</span><strong>{escape(str(row.get("signal_date") or "—"))}</strong></div>'
            f'<div><span>模拟买入日</span><strong>{escape(str(row.get("entry_date") or "—"))}</strong></div>'
            f'<div><span>模拟买价（触发）</span><strong>{entry_price}</strong></div>'
            f'<div><span>止损价</span><strong>{_format_price(row.get("stop"))}</strong></div>'
            f'<div><span>目标价</span><strong>{_format_price(row.get("target"))}</strong></div>'
            f'<div><span>浮动毛收益</span><strong class="c-sim-pnl {pnl_tone}">{escape(pnl_text)}</strong></div>'
            '</div></article>'
        )
    return (
        '<div class="c-sim-holdings">'
        '<div class="c-sim-holdings-head">'
        f'<strong>当前模拟持仓 · {len(open_rows)} 只</strong>'
        '<small>已按触发价模拟买入，等待后续触及目标价或止损价</small>'
        '</div>'
        f'<div class="c-sim-holding-list">{"".join(cards)}</div>'
        '</div>'
    )


def render_section(
    day: str,
    rows: list[dict[str, Any]] | None = None,
    *,
    positions: Mapping[str, Mapping[str, Any]] | None = None,
) -> str:
    safe_day = escape(day)
    style = f'<style data-c-simulation-inline-style>{_SIM_STYLE}</style>'
    if rows is None:
        return (
            f'<section id="c-research-simulation">{style}'
            '<div class="section-head"><div>'
            '<p class="section-kicker">C SIMULATION · 副线规则模拟</p>'
            '<h2>C研究模拟</h2>'
            f'<p class="section-subtitle">截至 {safe_day} · 独立副线研究，与主策略 B 相互隔离；不限时规则模拟，不代表真实账户持仓。</p>'
            '</div><span class="badge warning">本期暂不可用</span></div>'
            '<div class="empty-state"><strong>本期 C 模拟数据暂不可用</strong>'
            '<p>主策略 B 正式名单与复盘不受影响，待下次正常收盘运行后自动恢复跟踪。</p></div>'
            '</section>'
        )
    positions = positions or {}
    counts = Counter(row["status"] for row in rows)
    open_count = counts[RULE_STATUS_OPEN]
    not_yet_count = counts[RULE_STATUS_NOT_YET_ELIGIBLE]
    untriggered_count = counts[RULE_STATUS_UNTRIGGERED]
    waiting_count = not_yet_count + untriggered_count
    closed_count = counts[RULE_STATUS_CLOSED]
    win_count = sum(1 for row in rows if row.get("exit_reason") == "TARGET")
    stop_count = sum(1 for row in rows if row.get("exit_reason") == "STOP")
    ambiguous_count = counts[RULE_STATUS_AMBIGUOUS]
    other_issue_count = counts[PERFORMANCE_DATA_INCOMPLETE] + counts[STRATEGY_RULE_CONFIG_ERROR]
    issue_count = ambiguous_count + other_issue_count
    if open_count:
        head_badge = f'<span class="badge c-sim-open">模拟持有 {open_count} 只</span>'
    elif waiting_count:
        head_badge = f'<span class="badge neutral">待触发观察 {waiting_count} 只</span>'
    elif rows:
        head_badge = f'<span class="badge neutral">共 {len(rows)} 条记录</span>'
    else:
        head_badge = '<span class="badge neutral">暂无模拟信号</span>'
    summary = " · ".join(f"{label} {counts[status]}" for status, label in _STATUS.items() if counts[status])
    open_note = "已按触发价模拟买入" if open_count else "当前无模拟持仓"
    issue_note = (
        f"顺序不明 {ambiguous_count} · 缺数据/价位异常 {other_issue_count}"
        if issue_count
        else "无异常记录"
    )
    kpi_grid = (
        '<div class="c-sim-kpi-grid">'
        f'<article class="c-sim-kpi"><span>当前模拟持有</span><strong>{open_count}</strong>'
        f'<small>{open_note}</small></article>'
        f'<article class="c-sim-kpi"><span>待触发 / 待次日</span><strong>{waiting_count}</strong>'
        f'<small>待次一交易日 {not_yet_count} · 未触发 {untriggered_count}</small></article>'
        f'<article class="c-sim-kpi"><span>已结案</span><strong>{closed_count}</strong>'
        f'<small>模拟止盈 {win_count} · 模拟止损 {stop_count}</small></article>'
        f'<article class="c-sim-kpi"><span>待核验 / 异常</span><strong>{issue_count}</strong>'
        f'<small>{issue_note}</small></article>'
        '</div>'
    )
    cells = []
    for row in sorted(rows, key=lambda item: item["signal_date"], reverse=True):
        status_label, status_tone = _status_presentation(row)
        pnl_text, pnl_tone = _format_pnl(row)
        stock_label = f'{row["code"]} {row["name"]}'
        position_badge = _position_badge_html(positions.get(row.get("signal_id"), {}))
        cells.append(
            "<tr>"
            f'<td>{escape(str(row["signal_date"]))}</td>'
            f'<td>{escape(stock_label)}{position_badge}</td>'
            f'<td>{_rule_cell_html(row.get("setup"))}</td>'
            f'<td>{_format_price(row.get("trigger"))}</td>'
            f'<td>{_format_price(row.get("stop"))}</td>'
            f'<td>{_format_price(row.get("target"))}</td>'
            f'<td><span class="badge {status_tone}">{escape(status_label)}</span></td>'
            f'<td>{escape(str(row.get("entry_date") or "—"))}</td>'
            f'<td>{escape(str(row.get("exit_date") or "—"))}</td>'
            f'<td><span class="c-sim-pnl {pnl_tone}">{escape(pnl_text)}</span></td>'
            "</tr>"
        )
    if cells:
        columns = ["信号日", "股票", "C规则", "触发价", "止损价", "目标价", "状态", "模拟买入", "模拟卖出", "毛收益"]
        headings = "".join(f'<th scope="col">{column}</th>' for column in columns)
        detail = (
            f'<details class="research-data-details c-sim-detail"><summary>展开全部模拟明细（共 {len(cells)} 条）</summary>'
            '<div class="table-scroll" role="region" aria-label="C研究模拟明细" tabindex="0"><table>'
            f'<thead><tr>{headings}</tr></thead><tbody>{"".join(cells)}</tbody></table></div></details>'
        )
    else:
        detail = (
            '<div class="empty-state"><strong>暂无 C 模拟信号</strong>'
            '<p>当 C 研究出现命中股票时，将在收盘后冻结价位，并从次一交易日起自动按规则跟踪模拟持仓。</p></div>'
        )
    return (
        f'<section id="c-research-simulation">{style}'
        '<div class="section-head"><div>'
        '<p class="section-kicker">C SIMULATION · 副线规则模拟</p>'
        '<h2>C研究模拟</h2>'
        f'<p class="section-subtitle">截至 {safe_day} · 独立副线研究，与主策略 B 相互隔离；不限时规则模拟，不代表真实账户持仓。</p>'
        f'</div>{head_badge}</div>'
        f'{kpi_grid}'
        f'<p class="c-sim-status-line">截至 {safe_day} · {summary or "暂无 C 模拟信号"}（毛收益未扣费用及滑点）</p>'
        f'{_open_holdings_html(rows, positions)}'
        f'{_rules_details_html()}'
        f'{detail}</section>'
    )


def read_section(simulation: Mapping[str, Any]) -> str:
    raw = Path(simulation["section"]).read_bytes()
    if sha256(raw).hexdigest() != simulation["section_sha256"]:
        raise ValueError("C simulation section SHA mismatch")
    return raw.decode("utf-8")


def publish(simulation: Mapping[str, Any], state_root: Path, day: str, manifest_sha: str) -> None:
    from run_c_daily_watchlist import _git
    from cloud_runtime_state import validate_state_tree

    ledger = Path(simulation["ledger"])
    payload = _read(ledger, simulation["ledger_sha256"])
    if payload["date"] != day or payload["version"] != VERSION or payload["c_manifest_sha256"] != manifest_sha:
        raise ValueError("C simulation publication identity mismatch")
    validate_state_tree(state_root)
    if _git(state_root, "status", "--porcelain").strip():
        raise ValueError("C simulation requires a clean runtime-state checkout")
    relative = (STATE_PATH / f'{day.replace("-", "")}.json').as_posix()
    target = state_root / relative
    raw = ledger.read_bytes()
    if target.exists() and target.read_bytes() != raw:
        raise ValueError("C simulation immutable ledger conflict")
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        _git(state_root, "add", "--", relative)
        _git(state_root, "diff", "--cached", "--check")
        _git(state_root, "-c", "user.name=github-actions[bot]", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
             "commit", "-m", f"runtime: append C research simulation {day}")
        _git(state_root, "push", "origin", "HEAD:runtime-state", timeout=60)
    _git(state_root, "fetch", "origin", "runtime-state", timeout=60)
    if _git(state_root, "show", f"FETCH_HEAD:{relative}") != raw:
        raise ValueError("C simulation remote readback mismatch")
