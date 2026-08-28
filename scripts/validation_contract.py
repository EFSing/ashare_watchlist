"""Phase 2D validation and historical replay governance contract.

This module freezes the *governance boundary* for a future validation run.  It
does not fetch data, run ``A_PLATFORM_BREAKOUT_LEGACY_V1``, calculate returns,
or decide whether a strategy should be promoted.

The important distinction in this module is between a semantic protocol hash
and runtime/provenance metadata.  The former changes only when a rule changes;
the latter is retained in a frozen dataset manifest but cannot change the
protocol identity.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from generation_contract import (
    ASIA_SHANGHAI,
    POINT_IN_TIME,
    PROVIDER_QFQ_SNAPSHOT,
    XSHG_CALENDAR,
    next_execution_date,
)
from trading_calendar import CalendarUnavailable, TradingCalendar, default_calendar


# Public protocol and schema identities.
VALIDATION_PROTOCOL_VERSION = "PHASE2D_VALIDATION_PROTOCOL_V1"
VALIDATION_DATASET_SCHEMA_VERSION = "FROZEN_VALIDATION_DATASET_MANIFEST_V1"
VALIDATION_DATA_PARTITION = "validation"
DEVELOPMENT_DATA_PARTITION = "development"
FINAL_OOS_DATA_PARTITION = "final_oos"

# Phase 2B's live qfq snapshot is intentionally not a historical adjustment
# contract.  These are distinct labels so a future loader cannot silently
# treat one as the other.
HISTORICAL_ADJUSTED_AS_OF = "HISTORICAL_ADJUSTED_AS_OF"
HISTORICAL_QFQ_AS_OF = "HISTORICAL_QFQ_AS_OF"
UNADJUSTED_OHLCV_AS_OF = "UNADJUSTED_OHLCV_AS_OF"
ALLOWED_HISTORICAL_ADJUSTMENTS = frozenset(
    {HISTORICAL_ADJUSTED_AS_OF, HISTORICAL_QFQ_AS_OF, UNADJUSTED_OHLCV_AS_OF}
)

LEGACY_STRATEGY_VERSION = "A_PLATFORM_BREAKOUT_LEGACY_V1"
LEGACY_STRATEGY_SPEC_SHA256 = (
    "7ce0bf660e3ae685405e01fb9d1ef8e27e7dec44a201ab290da5d8fa8079068d"
)

# Machine-readable failure states.  No state below means "use current data as
# a fallback"; callers must stop or explicitly exclude the affected input.
READY_FOR_VALIDATION_DATASET_FREEZE = "READY_FOR_VALIDATION_DATASET_FREEZE"
MISSING_POINT_IN_TIME_EVIDENCE = "MISSING_POINT_IN_TIME_EVIDENCE"
CURRENT_DATA_BACKFILL = "CURRENT_DATA_BACKFILL"
FUTURE_DATA_INPUT = "FUTURE_DATA_INPUT"
INPUT_DATE_MISMATCH = "INPUT_DATE_MISMATCH"
UNSUPPORTED_ADJUSTMENT_SEMANTICS = "UNSUPPORTED_ADJUSTMENT_SEMANTICS"
INVALID_MANIFEST = "INVALID_MANIFEST"
MANIFEST_HASH_MISMATCH = "MANIFEST_HASH_MISMATCH"
FINAL_OOS_FORBIDDEN = "FINAL_OOS_FORBIDDEN"
PARTITION_FORBIDDEN = "PARTITION_FORBIDDEN"
REPLAY_TIMING_INVALID = "REPLAY_TIMING_INVALID"
SAME_BAR_EXECUTION = "SAME_BAR_EXECUTION"
EXECUTION_BEFORE_EARLIEST = "EXECUTION_BEFORE_EARLIEST"
CALENDAR_ERROR = "CALENDAR_ERROR"


class ValidationContractError(ValueError):
    """A fail-safe, machine-readable validation contract violation."""

    def __init__(self, status: str, message: str) -> None:
        self.status = status
        super().__init__(f"{status}: {message}")


ContractError = ValidationContractError


def _canonical_date(value: date | datetime | str, field_name: str = "date") -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip().replace("/", "-")
    if len(text) == 8 and text.isdigit():
        return datetime.strptime(text, "%Y%m%d").date().isoformat()
    try:
        return datetime.strptime(text, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO date") from exc


def _canonical_timestamp(value: datetime | str, field_name: str) -> str:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            raise ValueError(f"{field_name} must be a non-empty ISO-8601 timestamp")
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone offset")
    return parsed.isoformat()


def _known_at_date(value: date | datetime | str, field_name: str) -> date:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if len(text) == 10 and text[4] == "-":
            return date.fromisoformat(text)
        if len(text) == 8 and text.isdigit():
            return datetime.strptime(text, "%Y%m%d").date()
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone offset when it has a time")
    return parsed.astimezone(timezone(timedelta(hours=8))).date()


def _canonical_known_at(value: date | datetime | str, field_name: str) -> str:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        text = value.strip()
        if len(text) == 10 and text[4] == "-":
            return _canonical_date(text, field_name)
        if len(text) == 8 and text.isdigit():
            return _canonical_date(text, field_name)
    return _canonical_timestamp(value, field_name)


def _require_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _normalize_symbol(value: Any) -> str:
    return _require_text(value, "symbol").lower()


def _normalize_symbols(value: Any, field_name: str = "symbols") -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field_name} must be a sequence of symbols")
    symbols = tuple(_normalize_symbol(item) for item in value)
    if not symbols:
        raise ValueError(f"{field_name} must not be empty")
    if len(set(symbols)) != len(symbols):
        raise ValueError(f"{field_name} must contain unique symbols")
    return tuple(sorted(symbols))


def _normalized_value(value: Any) -> Any:
    """Convert JSON-compatible values to deterministic canonical values."""

    if isinstance(value, Mapping):
        return {
            str(key): _normalized_value(value[key])
            for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, (list, tuple)):
        return [_normalized_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        values = [_normalized_value(item) for item in value]
        return sorted(values, key=lambda item: _canonical_json(item))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("canonical data must not contain NaN or infinity")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"canonical data is not JSON-compatible: {type(value).__name__}")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _normalized_value(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def canonical_json(value: Any) -> str:
    """Return the canonical JSON representation used by this protocol."""

    return _canonical_json(value)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_NON_SEMANTIC_KEYS = frozenset(
    {"created_at", "retrieved_at", "retrieved_at_bjt", "generated_at", "runtime_metadata"}
)


def _require_sha256(value: Any, field_name: str) -> str:
    text = _require_text(value, field_name).lower()
    if _SHA256_RE.fullmatch(text) is None:
        raise ValueError(f"{field_name} must be a 64-character SHA-256 hex digest")
    return text


# This object is the only input to the protocol semantic hash.  Runtime
# timestamps, provider retrieval metadata, formatting, and test results are
# deliberately absent.
VALIDATION_PROTOCOL_SEMANTIC_SPEC: dict[str, Any] = {
    "protocol_version": VALIDATION_PROTOCOL_VERSION,
    "data_contract": {
        "known_information": "every input used for signal_date=T has known_at<=T",
        "universe": "POINT_IN_TIME source snapshot for T; never current membership backfill",
        "sector": "POINT_IN_TIME membership, rank, and sector_chg for T",
        "current_data_fallback": "forbidden; missing evidence fails safe",
        "ohlcv": {
            "phase_2b_snapshot": PROVIDER_QFQ_SNAPSHOT,
            "phase_2b_snapshot_is_historical": False,
            "accepted_adjustments": sorted(ALLOWED_HISTORICAL_ADJUSTMENTS),
            "adjustment_factors_must_be_point_in_time": True,
        },
    },
    "replay": {
        "signal_date": "T",
        "input_dates": "<=T",
        "evaluation": "after T close data is frozen",
        "earliest_execution": "next XSHG session T+1",
        "same_bar_execution": False,
        "future_bar": False,
        "output_provenance": [
            "strategy_spec_sha256",
            "dataset_manifest_sha256",
        ],
    },
    "partitions": {
        "development": DEVELOPMENT_DATA_PARTITION,
        "validation": VALIDATION_DATA_PARTITION,
        "final_oos": FINAL_OOS_DATA_PARTITION,
        "phase_2d_reads_final_oos": False,
        "validation_output_may_tune_legacy": False,
        "tuning_requires_new_strategy_version": True,
    },
    "promotion_gate": {
        "evidence_only": True,
        "required": [
            "deterministic_replay",
            "input_completeness",
            "point_in_time_provenance",
            "signal_frequency",
            "cross_period_structural_stability",
            "concentration",
            "sensitivity_robustness",
        ],
        "future_validation_metrics_allowed_as_evidence": [
            "return",
            "win_rate",
            "mfe",
            "mae",
            "expectancy",
            "pnl",
            "profit_factor",
        ],
        "not_computed_in_phase_2d": True,
        "score_85_is_predictive_score": False,
    },
}


def _semantic_projection(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _semantic_projection(item)
            for key, item in value.items()
            if str(key) not in _NON_SEMANTIC_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_semantic_projection(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [_semantic_projection(item) for item in sorted(value, key=str)]
    return value


def compute_protocol_semantic_sha256(spec: Mapping[str, Any] | None = None) -> str:
    """Hash semantic protocol rules, independent of formatting and timestamps."""

    return _sha256(
        _semantic_projection(VALIDATION_PROTOCOL_SEMANTIC_SPEC if spec is None else spec)
    )


# Public aliases make the intent explicit at call sites and in manifests.
protocol_semantic_sha256 = compute_protocol_semantic_sha256
PROTOCOL_SEMANTIC_SHA256 = compute_protocol_semantic_sha256()


def _fail(status: str, message: str) -> None:
    raise ValidationContractError(status, message)


def _copy_mapping(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail(MISSING_POINT_IN_TIME_EVIDENCE, f"{field_name} must be a mapping")
    return copy.deepcopy(dict(value))


def _identifier_has_final_oos(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            _identifier_has_final_oos(key) or _identifier_has_final_oos(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_identifier_has_final_oos(item) for item in value)
    if not isinstance(value, str):
        return False
    compact = re.sub(r"[^a-z0-9]+", "", value.lower())
    return "finaloos" in compact


def _guard_source(value: Any, field_name: str) -> str:
    source = _require_text(value, field_name)
    if _identifier_has_final_oos(source):
        _fail(FINAL_OOS_FORBIDDEN, f"{field_name} identifies final OOS data")
    return source


def _normalize_evidence_common(
    evidence: Mapping[str, Any],
    *,
    signal_date: str,
    kind: str,
) -> dict[str, Any]:
    normalized = _copy_mapping(evidence, kind)
    required = ("source", "source_version", "temporal_semantics", "as_of_date", "known_at", "content_sha256")
    missing = [field_name for field_name in required if field_name not in normalized]
    if missing:
        _fail(
            MISSING_POINT_IN_TIME_EVIDENCE,
            f"{kind} missing point-in-time fields: {', '.join(missing)}",
        )

    normalized["source"] = _guard_source(normalized["source"], f"{kind}.source")
    normalized["source_version"] = _require_text(
        normalized["source_version"], f"{kind}.source_version"
    )
    if normalized.get("is_current_snapshot") is True or normalized.get("backfilled_from_current") is True:
        _fail(CURRENT_DATA_BACKFILL, f"{kind} is explicitly marked as current-data backfill")

    semantics = _require_text(normalized["temporal_semantics"], f"{kind}.temporal_semantics").upper()
    if semantics == "LIVE_OBSERVED" or semantics == "CURRENT_SNAPSHOT":
        _fail(CURRENT_DATA_BACKFILL, f"{kind} is LIVE/current-observed data, not historical PIT data")
    if semantics != POINT_IN_TIME:
        _fail(MISSING_POINT_IN_TIME_EVIDENCE, f"{kind}.temporal_semantics must be POINT_IN_TIME")
    normalized["temporal_semantics"] = POINT_IN_TIME

    try:
        observed_date = _canonical_date(normalized["as_of_date"], f"{kind}.as_of_date")
    except (TypeError, ValueError) as exc:
        _fail(MISSING_POINT_IN_TIME_EVIDENCE, str(exc))
    if observed_date > signal_date:
        _fail(FUTURE_DATA_INPUT, f"{kind}.as_of_date {observed_date} is after {signal_date}")
    if observed_date != signal_date:
        _fail(INPUT_DATE_MISMATCH, f"{kind}.as_of_date {observed_date} must equal {signal_date}")
    normalized["as_of_date"] = observed_date

    try:
        known_at = _known_at_date(normalized["known_at"], f"{kind}.known_at")
    except (TypeError, ValueError) as exc:
        _fail(MISSING_POINT_IN_TIME_EVIDENCE, str(exc))
    if known_at.isoformat() > signal_date:
        _fail(FUTURE_DATA_INPUT, f"{kind}.known_at {known_at.isoformat()} is after {signal_date}")
    # Keep date-only metadata canonical, while preserving an aware timestamp
    # when one was supplied for auditability.
    try:
        normalized["known_at"] = _canonical_known_at(
            normalized["known_at"], f"{kind}.known_at"
        )
    except (TypeError, ValueError) as exc:
        _fail(MISSING_POINT_IN_TIME_EVIDENCE, str(exc))
    try:
        normalized["content_sha256"] = _require_sha256(
            normalized["content_sha256"], f"{kind}.content_sha256"
        )
    except ValueError as exc:
        _fail(MISSING_POINT_IN_TIME_EVIDENCE, str(exc))
    return normalized


@dataclass(frozen=True)
class PointInTimeEvidence:
    """Canonicalized provenance for one historical input artifact."""

    kind: str
    source: str
    source_version: str
    as_of_date: str
    known_at: str
    content_sha256: str
    payload: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = copy.deepcopy(dict(self.payload))
        result.update(
            {
                "kind": self.kind,
                "source": self.source,
                "source_version": self.source_version,
                "temporal_semantics": POINT_IN_TIME,
                "as_of_date": self.as_of_date,
                "known_at": self.known_at,
                "content_sha256": self.content_sha256,
            }
        )
        return result


def validate_point_in_time_evidence(
    evidence: Mapping[str, Any],
    *,
    signal_date: date | datetime | str,
    kind: str = "input",
) -> PointInTimeEvidence:
    """Validate generic PIT evidence and fail rather than fallback."""

    canonical_signal_date = _canonical_date(signal_date, "signal_date")
    normalized = _normalize_evidence_common(
        evidence, signal_date=canonical_signal_date, kind=kind
    )
    return PointInTimeEvidence(
        kind=_require_text(kind, "kind"),
        source=normalized["source"],
        source_version=normalized["source_version"],
        as_of_date=normalized["as_of_date"],
        known_at=normalized["known_at"],
        content_sha256=normalized["content_sha256"],
        payload=normalized,
    )


def validate_universe_evidence(
    evidence: Mapping[str, Any], *, signal_date: date | datetime | str
) -> PointInTimeEvidence:
    """Require a T-specific, versioned universe snapshot."""

    canonical_signal_date = _canonical_date(signal_date, "signal_date")
    normalized = _normalize_evidence_common(
        evidence, signal_date=canonical_signal_date, kind="universe"
    )
    try:
        normalized["symbols"] = list(_normalize_symbols(normalized.get("symbols"), "universe.symbols"))
    except (TypeError, ValueError) as exc:
        _fail(MISSING_POINT_IN_TIME_EVIDENCE, str(exc))
    return PointInTimeEvidence(
        kind="universe",
        source=normalized["source"],
        source_version=normalized["source_version"],
        as_of_date=normalized["as_of_date"],
        known_at=normalized["known_at"],
        content_sha256=normalized["content_sha256"],
        payload=normalized,
    )


def validate_sector_evidence(
    evidence: Mapping[str, Any], *, signal_date: date | datetime | str
) -> PointInTimeEvidence:
    """Require T-specific membership, rank, and sector change evidence."""

    canonical_signal_date = _canonical_date(signal_date, "signal_date")
    normalized = _normalize_evidence_common(
        evidence, signal_date=canonical_signal_date, kind="sector"
    )
    if "membership" not in normalized and "sector_membership" in normalized:
        normalized["membership"] = normalized["sector_membership"]
    if "rank" not in normalized and "sector_rank" in normalized:
        normalized["rank"] = normalized["sector_rank"]
    required_payload = ("membership", "rank", "sector_chg")
    missing = [field_name for field_name in required_payload if not normalized.get(field_name)]
    if missing:
        _fail(
            MISSING_POINT_IN_TIME_EVIDENCE,
            f"sector missing PIT payload: {', '.join(missing)}",
        )
    return PointInTimeEvidence(
        kind="sector",
        source=normalized["source"],
        source_version=normalized["source_version"],
        as_of_date=normalized["as_of_date"],
        known_at=normalized["known_at"],
        content_sha256=normalized["content_sha256"],
        payload=normalized,
    )


def validate_historical_bars(
    bars: Sequence[Mapping[str, Any]], *, signal_date: date | datetime | str, field_name: str = "bars"
) -> tuple[dict[str, Any], ...]:
    """Reject any OHLCV bar or bar-level known-at timestamp after T."""

    canonical_signal_date = _canonical_date(signal_date, "signal_date")
    if isinstance(bars, (str, bytes)) or not isinstance(bars, Sequence) or not bars:
        _fail(MISSING_POINT_IN_TIME_EVIDENCE, f"{field_name} must be a non-empty sequence")
    normalized: list[dict[str, Any]] = []
    for index, raw_bar in enumerate(bars):
        if not isinstance(raw_bar, Mapping):
            _fail(MISSING_POINT_IN_TIME_EVIDENCE, f"{field_name}[{index}] must be a mapping")
        bar = copy.deepcopy(dict(raw_bar))
        raw_date = bar.get("date", bar.get("bar_date"))
        if raw_date is None:
            _fail(MISSING_POINT_IN_TIME_EVIDENCE, f"{field_name}[{index}] is missing date")
        bar_date = _canonical_date(raw_date, f"{field_name}[{index}].date")
        if bar_date > canonical_signal_date:
            _fail(FUTURE_DATA_INPUT, f"{field_name}[{index}] date {bar_date} is after {canonical_signal_date}")
        bar["date"] = bar_date
        if "known_at" in bar:
            try:
                if _known_at_date(bar["known_at"], f"{field_name}[{index}].known_at").isoformat() > canonical_signal_date:
                    _fail(FUTURE_DATA_INPUT, f"{field_name}[{index}].known_at is after {canonical_signal_date}")
            except (TypeError, ValueError) as exc:
                _fail(MISSING_POINT_IN_TIME_EVIDENCE, str(exc))
        normalized.append(bar)
    normalized.sort(key=lambda item: (item["date"], _canonical_json(item)))
    return tuple(normalized)


def validate_ohlcv_evidence(
    evidence: Mapping[str, Any], *, signal_date: date | datetime | str
) -> PointInTimeEvidence:
    """Validate historical OHLCV provenance and adjustment semantics."""

    canonical_signal_date = _canonical_date(signal_date, "signal_date")
    normalized = _normalize_evidence_common(
        evidence, signal_date=canonical_signal_date, kind="ohlcv"
    )
    try:
        adjustment = _require_text(
            normalized.get("adjustment_semantics"), "ohlcv.adjustment_semantics"
        ).upper()
    except ValueError as exc:
        _fail(MISSING_POINT_IN_TIME_EVIDENCE, str(exc))
    if adjustment == PROVIDER_QFQ_SNAPSHOT:
        _fail(
            UNSUPPORTED_ADJUSTMENT_SEMANTICS,
            "PROVIDER_QFQ_SNAPSHOT is a Phase 2B provider snapshot, not historical PIT adjustment",
        )
    if adjustment not in ALLOWED_HISTORICAL_ADJUSTMENTS:
        _fail(UNSUPPORTED_ADJUSTMENT_SEMANTICS, f"unsupported adjustment_semantics: {adjustment}")
    normalized["adjustment_semantics"] = adjustment

    if "bars" in normalized:
        normalized["bars"] = list(
            validate_historical_bars(normalized["bars"], signal_date=canonical_signal_date)
        )

    if adjustment in {HISTORICAL_ADJUSTED_AS_OF, HISTORICAL_QFQ_AS_OF}:
        factor_evidence = normalized.get("adjustment_evidence")
        if not isinstance(factor_evidence, Mapping):
            _fail(
                MISSING_POINT_IN_TIME_EVIDENCE,
                "adjusted OHLCV requires separate point-in-time adjustment_evidence",
            )
        factor = validate_point_in_time_evidence(
            factor_evidence,
            signal_date=canonical_signal_date,
            kind="adjustment_evidence",
        )
        normalized["adjustment_evidence"] = factor.to_dict()
    return PointInTimeEvidence(
        kind="ohlcv",
        source=normalized["source"],
        source_version=normalized["source_version"],
        as_of_date=normalized["as_of_date"],
        known_at=normalized["known_at"],
        content_sha256=normalized["content_sha256"],
        payload=normalized,
    )


def validate_validation_inputs(
    *,
    signal_date: date | datetime | str,
    universe: Mapping[str, Any],
    sector: Mapping[str, Any],
    ohlcv: Mapping[str, Any],
) -> dict[str, PointInTimeEvidence]:
    """Validate all three required PIT evidence families for one T."""

    canonical_signal_date = _canonical_date(signal_date, "signal_date")
    return {
        "universe": validate_universe_evidence(universe, signal_date=canonical_signal_date),
        "sector": validate_sector_evidence(sector, signal_date=canonical_signal_date),
        "ohlcv": validate_ohlcv_evidence(ohlcv, signal_date=canonical_signal_date),
    }


def _canonical_date_range(value: Mapping[str, Any] | Sequence[Any]) -> dict[str, str]:
    if isinstance(value, Mapping):
        start = value.get("start", value.get("start_date"))
        end = value.get("end", value.get("end_date"))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) == 2:
        start, end = value
    else:
        raise ValueError("date_range must contain start and end dates")
    if start is None or end is None:
        raise ValueError("date_range must contain start and end dates")
    canonical_start = _canonical_date(start, "date_range.start")
    canonical_end = _canonical_date(end, "date_range.end")
    if canonical_start > canonical_end:
        raise ValueError("date_range.start must not be after date_range.end")
    return {"start": canonical_start, "end": canonical_end}


def _manifest_payload(manifest: "ValidationDatasetManifest") -> dict[str, Any]:
    return {
        "schema_version": VALIDATION_DATASET_SCHEMA_VERSION,
        "protocol_version": VALIDATION_PROTOCOL_VERSION,
        "dataset_version": manifest.dataset_version,
        "data_partition": manifest.data_partition,
        "market": manifest.market,
        "symbol": manifest.symbol,
        "date_range": copy.deepcopy(manifest.date_range),
        "universe_source": manifest.universe_source,
        "universe_source_version": manifest.universe_source_version,
        "sector_source": manifest.sector_source,
        "sector_source_version": manifest.sector_source_version,
        "ohlcv_source": manifest.ohlcv_source,
        "ohlcv_source_version": manifest.ohlcv_source_version,
        "adjustment_semantics": manifest.adjustment_semantics,
        "calendar": manifest.calendar,
        "timezone": manifest.timezone,
        "content_sha256": manifest.content_sha256,
        "created_at": manifest.created_at,
        "retrieved_at": manifest.retrieved_at,
        "universe_provenance": copy.deepcopy(manifest.universe_provenance),
        "sector_provenance": copy.deepcopy(manifest.sector_provenance),
        "ohlcv_provenance": copy.deepcopy(manifest.ohlcv_provenance),
        "protocol_semantic_sha256": manifest.protocol_semantic_sha256,
    }


@dataclass(frozen=True)
class ValidationDatasetManifest:
    """Deterministic schema/provenance record for one frozen validation artifact."""

    dataset_version: str
    market: str
    symbol: str
    date_range: Mapping[str, Any] | Sequence[Any]
    universe_source: str
    universe_source_version: str
    sector_source: str
    sector_source_version: str
    ohlcv_source: str
    ohlcv_source_version: str
    adjustment_semantics: str
    calendar: str
    timezone: str
    content_sha256: str
    created_at: datetime | str
    retrieved_at: datetime | str
    universe_provenance: Mapping[str, Any]
    sector_provenance: Mapping[str, Any]
    ohlcv_provenance: Mapping[str, Any]
    data_partition: str = VALIDATION_DATA_PARTITION
    protocol_semantic_sha256: str = field(init=False)
    manifest_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "dataset_version", _require_text(self.dataset_version, "dataset_version"))
        object.__setattr__(self, "market", _require_text(self.market, "market"))
        object.__setattr__(self, "symbol", _normalize_symbol(self.symbol))
        object.__setattr__(self, "date_range", _canonical_date_range(self.date_range))
        object.__setattr__(self, "universe_source", _guard_source(self.universe_source, "universe_source"))
        object.__setattr__(
            self,
            "universe_source_version",
            _require_text(self.universe_source_version, "universe_source_version"),
        )
        object.__setattr__(self, "sector_source", _guard_source(self.sector_source, "sector_source"))
        object.__setattr__(
            self,
            "sector_source_version",
            _require_text(self.sector_source_version, "sector_source_version"),
        )
        object.__setattr__(self, "ohlcv_source", _guard_source(self.ohlcv_source, "ohlcv_source"))
        object.__setattr__(
            self,
            "ohlcv_source_version",
            _require_text(self.ohlcv_source_version, "ohlcv_source_version"),
        )
        adjustment = _require_text(self.adjustment_semantics, "adjustment_semantics").upper()
        if adjustment == PROVIDER_QFQ_SNAPSHOT or adjustment not in ALLOWED_HISTORICAL_ADJUSTMENTS:
            raise ValidationContractError(
                UNSUPPORTED_ADJUSTMENT_SEMANTICS,
                f"manifest adjustment_semantics is not historical PIT: {adjustment}",
            )
        object.__setattr__(self, "adjustment_semantics", adjustment)
        if self.calendar != XSHG_CALENDAR:
            raise ValidationContractError(CALENDAR_ERROR, f"calendar must be {XSHG_CALENDAR}")
        if self.timezone != ASIA_SHANGHAI:
            raise ValidationContractError(
                INVALID_MANIFEST, f"timezone must be {ASIA_SHANGHAI}"
            )
        object.__setattr__(self, "content_sha256", _require_sha256(self.content_sha256, "content_sha256"))
        object.__setattr__(self, "created_at", _canonical_timestamp(self.created_at, "created_at"))
        object.__setattr__(self, "retrieved_at", _canonical_timestamp(self.retrieved_at, "retrieved_at"))
        for name in ("universe_provenance", "sector_provenance", "ohlcv_provenance"):
            provenance = _copy_mapping(getattr(self, name), name)
            if _identifier_has_final_oos(provenance):
                _fail(FINAL_OOS_FORBIDDEN, f"{name} identifies final OOS data")
            if provenance.get("temporal_semantics") != POINT_IN_TIME:
                _fail(MISSING_POINT_IN_TIME_EVIDENCE, f"{name} must retain POINT_IN_TIME semantics")
            object.__setattr__(self, name, provenance)
        partition = _require_text(self.data_partition, "data_partition").lower()
        if partition != VALIDATION_DATA_PARTITION:
            raise ValidationContractError(
                PARTITION_FORBIDDEN,
                f"Phase 2D can only freeze {VALIDATION_DATA_PARTITION} data",
            )
        object.__setattr__(self, "data_partition", partition)
        object.__setattr__(self, "protocol_semantic_sha256", PROTOCOL_SEMANTIC_SHA256)
        object.__setattr__(self, "manifest_sha256", _sha256(_manifest_payload(self)))

    @property
    def signal_date(self) -> str:
        return self.date_range["end"]

    @property
    def semantic_sha256(self) -> str:
        """Alias for the protocol hash, excluding runtime manifest metadata."""

        return self.protocol_semantic_sha256

    def to_dict(self) -> dict[str, Any]:
        payload = _manifest_payload(self)
        payload["manifest_sha256"] = self.manifest_sha256
        return payload

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ValidationDatasetManifest":
        raw = _copy_mapping(value, "manifest")
        supplied_manifest_hash = raw.pop("manifest_sha256", None)
        supplied_protocol_hash = raw.pop("protocol_semantic_sha256", None)
        raw.pop("schema_version", None)
        raw.pop("protocol_version", None)
        try:
            manifest = cls(**raw)
        except ValidationContractError:
            raise
        except (TypeError, ValueError) as exc:
            _fail(INVALID_MANIFEST, str(exc))
        if supplied_protocol_hash is not None and supplied_protocol_hash != PROTOCOL_SEMANTIC_SHA256:
            _fail(INVALID_MANIFEST, "protocol_semantic_sha256 does not match this protocol")
        if supplied_manifest_hash != manifest.manifest_sha256:
            _fail(MANIFEST_HASH_MISMATCH, "manifest_sha256 does not match canonical manifest")
        return manifest


# A descriptive alias used by callers that prefer to emphasize frozen state.
FrozenValidationDatasetManifest = ValidationDatasetManifest


def canonical_manifest_json(value: ValidationDatasetManifest | Mapping[str, Any]) -> str:
    """Return deterministic JSON for a manifest, excluding its self-hash."""

    if isinstance(value, ValidationDatasetManifest):
        payload = value.to_dict()
    else:
        payload = _copy_mapping(value, "manifest")
    payload.pop("manifest_sha256", None)
    return _canonical_json(payload)


def freeze_validation_dataset(
    *,
    dataset_version: str,
    market: str,
    symbol: str,
    date_range: Mapping[str, Any] | Sequence[Any],
    universe: Mapping[str, Any],
    sector: Mapping[str, Any],
    ohlcv: Mapping[str, Any],
    content_sha256: str,
    created_at: datetime | str,
    retrieved_at: datetime | str,
    calendar: str = XSHG_CALENDAR,
    timezone_name: str = ASIA_SHANGHAI,
) -> ValidationDatasetManifest:
    """Freeze schema and provenance without fetching or evaluating any data."""

    canonical_range = _canonical_date_range(date_range)
    evidence = validate_validation_inputs(
        signal_date=canonical_range["end"],
        universe=universe,
        sector=sector,
        ohlcv=ohlcv,
    )
    ohlcv_payload = evidence["ohlcv"].to_dict()
    return ValidationDatasetManifest(
        dataset_version=dataset_version,
        market=market,
        symbol=symbol,
        date_range=canonical_range,
        universe_source=evidence["universe"].source,
        universe_source_version=evidence["universe"].source_version,
        sector_source=evidence["sector"].source,
        sector_source_version=evidence["sector"].source_version,
        ohlcv_source=evidence["ohlcv"].source,
        ohlcv_source_version=evidence["ohlcv"].source_version,
        adjustment_semantics=ohlcv_payload["adjustment_semantics"],
        calendar=calendar,
        timezone=timezone_name,
        content_sha256=content_sha256,
        created_at=created_at,
        retrieved_at=retrieved_at,
        universe_provenance=evidence["universe"].to_dict(),
        sector_provenance=evidence["sector"].to_dict(),
        ohlcv_provenance=ohlcv_payload,
    )


def _guard_manifest_path(path: Path, validation_root: Path | None) -> Path:
    resolved = path.resolve()
    parts = [part.lower() for part in resolved.parts]
    if any("finaloos" in re.sub(r"[^a-z0-9]+", "", part) for part in parts):
        _fail(FINAL_OOS_FORBIDDEN, f"manifest path identifies final OOS: {path}")
    if any(part in {DEVELOPMENT_DATA_PARTITION, "engineering"} for part in parts):
        _fail(PARTITION_FORBIDDEN, f"manifest path identifies development data: {path}")
    if validation_root is not None:
        root = validation_root.resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            _fail(PARTITION_FORBIDDEN, f"manifest path is outside validation root: {path}")
    return resolved


def load_validation_manifest(
    path: str | Path, *, validation_root: str | Path | None = None
) -> ValidationDatasetManifest:
    """Load only a validation manifest; final OOS is rejected before file I/O."""

    manifest_path = Path(path)
    root = None if validation_root is None else Path(validation_root)
    safe_path = _guard_manifest_path(manifest_path, root)
    try:
        payload = json.loads(safe_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail(INVALID_MANIFEST, f"cannot read validation manifest: {exc}")
    manifest = ValidationDatasetManifest.from_dict(payload)
    if manifest.data_partition != VALIDATION_DATA_PARTITION:
        _fail(PARTITION_FORBIDDEN, "loaded manifest is not validation data")
    return manifest


load_frozen_validation_manifest = load_validation_manifest


def validate_replay_input_dates(
    inputs: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    signal_date: date | datetime | str,
) -> None:
    """Validate explicit input records without reading any dataset path."""

    canonical_signal_date = _canonical_date(signal_date, "signal_date")
    records: Sequence[Any]
    if isinstance(inputs, Mapping):
        records = (inputs,)
    elif isinstance(inputs, Sequence) and not isinstance(inputs, (str, bytes)):
        records = inputs
    else:
        _fail(MISSING_POINT_IN_TIME_EVIDENCE, "replay inputs must be mappings")
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            _fail(MISSING_POINT_IN_TIME_EVIDENCE, f"replay input {index} must be a mapping")
        for field_name in ("date", "bar_date", "as_of_date", "effective_date"):
            if field_name in record and record[field_name] is not None:
                observed = _canonical_date(record[field_name], f"replay input {index}.{field_name}")
                if observed > canonical_signal_date:
                    _fail(FUTURE_DATA_INPUT, f"replay input {index}.{field_name} is after {canonical_signal_date}")
        if "known_at" in record and record["known_at"] is not None:
            try:
                known_at = _known_at_date(record["known_at"], f"replay input {index}.known_at")
            except (TypeError, ValueError) as exc:
                _fail(MISSING_POINT_IN_TIME_EVIDENCE, str(exc))
            if known_at.isoformat() > canonical_signal_date:
                _fail(FUTURE_DATA_INPUT, f"replay input {index}.known_at is after {canonical_signal_date}")


def validate_replay_timing(
    *,
    signal_date: date | datetime | str,
    earliest_execution_date: date | datetime | str,
    execution_date: date | datetime | str | None = None,
    calendar: TradingCalendar | None = None,
) -> str:
    """Enforce T-close evaluation and earliest execution on the next session."""

    canonical_signal_date = _canonical_date(signal_date, "signal_date")
    canonical_earliest = _canonical_date(earliest_execution_date, "earliest_execution_date")
    try:
        expected_earliest = next_execution_date(canonical_signal_date, calendar or default_calendar())
    except (CalendarUnavailable, Exception) as exc:
        _fail(CALENDAR_ERROR, f"XSHG calendar unavailable: {exc}")
    if canonical_earliest != expected_earliest:
        _fail(
            REPLAY_TIMING_INVALID,
            f"earliest execution must be XSHG next session {expected_earliest}, got {canonical_earliest}",
        )
    if execution_date is None:
        return canonical_earliest
    canonical_execution = _canonical_date(execution_date, "execution_date")
    if canonical_execution <= canonical_signal_date:
        _fail(SAME_BAR_EXECUTION, "execution must be strictly after signal_date T")
    if canonical_execution < canonical_earliest:
        _fail(EXECUTION_BEFORE_EARLIEST, "execution is before the earliest allowed T+1 session")
    return canonical_execution


@dataclass(frozen=True)
class ReplayPlan:
    """Replay envelope; it carries provenance but does not contain results."""

    signal_date: date | datetime | str
    earliest_execution_date: date | datetime | str
    strategy_version: str
    strategy_spec_sha256: str
    dataset_manifest_sha256: str
    execution_date: date | datetime | str | None = None
    calendar: str = XSHG_CALENDAR
    protocol_semantic_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if self.calendar != XSHG_CALENDAR:
            _fail(CALENDAR_ERROR, f"replay calendar must be {XSHG_CALENDAR}")
        signal = _canonical_date(self.signal_date, "signal_date")
        earliest = _canonical_date(self.earliest_execution_date, "earliest_execution_date")
        execution = None if self.execution_date is None else _canonical_date(self.execution_date, "execution_date")
        validate_replay_timing(
            signal_date=signal,
            earliest_execution_date=earliest,
            execution_date=execution,
        )
        object.__setattr__(self, "signal_date", signal)
        object.__setattr__(self, "earliest_execution_date", earliest)
        object.__setattr__(self, "execution_date", execution)
        object.__setattr__(self, "strategy_version", _require_text(self.strategy_version, "strategy_version"))
        object.__setattr__(self, "strategy_spec_sha256", _require_sha256(self.strategy_spec_sha256, "strategy_spec_sha256"))
        object.__setattr__(self, "dataset_manifest_sha256", _require_sha256(self.dataset_manifest_sha256, "dataset_manifest_sha256"))
        object.__setattr__(self, "protocol_semantic_sha256", PROTOCOL_SEMANTIC_SHA256)

    def output_provenance(self) -> dict[str, str]:
        return {
            "strategy_version": self.strategy_version,
            "strategy_spec_sha256": self.strategy_spec_sha256,
            "dataset_manifest_sha256": self.dataset_manifest_sha256,
            "protocol_semantic_sha256": self.protocol_semantic_sha256,
        }


@dataclass(frozen=True)
class PromotionGateSpec:
    """Evidence checklist only; it intentionally has no evaluator."""

    strategy_version: str = LEGACY_STRATEGY_VERSION
    strategy_spec_sha256: str = LEGACY_STRATEGY_SPEC_SHA256
    protocol_semantic_sha256: str = PROTOCOL_SEMANTIC_SHA256
    required_evidence: tuple[str, ...] = (
        "deterministic_replay",
        "input_completeness",
        "point_in_time_provenance",
        "signal_frequency",
        "cross_period_structural_stability",
        "concentration",
        "sensitivity_robustness",
    )
    future_validation_metrics_allowed: tuple[str, ...] = (
        "return",
        "win_rate",
        "mfe",
        "mae",
        "expectancy",
        "pnl",
        "profit_factor",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_version": self.strategy_version,
            "strategy_spec_sha256": self.strategy_spec_sha256,
            "protocol_semantic_sha256": self.protocol_semantic_sha256,
            "required_evidence": list(self.required_evidence),
            "future_validation_metrics_allowed": list(self.future_validation_metrics_allowed),
            "phase_2d_computes_results": False,
            "score_85_is_predictive_score": False,
        }


def promotion_gate_spec() -> PromotionGateSpec:
    """Return the frozen evidence gate without evaluating any evidence."""

    return PromotionGateSpec()
