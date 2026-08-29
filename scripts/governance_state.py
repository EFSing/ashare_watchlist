"""Pure governance-state comparison helpers.

The repository stores provenance snapshots in tracked documents, while live
Git/GitHub state is queried at intake.  This module intentionally has no Git
or GitHub dependency so the semantic rules can be regression-tested locally.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


SEMANTIC_STATE_FIELDS = (
    "active_pr",
    "delivery_ladder",
    "artifact_recoverability",
    "current_objective",
)
_MISSING = object()


def find_governance_conflicts(
    live_state: Mapping[str, Any],
    persisted_state: Mapping[str, Any],
) -> tuple[str, ...]:
    """Return semantic or frozen-identity conflicts between two state views.

    ``head`` and ``last_verified_master_snapshot`` are intentionally not
    compared: a newer HEAD is normal.  Callers provide semantic observations
    separately when an intake audit finds a material state change.
    """

    conflicts: list[str] = []

    live_frozen = live_state.get("frozen_identities", {})
    persisted_frozen = persisted_state.get("frozen_identities", {})
    if not isinstance(live_frozen, Mapping) or not isinstance(persisted_frozen, Mapping):
        conflicts.append("required_frozen_identities_missing_or_invalid")
    else:
        for identity in sorted(set(live_frozen) | set(persisted_frozen)):
            if live_frozen.get(identity) != persisted_frozen.get(identity):
                conflicts.append(f"frozen_identity_mismatch:{identity}")

    live_semantic = live_state.get("semantic_state", {})
    persisted_semantic = persisted_state.get("semantic_state", {})
    if not isinstance(live_semantic, Mapping) or not isinstance(persisted_semantic, Mapping):
        conflicts.append("semantic_state_missing_or_invalid")
    else:
        for field in SEMANTIC_STATE_FIELDS:
            live_value = live_semantic.get(field, _MISSING)
            persisted_value = persisted_semantic.get(field, _MISSING)
            if (
                live_value is not _MISSING
                and persisted_value is not _MISSING
                and live_value != persisted_value
            ):
                conflicts.append(f"semantic_state_mismatch:{field}")

    return tuple(conflicts)
