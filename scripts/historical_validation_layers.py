"""Governance-only contracts for the two Phase 2E historical validation layers.

This module does not fetch data, invoke the strategy evaluator, calculate
returns, tune parameters, or read final OOS.  It only makes the permitted
claims and the sector-evidence boundary explicit for a future validation run.
"""

from __future__ import annotations

import copy
from typing import Any


CORE_SIGNAL_VALIDATION = "CORE_SIGNAL_VALIDATION"
FULL_LEGACY_OUTPUT_VALIDATION = "FULL_LEGACY_OUTPUT_VALIDATION"


_HISTORICAL_VALIDATION_LAYERS: dict[str, dict[str, Any]] = {
    CORE_SIGNAL_VALIDATION: {
        "name": CORE_SIGNAL_VALIDATION,
        "required_outputs": [
            "a_match",
            "hard_rejects",
            "support",
            "stop",
            "target",
            "rr",
            "trigger",
            "qualified_signal_identity",
        ],
        "sector_score_status": "UNVERIFIED",
        "sector_report_status": "UNVERIFIED",
        "requires_historical_sina_membership": False,
        "requires_exact_legacy_sector_provenance": False,
        "claims_full_legacy_output_parity": False,
        "historical_returns_enabled": False,
        "parameter_tuning_enabled": False,
        "final_oos_enabled": False,
    },
    FULL_LEGACY_OUTPUT_VALIDATION: {
        "name": FULL_LEGACY_OUTPUT_VALIDATION,
        "required_outputs": [
            "a_match",
            "hard_rejects",
            "support",
            "stop",
            "target",
            "rr",
            "trigger",
            "qualified_signal_identity",
            "score_85",
            "legacy_sector_report",
        ],
        "sector_score_status": "VERIFIED",
        "sector_report_status": "VERIFIED",
        "requires_historical_sina_membership": True,
        "requires_exact_legacy_sector_provenance": True,
        "sector_taxonomy": "新浪行业",
        "claims_full_legacy_output_parity": True,
        "historical_returns_enabled": False,
        "parameter_tuning_enabled": False,
        "final_oos_enabled": False,
    },
}


def historical_validation_layer(name: str) -> dict[str, Any]:
    """Return a defensive copy of one known historical validation contract."""

    try:
        return copy.deepcopy(_HISTORICAL_VALIDATION_LAYERS[name])
    except KeyError as exc:
        raise ValueError(f"unknown historical validation layer: {name!r}") from exc


__all__ = [
    "CORE_SIGNAL_VALIDATION",
    "FULL_LEGACY_OUTPUT_VALIDATION",
    "historical_validation_layer",
]
