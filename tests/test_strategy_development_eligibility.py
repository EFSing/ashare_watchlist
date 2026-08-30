from __future__ import annotations

from strategy_development_eligibility import (
    ELIGIBILITY_RULE_FROZEN_BEFORE_B_RETURNS_READ,
    ELIGIBILITY_THRESHOLDS,
    _fixed_decision,
    _year_robustness,
)


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
