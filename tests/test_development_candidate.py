import json
import hashlib

import development_candidate
from a_platform_breakout import STRATEGY_VERSION
from data_paths import DataPaths
from development_candidate import (
    DevelopmentCandidateStore,
    INELIGIBLE_ST,
    MONITOR_HEALTHY,
    MONITOR_INVALID_OUTPUT,
    RUN_ALREADY_CURRENT,
    RUN_EVALUATION_FAILURE,
    RUN_MISSING_DISPLAY_NAME,
    RUN_NO_CANDIDATES,
    RUN_OUTPUT_CONFLICT,
    RUN_OUTPUT_WRITE_FAILURE,
    RUN_PUBLISHED,
    USER_TRADABILITY_ELIGIBILITY_POLICY,
    MONITOR_UNTRACKED_OUTPUT,
)
from test_a_platform_breakout import _base_bars, _manifest
from track_perf import ingest, new_tracker
from watchlist_schema import load_watchlist


def _market_env():
    return {"level": "B", "score": 5, "detail": {"fixture": "development-candidate-v1"}}


def _canonical_json(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def test_success_publishes_canonical_output_with_immutable_provenance(tmp_path):
    store = DevelopmentCandidateStore(tmp_path)
    manifest = _manifest(_base_bars())

    result = store.generate(manifest, names={"600000": "测试银行"}, market_env=_market_env())

    assert result.status == RUN_PUBLISHED
    assert result.output_path == tmp_path / "watchlist_20260827.json"
    payload = load_watchlist(result.output_path)
    assert payload["strategy_version"] == STRATEGY_VERSION
    assert payload["candidates"][0]["name"] == "测试银行"
    assert payload["candidates"][0]["signal_id"].startswith(f"{STRATEGY_VERSION}:2026-08-27:600000:")
    assert ingest(new_tracker(), paths=DataPaths(tmp_path)) == 1
    record = json.loads(result.run_manifest_path.read_text(encoding="utf-8"))
    assert record["input_fingerprint"] == manifest.input_fingerprint
    assert record["generation_fingerprint"] == result.generation_fingerprint
    assert record["output"]["file_sha256"] == result.output_sha256
    assert record["auxiliary_inputs"]["display_names"]["values"] == {"600000": "测试银行"}
    assert hashlib.sha256(_canonical_json(record["generation_fingerprint_payload"])).hexdigest() == result.generation_fingerprint
    for auxiliary_name, auxiliary in record["auxiliary_inputs"].items():
        assert hashlib.sha256(_canonical_json(auxiliary["values"])).hexdigest() == auxiliary["sha256"], auxiliary_name

    monitored = store.monitor("2026-08-27")
    assert monitored.status == MONITOR_HEALTHY
    assert monitored.output_sha256 == result.output_sha256
    assert monitored.generation_fingerprint == result.generation_fingerprint


def test_same_total_inputs_have_same_generation_fingerprint_and_output_bytes(tmp_path):
    store = DevelopmentCandidateStore(tmp_path)
    manifest = _manifest(_base_bars())
    first = store.generate(manifest, names={"600000": "测试银行"}, market_env=_market_env())
    first_bytes = first.output_path.read_bytes()

    second = store.generate(manifest, names={"600000": "测试银行"}, market_env=_market_env())

    assert second.status == RUN_ALREADY_CURRENT
    assert second.generation_fingerprint == first.generation_fingerprint
    assert second.output_sha256 == first.output_sha256
    assert second.output_path.read_bytes() == first_bytes
    assert len(list((tmp_path / "development_candidate" / "versions").rglob("watchlist_*.json"))) == 1


def test_zero_candidate_is_successful_empty_watchlist_and_idempotent(tmp_path):
    store = DevelopmentCandidateStore(tmp_path)
    manifest = _manifest(_base_bars(), sector_evidence={})
    names = {"600000": "测试银行"}

    first = store.generate(manifest, names=names, market_env=_market_env())
    first_bytes = first.output_path.read_bytes()
    payload = load_watchlist(first.output_path)
    record = json.loads(first.run_manifest_path.read_text(encoding="utf-8"))

    assert first.status == RUN_PUBLISHED
    assert first.candidate_count == 0
    assert payload["candidates"] == []
    assert payload["sectors"] == []
    assert ingest(new_tracker(), paths=DataPaths(tmp_path)) == 0
    assert record["status"] == "SUCCESS"
    assert record["selection_status"] == RUN_NO_CANDIDATES
    assert record["candidate_count"] == 0
    assert store.monitor("2026-08-27").status == MONITOR_HEALTHY

    second = store.generate(manifest, names=names, market_env=_market_env())

    assert second.status == RUN_ALREADY_CURRENT
    assert second.generation_fingerprint == first.generation_fingerprint
    assert second.output_sha256 == first.output_sha256
    assert second.output_path.read_bytes() == first_bytes
    assert len(list((tmp_path / "development_candidate" / "versions").rglob("watchlist_*.json"))) == 1


def test_user_non_st_eligibility_filters_after_raw_qualification_and_reports_audit(tmp_path):
    symbols = ("600000", "600001", "600002", "600003")
    sector_evidence = {
        symbol: {"sector_name": "银行", "sector_rank": 5, "sector_chg": 1.5}
        for symbol in symbols
    }
    manifest = _manifest(_base_bars(), symbols=symbols, sector_evidence=sector_evidence)
    names = {
        "600000": " ST银行 ",
        "600001": " *st风险 ",
        "600002": "公司ST",
        "600003": "S T公司",
    }

    result = DevelopmentCandidateStore(tmp_path).generate(manifest, names=names, market_env=_market_env())

    assert result.b_raw_qualified_count == 4
    assert result.st_excluded_count == 2
    assert result.final_non_st_qualified_count == 2
    assert result.candidate_count == 2
    assert result.st_excluded == (
        {"symbol": "600000", "name": "ST银行", "status": INELIGIBLE_ST},
        {"symbol": "600001", "name": "*st风险", "status": INELIGIBLE_ST},
    )
    payload = load_watchlist(result.output_path)
    assert [item["code"] for item in payload["candidates"]] == ["600002", "600003"]
    assert [item["name"] for item in payload["candidates"]] == ["公司ST", "S T公司"]

    record = json.loads(result.run_manifest_path.read_text(encoding="utf-8"))
    audit = record["user_tradability_eligibility"]
    assert audit["policy"] == USER_TRADABILITY_ELIGIBILITY_POLICY
    assert audit["b_raw_qualified_count"] == 4
    assert audit["st_excluded_count"] == 2
    assert audit["final_non_st_qualified_count"] == 2
    assert audit["st_excluded"] == list(result.st_excluded)
    assert record["b_raw_qualified_count"] == 4
    assert record["st_excluded_count"] == 2
    assert record["final_non_st_qualified_count"] == 2
    assert record["st_excluded"] == list(result.st_excluded)
    assert record["auxiliary_inputs"]["user_tradability_eligibility"]["identity"] == (
        USER_TRADABILITY_ELIGIBILITY_POLICY
    )


def test_user_non_st_eligibility_does_not_change_evaluator_status_or_strategy_identity(tmp_path):
    manifest = _manifest(_base_bars())

    result = DevelopmentCandidateStore(tmp_path).generate(
        manifest,
        names={"600000": "*ST测试"},
        market_env=_market_env(),
    )

    assert result.status == RUN_PUBLISHED
    assert result.candidate_count == 0
    assert result.b_raw_qualified_count == 1
    assert result.st_excluded_count == 1
    assert result.final_non_st_qualified_count == 0
    record = json.loads(result.run_manifest_path.read_text(encoding="utf-8"))
    assert record["evaluation_counts"] == {"QUALIFIED_LEGACY_BASELINE": 1}
    assert record["strategy_version"] == STRATEGY_VERSION


def test_evaluator_failure_is_distinct_from_zero_candidate_success(tmp_path, monkeypatch):
    store = DevelopmentCandidateStore(tmp_path)
    manifest = _manifest(_base_bars())

    def fail_evaluator(_manifest):
        raise RuntimeError("simulated evaluator failure")

    monkeypatch.setattr(development_candidate, "evaluate_universe", fail_evaluator)
    result = store.generate(manifest, names={"600000": "测试银行"}, market_env=_market_env())

    assert result.status == RUN_EVALUATION_FAILURE
    assert result.generation_fingerprint
    assert result.output_path is None
    assert not store.canonical_path("2026-08-27").exists()
    record = json.loads(result.run_manifest_path.read_text(encoding="utf-8"))
    assert record["status"] == RUN_EVALUATION_FAILURE
    assert "output" not in record


def test_missing_name_fails_closed_and_does_not_create_output(tmp_path):
    store = DevelopmentCandidateStore(tmp_path)
    result = store.generate(_manifest(_base_bars()), names={}, market_env=_market_env())

    assert result.status == RUN_MISSING_DISPLAY_NAME
    assert result.output_path is None
    assert not (tmp_path / "watchlist_20260827.json").exists()


def test_names_and_market_env_are_part_of_generation_fingerprint(tmp_path):
    manifest = _manifest(_base_bars())
    named_a = DevelopmentCandidateStore(tmp_path / "named-a").generate(
        manifest, names={"600000": "测试银行"}, market_env=_market_env()
    )
    named_b = DevelopmentCandidateStore(tmp_path / "named-b").generate(
        manifest, names={"600000": "另一家银行"}, market_env=_market_env()
    )
    env_b = DevelopmentCandidateStore(tmp_path / "env-b").generate(
        manifest, names={"600000": "测试银行"}, market_env={**_market_env(), "score": 6}
    )

    assert named_a.generation_fingerprint != named_b.generation_fingerprint
    assert named_a.output_sha256 != named_b.output_sha256
    assert named_a.generation_fingerprint != env_b.generation_fingerprint
    assert named_a.output_sha256 != env_b.output_sha256


def test_changed_generation_identity_is_conflict_and_not_old_run_identity(tmp_path):
    store = DevelopmentCandidateStore(tmp_path)
    manifest = _manifest(_base_bars())
    first = store.generate(manifest, names={"600000": "测试银行"}, market_env=_market_env())

    result = store.generate(manifest, names={"600000": "另一家银行"}, market_env=_market_env())

    assert result.status == RUN_OUTPUT_CONFLICT
    assert result.generation_fingerprint != first.generation_fingerprint
    assert result.run_manifest_path != first.run_manifest_path
    record = json.loads(result.run_manifest_path.read_text(encoding="utf-8"))
    assert record["input_fingerprint"] == first.input_fingerprint
    assert record["generation_fingerprint"] == result.generation_fingerprint


def test_existing_different_canonical_output_is_not_overwritten(tmp_path):
    store = DevelopmentCandidateStore(tmp_path)
    manifest = _manifest(_base_bars())
    first = store.generate(manifest, names={"600000": "测试银行"}, market_env=_market_env())
    original = first.output_path.read_bytes()
    changed_env = {**_market_env(), "score": 6}

    result = store.generate(manifest, names={"600000": "测试银行"}, market_env=changed_env)

    assert result.status == RUN_OUTPUT_CONFLICT
    assert result.generation_fingerprint != first.generation_fingerprint
    assert first.output_path.read_bytes() == original


def test_publish_write_failure_is_fail_closed_and_preserves_known_good(tmp_path, monkeypatch):
    known_good_store = DevelopmentCandidateStore(tmp_path / "known-good")
    manifest = _manifest(_base_bars())
    known_good = known_good_store.generate(manifest, names={"600000": "测试银行"}, market_env=_market_env())
    known_good_bytes = known_good.output_path.read_bytes()

    failing_store = DevelopmentCandidateStore(tmp_path / "failing")
    failed_path = failing_store.canonical_path("2026-08-27")
    original_atomic_write = development_candidate._atomic_write

    def fail_canonical_write(path, content):
        if path == failed_path:
            raise OSError("simulated canonical filesystem failure")
        original_atomic_write(path, content)

    monkeypatch.setattr(development_candidate, "_atomic_write", fail_canonical_write)
    result = failing_store.generate(manifest, names={"600000": "测试银行"}, market_env=_market_env())

    assert result.status == RUN_OUTPUT_WRITE_FAILURE
    assert result.output_path is None
    assert not failed_path.exists()
    assert not list(failed_path.parent.glob(f".{failed_path.name}.*.tmp"))
    assert known_good.output_path.read_bytes() == known_good_bytes
    record = json.loads(result.run_manifest_path.read_text(encoding="utf-8"))
    assert record["status"] == RUN_OUTPUT_WRITE_FAILURE
    assert record["generation_fingerprint"] == result.generation_fingerprint
    assert "simulated canonical filesystem failure" in record["failure_message"]


def test_monitor_detects_tampering_and_rollback_restores_known_good_version(tmp_path):
    store = DevelopmentCandidateStore(tmp_path)
    manifest = _manifest(_base_bars())
    first = store.generate(manifest, names={"600000": "测试银行"}, market_env=_market_env())
    first.output_path.write_text("{}", encoding="utf-8")

    assert store.monitor("2026-08-27").status == MONITOR_INVALID_OUTPUT

    restored = store.rollback("2026-08-27", first.generation_fingerprint)

    assert restored.status == MONITOR_HEALTHY
    assert restored.output_sha256 == first.output_sha256
    assert restored.generation_fingerprint == first.generation_fingerprint


def test_monitor_rejects_a_valid_but_untracked_canonical_output(tmp_path):
    source = DevelopmentCandidateStore(tmp_path / "source")
    manifest = _manifest(_base_bars())
    first = source.generate(manifest, names={"600000": "测试银行"}, market_env=_market_env())
    untracked = DevelopmentCandidateStore(tmp_path / "untracked")
    untracked.canonical_path("2026-08-27").parent.mkdir(parents=True)
    untracked.canonical_path("2026-08-27").write_bytes(first.output_path.read_bytes())

    assert untracked.monitor("2026-08-27").status == MONITOR_UNTRACKED_OUTPUT


def test_monitor_rejects_tampered_generation_provenance(tmp_path):
    store = DevelopmentCandidateStore(tmp_path)
    manifest = _manifest(_base_bars())
    first = store.generate(manifest, names={"600000": "测试银行"}, market_env=_market_env())
    record = json.loads(first.run_manifest_path.read_text(encoding="utf-8"))
    record["auxiliary_inputs"]["market_env"]["values"]["score"] = 999
    first.run_manifest_path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")

    monitored = store.monitor("2026-08-27")

    assert monitored.status == MONITOR_UNTRACKED_OUTPUT
