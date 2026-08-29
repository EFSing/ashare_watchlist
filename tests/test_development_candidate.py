import json

from a_platform_breakout import STRATEGY_VERSION
from data_paths import DataPaths
from development_candidate import (
    DevelopmentCandidateStore,
    MONITOR_HEALTHY,
    MONITOR_INVALID_OUTPUT,
    RUN_ALREADY_CURRENT,
    RUN_MISSING_DISPLAY_NAME,
    RUN_NO_QUALIFIED_CANDIDATES,
    RUN_OUTPUT_CONFLICT,
    RUN_PUBLISHED,
    MONITOR_UNTRACKED_OUTPUT,
)
from test_a_platform_breakout import _base_bars, _manifest
from track_perf import ingest, new_tracker
from watchlist_schema import load_watchlist


def _market_env():
    return {"level": "B", "score": 5, "detail": {"fixture": "development-candidate-v1"}}


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
    assert record["output"]["file_sha256"] == result.output_sha256

    monitored = store.monitor("2026-08-27")
    assert monitored.status == MONITOR_HEALTHY
    assert monitored.output_sha256 == result.output_sha256


def test_same_input_is_idempotent_and_output_bytes_do_not_change(tmp_path):
    store = DevelopmentCandidateStore(tmp_path)
    manifest = _manifest(_base_bars())
    first = store.generate(manifest, names={"600000": "测试银行"}, market_env=_market_env())
    first_bytes = first.output_path.read_bytes()

    second = store.generate(manifest, names={"600000": "测试银行"}, market_env=_market_env())

    assert second.status == RUN_ALREADY_CURRENT
    assert second.output_sha256 == first.output_sha256
    assert second.output_path.read_bytes() == first_bytes
    assert len(list((tmp_path / "development_candidate" / "versions").rglob("watchlist_*.json"))) == 1


def test_no_qualified_candidate_fails_closed_without_canonical_output(tmp_path):
    store = DevelopmentCandidateStore(tmp_path)
    manifest = _manifest(_base_bars(), sector_evidence={})

    result = store.generate(manifest, names={"600000": "测试银行"}, market_env=_market_env())

    assert result.status == RUN_NO_QUALIFIED_CANDIDATES
    assert result.output_path is None
    assert not (tmp_path / "watchlist_20260827.json").exists()
    record = json.loads(result.run_manifest_path.read_text(encoding="utf-8"))
    assert record["status"] == RUN_NO_QUALIFIED_CANDIDATES
    assert "output" not in record


def test_missing_name_fails_closed_and_does_not_create_output(tmp_path):
    store = DevelopmentCandidateStore(tmp_path)
    result = store.generate(_manifest(_base_bars()), names={}, market_env=_market_env())

    assert result.status == RUN_MISSING_DISPLAY_NAME
    assert result.output_path is None
    assert not (tmp_path / "watchlist_20260827.json").exists()


def test_existing_different_canonical_output_is_not_overwritten(tmp_path):
    store = DevelopmentCandidateStore(tmp_path)
    manifest = _manifest(_base_bars())
    first = store.generate(manifest, names={"600000": "测试银行"}, market_env=_market_env())
    original = first.output_path.read_bytes()
    changed_env = {**_market_env(), "score": 6}

    result = store.generate(manifest, names={"600000": "测试银行"}, market_env=changed_env)

    assert result.status == RUN_OUTPUT_CONFLICT
    assert first.output_path.read_bytes() == original


def test_monitor_detects_tampering_and_rollback_restores_known_good_version(tmp_path):
    store = DevelopmentCandidateStore(tmp_path)
    manifest = _manifest(_base_bars())
    first = store.generate(manifest, names={"600000": "测试银行"}, market_env=_market_env())
    first.output_path.write_text("{}", encoding="utf-8")

    assert store.monitor("2026-08-27").status == MONITOR_INVALID_OUTPUT

    restored = store.rollback("2026-08-27", manifest.input_fingerprint)

    assert restored.status == MONITOR_HEALTHY
    assert restored.output_sha256 == first.output_sha256


def test_monitor_rejects_a_valid_but_untracked_canonical_output(tmp_path):
    source = DevelopmentCandidateStore(tmp_path / "source")
    manifest = _manifest(_base_bars())
    first = source.generate(manifest, names={"600000": "测试银行"}, market_env=_market_env())
    untracked = DevelopmentCandidateStore(tmp_path / "untracked")
    untracked.canonical_path("2026-08-27").parent.mkdir(parents=True)
    untracked.canonical_path("2026-08-27").write_bytes(first.output_path.read_bytes())

    assert untracked.monitor("2026-08-27").status == MONITOR_UNTRACKED_OUTPUT
