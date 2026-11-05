"""Prospective membership, causality, immutability and delivery isolation."""
from copy import deepcopy
from datetime import date, datetime, time, timedelta
import json
from pathlib import Path
import subprocess

import pytest

import b_structure_volume_shadow as shadow
from b_breakout_retest_v1_1 import evaluate_candidate
from cloud_runtime_state import _is_allowlisted_data_relative
from trading_calendar import TradingCalendar
from volume_observation import build_volume_observation_store, calculate_stock_volume_observation
from watchlist_schema import load_watchlist, validate_watchlist
from test_a_platform_breakout import SYMBOL, _manifest
from test_b_breakout_retest_v1_1 import _b_bars
from test_b_prospective_observation import _candidate
from test_c_daily_watchlist import _init_c_state_repo

DAY = "2026-11-05"
CAL = TradingCalendar(holidays=set(), session_close_time=time(15))
GENERATION_COMMIT = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=shadow.SOURCE_ROOT).decode().strip()


def _bars(day=DAY):
    bars = deepcopy(_b_bars())
    first = date.fromisoformat(day) - timedelta(days=len(bars) - 1)
    for i, bar in enumerate(bars):
        bar["date"] = (first + timedelta(days=i)).isoformat()
    # Give the frozen structure proxy a valid 0.5 transition, without altering
    # the original breakout or qualification. Alternate up/down pullback days.
    for i in range(253, 259):
        bars[i].update(close=10.25 if i % 2 else 10.1, low=9.7, high=10.35,
                       volume=80.0 if i % 2 else 100.0)
    bars[-1].update(close=10.4, high=10.5, low=9.7)
    return bars


def _inputs(tmp_path, *, day=DAY, codes=("600000",), missing=(), bars=None):
    source = tmp_path / day
    source.mkdir(parents=True, exist_ok=True)
    watch = {"date": day, "mode": "close", "market_env": {"level": "B"}, "sectors": [],
             "strategy_version": shadow.STRATEGY_VERSION,
             "candidates": [dict(_candidate(day), code=code) for code in codes]}
    watch = validate_watchlist(watch)
    watch_path = source / f"watchlist_{day.replace('-', '')}.json"
    watch_path.write_bytes(shadow.canonical(watch))
    manifest = {"status": "READY_FOR_STRATEGY_EVALUATION", "signal_date": day,
                "earliest_execution_date": shadow._next_horizon_date(day, 1, CAL),
                "run_context": {"mode": "close", "historical": False},
                "stock_klines": [{"symbol": code, "bars": deepcopy(bars or _bars(day))}
                                 for code in codes if code not in missing]}
    run = {"status": "SUCCESS", "strategy_version": shadow.STRATEGY_VERSION,
           "strategy_spec_sha256": shadow.STRATEGY_SPEC_SHA256, "signal_date": day, "as_of_date": day,
           "earliest_execution_date": manifest["earliest_execution_date"], "input_manifest": manifest,
           "generation_fingerprint": "a" * 64, "input_fingerprint": "b" * 64,
           "output": {"file_sha256": shadow.sha(watch_path.read_bytes())}}
    run_path = source / "run.json"
    run_path.write_bytes(shadow.canonical(run))
    # Package and canonical generation are different fingerprint schemas.
    package = {"generation_input_manifest": manifest, "generation_fingerprint": "c" * 64,
               "candidate": {"strategy_version": shadow.STRATEGY_VERSION, "spec_sha256": shadow.STRATEGY_SPEC_SHA256},
               "provenance": {"retrieved_at_bjt": day + "T17:17:00+08:00"}}
    package_path = source / "package.json"
    package_path.write_bytes(shadow.canonical(package))
    report_path = source / "volume.json"
    report_path.write_bytes(shadow.canonical(build_volume_observation_store(watch["candidates"], manifest, day)))
    b = {"status": "T_CLOSE_EVIDENCE_PACKAGE_AND_WATCHLIST_PERSISTED", "as_of_date": day,
         "code_git_sha": GENERATION_COMMIT, "acquisition_timing": "SAME_CALENDAR_DATE",
         "input_package": {"path": str(package_path), "file_sha256": shadow.sha(package_path.read_bytes())},
         "watchlist": {"path": str(watch_path), "file_sha256": shadow.sha(watch_path.read_bytes()),
                       "run_manifest_path": str(run_path), "candidate_count": len(codes)},
         "volume_observations": {"path": str(report_path), "file_sha256": shadow.sha(report_path.read_bytes())}}
    state = tmp_path / "runtime-state"
    (state / "data/checkpoints").mkdir(parents=True, exist_ok=True)
    (state / "data" / watch_path.name).write_bytes(watch_path.read_bytes())
    checkpoint = {"schema_version": "DAILY_LIGHTWEIGHT_CLOUD_CHECKPOINT_V1", "list_date": day,
                  "strategy_version": shadow.STRATEGY_VERSION, "code_git_sha": GENERATION_COMMIT,
                  "created_at_bjt": day + "T18:00:00+08:00", "watchlist": {"sha256": b["watchlist"]["file_sha256"]}}
    (state / "data/checkpoints" / f"daily_checkpoint_{day.replace('-', '')}.json").write_bytes(shadow.canonical(checkpoint))
    return b, {"status": "DELIVERY_SUCCESS", "report_date": day}, state


def _capture(inputs, tmp_path, *, start=DAY):
    b, delivery, state = inputs
    return shadow.capture(b, delivery, state_root=state, output_root=tmp_path / "output",
                          start_date=start, now=datetime.fromisoformat(b["as_of_date"] + "T19:00:00+08:00"), calendar=CAL)


def test_all_qualified_retained_exact_volume_and_formal_semantic_byte_parity(tmp_path, monkeypatch):
    import requests
    monkeypatch.setattr(requests.sessions.Session, "request", lambda *a, **k: pytest.fail("provider/network request"))
    inputs = _inputs(tmp_path, codes=("600001", "600000", "600002"), missing=("600002",))
    b, _, state = inputs
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.json")}
    qualified = evaluate_candidate(_manifest(_b_bars(), sector_evidence={}), SYMBOL)
    staged = _capture(inputs, tmp_path)
    receipt, observed = shadow.verify_artifacts(state, DAY)
    rows = observed["rows"]
    assert [r["code"] for r in rows] == ["600001", "600000", "600002"]
    assert all(r["formal_b_qualified"] for r in rows)
    assert rows[0]["is_w2w3_transition"]
    assert rows[2]["structure"]["state"] == shadow.INVALID
    assert rows[2]["volume"]["down_volume_share"] is None
    assert rows[0]["volume"] == calculate_stock_volume_observation(_bars(), DAY, code="600001")
    assert all(before[p] == p.read_bytes() for p in before)
    assert evaluate_candidate(_manifest(_b_bars(), sector_evidence={}), SYMBOL) == qualified
    assert staged["rows"] == 3 == receipt["observations"]["rows"]
    assert receipt["outcome_accessed"] is False
    # No copied canonical candidate Score, ranking, priority labels or raw bars.
    keys = set()
    def collect(value):
        if isinstance(value, dict):
            keys.update(value)
            for v in value.values():
                collect(v)
        elif isinstance(value, list):
            for v in value:
                collect(v)
    collect(observed)
    assert not keys.intersection({"score", "volume_quality", "rank", "priority", "bars", "open", "target", "stop"})


def test_b_html_is_byte_identical_before_and_after_capture(tmp_path):
    from data_paths import DataPaths
    from render_daily_close_html import build_report_model, render_html
    inputs = _inputs(tmp_path)
    paths = DataPaths(inputs[2] / "data")
    now = datetime.fromisoformat(DAY + "T19:00:00+08:00")
    before = render_html(build_report_model(DAY, paths=paths, calendar=CAL, generated_at=now))
    _capture(inputs, tmp_path)
    assert render_html(build_report_model(DAY, paths=paths, calendar=CAL, generated_at=now)) == before


def test_actual_package_and_formal_generation_contract_with_synthetic_providers(tmp_path):
    from development_candidate import B_STRATEGY_BINDING, DevelopmentCandidateStore
    from live_acquisition import persist_live_input_package
    from t_close_runner import _capture_volume_observations
    from test_live_acquisition import FakeHiThink, _acquire
    original_bars = _b_bars()
    for original, dated in zip(original_bars, _bars()):
        original["date"] = dated["date"]
    bars = [[b["date"], b["open"], b["close"], b["high"], b["low"], b["volume"]] for b in original_bars]
    package = _acquire(as_of_date=DAY, now_bjt=DAY + "T17:17:00+08:00", calendar=CAL,
                       hithink_client=FakeHiThink(bars=bars, index_bars=bars),
                       stock_bar_count=260, index_bar_count=260)
    root = tmp_path / "formal"
    persisted = persist_live_input_package(package, root)
    result = DevelopmentCandidateStore(root).generate(package.generation_input_manifest,
                 names=package.display_names, market_env=package.market_env,
                 strategy_binding=B_STRATEGY_BINDING, input_provenance=package.provenance)
    assert result.candidate_count == 1
    run = json.loads(result.run_manifest_path.read_bytes())
    assert run["generation_fingerprint"] != package.generation_fingerprint
    original = {p: p.read_bytes() for p in root.rglob("*.json")}
    volume = _capture_volume_observations(package, result, root, weekend_backfill=False)
    b = {"status": "T_CLOSE_EVIDENCE_PACKAGE_AND_WATCHLIST_PERSISTED", "as_of_date": DAY,
         "code_git_sha": GENERATION_COMMIT,
         "input_package": {"path": str(persisted.path), "file_sha256": persisted.file_sha256},
         "watchlist": {"path": str(result.output_path), "file_sha256": result.output_sha256,
                       "candidate_count": result.candidate_count, "run_manifest_path": str(result.run_manifest_path)},
         "volume_observations": volume}
    fixture = _inputs(tmp_path / "state-fixture")
    state = fixture[2]
    (state / "data/watchlist_20261105.json").write_bytes(result.output_path.read_bytes())
    path = state / "data/checkpoints/daily_checkpoint_20261105.json"
    meta = json.loads(path.read_bytes())
    meta["watchlist"]["sha256"] = result.output_sha256
    path.write_bytes(shadow.canonical(meta))
    staged = _capture((b, fixture[1], state), tmp_path)
    assert staged["rows"] == 1
    receipt, _ = shadow.verify_artifacts(state, DAY)
    assert receipt["package_generation_fingerprint"] == package.generation_fingerprint
    assert receipt["generation_fingerprint"] == run["generation_fingerprint"]
    assert all(p.read_bytes() == raw for p, raw in original.items())


def test_coordinates_are_independent_field_specific_and_never_force_small_cross_section():
    rows = [{"is_w2w3_transition": True, "volume": dict(zip(shadow.FIELDS, values))} for values in
            [(0.1, 1.0, None), (0.2, 2.0, 0.8), (0.3, 3.0, 1.2)]]
    shadow.add_coordinates(rows)
    assert [r["coordinates"][shadow.FIELDS[0]]["bucket"] for r in rows] == ["LOW", "MID", "HIGH"]
    assert rows[0]["coordinates"][shadow.FIELDS[0]]["cross_section_n"] == 3
    assert rows[1]["coordinates"][shadow.FIELDS[2]]["status"] == "INSUFFICIENT_CROSS_SECTION"
    assert rows[0]["coordinates"][shadow.FIELDS[2]]["status"] == "FEATURE_UNAVAILABLE"
    # Adding a non-transition extreme cannot change any primary coordinate.
    expected = deepcopy(rows)
    rows.append({"is_w2w3_transition": False, "volume": dict.fromkeys(shadow.FIELDS, 999)})
    shadow.add_coordinates(rows)
    assert rows[:3] == expected
    assert all(c["status"] == "NOT_PRIMARY_COHORT" for c in rows[-1]["coordinates"].values())
    ties = [{"is_w2w3_transition": True, "volume": dict.fromkeys(shadow.FIELDS, 1.0)} for _ in range(4)]
    shadow.add_coordinates(ties)
    assert len({r["coordinates"][shadow.FIELDS[0]]["percentile"] for r in ties}) == 1
    assert {r["coordinates"][shadow.FIELDS[0]]["bucket"] for r in ties} == {"MID"}


def test_empty_day_and_partial_features_are_recorded_without_selection(tmp_path):
    inputs = _inputs(tmp_path, codes=())
    assert _capture(inputs, tmp_path)["rows"] == 0
    receipt, rows = shadow.verify_artifacts(inputs[2], DAY)
    assert rows["rows"] == [] and receipt["checkpoint"]["real_b_signal_sessions"] == 1
    bars = _bars()
    for i in range(253, 259):
        bars[i]["close"] = 10.1
    candidate = load_watchlist(_inputs(tmp_path / "partial")[0]["watchlist"]["path"])["candidates"][0]
    row = shadow.observe(candidate, bars, DAY)
    assert row["volume"]["down_volume_share"] is not None
    assert row["volume"]["up_down_volume_ratio"] is None
    assert row["volume"]["missing_reason"]["up_down_volume_ratio"] == "NO_UP_OR_DOWN_DAY"


def test_deterministic_idempotency_and_same_date_conflict_no_overwrite(tmp_path):
    inputs = _inputs(tmp_path)
    first = _capture(inputs, tmp_path)
    assert _capture(inputs, tmp_path) == first
    target = inputs[2] / first["paths"][0]
    raw = target.read_bytes()
    target.write_bytes(b"conflict")
    with pytest.raises(ValueError, match="IMMUTABILITY_CONFLICT"):
        _capture(inputs, tmp_path)
    assert target.read_bytes() == b"conflict"
    target.write_bytes(raw)
    receipt = inputs[2] / first["paths"][1]
    receipt.write_bytes(receipt.read_bytes().replace(b'"outcome_accessed":false', b'"outcome_accessed":true'))
    with pytest.raises(ValueError, match="RECEIPT_HASH"):
        shadow.verify_artifacts(inputs[2], DAY)


@pytest.mark.parametrize("failure", ["package_sha", "run_output", "report_value", "backfill", "not_delivered", "prior_day", "pre_close", "bad_start", "generation"])
def test_source_or_time_mismatch_refuses_whole_day(tmp_path, failure):
    inputs = _inputs(tmp_path)
    b, delivery, state = inputs
    now = datetime.fromisoformat(DAY + "T19:00:00+08:00")
    start = DAY
    if failure == "package_sha":
        b["input_package"]["file_sha256"] = "0" * 64
    elif failure == "run_output":
        path = Path(b["watchlist"]["run_manifest_path"])
        payload = json.loads(path.read_bytes())
        payload["output"]["file_sha256"] = "0" * 64
        path.write_bytes(shadow.canonical(payload))
    elif failure == "report_value":
        path = Path(b["volume_observations"]["path"])
        payload = json.loads(path.read_bytes())
        next(iter(payload["observations"].values()))["observation"]["down_volume_share"] = .999
        path.write_bytes(shadow.canonical(payload))
        b["volume_observations"]["file_sha256"] = shadow.sha(path.read_bytes())
    elif failure == "backfill":
        b["acquisition_timing"] = "AUTHORIZED_WEEKEND_BACKFILL"
    elif failure == "not_delivered":
        delivery["status"] = "DELIVERY_FAILED"
    elif failure == "prior_day":
        now -= timedelta(days=1)
    elif failure == "pre_close":
        now = now.replace(hour=14)
    elif failure == "bad_start":
        start = "2026-11-06"
    else:
        b["code_git_sha"] = "8164eede3a04f2ba6d93cc0b4663fe9def98d9f1"
    with pytest.raises((ValueError, RuntimeError, subprocess.CalledProcessError)):
        shadow.capture(b, delivery, state_root=state, output_root=tmp_path / "out", start_date=start, now=now, calendar=CAL)
    assert not (state / shadow.RELATIVE_ROOT).exists()


def test_size_cap_is_atomic_and_never_truncates_candidates(tmp_path, monkeypatch):
    inputs = _inputs(tmp_path, codes=("600000", "600001", "600002"))
    monkeypatch.setattr(shadow, "MAX_FILE_BYTES", 100)
    with pytest.raises(ValueError, match="SIZE_LIMIT"):
        _capture(inputs, tmp_path)
    assert not (inputs[2] / shadow.RELATIVE_ROOT).exists()


def test_episode_repeat_rolling_index_is_one_independent_transition(tmp_path):
    first = _inputs(tmp_path)
    _capture(first, tmp_path)
    bars = _bars()
    bars.pop(0)  # same dated breakout now at index 251 instead of 252
    bars.append(dict(bars[-1], date="2026-11-06"))
    second = _inputs(tmp_path, day="2026-11-06", bars=bars)
    _capture(second, tmp_path)
    r1 = shadow.verify_artifacts(first[2], DAY)[1]["rows"][0]
    r2 = shadow.verify_artifacts(first[2], "2026-11-06")[1]["rows"][0]
    assert r1["episode"]["breakout_episode_id"] != r2["episode"]["breakout_episode_id"]
    assert r1["episode"]["analysis_episode_key"] == r2["episode"]["analysis_episode_key"]
    assert r1["episode"]["first_transition_observation"]
    assert r2["is_w2w3_transition"]
    assert not r2["episode"]["first_observed_signal"]
    assert not r2["episode"]["first_transition_observation"]


def test_early_episode_can_later_supply_first_transition_without_double_count(tmp_path):
    bars = _bars()
    bars[-1]["close"] = 10.1
    first = _inputs(tmp_path, bars=bars)
    _capture(first, tmp_path)
    bars.append(dict(bars[-1], date="2026-11-06", close=10.4, high=10.5))
    later = _inputs(tmp_path, day="2026-11-06", bars=bars)
    _capture(later, tmp_path)
    prior = shadow.verify_artifacts(first[2], DAY)[1]["rows"][0]
    row = shadow.verify_artifacts(first[2], "2026-11-06")[1]["rows"][0]
    assert prior["structure"]["state"] == "EARLY_PULLBACK"
    assert not row["episode"]["first_observed_signal"]
    assert row["episode"]["first_transition_observation"]


def test_future_bar_values_and_forbidden_outcome_paths_never_read(tmp_path):
    class FutureBar(dict):
        def __getitem__(self, key):
            assert key == "date", "future OHLCV read"
            return "2099-01-01"
        def get(self, key, default=None):
            return self[key]
    inputs = _inputs(tmp_path)
    candidate = load_watchlist(inputs[0]["watchlist"]["path"])["candidates"][0]
    row = shadow.observe(candidate, _bars() + [FutureBar()], DAY)
    assert row["structure"]["state"] == shadow.INVALID
    assert all(row["volume"][f] is None for f in shadow.FIELDS)
    with pytest.raises(ValueError, match="FORBIDDEN_INPUT_PATH"):
        shadow._read(tmp_path / "final_oos" / "never-created.json")


@pytest.mark.parametrize("sessions,episodes,status", [(59, 999, "COLLECTING"), (60, 199, "COLLECTING"),
    (60, 200, "REVIEW_REQUIRED_PENDING_OUTCOME_VERIFICATION"),
    (120, 199, "B_STRUCTURE_VOLUME_PROSPECTIVE_EVIDENCE_INSUFFICIENT")])
def test_stricter_checkpoint_never_claims_actual_maturity(sessions, episodes, status):
    result = shadow.checkpoint(sessions, episodes)
    assert result["status"] == status
    assert result["actual_mature_episodes"] is None


def test_recorder_gaps_count_and_calendar_eligibility_without_reading_outcomes(tmp_path, monkeypatch):
    first = _inputs(tmp_path)
    _capture(first, tmp_path)
    _inputs(tmp_path, day="2026-11-06")  # completed real day, recorder missing
    later = _inputs(tmp_path, day="2026-11-23")
    # Poison unneeded files, including a future outcome payload. Recorder must
    # never open them, nor read the tracker named in a checkpoint's metadata.
    prohibited = later[2] / "data/perf_tracker.json"
    prohibited.write_bytes(b"must never be opened")
    original = Path.read_bytes
    def guarded(path):
        assert path != prohibited, "outcome/tracker access"
        return original(path)
    monkeypatch.setattr(Path, "read_bytes", guarded)
    result = _capture(later, tmp_path)
    receipt, _ = shadow.verify_artifacts(later[2], "2026-11-23")
    assert receipt["recorder_gap_dates"] == ["2026-11-06"]
    assert result["checkpoint"]["real_b_signal_sessions"] == 3
    assert result["checkpoint"]["calendar_eligible_transition_episodes"] == 1


@pytest.mark.parametrize("boundary", ["minimum", "maximum_gap"])
def test_checkpoint_stops_subsequent_capture_without_outcomes(tmp_path, monkeypatch, boundary):
    first = _inputs(tmp_path)
    if boundary == "minimum":
        monkeypatch.setattr(shadow, "MINIMUM_SIGNAL_SESSIONS", 1)
        monkeypatch.setattr(shadow, "MINIMUM_MATURE_INDEPENDENT_EPISODES", 0)
        assert _capture(first, tmp_path)["checkpoint"]["status"] == "REVIEW_REQUIRED_PENDING_OUTCOME_VERIFICATION"
    else:
        monkeypatch.setattr(shadow, "MAXIMUM_SIGNAL_SESSIONS", 1)
        # Existing real day with no recorder. The maximum cannot be extended.
    second = _inputs(tmp_path, day="2026-11-06")
    result = _capture(second, tmp_path)
    assert "NO_FURTHER_CAPTURE" in result["status"]
    assert not (second[2] / shadow._relative("2026-11-06", "daily")).exists()


def test_local_bare_remote_publish_is_narrow_and_readback_idempotent(tmp_path):
    inputs = _inputs(tmp_path)
    state, remote = inputs[2], tmp_path / "remote.git"
    _init_c_state_repo(state, remote)
    before = (state / "data/watchlist_20261105.json").read_bytes()
    staged = _capture(inputs, tmp_path)
    published = shadow.publish(state, staged)
    assert published["status"] == "B_SHADOW_REMOTE_READBACK_VERIFIED"
    assert shadow.publish(state, staged)["runtime_state_sha"] == published["runtime_state_sha"]
    assert (state / "data/watchlist_20261105.json").read_bytes() == before
    changed = subprocess.check_output(["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"], cwd=state).decode().splitlines()
    assert set(changed) == set(staged["paths"])
    for path in staged["paths"]:
        assert subprocess.check_output(["git", "--git-dir", str(remote), "show", "runtime-state:" + path]) == (state / path).read_bytes()
    with pytest.raises(ValueError, match="PATHS_REFUSED"):
        shadow.publish(state, {**staged, "paths": ["data/perf_tracker.json"]})


def test_disabled_and_failed_cli_are_fail_soft(tmp_path, monkeypatch, capsys):
    args = ["--b-result", str(tmp_path / "missing"), "--delivery-result", str(tmp_path / "missing"), "--state-root", str(tmp_path)]
    monkeypatch.delenv("ENABLE_B_STRUCTURE_VOLUME_SHADOW_V1", raising=False)
    assert shadow.main(args) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "B_STRUCTURE_VOLUME_SHADOW_DISABLED"
    monkeypatch.setenv("ENABLE_B_STRUCTURE_VOLUME_SHADOW_V1", "true")
    assert shadow.main(args) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "B_STRUCTURE_VOLUME_SHADOW_FAILED_B_C_UNCHANGED"


def test_workflow_post_delivery_default_disabled_independent_of_c_and_narrow_allowlist():
    workflow = (shadow.SOURCE_ROOT / ".github/workflows/daily_t_close.yml").read_text(encoding="utf-8")
    checkout = workflow.split("      - name: Checkout clean runtime-state for B structure-volume Shadow", 1)[1].split("      - name:", 1)[0]
    step = workflow.split("      - name: Record independent B structure and volume", 1)[1].split("      - name:", 1)[0]
    assert "continue-on-error: true" in step and "timeout-minutes: 3" in step
    assert "vars.ENABLE_B_STRUCTURE_VOLUME_SHADOW_V1 || 'false'" in step
    assert "steps.delivery_health.outcome == 'success'" in checkout
    assert "steps.c_daily" not in checkout and "steps.c_daily" not in step
    assert workflow.index("python scripts/c_rule_funnel_capture.py") < workflow.index("python scripts/b_structure_volume_shadow.py")
    for kind in ("daily", "observations"):
        assert _is_allowlisted_data_relative(Path(f"research/b_structure_volume_shadow_v1/{kind}/20261105.json"))
    assert not _is_allowlisted_data_relative(Path("research/b_structure_volume_shadow_v1/details/20261105.json"))


def test_bounded_synthetic_capacity(tmp_path):
    import time as timing
    inputs = _inputs(tmp_path, codes=tuple(f"{600000+i:06d}" for i in range(50)))
    started = timing.perf_counter()
    result = _capture(inputs, tmp_path)
    elapsed = timing.perf_counter() - started
    assert result["rows"] == 50
    assert result["combined_bytes"] < shadow.MAX_DAY_BYTES
    print(f"B_SHADOW_SYNTHETIC_CAPACITY rows=50 seconds={elapsed:.3f} observations_bytes={result['observations_bytes']} receipt_bytes={result['receipt_bytes']} combined_bytes={result['combined_bytes']}")
