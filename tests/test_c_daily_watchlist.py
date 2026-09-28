from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from c_b_input_adapter import _price_only_observation
from c_daily_watchlist import build_watchlist, classify_c_status, publish_report, render_html, write_report
from run_c_daily_watchlist import (
    build_composite_delivery,
    b_is_complete,
    post_b,
    prepare_fallback_delivery,
    run,
    time_budget_status,
)
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
                       "b_input_coverage": {"excluded_symbol_count": 9},
                       "coverage_groups": {"b_evaluated_symbols": ["600000"],
                                           "b_input_isolated": [f"600{i:03d}" for i in range(1, 10)],
                                           "c_rule_or_st_excluded": [], "c_st_evidence_unresolved": []}},
            "gaps": ["VOLUME_ADJUSTMENT_SEMANTICS_UNRESOLVED"],
            "observations": [{"symbol": "600000", "name": "浦发银行", "b_kline_sha256": "b" * 64,
                              "price_protocol": "C_QFQ_INPUT_V1", "price_basis": "PROVIDER_QFQ_SNAPSHOT",
                              "volume_basis": "HITHINK_HISTORICAL_VOLUME_SHARES_ADJUSTMENT_UNVERIFIED",
                              "rules": {"BALANCED_A": a, "CONSERVATIVE_B": b}}]}


def test_research_match_keeps_volume_and_formal_signal_separate() -> None:
    result = build_watchlist(_record())
    assert result["matched_stock_count"] == 1
    assert result["matched_by_rule"]["BALANCED_A"] == 1
    assert result["coverage_breakdown"]["b_input_isolated"] == 9
    assert result["formal_b_signal"] is False
    a = result["rows"][0]["rules"]["BALANCED_A"]
    assert a["research_match_status"] == "PRICE_STRUCTURE_MATCH_VOLUME_GATE_UNVERIFIED"
    assert a["price_structure_event_identity"]
    assert a["entry_candidate"] is False
    assert a["volume_observation"]["volume_confirmation_valid"] is False
    html = render_html(result)
    assert "确认日 RV_T" in html and "回踩后半/前半量" in html
    assert "上涨日/下跌日量" in html and "VOLUME_BASIS_UNVERIFIED" in html
    assert "不属于 Formal B 正式名单" in html
    assert "B 输入隔离 9" in html
    assert "grid-template-columns: 1fr" in html


def test_no_match_still_has_readable_report() -> None:
    result = build_watchlist(_record(matched=False))
    assert result["matched_stock_count"] == 0
    assert result["data_pending_by_rule"]["CONSERVATIVE_B"] == 1
    html = render_html(result)
    assert "当前结果不能解释为零匹配" in html
    assert "matched_stock_count</span><strong>0" not in html


def test_explicit_zero_result_uses_success_no_match_status() -> None:
    record = _record(double=True)
    for rule in record["observations"][0]["rules"].values():
        rule["price_structure_match"] = False
        rule["research_match_status"] = "PRICE_STRUCTURE_NO_MATCH"
    result = build_watchlist(record)
    assert classify_c_status(result) == "C_SUCCESS_NO_MATCH"
    html = render_html(result)
    assert "今日无 C 研究匹配" in html
    assert "C_SUCCESS_NO_MATCH" in html


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


def test_public_report_is_small_versioned_and_c_only(tmp_path: Path) -> None:
    record = tmp_path / "record.json"
    record.write_text(json.dumps(_record(), ensure_ascii=False), encoding="utf-8")
    report = write_report(record, tmp_path / "rendered")
    state = tmp_path / "runtime-state"
    published = publish_report(report, state)
    assert published["status"] == "C_REPORT_STAGED"
    assert all(path.startswith("data/reports/c_daily/") for path in published["paths"])
    assert report["html_bytes"] < 2_000_000
    assert report["manifest_bytes"] < 100_000
    day = report["signal_date"].replace("-", "")
    dated = state / "data" / "reports" / "c_daily" / day
    assert (dated / "index.html").read_bytes() == Path(report["path"]).read_bytes()
    assert (dated / "manifest.json").read_bytes() == Path(report["manifest_path"]).read_bytes()
    assert (dated / report["version_sha256"] / "index.html").is_file()
    assert publish_report(report, state) == published
    assert not (state / "data" / "reports" / "latest.html").exists()


def test_publication_rejects_corrupt_report_and_preserves_previous_version(tmp_path: Path) -> None:
    record = tmp_path / "record.json"
    record.write_text(json.dumps(_record(), ensure_ascii=False), encoding="utf-8")
    report = write_report(record, tmp_path / "rendered")
    state = tmp_path / "runtime-state"
    publish_report(report, state)
    day = report["signal_date"].replace("-", "")
    previous = (state / "data" / "reports" / "c_daily" / day / "index.html").read_bytes()
    Path(report["path"]).write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="bytes differ"):
        publish_report(report, state)
    assert (state / "data" / "reports" / "c_daily" / day / "index.html").read_bytes() == previous


def test_missing_c_input_is_not_called_no_match() -> None:
    record = _record()
    record["observations"] = []
    with pytest.raises(ValueError, match="no verified C rule input"):
        build_watchlist(record)


def _b_result(tmp_path: Path) -> tuple[dict, dict]:
    from hashlib import sha256
    from daily_report_delivery import RECEIPT_SCHEMA_VERSION, delivery_receipt_path
    data = tmp_path / "data"
    (data / "reports").mkdir(parents=True)
    paths = [data / "input.json", data / "watchlist_20260922.json", data / "reports" / "daily_close_20260922.html"]
    for path in paths:
        content = ("<!doctype html><html><body><main>formal B bytes</main></body></html>"
                   if path.suffix == ".html" else "formal B bytes")
        path.write_text(content, encoding="utf-8")
    receipt = {"schema_version": RECEIPT_SCHEMA_VERSION, "report_date": "2026-09-22",
               "report_sha256": sha256(paths[2].read_bytes()).hexdigest(), "candidate_count": 0,
               "review_status": "READY", "shadow_status": "READY", "email_status": "SUCCESS",
               "email_sent_at_bjt": "2026-09-22T17:30:00+08:00", "bark_status": "SUCCESS",
               "bark_sent_at_bjt": "2026-09-22T17:30:00+08:00",
               "last_attempt_at_bjt": "2026-09-22T17:30:00+08:00"}
    receipt_path = delivery_receipt_path(data, "2026-09-22")
    receipt_path.parent.mkdir(parents=True)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    persisted = tmp_path / "runtime-state" / "data" / "delivery" / receipt_path.name
    persisted.parent.mkdir(parents=True)
    persisted.write_bytes(receipt_path.read_bytes())
    for source, relative in (
        (paths[1], Path("watchlist_20260922.json")),
        (paths[2], Path("reports/daily_close_20260922.html")),
        (data / "reports" / "latest.html", Path("reports/latest.html")),
    ):
        source.parent.mkdir(parents=True, exist_ok=True)
        if relative.name == "latest.html":
            source.write_text("formal B latest bytes", encoding="utf-8")
        destination = tmp_path / "runtime-state" / "data" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
    result = {"status": "T_CLOSE_EVIDENCE_PACKAGE_AND_WATCHLIST_PERSISTED", "as_of_date": "2026-09-22",
              "input_package": {"path": str(paths[0]), "file_sha256": sha256(paths[0].read_bytes()).hexdigest()},
              "watchlist": {"path": str(paths[1]), "file_sha256": sha256(paths[1].read_bytes()).hexdigest()},
              "daily_close_bundle": {"status": "READY", "track_perf": {"status": "SUCCESS"},
                                     "renderer": {"status": "SUCCESS"},
                                     "cloud_checkpoint": {"status": "DRIVE_CHECKPOINT_DISABLED_FOR_CLOUD"},
                                     "dated_html": str(paths[2])}}
    return result, {"status": "DELIVERY_SUCCESS", "receipt_status": "PERSISTED"}


def test_b_formal_gate_is_independent_of_delivery_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result, delivery = _b_result(tmp_path)
    data = tmp_path / "data"
    state = tmp_path / "runtime-state"
    assert b_is_complete(result, delivery, data, state)
    from run_c_daily_watchlist import b_formal_is_complete
    assert b_formal_is_complete(result, data, state)
    monkeypatch.setattr("run_c_daily_watchlist.consume_b_input", lambda *a, **k: pytest.fail("C started"))
    cases = [({**result, "status": "NO_VALID_INPUT"}, delivery),
             ({**result, "daily_close_bundle": {**result["daily_close_bundle"], "renderer": {"status": "FAILED"}}}, delivery)]
    for b_result, b_delivery in cases:
        assert run(b_result, b_delivery, data_root=data, state_root=state, evidence_root=tmp_path, report_root=tmp_path)["status"] == "C_NOT_STARTED_B_FORMAL_GATE_INCOMPLETE"
    (state / "data" / "delivery" / "daily_delivery_20260922.json").unlink()
    assert b_formal_is_complete(result, data, state)
    monkeypatch.setattr("run_c_daily_watchlist.consume_b_input", lambda *a, **k: (_ for _ in ()).throw(TimeoutError("C")))
    assert run(result, {"status": "DELIVERY_FAILED"}, data_root=data, state_root=state,
               evidence_root=tmp_path, report_root=tmp_path)["status"] == "C_FAILED_B_UNCHANGED"


def test_c_exception_is_isolated_from_b_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result, delivery = _b_result(tmp_path)
    data = tmp_path / "data"
    state = tmp_path / "runtime-state"
    formal = [Path(result["input_package"]["path"]), Path(result["watchlist"]["path"]),
              Path(result["daily_close_bundle"]["dated_html"])]
    before = [path.read_bytes() for path in formal]
    monkeypatch.setattr("run_c_daily_watchlist.consume_b_input", lambda *a, **k: (_ for _ in ()).throw(TimeoutError("C budget")))
    status = run(result, delivery, data_root=data, state_root=state, evidence_root=tmp_path, report_root=tmp_path)["status"]
    assert status == "C_FAILED_B_UNCHANGED"
    assert [path.read_bytes() for path in formal] == before


def test_c_time_budget_protects_retry_job_deadline_and_manual_dispatch() -> None:
    utc = timezone.utc
    base = datetime(2026, 9, 24, 9, 20, tzinfo=utc)
    assert time_budget_status(base, base + timedelta(minutes=10), "17 9 * * 1-5")["status"] == "C_BUDGET_READY"
    assert time_budget_status(base, datetime(2026, 9, 24, 10, 20, tzinfo=utc), "17 9 * * 1-5")["reason"] == "PRIMARY_OVERLAPS_RETRY"
    assert time_budget_status(base, datetime(2026, 9, 24, 10, 5, tzinfo=utc))["status"] == "C_NOT_STARTED_TIME_BUDGET"
    retry_start = datetime(2026, 9, 24, 10, 20, tzinfo=utc)
    assert time_budget_status(retry_start, retry_start + timedelta(minutes=45), "17 10 * * 1-5")["status"] == "C_BUDGET_READY"
    assert time_budget_status(base, base + timedelta(minutes=107), "17 9 * * 1-5")["reason"] == "JOB_DEADLINE"


def test_primary_run_may_start_c_once_b_completed_the_target_date() -> None:
    utc = timezone.utc
    base = datetime(2026, 9, 24, 9, 20, tzinfo=utc)
    after_retry_slot = datetime(2026, 9, 24, 10, 20, tzinfo=utc)
    assert time_budget_status(base, after_retry_slot, "17 9 * * 1-5")["reason"] == "PRIMARY_OVERLAPS_RETRY"
    ready = time_budget_status(base, after_retry_slot, "17 9 * * 1-5", b_complete_for_target_date=True)
    assert ready["status"] == "C_BUDGET_READY"
    assert ready["next_b_schedule_utc"] == "2026-09-25T09:17:00+00:00"
    assert ready["c_tail_budget_seconds"] == 600
    near_retry_slot = datetime(2026, 9, 24, 10, 5, tzinfo=utc)
    assert time_budget_status(base, near_retry_slot, "17 9 * * 1-5")["reason"] == "NEXT_B_SCHEDULE"
    assert time_budget_status(base, near_retry_slot, "17 9 * * 1-5",
                              b_complete_for_target_date=True)["status"] == "C_BUDGET_READY"
    manual_window = datetime(2026, 9, 24, 10, 30, tzinfo=utc)
    assert time_budget_status(base, manual_window, "")["reason"] == "MANUAL_NEAR_B_SCHEDULE"
    assert time_budget_status(base, manual_window, "",
                              b_complete_for_target_date=True)["status"] == "C_BUDGET_READY"
    for complete in (False, True):
        assert time_budget_status(base, base + timedelta(minutes=107), "17 9 * * 1-5",
                                  b_complete_for_target_date=complete)["reason"] == "JOB_DEADLINE"


def test_prepare_delivery_builds_inline_composite_and_fallback_on_c_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, _delivery = _b_result(tmp_path)
    b_result = tmp_path / "b-result.json"
    b_result.write_text(json.dumps(result), encoding="utf-8")
    formal_path = Path(result["daily_close_bundle"]["dated_html"])
    formal_before = formal_path.read_bytes()

    monkeypatch.setattr(
        "run_c_daily_watchlist._run_c_child",
        lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("c", 1)),
    )
    prepared = __import__("run_c_daily_watchlist").prepare_delivery(
        b_result=b_result,
        data_root=tmp_path / "data",
        state_root=tmp_path / "runtime-state",
        evidence_root=tmp_path / "evidence",
        report_root=tmp_path / "rendered",
        delivery_root=tmp_path / "delivery-report",
        started_at=datetime(2026, 9, 24, 11, tzinfo=timezone.utc),
        now=datetime(2026, 9, 24, 11, 1, tzinfo=timezone.utc),
    )
    assert prepared["status"] == "C_DELIVERY_READY"
    assert prepared["c_status"] == "C_TIMEOUT"
    composite = Path(prepared["delivery_report_path"])
    text = composite.read_text(encoding="utf-8")
    assert "C_TIMEOUT" in text
    assert "C 研究结果今日未完成" in text
    assert "formal_b_signal" in text and "false" in text
    assert formal_path.read_bytes() == formal_before


def test_success_composite_contains_c_once_without_external_dependencies(tmp_path: Path) -> None:
    result, _delivery = _b_result(tmp_path)
    observation = tmp_path / "observation.json"
    observation.write_text(json.dumps(_record(double=True), ensure_ascii=False), encoding="utf-8")
    report = write_report(observation, tmp_path / "rendered")
    prepared = build_composite_delivery(
        result,
        {"status": "C_DAILY_RESEARCH_REPORT_READY", "c_status": report["c_status"], "report": report},
        delivery_root=tmp_path / "delivery-report",
    )

    html = Path(prepared["delivery_report_path"]).read_text(encoding="utf-8")
    assert prepared["c_status"] == "C_SUCCESS_WITH_MATCHES"
    assert html.count('id="c-daily-research"') == 1
    assert "600000" in html and "浦发银行" in html
    assert "BALANCED_A" in html and "CONSERVATIVE_B" in html
    assert "VOLUME_BASIS_UNVERIFIED" in html and "formal_b_signal" in html
    assert "c_daily/" not in html and "iframe" not in html and "fetch(" not in html
    assert Path(result["daily_close_bundle"]["dated_html"]).read_bytes() == (
        b"<!doctype html><html><body><main>formal B bytes</main></body></html>"
    )


def test_already_completed_retry_gets_explicit_c_not_run_composite(tmp_path: Path) -> None:
    result, _delivery = _b_result(tmp_path)
    prepared = prepare_fallback_delivery(
        report_date=result["as_of_date"],
        formal_report_path=Path(result["daily_close_bundle"]["dated_html"]),
        delivery_root=tmp_path / "delivery-report",
    )
    html = Path(prepared["delivery_report_path"]).read_text(encoding="utf-8")
    assert prepared["status"] == "C_DELIVERY_READY"
    assert prepared["c_status"] == "C_NOT_RUN"
    assert "C_NOT_RUN" in html and "C 研究结果今日未完成" in html
    assert "matched_stock_count=0" not in html


def test_post_b_reuses_precomputed_c_result_without_rerunning_c(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, delivery = _b_result(tmp_path)
    b_result = tmp_path / "b-result.json"
    delivery_result = tmp_path / "delivery-result.json"
    b_result.write_text(json.dumps(result), encoding="utf-8")
    delivery_result.write_text(json.dumps(delivery), encoding="utf-8")
    observation = tmp_path / "observation.json"
    observation.write_text(json.dumps(_record(), ensure_ascii=False), encoding="utf-8")
    report = write_report(observation, tmp_path / "rendered")
    prepared = tmp_path / "prepared.json"
    prepared.write_text(json.dumps({
        "status": "C_DELIVERY_READY",
        "c_status": report["c_status"],
        "c_result": {"status": "C_DAILY_RESEARCH_REPORT_READY", "c_status": report["c_status"], "report": report},
    }), encoding="utf-8")
    _init_c_state_repo(tmp_path / "runtime-state", tmp_path / "remote.git")
    monkeypatch.setattr("run_c_daily_watchlist.consume_b_input", lambda *a, **k: pytest.fail("C reran"))
    outcome = post_b(
        b_result=b_result,
        delivery_result=delivery_result,
        prepared_result=prepared,
        data_root=tmp_path / "data",
        state_root=tmp_path / "runtime-state",
    )
    assert outcome["status"] == "C_DAILY_REPORT_PUBLISHED"
    assert outcome["c_status"] == report["c_status"]


def _init_c_state_repo(state: Path, remote: Path) -> None:
    state.mkdir(parents=True, exist_ok=True)
    (state / "RUNTIME_STATE.md").write_text(
        "GITHUB_ACTIONS_DAILY_RUNTIME_V1\noperational state only\nnever merge into master\n"
        "cloud workflow is the normal single writer\nno secrets\nno raw market evidence\n", encoding="utf-8")
    subprocess.run(["git", "init", "--initial-branch=runtime-state", str(state)], check=True, capture_output=True)
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    for args in (("config", "user.name", "test"), ("config", "user.email", "test@example.com"),
                 ("remote", "add", "origin", str(remote)), ("add", "."), ("commit", "-m", "initial"),
                 ("push", "origin", "HEAD:runtime-state")):
        subprocess.run(["git", *args], cwd=state, check=True, capture_output=True)


@pytest.mark.parametrize("matched", [True, False])
@pytest.mark.parametrize("fail_stage", [None, "push", "readback"])
def test_post_b_publishes_only_c_files_with_real_git_readback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                               matched: bool, fail_stage: str | None) -> None:
    result, delivery = _b_result(tmp_path)
    state = tmp_path / "runtime-state"
    remote = tmp_path / "remote.git"
    _init_c_state_repo(state, remote)
    b_result = tmp_path / "b-result.json"
    delivery_result = tmp_path / "delivery-result.json"
    b_result.write_text(json.dumps(result), encoding="utf-8")
    delivery_result.write_text(json.dumps(delivery), encoding="utf-8")
    observation = tmp_path / "observation.json"
    observation.write_text(json.dumps(_record(matched=matched), ensure_ascii=False), encoding="utf-8")
    report = write_report(observation, tmp_path / "rendered")
    prepared = tmp_path / "prepared.json"
    prepared.write_text(json.dumps({
        "status": "C_DELIVERY_READY",
        "c_status": report["c_status"],
        "c_result": {"status": "C_DAILY_RESEARCH_REPORT_READY", "c_status": report["c_status"], "report": report},
    }), encoding="utf-8")
    if fail_stage:
        import run_c_daily_watchlist as runner
        original_git = runner._git
        def reject_git(root, *args, **kwargs):
            if (fail_stage == "push" and args and args[0] == "push") or (
                fail_stage == "readback" and args and args[0] == "show"
            ):
                raise subprocess.CalledProcessError(1, ["git", *args])
            return original_git(root, *args, **kwargs)
        monkeypatch.setattr(runner, "_git", reject_git)
    formal_paths = [Path(result["input_package"]["path"]), Path(result["watchlist"]["path"]),
                    Path(result["daily_close_bundle"]["dated_html"]),
                    state / "data" / "delivery" / "daily_delivery_20260922.json"]
    original = {str(path): path.read_bytes() for path in formal_paths}
    outcome = post_b(b_result=b_result, delivery_result=delivery_result, prepared_result=prepared,
                     data_root=tmp_path / "data", state_root=state)
    assert outcome["status"] == ("C_REPORT_PUBLISH_FAILED_B_UNCHANGED" if fail_stage else "C_DAILY_REPORT_PUBLISHED")
    if fail_stage:
        assert outcome["stage"] == ("PUSH_C_REPORT" if fail_stage == "push" else "REMOTE_READBACK")
    if not fail_stage:
        assert outcome["matched_stock_count"] == (1 if matched else 0)
        assert all(path.startswith("data/reports/c_daily/") for path in outcome["paths"])
    assert {str(path): path.read_bytes() for path in formal_paths} == original
    assert (state / "data" / "reports" / "latest.html").read_bytes() == (
        tmp_path / "data" / "reports" / "latest.html"
    ).read_bytes()
    if not fail_stage:
        assert subprocess.run(["git", "--git-dir", str(remote), "show", "runtime-state:" + outcome["paths"][-2]],
                              check=True, capture_output=True).stdout == (state / outcome["paths"][-2]).read_bytes()


def test_post_b_c_failure_and_publish_failure_leave_b_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result, delivery = _b_result(tmp_path)
    b_result = tmp_path / "b-result.json"
    delivery_result = tmp_path / "delivery-result.json"
    b_result.write_text(json.dumps(result), encoding="utf-8")
    delivery_result.write_text(json.dumps(delivery), encoding="utf-8")
    prepared = tmp_path / "prepared.json"
    prepared.write_text(json.dumps({"status": "C_DELIVERY_READY", "c_status": "C_FAILED",
                                    "c_result": {"status": "C_FAILED_B_UNCHANGED"}}), encoding="utf-8")
    assert post_b(b_result=b_result, delivery_result=delivery_result, prepared_result=prepared,
                  data_root=tmp_path / "data", state_root=tmp_path / "runtime-state")["status"] == "C_NOT_PUBLISHED_C_UNAVAILABLE"
    assert delivery["status"] == "DELIVERY_SUCCESS"


def test_workflow_prepares_composite_before_delivery_and_publishes_c_after_health() -> None:
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/daily_t_close.yml").read_text(encoding="utf-8")
    ids = {name: workflow.index(f"        id: {name}\n") for name in (
        "b_production", "b_output_validation", "b_state_push", "c_pre_delivery", "b_delivery",
        "b_receipt_persist", "delivery_health", "c_daily")}
    assert ids["b_production"] < ids["b_output_validation"] < ids["b_state_push"]
    assert ids["b_state_push"] < ids["c_pre_delivery"] < ids["b_delivery"] < ids["b_receipt_persist"] < ids["delivery_health"] < ids["c_daily"]
    pre_step = workflow[ids["c_pre_delivery"]:workflow.index("      - name:", ids["c_pre_delivery"])]
    c_step = workflow[ids["c_daily"]:workflow.index("      - name:", ids["c_daily"])]
    for gate in ("b_production", "b_output_validation", "b_state_push", "b_delivery",
                 "b_receipt_persist", "delivery_health"):
        if gate == "b_delivery" or gate == "b_receipt_persist" or gate == "delivery_health":
            assert f"steps.{gate}.outcome == 'success'" in c_step
        else:
            assert f"steps.{gate}.outcome == 'success'" in pre_step or gate == "b_production"
    assert "ENABLE_C_DAILY_RESEARCH_WATCHLIST_V1" in pre_step
    assert "--prepare-delivery" in pre_step and "--delivery-root" in pre_step
    assert "--prepare-fallback" in pre_step
    assert "--delivery-report-path" in workflow
    assert "steps.c_pre_delivery.outcome == 'success'" in c_step
    assert "--prepared-result" in c_step
    assert "continue-on-error: true" in c_step
    assert "C status:" in c_step and "Formal B delivery health: SUCCESS" in c_step
    fallback = workflow[workflow.index("      - name: Preserve C failure diagnosis") :]
    assert "steps.c_pre_delivery.outcome == 'failure'" in fallback
    assert "steps.c_daily.outcome == 'failure'" in fallback
    assert "continue-on-error: true" in fallback
    assert "C presentation/publication outcome:" in fallback


def test_c_unavailable_presentation_never_fabricates_zero_match() -> None:
    from c_daily_watchlist import render_unavailable_section

    for status in ("C_TIMEOUT", "C_FAILED", "C_NOT_RUN", "C_DATA_PENDING"):
        html = render_unavailable_section("2026-09-24", status)
        assert "formal_b_signal" in html and "false" in html
        assert "matched_stock_count=0" not in html
        assert "今日无 C 研究匹配" not in html


def test_same_day_retry_keeps_both_c_package_versions(tmp_path: Path) -> None:
    first_record = _record()
    second_record = _record()
    second_record["source"]["b_package_actual_sha256"] = "c" * 64
    state = tmp_path / "runtime-state"
    reports = []
    for number, record in enumerate((first_record, second_record)):
        path = tmp_path / f"record-{number}.json"
        path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        report = write_report(path, tmp_path / "rendered")
        publish_report(report, state)
        reports.append(report)
    day = reports[0]["signal_date"].replace("-", "")
    root = state / "data" / "reports" / "c_daily" / day
    assert reports[0]["version_sha256"] != reports[1]["version_sha256"]
    assert (root / reports[0]["version_sha256"] / "index.html").is_file()
    assert (root / reports[1]["version_sha256"] / "index.html").is_file()
    assert json.loads((root / "manifest.json").read_bytes())["package_sha256"] == "c" * 64


def test_real_b_serializer_to_c_html_uses_only_frozen_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import hashlib
    import c_b_input_adapter as adapter
    import c_prospective_capture as capture
    import live_acquisition as live
    from test_live_acquisition import FakeHiThink, _acquire, _bars

    package = _acquire(hithink_client=FakeHiThink(bars=_bars(count=120), index_bars=_bars(count=120)),
                       stock_bar_count=120)
    persisted = live.persist_live_input_package(package, tmp_path / "b")
    value = json.loads(persisted.path.read_bytes())
    symbol = value["generation_input_manifest"]["universe"]["symbols"][0]
    evidence = tmp_path / "evidence"
    captures = []
    for source, logical, body in (
        ("/api/meta/tickers/list", "ticker-page",
         {"code": 0, "data": {"item": [{"ticker": symbol, "name": value["display_names"][symbol]}]}}),
        ("/api/a-share/prices/historical", f"thscode={symbol}.SH", {"code": 0, "data": {"item": []}}),
    ):
        payload = adapter._canonical(body)
        digest = hashlib.sha256(payload).hexdigest()
        base = evidence / "20260827" / "hithink_response" / hashlib.sha256(logical.encode()).hexdigest()
        base.parent.mkdir(parents=True, exist_ok=True)
        base.with_suffix(".raw").write_bytes(payload)
        base.with_suffix(".json").write_bytes(adapter._canonical({
            "file_sha256": digest, "byte_length": len(payload),
            "logical_component_identity": logical, "source_identity": source,
            "request_identity": logical, "requested_at_bjt": "2026-08-27T15:01:00+08:00",
            "received_at_bjt": "2026-08-27T15:02:00+08:00"}))
        captures.append({"component": "hithink_response", "logical_component_identity": logical,
                         "source_identity": source, "file_sha256": digest, "completeness_status": "COMPLETE"})
    value["provenance"]["evidence_capture"] = {"captures": captures}
    value.pop("content_sha256")
    value["content_sha256"] = hashlib.sha256(adapter._canonical(value)).hexdigest()
    persisted.path.write_bytes(adapter._canonical(value))
    sha = hashlib.sha256(persisted.path.read_bytes()).hexdigest()
    monkeypatch.setattr(capture, "C_OUTPUT_ROOT", tmp_path / "data/research/c_prospective_capture_v1")
    monkeypatch.setattr("requests.get", lambda *a, **k: pytest.fail("C requested provider data"))
    from datetime import timezone as tz
    observed = adapter.consume_b_input(persisted.path, target_date="2026-08-27", expected_sha256=sha,
                                       local_runner_input=True, evidence_root=evidence,
                                       read_at=datetime(2026, 8, 27, 19, tzinfo=tz(timedelta(hours=8))))
    assert observed["observation_count"] == 1
    report = write_report(capture.C_OUTPUT_ROOT / observed["record"], tmp_path / "c-report")
    assert "C 策略研究名单" in Path(report["path"]).read_text(encoding="utf-8")
    assert report["html_bytes"] < 2_000_000
    assert hashlib.sha256(persisted.path.read_bytes()).hexdigest() == sha


_B_SHELL = (
    '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><style>'
    '.section-nav { position: sticky; top: 0; z-index: 20; }</style></head><body><main>'
    '<header class="site-header"><h1>测试日报</h1>\n'
    '<nav class="section-nav" aria-label="报告章节导航">'
    '<a href="#overview">总览</a><a href="#tomorrow-watchlist">新名单</a>'
    '<a href="#trade-performance">绩效</a></nav>\n</header>\n'
    '<section id="overview">总览内容</section>\n'
    '<section id="tomorrow-watchlist">新名单内容</section>\n'
    '<section id="trade-performance">绩效内容</section>\n'
    '<details id="audit"><summary>技术与审计信息</summary></details>\n'
    '</main></body></html>'
)


def _single_match_watchlist() -> dict:
    record = _record(double=True)
    rule = record["observations"][0]["rules"]["CONSERVATIVE_B"]
    rule["price_structure_match"] = False
    rule["research_match_status"] = "PRICE_STRUCTURE_RULE_NOT_SATISFIED"
    rule["research_match_reason"] = "PRICE_STRUCTURE_RULE_NOT_SATISFIED"
    rule["price_structure_event_identity"] = None
    return build_watchlist(record)


def test_composite_places_c_module_after_new_list_with_nav_entry() -> None:
    from c_daily_watchlist import compose_delivery_html, render_section

    watchlist = _single_match_watchlist()
    section = render_section(watchlist)
    html = compose_delivery_html(_B_SHELL, section).decode("utf-8")

    assert html.count('id="c-daily-research"') == 1
    assert '<a href="#tomorrow-watchlist">新名单</a><a href="#c-daily-research">C研究</a>' in html
    assert (html.index('<section id="tomorrow-watchlist"') < html.index('<section id="c-daily-research"')
            < html.index('<section id="trade-performance"'))
    assert "c_daily/" not in html and "iframe" not in html
    # The presentation copy differs from the canonical Formal B bytes only by the
    # added navigation entry and the inline C module.
    restored = html.replace(f"\n{section}\n", "").replace(
        '<a href="#c-daily-research">C研究</a>', "")
    assert restored == _B_SHELL


def test_c_module_first_layer_is_compact_and_technical_detail_is_collapsed() -> None:
    from c_daily_watchlist import render_section

    watchlist = _single_match_watchlist()
    assert watchlist["matched_stock_count"] == 1
    assert watchlist["matched_by_rule"] == {"BALANCED_A": 1, "CONSERVATIVE_B": 0}
    html = render_section(watchlist)
    card = html.split('<article class="c-stock-card">', 1)[1]
    visible = card.split("<details", 1)[0]

    assert "<h2>C 策略研究名单 · 1 只</h2>" in html
    assert "<span>命中股票</span><strong>1</strong>" in html
    assert "<span>BALANCED_A</span><strong>1</strong>" in html
    assert "<span>CONSERVATIVE_B</span><strong>0</strong>" in html
    assert "600000" in visible and "浦发银行" in visible
    assert '<span class="badge positive">BALANCED_A</span>' in visible
    assert "价格结构匹配" in visible
    for label in ("前高", "回踩低点", "确认状态", "确认日 RV_T", "回踩/基准量",
                  "回踩后半/前半量", "上涨日/下跌日量"):
        assert label in visible
    # The unmatched rule is one collapsed line, not a second full-size block.
    assert "CONSERVATIVE_B" not in visible
    assert ('<details class="c-rule-other"><summary>其他规则详情 · CONSERVATIVE_B · 未匹配</summary>'
            in html)
    assert '<details class="c-stock-audit"><summary>技术审计详情</summary>' in html
    assert '<details class="c-stock-audit" open' not in html
    assert '<details class="c-rule-other" open' not in html
    # Machine detail is still reachable: identity, SHAs and raw status codes.
    assert "事件身份" in html
    assert "VOLUME_BASIS_UNVERIFIED" in html and "formal_b_signal=false" in html
    assert "B 输入隔离 9" in html and "package SHA" in html


def test_c_module_style_is_scoped_and_reuses_formal_b_tokens() -> None:
    from c_daily_watchlist import render_section

    html = render_section(_single_match_watchlist())
    style = html.split("<style data-c-daily-inline-style>", 1)[1].split("</style>", 1)[0]
    for unscoped in ("html", "body", "main", "header", "section", "table", "th", "td",
                     ".badge", "h2", "h3", "p"):
        assert not re.search(rf"(?:^|}})\s*{re.escape(unscoped)}\s*[{{,]", style), unscoped
    for token in ("var(--border", "var(--muted", "var(--surface-2", "var(--accent",
                  "var(--surface", "var(--warning"):
        assert token in style
    section = html.split("</style>", 1)[1]
    for shared_class in ('class="section-head"', 'class="section-kicker"',
                         'class="section-subtitle"', 'class="badge warning"'):
        assert shared_class in section
    assert "grid-template-columns: 1fr" in style


def test_c_module_result_values_come_from_the_computed_watchlist() -> None:
    from c_daily_watchlist import render_section

    watchlist = build_watchlist(_record(double=True))
    assert watchlist["matched_by_rule"] == {"BALANCED_A": 1, "CONSERVATIVE_B": 1}
    html = render_section(watchlist)
    assert "<span>命中股票</span><strong>1</strong>" in html
    assert "<span>BALANCED_A</span><strong>1</strong>" in html
    assert "<span>CONSERVATIVE_B</span><strong>1</strong>" in html
    assert '<span class="badge positive">BALANCED_A</span>' in html
    assert '<span class="badge positive">CONSERVATIVE_B</span>' in html
    # A double match keeps both rule events reachable without a second visible block.
    assert html.count("independent-b-event") == 1
