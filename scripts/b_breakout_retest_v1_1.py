"""Corrected, versioned reconstruction of the fixed V0 B rule.

The previous ``B_BREAKOUT_RETEST_LEGACY_V1`` remains historical evidence.  This
module has its own semantic spec and binds directly to the authoritative raw
V0 source identity.  Numeric calculations are shared with the audited B
calculator; sector resolution is implemented here because the old evaluator's
missing-sector hardening was not part of V0.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import replace
import copy
import math
from typing import Any

from a_platform_breakout import (
    CandidateEvaluation,
    FeatureSnapshot,
    INSUFFICIENT_DATA,
    LEGACY_SECTOR_PROVENANCE,
    MATCHED_REJECTED,
    NOT_MATCHED,
    QUALIFIED_LEGACY_BASELINE,
    StrategyInputError,
    _same_symbol,
    semantic_spec_sha256,
)
from b_breakout_retest import (
    ACCELERATION_OVEREXTENDED,
    GAIN_EXHAUSTED,
    REJECTED_CLOSE_TOO_LOW,
    REJECTED_NO_SUPPORT,
    REJECTED_OVERHANG_RR,
    REJECTED_RR,
    REJECTED_STOP_DISTANCE,
    SETUP_ID as B_SETUP_ID,
    _evaluate_arrays as _shared_evaluate_arrays,
    _base_result as _shared_base_result,
    evaluate_numeric_projection as _shared_numeric_projection,
)
from generation_contract import GenerationInputManifest, READY_FOR_STRATEGY_EVALUATION


STRATEGY_VERSION = "B_BREAKOUT_RETEST_LEGACY_V1_1"
B_BREAKOUT_RETEST_LEGACY_V1_1 = STRATEGY_VERSION
CORRECTED_FROM_STRATEGY_VERSION = "B_BREAKOUT_RETEST_LEGACY_V1"
SETUP_ID = B_SETUP_ID
V0_SOURCE_REPOSITORY = "EFSing/ashare_watchlist-V0"
V0_SOURCE_COMMIT = "c8406c393c0b135eafb0aec763576ae869fddcff"
V0_SOURCE_PATH = "ashare_watchlist/scripts/screen_system.py"
V0_SOURCE_FILE_SHA256 = "843935d9b86ec05af848ee8cc54812334475e3d17807cb93349a02c84896417a"
LEGACY_WINDOWS_CRLF_WORKING_TREE_SHA256 = "6cac746123e3151999cbeeb1a612868ef77b50af6c7c64b0d80eb387ae1d19f9"
LEGACY_PROVIDER_ORDER_LAST_WRITE_WINS_V1 = "LEGACY_PROVIDER_ORDER_LAST_WRITE_WINS_V1"


# This is intentionally an explicit B object.  It does not inherit A's
# generic sector contract, whose missing-sector semantics were not V0.
LEGACY_SPEC: dict[str, Any] = {
    "identity": {
        "strategy_version": STRATEGY_VERSION,
        "setup_id": SETUP_ID,
        "role": "CORRECTED_EXACT_V0_RECONSTRUCTION",
        "supersedes": CORRECTED_FROM_STRATEGY_VERSION,
    },
    "legacy_source": {
        "repository": V0_SOURCE_REPOSITORY,
        "commit": V0_SOURCE_COMMIT,
        "path": V0_SOURCE_PATH,
        "raw_file_sha256": V0_SOURCE_FILE_SHA256,
        "historical_crlf_working_tree_sha256": LEGACY_WINDOWS_CRLF_WORKING_TREE_SHA256,
        "rule_label": "B 突破回踩",
    },
    "input_contract": {
        "required_manifest_status": READY_FOR_STRATEGY_EVALUATION,
        "minimum_stock_bars": 120,
        "minimum_index_bars_for_chg5": 6,
        "numeric_validation": {"prices": ">0", "volume": ">=0", "finite_required": True},
        "sector_evidence": {
            "source": "V0 get_sectors() exact Sina industry membership",
            "required_fields_when_observed": ["sector_name", "sector_rank", "sector_chg"],
            "missing_symbol": {
                "sector_name": "-",
                "sector_rank": 50,
                "sector_chg": 0.0,
                "action": "CONTINUE_B_EVALUATION",
            },
            "multiple_memberships": {
                "resolution_policy": LEGACY_PROVIDER_ORDER_LAST_WRITE_WINS_V1,
                "provider_traversal": "stock_sector_spot label order, then detail member row order",
                "raw_memberships_retained": True,
            },
            "taxonomy_substitution": False,
        },
    },
    "b_match": {
        "scan_window": "range(max(61,n-15),n-1)",
        "first_qualifying_breakout_only": True,
        "breakout": {
            "base_hi": "max(close[i-60:i])",
            "close_above_base": "close[i]>base_hi",
            "volume": "volume[i]>=1.8*mean(volume[i-20:i])",
            "one_day_change": "close[i]/close[i-1]-1>=0.03",
        },
        "pullback": {
            "pull_volume": "mean(volume[i+1:]) if n-1>i+1 else volume[-1]",
            "near_platform": "abs(close/base_hi-1)<=0.04 or base_hi*0.97<=close<=base_hi*1.04",
            "close_floor": "close>=base_hi*0.97",
            "volume_contraction": "pull_volume<volume[i]*0.7",
            "turn_strength": "close>=close[-2] or close>=ma5",
        },
        "first_qualifying_breakout_failure": "return_no_match_after_first_breakout_pullback_failure",
        "output": "(B 突破回踩, base_hi)",
    },
    "hard_gates_in_order": [
        {"audit": "SECTOR_EVIDENCE_RESOLVED_OR_V0_DEFAULT", "pass": "observed evidence valid or no symbol mapping", "fail_status": INSUFFICIENT_DATA},
        {"audit": "CLOSE_GT_2", "pass": "close>2", "reject": "close<=2", "reject_reason": REJECTED_CLOSE_TOO_LOW},
        {"audit": "NO_ACCELERATION_OVEREXTENDED", "pass": "not(chg10>35 and bias20>15)", "reject_reason": ACCELERATION_OVEREXTENDED},
        {"audit": "NO_GAIN_EXHAUSTED", "pass": "not(pos250>0.9 and chg20>40)", "reject_reason": GAIN_EXHAUSTED},
        {"audit": "VALID_SUPPORT_EXISTS", "pass": "at least one support candidate < close", "reject_reason": REJECTED_NO_SUPPORT},
        {"audit": "RISK_IN_0_TO_9_PCT", "pass": "risk>0 and risk<=0.09", "reject_reason": REJECTED_STOP_DISTANCE},
        {"audit": "RR_GE_2", "pass": "rr>=2", "reject_reason": REJECTED_RR},
        {"audit": "OVERHANG_RR_COMBINATION_ACCEPTED", "pass": "not(overhang>0.5 and rr<2.5)", "reject_reason": REJECTED_OVERHANG_RR},
    ],
    "shared_numeric_semantics": {
        "features": {
            "ma5": "mean(close[-5:])",
            "ma20": "mean(close[-20:])",
            "vma20_prev": "mean(volume[-21:-1])",
            "chg1_pct": "(close[-1]/close[-2]-1)*100",
            "chg5_pct": "(close[-1]/close[-6]-1)*100",
            "chg10_pct": "(close[-1]/close[-11]-1)*100",
            "chg20_pct": "(close[-1]/close[-21]-1)*100",
            "bias20_pct": "(close/ma20-1)*100",
            "pos250": "(close-min(low[-250:]))/(max(high[-250:])-min(low[-250:])) else 0.5",
            "relative_strength": "chg5-index_chg5",
        },
        "support": "max(valid(ma20,base_hi,low_of_max_volume_bar_last_10,min(low[-20:])))",
        "stop": "round(support*0.98,2)",
        "risk": "(close-stop)/close",
        "target": "min(h60,volume_bin,hhv120) above close*1.03 else close*(1+2.5*risk)",
        "trigger": "round(max(base_hi,ma5),2)",
    },
    "score_85": {
        "calculation_stage": "qualified only",
        "strong_sector": {"max": 10, "rules": ["rank<=10:10", "rank<=20:6", "else:2"]},
        "relative_low": {"max": 15, "rules": ["pos250<0.35 and chg10<=30:15", "pos250<0.5:10", "pos250<0.65:5", "else:0"]},
        "volume_price_health": {"max": 15, "rules": ["ud_ratio>=1.3:8", "ud_ratio>=1.1:5", "else:2", "1.5<=vol_ratio_k<=4:4", "vol_ratio_k>4:2", "else:1", "B_setup:+2", "cap:15"]},
        "clear_support": {"max": 10, "rules": ["risk<=0.04:10", "risk<=0.06:6", "else:3"]},
        "five_day_strength": {"max": 5, "rules": ["close>ma5 and ma5>=mean(close[-6:-1]):5", "close>ma5:3", "else:0"]},
        "sector_linkage": {"max": 10, "rules": ["sector_chg>=1:10", "sector_chg>0:5", "else:1"]},
        "relative_strength": {"max": 10, "rules": ["rs>3:10", "rs>0:6", "else:2"]},
        "risk_reward": {"max": 10, "rules": ["rr>=3:10", "rr>=2.5:8", "else:5"]},
        "total": "sum(all eight items)",
        "score_cutoff": None,
        "top_n": None,
    },
    "selection": {"score_cutoff": None, "top_n": None, "strategy_selection": "no_score_filter_or_top_n"},
    "status_vocabulary": {
        NOT_MATCHED: "B breakout-retest conditions not all satisfied",
        INSUFFICIENT_DATA: "required numeric input incomplete; missing sector uses the V0 default tuple",
        MATCHED_REJECTED: "B matched but a legacy hard gate rejected",
        QUALIFIED_LEGACY_BASELINE: "B matched and all legacy hard gates passed",
    },
}

STRATEGY_SPEC_SHA256 = semantic_spec_sha256(LEGACY_SPEC)
STRATEGY_SPEC_HASH = STRATEGY_SPEC_SHA256


def strategy_spec_sha256() -> str:
    return STRATEGY_SPEC_SHA256


def _provenance(manifest: GenerationInputManifest) -> dict[str, Any]:
    return {
        "strategy_version": STRATEGY_VERSION,
        "spec_sha256": STRATEGY_SPEC_SHA256,
        "input_fingerprint": manifest.input_fingerprint,
        "as_of_date": manifest.run_context.as_of_date,
        "signal_date": manifest.signal_date,
        "earliest_execution_date": manifest.earliest_execution_date,
        "mode": manifest.run_context.mode,
        "timezone": manifest.run_context.timezone,
        "calendar": manifest.run_context.calendar,
        "adjustment_modes": sorted({x.adjustment_mode for x in (*manifest.stock_klines, manifest.index)}),
        "input_sector_source": manifest.sector.source,
        "legacy_sector_provenance": {
            **copy.deepcopy(LEGACY_SECTOR_PROVENANCE),
            "missing_symbol_default": {"sector_name": "-", "sector_rank": 50, "sector_chg": 0.0},
            "multiple_membership_resolution": LEGACY_PROVIDER_ORDER_LAST_WRITE_WINS_V1,
            "provider_traversal": "rank_input sequence preserves provider traversal order",
            "raw_memberships_retained_in_manifest": True,
        },
        "legacy_source": {
            "repository": V0_SOURCE_REPOSITORY,
            "commit": V0_SOURCE_COMMIT,
            "path": V0_SOURCE_PATH,
            "raw_file_sha256": V0_SOURCE_FILE_SHA256,
            "historical_crlf_working_tree_sha256": LEGACY_WINDOWS_CRLF_WORKING_TREE_SHA256,
        },
    }


def _relabel(result: CandidateEvaluation, manifest: GenerationInputManifest) -> CandidateEvaluation:
    return replace(result, strategy_version=STRATEGY_VERSION, provenance=_provenance(manifest))


def _sector_records(value: Any, symbol: str, *, mapping_key: Any = None) -> Iterator[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        record_symbol = value.get("symbol", value.get("code"))
        if (record_symbol is not None and _same_symbol(record_symbol, symbol)) or (
            mapping_key is not None and _same_symbol(mapping_key, symbol)
        ):
            yield value
        for key, child in value.items():
            yield from _sector_records(child, symbol, mapping_key=key)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _sector_records(child, symbol, mapping_key=mapping_key)


def _valid_sector_record(record: Mapping[str, Any]) -> tuple[str, float, float] | None:
    name = record.get("sector_name")
    rank = record.get("sector_rank")
    change = record.get("sector_chg")
    if (
        isinstance(name, str) and bool(name.strip())
        and isinstance(rank, (int, float)) and not isinstance(rank, bool)
        and math.isfinite(float(rank)) and float(rank) > 0
        and isinstance(change, (int, float)) and not isinstance(change, bool)
        and math.isfinite(float(change))
    ):
        return name.strip(), float(rank), float(change)
    return None


def _v0_sector_evidence(manifest: GenerationInputManifest, symbol: str) -> tuple[str, float, float]:
    """Resolve the last valid observed membership, or the exact V0 default."""

    records = list(_sector_records(manifest.sector.rank_input, symbol))
    if not records:
        records = list(_sector_records(manifest.sector.members, symbol))
    resolved: tuple[str, float, float] | None = None
    for record in records:
        candidate = _valid_sector_record(record)
        if candidate is not None:
            resolved = candidate
    return resolved if resolved is not None else ("-", 50.0, 0.0)


def _base_result(
    manifest: GenerationInputManifest,
    symbol: str,
    *,
    status: str,
    features: FeatureSnapshot | None = None,
    matched: Sequence[str] = (),
    failed: Sequence[str] = (),
    rejects: Sequence[str] = (),
) -> CandidateEvaluation:
    return _relabel(
        _shared_base_result(
            manifest,
            symbol,
            status=status,
            features=features,
            matched=matched,
            failed=failed,
            rejects=rejects,
        ),
        manifest,
    )


def _require_manifest(manifest: GenerationInputManifest) -> None:
    if not isinstance(manifest, GenerationInputManifest):
        raise StrategyInputError("manifest must be a GenerationInputManifest")
    if manifest.status != READY_FOR_STRATEGY_EVALUATION:
        raise StrategyInputError("strategy evaluation requires status=READY_FOR_STRATEGY_EVALUATION")


def evaluate_candidate(manifest: GenerationInputManifest, symbol: str) -> CandidateEvaluation:
    """Evaluate one symbol using exact V0 B numeric and sector semantics."""

    _require_manifest(manifest)
    normalized_symbol = str(symbol).strip().lower()
    kline_by_symbol = {item.symbol: item for item in manifest.stock_klines}
    if normalized_symbol not in kline_by_symbol:
        raise StrategyInputError(f"symbol is not present in manifest universe: {symbol}")
    item = kline_by_symbol[normalized_symbol]
    if item.bar_count < 120:
        return _base_result(manifest, normalized_symbol, status=INSUFFICIENT_DATA, failed=("MINIMUM_BARS_120",), rejects=(INSUFFICIENT_DATA,))
    quote = manifest.quote_snapshot.quotes.get(normalized_symbol)
    try:
        if quote is None:
            raise ValueError("quote is missing")
        if len(manifest.index.bars) < 6:
            raise ValueError("index has fewer than six bars")
        sector_name, sector_rank, sector_chg = _v0_sector_evidence(manifest, normalized_symbol)
        result = _shared_evaluate_arrays(
            manifest=manifest,
            symbol=normalized_symbol,
            bars=item.bars,
            quote=quote,
            sector_name=sector_name,
            sector_rank=sector_rank,
            sector_chg=sector_chg,
        )
        return _relabel(result, manifest)
    except (TypeError, ValueError, ZeroDivisionError):
        return _base_result(manifest, normalized_symbol, status=INSUFFICIENT_DATA, failed=("NUMERIC_INPUT_COMPLETE",), rejects=(INSUFFICIENT_DATA,))


def evaluate_universe(manifest: GenerationInputManifest) -> tuple[CandidateEvaluation, ...]:
    _require_manifest(manifest)
    return tuple(evaluate_candidate(manifest, symbol) for symbol in manifest.universe.symbols)


def evaluate_numeric_projection(
    *,
    symbol: str,
    signal_date: str,
    earliest_execution_date: str,
    bars: tuple[Any, Any, Any, Any],
    index_bars: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Reuse the sector-independent frozen projection path for impact audits."""

    return _shared_numeric_projection(
        symbol=symbol,
        signal_date=signal_date,
        earliest_execution_date=earliest_execution_date,
        bars=bars,
        index_bars=index_bars,
    )


def evaluate_batch(manifest: GenerationInputManifest) -> tuple[CandidateEvaluation, ...]:
    return evaluate_universe(manifest)


__all__ = [
    "B_BREAKOUT_RETEST_LEGACY_V1_1",
    "CORRECTED_FROM_STRATEGY_VERSION",
    "LEGACY_PROVIDER_ORDER_LAST_WRITE_WINS_V1",
    "LEGACY_SPEC",
    "LEGACY_WINDOWS_CRLF_WORKING_TREE_SHA256",
    "SETUP_ID",
    "STRATEGY_SPEC_HASH",
    "STRATEGY_SPEC_SHA256",
    "STRATEGY_VERSION",
    "V0_SOURCE_COMMIT",
    "V0_SOURCE_FILE_SHA256",
    "V0_SOURCE_PATH",
    "V0_SOURCE_REPOSITORY",
    "evaluate_batch",
    "evaluate_candidate",
    "evaluate_numeric_projection",
    "evaluate_universe",
    "semantic_spec_sha256",
    "strategy_spec_sha256",
]
