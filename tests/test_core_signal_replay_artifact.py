import gzip
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
ARTIFACT_DIR = ROOT / "data" / "validation" / "core_signal_validation"
MANIFEST_PATH = ARTIFACT_DIR / "core_signal_validation_manifest.json"
RESULTS_PATH = ARTIFACT_DIR / "core_replay_results.jsonl.gz"


def _manifest() -> dict[str, object]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def test_core_artifact_is_frozen_without_sector_score_or_return_metrics():
    manifest = _manifest()
    assert manifest["schema_version"] == "CORE_SIGNAL_VALIDATION_DATASET_MANIFEST_V1"
    assert manifest["validation_layer"] == "CORE_SIGNAL_VALIDATION"
    assert manifest["sector_semantics"]["historical_membership_included"] is False
    assert manifest["sector_semantics"]["sector_score_status"] == "UNVERIFIED"
    assert manifest["sector_semantics"]["sector_report_status"] == "UNVERIFIED"
    assert manifest["sector_semantics"]["taxonomy_substitution"] is False
    assert manifest["replay"]["score_fields_in_output"] is False
    assert set(manifest["forbidden_metrics"]) == {
        "return", "win_rate", "mfe", "mae", "pnl", "expectancy", "profit_factor"
    }


def test_core_result_stream_hash_and_coverage_are_reproducible():
    manifest = _manifest()
    digest = hashlib.sha256()
    row_count = 0
    dates: dict[str, int] = {}
    with gzip.open(RESULTS_PATH, "rt", encoding="utf-8", newline="") as handle:
        for line in handle:
            row = json.loads(line)
            assert "score_breakdown" not in row
            assert "score_total" not in row
            assert not any(metric in row for metric in manifest["forbidden_metrics"])
            digest.update(_canonical(row))
            dates[row["signal_date"]] = dates.get(row["signal_date"], 0) + 1
            row_count += 1
    replay = manifest["replay"]
    assert digest.hexdigest() == replay["projection_stream_sha256"]
    assert replay["deterministic_second_pass_sha256"] == replay["projection_stream_sha256"]
    assert replay["hash_parity"] is True
    assert replay["full_evaluator_double_pass_hash_parity"] is True
    assert "two independent full evaluator runs" in replay["determinism_method"]
    assert row_count == replay["candidate_evaluations"]
    expected = {
        date: values["evaluable_symbol_count"]
        for date, values in manifest["coverage_and_correctness"]["coverage_by_date"].items()
    }
    assert dates == expected


def test_core_artifact_preserves_strategy_identity_and_timing_boundary():
    manifest = _manifest()
    assert manifest["strategy"]["version"] == "A_PLATFORM_BREAKOUT_LEGACY_V1"
    assert len(manifest["strategy"]["spec_sha256"]) == 64
    assert manifest["timing_contract"]["signal_uses"] == "T close only"
    assert manifest["timing_contract"]["same_bar_execution"] is False
    assert manifest["timing_contract"]["future_bar_inputs"] is False
    assert manifest["coverage_and_correctness"]["look_ahead_scan"].startswith("PASS")
    assert manifest["coverage_and_correctness"]["timing_scan"].startswith("PASS")


def test_core_manifest_self_hash_excludes_only_manifest_hash():
    manifest = _manifest()
    expected = manifest.pop("manifest_sha256")
    canonical = json.dumps(manifest, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == expected
