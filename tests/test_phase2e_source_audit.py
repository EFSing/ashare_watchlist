import json
from pathlib import Path


AUDIT_PATH = Path(__file__).parents[1] / "data" / "validation" / "phase2e_source_audit.json"


def _audit() -> dict[str, object]:
    return json.loads(AUDIT_PATH.read_text(encoding="utf-8"))


def test_phase2e_audit_is_explicitly_blocked_without_freezing_data():
    audit = _audit()

    assert audit["schema_version"] == "PHASE2E_SOURCE_AUDIT_V1"
    assert audit["status"] == "BLOCKED_NO_PIT_DATASET"
    dataset = audit["dataset"]
    assert dataset["frozen"] is False
    assert dataset["dataset_version"] is None
    assert dataset["content_sha256"] is None
    assert dataset["manifest_sha256"] is None


def test_phase2e_audit_has_hard_blockers_and_no_unsafe_runtime_activity():
    audit = _audit()

    inventory = audit["runtime_inventory"]
    assert inventory["configured_clients"] == []
    assert inventory["configured_credentials"] is False
    assert inventory["current_data_fetched"] is False
    assert inventory["strategy_validation_run"] is False

    blocker_ids = {item["id"] for item in audit["blockers"]}
    assert "PIT_SECTOR_EVIDENCE_UNAVAILABLE" in blocker_ids
    assert "PIT_ADJUSTMENT_EVIDENCE_UNAVAILABLE" in blocker_ids
    assert "PIT_UNIVERSE_AND_OHLCV_VINTAGE_UNAVAILABLE" in blocker_ids


def test_phase2e_audit_does_not_claim_any_candidate_source_is_pit_ready():
    audit = _audit()

    assert audit["sources"]
    assert all(source["known_at_proof"] is False for source in audit["sources"])
    assert all(source["content_sha256"] is None for source in audit["sources"])
    assert all(source["status"] != "READY_FOR_VALIDATION_DATASET_FREEZE" for source in audit["sources"])
