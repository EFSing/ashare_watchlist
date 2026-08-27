"""Generation input and timing contract for the Phase 2B boundary.

This module freezes the *inputs* a future generation strategy may consume.  It
does not implement a strategy, score, screener, replay engine, or scheduler.
The live contract is close-only: all inputs describe the completed session T,
and the earliest execution date is the next XSHG session after T.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from trading_calendar import CalendarUnavailable, TradingCalendar, default_calendar


# Public contract literals.  Keep these stable for manifests, tests, and
# downstream consumers; strategy code must not invent a second vocabulary.
CLOSE_GENERATION = "close"
ASIA_SHANGHAI = "Asia/Shanghai"
XSHG_CALENDAR = "XSHG"
LIVE_OBSERVED = "LIVE_OBSERVED"
POINT_IN_TIME = "POINT_IN_TIME"
PROVIDER_QFQ_SNAPSHOT = "PROVIDER_QFQ_SNAPSHOT"

READY_FOR_STRATEGY_EVALUATION = "READY_FOR_STRATEGY_EVALUATION"
INPUT_DATE_MISMATCH = "INPUT_DATE_MISMATCH"
FUTURE_DATA_DETECTED = "FUTURE_DATA_DETECTED"
INCOMPLETE_COVERAGE = "INCOMPLETE_COVERAGE"
UNSUPPORTED_MODE = "UNSUPPORTED_MODE"
UNSUPPORTED_HISTORICAL_REPLAY = "UNSUPPORTED_HISTORICAL_REPLAY"
CALENDAR_ERROR = "CALENDAR_ERROR"
SESSION_NOT_CLOSED = "SESSION_NOT_CLOSED"


class GenerationContractError(ValueError):
    """A fail-fast violation of the generation input/timing contract."""

    def __init__(self, status: str, message: str) -> None:
        self.status = status
        super().__init__(f"{status}: {message}")


ContractError = GenerationContractError


def _canonical_date(value: date | datetime | str) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip().replace("/", "-")
    if len(text) == 8 and text.isdigit():
        parsed = datetime.strptime(text, "%Y%m%d").date()
        return parsed.isoformat()
    parsed = datetime.strptime(text, "%Y-%m-%d").date()
    return parsed.isoformat()


def _canonical_timestamp_bjt(value: datetime | str) -> str:
    """Normalize an aware timestamp and require the Asia/Shanghai offset."""

    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            raise ValueError("retrieved_at_bjt must be a non-empty ISO-8601 timestamp")
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(hours=8):
        raise ValueError("retrieved_at_bjt must include the Asia/Shanghai +08:00 offset")
    return parsed.astimezone(timezone(timedelta(hours=8))).isoformat()


def _require_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _normalize_symbol(value: Any) -> str:
    return _require_text(value, "symbol").lower()


def _normalize_symbols(values: Sequence[Any]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError("symbols must be a sequence, not one string")
    normalized = tuple(_normalize_symbol(value) for value in values)
    if not normalized:
        raise ValueError("symbols must not be empty")
    if len(set(normalized)) != len(normalized):
        raise ValueError("symbols must be unique")
    return tuple(sorted(normalized))


def _normalized_value(value: Any) -> Any:
    """Return JSON-compatible data with deterministic mapping key order."""

    if isinstance(value, Mapping):
        return {
            str(key): _normalized_value(value[key])
            for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, (list, tuple)):
        return [_normalized_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized = [_normalized_value(item) for item in value]
        return sorted(normalized, key=lambda item: _canonical_json(item))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("manifest data must not contain NaN or infinity")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"manifest data is not JSON-compatible: {type(value).__name__}")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _normalized_value(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _copy_mapping(value: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping")
    return copy.deepcopy(dict(value))


def _bar_date(bar: Mapping[str, Any]) -> str:
    value = bar.get("date", bar.get("bar_date"))
    if value is None:
        raise ValueError("each kline bar must contain date")
    return _canonical_date(value)


def _normalize_bars(values: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError("bars must be a sequence of mappings")
    normalized: list[dict[str, Any]] = []
    for raw in values:
        record = _copy_mapping(raw, "bar")
        record["date"] = _bar_date(record)
        normalized.append(record)
    # Bar order is transport formatting, not input content.  Date order is
    # also what first/last coverage means for the contract.
    normalized.sort(key=lambda item: (item["date"], _canonical_json(item)))
    return tuple(normalized)


def _ensure_same_date(actual: str, expected: str, label: str) -> None:
    if actual != expected:
        raise GenerationContractError(
            INPUT_DATE_MISMATCH,
            f"{label} date {actual} does not equal as_of_date {expected}",
        )


def _next_xshg_session(
    as_of_date: str,
    calendar: TradingCalendar,
) -> str:
    current = datetime.strptime(as_of_date, "%Y-%m-%d").date() + timedelta(days=1)
    try:
        while not calendar.is_trading_day(current):
            current += timedelta(days=1)
    except CalendarUnavailable as exc:
        raise GenerationContractError(CALENDAR_ERROR, str(exc)) from exc
    except Exception as exc:
        raise GenerationContractError(CALENDAR_ERROR, f"XSHG calendar failed: {exc}") from exc
    return current.isoformat()


@dataclass(frozen=True)
class RunContext:
    """The timing and calendar identity for one generation-input freeze.

    ``historical=True`` is explicit so tests and callers do not depend on the
    wall clock.  Such a run is rejected before any generation manifest is
    produced; it is not a replay implementation.
    """

    as_of_date: date | datetime | str
    mode: str = CLOSE_GENERATION
    timezone: str = ASIA_SHANGHAI
    calendar: str = XSHG_CALENDAR
    historical: bool = False
    provider_version_metadata: Mapping[str, Any] = field(default_factory=dict)
    signal_date: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of_date", _canonical_date(self.as_of_date))
        object.__setattr__(self, "signal_date", self.as_of_date)
        object.__setattr__(self, "mode", _require_text(self.mode, "mode").lower())
        object.__setattr__(self, "timezone", _require_text(self.timezone, "timezone"))
        object.__setattr__(self, "calendar", _require_text(self.calendar, "calendar").upper())
        if not isinstance(self.historical, bool):
            raise ValueError("historical must be a boolean")
        object.__setattr__(
            self,
            "provider_version_metadata",
            _copy_mapping(self.provider_version_metadata, "provider_version_metadata"),
        )

    def earliest_execution_date(self, calendar: TradingCalendar | None = None) -> str:
        return _next_xshg_session(self.as_of_date, calendar or default_calendar())

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of_date": self.as_of_date,
            "signal_date": self.signal_date,
            "mode": self.mode,
            "timezone": self.timezone,
            "calendar": self.calendar,
            "historical": self.historical,
            "provider_version_metadata": copy.deepcopy(self.provider_version_metadata),
        }


@dataclass(frozen=True)
class UniverseManifest:
    as_of_date: date | datetime | str
    retrieved_at_bjt: datetime | str
    source: str
    symbols: Sequence[Any]
    temporal_semantics: str = LIVE_OBSERVED
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of_date", _canonical_date(self.as_of_date))
        object.__setattr__(self, "retrieved_at_bjt", _canonical_timestamp_bjt(self.retrieved_at_bjt))
        object.__setattr__(self, "source", _require_text(self.source, "source"))
        object.__setattr__(self, "symbols", _normalize_symbols(self.symbols))
        semantics = _require_text(self.temporal_semantics, "temporal_semantics").upper()
        if semantics not in {LIVE_OBSERVED, POINT_IN_TIME}:
            raise ValueError(f"unsupported temporal_semantics: {semantics}")
        object.__setattr__(self, "temporal_semantics", semantics)
        object.__setattr__(
            self,
            "content_sha256",
            _sha256({"symbols": list(self.symbols), "temporal_semantics": semantics}),
        )

    @property
    def sorted_symbols(self) -> tuple[str, ...]:
        return self.symbols

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of_date": self.as_of_date,
            "retrieved_at_bjt": self.retrieved_at_bjt,
            "source": self.source,
            "temporal_semantics": self.temporal_semantics,
            "symbols": list(self.symbols),
            "symbol_count": len(self.symbols),
            "content_sha256": self.content_sha256,
        }


@dataclass(frozen=True)
class QuoteSnapshotManifest:
    as_of_date: date | datetime | str
    retrieved_at_bjt: datetime | str
    source: str
    quotes: Mapping[str, Mapping[str, Any]]
    provider: str = "Tencent"
    temporal_semantics: str = LIVE_OBSERVED
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of_date", _canonical_date(self.as_of_date))
        object.__setattr__(self, "retrieved_at_bjt", _canonical_timestamp_bjt(self.retrieved_at_bjt))
        object.__setattr__(self, "source", _require_text(self.source, "source"))
        object.__setattr__(self, "provider", _require_text(self.provider, "provider"))
        semantics = _require_text(self.temporal_semantics, "temporal_semantics").upper()
        if semantics not in {LIVE_OBSERVED, POINT_IN_TIME}:
            raise ValueError(f"unsupported temporal_semantics: {semantics}")
        object.__setattr__(self, "temporal_semantics", semantics)
        if not isinstance(self.quotes, Mapping):
            raise ValueError("quotes must be a mapping keyed by symbol")
        normalized: dict[str, dict[str, Any]] = {}
        for raw_symbol, raw_quote in self.quotes.items():
            symbol = _normalize_symbol(raw_symbol)
            if symbol in normalized:
                raise ValueError(f"duplicate quote symbol: {symbol}")
            record = _copy_mapping(raw_quote, f"quote[{symbol}]")
            record.setdefault("code", symbol)
            if "quote_date" not in record:
                raise ValueError(f"quote[{symbol}] is missing quote_date")
            record["quote_date"] = _canonical_date(record["quote_date"])
            normalized[symbol] = record
        object.__setattr__(self, "quotes", dict(sorted(normalized.items())))
        object.__setattr__(self, "content_sha256", _sha256({"quotes": self.quotes}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of_date": self.as_of_date,
            "retrieved_at_bjt": self.retrieved_at_bjt,
            "source": self.source,
            "provider": self.provider,
            "temporal_semantics": self.temporal_semantics,
            "quotes": copy.deepcopy(self.quotes),
            "content_sha256": self.content_sha256,
        }


@dataclass(frozen=True)
class KlineManifest:
    """One stock daily-K series and its provider-adjustment evidence."""

    symbol: str
    as_of_date: date | datetime | str
    retrieved_at_bjt: datetime | str
    bars: Sequence[Mapping[str, Any]]
    provider: str = "Tencent"
    adjustment_mode: str = PROVIDER_QFQ_SNAPSHOT
    source: str = "Tencent qfq daily kline"
    temporal_semantics: str = LIVE_OBSERVED
    first_bar_date: str | None = field(init=False)
    last_bar_date: str | None = field(init=False)
    bar_count: int = field(init=False)
    normalized_data_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", _normalize_symbol(self.symbol))
        object.__setattr__(self, "as_of_date", _canonical_date(self.as_of_date))
        object.__setattr__(self, "retrieved_at_bjt", _canonical_timestamp_bjt(self.retrieved_at_bjt))
        object.__setattr__(self, "provider", _require_text(self.provider, "provider"))
        object.__setattr__(self, "adjustment_mode", _require_text(self.adjustment_mode, "adjustment_mode"))
        object.__setattr__(self, "source", _require_text(self.source, "source"))
        semantics = _require_text(self.temporal_semantics, "temporal_semantics").upper()
        if semantics not in {LIVE_OBSERVED, POINT_IN_TIME}:
            raise ValueError(f"unsupported temporal_semantics: {semantics}")
        object.__setattr__(self, "temporal_semantics", semantics)
        normalized_bars = _normalize_bars(self.bars)
        object.__setattr__(self, "bars", normalized_bars)
        object.__setattr__(self, "first_bar_date", normalized_bars[0]["date"] if normalized_bars else None)
        object.__setattr__(self, "last_bar_date", normalized_bars[-1]["date"] if normalized_bars else None)
        object.__setattr__(self, "bar_count", len(normalized_bars))
        object.__setattr__(
            self,
            "normalized_data_sha256",
            _sha256({"symbol": self.symbol, "bars": list(normalized_bars)}),
        )

    @property
    def content_sha256(self) -> str:
        return self.normalized_data_sha256

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "as_of_date": self.as_of_date,
            "retrieved_at_bjt": self.retrieved_at_bjt,
            "provider": self.provider,
            "adjustment_mode": self.adjustment_mode,
            "source": self.source,
            "temporal_semantics": self.temporal_semantics,
            "first_bar_date": self.first_bar_date,
            "last_bar_date": self.last_bar_date,
            "bar_count": self.bar_count,
            "bars": copy.deepcopy(self.bars),
            "normalized_data_sha256": self.normalized_data_sha256,
        }


@dataclass(frozen=True)
class IndexManifest(KlineManifest):
    """One index daily-K series, validated with the same as-of rules."""


def _normalize_sector_members(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _normalize_sector_members(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        normalized = [_normalize_sector_members(item) for item in value]
        return sorted(normalized, key=lambda item: _canonical_json(item))
    return copy.deepcopy(value)


@dataclass(frozen=True)
class SectorManifest:
    as_of_date: date | datetime | str
    retrieved_at_bjt: datetime | str
    source: str
    definitions: Any
    members: Any
    rank_input: Any
    temporal_semantics: str = LIVE_OBSERVED
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of_date", _canonical_date(self.as_of_date))
        object.__setattr__(self, "retrieved_at_bjt", _canonical_timestamp_bjt(self.retrieved_at_bjt))
        object.__setattr__(self, "source", _require_text(self.source, "source"))
        semantics = _require_text(self.temporal_semantics, "temporal_semantics").upper()
        if semantics not in {LIVE_OBSERVED, POINT_IN_TIME}:
            raise ValueError(f"unsupported temporal_semantics: {semantics}")
        object.__setattr__(self, "temporal_semantics", semantics)
        definitions = copy.deepcopy(self.definitions)
        members = _normalize_sector_members(self.members)
        rank_input = copy.deepcopy(self.rank_input)
        object.__setattr__(self, "definitions", definitions)
        object.__setattr__(self, "members", members)
        object.__setattr__(self, "rank_input", rank_input)
        object.__setattr__(
            self,
            "content_sha256",
            _sha256(
                {
                    "definitions": definitions,
                    "members": members,
                    "rank_input": rank_input,
                    "temporal_semantics": semantics,
                }
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of_date": self.as_of_date,
            "retrieved_at_bjt": self.retrieved_at_bjt,
            "source": self.source,
            "temporal_semantics": self.temporal_semantics,
            "definitions": copy.deepcopy(self.definitions),
            "members": copy.deepcopy(self.members),
            "rank_input": copy.deepcopy(self.rank_input),
            "content_sha256": self.content_sha256,
        }


@dataclass(frozen=True)
class GenerationInputManifest:
    """Validated, deterministic input evidence for one close-generation run."""

    run_context: RunContext
    universe: UniverseManifest
    quote_snapshot: QuoteSnapshotManifest
    stock_klines: Sequence[KlineManifest]
    index: IndexManifest
    sector: SectorManifest
    provider_version_metadata: Mapping[str, Any] = field(default_factory=dict)
    status: str = READY_FOR_STRATEGY_EVALUATION
    earliest_execution_date: str | None = None
    input_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if self.status != READY_FOR_STRATEGY_EVALUATION:
            raise ValueError("a frozen manifest can only have the READY status")
        if not isinstance(self.stock_klines, Sequence) or isinstance(self.stock_klines, (str, bytes)):
            raise ValueError("stock_klines must be a sequence of KlineManifest objects")
        by_symbol: dict[str, KlineManifest] = {}
        for item in self.stock_klines:
            if not isinstance(item, KlineManifest) or isinstance(item, IndexManifest):
                raise ValueError("stock_klines must contain KlineManifest objects")
            if item.symbol in by_symbol:
                raise ValueError(f"duplicate stock kline symbol: {item.symbol}")
            by_symbol[item.symbol] = item
        ordered = tuple(by_symbol[symbol] for symbol in sorted(by_symbol))
        object.__setattr__(self, "stock_klines", ordered)
        object.__setattr__(
            self,
            "provider_version_metadata",
            _copy_mapping(self.provider_version_metadata, "provider_version_metadata"),
        )
        if self.earliest_execution_date is None:
            object.__setattr__(self, "earliest_execution_date", self.run_context.earliest_execution_date())
        else:
            object.__setattr__(self, "earliest_execution_date", _canonical_date(self.earliest_execution_date))
        if self.input_fingerprint is None:
            object.__setattr__(self, "input_fingerprint", self._calculate_input_fingerprint())
        elif len(self.input_fingerprint) != 64:
            raise ValueError("input_fingerprint must be a SHA-256 hex digest")

    @property
    def quotes(self) -> QuoteSnapshotManifest:
        """Short alias for callers that use the input type rather than source name."""

        return self.quote_snapshot

    @property
    def signal_date(self) -> str:
        return self.run_context.signal_date

    def _fingerprint_payload(self) -> dict[str, Any]:
        # Deliberately omit input_fingerprint itself and all retrieved_at_bjt
        # fields.  Hashes represent content; timestamps are provenance only.
        return {
            "as_of_date": self.run_context.as_of_date,
            "calendar": self.run_context.calendar,
            "mode": self.run_context.mode,
            "timezone": self.run_context.timezone,
            "universe_hash": self.universe.content_sha256,
            "quote_hash": self.quote_snapshot.content_sha256,
            "stock_kline_hashes": {
                item.symbol: item.normalized_data_sha256 for item in self.stock_klines
            },
            "index_hash": self.index.normalized_data_sha256,
            "sector_hash": self.sector.content_sha256,
            "adjustment_mode": sorted({item.adjustment_mode for item in (*self.stock_klines, self.index)}),
            "temporal_semantics": {
                "universe": self.universe.temporal_semantics,
                "quotes": self.quote_snapshot.temporal_semantics,
                "stock_klines": {
                    item.symbol: item.temporal_semantics for item in self.stock_klines
                },
                "index": self.index.temporal_semantics,
                "sector": self.sector.temporal_semantics,
            },
            "provider_version_metadata": {
                **copy.deepcopy(self.run_context.provider_version_metadata),
                **copy.deepcopy(self.provider_version_metadata),
            },
            "providers": {
                "universe": self.universe.source,
                "quotes": self.quote_snapshot.provider,
                "stock_klines": {item.symbol: item.provider for item in self.stock_klines},
                "index": self.index.provider,
                "sector": self.sector.source,
            },
        }

    def _calculate_input_fingerprint(self) -> str:
        return _sha256(self._fingerprint_payload())

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "run_context": self.run_context.to_dict(),
            "signal_date": self.signal_date,
            "earliest_execution_date": self.earliest_execution_date,
            "universe": self.universe.to_dict(),
            "quote_snapshot": self.quote_snapshot.to_dict(),
            "stock_klines": [item.to_dict() for item in self.stock_klines],
            "index": self.index.to_dict(),
            "sector": self.sector.to_dict(),
            "provider_version_metadata": copy.deepcopy(self.provider_version_metadata),
            "input_fingerprint": self.input_fingerprint,
        }


def _fail(status: str, message: str) -> None:
    raise GenerationContractError(status, message)


def _validate_calendar(as_of_date: str, calendar: TradingCalendar) -> None:
    try:
        if not calendar.is_trading_day(as_of_date):
            _fail(CALENDAR_ERROR, f"as_of_date {as_of_date} is not an XSHG trading session")
    except GenerationContractError:
        raise
    except CalendarUnavailable as exc:
        _fail(CALENDAR_ERROR, str(exc))
    except Exception as exc:
        _fail(CALENDAR_ERROR, f"XSHG calendar failed: {exc}")


def _validate_kline_dates(item: KlineManifest, as_of_date: str, label: str) -> None:
    if item.adjustment_mode != PROVIDER_QFQ_SNAPSHOT:
        _fail(
            UNSUPPORTED_MODE,
            f"{label} {item.symbol} adjustment_mode must be {PROVIDER_QFQ_SNAPSHOT}",
        )
    if item.bar_count == 0 or item.first_bar_date is None or item.last_bar_date is None:
        _fail(INCOMPLETE_COVERAGE, f"{label} {item.symbol} has no bars")
    future_dates = [bar["date"] for bar in item.bars if bar["date"] > as_of_date]
    if future_dates:
        _fail(
            FUTURE_DATA_DETECTED,
            f"{label} {item.symbol} contains bar after {as_of_date}: {future_dates[0]}",
        )
    if item.last_bar_date != as_of_date:
        _fail(
            INPUT_DATE_MISMATCH,
            f"{label} {item.symbol} last_bar_date {item.last_bar_date} != {as_of_date}",
        )


def _validate_live_observation_date(item: Any, as_of_date: str, label: str) -> None:
    if item.temporal_semantics != LIVE_OBSERVED:
        _fail(
            UNSUPPORTED_MODE,
            f"{label} must be marked {LIVE_OBSERVED} for live close generation",
        )
    observed_date = datetime.fromisoformat(item.retrieved_at_bjt).date().isoformat()
    if observed_date != as_of_date:
        _fail(
            INPUT_DATE_MISMATCH,
            f"{label} observation date {observed_date} != as_of_date {as_of_date}",
        )


def _validate_session_closed(
    as_of_date: str,
    calendar: TradingCalendar,
    live_inputs: Sequence[tuple[str, Any]],
) -> None:
    try:
        session_close = calendar.session_close(as_of_date)
    except CalendarUnavailable as exc:
        _fail(CALENDAR_ERROR, str(exc))
    except Exception as exc:
        _fail(CALENDAR_ERROR, f"XSHG session close lookup failed: {exc}")
    if session_close.tzinfo is None:
        _fail(CALENDAR_ERROR, "XSHG session close must be timezone-aware")
    session_close_bjt = session_close.astimezone(timezone(timedelta(hours=8)))
    for label, item in live_inputs:
        retrieved_at = datetime.fromisoformat(item.retrieved_at_bjt)
        if retrieved_at < session_close_bjt:
            _fail(
                SESSION_NOT_CLOSED,
                f"{label} retrieved_at_bjt {item.retrieved_at_bjt} is before "
                f"XSHG session close {session_close_bjt.isoformat()}",
            )


def freeze_generation_inputs(
    run_context: RunContext,
    universe: UniverseManifest,
    quote_snapshot: QuoteSnapshotManifest,
    stock_klines: Sequence[KlineManifest],
    index: IndexManifest,
    sector: SectorManifest,
    *,
    calendar: TradingCalendar | None = None,
    provider_version_metadata: Mapping[str, Any] | None = None,
) -> GenerationInputManifest:
    """Validate and freeze a close-generation input set.

    Every failure is fatal and carries one of the public contract statuses.
    ``historical=True`` is rejected before current/live manifests can be used
    as a replay substitute.
    """

    if not isinstance(run_context, RunContext):
        raise TypeError("run_context must be a RunContext")
    if run_context.mode != CLOSE_GENERATION or run_context.timezone != ASIA_SHANGHAI:
        _fail(
            UNSUPPORTED_MODE,
            f"only mode={CLOSE_GENERATION!r} and timezone={ASIA_SHANGHAI!r} are supported",
        )
    if run_context.calendar != XSHG_CALENDAR:
        _fail(CALENDAR_ERROR, f"only {XSHG_CALENDAR} calendar is supported")
    if run_context.historical:
        _fail(
            UNSUPPORTED_HISTORICAL_REPLAY,
            "historical as-of generation is not implemented in Phase 2B",
        )
    if not isinstance(universe, UniverseManifest):
        raise TypeError("universe must be a UniverseManifest")
    if not isinstance(quote_snapshot, QuoteSnapshotManifest):
        raise TypeError("quote_snapshot must be a QuoteSnapshotManifest")
    if not isinstance(index, IndexManifest):
        raise TypeError("index must be an IndexManifest")
    if not isinstance(sector, SectorManifest):
        raise TypeError("sector must be a SectorManifest")

    cal = calendar or default_calendar()
    as_of_date = run_context.as_of_date
    _validate_calendar(as_of_date, cal)
    _ensure_same_date(universe.as_of_date, as_of_date, "universe")
    _ensure_same_date(quote_snapshot.as_of_date, as_of_date, "quote snapshot")
    _ensure_same_date(index.as_of_date, as_of_date, "index")
    _ensure_same_date(sector.as_of_date, as_of_date, "sector")

    expected_symbols = set(universe.symbols)
    quote_symbols = set(quote_snapshot.quotes)
    missing_quotes = sorted(expected_symbols - quote_symbols)
    if missing_quotes:
        _fail(INCOMPLETE_COVERAGE, f"missing quotes for symbols: {', '.join(missing_quotes)}")
    for symbol, quote in quote_snapshot.quotes.items():
        quote_date = quote.get("quote_date")
        if quote_date != as_of_date:
            _fail(
                INPUT_DATE_MISMATCH,
                f"quote {symbol} quote_date {quote_date} != {as_of_date}",
            )

    if not isinstance(stock_klines, Sequence) or isinstance(stock_klines, (str, bytes)):
        _fail(INCOMPLETE_COVERAGE, "stock_klines must be a sequence")
    kline_by_symbol: dict[str, KlineManifest] = {}
    for item in stock_klines:
        if not isinstance(item, KlineManifest) or isinstance(item, IndexManifest):
            _fail(INCOMPLETE_COVERAGE, "stock_klines contains a non-stock KlineManifest")
        if item.symbol in kline_by_symbol:
            _fail(INCOMPLETE_COVERAGE, f"duplicate stock kline for {item.symbol}")
        kline_by_symbol[item.symbol] = item
    missing_klines = sorted(expected_symbols - set(kline_by_symbol))
    if missing_klines:
        _fail(INCOMPLETE_COVERAGE, f"missing stock klines for: {', '.join(missing_klines)}")
    extra_klines = sorted(set(kline_by_symbol) - expected_symbols)
    if extra_klines:
        _fail(INCOMPLETE_COVERAGE, f"stock klines outside universe: {', '.join(extra_klines)}")
    for item in sorted(kline_by_symbol.values(), key=lambda value: value.symbol):
        _ensure_same_date(item.as_of_date, as_of_date, f"stock kline {item.symbol}")
        _validate_kline_dates(item, as_of_date, "stock kline")

    _ensure_same_date(index.as_of_date, as_of_date, "index")
    _validate_kline_dates(index, as_of_date, "index kline")

    live_inputs = [
        ("universe", universe),
        ("quote snapshot", quote_snapshot),
        *[(f"stock kline {item.symbol}", item) for item in kline_by_symbol.values()],
        ("index kline", index),
        ("sector", sector),
    ]
    for label, item in live_inputs:
        _validate_live_observation_date(item, as_of_date, label)
    _validate_session_closed(as_of_date, cal, live_inputs)

    metadata = {} if provider_version_metadata is None else provider_version_metadata
    if not isinstance(metadata, Mapping):
        raise TypeError("provider_version_metadata must be a mapping")
    execution_date = _next_xshg_session(as_of_date, cal)
    return GenerationInputManifest(
        run_context=run_context,
        universe=universe,
        quote_snapshot=quote_snapshot,
        stock_klines=tuple(sorted(kline_by_symbol.values(), key=lambda value: value.symbol)),
        index=index,
        sector=sector,
        provider_version_metadata=dict(metadata),
        earliest_execution_date=execution_date,
    )


def validate_generation_inputs(*args: Any, **kwargs: Any) -> GenerationInputManifest:
    """Compatibility/readability alias for :func:`freeze_generation_inputs`."""

    return freeze_generation_inputs(*args, **kwargs)


def next_execution_date(
    as_of_date: date | datetime | str,
    calendar: TradingCalendar | None = None,
) -> str:
    """Return the next XSHG session, skipping weekends and holidays."""

    return _next_xshg_session(_canonical_date(as_of_date), calendar or default_calendar())
