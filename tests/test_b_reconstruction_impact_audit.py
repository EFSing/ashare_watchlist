from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).parents[1]
AUDIT_PATH = REPO_ROOT / "data" / "validation" / "strategy_candidate_eligibility_v1_1" / "b_reconstruction_impact_audit.json"


def test_corrected_b_structural_impact_is_event_set_invariant_without_returns_replay():
    audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))

    assert audit["decision"] == "ELIGIBILITY_ARTIFACT_EVENT_SET_INVARIANT"
    assert audit["frozen_input"]["evaluated_symbol_dates"] == 4_041_140
    assert audit["comparison"]["corrected_projection_shared_callable_identity"] is True
    assert audit["comparison"]["projection_differences"] == 0
    assert audit["comparison"]["status_differences"] == 0
    assert audit["comparison"]["qualification_event_membership_differences"] == 0
    assert audit["comparison"]["old_qualified_event_count"] == 17_714
    assert audit["comparison"]["corrected_qualified_event_count"] == 17_714
    assert audit["sector_observations"]["status"] == "NOT_AVAILABLE_IN_FROZEN_DEVELOPMENT_INPUT"
    assert audit["frozen_input"]["forward_returns_read"] is False
    assert audit["forbidden_scope"]["returns_regenerated"] is False
    assert audit["forbidden_scope"]["old_artifact_overwritten"] is False
