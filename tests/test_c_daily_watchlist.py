from __future__ import annotations

import json
from pathlib import Path

import pytest

from c_b_input_adapter import _price_only_observation
from c_daily_watchlist import build_watchlist, render_html, write_report
from run_c_daily_watchlist import b_is_complete, run
from test_c_pre_outcome_design import _synthetic_entry_bars


def _record(*, matched: bool = True, double: bool = False) -> dict:
    bars = _synthetic_entry_bars()
    a = _price_only_observation("600000", bars[-1]["date"], bars, "BALANCED_A")
    b = _price_only_observation("600000", bars[-1]["date"], bars, "CONSERVATIVE_B")
    assert a["price_structure_match"] is True
    if not matched:
        a["price_structure_match"] = False
    if double:
        b["price_structure_match"] = True
        b["price_structure_event_identity"] = "independent-b-event"
        b["research_match_status"] = "PRICE_STRUCTURE_MATCH_VOLUME_GATE_UNVERIFIED"
        b["research_match_reason"] = "TREND_PULLBACK_REBOUND_SUPPORT_MATCH; VOLUME_BASIS_UNVERIFIED"
    return {"schema_version": "C_B_FROZEN_INPUT_READER_V1", "status": "PRICE_OBSERVATION_VOLUME_UNVERIFIED",
            "source": {"target_date": bars[-1]["date"], "b_package_actual_sha256": "a" * 64,
                       "b_generation_fingerprint": "generation", "coverage_status": "PARTIAL_UNVERIFIED",
                       "b_input_coverage": {"excluded_symbol_count": 9}},
            "gaps": ["VOLUME_ADJUSTMENT_SEMANTICS_UNRESOLVED"],
            "observations": [{"symbol": "600000", "name": "浦发银行", "b_kline_sha256": "b" * 64,
                              "price_protocol": "C_QFQ_INPUT_V1", "price_basis": "PROVIDER_QFQ_SNAPSHOT",
                              "volume_basis": "HITHINK_HISTORICAL_VOLUME_SHARES_ADJUSTMENT_UNVERIFIED",
                              "rules": {"BALANCED_A": a, "CONSERVATIVE_B": b}}]}


def test_research_match_keeps_volume_and_formal_signal_separate() -> None:
    result = build_watchlist(_record())
    assert result["matched_stock_count"] == 1
    assert result["matched_by_rule"]["BALANCED_A"] == 1
    assert result["formal_b_signal"] is False
    a = result["rows"][0]["rules"]["BALANCED_A"]
    assert a["research_match_status"] == "PRICE_STRUCTURE_MATCH_VOLUME_GATE_UNVERIFIED"
    assert a["price_structure_event_identity"]
    assert a["entry_candidate"] is False
    assert a["volume_observation"]["volume_confirmation_valid"] is False
    html = render_html(result)
    assert "确认日 RV_T" in html and "回踩后半/前半量" in html
    assert "上涨日/下跌日量" in html and "VOLUME_BASIS_UNVERIFIED" in html
    assert "非 Formal B 名单" in html
    assert "grid-template-columns:1fr" in html


def test_no_match_still_has_readable_report() -> None:
    result = build_watchlist(_record(matched=False))
    assert result["matched_stock_count"] == 0
    assert "今日无 C 研究匹配" in render_html(result)


def test_double_match_keeps_two_rule_events() -> None:
    result = build_watchlist(_record(double=True))
    assert result["matched_stock_count"] == 1
    assert result["matched_by_rule"] == {"BALANCED_A": 1, "CONSERVATIVE_B": 1}
    html = render_html(result)
    assert "independent-b-event" in html
    assert result["rows"][0]["rules"]["BALANCED_A"]["price_structure_event_identity"] != "independent-b-event"


def test_report_write_failure_does_not_touch_input(tmp_path: Path) -> None:
    record = tmp_path / "record.json"
    record.write_text(json.dumps(_record(), ensure_ascii=False), encoding="utf-8")
    before = record.read_bytes()
    report = write_report(record, tmp_path / "reports")
    assert Path(report["path"]).is_file()
    assert record.read_bytes() == before
    blocked = tmp_path / "reports" / "blocked-file"
    blocked.write_text("x", encoding="utf-8")
    with pytest.raises(OSError):
        write_report(record, blocked)
    assert record.read_bytes() == before


def test_missing_c_input_is_not_called_no_match() -> None:
    record = _record()
    record["observations"] = []
    with pytest.raises(ValueError, match="no verified C rule input"):
        build_watchlist(record)


def _b_result(tmp_path: Path) -> tuple[dict, dict]:
    from hashlib import sha256
    data = tmp_path / "data"
    (data / "reports").mkdir(parents=True)
    paths = [data / "input.json", data / "watchlist.json", data / "reports" / "daily_close_20260922.html"]
    for path in paths:
        path.write_text("formal B bytes", encoding="utf-8")
    result = {"status": "T_CLOSE_EVIDENCE_PACKAGE_AND_WATCHLIST_PERSISTED", "as_of_date": "2026-09-22",
              "input_package": {"path": str(paths[0]), "file_sha256": sha256(paths[0].read_bytes()).hexdigest()},
              "watchlist": {"path": str(paths[1]), "file_sha256": sha256(paths[1].read_bytes()).hexdigest()},
              "daily_close_bundle": {"status": "READY", "track_perf": {"status": "SUCCESS"},
                                     "renderer": {"status": "SUCCESS"},
                                     "cloud_checkpoint": {"status": "DRIVE_CHECKPOINT_DISABLED_FOR_CLOUD"},
                                     "dated_html": str(paths[2])}}
    return result, {"status": "DELIVERY_SUCCESS"}


def test_b_failure_modes_never_start_c(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result, delivery = _b_result(tmp_path)
    data = tmp_path / "data"
    assert b_is_complete(result, delivery, data)
    monkeypatch.setattr("run_c_daily_watchlist.consume_b_input", lambda *a, **k: pytest.fail("C started"))
    cases = [({**result, "status": "NO_VALID_INPUT"}, delivery),
             ({**result, "daily_close_bundle": {**result["daily_close_bundle"], "renderer": {"status": "FAILED"}}}, delivery),
             (result, {"status": "DELIVERY_FAILED"})]
    for b_result, b_delivery in cases:
        assert run(b_result, b_delivery, data_root=data, evidence_root=tmp_path, report_root=tmp_path)["status"] == "C_NOT_STARTED_B_FORMAL_GATE_INCOMPLETE"


def test_c_exception_is_isolated_from_b_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result, delivery = _b_result(tmp_path)
    data = tmp_path / "data"
    formal = [Path(result["input_package"]["path"]), Path(result["watchlist"]["path"]),
              Path(result["daily_close_bundle"]["dated_html"])]
    before = [path.read_bytes() for path in formal]
    monkeypatch.setattr("run_c_daily_watchlist.consume_b_input", lambda *a, **k: (_ for _ in ()).throw(TimeoutError("C budget")))
    status = run(result, delivery, data_root=data, evidence_root=tmp_path, report_root=tmp_path)["status"]
    assert status == "C_FAILED_B_UNCHANGED"
    assert [path.read_bytes() for path in formal] == before
