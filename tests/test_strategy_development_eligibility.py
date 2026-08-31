from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import core_signal_replay as replay

from strategy_development_eligibility import (
    ELIGIBILITY_RULE_FROZEN_BEFORE_B_RETURNS_READ,
    ELIGIBILITY_THRESHOLDS,
    _canonicalise_provenance_paths,
    _content_identity_payload,
    _fixed_decision,
    _year_robustness,
)


REPO_ROOT = Path(__file__).parents[1]
ELIGIBILITY_DIR = REPO_ROOT / "data" / "validation" / "strategy_candidate_eligibility_v1"
EVENT_PATH = ELIGIBILITY_DIR / "b_breakout_retest_eligibility_events.jsonl.gz"
MANIFEST_PATH = ELIGIBILITY_DIR / "strategy_development_eligibility_manifest.json"
REGISTRY_PATH = REPO_ROOT / "data" / "governance" / "frozen_artifacts.json"


def _metrics(*, primary_mean: float = 1.0, primary_median: float = 0.5) -> dict[str, dict]:
    horizons = {}
    for horizon in ("1D", "3D", "5D", "10D"):
        horizons[horizon] = {
            "sample_count": 40,
            "positive_rate": 0.55,
            "mean_return_pct": primary_mean if horizon == "10D" else 0.1,
            "median_return_pct": primary_median if horizon == "10D" else 0.05,
            "by_year": {
                "2023": {"sample_count": 12, "positive_rate": 0.5, "mean_return_pct": 0.1, "median_return_pct": 0.1},
                "2024": {"sample_count": 14, "positive_rate": 0.6, "mean_return_pct": 0.2, "median_return_pct": 0.2},
                "2025": {"sample_count": 14, "positive_rate": 0.55, "mean_return_pct": -0.1, "median_return_pct": -0.1},
            },
        }
    return horizons


def _frequency() -> dict:
    return {"qualified_signal_event_count": 40}


def test_eligibility_protocol_is_frozen_before_b_returns_are_read():
    assert ELIGIBILITY_RULE_FROZEN_BEFORE_B_RETURNS_READ is True
    assert ELIGIBILITY_THRESHOLDS == {
        "minimum_total_event_count": 30,
        "minimum_available_events_per_horizon": 30,
        "primary_horizon": "10D",
        "primary_positive_rate_min": 0.50,
        "primary_mean_return_min_exclusive": 0.0,
        "primary_median_return_min_exclusive": 0.0,
        "minimum_robust_year_count": 3,
        "minimum_events_per_robust_year": 10,
        "minimum_positive_mean_year_count": 2,
    }


def test_fixed_eligibility_rule_can_pass_without_searching_parameters():
    metrics = _metrics()
    decision, audit = _fixed_decision(metrics, _frequency(), {"all_passed": True})
    assert decision == "CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES"
    assert audit["failed_gates"] == []
    assert _year_robustness(metrics)["horizon"] == "10D"


def test_fixed_eligibility_rule_rejects_negative_primary_mean():
    decision, audit = _fixed_decision(
        _metrics(primary_mean=-0.1, primary_median=-0.05),
        _frequency(),
        {"all_passed": True},
    )
    assert decision == "CANDIDATE_REJECTED"
    assert "primary_mean_return" in audit["failed_gates"]
    assert "primary_median_return" in audit["failed_gates"]


def test_fixed_eligibility_rule_rejects_failed_manifest_parity():
    decision, audit = _fixed_decision(_metrics(), _frequency(), {"all_passed": False})
    assert decision == "CANDIDATE_REJECTED"
    assert audit["failed_gates"] == ["manifest_parity"]


def _path_identity_payload(root: Path, *, absolute: bool) -> dict:
    paths = {
        "event": root / "data/validation/strategy_candidate_eligibility_v1/b_breakout_retest_eligibility_events.jsonl.gz",
        "manifest": root / "data/validation/strategy_candidate_eligibility_v1/strategy_development_eligibility_manifest.json",
        "registry": root / "data/governance/frozen_artifacts.json",
        "checkpoint": root / "data/validation/core_signal_validation_continuous_parts/core_signal_validation_resume_checkpoint.json",
        "core_output": root / "data/validation/core_signal_validation_continuous_parts/core_replay_results.jsonl.gz",
        "core_manifest": root / "data/validation/core_signal_validation_continuous_parts/core_signal_validation_manifest.json",
        "raw": root / "data/validation/core_signal_validation/raw/daily_k.parquet",
    }
    if not absolute:
        paths = {key: Path(value.relative_to(root)) for key, value in paths.items()}
    return {
        "candidate": {"version": "B", "spec_sha256": "spec"},
        "input_provenance": {
            "frozen_registry": {"path": paths["registry"].as_posix()},
            "raw_inputs": {"files": [{"path": paths["raw"].as_posix()}]},
            "core_checkpoint": {"path": paths["checkpoint"].as_posix()},
            "core_output": {"path": paths["core_output"].as_posix()},
            "core_manifest": {"path": paths["core_manifest"].as_posix()},
            "frozen_identity": {
                "raw_source_content_sha256": "raw",
                "core_projection_stream_sha256": "core",
            },
        },
        "artifacts": {"event_results": {"path": paths["event"].as_posix(), "sha256": "event"}},
        "metrics": {"10D": {"sample_count": 1}},
        "signal_concentration": {"qualified_signal_event_count": 1},
        "execution_environment": {"python": "3.12.13"},
        "decision": "CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES",
    }


def test_provenance_identity_is_invariant_under_relocated_filesystem_roots(tmp_path):
    root_a = tmp_path / "machine-a" / "repo"
    root_b = tmp_path / "machine-b" / "repo"
    for root in (root_a, root_b):
        (root / "data/governance").mkdir(parents=True)
        (root / "data/validation/strategy_candidate_eligibility_v1").mkdir(parents=True)
        (root / "data/validation/core_signal_validation/raw").mkdir(parents=True)
        (root / "data/governance/frozen_artifacts.json").write_bytes(b"registry")
        (root / "data/validation/strategy_candidate_eligibility_v1/b_breakout_retest_eligibility_events.jsonl.gz").write_bytes(b"events")
        (root / "data/validation/strategy_candidate_eligibility_v1/strategy_development_eligibility_manifest.json").write_bytes(b"manifest")
        (root / "data/validation/core_signal_validation/raw/daily_k.parquet").write_bytes(b"daily-k")

    absolute_a = _path_identity_payload(root_a, absolute=True)
    absolute_b = _path_identity_payload(root_b, absolute=True)
    canonical_a = _canonicalise_provenance_paths(absolute_a, root_a)
    canonical_b = _canonicalise_provenance_paths(absolute_b, root_b)

    assert canonical_a == canonical_b
    assert replay.sha256_json(canonical_a) == replay.sha256_json(canonical_b)
    assert replay.sha256_json(_content_identity_payload(canonical_a)) == replay.sha256_json(
        _content_identity_payload(canonical_b)
    )
    serialized = json.dumps(canonical_a, ensure_ascii=False, sort_keys=True)
    assert str(root_a) not in serialized
    assert str(root_b) not in serialized
    assert "data/validation/strategy_candidate_eligibility_v1/b_breakout_retest_eligibility_events.jsonl.gz" in serialized


def test_provenance_identity_is_invariant_between_relative_and_absolute_invocation(tmp_path, monkeypatch):
    root = tmp_path / "relocation" / "repo"
    root.mkdir(parents=True)
    monkeypatch.chdir(root)
    relative = _canonicalise_provenance_paths(_path_identity_payload(root, absolute=False), root)
    absolute = _canonicalise_provenance_paths(_path_identity_payload(root, absolute=True), root)
    assert relative == absolute
    assert replay.sha256_json(relative) == replay.sha256_json(absolute)


def test_formal_b_artifacts_are_registered_and_metrics_decision_are_unchanged():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    by_path = {item["logical_path"]: item for item in registry["artifacts"]}

    event_bytes = EVENT_PATH.read_bytes()
    manifest_bytes = MANIFEST_PATH.read_bytes()
    event_record = by_path[EVENT_PATH.relative_to(REPO_ROOT).as_posix()]
    manifest_record = by_path[MANIFEST_PATH.relative_to(REPO_ROOT).as_posix()]
    assert hashlib.sha256(event_bytes).hexdigest() == event_record["file_sha256"]
    assert hashlib.sha256(manifest_bytes).hexdigest() == manifest_record["file_sha256"]
    assert manifest["decision"] == "CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES"
    assert manifest["scope"]["qualified_signal_event_count"] == 17714
    assert manifest["artifacts"]["event_results"]["sha256"] == event_record["file_sha256"]
    assert manifest["artifacts"]["event_results"]["content_sha256"] == event_record["content_sha256"]
    assert event_record["required_for_replay"] is False
    assert event_record["required_for_decision"] is True
    assert manifest_record["required_for_replay"] is False
    assert manifest_record["required_for_decision"] is True
    assert manifest_record["content_sha256"] == manifest["manifest_sha256"]
    assert manifest_record["payload_content_sha256"] == manifest["content_sha256"]
    manifest_payload = dict(manifest)
    manifest_payload.pop("manifest_sha256")
    assert replay.sha256_json(manifest_payload) == manifest["manifest_sha256"]
    assert manifest["manifest_sha256"] == "f79ec9baa494f2f0256843c2540988bd25c94269ed9a1fd4ada228759bd8e0a2"
    assert replay.sha256_json(manifest["metrics"]) == "5412a331a823132375c6615db4a3a95cca83be82da5b00523c611332fd5c68d8"
    assert manifest["content_sha256"] == "e754787836b28316430278372ab2d84817091d4608da394f9207f695a4c27aee"
    assert manifest["metrics"]["10D"]["sample_count"] == 17558
    assert manifest["metrics"]["10D"]["positive_rate"] == 0.5164027793598359
    assert manifest["metrics"]["10D"]["mean_return_pct"] == 1.4602560665420288
    assert manifest["metrics"]["10D"]["median_return_pct"] == 0.3225806451612856
    with gzip.open(EVENT_PATH, "rt", encoding="utf-8", newline="") as handle:
        records = [json.loads(line) for line in handle]
    assert len(records) == 17714
    assert replay.sha256_json(records) == event_record["content_sha256"]
    serialized = MANIFEST_PATH.read_text(encoding="utf-8")
    assert str(REPO_ROOT) not in serialized
