"""Auditable A-platform breakout legacy baseline evaluator.

Research-only consumer of the Phase 2B frozen GenerationInputManifest. The
legacy V0 A-platform formulas are intentionally preserved; Phase 2C.1 only
hardens semantic provenance and gate-by-gate auditability.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields, is_dataclass
from typing import Any

import numpy as np

from generation_contract import GenerationInputManifest, READY_FOR_STRATEGY_EVALUATION

STRATEGY_VERSION = "A_PLATFORM_BREAKOUT_LEGACY_V1"
A_PLATFORM_BREAKOUT_LEGACY_V1 = STRATEGY_VERSION
SETUP_ID = "A_PLATFORM_BREAKOUT"

NOT_MATCHED = "NOT_MATCHED"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
MATCHED_REJECTED = "MATCHED_REJECTED"
QUALIFIED_LEGACY_BASELINE = "QUALIFIED_LEGACY_BASELINE"

ACCELERATION_OVEREXTENDED = "ACCELERATION_OVEREXTENDED"
GAIN_EXHAUSTED = "GAIN_EXHAUSTED"
REJECTED_CLOSE_TOO_LOW = "REJECTED_CLOSE_TOO_LOW"
REJECTED_NO_SUPPORT = "REJECTED_NO_SUPPORT"
REJECTED_STOP_DISTANCE = "REJECTED_STOP_DISTANCE"
REJECTED_RR = "REJECTED_RR"
REJECTED_OVERHANG_RR = "REJECTED_OVERHANG_RR"
MISSING_SECTOR_EVIDENCE = "MISSING_SECTOR_EVIDENCE"

MINIMUM_BARS = 120

# V0's sector source is part of the legacy output contract.  This is kept
# separate from LEGACY_SPEC so documenting the source taxonomy does not alter
# the frozen strategy-rule hash.
LEGACY_SECTOR_PROVENANCE = {
    "version": "V0",
    "getter": "get_sectors",
    "provider": "AKShare",
    "taxonomy": "新浪行业",
    "spot_method": "stock_sector_spot",
    "detail_method": "stock_sector_detail",
    "exact_legacy_taxonomy": True,
    "forbidden_substitutions": ["申万行业", "同花顺行业"],
}


class StrategyInputError(ValueError):
    """The evaluator was given something other than a ready Phase 2B input."""


def _canonical_json(value: Any) -> str:
    def normalize(item: Any) -> Any:
        if is_dataclass(item):
            return {f.name: normalize(getattr(item, f.name)) for f in fields(item)}
        if isinstance(item, Mapping):
            return {str(k): normalize(item[k]) for k in sorted(item, key=str)}
        if isinstance(item, (list, tuple)):
            return [normalize(child) for child in item]
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("evaluation data must not contain NaN or infinity")
        if isinstance(item, (str, int, float, bool)) or item is None:
            return item
        raise TypeError(f"unsupported evaluation value: {type(item).__name__}")

    return json.dumps(normalize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def semantic_spec_sha256(spec: Mapping[str, Any]) -> str:
    """Hash canonical semantic config only; source formatting/comments are irrelevant."""

    return hashlib.sha256(_canonical_json(spec).encode("utf-8")).hexdigest()


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {f.name: _jsonable(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(v) for v in value]
    return value


LEGACY_SPEC: dict[str, Any] = {
    "identity": {
        "strategy_version": STRATEGY_VERSION,
        "setup_id": SETUP_ID,
        "role": "RESEARCH_ONLY_LEGACY_BASELINE",
    },
    "input_contract": {
        "required_manifest_status": READY_FOR_STRATEGY_EVALUATION,
        "minimum_stock_bars": MINIMUM_BARS,
        "minimum_index_bars_for_chg5": 6,
        "numeric_validation": {"prices": ">0", "volume": ">=0", "finite_required": True},
        "sector_evidence": {
            "required_fields": ["sector_name", "sector_rank", "sector_chg"],
            "sector_name": "non-empty string",
            "sector_rank": "finite numeric > 0",
            "sector_chg": "finite numeric",
            "silent_fallback": False,
            "missing_status": INSUFFICIENT_DATA,
        },
    },
    "features": {
        "ma5": "mean(close[-5:])",
        "ma20": "mean(close[-20:])",
        "vma20_prev": "mean(volume[-21:-1])",
        "vol_ratio_k": "volume[-1]/vma20_prev if vma20_prev>0 else 0.0",
        "chg1_pct": "(close[-1]/close[-2]-1)*100",
        "chg5_pct": "(close[-1]/close[-6]-1)*100",
        "chg10_pct": "(close[-1]/close[-11]-1)*100",
        "chg20_pct": "(close[-1]/close[-21]-1)*100",
        "bias20_pct": "(close/ma20-1)*100",
        "llv250": "min(low[-250:])",
        "hhv250": "max(high[-250:])",
        "pos250": "(close-llv250)/(hhv250-llv250) if hhv250>llv250 else 0.5",
        "prev60_hi_c": "max(close[-61:-1])",
        "prev60_lo": "min(low[-61:-1])",
        "plat_range": "(max(high[-61:-1])-prev60_lo)/prev60_lo",
        "index_chg5_pct": "(index_close[-1]/index_close[-6]-1)*100",
        "relative_strength": "chg5-index_chg5",
        "ud_ratio": {
            "price_diff": "np.diff(close[-21:])",
            "volume_window": "volume[-20:]",
            "up_volume": "volume[-20:][diff>0]",
            "down_volume": "volume[-20:][diff<0]",
            "formula": "mean(up_volume)/mean(down_volume)",
            "fallback": 1.0,
            "fallback_when": "either side empty or mean(down_volume)<=0",
        },
    },
    "a_match": {
        "conditions_in_order": [
            {"audit": "PLATFORM_RANGE_LE_30_PCT", "lhs": "plat_range", "op": "<=", "rhs": 0.30},
            {"audit": "CLOSE_ABOVE_PREV_60_CLOSE_HIGH", "lhs": "close", "op": ">", "rhs": "prev60_hi_c"},
            {"audit": "VOLUME_RATIO_K_GE_1_8", "lhs": "vol_ratio_k", "op": ">=", "rhs": 1.8},
            {"audit": "CHG1_GE_3_PCT", "lhs": "chg1", "op": ">=", "rhs": 3.0},
            {"audit": "CLOSE_ABOVE_MA20", "lhs": "close", "op": ">", "rhs": "ma20"},
        ],
        "bp_price": "max(close[-61:-1])",
        "all_required": True,
    },
    "hard_gates_in_order": [
        {"audit": "SECTOR_EVIDENCE_COMPLETE", "pass": "all sector fields valid", "fail_status": INSUFFICIENT_DATA},
        {"audit": "CLOSE_GT_2", "pass": "close>2", "reject": "close<=2", "reject_reason": REJECTED_CLOSE_TOO_LOW},
        {"audit": "NO_ACCELERATION_OVEREXTENDED", "pass": "not(chg10>35 and bias20>15)", "reject": "chg10>35 and bias20>15", "reject_reason": ACCELERATION_OVEREXTENDED},
        {"audit": "NO_GAIN_EXHAUSTED", "pass": "not(pos250>0.9 and chg20>40)", "reject": "pos250>0.9 and chg20>40", "reject_reason": GAIN_EXHAUSTED},
        {"audit": "VALID_SUPPORT_EXISTS", "pass": "at least one support candidate < close", "reject_reason": REJECTED_NO_SUPPORT},
        {"audit": "RISK_IN_0_TO_9_PCT", "pass": "risk>0 and risk<=0.09", "reject": "risk<=0 or risk>0.09", "reject_reason": REJECTED_STOP_DISTANCE},
        {"audit": "RR_GE_2", "pass": "rr>=2", "reject": "rr<2", "reject_reason": REJECTED_RR},
        {"audit": "OVERHANG_RR_COMBINATION_ACCEPTED", "pass": "not(overhang>0.5 and rr<2.5)", "reject": "overhang>0.5 and rr<2.5", "reject_reason": REJECTED_OVERHANG_RR},
    ],
    "support_stop_risk": {
        "support_candidates_in_order": ["ma20", "bp_price", "low_of_max_volume_bar_in_last_10_bars", "min(low[-20:])"],
        "support_filter": {"op": "<", "rhs": "close"},
        "support_selection": "max(valid_supports)",
        "stop": {"formula": "round(support*0.98,2)", "rounding": "python_round_ndigits_2"},
        "risk": "(close-stop)/close",
        "risk_pass": "0<risk<=0.09",
    },
    "volume_price_distribution": {
        "window_bars": 120,
        "edges": "np.linspace(min(low[-120:]),max(high[-120:]),21)",
        "digitize": "np.digitize(close[-120:],bins)-1",
        "index_clip": [0, 19],
        "bin_count": 20,
        "aggregation": "sum volume[-120:] by clipped bin index",
        "volume_bin_tie_break": "ascending first on equal volume",
    },
    "overhang": {
        "buffer_multiplier": 1.02,
        "formula": "sum(vol_by_price[bins[:-1]>close*1.02])/sum(vol_by_price) if total_vol>0 else 0.0",
    },
    "target_rr_trigger": {
        "pressure_buffer_multiplier": 1.03,
        "target_candidates_in_order": [
            {"name": "h60", "formula": "max(high[-60:])", "include_if": "h60>close*1.03"},
            {"name": "volume_bin", "formula": "bins[argmax(vol_by_price) among bins[index]>close*1.03]", "include_if": "eligible above bins exist", "tie_break": "ascending first"},
            {"name": "hhv120", "formula": "max(high[-120:])", "include_if": "hhv120>close*1.03"},
        ],
        "pressure_target": "min(target_candidates)",
        "pressure_target_type": "PRESSURE",
        "no_pressure_target": "close*(1+2.5*risk)",
        "no_pressure_multiple_r": 2.5,
        "no_pressure_target_type": "TREND_2_5R",
        "rr": "(target-close)/(close-stop)",
        "rr_reject": "rr<2",
        "overhang_rr_reject": "overhang>0.5 and rr<2.5",
        "trigger": {"formula": "round(max(bp_price,ma5),2)", "rounding": "python_round_ndigits_2", "execution_semantics": "planned legacy trigger; earliest execution remains T+1"},
    },
    "score_85": {
        "calculation_stage": "qualified only",
        "strong_sector": {"max": 10, "rules": ["rank<=10:10", "rank<=20:6", "else:2"]},
        "relative_low": {"max": 15, "rules": ["pos250<0.35 and chg10<=30:15", "pos250<0.5:10", "pos250<0.65:5", "else:0"]},
        "volume_price_health": {"max": 15, "rules": ["ud_ratio>=1.3:8", "ud_ratio>=1.1:5", "else:2", "1.5<=vol_ratio_k<=4:4", "vol_ratio_k>4:2", "else:1", "A_setup:+3", "cap:15"]},
        "clear_support": {"max": 10, "rules": ["risk<=0.04:10", "risk<=0.06:6", "else:3"]},
        "five_day_strength": {"max": 5, "prior_five_mean": "mean(close[-6:-1])", "rules": ["close>ma5 and ma5>=prior_five_mean:5", "close>ma5:3", "else:0"]},
        "sector_linkage": {"max": 10, "rules": ["sector_chg>=1:10", "sector_chg>0:5", "else:1"]},
        "relative_strength": {"max": 10, "rs": "chg5-index_chg5", "rules": ["rs>3:10", "rs>0:6", "else:2"]},
        "risk_reward": {"max": 10, "rules": ["rr>=3:10", "rr>=2.5:8", "else:5"]},
        "total": "sum(all eight items)",
        "score_cutoff": None,
        "top_n": None,
    },
    "risk_flags": [
        {"flag": "HIGH_TURNOVER", "condition": "quote.turnover>10"},
        {"flag": "OVERHANG", "condition": "overhang>0.35"},
        {"flag": "TWENTY_DAY_GAIN", "condition": "chg20>30"},
    ],
    "status_vocabulary": {
        NOT_MATCHED: "A five conditions not all satisfied",
        INSUFFICIENT_DATA: "required coverage/numeric/sector evidence incomplete",
        MATCHED_REJECTED: "A matched but a legacy hard gate rejected",
        QUALIFIED_LEGACY_BASELINE: "A matched and all legacy hard gates passed",
    },
}
STRATEGY_SPEC_SHA256 = semantic_spec_sha256(LEGACY_SPEC)
STRATEGY_SPEC_HASH = STRATEGY_SPEC_SHA256


def strategy_spec_sha256() -> str:
    return STRATEGY_SPEC_SHA256


@dataclass(frozen=True)
class FeatureSnapshot:
    symbol: str
    close: float
    ma5: float
    ma20: float
    vma20_prev: float
    vol_ratio_k: float
    chg1: float
    chg5: float
    chg10: float
    chg20: float
    bias20: float
    llv250: float
    hhv250: float
    pos250: float
    prev60_hi_c: float
    prev60_lo: float
    plat_range: float
    ud_ratio: float
    vol_bar_lo: float
    h60: float
    hhv120: float
    overhang: float
    idx_chg5: float
    rs: float
    turnover: float | None
    sector_name: str
    sector_rank: float
    sector_chg: float
    bins: tuple[float, ...] = ()
    vol_by_price: tuple[float, ...] = ()
    target_candidates: tuple[float, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True)
class LevelPlan:
    support: float
    trigger: float
    stop: float
    target: float
    target_type: str
    risk: float
    rr: float
    overhang: float

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True)
class ScoreBreakdown:
    strong_sector: int
    relative_low: int
    volume_price_health: int
    clear_support: int
    five_day_strength: int
    sector_linkage: int
    relative_strength: int
    risk_reward: int
    total: int

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True)
class CandidateEvaluation:
    strategy_version: str
    input_fingerprint: str
    as_of_date: str
    signal_date: str
    earliest_execution_date: str
    symbol: str
    setup_id: str
    status: str
    features: FeatureSnapshot | None
    matched_conditions: tuple[str, ...]
    failed_conditions: tuple[str, ...]
    reject_reasons: tuple[str, ...]
    support: float | None
    trigger: float | None
    stop: float | None
    target: float | None
    target_type: str | None
    risk: float | None
    rr: float | None
    score_breakdown: ScoreBreakdown | None
    score_total: int | None
    risk_flags: tuple[str, ...]
    level_plan: LevelPlan | None
    provenance: Mapping[str, Any]
    evaluation_hash: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "evaluation_hash", _sha256(self.to_dict(include_hash=False)))

    @property
    def semantic_hash(self) -> str:
        return self.evaluation_hash

    @property
    def evaluation_provenance(self) -> Mapping[str, Any]:
        return self.provenance

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        payload = {
            "strategy_version": self.strategy_version,
            "input_fingerprint": self.input_fingerprint,
            "as_of_date": self.as_of_date,
            "signal_date": self.signal_date,
            "earliest_execution_date": self.earliest_execution_date,
            "symbol": self.symbol,
            "setup_id": self.setup_id,
            "status": self.status,
            "features": None if self.features is None else self.features.to_dict(),
            "matched_conditions": list(self.matched_conditions),
            "failed_conditions": list(self.failed_conditions),
            "reject_reasons": list(self.reject_reasons),
            "support": self.support,
            "trigger": self.trigger,
            "stop": self.stop,
            "target": self.target,
            "target_type": self.target_type,
            "risk": self.risk,
            "rr": self.rr,
            "score_breakdown": None if self.score_breakdown is None else self.score_breakdown.to_dict(),
            "score_total": self.score_total,
            "risk_flags": list(self.risk_flags),
            "level_plan": None if self.level_plan is None else self.level_plan.to_dict(),
            "provenance": copy.deepcopy(dict(self.provenance)),
        }
        if include_hash:
            payload["evaluation_hash"] = self.evaluation_hash
        return payload


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
        "legacy_sector_provenance": copy.deepcopy(LEGACY_SECTOR_PROVENANCE),
    }


def _base_result(
    manifest: GenerationInputManifest,
    symbol: str,
    *,
    status: str,
    features: FeatureSnapshot | None = None,
    matched: Sequence[str] = (),
    failed: Sequence[str] = (),
    rejects: Sequence[str] = (),
    level_plan: LevelPlan | None = None,
    score: ScoreBreakdown | None = None,
    risk_flags: Sequence[str] = (),
) -> CandidateEvaluation:
    return CandidateEvaluation(
        strategy_version=STRATEGY_VERSION,
        input_fingerprint=manifest.input_fingerprint or "",
        as_of_date=manifest.run_context.as_of_date,
        signal_date=manifest.signal_date,
        earliest_execution_date=manifest.earliest_execution_date or "",
        symbol=symbol,
        setup_id=SETUP_ID,
        status=status,
        features=features,
        matched_conditions=tuple(matched),
        failed_conditions=tuple(failed),
        reject_reasons=tuple(rejects),
        support=None if level_plan is None else level_plan.support,
        trigger=None if level_plan is None else level_plan.trigger,
        stop=None if level_plan is None else level_plan.stop,
        target=None if level_plan is None else level_plan.target,
        target_type=None if level_plan is None else level_plan.target_type,
        risk=None if level_plan is None else level_plan.risk,
        rr=None if level_plan is None else level_plan.rr,
        score_breakdown=score,
        score_total=None if score is None else score.total,
        risk_flags=tuple(risk_flags),
        level_plan=level_plan,
        provenance=_provenance(manifest),
    )


def _require_manifest(manifest: GenerationInputManifest) -> None:
    if not isinstance(manifest, GenerationInputManifest):
        raise StrategyInputError("manifest must be a GenerationInputManifest")
    if manifest.status != READY_FOR_STRATEGY_EVALUATION:
        raise StrategyInputError("strategy evaluation requires status=READY_FOR_STRATEGY_EVALUATION")


def _same_symbol(left: Any, right: str) -> bool:
    left_text, right_text = str(left).strip().lower(), str(right).strip().lower()
    if left_text == right_text:
        return True
    for prefix in ("sh", "sz", "bj"):
        if left_text.startswith(prefix) and left_text[len(prefix):] == right_text:
            return True
        if right_text.startswith(prefix) and right_text[len(prefix):] == left_text:
            return True
    return False


def _sector_record(value: Any, symbol: str, *, mapping_key: Any = None) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        record_symbol = value.get("symbol", value.get("code"))
        if record_symbol is not None and _same_symbol(record_symbol, symbol):
            return value
        if mapping_key is not None and _same_symbol(mapping_key, symbol):
            return value
        for key, child in value.items():
            found = _sector_record(child, symbol, mapping_key=key)
            if found is not None:
                return found
    elif isinstance(value, (list, tuple)):
        for child in value:
            found = _sector_record(child, symbol)
            if found is not None:
                return found
    return None


def _sector_evidence(manifest: GenerationInputManifest, symbol: str) -> tuple[str, float, float] | None:
    for container in (manifest.sector.rank_input, manifest.sector.members):
        record = _sector_record(container, symbol)
        if record is None:
            continue
        name, rank, change = record.get("sector_name"), record.get("sector_rank"), record.get("sector_chg")
        if (
            isinstance(name, str) and bool(name.strip())
            and isinstance(rank, (int, float)) and not isinstance(rank, bool)
            and math.isfinite(float(rank)) and float(rank) > 0
            and isinstance(change, (int, float)) and not isinstance(change, bool)
            and math.isfinite(float(change))
        ):
            return name.strip(), float(rank), float(change)
    return None


def _bar_number(bar: Mapping[str, Any], field_name: str) -> float:
    value = bar.get(field_name)
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"bar field {field_name} is not numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"bar field {field_name} is not numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"bar field {field_name} is not finite")
    return number


def _quote_number(quote: Mapping[str, Any], *names: str) -> float:
    for name in names:
        if name in quote:
            value = quote[name]
            if isinstance(value, bool):
                break
            try:
                number = float(value)
            except (TypeError, ValueError):
                break
            if math.isfinite(number):
                return number
    raise ValueError(f"quote is missing numeric field: {', '.join(names)}")


def _optional_quote_number(quote: Mapping[str, Any], *names: str) -> float | None:
    """Read an optional diagnostic quote field without changing B semantics."""

    for name in names:
        if name not in quote or quote[name] is None:
            continue
        value = quote[name]
        if isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if math.isfinite(number):
            return number
        return None
    return None


def _index_change(index_bars: Sequence[Mapping[str, Any]]) -> float:
    if len(index_bars) < 6:
        raise ValueError("index needs at least six bars for chg5")
    closes = [_bar_number(bar, "close") for bar in index_bars]
    if closes[-6] == 0:
        raise ValueError("index close[-6] must be non-zero")
    return (closes[-1] / closes[-6] - 1.0) * 100.0


def _volume_distribution(lows: np.ndarray, highs: np.ndarray, closes: np.ndarray, volumes: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    bins = np.linspace(float(np.min(lows[-120:])), float(np.max(highs[-120:])), 21)
    indices = np.clip(np.digitize(closes[-120:], bins) - 1, 0, 19)
    vol_by_price = np.zeros(20, dtype=float)
    for index, volume in zip(indices, volumes[-120:]):
        vol_by_price[int(index)] += float(volume)
    return bins, vol_by_price, indices


def _score(*, sector_rank: float, pos250: float, chg10: float, ud_ratio: float, vol_ratio_k: float, risk: float, close: float, ma5: float, prior_five_mean: float, sector_chg: float, rs: float, rr: float) -> ScoreBreakdown:
    strong_sector = 10 if sector_rank <= 10 else (6 if sector_rank <= 20 else 2)
    relative_low = 15 if pos250 < 0.35 and chg10 <= 30 else (10 if pos250 < 0.5 else (5 if pos250 < 0.65 else 0))
    volume_price_health = 8 if ud_ratio >= 1.3 else (5 if ud_ratio >= 1.1 else 2)
    volume_price_health += 4 if 1.5 <= vol_ratio_k <= 4 else (2 if vol_ratio_k > 4 else 1)
    volume_price_health = min(volume_price_health + 3, 15)
    clear_support = 10 if risk <= 0.04 else (6 if risk <= 0.06 else 3)
    five_day_strength = 5 if close > ma5 and ma5 >= prior_five_mean else (3 if close > ma5 else 0)
    sector_linkage = 10 if sector_chg >= 1 else (5 if sector_chg > 0 else 1)
    relative_strength = 10 if rs > 3 else (6 if rs > 0 else 2)
    risk_reward = 10 if rr >= 3 else (8 if rr >= 2.5 else 5)
    values = (strong_sector, relative_low, volume_price_health, clear_support, five_day_strength, sector_linkage, relative_strength, risk_reward)
    return ScoreBreakdown(strong_sector, relative_low, volume_price_health, clear_support, five_day_strength, sector_linkage, relative_strength, risk_reward, sum(values))


def evaluate_candidate(manifest: GenerationInputManifest, symbol: str) -> CandidateEvaluation:
    """Evaluate one stock from a ready frozen input manifest."""

    _require_manifest(manifest)
    normalized_symbol = str(symbol).strip().lower()
    kline_by_symbol = {item.symbol: item for item in manifest.stock_klines}
    if normalized_symbol not in kline_by_symbol:
        raise StrategyInputError(f"symbol is not present in manifest universe: {symbol}")

    item = kline_by_symbol[normalized_symbol]
    if item.bar_count < MINIMUM_BARS:
        return _base_result(manifest, normalized_symbol, status=INSUFFICIENT_DATA, failed=("MINIMUM_BARS_120",), rejects=(INSUFFICIENT_DATA,))

    quote = manifest.quote_snapshot.quotes.get(normalized_symbol)
    evidence = _sector_evidence(manifest, normalized_symbol)
    try:
        if quote is None:
            raise ValueError("quote is missing")
        # Turnover is a display/risk diagnostic only.  It is deliberately
        # optional because the current authoritative HiThink snapshot field
        # is traded amount, not turnover rate.  No formal B selection rule
        # consumes it.
        turnover = _optional_quote_number(quote, "turnover", "换手率")
        bars = item.bars
        if len(manifest.index.bars) < 6:
            raise ValueError("index has fewer than six bars")
        c = np.asarray([_bar_number(bar, "close") for bar in bars], dtype=float)
        v = np.asarray([_bar_number(bar, "volume") for bar in bars], dtype=float)
        hi = np.asarray([_bar_number(bar, "high") for bar in bars], dtype=float)
        lo = np.asarray([_bar_number(bar, "low") for bar in bars], dtype=float)
        if np.any(v < 0) or np.any(c <= 0) or np.any(hi <= 0) or np.any(lo <= 0):
            raise ValueError("kline prices must be positive and volumes non-negative")
        if evidence is None:
            return _base_result(manifest, normalized_symbol, status=INSUFFICIENT_DATA, failed=("SECTOR_EVIDENCE_COMPLETE",), rejects=(MISSING_SECTOR_EVIDENCE,))
        sector_name, sector_rank, sector_chg = evidence

        close = float(c[-1])
        ma5, ma20 = float(np.mean(c[-5:])), float(np.mean(c[-20:]))
        vma20_prev = float(np.mean(v[-21:-1]))
        vol_ratio_k = float(v[-1] / vma20_prev) if vma20_prev > 0 else 0.0
        chg1 = float((c[-1] / c[-2] - 1) * 100)
        chg5 = float((c[-1] / c[-6] - 1) * 100)
        chg10 = float((c[-1] / c[-11] - 1) * 100)
        chg20 = float((c[-1] / c[-21] - 1) * 100)
        bias20 = float((close / ma20 - 1) * 100)
        llv250, hhv250 = float(np.min(lo[-250:])), float(np.max(hi[-250:]))
        pos250 = float((close - llv250) / (hhv250 - llv250)) if hhv250 > llv250 else 0.5
        diff = np.diff(c[-21:])
        up_v, dn_v = v[-20:][diff > 0], v[-20:][diff < 0]
        ud_ratio = float(np.mean(up_v) / np.mean(dn_v)) if len(up_v) and len(dn_v) and np.mean(dn_v) > 0 else 1.0
        prev60_hi_c, prev60_lo = float(np.max(c[-61:-1])), float(np.min(lo[-61:-1]))
        plat_range = float((np.max(hi[-61:-1]) - prev60_lo) / prev60_lo)
        idx_chg5 = _index_change(manifest.index.bars)
        rs = float(chg5 - idx_chg5)

        condition_pairs = (
            ("PLATFORM_RANGE_LE_30_PCT", plat_range <= 0.30),
            ("CLOSE_ABOVE_PREV_60_CLOSE_HIGH", close > prev60_hi_c),
            ("VOLUME_RATIO_K_GE_1_8", vol_ratio_k >= 1.8),
            ("CHG1_GE_3_PCT", chg1 >= 3),
            ("CLOSE_ABOVE_MA20", close > ma20),
        )
        matched = [name for name, passed in condition_pairs if passed]
        failed = [name for name, passed in condition_pairs if not passed]

        bins, vol_by_price, _ = _volume_distribution(lo, hi, c, v)
        h60, hhv120 = float(np.max(hi[-60:])), float(np.max(hi[-120:]))
        total_vol = float(np.sum(vol_by_price))
        overhang = float(np.sum(vol_by_price[bins[:-1] > close * 1.02]) / total_vol) if total_vol > 0 else 0.0
        features = FeatureSnapshot(
            normalized_symbol, close, ma5, ma20, vma20_prev, vol_ratio_k,
            chg1, chg5, chg10, chg20, bias20, llv250, hhv250, pos250,
            prev60_hi_c, prev60_lo, plat_range, ud_ratio,
            float(lo[-10:][int(np.argmax(v[-10:]))]), h60, hhv120, overhang,
            idx_chg5, rs, turnover, sector_name, sector_rank, sector_chg,
            tuple(float(x) for x in bins), tuple(float(x) for x in vol_by_price), (),
        )
        if failed:
            return _base_result(manifest, normalized_symbol, status=NOT_MATCHED, features=features, matched=matched, failed=failed)

        matched.append("SECTOR_EVIDENCE_COMPLETE")
        if close <= 2:
            return _base_result(manifest, normalized_symbol, status=MATCHED_REJECTED, features=features, matched=matched, failed=("CLOSE_GT_2",), rejects=(REJECTED_CLOSE_TOO_LOW,))
        matched.append("CLOSE_GT_2")

        if chg10 > 35 and bias20 > 15:
            return _base_result(manifest, normalized_symbol, status=MATCHED_REJECTED, features=features, matched=matched, failed=("NO_ACCELERATION_OVEREXTENDED",), rejects=(ACCELERATION_OVEREXTENDED,))
        matched.append("NO_ACCELERATION_OVEREXTENDED")

        if pos250 > 0.9 and chg20 > 40:
            return _base_result(manifest, normalized_symbol, status=MATCHED_REJECTED, features=features, matched=matched, failed=("NO_GAIN_EXHAUSTED",), rejects=(GAIN_EXHAUSTED,))
        matched.append("NO_GAIN_EXHAUSTED")

        bp_price = prev60_hi_c
        support_candidates = [ma20, bp_price, features.vol_bar_lo, float(np.min(lo[-20:]))]
        valid_supports = [value for value in support_candidates if value < close]
        if not valid_supports:
            return _base_result(manifest, normalized_symbol, status=MATCHED_REJECTED, features=features, matched=matched, failed=("VALID_SUPPORT_EXISTS",), rejects=(REJECTED_NO_SUPPORT,))
        matched.append("VALID_SUPPORT_EXISTS")

        support = float(max(valid_supports))
        stop = round(support * 0.98, 2)
        risk = float((close - stop) / close)
        if risk <= 0 or risk > 0.09:
            return _base_result(manifest, normalized_symbol, status=MATCHED_REJECTED, features=features, matched=matched, failed=("RISK_IN_0_TO_9_PCT",), rejects=(REJECTED_STOP_DISTANCE,))
        matched.append("RISK_IN_0_TO_9_PCT")

        target_candidates: list[float] = []
        if h60 > close * 1.03:
            target_candidates.append(h60)
        above_bin_indices = [index for index in range(20) if bins[index] > close * 1.03]
        if above_bin_indices:
            peak_index = max(above_bin_indices, key=lambda index: vol_by_price[index])
            target_candidates.append(float(bins[peak_index]))
        if hhv120 > close * 1.03:
            target_candidates.append(hhv120)
        if target_candidates:
            target, target_type = float(min(target_candidates)), "PRESSURE"
        else:
            target, target_type = float(close * (1 + 2.5 * risk)), "TREND_2_5R"
        rr = float((target - close) / (close - stop))
        features = FeatureSnapshot(**{**features.__dict__, "target_candidates": tuple(target_candidates)})
        trigger = round(max(bp_price, ma5), 2)
        level_plan = LevelPlan(support, trigger, stop, target, target_type, risk, rr, overhang)

        if rr < 2:
            return _base_result(manifest, normalized_symbol, status=MATCHED_REJECTED, features=features, matched=matched, failed=("RR_GE_2",), rejects=(REJECTED_RR,), level_plan=level_plan)
        matched.append("RR_GE_2")

        if overhang > 0.5 and rr < 2.5:
            return _base_result(manifest, normalized_symbol, status=MATCHED_REJECTED, features=features, matched=matched, failed=("OVERHANG_RR_COMBINATION_ACCEPTED",), rejects=(REJECTED_OVERHANG_RR,), level_plan=level_plan)
        matched.append("OVERHANG_RR_COMBINATION_ACCEPTED")

        score = _score(
            sector_rank=sector_rank, pos250=pos250, chg10=chg10, ud_ratio=ud_ratio,
            vol_ratio_k=vol_ratio_k, risk=risk, close=close, ma5=ma5,
            prior_five_mean=float(np.mean(c[-6:-1])), sector_chg=sector_chg, rs=rs, rr=rr,
        )
        risk_flags: list[str] = []
        if turnover is not None and turnover > 10:
            risk_flags.append("HIGH_TURNOVER")
        if overhang > 0.35:
            risk_flags.append("OVERHANG")
        if chg20 > 30:
            risk_flags.append("TWENTY_DAY_GAIN")
        return _base_result(manifest, normalized_symbol, status=QUALIFIED_LEGACY_BASELINE, features=features, matched=matched, score=score, risk_flags=risk_flags, level_plan=level_plan)
    except (TypeError, ValueError, ZeroDivisionError):
        return _base_result(manifest, normalized_symbol, status=INSUFFICIENT_DATA, failed=("NUMERIC_INPUT_COMPLETE",), rejects=(INSUFFICIENT_DATA,))


def evaluate_universe(manifest: GenerationInputManifest) -> tuple[CandidateEvaluation, ...]:
    """Return stable per-symbol audits only; no selection, ranking, or publication."""

    _require_manifest(manifest)
    return tuple(evaluate_candidate(manifest, symbol) for symbol in manifest.universe.symbols)


def evaluate_batch(manifest: GenerationInputManifest) -> tuple[CandidateEvaluation, ...]:
    return evaluate_universe(manifest)


def evaluate_generation_inputs(manifest: GenerationInputManifest) -> tuple[CandidateEvaluation, ...]:
    return evaluate_universe(manifest)


def evaluate_a_platform(manifest: GenerationInputManifest, symbol: str) -> CandidateEvaluation:
    return evaluate_candidate(manifest, symbol)


def evaluate_manifest(manifest: GenerationInputManifest) -> tuple[CandidateEvaluation, ...]:
    return evaluate_universe(manifest)


__all__ = [
    "ACCELERATION_OVEREXTENDED", "A_PLATFORM_BREAKOUT_LEGACY_V1", "CandidateEvaluation",
    "FeatureSnapshot", "GAIN_EXHAUSTED", "INSUFFICIENT_DATA", "LEGACY_SPEC", "LevelPlan",
    "MATCHED_REJECTED", "MISSING_SECTOR_EVIDENCE", "NOT_MATCHED", "QUALIFIED_LEGACY_BASELINE",
    "REJECTED_CLOSE_TOO_LOW", "REJECTED_NO_SUPPORT", "REJECTED_OVERHANG_RR", "REJECTED_RR",
    "REJECTED_STOP_DISTANCE", "SETUP_ID", "ScoreBreakdown", "STRATEGY_SPEC_SHA256",
    "STRATEGY_SPEC_HASH", "STRATEGY_VERSION", "StrategyInputError", "evaluate_a_platform",
    "LEGACY_SECTOR_PROVENANCE", "evaluate_batch", "evaluate_candidate", "evaluate_generation_inputs", "evaluate_manifest",
    "evaluate_universe", "semantic_spec_sha256", "strategy_spec_sha256",
]
