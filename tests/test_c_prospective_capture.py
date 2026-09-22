from __future__ import annotations

import ast
from datetime import date, datetime, time, timedelta, timezone
import json
from pathlib import Path

from trading_calendar import TradingCalendar

from c_prospective_capture import (
    C_ALREADY_CAPTURED,
    C_CAPTURED,
    C_CAPTURE_FAILED,
    C_INPUT_CONFLICT,
    C_NOT_PROSPECTIVE_BACKFILL,
    C_PARTIAL_UNVERIFIED,
    capture_t_close_snapshot,
    verify_persisted_capture,
)


_BJT = timezone(timedelta(hours=8))
_TARGET = date(2026, 9, 22)
_CALENDAR = TradingCalendar(holidays=[], session_close_time=time(15, 0))
_NOW = datetime(2026, 9, 22, 15, 8, tzinfo=_BJT)


def _sessions_ending(end: date, count: int) -> list[str]:
    values: list[date] = []
    current = end
    while len(values) < count:
        if current.weekday() < 5:
            values.append(current)
        current -= timedelta(days=1)
    return [item.isoformat() for item in reversed(values)]


def _bar(day: str, close: float, *, opening: float | None = None, high: float | None = None, low: float | None = None, volume: float = 100.0) -> dict[str, object]:
    opening = close if opening is None else opening
    high = max(opening, close) + 0.8 if high is None else high
    low = min(opening, close) - 0.8 if low is None else low
    return {"date": day, "open": opening, "high": high, "low": low, "close": close, "volume": volume}


def _bars() -> list[dict[str, object]]:
    dates = _sessions_ending(_TARGET, 102)
    bars = [
        _bar(day, 80.0 + index * 0.55, high=81.0 + index * 0.55, low=79.0 + index * 0.55)
        for index, day in enumerate(dates[:90])
    ]
    bars.extend(
        [
            _bar(dates[90], 129.0, high=135.0, low=127.0, volume=90.0),
            _bar(dates[91], 125.0, high=127.0, low=123.0, volume=75.0),
            _bar(dates[92], 127.0, high=128.0, low=125.0, volume=70.0),
            _bar(dates[93], 126.0, high=127.0, low=125.0, volume=68.0),
            _bar(dates[94], 128.0, high=129.0, low=127.0, volume=72.0),
            _bar(dates[95], 125.5, high=127.0, low=124.0, volume=70.0),
            _bar(dates[96], 129.0, high=130.0, low=126.0, volume=80.0),
            _bar(dates[97], 132.0, high=133.0, low=129.0, volume=90.0),
            _bar(dates[98], 130.0, high=131.0, low=128.0, volume=95.0),
            _bar(dates[99], 129.5, high=131.0, low=128.0, volume=92.0),
            _bar(dates[100], 130.0, high=131.0, low=128.0, volume=95.0),
            _bar(dates[101], 134.0, opening=131.0, high=135.0, low=131.0, volume=250.0),
        ]
    )
    assert bars[-1]["date"] == _TARGET.isoformat()
    return bars


def _snapshot(*, missing_st: bool = False, future_bar: bool = False) -> dict[str, object]:
    bars = _bars()
    if future_bar:
        bars[-2] = dict(bars[-2], date="2026-09-23")
    received = "2026-09-22T15:03:00+08:00"
    security: dict[str, object] = {
        "request_id": "c-fixture-batch-1",
        "security_identity": {
            "security_id": "600001.SH",
            "code": "600001",
            "symbol": "600001.SH",
            "exchange": "XSHG",
            "name": "样本银行",
        },
        "st_status": {
            "status": "NOT_ST",
            "known_at_t": True,
            "as_of_date": _TARGET.isoformat(),
            "known_at": received,
            "source": "fixture-security-master",
        },
        "historical_prefix": bars[:-1],
        "t_ohlcv": bars[-1],
        "adjustment_basis": {
            "status": "KNOWN_AT_T",
            "price_basis": "UNADJUSTED_OHLCV",
            "volume_basis": "RAW_UNADJUSTED_VOLUME",
            "corporate_action_policy": "T_KNOWN_ONLY",
            "source": "fixture-market-data",
        },
    }
    if missing_st:
        security.pop("st_status")
    return {
        "schema_version": "C_PROVIDER_SNAPSHOT_V1",
        "target_date": _TARGET.isoformat(),
        "capture": {
            "mode": "SAME_DAY_T_CLOSE",
            "provider": "synthetic-c-provider",
            "provider_version": "fixture-1",
            "requests": [
                {
                    "request_id": "c-fixture-batch-1",
                    "source": "synthetic-c-provider",
                    "endpoint": "fixture://c/t-close",
                    "requested_at": "2026-09-22T15:01:00+08:00",
                    "received_at": received,
                    "response_bytes": 4096,
                    "response_sha256": "a" * 64,
                }
            ],
        },
        "securities": [security],
    }


def _load(root: Path, relative: str) -> dict[str, object]:
    return json.loads((root / relative).read_text(encoding="utf-8"))


def test_same_day_capture_persists_c_only_snapshot_observations_and_hashes(tmp_path: Path):
    result = capture_t_close_snapshot(
        _snapshot(),
        target_date=_TARGET.isoformat(),
        output_root=tmp_path,
        now_bjt=_NOW,
        calendar=_CALENDAR,
    )

    assert result["status"] == C_CAPTURED
    assert result["quality_failure_count"] == 0
    assert result["matched_event_sample_counts"]["BALANCED_A"] >= 0
    assert result["matched_event_sample_counts"]["CONSERVATIVE_B"] >= 0
    verified = verify_persisted_capture(result["manifest"], output_root=tmp_path)
    assert verified["status"] == "PASS"

    observation = _load(tmp_path, result["observation"])
    assert observation["full_comparable_universe"]["scope"] == "FULL_COMPARABLE_UNIVERSE"
    assert observation["matched_event_samples"]["BALANCED_A"]["scope"] == "MATCHED_EVENT_SAMPLE"
    assert observation["matched_event_samples"]["CONSERVATIVE_B"]["scope"] == "MATCHED_EVENT_SAMPLE"
    assert observation["matched_event_samples"]["BALANCED_A"]["cohort_claim"] != observation["full_comparable_universe"]["cohort_claim"]
    assert observation["boundary"]["b_evaluator_called"] is False
    assert observation["boundary"]["b_runtime_state_written"] is False

    security = observation["securities"][0]
    assert security["source"]["requested_at"] == "2026-09-22T15:01:00+08:00"
    assert security["source"]["received_at"] == "2026-09-22T15:03:00+08:00"
    assert security["t_ohlcv"]["date"] == _TARGET.isoformat()
    assert security["historical_prefix"][-1]["date"] < _TARGET.isoformat()
    assert set(security["observations"]) == {"BALANCED_A", "CONSERVATIVE_B"}


def test_each_rule_records_confirmation_day_volume_separately_from_pullback_path(tmp_path: Path):
    result = capture_t_close_snapshot(
        _snapshot(),
        target_date=_TARGET.isoformat(),
        output_root=tmp_path,
        now_bjt=_NOW,
        calendar=_CALENDAR,
    )
    observation = _load(tmp_path, result["observation"])
    for rule_id in ("BALANCED_A", "CONSERVATIVE_B"):
        volume = observation["securities"][0]["observations"][rule_id]["volume_observation"]
        assert volume["rv_t_scope"] == "CONFIRMATION_DAY_ONLY"
        assert volume["rv_t_does_not_represent_complete_pullback_volume_path"] is True
        assert volume["t_day_relative_volume"]["relative_volume_ratio"] >= 2.0
        assert volume["t_day_relative_volume"]["anomaly_ratio_candidate"] is True
        assert volume["pullback_path"]["path_status"] in {"OK", "INSUFFICIENT_REFERENCE_DAYS"}


def test_missing_st_is_persisted_as_partial_unverified_not_fake_complete(tmp_path: Path):
    result = capture_t_close_snapshot(
        _snapshot(missing_st=True),
        target_date=_TARGET.isoformat(),
        output_root=tmp_path,
        now_bjt=_NOW,
        calendar=_CALENDAR,
    )
    assert result["status"] == C_PARTIAL_UNVERIFIED
    assert result["quality_failure_count"] == 1
    observation = _load(tmp_path, result["observation"])
    security = observation["securities"][0]
    assert security["quality_status"] == C_PARTIAL_UNVERIFIED
    assert "UNRESOLVED_ST_STATUS" in security["failure_reasons"]
    assert observation["full_comparable_universe"]["count"] == 0
    assert not security["observations"]


def test_future_bar_is_rejected_and_failure_reason_is_retained(tmp_path: Path):
    result = capture_t_close_snapshot(
        _snapshot(future_bar=True),
        target_date=_TARGET.isoformat(),
        output_root=tmp_path,
        now_bjt=_NOW,
        calendar=_CALENDAR,
    )
    assert result["status"] == C_PARTIAL_UNVERIFIED
    assert "log" in result
    assert (tmp_path / "captures" / "20260922" / "canonical.json").exists()
    observation = _load(tmp_path, result["observation"])
    security = observation["securities"][0]
    assert security["quality_status"] == C_PARTIAL_UNVERIFIED
    assert any("OHLCV_INVALID" in reason for reason in security["failure_reasons"])
    log = _load(tmp_path, result["log"])
    assert log["quality_failure_count"] == 1


def test_same_input_is_idempotent_and_different_input_cannot_overwrite(tmp_path: Path):
    snapshot = _snapshot()
    first = capture_t_close_snapshot(
        snapshot,
        target_date=_TARGET.isoformat(),
        output_root=tmp_path,
        now_bjt=_NOW,
        calendar=_CALENDAR,
    )
    canonical_before = (tmp_path / first["canonical"]).read_bytes()
    input_before = (tmp_path / first["input_snapshot"]).read_bytes()
    second = capture_t_close_snapshot(
        snapshot,
        target_date=_TARGET.isoformat(),
        output_root=tmp_path,
        now_bjt=_NOW + timedelta(hours=1),
        calendar=_CALENDAR,
    )
    assert second["status"] == C_ALREADY_CAPTURED
    assert (tmp_path / first["canonical"]).read_bytes() == canonical_before
    assert (tmp_path / first["input_snapshot"]).read_bytes() == input_before

    changed = _snapshot()
    changed["securities"][0]["t_ohlcv"]["close"] = 133.5
    conflict = capture_t_close_snapshot(
        changed,
        target_date=_TARGET.isoformat(),
        output_root=tmp_path,
        now_bjt=_NOW,
        calendar=_CALENDAR,
    )
    assert conflict["status"] == C_INPUT_CONFLICT
    assert (tmp_path / first["canonical"]).read_bytes() == canonical_before


def test_input_snapshot_is_immutable_even_when_same_payload_is_replayed(tmp_path: Path):
    snapshot = _snapshot()
    first = capture_t_close_snapshot(
        snapshot,
        target_date=_TARGET.isoformat(),
        output_root=tmp_path,
        now_bjt=_NOW,
        calendar=_CALENDAR,
    )
    input_path = tmp_path / first["input_snapshot"]
    input_path.write_text("{\"tampered\":true}\n", encoding="utf-8")
    replay = capture_t_close_snapshot(
        snapshot,
        target_date=_TARGET.isoformat(),
        output_root=tmp_path,
        now_bjt=_NOW,
        calendar=_CALENDAR,
    )
    assert replay["status"] == C_CAPTURE_FAILED
    assert replay["reason"] == "immutable file differs: " + str(input_path)


def test_later_retrieval_cannot_be_marked_prospective(tmp_path: Path):
    result = capture_t_close_snapshot(
        _snapshot(),
        target_date=_TARGET.isoformat(),
        output_root=tmp_path,
        now_bjt=_NOW + timedelta(days=1),
        calendar=_CALENDAR,
    )
    assert result["status"] == C_NOT_PROSPECTIVE_BACKFILL
    assert not (tmp_path / "captures" / "20260922" / "canonical.json").exists()


def test_c_module_has_no_b_runtime_imports_and_failure_does_not_touch_b_sentinel(tmp_path: Path):
    source = Path(__file__).parents[1] / "scripts" / "c_prospective_capture.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
        for alias in [ast.alias(name=node.module, asname=None)]
    )
    assert not imported.intersection({"b_breakout_retest_v1_1", "b_shadow_monitor", "track_perf", "t_close_runner"})

    b_sentinel = tmp_path / "b-runtime-state-sentinel.txt"
    b_sentinel.write_text("unchanged", encoding="utf-8")
    result = capture_t_close_snapshot(
        _snapshot(future_bar=True),
        target_date=_TARGET.isoformat(),
        output_root=tmp_path / "c-store",
        now_bjt=_NOW,
        calendar=_CALENDAR,
    )
    assert result["status"] == C_PARTIAL_UNVERIFIED
    assert b_sentinel.read_text(encoding="utf-8") == "unchanged"
    assert not (tmp_path / "c-store" / "watchlist_20260922.json").exists()
