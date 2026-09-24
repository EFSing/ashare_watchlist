from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from c_b_input_adapter import _price_only_observation
from c_daily_watchlist import build_watchlist, publish_report, render_html, write_report
from run_c_daily_watchlist import b_is_complete, post_b, run, time_budget_status
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
    assert "非 Formal B 名单" in html
    assert "B 输入隔离 9" in html
    assert "grid-template-columns:1fr" in html


def test_no_match_still_has_readable_report() -> None:
    result = build_watchlist(_record(matched=False))
    assert result["matched_stock_count"] == 0
    assert result["data_pending_by_rule"]["CONSERVATIVE_B"] == 1
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
    paths = [data / "input.json", data / "watchlist.json", data / "reports" / "daily_close_20260922.html"]
    for path in paths:
        path.write_text("formal B bytes", encoding="utf-8")
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
    result = {"status": "T_CLOSE_EVIDENCE_PACKAGE_AND_WATCHLIST_PERSISTED", "as_of_date": "2026-09-22",
              "input_package": {"path": str(paths[0]), "file_sha256": sha256(paths[0].read_bytes()).hexdigest()},
              "watchlist": {"path": str(paths[1]), "file_sha256": sha256(paths[1].read_bytes()).hexdigest()},
              "daily_close_bundle": {"status": "READY", "track_perf": {"status": "SUCCESS"},
                                     "renderer": {"status": "SUCCESS"},
                                     "cloud_checkpoint": {"status": "DRIVE_CHECKPOINT_DISABLED_FOR_CLOUD"},
                                     "dated_html": str(paths[2])}}
    return result, {"status": "DELIVERY_SUCCESS", "receipt_status": "PERSISTED"}


def test_b_failure_modes_never_start_c(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result, delivery = _b_result(tmp_path)
    data = tmp_path / "data"
    state = tmp_path / "runtime-state"
    assert b_is_complete(result, delivery, data, state)
    monkeypatch.setattr("run_c_daily_watchlist.consume_b_input", lambda *a, **k: pytest.fail("C started"))
    cases = [({**result, "status": "NO_VALID_INPUT"}, delivery),
             ({**result, "daily_close_bundle": {**result["daily_close_bundle"], "renderer": {"status": "FAILED"}}}, delivery),
             (result, {"status": "DELIVERY_FAILED"})]
    for b_result, b_delivery in cases:
        assert run(b_result, b_delivery, data_root=data, state_root=state, evidence_root=tmp_path, report_root=tmp_path)["status"] == "C_NOT_STARTED_B_FORMAL_GATE_INCOMPLETE"
    (state / "data" / "delivery" / "daily_delivery_20260922.json").unlink()
    assert run(result, delivery, data_root=data, state_root=state, evidence_root=tmp_path,
               report_root=tmp_path)["status"] == "C_NOT_STARTED_B_FORMAL_GATE_INCOMPLETE"


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
@pytest.mark.parametrize("fail_push", [False, True])
def test_post_b_publishes_only_c_files_with_real_git_readback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                               matched: bool, fail_push: bool) -> None:
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
    monkeypatch.setattr("run_c_daily_watchlist._run_c_child",
                        lambda command: {"status": "C_DAILY_RESEARCH_REPORT_READY", "report": report})
    if fail_push:
        import run_c_daily_watchlist as runner
        original_git = runner._git
        def reject_push(root, *args, **kwargs):
            if args and args[0] == "push":
                raise subprocess.CalledProcessError(1, ["git", *args])
            return original_git(root, *args, **kwargs)
        monkeypatch.setattr(runner, "_git", reject_push)
    formal_paths = [Path(result["input_package"]["path"]), Path(result["watchlist"]["path"]),
                    Path(result["daily_close_bundle"]["dated_html"]),
                    state / "data" / "delivery" / "daily_delivery_20260922.json"]
    original = {str(path): path.read_bytes() for path in formal_paths}
    started = datetime(2026, 9, 24, 11, tzinfo=timezone.utc)
    outcome = post_b(b_result=b_result, delivery_result=delivery_result, data_root=tmp_path / "data",
                     state_root=state, evidence_root=tmp_path / "evidence", report_root=tmp_path / "rendered",
                     started_at=started, now=started + timedelta(minutes=1), schedule_cron="17 10 * * 1-5")
    assert outcome["status"] == ("C_REPORT_PUBLISH_FAILED_B_UNCHANGED" if fail_push else "C_DAILY_REPORT_PUBLISHED")
    if not fail_push:
        assert outcome["matched_stock_count"] == (1 if matched else 0)
        assert all(path.startswith("data/reports/c_daily/") for path in outcome["paths"])
    assert {str(path): path.read_bytes() for path in formal_paths} == original
    assert not (state / "data" / "reports" / "latest.html").exists()
    if not fail_push:
        assert subprocess.run(["git", "--git-dir", str(remote), "show", "runtime-state:" + outcome["paths"][-2]],
                              check=True, capture_output=True).stdout == (state / outcome["paths"][-2]).read_bytes()


def test_post_b_c_failure_and_publish_failure_leave_b_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result, delivery = _b_result(tmp_path)
    b_result = tmp_path / "b-result.json"
    delivery_result = tmp_path / "delivery-result.json"
    b_result.write_text(json.dumps(result), encoding="utf-8")
    delivery_result.write_text(json.dumps(delivery), encoding="utf-8")
    started = datetime(2026, 9, 24, 11, tzinfo=timezone.utc)
    kwargs = dict(b_result=b_result, delivery_result=delivery_result, data_root=tmp_path / "data",
                  state_root=tmp_path / "runtime-state", evidence_root=tmp_path / "evidence",
                  report_root=tmp_path / "rendered", started_at=started,
                  now=started + timedelta(minutes=1), schedule_cron="17 10 * * 1-5")
    monkeypatch.setattr("run_c_daily_watchlist._run_c_child", lambda command: {"status": "C_FAILED_B_UNCHANGED"})
    assert post_b(**kwargs)["status"] == "C_FAILED_B_UNCHANGED"
    def timeout(command):
        raise subprocess.TimeoutExpired(command, 360)
    monkeypatch.setattr("run_c_daily_watchlist._run_c_child", timeout)
    assert post_b(**kwargs)["status"] == "C_TIMEOUT_B_UNCHANGED"
    monkeypatch.setattr("run_c_daily_watchlist._run_c_child",
                        lambda command: {"status": "C_DAILY_RESEARCH_REPORT_READY", "report": {"status": "C_DAILY_REPORT_READY"}})
    assert post_b(**kwargs)["status"] == "C_REPORT_PUBLISH_FAILED_B_UNCHANGED"
    assert delivery["status"] == "DELIVERY_SUCCESS"


def test_workflow_c_gate_is_after_all_b_success_steps() -> None:
    import yaml
    workflow = yaml.safe_load((Path(__file__).resolve().parents[1] / ".github/workflows/daily_t_close.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["daily"]["steps"]
    ids = {step.get("id"): index for index, step in enumerate(steps) if step.get("id")}
    assert ids["b_production"] < ids["b_output_validation"] < ids["b_state_push"]
    assert ids["b_state_push"] < ids["b_delivery"] < ids["b_receipt_persist"] < ids["delivery_health"] < ids["c_daily"]
    c_step = steps[ids["c_daily"]]
    condition = c_step["if"]
    for gate in ("b_production", "b_output_validation", "b_state_push", "b_delivery",
                 "b_receipt_persist", "delivery_health"):
        assert f"steps.{gate}.outcome == 'success'" in condition
    assert "ENABLE_C_DAILY_RESEARCH_WATCHLIST_V1" in condition
    assert "timeout --signal=TERM --kill-after=10s 600s" in c_step["run"]
    assert "C status:" in c_step["run"] and "Formal B delivery health: SUCCESS" in c_step["run"]


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
    assert "C 每日研究名单" in Path(report["path"]).read_text(encoding="utf-8")
    assert report["html_bytes"] < 2_000_000
    assert hashlib.sha256(persisted.path.read_bytes()).hexdigest() == sha
