from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path

import pytest

import c_research_simulation as simulation
import run_c_daily_watchlist as runner
from c_daily_watchlist import write_report
from test_c_daily_watchlist import _init_c_state_repo
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
    rules = {"BALANCED_A": {"price_structure_match": match, "structure": {
        "rebound_high": 10.2, "support_floor": 9.7, "stage_prior_high": 11.5,
    }}, "CONSERVATIVE_B": {"price_structure_match": False}}
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
