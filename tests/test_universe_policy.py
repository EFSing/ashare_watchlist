from __future__ import annotations

import json

import pytest

from b_breakout_retest_v1_1 import (
    STRATEGY_SPEC_SHA256,
    STRATEGY_VERSION as B_STRATEGY_VERSION,
    evaluate_candidate as evaluate_b_candidate,
    evaluate_universe as evaluate_b_universe,
)
from development_candidate import (
    B_STRATEGY_BINDING,
    DevelopmentCandidateStore,
    RUN_PUBLISHED,
    StrategyBinding,
)
from test_a_platform_breakout import _manifest
from test_b_breakout_retest_v1_1 import _b_bars
from universe_policy import (
    BOARD_CHINEXT,
    BOARD_MAIN,
    BOARD_STAR,
    BOARD_UNKNOWN,
    UNIVERSE_POLICY_MAIN_BOARD_ONLY_V1,
    build_board_policy_audit,
    classify_board,
    is_live_universe_eligible,
    universe_policy_metadata,
)
from watchlist_schema import load_watchlist


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [
        ("000001", BOARD_MAIN),
        ("001234", BOARD_MAIN),
        ("002123", BOARD_MAIN),
        ("003123", BOARD_MAIN),
        ("600000", BOARD_MAIN),
        ("601000", BOARD_MAIN),
        ("603000", BOARD_MAIN),
        ("605000", BOARD_MAIN),
        ("300001", BOARD_CHINEXT),
        ("301001", BOARD_CHINEXT),
        ("688001", BOARD_STAR),
        ("689001", BOARD_STAR),
        ("430001", BOARD_UNKNOWN),
        ("900001", BOARD_UNKNOWN),
    ],
)
def test_canonical_board_taxonomy_and_live_eligibility(symbol, expected):
    assert classify_board(symbol) == expected
    assert is_live_universe_eligible(symbol) is (expected == BOARD_MAIN)


def test_board_policy_audit_is_deterministic_and_excludes_non_main_boards():
    audit = build_board_policy_audit(["688001", "000001", "300001", "430001"])

    assert audit["classifier"] == "ASHARE_BOARD_TAXONOMY_V1"
    assert audit["policy"] == UNIVERSE_POLICY_MAIN_BOARD_ONLY_V1
    assert audit["board_counts"] == {"ChiNext": 1, "Main": 1, "STAR": 1, "Unknown": 1}
    assert audit["retained_count"] == 1
    assert audit["excluded_symbols"] == {
        "ChiNext": ["300001"],
        "STAR": ["688001"],
        "Unknown": ["430001"],
    }


def test_b_production_policy_filters_before_evaluator_and_preserves_b_values(tmp_path):
    symbols = ("000001", "300001", "688001")
    sector_evidence = {
        symbol: {"sector_name": "银行", "sector_rank": 5, "sector_chg": 1.5}
        for symbol in symbols
    }
    manifest = _manifest(_b_bars(), symbols=symbols, sector_evidence=sector_evidence)
    baseline = evaluate_b_candidate(manifest, "000001")
    assert baseline.status == "QUALIFIED_LEGACY_BASELINE"

    seen_universes: list[tuple[str, ...]] = []

    def evaluator(filtered_manifest):
        seen_universes.append(tuple(filtered_manifest.universe.symbols))
        return evaluate_b_universe(filtered_manifest)

    binding = StrategyBinding(
        strategy_version=B_STRATEGY_VERSION,
        strategy_spec_sha256=STRATEGY_SPEC_SHA256,
        qualification_status=B_STRATEGY_BINDING.qualification_status,
        buy_type=B_STRATEGY_BINDING.buy_type,
        evaluate_universe=evaluator,
    )
    result = DevelopmentCandidateStore(tmp_path).generate(
        manifest,
        names={"000001": "主板", "300001": "创业板", "688001": "科创板"},
        market_env={"level": "B", "score": 5, "detail": {}},
        strategy_binding=binding,
        input_provenance={
            "candidate": {"strategy_version": B_STRATEGY_VERSION, "spec_sha256": STRATEGY_SPEC_SHA256}
        },
    )

    assert result.status == RUN_PUBLISHED
    assert seen_universes == [("000001",)]
    payload = load_watchlist(result.output_path)
    assert payload["universe_policy"] == UNIVERSE_POLICY_MAIN_BOARD_ONLY_V1
    assert [item["code"] for item in payload["candidates"]] == ["000001"]
    candidate = payload["candidates"][0]
    assert candidate["score"] == baseline.score_total
    assert candidate["trigger"] == baseline.trigger
    assert candidate["stop"] == baseline.stop
    assert candidate["target"] == baseline.target
    assert candidate["rr"] == baseline.rr

    record = json.loads(result.run_manifest_path.read_text(encoding="utf-8"))
    assert record["universe_policy"] == UNIVERSE_POLICY_MAIN_BOARD_ONLY_V1
    assert record["generation_fingerprint_payload"]["universe_policy"] == universe_policy_metadata()
    assert record["input_manifest"]["universe"]["symbols"] == ["000001"]


def test_main_board_ranking_order_is_unchanged_within_retained_universe(tmp_path):
    symbols = ("600000", "000001")
    sector_evidence = {
        symbol: {"sector_name": "银行", "sector_rank": 5, "sector_chg": 1.5}
        for symbol in symbols
    }
    manifest = _manifest(_b_bars(), symbols=symbols, sector_evidence=sector_evidence)
    expected = [
        evaluation.symbol
        for evaluation in evaluate_b_universe(manifest)
        if evaluation.status == "QUALIFIED_LEGACY_BASELINE"
    ]

    result = DevelopmentCandidateStore(tmp_path).generate(
        manifest,
        names={"600000": "主板一", "000001": "主板二"},
        market_env={"level": "B", "score": 5, "detail": {}},
        strategy_binding=B_STRATEGY_BINDING,
        input_provenance={
            "candidate": {"strategy_version": B_STRATEGY_VERSION, "spec_sha256": STRATEGY_SPEC_SHA256}
        },
    )

    payload = load_watchlist(result.output_path)
    assert [item["code"] for item in payload["candidates"]] == expected


def test_old_watchlist_without_policy_remains_readable(tmp_path):
    path = tmp_path / "watchlist_20260827.json"
    path.write_text(
        json.dumps(
            {
                "date": "2026-08-27",
                "mode": "close",
                "market_env": {},
                "sectors": [],
                "candidates": [],
                "strategy_version": B_STRATEGY_VERSION,
            }
        ),
        encoding="utf-8",
    )

    loaded = load_watchlist(path)

    assert "universe_policy" not in loaded
    assert loaded["candidates"] == []


def test_policy_metadata_records_future_effective_boundary_and_b_spec_identity():
    metadata = universe_policy_metadata()

    assert metadata["name"] == UNIVERSE_POLICY_MAIN_BOARD_ONLY_V1
    assert metadata["allowed_boards"] == [BOARD_MAIN]
    assert metadata["excluded_boards"] == [BOARD_CHINEXT, BOARD_STAR]
    assert metadata["effective_from"] == "FIRST_GENUINE_T_CLOSE_RUN_AFTER_DEPLOYMENT"
    assert STRATEGY_SPEC_SHA256 == "f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd"
