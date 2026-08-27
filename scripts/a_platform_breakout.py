"""Auditable A-platform breakout legacy baseline evaluator.

This module is deliberately a research-only consumer of the Phase 2B
``GenerationInputManifest``.  It has no network access, no scheduler, no
historical replay path, and no watchlist writer.  The implementation keeps the
fixed V0 A-platform formulas while making their inputs, outcomes, and
provenance explicit.
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
# Readable public alias for callers that use the exact strategy-version name.
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


class StrategyInputError(ValueError):
    """The evaluator was given something other than a ready Phase 2B input."""


def _canonical_json(value: Any) -> str:
    def normalize(item: Any) -> Any:
        if is_dataclass(item):
            return {field.name: normalize(getattr(item, field.name)) for field in fields(item)}
        if isinstance(item, Mapping):
            return {str(key): normalize(item[key]) for key in sorted(item, key=str)}
        if isinstance(item, (list, tuple)):
            return [normalize(child) for child in item]
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("evaluation data must not contain NaN or infinity")
        if isinstance(item, (str, int, float, bool)) or item is None:
            return item
        raise TypeError(f"unsupported evaluation value: {type(item).__name__}")

    return json.dumps(
        normalize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {field.name: _jsonable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


# The spec payload is intentionally data, rather than executable configuration.
# Its hash is part of every evaluation's provenance and is independent of run
# timestamps or transport ordering.
LEGACY_SPEC: dict[str, Any] = {
    "strategy_version": STRATEGY_VERSION,
    "setup_id": SETUP_ID,
    "minimum_bars": MINIMUM_BARS,
    "a_setup": {
        "platform_range_lte": 0.30,
        "close_above_previous_60_close_high": True,
        "volume_ratio_gte": 1.8,
        "one_day_change_gte_pct": 3.0,
        "close_above_ma20": True,
        "breakout_price": "max(close[-61:-1])",
    },
    "hard_rejects": {
        "close_lte": 2.0,
        "acceleration": "chg10 > 35 and bias20 > 15",
        "gain_exhausted": "pos250 > 0.9 and chg20 > 40",
        "risk_max": 0.09,
        "rr_min": 2.0,
        "overhang_rr": "overhang > 0.5 and rr < 2.5",
    },
    "levels": {
        "stop_multiplier": 0.98,
        "pressure_buffer": 1.03,
        "overhang_buffer": 1.02,
        "trend_multiple": 2.5,
        "volume_bins": 20,
        "volume_window": 120,
    },
    "score": {
        "strong_sector": "rank <= 10: 10; rank <= 20: 6; else: 2",
        "relative_low": "pos250 < .35 and chg10 <= 30: 15; pos250 < .5: 10; pos250 < .65: 5; else: 0",
        "volume_price_health": "ud_ratio thresholds 1.3/1.1; volume ratio ranges 1.5..4/>4; A setup +3; cap 15",
        "clear_support": "risk <= .04: 10; risk <= .06: 6; else: 3",
        "five_day_strength": "close > ma5 and ma5 >= mean(close[-6:-1]): 5; close > ma5: 3; else: 0",
        "sector_linkage": "sector_chg >= 1: 10; sector_chg > 0: 5; else: 1",
        "relative_strength": "rs > 3: 10; rs > 0: 6; else: 2",
        "risk_reward": "rr >= 3: 10; rr >= 2.5: 8; else: 5",
    },
    "risk_flags": {
        "high_turnover": "quote.turnover > 10",
        "overhang": "overhang > .35",
        "twenty_day_gain": "chg20 > 30",
    },
}
STRATEGY_SPEC_SHA256 = _sha256(LEGACY_SPEC)
STRATEGY_SPEC_HASH = STRATEGY_SPEC_SHA256


def strategy_spec_sha256() -> str:
    """Return the deterministic SHA-256 of the fixed legacy rule spec."""

    return STRATEGY_SPEC_SHA256


@dataclass(frozen=True)
class FeatureSnapshot:
    """All scalar and volume-distribution features used by the evaluator."""

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
    turnover: float
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
    """The legacy support, stop, trigger, target, and risk/return plan."""

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
    """The complete eight-part legacy 85-point score."""

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
    """One deterministic, audit-oriented result for one symbol."""

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
        semantic_payload = self.to_dict(include_hash=False)
        object.__setattr__(self, "evaluation_hash", _sha256(semantic_payload))

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
            "score_breakdown": None
            if self.score_breakdown is None
            else self.score_breakdown.to_dict(),
            "score_total": self.score_total,
            "risk_flags": list(self.risk_flags),
            "level_plan": None if self.level_plan is None else self.level_plan.to_dict(),
            "provenance": copy.deepcopy(dict(self.provenance)),
        }
        if include_hash:
            payload["evaluation_hash"] = self.evaluation_hash
        return payload


def _provenance(manifest: GenerationInputManifest) -> dict[str, Any]:
    """Build semantic provenance without retrieved-at timestamps."""

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
        "adjustment_modes": sorted(
            {item.adjustment_mode for item in (*manifest.stock_klines, manifest.index)}
        ),
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
        raise StrategyInputError(
            "strategy evaluation requires status=READY_FOR_STRATEGY_EVALUATION"
        )


def _same_symbol(left: Any, right: str) -> bool:
    left_text = str(left).strip().lower()
    right_text = str(right).strip().lower()
    if left_text == right_text:
        return True
    for prefix in ("sh", "sz", "bj"):
        if left_text.startswith(prefix) and left_text[len(prefix) :] == right_text:
            return True
        if right_text.startswith(prefix) and right_text[len(prefix) :] == left_text:
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
    """Read explicit per-stock evidence; never invent rank or change values."""

    for container in (manifest.sector.rank_input, manifest.sector.members):
        record = _sector_record(container, symbol)
        if record is None:
            continue
        name = record.get("sector_name")
        rank = record.get("sector_rank")
        change = record.get("sector_chg")
        if (
            isinstance(name, str)
            and bool(name.strip())
            and isinstance(rank, (int, float))
            and not isinstance(rank, bool)
            and math.isfinite(float(rank))
            and float(rank) > 0
            and isinstance(change, (int, float))
            and not isinstance(change, bool)
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


def _index_change(index_bars: Sequence[Mapping[str, Any]]) -> float:
    if len(index_bars) < 6:
        raise ValueError("index needs at least six bars for chg5")
    closes = [_bar_number(bar, "close") for bar in index_bars]
    if closes[-6] == 0:
        raise ValueError("index close[-6] must be non-zero")
    return (closes[-1] / closes[-6] - 1.0) * 100.0


def _volume_distribution(
    lows: np.ndarray, highs: np.ndarray, closes: np.ndarray, volumes: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    bins = np.linspace(float(np.min(lows[-120:])), float(np.max(highs[-120:])), 21)
    indices = np.clip(np.digitize(closes[-120:], bins) - 1, 0, 19)
    vol_by_price = np.zeros(20, dtype=float)
    for index, volume in zip(indices, volumes[-120:]):
        vol_by_price[int(index)] += float(volume)
    return bins, vol_by_price, indices


def _score(
    *,
    sector_rank: float,
    pos250: float,
    chg10: float,
    ud_ratio: float,
    vol_ratio_k: float,
    risk: float,
    close: float,
    ma5: float,
    prior_five_mean: float,
    sector_chg: float,
    rs: float,
    rr: float,
) -> ScoreBreakdown:
    strong_sector = 10 if sector_rank <= 10 else (6 if sector_rank <= 20 else 2)
    relative_low = (
        15
        if pos250 < 0.35 and chg10 <= 30
        else (10 if pos250 < 0.5 else (5 if pos250 < 0.65 else 0))
    )
    volume_price_health = 8 if ud_ratio >= 1.3 else (5 if ud_ratio >= 1.1 else 2)
    volume_price_health += 4 if 1.5 <= vol_ratio_k <= 4 else (2 if vol_ratio_k > 4 else 1)
    volume_price_health += 3
    volume_price_health = min(volume_price_health, 15)
    clear_support = 10 if risk <= 0.04 else (6 if risk <= 0.06 else 3)
    five_day_strength = (
        5
        if close > ma5 and ma5 >= prior_five_mean
        else (3 if close > ma5 else 0)
    )
    sector_linkage = 10 if sector_chg >= 1 else (5 if sector_chg > 0 else 1)
    relative_strength = 10 if rs > 3 else (6 if rs > 0 else 2)
    risk_reward = 10 if rr >= 3 else (8 if rr >= 2.5 else 5)
    total = sum(
        (
            strong_sector,
            relative_low,
            volume_price_health,
            clear_support,
            five_day_strength,
            sector_linkage,
            relative_strength,
            risk_reward,
        )
    )
    return ScoreBreakdown(
        strong_sector=strong_sector,
        relative_low=relative_low,
        volume_price_health=volume_price_health,
        clear_support=clear_support,
        five_day_strength=five_day_strength,
        sector_linkage=sector_linkage,
        relative_strength=relative_strength,
        risk_reward=risk_reward,
        total=total,
    )


def evaluate_candidate(manifest: GenerationInputManifest, symbol: str) -> CandidateEvaluation:
    """Evaluate one stock from a ready frozen input manifest."""

    _require_manifest(manifest)
    normalized_symbol = str(symbol).strip().lower()
    kline_by_symbol = {item.symbol: item for item in manifest.stock_klines}
    if normalized_symbol not in kline_by_symbol:
        raise StrategyInputError(f"symbol is not present in manifest universe: {symbol}")

    item = kline_by_symbol[normalized_symbol]
    if item.bar_count < MINIMUM_BARS:
        return _base_result(
            manifest,
            normalized_symbol,
            status=INSUFFICIENT_DATA,
            failed=("MINIMUM_BARS_120",),
            rejects=(INSUFFICIENT_DATA,),
        )

    quote = manifest.quote_snapshot.quotes.get(normalized_symbol)
    evidence = _sector_evidence(manifest, normalized_symbol)
    try:
        if quote is None:
            raise ValueError("quote is missing")
        turnover = _quote_number(quote, "turnover", "换手率")
        bars = item.bars
        index_bars = manifest.index.bars
        if len(index_bars) < 6:
            raise ValueError("index has fewer than six bars")
        c = np.asarray([_bar_number(bar, "close") for bar in bars], dtype=float)
        v = np.asarray([_bar_number(bar, "volume") for bar in bars], dtype=float)
        hi = np.asarray([_bar_number(bar, "high") for bar in bars], dtype=float)
        lo = np.asarray([_bar_number(bar, "low") for bar in bars], dtype=float)
        if np.any(v < 0) or np.any(c <= 0) or np.any(hi <= 0) or np.any(lo <= 0):
            raise ValueError("kline prices and volumes must be positive")
        if evidence is None:
            return _base_result(
                manifest,
                normalized_symbol,
                status=INSUFFICIENT_DATA,
                failed=("SECTOR_EVIDENCE_COMPLETE",),
                rejects=(MISSING_SECTOR_EVIDENCE,),
            )
        sector_name, sector_rank, sector_chg = evidence

        close = float(c[-1])
        ma5 = float(np.mean(c[-5:]))
        ma20 = float(np.mean(c[-20:]))
        vma20_prev = float(np.mean(v[-21:-1]))
        vol_ratio_k = float(v[-1] / vma20_prev) if vma20_prev > 0 else 0.0
        chg1 = float((c[-1] / c[-2] - 1) * 100)
        chg5 = float((c[-1] / c[-6] - 1) * 100)
        chg10 = float((c[-1] / c[-11] - 1) * 100)
        chg20 = float((c[-1] / c[-21] - 1) * 100)
        bias20 = float((close / ma20 - 1) * 100)
        llv250 = float(np.min(lo[-250:]))
        hhv250 = float(np.max(hi[-250:]))
        pos250 = float((close - llv250) / (hhv250 - llv250)) if hhv250 > llv250 else 0.5
        diff = np.diff(c[-21:])
        up_v = v[-20:][diff > 0]
        dn_v = v[-20:][diff < 0]
        ud_ratio = (
            float(np.mean(up_v) / np.mean(dn_v))
            if len(up_v) and len(dn_v) and np.mean(dn_v) > 0
            else 1.0
        )
        prev60_hi_c = float(np.max(c[-61:-1]))
        prev60_lo = float(np.min(lo[-61:-1]))
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
        h60 = float(np.max(hi[-60:]))
        hhv120 = float(np.max(hi[-120:]))
        total_vol = float(np.sum(vol_by_price))
        overhang = (
            float(np.sum(vol_by_price[bins[:-1] > close * 1.02]) / total_vol)
            if total_vol > 0
            else 0.0
        )
        features = FeatureSnapshot(
            symbol=normalized_symbol,
            close=close,
            ma5=ma5,
            ma20=ma20,
            vma20_prev=vma20_prev,
            vol_ratio_k=vol_ratio_k,
            chg1=chg1,
            chg5=chg5,
            chg10=chg10,
            chg20=chg20,
            bias20=bias20,
            llv250=llv250,
            hhv250=hhv250,
            pos250=pos250,
            prev60_hi_c=prev60_hi_c,
            prev60_lo=prev60_lo,
            plat_range=plat_range,
            ud_ratio=ud_ratio,
            vol_bar_lo=float(lo[-10:][int(np.argmax(v[-10:]))]),
            h60=h60,
            hhv120=hhv120,
            overhang=overhang,
            idx_chg5=idx_chg5,
            rs=rs,
            turnover=turnover,
            sector_name=sector_name,
            sector_rank=sector_rank,
            sector_chg=sector_chg,
            bins=tuple(float(value) for value in bins),
            vol_by_price=tuple(float(value) for value in vol_by_price),
            target_candidates=(),
        )
        if failed:
            return _base_result(
                manifest,
                normalized_symbol,
                status=NOT_MATCHED,
                features=features,
                matched=matched,
                failed=failed,
            )

        matched.append("SECTOR_EVIDENCE_COMPLETE")
        if close <= 2:
            return _base_result(
                manifest,
                normalized_symbol,
                status=MATCHED_REJECTED,
                features=features,
                matched=matched,
                failed=("CLOSE_GT_2",),
                rejects=(REJECTED_CLOSE_TOO_LOW,),
            )
        if chg10 > 35 and bias20 > 15:
            return _base_result(
                manifest,
                normalized_symbol,
                status=MATCHED_REJECTED,
                features=features,
                matched=matched,
                failed=("NOT_ACCELERATION_OVEREXTENDED",),
                rejects=(ACCELERATION_OVEREXTENDED,),
            )
        if pos250 > 0.9 and chg20 > 40:
            return _base_result(
                manifest,
                normalized_symbol,
                status=MATCHED_REJECTED,
                features=features,
                matched=matched,
                failed=("NOT_GAIN_EXHAUSTED",),
                rejects=(GAIN_EXHAUSTED,),
            )

        bp_price = prev60_hi_c
        support_candidates = [ma20, bp_price, features.vol_bar_lo, float(np.min(lo[-20:]))]
        valid_supports = [value for value in support_candidates if value < close]
        if not valid_supports:
            return _base_result(
                manifest,
                normalized_symbol,
                status=MATCHED_REJECTED,
                features=features,
                matched=matched,
                failed=("VALID_SUPPORT_EXISTS",),
                rejects=(REJECTED_NO_SUPPORT,),
            )
        support = float(max(valid_supports))
        stop = round(support * 0.98, 2)
        risk = float((close - stop) / close)
        if risk <= 0 or risk > 0.09:
            return _base_result(
                manifest,
                normalized_symbol,
                status=MATCHED_REJECTED,
                features=features,
                matched=matched,
                failed=("RISK_IN_0_TO_9_PCT",),
                rejects=(REJECTED_STOP_DISTANCE,),
            )

        target_candidates: list[float] = []
        if h60 > close * 1.03:
            target_candidates.append(h60)
        above_bin_indices = [
            index for index in range(20) if bins[index] > close * 1.03
        ]
        if above_bin_indices:
            # ``max`` keeps the first index on a volume tie, matching the
            # ascending ``above_bins`` list in the fixed V0 script.
            peak_index = max(above_bin_indices, key=lambda index: vol_by_price[index])
            target_candidates.append(float(bins[peak_index]))
        if hhv120 > close * 1.03:
            target_candidates.append(hhv120)
        if target_candidates:
            target = float(min(target_candidates))
            target_type = "PRESSURE"
        else:
            target = float(close * (1 + 2.5 * risk))
            target_type = "TREND_2_5R"
        denominator = close - stop
        rr = float((target - close) / denominator)
        features = FeatureSnapshot(
            **{
                **features.__dict__,
                "target_candidates": tuple(target_candidates),
            }
        )
        trigger = round(max(bp_price, ma5), 2)
        level_plan = LevelPlan(
            support=support,
            trigger=trigger,
            stop=stop,
            target=target,
            target_type=target_type,
            risk=risk,
            rr=rr,
            overhang=overhang,
        )
        if rr < 2:
            return _base_result(
                manifest,
                normalized_symbol,
                status=MATCHED_REJECTED,
                features=features,
                matched=matched,
                failed=("RR_GE_2",),
                rejects=(REJECTED_RR,),
                level_plan=level_plan,
            )
        if overhang > 0.5 and rr < 2.5:
            return _base_result(
                manifest,
                normalized_symbol,
                status=MATCHED_REJECTED,
                features=features,
                matched=matched,
                failed=("OVERHANG_RR_COMBINATION_ACCEPTED",),
                rejects=(REJECTED_OVERHANG_RR,),
                level_plan=level_plan,
            )

        score = _score(
            sector_rank=sector_rank,
            pos250=pos250,
            chg10=chg10,
            ud_ratio=ud_ratio,
            vol_ratio_k=vol_ratio_k,
            risk=risk,
            close=close,
            ma5=ma5,
            prior_five_mean=float(np.mean(c[-6:-1])),
            sector_chg=sector_chg,
            rs=rs,
            rr=rr,
        )
        risk_flags: list[str] = []
        if turnover > 10:
            risk_flags.append("HIGH_TURNOVER")
        if overhang > 0.35:
            risk_flags.append("OVERHANG")
        if chg20 > 30:
            risk_flags.append("TWENTY_DAY_GAIN")
        matched.extend(
            (
                "CLOSE_GT_2",
                "NO_ACCELERATION_OVEREXTENDED",
                "NO_GAIN_EXHAUSTED",
                "VALID_SUPPORT_EXISTS",
                "RISK_IN_0_TO_9_PCT",
                "RR_GE_2",
                "OVERHANG_RR_COMBINATION_ACCEPTED",
            )
        )
        return _base_result(
            manifest,
            normalized_symbol,
            status=QUALIFIED_LEGACY_BASELINE,
            features=features,
            matched=matched,
            score=score,
            risk_flags=risk_flags,
            level_plan=level_plan,
        )
    except (TypeError, ValueError, ZeroDivisionError):
        return _base_result(
            manifest,
            normalized_symbol,
            status=INSUFFICIENT_DATA,
            failed=("NUMERIC_INPUT_COMPLETE",),
            rejects=(INSUFFICIENT_DATA,),
        )


def evaluate_universe(manifest: GenerationInputManifest) -> tuple[CandidateEvaluation, ...]:
    """Evaluate every frozen-universe stock in stable symbol order.

    This returns audit evaluations only.  It deliberately has no ranking,
    score cut, TOP N, portfolio, position-sizing, or canonical watchlist path.
    """

    _require_manifest(manifest)
    return tuple(evaluate_candidate(manifest, symbol) for symbol in manifest.universe.symbols)


def evaluate_batch(manifest: GenerationInputManifest) -> tuple[CandidateEvaluation, ...]:
    """Readability alias for :func:`evaluate_universe`."""

    return evaluate_universe(manifest)


def evaluate_generation_inputs(manifest: GenerationInputManifest) -> tuple[CandidateEvaluation, ...]:
    """Public batch entrypoint named after the Phase 2B input boundary."""

    return evaluate_universe(manifest)


def evaluate_a_platform(
    manifest: GenerationInputManifest, symbol: str
) -> CandidateEvaluation:
    """Readable alias for the single-symbol A-platform evaluation."""

    return evaluate_candidate(manifest, symbol)


def evaluate_manifest(manifest: GenerationInputManifest) -> tuple[CandidateEvaluation, ...]:
    """Readable alias for the frozen-universe batch evaluation."""

    return evaluate_universe(manifest)


__all__ = [
    "ACCELERATION_OVEREXTENDED",
    "A_PLATFORM_BREAKOUT_LEGACY_V1",
    "CandidateEvaluation",
    "FeatureSnapshot",
    "GAIN_EXHAUSTED",
    "INSUFFICIENT_DATA",
    "LevelPlan",
    "MATCHED_REJECTED",
    "MISSING_SECTOR_EVIDENCE",
    "NOT_MATCHED",
    "QUALIFIED_LEGACY_BASELINE",
    "REJECTED_CLOSE_TOO_LOW",
    "REJECTED_NO_SUPPORT",
    "REJECTED_OVERHANG_RR",
    "REJECTED_RR",
    "REJECTED_STOP_DISTANCE",
    "SETUP_ID",
    "ScoreBreakdown",
    "STRATEGY_SPEC_SHA256",
    "STRATEGY_SPEC_HASH",
    "STRATEGY_VERSION",
    "StrategyInputError",
    "evaluate_batch",
    "evaluate_a_platform",
    "evaluate_candidate",
    "evaluate_generation_inputs",
    "evaluate_manifest",
    "evaluate_universe",
    "strategy_spec_sha256",
]
