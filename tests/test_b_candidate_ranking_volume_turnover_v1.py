"""High-value regressions for the blocked exact-baseline research gate."""
import gzip
import hashlib
import json
from pathlib import Path

import pytest

import b_candidate_ranking_volume_turnover_v1 as ranking


def write_stream(path, lines):
    with gzip.GzipFile(filename=str(path), mode="wb", mtime=0) as stream:
        stream.write(b"\n".join(lines) + b"\n")
    return path


def test_identity_scan_never_decodes_outcomes(tmp_path, monkeypatch):
    path = write_stream(tmp_path / "events.gz", [
        b'{"symbol":"600001.sh","signal_date":"2024-01-02","setup_id":"B","outcomes":{"opaque":"sealed-by-test"}}',
        b'{"symbol":"300001.sz","signal_date":"2024-01-02","setup_id":"B","outcomes":null}',
    ])
    def forbidden_decode(*args, **kwargs):
        pytest.fail("outcome-bearing rows must never be JSON-decoded")
    monkeypatch.setattr(ranking.json, "loads", forbidden_decode)
    audit, identities = ranking.scan_stream(path, identities=True)
    assert audit["rows"] == 2 and len(identities) == 2
    assert audit["rows_with_any_score_or_sector_key"] == 0
    assert audit["content_stream_sha256"] == hashlib.sha256(gzip.decompress(path.read_bytes())).hexdigest()


@pytest.mark.parametrize("line", [
    b'{"symbol":"600001.sh","signal_date":"2024-01-02"}',
    b'{"symbol":"600001.sh","signal_date":"2024-01-02","setup_id":"B","nested":{"symbol":"600002.sh"}}',
])
def test_missing_or_ambiguous_identity_fails_closed(tmp_path, line):
    with pytest.raises(RuntimeError, match="ambiguous/missing identity"):
        ranking.scan_stream(write_stream(tmp_path / "events.gz", [line]), identities=True)


def test_duplicate_identity_and_frozen_hash_mismatch_fail_closed(tmp_path):
    line = b'{"symbol":"600001.sh","signal_date":"2024-01-02","setup_id":"B"}'
    with pytest.raises(RuntimeError, match="duplicate qualified"):
        ranking.scan_stream(write_stream(tmp_path / "duplicate.gz", [line, line]), identities=True)
    actual, _ = ranking.scan_stream(write_stream(tmp_path / "events.gz", [line]))
    declared = {"rows": actual["rows"], "bytes": actual["bytes"], "sha256": "wrong",
                "content_sha256": actual["content_stream_sha256"]}
    with pytest.raises(RuntimeError, match="file_sha256"):
        ranking.verify_stream(actual, declared, stream_hash_key="content_sha256")


@pytest.mark.parametrize("key", ["score_total", "score", "score_85", "score_breakdown", "sector_rank", "sector_chg"])
def test_any_new_score_or_sector_evidence_requires_review(tmp_path, key):
    line = json.dumps({"nested": {key: 55}}).encode()
    audit, _ = ranking.scan_stream(write_stream(tmp_path / "events.gz", [line]))
    assert audit["rows_with_any_score_or_sector_key"] == 1


def test_delivered_blocker_has_null_metrics_and_preserves_boundaries():
    root = Path(__file__).resolve().parents[1]
    summary = json.loads((root / ranking.OUTPUT).read_text(encoding="utf-8"))
    assert summary["status"] == ranking.BLOCKER
    assert summary["decision"] == ranking.DECISION
    cohort = summary["cohort"]
    assert cohort["exact_baseline_missing_rows"] == cohort["qualified_rows"]
    assert sum(cohort["rows_by_board"].values()) == cohort["qualified_rows"]
    assert ranking._board_for_symbol("920001.bj") == "OUT_OF_SCOPE_PREFIX"
    assert cohort["rows_by_board"]["OUT_OF_SCOPE_PREFIX"] == 706
    assert cohort["ranking_evaluated_rows"] == cohort["ranking_evaluated_dates"] == 0
    assert all(model["Top1_increment_pp"] is None and model["mean_rank_ic"] is None
               for model in summary["models"].values())
    assert all(value is False or value == 0 for value in summary["boundaries"].values())


def test_same_qualified_b_can_have_seventeen_points_of_missing_sector_score():
    from b_breakout_retest_v1_1 import evaluate_candidate
    from test_a_platform_breakout import SYMBOL, _manifest
    from test_b_breakout_retest_v1_1 import _b_bars

    low = evaluate_candidate(_manifest(_b_bars(), sector_evidence={
        SYMBOL: {"sector_name": "synthetic", "sector_rank": 50, "sector_chg": -1.0}
    }), SYMBOL)
    high = evaluate_candidate(_manifest(_b_bars(), sector_evidence={
        SYMBOL: {"sector_name": "synthetic", "sector_rank": 1, "sector_chg": 2.0}
    }), SYMBOL)
    assert low.status == high.status == "QUALIFIED_LEGACY_BASELINE"
    assert low.level_plan == high.level_plan
    assert high.score_total - low.score_total == 17
