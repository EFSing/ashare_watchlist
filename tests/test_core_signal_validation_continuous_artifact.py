import gzip
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
CHECKPOINT_DIR = ROOT / "data" / "validation" / "core_signal_validation_continuous_parts"
CHECKPOINT_PATH = CHECKPOINT_DIR / "core_signal_validation_resume_checkpoint.json"
FORBIDDEN_METRICS = {"return", "win_rate", "mfe", "mae", "pnl", "expectancy", "profit_factor"}


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _self_hash(payload: dict[str, object]) -> str:
    value = dict(payload)
    expected = value.pop("checkpoint_sha256")
    actual = hashlib.sha256(_canonical(value)).hexdigest()
    assert actual == expected
    return str(expected)


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_continuous_resume_checkpoint_is_self_consistent_and_core_only():
    root = _load(CHECKPOINT_PATH)
    assert root["schema_version"] == "CORE_SIGNAL_VALIDATION_RESUME_CHECKPOINT_V1"
    assert root["dataset_version"] == "core-signal-hithink-continuous-2023-06-30-to-2026-08-28-v1"
    assert root["signal_date_count"] == 769
    assert root["signal_dates_start"] == "2023-06-30"
    assert root["signal_dates_end"] == "2026-08-28"
    assert root["sector_score_status"] == "UNVERIFIED"
    assert root["full_legacy_output_validation"] == "BLOCKED_HISTORICAL_SINA_MEMBERSHIP"
    assert root["return_metrics_computed"] is False
    _self_hash(root)

    for ref in root["parts"]:
        checkpoint_path = ROOT / Path(ref["path"])
        assert checkpoint_path.exists()
        assert hashlib.sha256(checkpoint_path.read_bytes()).hexdigest() == ref["sha256"]
        checkpoint = _load(checkpoint_path)
        _self_hash(checkpoint)
        assert checkpoint["sector_semantics"]["historical_membership_included"] is False
        assert checkpoint["sector_semantics"]["sector_score_status"] == "UNVERIFIED"
        assert checkpoint["forbidden_scope"]["return_metrics_computed"] is False
        progress = checkpoint["progress"]
        expected = checkpoint["expected_candidate_count_by_date"]
        completed = progress["completed_signal_dates"]
        pending = progress["pending_signal_dates"]
        assert completed + pending == list(expected)
        assert progress["completed_date_count"] == len(completed)
        assert progress["expected_candidate_evaluations_completed"] == sum(expected[d] for d in completed)
        assert progress["partial_current_date"] == pending[0]
        assert checkpoint["resume"]["required_start_date"] == pending[0]
        assert checkpoint["interrupted_output"]["gzip_readable"] is False
        assert checkpoint["interrupted_output"]["rows_read"] > progress["expected_candidate_evaluations_completed"]
        assert checkpoint["completed_output"]["rows"] == progress["expected_candidate_evaluations_completed"]


def test_completed_checkpoint_streams_have_hash_coverage_and_no_forbidden_metrics():
    root = _load(CHECKPOINT_PATH)
    for ref in root["parts"]:
        checkpoint = _load(ROOT / Path(ref["path"]))
        output = checkpoint["completed_output"]
        output_path = ROOT / Path(output["path"])
        digest = hashlib.sha256()
        rows = 0
        dates: dict[str, int] = {}
        with gzip.open(output_path, "rt", encoding="utf-8", newline="") as handle:
            for line in handle:
                row = json.loads(line)
                assert "score_breakdown" not in row
                assert "score_total" not in row
                assert not any(metric in row for metric in FORBIDDEN_METRICS)
                digest.update(_canonical(row))
                dates[row["signal_date"]] = dates.get(row["signal_date"], 0) + 1
                rows += 1
        progress = checkpoint["progress"]
        expected = checkpoint["expected_candidate_count_by_date"]
        assert rows == output["rows"] == progress["expected_candidate_evaluations_completed"]
        assert dates == {d: expected[d] for d in progress["completed_signal_dates"]}
        assert digest.hexdigest() == output["projection_stream_sha256"]
        assert hashlib.sha256(output_path.read_bytes()).hexdigest() == output["sha256"]
