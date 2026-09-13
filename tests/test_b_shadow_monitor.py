from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import b_shadow_monitor as shadow
import render_daily_close_html as renderer
import t_close_runner
from b_breakout_retest_v1_1 import STRATEGY_SPEC_SHA256, STRATEGY_VERSION
from data_paths import DataPaths
from track_perf import _signal_from_candidate, new_tracker
from trading_calendar import TradingCalendar
from watchlist_schema import load_watchlist


CALENDAR = TradingCalendar(holidays={date(2026, 9, 7)})


def _formal_candidate(code: str = "002394") -> dict[str, object]:
    return {
        "code": code,
        "name": "测试信号",
        "buy_type": "B 突破回踩",
        "score": 58,
        "price": 10.0,
        "trigger": 10.2,
        "stop": 9.5,
        "target": 12.0,
        "rr": 2.57,
        "sector": "测试行业",
        "setup": "B_BREAKOUT_RETEST",
        "strategy_version": STRATEGY_VERSION,
        "signal_id": f"{STRATEGY_VERSION}:2026-09-10:{code}:B_BREAKOUT_RETEST",
    }


def _write_watchlist(root: Path, list_date: str = "20260910") -> Path:
    data_root = root / "data"
    data_root.mkdir(parents=True, exist_ok=True)
    payload = {
        "date": f"{list_date[:4]}-{list_date[4:6]}-{list_date[6:]}",
        "mode": "close",
        "market_env": {"grade": "A"},
        "sectors": [],
        "candidates": [_formal_candidate()],
        "strategy_version": STRATEGY_VERSION,
    }
    path = data_root / f"watchlist_{list_date}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    load_watchlist(path)
    return path


def _index_bars(signal_date: str, *, future: bool = False) -> list[dict[str, float | str]]:
    final = date.fromisoformat(signal_date) + (timedelta(days=1) if future else timedelta())
    start = final - timedelta(days=60)
    return [
        {"date": (start + timedelta(days=index)).isoformat(), "open": 100.0 + index, "high": 100.0 + index + 1, "low": 99.0 + index, "close": 100.0 + index, "volume": 1000.0}
        for index in range(61)
    ]


def _shadow_record(
    signal_id: str = "B_BREAKOUT_RETEST_LEGACY_V1_1:2026-09-08:002394:B_BREAKOUT_RETEST",
    signal_date: str = "2026-09-08",
    *,
    capture_mode: str = shadow.CAPTURE_PROSPECTIVE,
    trend: str = shadow.TREND_UP,
    vol: str = shadow.VOL_NORMAL,
    reactivation: float = 0.8,
) -> dict[str, object]:
    return {
        "signal_id": signal_id,
        "signal_date": signal_date,
        "strategy_version": STRATEGY_VERSION,
        "code": "002394",
        "name": "测试信号",
        "formal_context": {"score": 58, "trigger": 10.0, "stop": 9.0, "target": 12.0, "rr": 2.0},
        "pre_outcome": {
            "capture_mode": capture_mode,
            "capture_status": shadow.CAPTURE_COMPLETE,
            "signal_date": signal_date,
            "strategy_version": STRATEGY_VERSION,
            "market_regime": {"trend_regime": trend, "vol_regime": vol},
            "reactivation": {"reactivation_vs_breakout_ratio": reactivation},
            "structural_context": {"score": 58},
            "captured_at_bjt": "2026-09-08T18:00:00+08:00",
            "source": {"capture_mode": capture_mode, "captured_at_bjt": "2026-09-08T18:00:00+08:00"},
        },
        "outcomes": shadow._empty_outcome(),
    }


def _obs(day: str, *, high: float, low: float, close: float = 10.0) -> dict[str, object]:
    return {"date": day, "open": close, "high": high, "low": low, "price": close}


def _evaluate(observations: list[dict[str, object]], as_of: str = "2026-09-24") -> dict[str, object]:
    signal = {"signal_date": "2026-09-08", "trigger": 10.0, "stop": 9.0, "target": 12.0}
    tracker_signal = {"observations": observations}
    return shadow.evaluate_shadow_outcome(signal, tracker_signal, as_of, calendar=CALENDAR)


def test_shadow_capture_does_not_change_canonical_candidate(tmp_path: Path):
    watchlist_path = _write_watchlist(tmp_path)
    before = watchlist_path.read_bytes()
    result = shadow.capture_t_close_signals(
        watchlist_path=watchlist_path,
        run_manifest_path=None,
        generation_input_manifest={
            "status": "READY_FOR_STRATEGY_EVALUATION",
            "signal_date": "2026-09-10",
            "input_fingerprint": "a" * 64,
            "index": {"bars": _index_bars("2026-09-10")},
            "stock_klines": [],
        },
        market_env={},
        input_package_sha256="b" * 64,
        store_root=tmp_path / "data" / "shadow_monitor",
    )
    assert watchlist_path.read_bytes() == before
    assert result["expected"] == 1
    assert result["incomplete"] == 1
    normalized = load_watchlist(watchlist_path)
    assert normalized["candidates"][0]["signal_id"]


def test_shadow_capture_failure_is_fail_soft_for_formal_runner(monkeypatch, tmp_path: Path):
    watchlist_path = _write_watchlist(tmp_path)
    run_manifest = tmp_path / "run_manifest.json"
    run_manifest.write_text("{}", encoding="utf-8")

    class FakeManifest:
        signal_date = "2026-09-10"

        def to_dict(self):
            return {"signal_date": self.signal_date, "status": "READY_FOR_STRATEGY_EVALUATION"}

    package = SimpleNamespace(
        generation_input_manifest=FakeManifest(),
        market_env={},
        provenance={},
        display_names={},
    )
    persisted = SimpleNamespace(
        status="READY",
        path=tmp_path / "input_package.json",
        file_sha256="a" * 64,
    )
    candidate = SimpleNamespace(
        status=t_close_runner.RUN_SUCCESS,
        output_path=watchlist_path,
        run_manifest_path=run_manifest,
        output_sha256="b" * 64,
        candidate_count=1,
        as_of_date="2026-09-10",
    )
    monkeypatch.setattr(t_close_runner, "acquire_live_generation_inputs", lambda *args, **kwargs: package)
    monkeypatch.setattr(t_close_runner, "persist_live_input_package", lambda *args, **kwargs: persisted)
    monkeypatch.setattr(t_close_runner.DevelopmentCandidateStore, "generate", lambda *args, **kwargs: candidate)
    monkeypatch.setattr(shadow, "capture_t_close_signals", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("shadow boom")))

    result = t_close_runner.run("2026-09-10", tmp_path / "data", tmp_path / "evidence")
    assert result["status"] == t_close_runner.T_CLOSE_SUCCESS_STATUS
    assert result["watchlist"]["path"] == str(watchlist_path)
    assert result["shadow_monitor"]["status"] == "SHADOW_CAPTURE_INCOMPLETE"


def test_pre_outcome_snapshot_is_immutable_and_same_value_is_idempotent():
    store = shadow.new_store()
    record = _shadow_record()
    assert shadow._upsert_record(store, record) == "ADDED"
    assert shadow._upsert_record(store, deepcopy(record)) == "IDEMPOTENT"
    original = deepcopy(store["signals"][record["signal_id"]]["pre_outcome"])
    changed = deepcopy(record)
    changed["pre_outcome"]["reactivation"]["reactivation_vs_breakout_ratio"] = 0.9
    with pytest.raises(shadow.ShadowMonitorError, match="SHADOW_PRE_OUTCOME_IDENTITY_CONFLICT"):
        shadow._upsert_record(store, changed)
    assert store["signals"][record["signal_id"]]["pre_outcome"] == original


def test_duplicate_timestamp_change_remains_idempotent():
    store = shadow.new_store()
    record = _shadow_record()
    shadow._upsert_record(store, record)
    duplicate = deepcopy(record)
    duplicate["pre_outcome"]["captured_at_bjt"] = "2026-09-08T18:01:00+08:00"
    duplicate["pre_outcome"]["source"]["captured_at_bjt"] = "2026-09-08T18:01:00+08:00"
    assert shadow._upsert_record(store, duplicate) == "IDEMPOTENT"


def test_future_bar_is_rejected_before_pre_outcome_capture():
    with pytest.raises(shadow.ShadowMonitorError, match="SHADOW_FUTURE_BAR_IN_PRE_OUTCOME"):
        shadow._market_snapshot({"bars": _index_bars("2026-09-10", future=True)}, "2026-09-10")


def test_fast_stop_on_first_sellable_session_is_true():
    result = _evaluate([
        _obs("2026-09-09", high=10.5, low=9.0),
        _obs("2026-09-10", high=10.2, low=8.9),
    ])
    assert result["status"] == shadow.OUTCOME_STOP
    assert result["stop_session_index"] == 1
    assert result["fast_stop"] is True


def test_fast_stop_on_second_sellable_session_is_true():
    result = _evaluate([
        _obs("2026-09-09", high=10.5, low=9.0),
        _obs("2026-09-10", high=10.2, low=9.2),
        _obs("2026-09-11", high=10.2, low=8.9),
    ])
    assert result["status"] == shadow.OUTCOME_STOP
    assert result["stop_session_index"] == 2
    assert result["fast_stop"] is True


def test_stop_on_third_sellable_session_is_not_fast_stop():
    result = _evaluate([
            _obs("2026-09-09", high=10.5, low=9.0),
            _obs("2026-09-10", high=10.2, low=9.2),
            _obs("2026-09-11", high=10.2, low=9.2),
            _obs("2026-09-14", high=10.2, low=8.9),
        ])
    assert result["status"] == shadow.OUTCOME_STOP
    assert result["stop_session_index"] == 3
    assert result["fast_stop"] is False


def test_target_does_not_receive_fast_stop_label():
    result = _evaluate([
        _obs("2026-09-09", high=10.5, low=9.0),
        _obs("2026-09-10", high=12.0, low=9.5),
    ])
    assert result["status"] == shadow.OUTCOME_TARGET
    assert result["fast_stop"] is False


def test_entry_day_stop_touch_is_not_an_exit():
    result = _evaluate([_obs("2026-09-09", high=10.5, low=9.0)])
    assert result["status"] == shadow.OUTCOME_OPEN
    assert result["entry_day_stop_touched"] is True
    assert result["exit_date"] is None


def test_same_bar_stop_and_target_is_ambiguous():
    result = _evaluate([
        _obs("2026-09-09", high=10.5, low=9.0),
        _obs("2026-09-10", high=12.0, low=8.9),
    ])
    assert result["status"] == shadow.OUTCOME_AMBIGUOUS
    assert result["realized_return_pct"] is None


def test_no_t10_forced_exit_keeps_trade_open():
    observations = [_obs("2026-09-09", high=10.5, low=9.8)]
    for day in ("2026-09-10", "2026-09-11", "2026-09-12", "2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18", "2026-09-21", "2026-09-22"):
        observations.append(_obs(day, high=10.5, low=9.8))
    result = _evaluate(observations, as_of="2026-09-22")
    assert result["status"] == shadow.OUTCOME_OPEN
    assert result["exit_date"] is None


def test_stop_recovery_records_plus_three_plus_five_plus_ten():
    observations = [
        _obs("2026-09-09", high=10.5, low=9.0),
        _obs("2026-09-10", high=10.2, low=8.9),
    ]
    recovery_days = ("2026-09-11", "2026-09-12", "2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18", "2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24")
    observations.extend(_obs(day, high=12.5, low=9.5) for day in recovery_days)
    result = _evaluate(observations, as_of="2026-09-24")
    assert result["status"] == shadow.OUTCOME_STOP
    assert result["post_stop_max_high_3"] == 12.5
    assert result["recovered_to_entry_3"] is True
    assert result["reached_original_target_5"] is True
    assert result["reached_original_target_10"] is True


def test_recovery_does_not_modify_original_stop_outcome():
    observations = [
        _obs("2026-09-09", high=10.5, low=9.0),
        _obs("2026-09-10", high=10.2, low=8.9),
            _obs("2026-09-11", high=12.5, low=9.5),
            _obs("2026-09-12", high=12.5, low=9.5),
            _obs("2026-09-14", high=12.5, low=9.5),
            _obs("2026-09-15", high=12.5, low=9.5),
        ]
    result = _evaluate(observations, as_of="2026-09-15")
    assert result["status"] == shadow.OUTCOME_STOP
    assert result["exit_price"] == 9.0
    assert result["realized_r"] == pytest.approx(-1.0)
    assert result["recovery_status_3"] == shadow.CAPTURE_COMPLETE


def test_recovery_is_pending_until_horizon_is_observed():
    result = _evaluate([
        _obs("2026-09-09", high=10.5, low=9.0),
        _obs("2026-09-10", high=10.2, low=8.9),
    ], as_of="2026-09-10")
    assert result["status"] == shadow.OUTCOME_STOP
    assert result["recovery_status_3"] == "PENDING"


def test_prospective_and_retrospective_labels_are_separate_in_summary():
    store = shadow.new_store()
    prospective = _shadow_record()
    retrospective = _shadow_record(signal_id="retrospective", capture_mode=shadow.CAPTURE_RETROSPECTIVE)
    store["signals"] = {prospective["signal_id"]: prospective, retrospective["signal_id"]: retrospective}
    summary = shadow.build_shadow_summary(store, "2026-09-24", current_signal_ids=set())
    assert summary["overall"]["signals"] == 1


def test_regime_statistics_exclude_future_signal():
    store = shadow.new_store()
    current = _shadow_record(signal_id="current", signal_date="2026-09-08")
    future = _shadow_record(signal_id="future", signal_date="2026-09-25", trend=shadow.TREND_DOWN)
    store["signals"] = {"current": current, "future": future}
    summary = shadow.build_shadow_summary(store, "2026-09-24", current_signal_ids=set())
    assert summary["overall"]["signals"] == 1
    assert all(row["environment"] != shadow.TREND_DOWN for row in summary["trend_rows"])


def test_store_update_uses_tracker_ohlc_without_mutating_pre_outcome():
    store = shadow.new_store()
    record = _shadow_record()
    store["signals"][record["signal_id"]] = deepcopy(record)
    before = deepcopy(store["signals"][record["signal_id"]]["pre_outcome"])
    tracker = {"signals": {record["signal_id"]: {"observations": [
        _obs("2026-09-09", high=10.5, low=9.0),
        _obs("2026-09-10", high=12.0, low=9.5),
    ]}}}
    result = shadow.update_store_from_tracker(store, tracker, "2026-09-10", calendar=CALENDAR)
    assert result["changed"] == 1
    assert store["signals"][record["signal_id"]]["outcomes"]["status"] == shadow.OUTCOME_TARGET
    assert store["signals"][record["signal_id"]]["pre_outcome"] == before


def test_html_empty_state_and_no_decision_language(tmp_path: Path):
    watchlist_path = _write_watchlist(tmp_path, "20260910")
    watchlist = load_watchlist(watchlist_path)
    tracker = new_tracker()
    signal = _signal_from_candidate(watchlist, watchlist["candidates"][0], CALENDAR)
    tracker["signals"][signal["signal_id"]] = signal
    (tmp_path / "data" / "perf_tracker.json").write_text(json.dumps(tracker), encoding="utf-8")
    model = renderer.build_report_model("20260910", paths=DataPaths(tmp_path / "data"), calendar=CALENDAR)
    html = renderer.render_html(model)
    section = html.split('<section id="shadow-monitor">', 1)[1].split('<section id="daily-review">', 1)[0]
    assert "暂无 prospective shadow 样本" in section
    assert "BUY" not in section and "AVOID" not in section


def test_current_b_spec_sha_is_unchanged():
    assert STRATEGY_VERSION == "B_BREAKOUT_RETEST_LEGACY_V1_1"
    assert STRATEGY_SPEC_SHA256 == "f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd"


def test_shadow_store_reference_is_reference_only():
    reference = shadow.new_store()["reference_only"]
    assert reference["label"] == "REFERENCE_ONLY"
    assert reference["historical_fast_stop_rate"] == 46.221786
    assert reference["used_for_thresholds"] is False


def test_capture_context_contains_no_candidate_filter_or_decision_field():
    record = _shadow_record()
    encoded = json.dumps(record["pre_outcome"], ensure_ascii=False).upper()
    assert "BUY" not in encoded and "AVOID" not in encoded
    assert "qualification" not in encoded.lower()
