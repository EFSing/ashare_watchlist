import hashlib
import json
from pathlib import Path

import pytest

from validate_development_returns import _metric_summary


ROOT = Path(__file__).parents[1]
RETURNS_DIR = ROOT / "data" / "validation" / "core_signal_validation_continuous_parts" / "development_returns"


def test_metric_summary_reports_positive_rate_and_expectancy():
    records = [
        {"return_pct": 10.0, "mfe_pct": 12.0, "mae_pct": -1.0},
        {"return_pct": -4.0, "mfe_pct": 2.0, "mae_pct": -6.0},
        {"return_pct": 0.0, "mfe_pct": 1.0, "mae_pct": -2.0},
    ]

    summary = _metric_summary(records)

    assert summary["sample_count"] == 3
    assert summary["positive_count"] == 1
    assert summary["positive_rate"] == 1 / 3
    assert summary["mean_return_pct"] == 2.0
    assert summary["expectancy_pct"] == pytest.approx(2.0)
    assert summary["mean_mfe_pct"] == 5.0
    assert summary["mean_mae_pct"] == -3.0


def test_development_returns_artifact_is_complete_and_self_consistent():
    path = RETURNS_DIR / "development_historical_returns_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    expected_hash = manifest.pop("manifest_sha256")
    canonical = json.dumps(manifest, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))

    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == expected_hash
    assert manifest["status"] == "DEVELOPMENT_HISTORICAL_RETURNS_VALIDATION_COMPLETE"
    assert manifest["retrospective_status"] == "RECONSTRUCTED_RETROSPECTIVE"
    assert manifest["scope"]["signal_date_count"] == 769
    assert manifest["scope"]["qualified_signal_count"] == 8463
    assert manifest["provenance"]["final_oos_read"] is False
    assert manifest["provenance"]["score_85_status"] == "UNVERIFIED"
    assert manifest["provenance"]["full_legacy_output_validation"] == "BLOCKED_HISTORICAL_SINA_MEMBERSHIP"
    assert set(manifest["metrics"]) == {"1D", "3D", "5D", "10D"}

    event_artifact = manifest["artifacts"]["event_results"]
    event_path = ROOT / Path(event_artifact["path"])
    assert event_artifact["rows"] == 8463
    assert hashlib.sha256(event_path.read_bytes()).hexdigest() == event_artifact["sha256"]
