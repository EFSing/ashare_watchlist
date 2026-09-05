from __future__ import annotations

from datetime import date, timedelta
import hashlib
import json

import pytest

import b_prospective_observation as observation
from trading_calendar import TradingCalendar


CALENDAR = TradingCalendar(holidays=set())
SIGNAL_DATE = "2026-09-02"
GENERATION_SHA = observation.PROTOCOL_COMMIT_SHA


def _bars(length: int, *, signal_date: str) -> list[dict[str, object]]:
    start = date(2026, 5, 6)
    bars: list[dict[str, object]] = []
    for index in range(length):
        day = start + timedelta(days=index)
        close = 10.0
        volume = 100.0
        if index == 118:
            close, volume = 11.0, 300.0
        elif index > 118:
            close = 10.3
        if index == length - 1:
            volume = 150.0
        bars.append({
            "date": day.isoformat(),
            "open": close,
            "high": close + 0.1,
            "low": close - 0.1,
            "close": close,
            "volume": volume,
        })
    assert bars[-1]["date"] == signal_date
    return bars


def _candidate(signal_date: str = SIGNAL_DATE) -> dict[str, object]:
    return {
        "code": "600000",
        "name": "测试股份",
        "sector": "银行",
        "buy_type": "B 突破回踩",
        "score": 66,
        "price": 10.3,
        "chg": 1.0,
        "trigger": 10.3,
        "support": 10.0,
        "stop": 9.8,
        "target": 12.8,
        "rr": 10.0,
        "stop_dist": 9.26,
        "vol_ratio": 1.5,
        "turnover": 2.0,
        "float_mv": 1000.0,
        "target_type": "PRESSURE",
        "risk": 0.0926,
        "setup": "B 突破回踩",
        "strategy_version": observation.STRATEGY_VERSION,
    }


def _canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _source(tmp_path, *, signal_date: str = SIGNAL_DATE, length: int = 120):
    candidate = _candidate(signal_date)
    watchlist = {
        "date": signal_date,
        "mode": "close",
        "market_env": {"level": "B", "regime": "fixture"},
        "sectors": [{"name": "银行", "rank": 1, "chg": 1.0}],
        "candidates": [candidate],
        "strategy_version": observation.STRATEGY_VERSION,
    }
    from watchlist_schema import validate_watchlist

    watchlist_bytes = _canonical(validate_watchlist(watchlist))
    watchlist_path = tmp_path / f"watchlist_{signal_date.replace('-', '')}.json"
    watchlist_path.write_bytes(watchlist_bytes)
    input_fingerprint = "b" * 64
    generation_fingerprint = "a" * 64
    entry_date = observation.next_execution_date(signal_date, CALENDAR)
    input_manifest = {
        "status": "READY_FOR_STRATEGY_EVALUATION",
        "signal_date": signal_date,
        "earliest_execution_date": entry_date,
        "run_context": {"mode": "close", "historical": False},
        "stock_klines": [{"symbol": "600000", "bars": _bars(length, signal_date=signal_date)}],
    }
    run_manifest = {
        "schema_version": "DEVELOPMENT_CANDIDATE_RUN_V1",
        "status": "SUCCESS",
        "strategy_version": observation.STRATEGY_VERSION,
        "strategy_spec_sha256": observation.STRATEGY_SPEC_SHA256,
        "signal_date": signal_date,
        "as_of_date": signal_date,
        "earliest_execution_date": entry_date,
        "input_fingerprint": input_fingerprint,
        "generation_fingerprint": generation_fingerprint,
        "input_manifest": input_manifest,
        "output": {
            "logical_identity": f"watchlist_{signal_date.replace('-', '')}.json",
            "file_sha256": hashlib.sha256(watchlist_bytes).hexdigest(),
        },
    }
    run_path = tmp_path / f"run_{signal_date.replace('-', '')}.json"
    run_path.write_bytes(_canonical(run_manifest))
    return watchlist_path, run_path, candidate


def _available_outcomes(signal_date: str, observed_date: str = "2026-09-16"):
    values = {}
    for horizon in observation.HORIZONS:
        target_date = observation._next_horizon_date(signal_date, horizon, CALENDAR)
        values[f"{horizon}D"] = {
            "status": "AVAILABLE",
            "target_date": target_date,
            "target_close": 11.0 + horizon / 10,
            "return_pct": 2.0 + horizon / 10,
            "mfe_pct": 4.0 + horizon / 10,
            "mae_pct": -1.0,
            "corporate_actions": [],
        }
    return values


def _unavailable_outcomes(signal_date: str):
    return {
        f"{horizon}D": {
            "status": "NO_T_PLUS_1_OPEN",
            "target_date": observation._next_horizon_date(signal_date, horizon, CALENDAR),
            "target_close": None,
            "return_pct": None,
            "mfe_pct": None,
            "mae_pct": None,
        }
        for horizon in observation.HORIZONS
    }


def test_signal_bytes_immutable_and_repeat_is_retained_but_deduplicated(tmp_path):
    first_dir, second_dir = tmp_path / "first", tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first_watchlist, first_run, _ = _source(first_dir, signal_date="2026-09-02", length=120)
    second_watchlist, second_run, _ = _source(second_dir, signal_date="2026-09-03", length=121)
    store = observation.AppendOnlyObservationStore(tmp_path / "store")

    first = store.record_watchlist(first_watchlist, first_run, generation_commit_sha=GENERATION_SHA, calendar=CALENDAR)
    assert first["episode_independent_count"] == 1
    before = [item for item in store._events() if item["record_type"] == "SIGNAL"][0]
    store.append_outcome(
        before["signal_id"],
        observed_date="2026-09-16",
        reference_open=10.9,
        execution_classification=observation.EXECUTABLE_REFERENCE_OPEN,
        outcomes=_available_outcomes("2026-09-02"),
        corporate_action_treatment={"mode": "ADJUSTED_OUTCOME_ONLY_EX_POST", "events": []},
        outcome_source_identity={"source": "fixture", "sha256": "c" * 64},
        calendar=CALENDAR,
    )
    second = store.record_watchlist(second_watchlist, second_run, generation_commit_sha=GENERATION_SHA, calendar=CALENDAR)
    assert second["episode_independent_count"] == 0
    after = [item for item in store._events() if item["record_type"] == "SIGNAL"][0]
    assert after == before
    assert len([item for item in store._events() if item["record_type"] == "SIGNAL"]) == 2
    summary = store.summary()
    assert summary["raw_signal_level_count"] == 2
    assert summary["episode_deduplicated_count"] == 1
    assert summary["independent_episode_count"] == 1
    assert summary["primary_10d_episode_metrics"]["N"] == 1


def test_generation_before_protocol_is_rejected_without_appending(tmp_path, monkeypatch):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    watchlist, run, _ = _source(source_dir)
    monkeypatch.setattr(observation, "_git_is_ancestor", lambda *_: False)
    store = observation.AppendOnlyObservationStore(tmp_path / "store")
    with pytest.raises(observation.ObservationError) as caught:
        store.record_watchlist(watchlist, run, generation_commit_sha=GENERATION_SHA, calendar=CALENDAR)
    assert caught.value.status == "OBSERVATION_BACKFILL_FORBIDDEN"
    assert not store.events_path.exists()


def test_backfill_is_rejected_after_calendar_stream_has_advanced(tmp_path):
    first_dir, second_dir = tmp_path / "first", tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first_watchlist, first_run, _ = _source(first_dir, signal_date="2026-09-02", length=120)
    second_watchlist, second_run, _ = _source(second_dir, signal_date="2026-09-03", length=121)
    store = observation.AppendOnlyObservationStore(tmp_path / "store")
    store.record_watchlist(second_watchlist, second_run, generation_commit_sha=GENERATION_SHA, calendar=CALENDAR)
    with pytest.raises(observation.ObservationError) as caught:
        store.record_watchlist(first_watchlist, first_run, generation_commit_sha=GENERATION_SHA, calendar=CALENDAR)
    assert caught.value.status == "OBSERVATION_BACKFILL_FORBIDDEN"


def test_failed_execution_is_explicit_and_not_counted_as_executable(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    watchlist, run, _ = _source(source_dir)
    store = observation.AppendOnlyObservationStore(tmp_path / "store")
    store.record_watchlist(watchlist, run, generation_commit_sha=GENERATION_SHA, calendar=CALENDAR)
    signal = [item for item in store._events() if item["record_type"] == "SIGNAL"][0]
    store.append_outcome(
        signal["signal_id"],
        observed_date="2026-09-16",
        reference_open=None,
        execution_classification=observation.MISSING_OPEN,
        outcomes=_unavailable_outcomes(SIGNAL_DATE),
        corporate_action_treatment={"mode": "ADJUSTED_OUTCOME_ONLY_EX_POST", "events": []},
        outcome_source_identity={"source": "fixture", "sha256": "d" * 64},
        calendar=CALENDAR,
    )
    summary = store.summary()
    assert summary["execution"]["total_signals"] == 1
    assert summary["execution"]["executable_reference_count"] == 0
    assert summary["execution"]["non_executable_count"] == 1
    assert summary["execution"]["execution_coverage_rate"] == 0.0
    assert summary["primary_10d_episode_metrics"]["N"] == 0


def test_outcome_target_must_follow_xshg_t_plus_one_calendar(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    watchlist, run, _ = _source(source_dir)
    store = observation.AppendOnlyObservationStore(tmp_path / "store")
    store.record_watchlist(watchlist, run, generation_commit_sha=GENERATION_SHA, calendar=CALENDAR)
    signal = [item for item in store._events() if item["record_type"] == "SIGNAL"][0]
    outcomes = _available_outcomes(SIGNAL_DATE)
    outcomes["1D"] = dict(outcomes["1D"], target_date="2026-09-04")
    with pytest.raises(observation.ObservationError) as caught:
        store.append_outcome(
            signal["signal_id"],
            observed_date="2026-09-16",
            reference_open=10.9,
            execution_classification=observation.EXECUTABLE_REFERENCE_OPEN,
            outcomes=outcomes,
            corporate_action_treatment={"mode": "ADJUSTED_OUTCOME_ONLY_EX_POST", "events": []},
            outcome_source_identity={"source": "fixture", "sha256": "e" * 64},
            calendar=CALENDAR,
        )
    assert caught.value.status == "OBSERVATION_T_PLUS_ONE_MISMATCH"


def test_outcome_update_does_not_add_outcome_fields_to_signal_bytes(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    watchlist, run, _ = _source(source_dir)
    store = observation.AppendOnlyObservationStore(tmp_path / "store")
    store.record_watchlist(watchlist, run, generation_commit_sha=GENERATION_SHA, calendar=CALENDAR)
    signal_before = [item for item in store._events() if item["record_type"] == "SIGNAL"][0]
    store.append_outcome(
        signal_before["signal_id"],
        observed_date="2026-09-16",
        reference_open=10.9,
        execution_classification=observation.LIMIT_STATE_EXECUTION_UNCERTAIN,
        outcomes=_available_outcomes(SIGNAL_DATE),
        corporate_action_treatment={"mode": "ADJUSTED_OUTCOME_ONLY_EX_POST", "events": []},
        outcome_source_identity={"source": "fixture", "sha256": "f" * 64},
        calendar=CALENDAR,
    )
    signal_after = [item for item in store._events() if item["record_type"] == "SIGNAL"][0]
    assert signal_after == signal_before
    assert "return_pct" not in signal_after
    assert signal_after["outcome_maturity_status"] == "NOT_MATURED"
