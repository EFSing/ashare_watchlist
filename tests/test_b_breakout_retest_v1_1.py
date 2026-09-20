from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from b_breakout_retest_v1_1 import (
    LEGACY_PROVIDER_ORDER_LAST_WRITE_WINS_V1,
    LEGACY_SPEC,
    LEGACY_WINDOWS_CRLF_WORKING_TREE_SHA256,
    STRATEGY_SPEC_SHA256,
    STRATEGY_VERSION,
    V0_SOURCE_COMMIT,
    V0_SOURCE_FILE_SHA256,
    V0_SOURCE_PATH,
    V0_SOURCE_REPOSITORY,
    evaluate_candidate,
    evaluate_numeric_projection,
    semantic_spec_sha256,
)
from test_a_platform_breakout import AS_OF, SYMBOL, _base_bars, _bar, _manifest
from b_breakout_retest import evaluate_numeric_projection as old_numeric_projection


def _b_bars() -> list[dict[str, object]]:
    bars = _base_bars()
    first_day = date.fromisoformat(AS_OF) - timedelta(days=259)
    bars[252] = _bar(first_day + timedelta(days=252), close=11.0, high=11.1, low=10.5, volume=200)
    for index in range(253, 259):
        bars[index] = _bar(first_day + timedelta(days=index), close=10.1, high=10.2, low=9.9, volume=100)
    bars[259] = _bar(date.fromisoformat(AS_OF), close=10.1, high=10.3, low=9.9, volume=150)
    return bars


def test_corrected_identity_binds_authoritative_raw_v0_and_explicit_semantics():
    assert STRATEGY_VERSION == "B_BREAKOUT_RETEST_LEGACY_V1_1"
    assert len(V0_SOURCE_FILE_SHA256) == 64
    assert len(LEGACY_WINDOWS_CRLF_WORKING_TREE_SHA256) == 64
    assert V0_SOURCE_REPOSITORY == "EFSing/ashare_watchlist-V0"
    assert V0_SOURCE_COMMIT == "c8406c393c0b135eafb0aec763576ae869fddcff"
    assert V0_SOURCE_PATH == "ashare_watchlist/scripts/screen_system.py"
    assert LEGACY_SPEC["input_contract"]["sector_evidence"]["missing_symbol"] == {
        "sector_name": "-",
        "sector_rank": 50,
        "sector_chg": 0.0,
        "action": "CONTINUE_B_EVALUATION",
    }
    assert LEGACY_SPEC["input_contract"]["sector_evidence"]["multiple_memberships"]["resolution_policy"] == (
        LEGACY_PROVIDER_ORDER_LAST_WRITE_WINS_V1
    )
    assert LEGACY_SPEC["score_85"]["score_cutoff"] is None
    assert LEGACY_SPEC["score_85"]["top_n"] is None
    assert semantic_spec_sha256(LEGACY_SPEC) == STRATEGY_SPEC_SHA256
    assert STRATEGY_SPEC_SHA256 != "5bbeb345ebd8883149138d2f29f8606f919949ae285aa2839fa337921dfc7112"


def test_corrected_evaluator_uses_v0_missing_sector_default_and_continues():
    result = evaluate_candidate(_manifest(_b_bars(), sector_evidence={}), SYMBOL)

    assert result.status == "QUALIFIED_LEGACY_BASELINE"
    assert result.features is not None
    assert result.features.sector_name == "-"
    assert result.features.sector_rank == 50
    assert result.features.sector_chg == 0.0
    assert result.provenance["strategy_version"] == STRATEGY_VERSION
    assert result.provenance["spec_sha256"] == STRATEGY_SPEC_SHA256
    assert result.provenance["legacy_sector_provenance"]["missing_symbol_default"] == {
        "sector_name": "-",
        "sector_rank": 50,
        "sector_chg": 0.0,
    }


def test_formal_b_does_not_require_or_synthesize_turnover():
    result = evaluate_candidate(
        _manifest(_b_bars(), quote_updates={"turnover": None}),
        SYMBOL,
    )

    assert result.status == "QUALIFIED_LEGACY_BASELINE"
    assert result.features is not None
    assert result.features.turnover is None
    assert "HIGH_TURNOVER" not in result.risk_flags


def test_corrected_evaluator_resolves_multi_sector_last_write_wins():
    sector_evidence = {
        SYMBOL: [
            {"sector_name": "银行", "sector_rank": 5, "sector_chg": 1.5},
            {"sector_name": "保险", "sector_rank": 21, "sector_chg": -1.0},
        ]
    }
    result = evaluate_candidate(_manifest(_b_bars(), sector_evidence=sector_evidence), SYMBOL)

    assert result.status == "QUALIFIED_LEGACY_BASELINE"
    assert result.features is not None
    assert result.features.sector_name == "保险"
    assert result.features.sector_rank == 21
    assert result.features.sector_chg == -1.0
    assert result.provenance["legacy_sector_provenance"]["multiple_membership_resolution"] == (
        LEGACY_PROVIDER_ORDER_LAST_WRITE_WINS_V1
    )


def test_corrected_numeric_projection_is_identical_to_old_sector_independent_path():
    bars = _b_bars()
    manifest = _manifest(bars)
    arrays = tuple(
        np.asarray([float(item[field]) for item in bars], dtype=float)
        for field in ("close", "volume", "high", "low")
    )
    kwargs = {
        "symbol": SYMBOL,
        "signal_date": AS_OF,
        "earliest_execution_date": manifest.earliest_execution_date or "",
        "bars": arrays,
        "index_bars": manifest.index.bars,
    }
    assert evaluate_numeric_projection(**kwargs) == old_numeric_projection(**kwargs)


def test_corrected_full_numeric_evaluation_surface_matches_historical_v1():
    from b_breakout_retest import evaluate_candidate as old_evaluate_candidate

    scenarios = [_b_bars()]
    failed_first = _b_bars()
    first_day = date.fromisoformat(AS_OF) - timedelta(days=259)
    failed_first[246] = _bar(first_day + timedelta(days=246), close=11.0, high=11.1, low=10.5, volume=200)
    for index in range(247, 252):
        failed_first[index] = _bar(first_day + timedelta(days=index), close=9.0, high=9.2, low=8.8, volume=100)
    failed_first[259] = _bar(date.fromisoformat(AS_OF), close=9.5, high=9.6, low=9.2, volume=150)
    scenarios.append(failed_first)

    for bars in scenarios:
        manifest = _manifest(bars)
        old_result = old_evaluate_candidate(manifest, SYMBOL)
        corrected_result = evaluate_candidate(manifest, SYMBOL)
        for field in (
            "input_fingerprint",
            "as_of_date",
            "signal_date",
            "earliest_execution_date",
            "symbol",
            "setup_id",
            "status",
            "features",
            "matched_conditions",
            "failed_conditions",
            "reject_reasons",
            "support",
            "trigger",
            "stop",
            "target",
            "target_type",
            "risk",
            "rr",
            "score_breakdown",
            "score_total",
            "risk_flags",
            "level_plan",
        ):
            assert getattr(corrected_result, field) == getattr(old_result, field)


def test_corrected_b_preserves_first_breakout_unconditional_stop():
    bars = _b_bars()
    first_day = date.fromisoformat(AS_OF) - timedelta(days=259)
    bars[246] = _bar(first_day + timedelta(days=246), close=11.0, high=11.1, low=10.5, volume=200)
    for index in range(247, 252):
        bars[index] = _bar(first_day + timedelta(days=index), close=9.0, high=9.2, low=8.8, volume=100)
    bars[259] = _bar(date.fromisoformat(AS_OF), close=9.5, high=9.6, low=9.2, volume=150)

    result = evaluate_candidate(_manifest(bars), SYMBOL)

    assert result.status == "NOT_MATCHED"
    assert "PULLBACK_CLOSE_GE_97_PCT_BASE" in result.failed_conditions
