"""Apply the daily report's B theoretical execution model to frozen C signals."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
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
            target = pressure if pressure > close * 1.03 else close + 2.5 * (close - stop)
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
    anchor = next((bar for bar in bars if bar["date"] == signal["date"]), None)
    comparable = anchor is not None and _price_identity(anchor) == signal["price_anchor_sha256"]
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
    section.write_bytes(render_section(day, rows).encode("utf-8"))
    return {"ledger": str(ledger), "ledger_sha256": sha256(ledger.read_bytes()).hexdigest(),
            "section": str(section), "section_sha256": sha256(section.read_bytes()).hexdigest()}


def render_section(day: str, rows: list[dict[str, Any]] | None = None) -> str:
    head = ('<section id="c-research-simulation"><div class="section-head"><div>'
            '<h2>C研究模拟</h2></div></div>')
    if rows is None:
        return head + '<p class="empty-state">本期 C 模拟数据暂不可用。</p></section>'
    counts = Counter(row["status"] for row in rows)
    summary = " · ".join(f"{label} {counts[status]}" for status, label in _STATUS.items() if counts[status])
    cells = []
    for row in sorted(rows, key=lambda item: item["signal_date"], reverse=True):
        status = {"TARGET": "模拟止盈", "STOP": "模拟止损"}.get(row["exit_reason"], _STATUS.get(row["status"], row["status"]))
        numbers = [f"{row[key]:.2f}" if row.get(key) is not None else "—" for key in ("trigger", "stop", "target")]
        result = row.get("realized_return_pct")
        mark = row.get("mark_return_pct")
        pnl = f"{result:+.2f}%" if result is not None else f"浮动 {mark:+.2f}%" if mark is not None else "—"
        reason = row.get("reason")
        if row["status"] in {PERFORMANCE_DATA_INCOMPLETE, STRATEGY_RULE_CONFIG_ERROR} and reason:
            status += f"（{reason}）"
        values = [row["signal_date"], f'{row["code"]} {row["name"]}', row["setup"], *numbers, status,
                  row["entry_date"] or "—", row["exit_date"] or "—", pnl]
        cells.append("<tr>" + "".join(f"<td>{escape(str(value))}</td>" for value in values) + "</tr>")
    detail = ""
    if cells:
        columns = ["信号日", "股票", "C规则", "触发价", "止损", "目标", "状态", "模拟买入", "模拟卖出", "毛收益"]
        headings = "".join(f'<th scope="col">{column}</th>' for column in columns)
        detail = ('<details class="research-data-details"><summary>展开模拟明细</summary>'
                  '<div class="table-wrap" role="region" aria-label="C研究模拟明细" tabindex="0" style="overflow-x:auto"><table>'
                  f'<thead><tr>{headings}</tr></thead><tbody>{"".join(cells)}</tbody></table></div></details>')
    return (head + f'<p>截至 {escape(day)} · {summary or "暂无 C 模拟信号"}</p>'
            '<p>复用 B 日报的理论规则模拟，以 C 信号的价位和日线计算。触发后按触发价模拟买入，'
            '次一交易日起可按止损或目标价卖出，无固定到期。同日两价均触及则留空收益。'
            '重复入选按信号日和 C 规则独立记录。毛收益未扣费用及滑点。</p>'
            + detail + '</section>')


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
