import pytest

from historical_validation_layers import (
    CORE_SIGNAL_VALIDATION,
    FULL_LEGACY_OUTPUT_VALIDATION,
    historical_validation_layer,
)


def test_core_signal_validation_excludes_unverified_score_from_legacy_claims():
    layer = historical_validation_layer(CORE_SIGNAL_VALIDATION)

    assert layer["sector_score_status"] == "UNVERIFIED"
    assert layer["sector_report_status"] == "UNVERIFIED"
    assert layer["requires_historical_sina_membership"] is False
    assert layer["requires_exact_legacy_sector_provenance"] is False
    assert layer["claims_full_legacy_output_parity"] is False
    assert "score_85" not in layer["required_outputs"]
    assert layer["historical_returns_enabled"] is False
    assert layer["parameter_tuning_enabled"] is False
    assert layer["final_oos_enabled"] is False


def test_full_legacy_output_validation_requires_exact_historical_sina_membership():
    layer = historical_validation_layer(FULL_LEGACY_OUTPUT_VALIDATION)

    assert layer["sector_score_status"] == "VERIFIED"
    assert layer["sector_report_status"] == "VERIFIED"
    assert layer["requires_historical_sina_membership"] is True
    assert layer["requires_exact_legacy_sector_provenance"] is True
    assert layer["sector_taxonomy"] == "新浪行业"
    assert layer["claims_full_legacy_output_parity"] is True
    assert "score_85" in layer["required_outputs"]
    assert layer["historical_returns_enabled"] is False
    assert layer["parameter_tuning_enabled"] is False
    assert layer["final_oos_enabled"] is False


def test_historical_validation_layer_returns_defensive_copy_and_rejects_unknown_name():
    first = historical_validation_layer(CORE_SIGNAL_VALIDATION)
    first["required_outputs"].append("unapproved_output")
    second = historical_validation_layer(CORE_SIGNAL_VALIDATION)
    assert "unapproved_output" not in second["required_outputs"]

    with pytest.raises(ValueError, match="unknown historical validation layer"):
        historical_validation_layer("OTHER_LAYER")
