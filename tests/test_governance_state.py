from pathlib import Path

from governance_state import find_governance_conflicts


ROOT = Path(__file__).resolve().parents[1]


def _state(*, head: str, ladder: str = "research", active_pr: str | None = None):
    return {
        "head": head,
        "frozen_identities": {
            "strategy": "strategy-sha",
            "protocol": "protocol-sha",
            "artifact": "artifact-sha",
        },
        "semantic_state": {
            "active_pr": active_pr,
            "delivery_ladder": ladder,
            "artifact_recoverability": "FULLY_RECOVERABLE",
            "current_objective": "development candidate",
        },
    }


def test_live_head_can_advance_past_persisted_snapshot_without_conflict():
    persisted = {
        "last_verified_master_snapshot": "old-head",
        "formal_milestone_sha": "historical-milestone",
        **_state(head="old-head"),
    }
    live = _state(head="new-governance-only-head")

    assert find_governance_conflicts(live, persisted) == ()


def test_frozen_identity_mismatch_is_a_conflict_even_when_head_is_newer():
    persisted = _state(head="old-head")
    live = _state(head="new-head")
    live["frozen_identities"]["artifact"] = "different-artifact-sha"

    conflicts = find_governance_conflicts(live, persisted)

    assert "frozen_identity_mismatch:artifact" in conflicts


def test_material_semantic_product_state_mismatch_is_a_conflict():
    persisted = _state(head="old-head", active_pr=None)
    live = _state(head="new-head", active_pr="PR-12")

    conflicts = find_governance_conflicts(live, persisted)

    assert "semantic_state_mismatch:active_pr" in conflicts


def test_governance_documents_follow_fast_path_and_minimal_handoff_language():
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    handoff = (ROOT / "HANDOFF.md").read_text(encoding="utf-8")
    status = (ROOT / "docs" / "CURRENT_STATUS.md").read_text(encoding="utf-8")
    decisions = (ROOT / "docs" / "DECISION_LOG.md").read_text(encoding="utf-8")

    assert "PERSISTED GOVERNANCE STATE" in agents
    assert "FAST PATH" in agents and "STRICT PATH" in agents
    assert "REMOTE_RECOVERY_CHECKPOINT" in agents
    assert "remote HEAD" in handoff and "next action" in handoff
    assert "current live master HEAD" not in handoff
    assert "verified_master_sha" not in handoff
    assert "正式基线：`master@" not in status
    assert "Live Git State vs Persisted Governance Snapshot" in decisions
