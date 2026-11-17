"""User-visible shortlist behavior and original-input identity boundaries."""
import copy
import json
import subprocess

import pytest

import preview_b_shortlist as preview
from b_structure_volume_observation import FIELDS, TRANSITION, canonical, sha
from watchlist_schema import validate_watchlist


DAY = "2026-11-16"


def _inputs(specs=None):
    specs = specs if specs is not None else [
        ("600001", .10, 3, 12), ("600002", .20, 2, 12),
        ("600003", .30, 1, 11), ("600004", .05, 1, 11.5), ("600005", .05, 1, 11.5),
    ]
    watch = validate_watchlist({
        "date": DAY, "mode": "close", "market_env": {"grade": "C"}, "sectors": [],
        "strategy_version": preview.STRATEGY_VERSION,
        "candidates": [{"code": code, "name": "测试股份", "buy_type": "B 突破回踩",
                        "setup": "B_BREAKOUT_RETEST", "score": 99, "price": 10,
                        "trigger": 10, "stop": 9, "target": target, "rr": 99}
                       for code, _, _, target in specs],
    })
    rows = [{"signal_id": c["signal_id"], "code": c["code"], "signal_date": DAY,
             "formal_b_qualified": True, "structure": {"state": TRANSITION},
             "is_w2w3_transition": True,
             "volume": {"observation_version": preview.VOLUME_OBSERVATION_VERSION,
                        "protocol_commit_sha": preview.VOLUME_OBSERVATION_PROTOCOL_COMMIT_SHA,
                        FIELDS[0]: v1, FIELDS[1]: v2, FIELDS[2]: .8,
                        "window_days": 5, "missing_reason": {}}}
            for c, (_, v1, v2, _) in zip(watch["candidates"], specs)]
    return watch, {"schema_version": preview.shadow.VERSION, "signal_date": DAY,
                   "feature_identity": preview.shadow.feature_identity(), "rows": rows}


def test_fronts_tradeoffs_ties_and_two_or_three_cap_are_deterministic():
    watch, observations = _inputs()
    original = copy.deepcopy((watch, observations))
    two = preview.build_preview(watch, observations, limit=2)
    three = preview.build_preview(watch, observations, limit=3)
    assert two["selected_codes"] == ["600001", "600004"]
    assert three["selected_codes"] == ["600001", "600004", "600005"]
    by_code = {r["code"]: r for r in three["rows"]}
    assert by_code["600002"]["front"] == 2
    assert by_code["600003"]["front"] == 3
    assert by_code["600002"]["dominated_by"] == ["600001"]
    assert by_code["600003"]["dominated_by"] == ["600001", "600002", "600004", "600005"]
    # Fronts precede the within-front convention, even when that RR is higher.
    assert by_code["600002"]["reference_reward_risk"] > by_code["600004"]["reference_reward_risk"]
    assert (watch, observations) == original
    watch["candidates"].reverse()
    observations["rows"].reverse()
    assert preview.build_preview(watch, observations) == three


def test_reference_entry_uses_trigger_or_close_and_recomputes_distances():
    watch, observations = _inputs([("600001", .1, 2, 12), ("600002", .1, 2, 12)])
    watch["candidates"][0].update(price=9.5, rr=999, risk=.001)
    watch["candidates"][1].update(price=11, rr=999, risk=.001)
    result = preview.build_preview(watch, observations)
    first, second = result["rows"]
    assert first["reference_entry"] == 10
    assert first["reference_risk_fraction"] == pytest.approx(.1)
    assert first["reference_reward_risk"] == 2
    assert second["reference_entry"] == 11
    assert second["reference_risk_fraction"] == pytest.approx(2 / 11)
    assert second["reference_reward_risk"] == .5
    assert second["front"] == 2


def test_same_front_uses_risk_then_code_when_reward_risk_tied():
    watch, observations = _inputs([("600001", .1, 2, 12), ("600002", .2, 2, 12)])
    watch["candidates"][0].update(price=8, trigger=8, stop=6, target=10)
    watch["candidates"][1].update(price=8, trigger=8, stop=7, target=9)
    result = preview.build_preview(watch, observations)
    assert result["selected_codes"] == ["600002", "600001"]
    assert all(row["front"] == 1 for row in result["rows"])
    assert "次序由参考风险距离决定" in preview.render_markdown(result)


def test_float_tails_cannot_invent_dominance_or_override_risk_tie_break():
    watch, observations = _inputs([("600001", .1, 2, 12), ("600002", .1, 2, 12)])
    watch["candidates"][0].update(price=4.79, trigger=4.79, stop=4.58, target=5.315)
    watch["candidates"][1].update(price=23.43, trigger=23.43, stop=22.63, target=25.43)
    # Both targets are 2.5R. Binary arithmetic must not prefer the higher risk.
    result = preview.build_preview(watch, observations)
    assert result["selected_codes"] == ["600002", "600001"]
    assert result["rows"][0]["front"] == 2
    assert result["rows"][0]["dominated_by"] == ["600002"]
    # Equivalent formulas also cannot push one otherwise identical row to a later front.
    watch["candidates"][0].update(price=10, trigger=10, stop=9, target=12.5)
    watch["candidates"][1].update(price=10, trigger=10, stop=9, target=12.5 + 1e-14)
    result = preview.build_preview(watch, observations)
    assert result["selected_codes"] == ["600001", "600002"]
    assert all(row["front"] == 1 for row in result["rows"])


def test_missing_invalid_and_other_stages_remain_visible_without_padding():
    watch, observations = _inputs()
    observations["rows"][0].update(structure={"state": "EARLY_PULLBACK"}, is_w2w3_transition=False)
    observations["rows"][1]["volume"].update({FIELDS[1]: None, "missing_reason": {FIELDS[1]: "ZERO_DENOMINATOR"}})
    watch["candidates"][2]["target"] = 10
    observations["rows"][3]["volume"][FIELDS[0]] = float("nan")
    observations["rows"][4]["volume"].update({FIELDS[2]: None, "missing_reason": {FIELDS[2]: "PULLBACK_WINDOW_LT_4"}})
    result = preview.build_preview(watch, observations)
    assert result["selected_codes"] == ["600005"]
    assert result["candidate_count"] == 5 and result["eligible_count"] == 1
    assert [r["reasons"] for r in result["rows"]] == [
        ["OUTSIDE_COMPARISON_STAGE"], ["V1_V2_UNAVAILABLE_OR_INVALID"],
        ["INVALID_REFERENCE_PRICES"], ["V1_V2_UNAVAILABLE_OR_INVALID"], ["SELECTED"],
    ]
    assert result["rows"][3]["volume"][FIELDS[0]] is None
    assert json.loads(canonical(result))["selected_codes"] == ["600005"]
    rendered = preview.render_markdown(result)
    assert "PULLBACK_WINDOW_LT_4" in rendered and "ZERO_DENOMINATOR" in rendered
    assert "5 只正式候选 → 1 只可比较 → 1 只入选" in rendered
    assert "离线重放" in rendered and "NEEDS_MORE_EVIDENCE" in rendered


def test_v3_score_and_unrelated_fields_never_change_selection():
    watch, observations = _inputs()
    baseline = preview.build_preview(watch, observations)
    for i, (c, row) in enumerate(zip(watch["candidates"], observations["rows"])):
        c["score"] = -1000 * i
        c["rr"] = 1000 * (i + 1)
        row["volume"][FIELDS[2]] = 9999 - i
        row["coordinates"] = {"synthetic_ignored": 9999}
        row["future_return"] = -9999  # Synthetic canary, never read from an outcome source.
    changed = preview.build_preview(watch, observations)
    assert changed["selected_codes"] == baseline["selected_codes"]
    assert [r["comparison_order"] for r in changed["rows"]] == [r["comparison_order"] for r in baseline["rows"]]
    assert all("score" not in r and "future_return" not in r for r in changed["rows"])


@pytest.mark.parametrize("field,value,reason", [
    (FIELDS[0], 1.1, None), (FIELDS[0], True, None),
    (FIELDS[1], -1, None), (FIELDS[1], 2, "UNVERIFIED"),
])
def test_invalid_volume_or_contradictory_missing_flag_is_not_eligible(field, value, reason):
    watch, observations = _inputs([("600001", .1, 2, 12)])
    observations["rows"][0]["volume"][field] = value
    if reason:
        observations["rows"][0]["volume"]["missing_reason"][field] = reason
    result = preview.build_preview(watch, observations)
    assert result["selected_codes"] == []
    assert result["rows"][0]["reasons"] == ["V1_V2_UNAVAILABLE_OR_INVALID"]


def test_empty_list_is_explicit_and_limits_are_restricted():
    watch, observations = _inputs([])
    result = preview.build_preview(watch, observations)
    assert result["selected_codes"] == [] and result["rows"] == []
    assert "不补足名额" in preview.render_markdown(result)
    for limit in (0, 1, 4, True, 2.0):
        with pytest.raises(ValueError, match="LIMIT"):
            preview.build_preview(watch, observations, limit=limit)


@pytest.mark.parametrize("change", ["date", "code", "strategy", "set", "duplicate", "stage_flag", "volume_protocol"])
def test_mismatched_candidate_identity_fails_closed(change):
    watch, observations = _inputs()
    if change == "date":
        observations["rows"][0]["signal_date"] = "2026-11-17"
    elif change == "code":
        observations["rows"][0]["code"] = "600099"
    elif change == "strategy":
        watch["strategy_version"] = "OTHER"
    elif change == "set":
        observations["rows"].pop()
    elif change == "duplicate":
        observations["rows"].append(copy.deepcopy(observations["rows"][0]))
    elif change == "stage_flag":
        observations["rows"][0]["is_w2w3_transition"] = False
    else:
        observations["rows"][0]["volume"]["protocol_commit_sha"] = "wrong"
    with pytest.raises(ValueError, match="MISMATCH"):
        preview.build_preview(watch, observations)


@pytest.fixture
def git_inputs(monkeypatch, tmp_path):
    watch, observations = _inputs()
    generation = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=preview.ROOT).decode().strip()
    runtime = "a" * 40
    watch_path = "data/watchlist_20261116.json"
    receipt_path = f"{preview.shadow.RELATIVE_ROOT.as_posix()}/daily/20261116.json"
    obs_path = f"{preview.shadow.RELATIVE_ROOT.as_posix()}/observations/20261116.json"
    receipt = {"schema_version": preview.shadow.VERSION, "signal_date": DAY,
               "feature_identity": observations["feature_identity"],
               "generation_commit": generation, "strategy_spec_sha256": preview.STRATEGY_SPEC_SHA256}
    blobs = {}

    def refresh():
        blobs[watch_path] = canonical(watch)
        blobs[obs_path] = canonical(observations)
        receipt["watchlist_sha256"] = sha(blobs[watch_path])
        receipt["observations"] = {"path": obs_path, "sha256": sha(blobs[obs_path]),
                                   "bytes": len(blobs[obs_path]), "rows": len(observations["rows"])}
        receipt["record_sha256"] = sha(canonical({k: v for k, v in receipt.items() if k != "record_sha256"}))
        blobs[receipt_path] = canonical(receipt)

    refresh()
    calls = []
    actual_git = preview._git

    def fake_git(*args):
        calls.append(args)
        if args[0] == "rev-parse":
            return runtime.encode()
        if args[0] == "show" and args[1].startswith(runtime + ":"):
            return blobs[args[1].split(":", 1)[1]]
        assert args[0] == "show" and args[1].startswith(generation + ":scripts/")
        return actual_git(*args)

    monkeypatch.setattr(preview, "_git", fake_git)
    monkeypatch.setattr(preview.tempfile, "tempdir", str(tmp_path))
    return watch, observations, receipt, blobs, refresh, calls


def test_cli_verifies_only_named_inputs_and_writes_reproducible_offline_preview(git_inputs, tmp_path):
    _, _, _, blobs, _, calls = git_inputs
    originals = copy.deepcopy(blobs)
    output = tmp_path / "preview"
    args = ["--date", DAY, "--runtime-ref", "origin/runtime-state", "--limit", "2", "--output-dir", str(output)]
    assert preview.main(args) == 0
    files = {p.name: p.read_bytes() for p in output.iterdir()}
    assert len(files) == 2
    payload = json.loads(files["b_shortlist_preview_20261116_top2.json"])
    assert payload["selected_codes"] == ["600001", "600004"]
    assert payload["mode"] == "OFFLINE_AS_OF_REPLAY"
    assert payload["outcome_accessed"] is False and payload["production_validated"] is False
    assert set(payload["source"]["input_sha256"]) == set(blobs)
    assert preview.main(args) == 0
    assert {p.name: p.read_bytes() for p in output.iterdir()} == files
    assert blobs == originals
    assert all("outcomes" not in str(call) and "final_oos" not in str(call) for call in calls)


@pytest.mark.parametrize("corruption", ["watch_hash", "obs_hash", "receipt_hash", "spec", "feature", "source"])
def test_corrupt_original_identity_never_produces_a_preview(git_inputs, tmp_path, corruption):
    _, observations, receipt, blobs, refresh, _ = git_inputs
    if corruption in {"watch_hash", "obs_hash", "receipt_hash"}:
        needle = {"watch_hash": "watchlist_", "obs_hash": "/observations/", "receipt_hash": "/daily/"}[corruption]
        path = next(p for p in blobs if needle in p)
        if corruption == "receipt_hash":
            changed = json.loads(blobs[path])
            changed["record_sha256"] = "0" * 64
            blobs[path] = canonical(changed)
        else:
            blobs[path] += b"\n"
    else:
        if corruption == "spec":
            receipt["strategy_spec_sha256"] = "0" * 64
        elif corruption == "feature":
            observations["feature_identity"]["hypothesis"] = "OTHER"
        else:
            observations["feature_identity"]["source_lf_sha256"]["volume_observation.py"] = "0" * 64
        refresh()
    output = tmp_path / "should-not-exist"
    with pytest.raises(ValueError, match="MISMATCH"):
        preview.main(["--date", DAY, "--output-dir", str(output)])
    assert not output.exists()


def test_cli_refuses_production_output_before_reading_inputs(monkeypatch):
    monkeypatch.setattr(preview, "load_inputs", lambda *args: pytest.fail("must reject before reading"))
    for output in (preview.ROOT / "data" / "preview", preview.ROOT / ".git" / "preview"):
        with pytest.raises(SystemExit):
            preview.main(["--date", DAY, "--output-dir", str(output)])
