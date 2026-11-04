"""User-visible rank, fair benchmark and research isolation regressions."""
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import b_priority_w2w3_volume_exploratory_v0 as study


def candidates():
    rows = []
    for day in ("2023-07-03", "2024-07-03", "2025-07-03", "2026-07-03"):
        for i in range(6):
            rows.append({"symbol": f"60000{i}.sh", "signal_date": day,
                         "setup_id": "B_BREAKOUT_RETEST", "board": "Main",
                         "breakout_date": "2023-06-30", "structure_state": study.strict.STATES[0],
                         "down_volume_share": 0.1 + i * 0.1,
                         "up_down_volume_ratio": 6.0 - i,
                         "pullback_volume_decay_ratio": 0.1 + i * 0.1,
                         "5D_return_pct": float(i), "5D_mfe_pct": 10.0, "5D_mae_pct": -5.0})
    return pd.DataFrame(rows)


def test_topk_boundary_ties_are_fractional_and_permutation_invariant():
    score = np.array([1.0, 1.0, 0.0, 0.0])
    values = np.array([10.0, -2.0, 100.0, -100.0])
    assert study.top_weights(score, 1) @ values == 4.0
    assert study.top_weights(score, 3).sum() == pytest.approx(1.0)
    permutation = [3, 1, 0, 2]
    assert study.top_weights(score[permutation], 1) @ values[permutation] == 4.0


def test_mathematically_equal_composites_remain_exact_ties():
    f = candidates().iloc[:6].copy()
    # Each row has the same sum of good ordinal ranks in a different order.
    f["down_volume_share"] = [0, 1, 2, 3, 4, 5]
    f["up_down_volume_ratio"] = [0, 1, 2, 3, 4, 5]
    f["pullback_volume_decay_ratio"] = 1.0
    ranked = study.quality(f)
    assert ranked.volume_quality.nunique() == 1
    assert (study.top_weights(ranked.volume_quality.to_numpy(), 1) == np.full(6, 1 / 6)).all()


def test_r3_transition_precedes_better_volume_and_has_matched_r0():
    f = candidates().iloc[:6].copy()
    f.loc[f.index[-1], "structure_state"] = study.TRANSITION
    valid = study.quality(study.metrics_for(f, "5D"))
    r2, _, _ = study.ranked_daily(valid, "R2")
    r3, _, _ = study.ranked_daily(valid, "R3")
    assert r2[1].iloc[0].return_pct == 0.0
    assert r3[1].iloc[0].return_pct == 5.0
    assert r3[1].iloc[0].base_return_pct == r2[1].iloc[0].base_return_pct == 2.5
    assert r2[1].iloc[0].n == r3[1].iloc[0].n == 6


def test_missing_outcomes_and_missing_volume_do_not_enter_either_side():
    f = candidates().iloc[:6].copy()
    f.loc[0, "5D_return_pct"] = np.nan
    f.loc[1, "down_volume_share"] = np.nan
    valid = study.quality(study.metrics_for(f, "5D").dropna(subset=list(study.FIELDS)))
    result, _, _ = study.ranked_daily(valid, "R2")
    assert result[1].iloc[0].return_pct == 2.0
    assert result[1].iloc[0].base_return_pct == 3.5
    assert result[1].iloc[0].n == 4
    assert result[5].empty


def test_dates_are_equally_weighted_despite_unequal_stock_counts():
    f = study.metrics_for(candidates(), "5D")
    first = f.iloc[:2].copy()
    second = pd.concat([f.iloc[6:12]] * 20, ignore_index=True)
    first["return_pct"], second["return_pct"] = 1.0, 11.0
    result = study.describe(study.daily_equal(pd.concat([first, second])))
    assert result["mean"]["return_pct"] == 6.0
    assert result["candidate_rows"] == 122
    assert result["eligible_dates"] == 2


def test_prototype_is_outcome_blind_and_uses_only_three_priority_labels():
    f = candidates()
    expected, preview = study.prototype(f)
    changed = f.copy()
    changed["5D_return_pct"] = 99999.0
    changed["old_score"] = -1.0
    actual, other_preview = study.prototype(changed)
    assert actual == expected and other_preview == preview
    assert {r["prototype_label"] for r in actual} == {"首选", "次选", "观察"}
    assert all("old_score" not in r for r in actual)
    assert "earliest" in preview and "median" in preview and "latest" in preview and "most_candidates" in preview


def test_single_candidate_is_observe_and_incomplete_volume_never_imputed():
    f = candidates().iloc[:6].copy()
    f.loc[1:, "down_volume_share"] = np.nan
    # Another eligible date allows deterministic demonstration date selection.
    f = pd.concat([f, candidates().iloc[6:12]], ignore_index=True)
    ranked, _ = study.prototype(f)
    first = [r for r in ranked if r["signal_date"] == "2023-07-03"]
    assert len(first) == 1
    assert first[0]["prototype_label"] == "观察"
    assert first[0]["priority_rank"] == 1


def test_delivered_artifact_identities_and_strict_decisions_are_separate():
    root = Path(__file__).resolve().parents[1]
    path = root / study.OUTPUT / "summary.json"
    if not path.exists():
        pytest.fail("exploratory delivery summary is required")
    result = json.loads(path.read_text(encoding="utf-8"))
    assert result["strict_status"] == "B_PRIORITY_RESEARCH_BLOCKED_BY_DATA_GAP"
    assert all(m.endswith("NEEDS_MORE_EVIDENCE") for m in result["strict_markers"])
    assert all(m.startswith("EXPLORATORY_") for m in result["exploratory_markers"])
    assert result["boundaries"]["final_oos"] == "SEALED / UNREAD"
    assert result["boundaries"]["production_semantics_change"] == 0
    for artifact in result["artifacts"].values():
        content = root / artifact["path"]
        assert study.file_sha256(content) == artifact["sha256"]
        with gzip.open(content, "rb") as stream:
            payload = stream.read()
        assert hashlib.sha256(payload).hexdigest() == artifact["content_stream_sha256"]
        assert len(payload.splitlines()) == artifact["rows"]
