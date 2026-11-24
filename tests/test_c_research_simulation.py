from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
from statistics import mean

import pytest

from c_b_input_adapter import _price_only_observation
import c_research_simulation as simulation
import run_c_daily_watchlist as runner
from c_daily_watchlist import write_report
from test_c_daily_watchlist import _init_c_state_repo
from test_c_pre_outcome_design import _synthetic_entry_bars
from track_perf import RULE_STATUS_AMBIGUOUS, RULE_STATUS_CLOSED, RULE_STATUS_OPEN
from trading_calendar import TradingCalendar


BJT = timezone(timedelta(hours=8))
T = "2026-11-04"
T1 = "2026-11-05"
T2 = "2026-11-06"
CODE = "600000"


def _bar(day, low, high, opening=10.0, close=10.0):
    return {"date": day, "open": opening, "high": high, "low": low, "close": close, "volume": 100.0}


def _inputs(tmp_path, day, bars, *, match):
    directory = tmp_path / day
    directory.mkdir()
    package = directory / "package.json"
    package.write_text(json.dumps({"generation_input_manifest": {"stock_klines": [{
        "symbol": CODE, "adjustment_mode": "PROVIDER_QFQ_SNAPSHOT", "bars": bars,
        "normalized_data_sha256": "a" * 64,
    }]}}), encoding="utf-8")
    package_sha = sha256(package.read_bytes()).hexdigest()
    rules = {"BALANCED_A": {"price_structure_match": match, "price_structure_observation": {"structure": {
        "rebound_high": 10.2, "support_floor": 9.7, "stage_prior_high": 11.5,
    }}}, "CONSERVATIVE_B": {"price_structure_match": False}}
    record = directory / "observation.json"
    record.write_text(json.dumps({
        "schema_version": "C_B_FROZEN_INPUT_READER_V1",
        "status": "PRICE_OBSERVATION_VOLUME_UNVERIFIED",
        "source": {"target_date": day, "b_package_actual_sha256": package_sha,
                   "handoff": {"mode": "SAME_RUNNER_READ_ONLY"}, "b_acquired_at_bjt": day + "T17:20:00+08:00",
                   "c_read_at_bjt": day + "T17:30:00+08:00"},
        "observations": [{"symbol": CODE, "name": "模拟测试", "rules": rules}],
    }), encoding="utf-8")
    report = write_report(record, directory / "rendered")
    result = {"as_of_date": day, "input_package": {"path": str(package), "file_sha256": package_sha}}
    return result, {"record_sha256": sha256(record.read_bytes()).hexdigest()}, record, report


def _capture(inputs, state):
    result, consumed, record, report = inputs
    return simulation.capture(result, consumed, record, state, report,
                              now=datetime.fromisoformat(result["as_of_date"] + "T18:00:00+08:00"))


def test_c_simulation_daily_report_and_append_only_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(simulation, "default_calendar", lambda: TradingCalendar([], session_close_time=time(15)))
    state, remote = tmp_path / "runtime-state", tmp_path / "remote.git"
    _init_c_state_repo(state, remote)
    (state / "data").mkdir()
    original = _bar(T, 9.9, 10.1)
    def publish(files, day, report):
        simulation.publish(files, state, day, report["manifest_sha256"])

    t = _inputs(tmp_path, T, [original], match=True)
    t_files = _capture(t, state)
    publish(t_files, T, t[-1])
    publish(t_files, T, t[-1])
    original_ledger = (state / simulation.STATE_PATH / "20261104.json").read_bytes()
    ledger = json.loads(original_ledger)
    assert ledger["settled"] == []
    assert ledger["signals"][0]["trigger"] == 10.2
    assert "待次一交易日" in simulation.read_section(t_files)
    with pytest.raises(ValueError, match="already published"):
        _capture(t, state)
    with pytest.raises(ValueError, match="genuine current-day"):
        simulation.capture(t[0], t[1], t[2], state, t[3], now=datetime(2026, 11, 5, 18, tzinfo=BJT))

    # Both edges are touched on entry day. B's model must wait until the next session.
    entry = _bar(T1, 9.0, 12.0)
    t1 = _inputs(tmp_path, T1, [original, entry], match=False)
    t1_files = _capture(t1, state)
    assert "模拟持有 1" in simulation.read_section(t1_files)
    assert json.loads(Path(t1_files["ledger"]).read_bytes())["settled"] == []
    publish(t1_files, T1, t1[-1])

    t2 = _inputs(tmp_path, T2, [original, entry, _bar(T2, 9.9, 12.0)], match=False)
    t2_files = _capture(t2, state)
    closed, = json.loads(Path(t2_files["ledger"]).read_bytes())["settled"]
    assert (closed["status"], closed["entry_date"], closed["entry_price"]) == (RULE_STATUS_CLOSED, T1, 10.2)
    assert (closed["exit_date"], closed["exit_reason"], closed["exit_price"]) == (T2, "TARGET", 11.5)
    assert "open" not in closed and "ambiguous_high" not in closed
    formal = tmp_path / "formal.html"
    b_html = b'<html><head></head><body><nav></nav><main><section id="research-data"></section></main></body></html>'
    formal.write_bytes(b_html)
    result = {"as_of_date": T2, "daily_close_bundle": {"dated_html": str(formal)}}
    c_result = {"status": "C_DAILY_RESEARCH_REPORT_READY", "report": t2[-1], "simulation": t2_files}
    monkeypatch.setenv("ENABLE_C_RESEARCH_SIMULATION", "true")
    composite = runner.build_composite_delivery(result, c_result, delivery_root=tmp_path / "delivery")
    assert composite["simulation_rendered"] is True
    html = Path(composite["delivery_report_path"]).read_text(encoding="utf-8")
    assert '<h2>C研究模拟</h2>' in html and 'href="#c-research-simulation"' in html
    assert "模拟止盈" in html and "+12.75%" in html and formal.read_bytes() == b_html
    composite["c_result"] = c_result
    b_result, delivery_result, prepared_result = (tmp_path / name for name in ("b.json", "delivery.json", "prepared.json"))
    for path, value in ((b_result, result), (delivery_result, {}), (prepared_result, composite)):
        path.write_text(json.dumps(value), encoding="utf-8")
    monkeypatch.setattr(runner, "b_is_complete", lambda *args: True)
    outcome = runner.post_b(b_result=b_result, delivery_result=delivery_result, prepared_result=prepared_result,
                            data_root=tmp_path / "data", state_root=state)
    assert outcome["status"] == "C_DAILY_REPORT_PUBLISHED"
    assert outcome["simulation_status"] == "C_SIMULATION_PUBLISHED"
    assert (state / simulation.STATE_PATH / "20261106.json").read_bytes() == Path(t2_files["ledger"]).read_bytes()
    assert (state / simulation.STATE_PATH / "20261104.json").read_bytes() == original_ledger


def test_c_simulation_same_bar_ambiguity_and_missing_or_rebased_prices():
    calendar = TradingCalendar([])
    anchor = _bar(T, 9.9, 10.1)
    signal = {"signal_id": "c", "date": T, "code": CODE, "setup": "BALANCED_A",
              "trigger": 10.2, "stop": 9.5, "target": 11.5, "price_anchor_sha256": simulation._price_identity(anchor)}
    entry = _bar(T1, 9.6, 10.5)
    both = _bar(T2, 9.0, 12.0)

    def evaluate(bars, day):
        return simulation._simulate(signal, {CODE: {"bars": bars}}, day, calendar)
    assert evaluate([anchor, entry], T1)["status"] == RULE_STATUS_OPEN
    ambiguous = evaluate([anchor, entry, both], T2)
    assert ambiguous["status"] == RULE_STATUS_AMBIGUOUS and ambiguous["realized_return_pct"] is None
    for bars in ([anchor, both], [_bar(T, 9.7, 10.1), entry, both]):
        missing = evaluate(bars, T2)
        assert missing["status"] == "PERFORMANCE_DATA_INCOMPLETE"
        assert missing["realized_return_pct"] is None


def test_c_simulation_consumes_real_price_only_observation_schema(tmp_path, monkeypatch):
    monkeypatch.setattr(simulation, "default_calendar", lambda: TradingCalendar([], session_close_time=time(15)))
    bars = _synthetic_entry_bars()
    day = bars[-1]["date"]
    balanced = _price_only_observation(CODE, day, bars, "BALANCED_A")
    conservative = _price_only_observation(CODE, day, bars, "CONSERVATIVE_B")
    assert balanced["price_structure_match"] is True
    assert "structure" not in balanced
    assert "structure" in balanced["price_structure_observation"]

    directory = tmp_path / day
    directory.mkdir()
    package = directory / "package.json"
    package.write_text(json.dumps({"generation_input_manifest": {"stock_klines": [{
        "symbol": CODE, "adjustment_mode": "PROVIDER_QFQ_SNAPSHOT", "bars": bars,
        "normalized_data_sha256": "a" * 64,
    }]}}), encoding="utf-8")
    package_sha = sha256(package.read_bytes()).hexdigest()
    record = directory / "observation.json"
    record.write_text(json.dumps({
        "schema_version": "C_B_FROZEN_INPUT_READER_V1",
        "status": "PRICE_OBSERVATION_VOLUME_UNVERIFIED",
        "source": {
            "target_date": day,
            "b_package_actual_sha256": package_sha,
            "handoff": {"mode": "SAME_RUNNER_READ_ONLY"},
            "b_acquired_at_bjt": f"{day}T17:20:00+08:00",
            "c_read_at_bjt": f"{day}T17:30:00+08:00",
        },
        "observations": [{
            "symbol": CODE,
            "name": "浦发银行",
            "rules": {"BALANCED_A": balanced, "CONSERVATIVE_B": conservative},
        }],
    }), encoding="utf-8")
    report = write_report(record, directory / "rendered")
    result = {"as_of_date": day, "input_package": {"path": str(package), "file_sha256": package_sha}}
    consumed = {"record_sha256": sha256(record.read_bytes()).hexdigest()}
    state = tmp_path / "runtime-state"
    state.mkdir()

    files = simulation.capture(
        result,
        consumed,
        record,
        state,
        report,
        now=datetime.fromisoformat(f"{day}T18:00:00+08:00"),
    )
    ledger = json.loads(Path(files["ledger"]).read_bytes())
    assert len(ledger["signals"]) == 1
    signal = ledger["signals"][0]
    structure = balanced["price_structure_observation"]["structure"]
    close = bars[-1]["close"]
    ma5 = mean(bar["close"] for bar in bars[-5:])
    expected_trigger = round(max(structure["rebound_high"], ma5), 2)
    expected_stop = round(structure["support_floor"] * 0.98, 2)
    expected_target = (
        structure["stage_prior_high"]
        if structure["stage_prior_high"] > close * 1.03
        else close + 2.5 * (close - expected_stop)
    )
    assert (signal["code"], signal["setup"]) == (CODE, "BALANCED_A")
    assert signal["trigger"] == expected_trigger
    assert signal["stop"] == expected_stop
    assert signal["target"] == expected_target

    section = simulation.read_section(files)
    assert '<h2>C研究模拟</h2>' in section
    assert "待次一交易日" in section
    assert f"{CODE} 浦发银行" in section
    assert "BALANCED_A" in section


@pytest.mark.parametrize("rule_payload", [
    {"price_structure_match": True, "structure": {"rebound_high": 10.2, "support_floor": 9.7, "stage_prior_high": 11.5}},
    {"price_structure_match": True, "price_structure_observation": {}},
    {"price_structure_match": True, "price_structure_observation": {"structure": None}},
    {"price_structure_match": True, "price_structure_observation": {"structure": {"support_floor": 9.7, "stage_prior_high": 11.5}}},
    {"price_structure_match": True, "price_structure_observation": {"structure": {"rebound_high": 10.2, "support_floor": None, "stage_prior_high": 11.5}}},
    {"price_structure_match": True, "price_structure_observation": {"structure": {"rebound_high": 10.2, "support_floor": 9.7, "stage_prior_high": True}}},
    {"price_structure_match": True, "price_structure_observation": {"structure": {"rebound_high": float("nan"), "support_floor": 9.7, "stage_prior_high": 11.5}}},
])
def test_c_simulation_signals_rejects_missing_structure_or_numeric_fields(rule_payload):
    watchlist = {
        "signal_date": T,
        "rows": [{
            "symbol": CODE,
            "name": "模拟测试",
            "matched_rules": ["BALANCED_A"],
            "rules": {"BALANCED_A": rule_payload, "CONSERVATIVE_B": {"price_structure_match": False}},
        }],
    }
    histories = {CODE: {"bars": [_bar(T, 9.9, 10.1)]}}
    with pytest.raises(ValueError, match=r"price_structure_observation\.structure|numeric structure\."):
        simulation._signals(watchlist, histories)


def test_c_simulation_render_section_plain_chinese_holdings_and_states():
    unavailable = simulation.render_section(T2, None)
    assert 'id="c-research-simulation"' in unavailable
    assert '<h2>C研究模拟</h2>' in unavailable
    assert "本期暂不可用" in unavailable
    assert "主策略 B 正式名单与复盘不受影响" in unavailable

    empty = simulation.render_section(T2, [])
    assert "暂无模拟信号" in empty
    assert "一分钟看懂 C 模拟规则" in empty
    assert "当前模拟持仓" not in empty

    rows = [
        {
            "signal_date": T,
            "code": "600000",
            "name": "浦发银行",
            "setup": "BALANCED_A",
            "trigger": 10.2,
            "stop": 9.5,
            "target": 11.5,
            "status": RULE_STATUS_OPEN,
            "entry_date": T1,
            "entry_price": 10.2,
            "exit_date": None,
            "exit_reason": None,
            "realized_return_pct": None,
            "mark_return_pct": 3.92,
        },
        {
            "signal_date": "2026-11-03",
            "code": "600019",
            "name": "宝钢股份",
            "setup": "CONSERVATIVE_B",
            "trigger": 7.1,
            "stop": 6.6,
            "target": 8.0,
            "status": RULE_STATUS_CLOSED,
            "entry_date": T,
            "entry_price": 7.1,
            "exit_date": T2,
            "exit_reason": "TARGET",
            "realized_return_pct": 12.68,
            "mark_return_pct": None,
        },
    ]
    rendered = simulation.render_section(T2, rows)
    assert "<style data-c-simulation-inline-style>" in rendered
    assert "当前模拟持仓 · 1 只" in rendered
    assert "600000 浦发银行" in rendered
    assert "BALANCED_A · 平衡版" in rendered
    assert "浮动 +3.92%" in rendered
    assert "模拟止盈 1 · 模拟止损 0" in rendered
    assert "一分钟看懂 C 模拟规则" in rendered
    assert "展开全部模拟明细（共 2 条）" in rendered
    assert "模拟持有 1" in rendered
    assert "+12.68%" in rendered
