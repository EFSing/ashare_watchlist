from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
import gzip
import json
from pathlib import Path
import subprocess
import sys

import pytest

import c_pre_outcome_design as frozen
import c_rule_funnel_capture as funnel
from c_b_input_adapter import _b_kline_sha, _price_only_observation
from c_daily_watchlist import build_watchlist, render_html
from test_c_daily_watchlist import _init_c_state_repo
from test_c_pre_outcome_design import _synthetic_entry_bars


DAY = "2026-11-04"
BJT = timezone(timedelta(hours=8))


def _bars() -> list[dict]:
    original = _synthetic_entry_bars()
    bars = [{"date": "", "open": 80 + i * .5, "close": 80 + i * .5,
             "high": 81 + i * .5, "low": 79 + i * .5, "volume": 100.0} for i in range(38)] + original
    current = date.fromisoformat(DAY)
    for row in reversed(bars):
        while current.weekday() >= 5:
            current -= timedelta(days=1)
        row["date"] = current.isoformat()
        current -= timedelta(days=1)
    return bars


def _inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    bars = _bars()
    kline = {"symbol": "600000", "bars": bars,
             "normalized_data_sha256": _b_kline_sha({"symbol": "600000", "bars": bars})}
    package = {"display_names": {"600000": "浦发银行"}, "generation_input_manifest": {
        "universe": {"symbols": ["600000"]}, "stock_klines": [kline]}}
    package_path = tmp_path / "package.json"
    package_path.write_bytes(funnel.canonical(package))
    package_sha = funnel.sha(package_path.read_bytes())
    observation = {"schema_version": "C_B_FROZEN_INPUT_READER_V1", "status": "PRICE_OBSERVATION_VOLUME_UNVERIFIED",
                   "source": {"target_date": DAY, "b_package_actual_sha256": package_sha,
                              "handoff": {"mode": "SAME_RUNNER_READ_ONLY"},
                              "b_acquired_at_bjt": DAY + "T17:17:00+08:00", "c_read_at_bjt": DAY + "T18:30:00+08:00"},
                   "observations": [{"symbol": "600000", "name": "浦发银行", "st_status": "ELIGIBLE",
                                     "b_kline_sha256": kline["normalized_data_sha256"], "rules": {
                                         r: _price_only_observation("600000", DAY, bars, r) for r in funnel.RULES}}]}
    c_root = tmp_path / "c-input"
    c_root.mkdir()
    monkeypatch.setattr(funnel, "_safe_output_root", lambda: c_root)
    record = c_root / "observed.json"
    record.write_bytes(funnel.canonical(observation))
    prepared = {"c_result": {"observation": {"record": record.name, "record_sha256": funnel.sha(record.read_bytes())}}}
    state = tmp_path / "runtime-state"
    manifest_path = state / "data/reports/c_daily/20261104/manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest = {"signal_date": DAY, "package_sha256": package_sha,
                "schema_version": "C_DAILY_RESEARCH_WATCHLIST_V1", "c_status": "C_SUCCESS_WITH_MATCHES",
                "matched_by_rule": {r: sum(item["rules"][r]["price_structure_match"] for item in observation["observations"])
                                     for r in funnel.RULES}}
    manifest_path.write_bytes(funnel.canonical(manifest))
    published = {"status": "C_DAILY_REPORT_PUBLISHED", "signal_date": DAY, "package_sha256": package_sha,
                 "manifest_sha256": funnel.sha(manifest_path.read_bytes())}
    b_result = {"as_of_date": DAY, "input_package": {"path": str(package_path), "file_sha256": package_sha}}
    return b_result, prepared, published, state, package, observation


def _capture(inputs, tmp_path: Path, **kwargs):
    b, prepared, published, state, *_ = inputs
    return funnel.capture(b, prepared, published, state_root=state, output_root=tmp_path / "output",
                          start_date=DAY, now=datetime(2026, 11, 4, 19, tzinfo=BJT), **kwargs)


def test_exact_c_results_rules_and_report_bytes_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    inputs = _inputs(tmp_path, monkeypatch)
    *_, package, observation = inputs
    before = deepcopy((package, observation))
    watchlist = build_watchlist(observation)
    html = render_html(watchlist)
    assert watchlist["matched_by_rule"] == {"BALANCED_A": 1, "CONSERVATIVE_B": 1}
    result = _capture(inputs, tmp_path)
    assert result["status"] == "C_FUNNEL_STAGED_READBACK_VERIFIED"
    assert (package, observation) == before
    assert build_watchlist(observation) == watchlist
    assert render_html(build_watchlist(observation)) == html
    assert [(c.trend_window, c.minimum_up_close_fraction, c.pivot_radius,
             c.minimum_pivot_separation, c.maximum_pullback_sessions,
             c.shallow_depth_min, c.shallow_depth_max, c.rebound_size_min,
             c.rebound_size_max, c.confirmation_close_location) for c in frozen.RULE_CANDIDATES.values()] == [
                 (60, .55, 2, 3, 20, .03, .12, .02, .08, .60),
                 (90, .60, 3, 4, 25, .04, .15, .02, .10, .60)]
    summary = json.loads((inputs[3] / result["paths"][1]).read_bytes())
    assert summary["rules"] == {r: asdict(frozen.RULE_CANDIDATES[r]) for r in funnel.RULES}
    assert summary["complete_diagnostic_count"] == 2
    assert summary["by_rule"]["BALANCED_A"]["funnel_counts"]["F8"] == 1
    records = [json.loads(line) for line in gzip.decompress((inputs[3] / result["paths"][0]).read_bytes()).splitlines()]
    assert len(records) == 2
    keys = set()
    def collect(value):
        if isinstance(value, dict):
            keys.update(value)
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)
    collect([summary, records])
    assert not any("score" in key.lower() or "rank" in key.lower() for key in keys)
    assert records[0]["F2"]["positive_slope"] is True
    assert records[0]["F2"]["up_close_fraction_margin"] > 0


def test_deterministic_idempotent_same_date_and_append_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    inputs = _inputs(tmp_path, monkeypatch)
    first = _capture(inputs, tmp_path)
    before = {p: (inputs[3] / p).read_bytes() for p in first["paths"]}
    assert _capture(inputs, tmp_path) == first
    assert before == {p: (inputs[3] / p).read_bytes() for p in first["paths"]}
    target = inputs[3] / first["paths"][0]
    target.write_bytes(b"different same-date bytes")
    with pytest.raises(ValueError, match="IMMUTABILITY_CONFLICT"):
        _capture(inputs, tmp_path)
    assert target.read_bytes() == b"different same-date bytes"


def test_real_git_remote_readback_and_retry_no_extra_commit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    inputs = _inputs(tmp_path, monkeypatch)
    state, remote = inputs[3], tmp_path / "remote.git"
    _init_c_state_repo(state, remote)
    before = (state / "data/reports/c_daily/20261104/manifest.json").read_bytes()
    staged = _capture(inputs, tmp_path)
    published = funnel.publish(state, staged)
    assert published["status"] == "C_FUNNEL_REMOTE_READBACK_VERIFIED"
    assert funnel.publish(state, _capture(inputs, tmp_path))["runtime_state_sha"] == published["runtime_state_sha"]
    assert (state / "data/reports/c_daily/20261104/manifest.json").read_bytes() == before
    for path in staged["paths"]:
        raw = subprocess.run(["git", "--git-dir", str(remote), "show", "runtime-state:" + path],
                             check=True, capture_output=True).stdout
        assert raw == (state / path).read_bytes()
    (state / staged["paths"][0]).write_bytes(b"corrupted")
    with pytest.raises((ValueError, gzip.BadGzipFile)):
        funnel.verify_artifacts(state, Path(staged["paths"][1]))


def test_future_bar_is_not_used_and_missing_feature_stays_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    *_, package, observation = _inputs(tmp_path, monkeypatch)
    package["generation_input_manifest"]["stock_klines"][0]["bars"].append({
        "date": "2026-11-05", "open": 999, "high": 999, "low": 999, "close": 999, "volume": 999})
    rows = funnel.build_rows(package, observation)
    assert all(row["diagnostic_status"] == "PARTIAL_UNVERIFIED" for row in rows)
    assert rows[0]["F2"] is None
    assert rows[0]["F8"]["price_structure_match"] is True  # original result retained, never recalculated on future bars
    package["generation_input_manifest"]["stock_klines"][0]["bars"].pop()
    original = observation["observations"][0]["rules"]["CONSERVATIVE_B"]
    original["price_structure_observation"]["trend"].pop("positive_slope")
    row = funnel.build_rows(package, observation)[1]
    assert row["F2"]["positive_slope"] is None
    assert row["diagnostic_status"] == "PARTIAL_UNVERIFIED"
    assert row["near_miss_failed_condition_count"] is None


@pytest.mark.parametrize("kind", ["stale_day", "sha", "not_published", "backfill", "before_close"])
def test_capture_requires_same_day_exact_consumed_input(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str):
    inputs = _inputs(tmp_path, monkeypatch)
    b, prepared, published, state, *_ = inputs
    now = datetime(2026, 11, 4, 19, tzinfo=BJT)
    if kind == "stale_day":
        now += timedelta(days=1)
    elif kind == "before_close":
        now = now.replace(hour=14)
    elif kind == "sha":
        b["input_package"]["file_sha256"] = "0" * 64
    elif kind == "backfill":
        b["acquisition_timing"] = "AUTHORIZED_WEEKEND_BACKFILL"
    else:
        published["status"] = "C_FAILED"
    with pytest.raises(ValueError):
        funnel.capture(b, prepared, published, state_root=state, output_root=tmp_path / "output", start_date=DAY, now=now)
    assert not (state / funnel.RELATIVE_ROOT).exists()


def test_all_four_confirmation_subconditions_and_near_miss():
    bars = _bars()
    bars[-1]["open"] = bars[-1]["close"]
    original = _price_only_observation("600000", DAY, bars, "BALANCED_A")
    assert original["price_structure_match"] is False
    row = funnel.diagnose(frozen.validate_ohlcv_bars(bars), original, "BALANCED_A")
    assert row["F6"]["confirmation_fail_count"] == 1
    assert row["F6"]["failed_subconditions"] == ["positive_body"]
    assert row["near_miss_classes"] == ["ONE_CONFIRMATION_SUBCONDITION"]
    assert row["near_miss_failed_condition_count"] == 1
    assert row["F7"]["entry_support_ok"] is True


@pytest.mark.parametrize("kind", ["age", "depth", "no_high", "size"])
def test_structure_failure_decomposition_preserves_frozen_status(monkeypatch: pytest.MonkeyPatch, kind: str):
    bars = _bars()
    # Isolate one confirmed pair, while using the real frozen selection/return logic.
    low1, low2, peak, rebound = 95, 100, 90, 104
    bars[low1]["low"], bars[low2]["low"], bars[peak]["high"], bars[rebound]["high"] = 123., 124., 135., 130.
    if kind == "age":
        peak = 83
        bars[peak]["high"] = 135.
    if kind == "depth":
        bars[peak]["high"] = 160.
    if kind == "size":
        bars[rebound]["high"] = 150.
    highs = [peak] if kind == "no_high" else [peak, rebound]
    monkeypatch.setattr(frozen, "_pivot_indices", lambda values, radius, *, low: [low1, low2] if low else highs)
    original = _price_only_observation("600000", DAY, bars, "BALANCED_A")
    expected = "PULLBACK_DEPTH_OUTSIDE_CANDIDATE" if kind in {"age", "depth"} else "NO_CONFIRMED_REBOUND_HIGH"
    assert original["price_structure_observation"]["structure"]["status"] == expected
    row = funnel.diagnose(frozen.validate_ohlcv_bars(bars), original, "BALANCED_A")
    context = next(funnel.iter_pair_diagnostics(row))
    assert row["F3"]["exact_failure_status"] == expected
    assert context["peak_age_failed"] is (kind == "age")
    assert context["depth_failed"] is (kind == "depth")
    if kind == "no_high":
        assert context["rebound_status"] == "NO_CONFIRMED_REBOUND_HIGH"
        assert context["rebound_size"] is None
    elif kind == "size":
        assert context["rebound_status"] == "REBOUND_SIZE_OUTSIDE_CANDIDATE"
        assert context["rebound_upper_margin"] < 0


def test_conservative_slope_fraction_joint_and_overlapping_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    *_, package, observation = _inputs(tmp_path, monkeypatch)
    template = funnel.build_rows(package, observation)[1]
    rows = []
    for slope, fraction in [(False, False), (False, True), (True, False), (True, True)]:
        row = deepcopy(template)
        row["F2"].update(positive_slope=slope, up_close_fraction_ok=fraction)
        rows.append(row)
    result = funnel.aggregate(rows)["CONSERVATIVE_B"]
    assert result["condition_failure_counts"]["positive_slope"] == 2
    assert result["condition_failure_counts"]["up_close_fraction_ok"] == 2
    assert result["slope_up_close_fraction_joint"] == {
        "both_failed": 1, "slope_only_failed": 1, "up_close_fraction_only_failed": 1, "missing": 0}


def test_compact_pairs_keep_all_failures_and_exact_context_values():
    bars = frozen.validate_ohlcv_bars(_bars())
    for rule in funnel.RULES:
        original = _price_only_observation("600000", DAY, bars, rule)
        row = funnel.diagnose(bars, original, rule)
        _, _, expanded = funnel._pair_contexts(bars, frozen.RULE_CANDIDATES[rule])
        decoded = list(funnel.iter_pair_diagnostics(json.loads(funnel.canonical(row))))
        assert len(expanded) == len(decoded)
        for before, after in zip(expanded, decoded):
            assert all(before[key] == after[key] for key in before if key not in {"failed_conditions", "missing_conditions", "failed_condition_count"})


@pytest.mark.parametrize("failed_stage", ["write", "publish"])
def test_recorder_write_or_publish_failure_cannot_change_c_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys, failed_stage: str):
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    inputs = _inputs(tmp_path, monkeypatch)
    b, prepared, published, state, _, observation = inputs
    paths = []
    for name, value in (("b", b), ("prepared", prepared), ("published", published)):
        path = tmp_path / (name + ".json")
        path.write_bytes(funnel.canonical(value))
        paths.append(path)
    before = [path.read_bytes() for path in paths]
    report = render_html(build_watchlist(observation))
    monkeypatch.setattr(sys, "argv", ["capture", "--b-result", str(paths[0]), "--prepared-result", str(paths[1]),
                                     "--published-result", str(paths[2]), "--state-root", str(state)])
    monkeypatch.setenv("ENABLE_C_RULE_FUNNEL_CAPTURE_V1", "true")
    monkeypatch.setenv("C_RULE_FUNNEL_CAPTURE_START_DATE", DAY)
    original_capture = funnel.capture
    monkeypatch.setattr(funnel, "capture", lambda *args, **kwargs: original_capture(
        *args, **kwargs, now=datetime(2026, 11, 4, 19, tzinfo=BJT)))
    def fail(*args, **kwargs):
        raise OSError("synthetic recording failure")
    monkeypatch.setattr(funnel, "_copy_missing" if failed_stage == "write" else "publish", fail)
    assert funnel.main() == 0
    assert json.loads(capsys.readouterr().out)["status"] == "C_FUNNEL_RECORDING_FAILED_C_UNCHANGED"
    assert before == [path.read_bytes() for path in paths]
    assert report == render_html(build_watchlist(observation))


def test_checkpoint_prevents_further_capture_and_counts_real_run_gaps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    inputs = _inputs(tmp_path, monkeypatch)
    b, prepared, published, state, *_ = inputs
    start = "2026-09-01"
    previous = state / funnel.RELATIVE_ROOT / "daily/20261103.json"
    previous.parent.mkdir(parents=True)
    previous.write_bytes(funnel.canonical({"start_date": start,
        "rule_source_sha256": funnel.sha(Path(frozen.__file__).read_bytes()),
        "complete_diagnostic_count": 20000, "checkpoint": {"status": "REVIEW_REQUIRED"}}))
    result = funnel.capture(b, prepared, published, state_root=state, output_root=tmp_path / "output",
                            start_date=start, now=datetime(2026, 11, 4, 19, tzinfo=BJT))
    assert result["status"] == "C_FUNNEL_CHECKPOINT_REACHED_NO_FURTHER_CAPTURE"
    assert not (state / funnel.RELATIVE_ROOT / "details").exists()
    previous.unlink()  # test-owned synthetic summary, not project evidence
    current, count = date(2026, 9, 1), 0
    while count < 20:
        if not funnel.default_calendar().is_trading_day(current):
            current += timedelta(days=1)
            continue
        path = state / "data/reports/c_daily" / current.strftime("%Y%m%d") / "manifest.json"
        path.parent.mkdir(parents=True)
        path.write_bytes(funnel.canonical({"signal_date": current.isoformat(), "schema_version": "C_DAILY_RESEARCH_WATCHLIST_V1",
                                          "c_status": "C_SUCCESS_NO_MATCH"}))
        current += timedelta(days=1)
        count += 1
    result = funnel.capture(b, prepared, published, state_root=state, output_root=tmp_path / "output",
                            start_date=start, now=datetime(2026, 11, 4, 19, tzinfo=BJT))
    assert result["status"] == "C_FUNNEL_HARD_MAXIMUM_REACHED_NO_FURTHER_CAPTURE"
    assert not (state / funnel.RELATIVE_ROOT / "details").exists()


@pytest.mark.parametrize("days,count,status", [(14, 25000, "COLLECTING"), (15, 19999, "COLLECTING"),
                                              (15, 20000, "REVIEW_REQUIRED"), (20, 0, "REVIEW_REQUIRED")])
def test_checkpoint_rule(days: int, count: int, status: str):
    assert funnel.checkpoint(days, count)["status"] == status


def test_cli_failure_and_disabled_capture_are_non_blocking(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["capture", "--b-result", str(tmp_path / "absent"),
                                     "--prepared-result", "absent", "--published-result", "absent", "--state-root", str(tmp_path)])
    monkeypatch.delenv("ENABLE_C_RULE_FUNNEL_CAPTURE_V1", raising=False)
    assert funnel.main() == 0
    assert json.loads(capsys.readouterr().out)["status"] == "C_FUNNEL_DISABLED"
    monkeypatch.setenv("ENABLE_C_RULE_FUNNEL_CAPTURE_V1", "true")
    assert funnel.main() == 0
    assert json.loads(capsys.readouterr().out)["status"] == "C_FUNNEL_RECORDING_FAILED_C_UNCHANGED"


def test_fail_soft_workflow_after_publication_keeps_existing_scheduler_and_gates():
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/daily_t_close.yml").read_text(encoding="utf-8")
    step = workflow.split("      - name: Record prospective C rule funnel", 1)[1].split("      - name:", 1)[0]
    assert workflow.index("- name: Publish bounded C research") < workflow.index("- name: Record prospective C rule funnel")
    assert "steps.c_daily.outcome == 'success'" in step
    assert "vars.ENABLE_C_RULE_FUNNEL_CAPTURE_V1 == 'true'" in step
    assert "continue-on-error: true" in step and "timeout-minutes: 3" in step
    assert "C_RULE_FUNNEL_CAPTURE_START_DATE" in step
