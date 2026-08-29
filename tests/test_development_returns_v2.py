import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from validate_development_returns_v2 import _adjust_outcome_path, _crossing_events


ROOT = Path(__file__).parents[1]
V1_DIR = ROOT / "data" / "validation" / "core_signal_validation_continuous_parts" / "development_returns"
V2_DIR = ROOT / "data" / "validation" / "core_signal_validation_continuous_parts" / "development_returns_v2"


def _path(events=(), *, dates=(1, 2), opens=(100.0, 100.0), highs=(101.0, 101.0), lows=(99.0, 99.0), closes=(100.0, 100.0)):
    return _adjust_outcome_path(
        dates_ms=np.array(dates, dtype=np.int64),
        opens=np.array(opens),
        highs=np.array(highs),
        lows=np.array(lows),
        closes=np.array(closes),
        events=list(events),
        target_ms=dates[-1],
    )


def test_no_corporate_action_adjusted_equals_raw():
    adjusted = _path()
    expected = ((100.0, 100.0), (101.0, 101.0), (99.0, 99.0), (100.0, 100.0))
    for actual, raw in zip(adjusted, expected):
        assert actual == pytest.approx(raw)


def test_cash_dividend_puts_entry_and_target_on_same_basis():
    adjusted_open, _, _, adjusted_close = _path(
        [(2, 1.0, 0.0, 0.0, 0.0)],
        opens=(100.0, 99.0),
        closes=(100.0, 99.0),
    )
    assert adjusted_open[0] == pytest.approx(99.0)
    assert adjusted_close[-1] == pytest.approx(99.0)
    assert adjusted_close[-1] / adjusted_open[0] - 1.0 == pytest.approx(0.0)


def test_bonus_or_share_split_puts_entry_and_target_on_same_basis():
    adjusted_open, _, _, adjusted_close = _path(
        [(2, 0.0, 1.0, 0.0, 0.0)],
        opens=(100.0, 50.0),
        closes=(100.0, 50.0),
    )
    assert adjusted_open[0] == pytest.approx(50.0)
    assert adjusted_close[-1] == pytest.approx(50.0)


def test_rights_issue_uses_project_affine_convention():
    theoretical_ex_price = (20.0 + 10.0 * 0.5) / 1.5
    adjusted_open, _, _, adjusted_close = _path(
        [(2, 0.0, 0.0, 0.5, 10.0)],
        opens=(20.0, theoretical_ex_price),
        closes=(20.0, theoretical_ex_price),
    )
    assert adjusted_open[0] == pytest.approx(theoretical_ex_price)
    assert adjusted_close[-1] == pytest.approx(theoretical_ex_price)


def test_ex_date_equal_entry_date_is_not_applied_twice():
    adjusted = _path(
        [(1, 1.0, 1.0, 0.0, 0.0)],
        opens=(50.0, 51.0),
        closes=(50.0, 51.0),
    )
    assert adjusted[0][0] == pytest.approx(50.0)
    assert adjusted[3][-1] == pytest.approx(51.0)
    assert _crossing_events([(1, 1.0, 1.0, 0.0, 0.0)], 1, 2) == []


def test_multiple_corporate_actions_are_applied_sequentially():
    events = [
        (2, 1.0, 0.0, 0.0, 0.0),
        (3, 0.0, 1.0, 0.0, 0.0),
    ]
    adjusted_open, _, _, adjusted_close = _path(
        events,
        dates=(1, 2, 3),
        opens=(100.0, 99.0, 50.0),
        highs=(100.0, 99.0, 50.0),
        lows=(100.0, 99.0, 50.0),
        closes=(100.0, 99.0, 50.0),
    )
    assert adjusted_open == pytest.approx((49.5, 49.5, 50.0))
    assert adjusted_close == pytest.approx((49.5, 49.5, 50.0))
    assert len(_crossing_events(events, 1, 3)) == 2


def test_mfe_mae_crossing_ex_date_has_no_mechanical_false_jump():
    adjusted_open, adjusted_high, adjusted_low, _ = _path(
        [(2, 0.0, 1.0, 0.0, 0.0)],
        dates=(1, 2, 3),
        opens=(100.0, 50.0, 50.0),
        highs=(101.0, 50.5, 50.2),
        lows=(99.0, 49.5, 49.0),
        closes=(100.0, 50.0, 50.0),
    )
    entry = adjusted_open[0]
    assert (max(adjusted_high) / entry - 1.0) * 100 == pytest.approx(1.0)
    assert (min(adjusted_low) / entry - 1.0) * 100 == pytest.approx(-2.0)


def test_v2_artifacts_are_complete_and_preserve_v1_as_diagnostic():
    manifest_path = V2_DIR / "development_historical_returns_v2_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_hash = manifest.pop("manifest_sha256")
    canonical = json.dumps(manifest, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == expected_hash
    assert manifest["schema_version"] == "DEVELOPMENT_HISTORICAL_RETURNS_VALIDATION_V2"
    assert manifest["retrospective_status"] == "RECONSTRUCTED_RETROSPECTIVE"
    assert manifest["scope"]["signal_date_count"] == 769
    assert manifest["scope"]["qualified_signal_count"] == 8463
    assert manifest["provenance"]["core_output"]["replayed_for_v2"] is False
    assert manifest["provenance"]["v1_raw_diagnostic"]["preserved"] is True
    assert manifest["provenance"]["score_85_status"] == "UNVERIFIED"
    assert manifest["provenance"]["full_legacy_output_validation"] == "BLOCKED_HISTORICAL_SINA_MEMBERSHIP"
    assert manifest["provenance"]["final_oos_read"] is False
    assert manifest["strategy"]["parameter_changes"] is False
    assert manifest["strategy"]["promotion"] is False

    v1_manifest_path = V1_DIR / "development_historical_returns_manifest.json"
    assert hashlib.sha256(v1_manifest_path.read_bytes()).hexdigest() == manifest["provenance"]["v1_raw_diagnostic"]["manifest_file_sha256"]
    assert set(manifest["metrics"]) == {"1D", "3D", "5D", "10D"}
    assert set(manifest["difference_audit"]) == {"1D", "3D", "5D", "10D"}

    event_artifact = manifest["artifacts"]["event_results"]
    assert event_artifact["rows"] == 8463
    assert hashlib.sha256((ROOT / event_artifact["path"]).read_bytes()).hexdigest() == event_artifact["sha256"]

    audit_artifact = manifest["artifacts"]["v1_v2_difference_audit"]
    audit_path = ROOT / audit_artifact["path"]
    assert hashlib.sha256(audit_path.read_bytes()).hexdigest() == audit_artifact["sha256"]
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    expected_audit_hash = audit.pop("audit_sha256")
    audit_canonical = json.dumps(audit, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(audit_canonical.encode("utf-8")).hexdigest() == expected_audit_hash
    assert {
        horizon: audit["by_horizon"][horizon]["corporate_action_crossing_sample_count"]
        for horizon in ("1D", "3D", "5D", "10D")
    } == {"1D": 0, "3D": 48, "5D": 105, "10D": 271}
