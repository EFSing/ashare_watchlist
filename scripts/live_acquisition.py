"""Candidate-bound live input acquisition for the first prospective package.

This module is deliberately an acquisition adapter, not a strategy runner.  It
only assembles and validates a complete close-of-day input package for the
 nominated B candidate.  No provider is called before the official XSHG close,
 and no historical/current-data backfill is supported.

The package returned by :func:`acquire_live_generation_inputs` is in memory
until the caller explicitly persists it.  Persistence is immutable and keyed
by the full generation identity; this module never writes a canonical
watchlist.
"""

from __future__ import annotations

import copy
import hashlib
import importlib
import importlib.metadata
import json
import math
import os
import platform
import tempfile
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

import requests

from b_breakout_retest import STRATEGY_SPEC_SHA256, STRATEGY_VERSION
from generation_contract import (
    ASIA_SHANGHAI,
    EXCHANGE_CALENDARS_VERSION,
    FUTURE_DATA_DETECTED,
    GenerationContractError,
    INCOMPLETE_COVERAGE,
    INPUT_DATE_MISMATCH,
    LIVE_OBSERVED,
    PROVIDER_QFQ_SNAPSHOT,
    READY_FOR_STRATEGY_EVALUATION,
    SESSION_NOT_CLOSED,
    XSHG_CALENDAR,
    GenerationInputManifest,
    IndexManifest,
    KlineManifest,
    QuoteSnapshotManifest,
    RunContext,
    SectorManifest,
    UniverseManifest,
    freeze_generation_inputs,
)
from tencent_quotes import (
    MissingQuoteError,
    QuoteDataError,
    QuoteParseError,
    StaleQuoteError,
    fetch_quotes,
    to_symbol,
)
from trading_calendar import CalendarUnavailable, TradingCalendar, default_calendar


LIVE_INPUT_PACKAGE_SCHEMA = "CANDIDATE_BOUND_LIVE_INPUT_PACKAGE_V1"
GENERATION_IDENTITY_SCHEMA = "CANDIDATE_BOUND_GENERATION_IDENTITY_V1"
MARKET_ENV_SCHEMA = "MARKET_ENV_FROM_TENCENT_QFQ_INDEX_V1"
PROSPECTIVE_PROVENANCE_CONTRACT = "CANDIDATE_BOUND_PROSPECTIVE_INPUT_PROVENANCE_CONTRACT_V1"

PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
PROVIDER_FAILURE = "PROVIDER_FAILURE"
INPUT_CONFLICT = "INPUT_CONFLICT"
MISSING_DISPLAY_NAME = "MISSING_DISPLAY_NAME"
PERSISTENCE_CONFLICT = "PERSISTENCE_CONFLICT"
PERSISTENCE_FAILURE = "PERSISTENCE_FAILURE"

AKSHARE_UNIVERSE_API = "stock_info_a_code_name"
AKSHARE_SECTOR_DEFINITIONS_API = "stock_board_industry_name_em"
AKSHARE_SECTOR_MEMBERS_API = "stock_board_industry_cons_em"
TENCENT_QUOTE_SOURCE = "qt.gtimg.cn"
TENCENT_KLINE_SOURCE = "web.ifzq.gtimg.cn/appstock/app/fqkline/get"
INDEX_SYMBOL = "sh000001"

# B's fixed evaluator reads the last 250 stock bars.  The index market-env
# calculation reads a 20-session moving average and therefore needs 21 bars.
DEFAULT_STOCK_BAR_COUNT = 260
DEFAULT_INDEX_BAR_COUNT = 60
MIN_INDEX_BARS_FOR_MARKET_ENV = 21

_BJT = timezone(timedelta(hours=8))


class LiveAcquisitionError(GenerationContractError):
    """A fail-closed provider, completeness, or persistence violation."""


def _fail(status: str, message: str) -> None:
    raise LiveAcquisitionError(status, message)


def _canonical_date(value: date | datetime | str) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip().replace("/", "-")
    if len(text) == 8 and text.isdigit():
        return datetime.strptime(text, "%Y%m%d").date().isoformat()
    return datetime.strptime(text, "%Y-%m-%d").date().isoformat()


def _canonical_timestamp(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        _fail(INPUT_DATE_MISMATCH, "now_bjt must be timezone-aware")
    return parsed.astimezone(_BJT)


def _timestamp_text(value: datetime) -> str:
    return value.astimezone(_BJT).isoformat()


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256_bytes(_canonical_json(value))


def _copy_json(value: Any, field_name: str) -> Any:
    try:
        encoded = _canonical_json(value)
        return json.loads(encoded.decode("utf-8"))
    except (TypeError, ValueError) as exc:
        _fail(PROVIDER_FAILURE, f"{field_name} is not deterministic JSON: {exc}")


def _missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, float):
        return not math.isfinite(value)
    try:
        item = value.item() if callable(getattr(value, "item", None)) else value
    except Exception:
        item = value
    if isinstance(item, float):
        return not math.isfinite(item)
    return False


def _python_scalar(value: Any) -> Any:
    try:
        value = value.item() if callable(getattr(value, "item", None)) else value
    except Exception:
        pass
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _number(value: Any, field_name: str, *, positive: bool = False, non_negative: bool = False) -> float:
    if _missing(value) or isinstance(value, bool):
        _fail(INCOMPLETE_COVERAGE, f"{field_name} is missing or non-finite")
    try:
        number = float(_python_scalar(value))
    except (TypeError, ValueError) as exc:
        _fail(INCOMPLETE_COVERAGE, f"{field_name} is not numeric")
        raise AssertionError from exc
    if not math.isfinite(number):
        _fail(INCOMPLETE_COVERAGE, f"{field_name} is not finite")
    if positive and number <= 0:
        _fail(INCOMPLETE_COVERAGE, f"{field_name} must be positive")
    if non_negative and number < 0:
        _fail(INCOMPLETE_COVERAGE, f"{field_name} must be non-negative")
    return number


def _code(value: Any, field_name: str) -> str:
    value = _python_scalar(value)
    if _missing(value) or isinstance(value, bool):
        _fail(INCOMPLETE_COVERAGE, f"{field_name} is missing")
    if isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number) or not number.is_integer():
            _fail(INPUT_CONFLICT, f"{field_name} is not an integer stock code")
        text = str(int(number)).zfill(6)
    else:
        text = str(value).strip().lower()
        if text[:2] in {"sh", "sz", "bj"}:
            text = text[2:]
        if text.endswith(".0") and text[:-2].isdigit():
            text = text[:-2]
        if text.isdigit():
            text = text.zfill(6)
    if len(text) != 6 or not text.isdigit():
        _fail(INPUT_CONFLICT, f"{field_name} is not a six-digit A-share code: {value!r}")
    return text


def _text(value: Any, field_name: str) -> str:
    value = _python_scalar(value)
    if _missing(value) or not isinstance(value, str):
        _fail(INCOMPLETE_COVERAGE, f"{field_name} is missing")
    return value.strip()


def _records(frame: Any, field_name: str, required_columns: Mapping[str, Sequence[str]]) -> list[dict[str, Any]]:
    if frame is None:
        _fail(INCOMPLETE_COVERAGE, f"{field_name} returned no frame")
    try:
        if bool(getattr(frame, "empty")):
            _fail(INCOMPLETE_COVERAGE, f"{field_name} returned an empty frame")
    except AttributeError:
        pass
    if hasattr(frame, "columns") and callable(getattr(frame, "to_dict", None)):
        columns = {str(column) for column in frame.columns}
        rows = frame.to_dict(orient="records")
    elif isinstance(frame, Sequence) and not isinstance(frame, (str, bytes)):
        rows = list(frame)
        columns = {str(key) for row in rows if isinstance(row, Mapping) for key in row}
    else:
        _fail(PROVIDER_FAILURE, f"{field_name} returned an unsupported frame type")
    if not rows:
        _fail(INCOMPLETE_COVERAGE, f"{field_name} returned no rows")
    for canonical, aliases in required_columns.items():
        if not any(alias in columns for alias in aliases):
            _fail(PROVIDER_FAILURE, f"{field_name} is missing required column for {canonical}: {aliases}")
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            _fail(PROVIDER_FAILURE, f"{field_name}[{index}] is not a row mapping")
        normalized.append({str(key): _python_scalar(value) for key, value in row.items()})
    return normalized


def _field(row: Mapping[str, Any], aliases: Sequence[str], field_name: str) -> Any:
    for alias in aliases:
        if alias in row:
            return row[alias]
    _fail(PROVIDER_FAILURE, f"row is missing {field_name}")


def _load_akshare(module: ModuleType | Any | None) -> tuple[Any, str]:
    if module is None:
        try:
            module = importlib.import_module("akshare")
        except Exception as exc:
            _fail(PROVIDER_UNAVAILABLE, f"AkShare import failed: {type(exc).__name__}")
    try:
        version = importlib.metadata.version("akshare")
    except importlib.metadata.PackageNotFoundError as exc:
        _fail(PROVIDER_UNAVAILABLE, "AkShare package version is unavailable")
        raise AssertionError from exc
    return module, version


class AkShareClient:
    """Small, injectable wrapper around the exact APIs used by this package."""

    def __init__(self, module: ModuleType | Any | None = None, package_version: str | None = None) -> None:
        self.module, actual_version = _load_akshare(module)
        self.package_version = package_version or actual_version
        if not isinstance(self.package_version, str) or not self.package_version.strip():
            _fail(PROVIDER_UNAVAILABLE, "AkShare package version is empty")
        self.package_version = self.package_version.strip()
        self._apis = (
            AKSHARE_UNIVERSE_API,
            AKSHARE_SECTOR_DEFINITIONS_API,
            AKSHARE_SECTOR_MEMBERS_API,
        )
        missing = [name for name in self._apis if not callable(getattr(self.module, name, None))]
        if missing:
            _fail(PROVIDER_UNAVAILABLE, f"AkShare API capability missing: {', '.join(missing)}")

    def capability_report(self) -> dict[str, Any]:
        return {
            "package": "akshare",
            "version": self.package_version,
            "apis": {name: True for name in self._apis},
        }

    def universe(self) -> Any:
        return self.module.stock_info_a_code_name()

    def sector_definitions(self) -> Any:
        return self.module.stock_board_industry_name_em()

    def sector_members(self, sector_code: str) -> Any:
        return self.module.stock_board_industry_cons_em(symbol=sector_code)


def akshare_runtime_capability() -> dict[str, Any]:
    """Import-only capability probe; it never calls an AkShare data API."""

    return AkShareClient().capability_report()


def _runtime_versions(akshare_version: str) -> dict[str, Any]:
    try:
        exchange_calendars_version = importlib.metadata.version("exchange-calendars")
    except importlib.metadata.PackageNotFoundError:
        _fail(PROVIDER_UNAVAILABLE, "required runtime package version is unavailable: exchange-calendars")
    if exchange_calendars_version != EXCHANGE_CALENDARS_VERSION:
        _fail(
            PROVIDER_UNAVAILABLE,
            f"exchange-calendars runtime is {exchange_calendars_version}, expected {EXCHANGE_CALENDARS_VERSION}",
        )
    required = {"akshare": akshare_version, "exchange_calendars": exchange_calendars_version}
    for package in ("pandas", "requests"):
        try:
            required[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            _fail(PROVIDER_UNAVAILABLE, f"required runtime package version is unavailable: {package}")
    optional: dict[str, str] = {}
    try:
        optional["pyarrow"] = importlib.metadata.version("pyarrow")
    except importlib.metadata.PackageNotFoundError:
        pass
    return {
        "python": platform.python_version(),
        "packages": required | optional,
    }


def _validate_close_window(as_of_date: str, now_bjt: datetime, calendar: TradingCalendar) -> datetime:
    try:
        if not calendar.is_trading_day(as_of_date):
            _fail("CALENDAR_ERROR", f"as_of_date {as_of_date} is not an XSHG trading session")
        session_close = calendar.session_close(as_of_date)
    except LiveAcquisitionError:
        raise
    except CalendarUnavailable as exc:
        _fail("CALENDAR_ERROR", str(exc))
    except Exception as exc:
        _fail("CALENDAR_ERROR", f"XSHG calendar failed: {type(exc).__name__}")
    if session_close.tzinfo is None:
        _fail("CALENDAR_ERROR", "XSHG session close must be timezone-aware")
    session_close = session_close.astimezone(_BJT)
    if now_bjt.date().isoformat() != as_of_date:
        _fail(INPUT_DATE_MISMATCH, f"observation date {now_bjt.date().isoformat()} != as_of_date {as_of_date}")
    if now_bjt < session_close:
        _fail(SESSION_NOT_CLOSED, f"now_bjt {now_bjt.isoformat()} is before session close {session_close.isoformat()}")
    return session_close


def _build_universe(
    frame: Any,
    as_of_date: str,
    retrieved_at_bjt: str,
) -> tuple[UniverseManifest, dict[str, str]]:
    rows = _records(
        frame,
        AKSHARE_UNIVERSE_API,
        {"code": ("code", "证券代码"), "name": ("name", "证券简称")},
    )
    names: dict[str, str] = {}
    for index, row in enumerate(rows):
        symbol = _code(_field(row, ("code", "证券代码"), f"universe[{index}].code"), f"universe[{index}].code")
        name = _text(_field(row, ("name", "证券简称"), f"universe[{index}].name"), f"universe[{index}].name")
        if symbol in names:
            _fail(INPUT_CONFLICT, f"duplicate universe symbol: {symbol}")
        names[symbol] = name
    if not names:
        _fail(INCOMPLETE_COVERAGE, "universe has no symbols")
    return (
        UniverseManifest(
            as_of_date=as_of_date,
            retrieved_at_bjt=retrieved_at_bjt,
            source=f"AkShare.{AKSHARE_UNIVERSE_API}",
            symbols=tuple(names),
            temporal_semantics=LIVE_OBSERVED,
        ),
        dict(sorted(names.items())),
    )


def _build_sector(
    client: AkShareClient,
    as_of_date: str,
    retrieved_at_bjt: str,
    names: Mapping[str, str],
) -> SectorManifest:
    definition_rows = _records(
        client.sector_definitions(),
        AKSHARE_SECTOR_DEFINITIONS_API,
        {
            "sector_rank": ("排名", "rank", "sector_rank"),
            "sector_name": ("板块名称", "sector_name", "name"),
            "sector_code": ("板块代码", "sector_code", "code"),
            "sector_chg": ("涨跌幅", "sector_chg", "change_pct"),
        },
    )
    definitions: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(definition_rows):
        sector_code = _text(_field(row, ("板块代码", "sector_code", "code"), f"sector definition[{index}].code"), "sector code")
        sector_name = _text(_field(row, ("板块名称", "sector_name", "name"), f"sector definition[{index}].name"), "sector name")
        rank = _number(_field(row, ("排名", "rank", "sector_rank"), f"sector definition[{index}].rank"), "sector rank", positive=True)
        change = _number(_field(row, ("涨跌幅", "sector_chg", "change_pct"), f"sector definition[{index}].change"), "sector change")
        if sector_code in definitions or any(item["sector_name"] == sector_name for item in definitions.values()):
            _fail(INPUT_CONFLICT, f"duplicate sector definition: {sector_code}/{sector_name}")
        definitions[sector_code] = {
            "sector_code": sector_code,
            "sector_name": sector_name,
            "sector_rank": rank,
            "sector_chg": change,
        }
    if not definitions:
        _fail(INCOMPLETE_COVERAGE, "sector definitions are empty")

    members: dict[str, list[dict[str, Any]]] = {}
    by_symbol: dict[str, dict[str, Any]] = {}
    for sector_code, definition in sorted(definitions.items()):
        rows = _records(
            client.sector_members(sector_code),
            f"{AKSHARE_SECTOR_MEMBERS_API}[{sector_code}]",
            {"code": ("代码", "code"), "name": ("名称", "name")},
        )
        sector_members: list[dict[str, Any]] = []
        for index, row in enumerate(rows):
            symbol = _code(_field(row, ("代码", "code"), f"{sector_code}[{index}].code"), f"{sector_code}[{index}].code")
            member_name = _text(_field(row, ("名称", "name"), f"{sector_code}[{index}].name"), f"{sector_code}[{index}].name")
            if symbol not in names:
                _fail(INPUT_CONFLICT, f"sector member {symbol} is outside the T-date universe")
            if member_name != names[symbol]:
                _fail(INPUT_CONFLICT, f"display-name conflict for {symbol}: universe/member")
            if symbol in by_symbol:
                _fail(INPUT_CONFLICT, f"symbol belongs to multiple sector memberships: {symbol}")
            record = {
                "symbol": symbol,
                "display_name": member_name,
                "sector_code": sector_code,
                "sector_name": definition["sector_name"],
                "sector_rank": definition["sector_rank"],
                "sector_chg": definition["sector_chg"],
            }
            by_symbol[symbol] = record
            sector_members.append(record)
        if not sector_members:
            _fail(INCOMPLETE_COVERAGE, f"sector {sector_code} has no members")
        members[sector_code] = sorted(sector_members, key=lambda item: item["symbol"])

    missing = sorted(set(names) - set(by_symbol))
    if missing:
        _fail(INCOMPLETE_COVERAGE, f"universe symbols missing sector membership: {', '.join(missing)}")
    rank_input = [by_symbol[symbol] for symbol in sorted(by_symbol)]
    return SectorManifest(
        as_of_date=as_of_date,
        retrieved_at_bjt=retrieved_at_bjt,
        source=(
            f"AkShare.{AKSHARE_SECTOR_DEFINITIONS_API}+"
            f"AkShare.{AKSHARE_SECTOR_MEMBERS_API}"
        ),
        definitions=definitions,
        members=members,
        rank_input=rank_input,
        temporal_semantics=LIVE_OBSERVED,
    )


def _request_json(
    url: str,
    *,
    timeout: float,
    retries: int,
    request_get: Callable[..., Any],
) -> Mapping[str, Any]:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = request_get(url, timeout=timeout)
            raise_for_status = getattr(response, "raise_for_status", None)
            if callable(raise_for_status):
                raise_for_status()
            payload = response.json()
            if not isinstance(payload, Mapping):
                raise ValueError("response JSON is not an object")
            return payload
        except Exception as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(attempt + 1)
    _fail(PROVIDER_FAILURE, f"Tencent Kline request failed after {retries} attempts: {type(last_error).__name__}")
    raise AssertionError


def _fetch_qfq_bars(
    symbol: str,
    *,
    count: int,
    as_of_date: str,
    timeout: float,
    retries: int,
    request_get: Callable[..., Any],
) -> list[dict[str, Any]]:
    provider_symbol = to_symbol(symbol)
    url = f"https://{TENCENT_KLINE_SOURCE}?param={provider_symbol},day,,,{count},qfq"
    payload = _request_json(url, timeout=timeout, retries=retries, request_get=request_get)
    data = payload.get("data")
    if not isinstance(data, Mapping):
        _fail(PROVIDER_FAILURE, f"Tencent Kline response has no data object for {provider_symbol}")
    record = data.get(provider_symbol)
    if not isinstance(record, Mapping):
        _fail(INCOMPLETE_COVERAGE, f"Tencent Kline response has no symbol record for {provider_symbol}")
    raw_bars = record.get("qfqday")
    if not isinstance(raw_bars, Sequence) or isinstance(raw_bars, (str, bytes)) or not raw_bars:
        _fail(INCOMPLETE_COVERAGE, f"Tencent qfqday is empty for {provider_symbol}")
    bars: list[dict[str, Any]] = []
    seen_dates: set[str] = set()
    for index, raw_bar in enumerate(raw_bars):
        if not isinstance(raw_bar, Sequence) or isinstance(raw_bar, (str, bytes)) or len(raw_bar) < 6:
            _fail(PROVIDER_FAILURE, f"Tencent qfq bar {provider_symbol}[{index}] is incomplete")
        try:
            bar_date = _canonical_date(raw_bar[0])
        except (TypeError, ValueError) as exc:
            _fail(PROVIDER_FAILURE, f"Tencent qfq bar {provider_symbol}[{index}] has invalid date")
            raise AssertionError from exc
        if bar_date in seen_dates:
            _fail(INPUT_CONFLICT, f"duplicate Tencent qfq bar date for {provider_symbol}: {bar_date}")
        seen_dates.add(bar_date)
        if bar_date > as_of_date:
            _fail(FUTURE_DATA_DETECTED, f"Tencent qfq bar {provider_symbol} is after {as_of_date}: {bar_date}")
        opening = _number(raw_bar[1], f"{provider_symbol}[{index}].open", positive=True)
        closing = _number(raw_bar[2], f"{provider_symbol}[{index}].close", positive=True)
        high = _number(raw_bar[3], f"{provider_symbol}[{index}].high", positive=True)
        low = _number(raw_bar[4], f"{provider_symbol}[{index}].low", positive=True)
        volume = _number(raw_bar[5], f"{provider_symbol}[{index}].volume", non_negative=True)
        if high < low or high < opening or high < closing or low > opening or low > closing:
            _fail(INPUT_CONFLICT, f"Tencent qfq OHLC conflict for {provider_symbol} on {bar_date}")
        bars.append({"date": bar_date, "open": opening, "high": high, "low": low, "close": closing, "volume": volume})
    bars.sort(key=lambda item: item["date"])
    if len(bars) < count:
        _fail(INCOMPLETE_COVERAGE, f"Tencent qfq coverage for {provider_symbol} is {len(bars)} < {count}")
    if bars[-1]["date"] != as_of_date:
        _fail(INPUT_DATE_MISMATCH, f"Tencent qfq latest bar for {provider_symbol} is {bars[-1]['date']} != {as_of_date}")
    return bars


def _market_env(index: IndexManifest) -> dict[str, Any]:
    if len(index.bars) < MIN_INDEX_BARS_FOR_MARKET_ENV:
        _fail(INCOMPLETE_COVERAGE, f"index needs at least {MIN_INDEX_BARS_FOR_MARKET_ENV} bars for market_env")
    closes = [_number(bar.get("close"), f"index close {bar.get('date')}", positive=True) for bar in index.bars]
    volumes = [_number(bar.get("volume"), f"index volume {bar.get('date')}", non_negative=True) for bar in index.bars]
    previous_volumes = volumes[-21:-1]
    mean_previous_volume = sum(previous_volumes) / len(previous_volumes)
    if mean_previous_volume <= 0:
        _fail(INCOMPLETE_COVERAGE, "index prior-20 volume mean is not positive")
    close = closes[-1]
    ma5 = sum(closes[-5:]) / 5
    ma20 = sum(closes[-20:]) / 20
    chg5 = (close / closes[-6] - 1.0) * 100.0
    vol_ratio = volumes[-1] / mean_previous_volume
    above_ma5 = close >= ma5
    above_ma20 = close >= ma20
    score = 3 * int(above_ma5) + 3 * int(above_ma20) + int(chg5 > 0) + int(vol_ratio >= 0.8)
    grade = "A" if score >= 6 else ("B" if score >= 4 else "C")
    return {
        "schema_version": MARKET_ENV_SCHEMA,
        "as_of_date": index.as_of_date,
        "symbol": index.symbol,
        "provider": index.provider,
        "source": index.source,
        "adjustment_mode": index.adjustment_mode,
        "index_normalized_data_sha256": index.normalized_data_sha256,
        "grade": grade,
        "score": score,
        "detail": {
            "上证收盘": round(close, 2),
            "站MA5": above_ma5,
            "站MA20": above_ma20,
            "5日涨跌幅%": round(chg5, 2),
            "量能比": round(vol_ratio, 2),
        },
    }


def _generation_identity_payload(
    manifest: GenerationInputManifest,
    display_names: Mapping[str, str],
    market_env: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": GENERATION_IDENTITY_SCHEMA,
        "input_package_schema": LIVE_INPUT_PACKAGE_SCHEMA,
        "provenance_contract": PROSPECTIVE_PROVENANCE_CONTRACT,
        "candidate": {
            "strategy_version": STRATEGY_VERSION,
            "spec_sha256": STRATEGY_SPEC_SHA256,
        },
        "as_of_date": manifest.signal_date,
        "earliest_execution_date": manifest.earliest_execution_date,
        "input_fingerprint": manifest.input_fingerprint,
        "display_names": dict(sorted(display_names.items())),
        "market_env": _copy_json(dict(market_env), "market_env"),
    }


@dataclass(frozen=True)
class LiveInputPackage:
    """Complete in-memory candidate-bound input package; no watchlist output."""

    generation_input_manifest: GenerationInputManifest
    display_names: Mapping[str, str]
    market_env: Mapping[str, Any]
    provenance: Mapping[str, Any]
    generation_identity_payload: Mapping[str, Any] = field(init=False)
    generation_fingerprint: str = field(init=False)
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.generation_input_manifest, GenerationInputManifest):
            raise ValueError("generation_input_manifest must be a GenerationInputManifest")
        if self.generation_input_manifest.status != READY_FOR_STRATEGY_EVALUATION:
            raise ValueError("live input package requires a READY generation manifest")
        if not isinstance(self.display_names, Mapping) or not isinstance(self.market_env, Mapping):
            raise ValueError("display_names and market_env must be mappings")
        names = {str(key).strip().lower(): _text(value, f"display_names[{key}]") for key, value in self.display_names.items()}
        expected = set(self.generation_input_manifest.universe.symbols)
        if set(names) != expected:
            missing = sorted(expected - set(names))
            extra = sorted(set(names) - expected)
            _fail(MISSING_DISPLAY_NAME, f"display name coverage mismatch; missing={missing}, extra={extra}")
        object.__setattr__(self, "display_names", dict(sorted(names.items())))
        canonical_env = _copy_json(dict(self.market_env), "market_env")
        if canonical_env.get("as_of_date") != self.generation_input_manifest.signal_date:
            _fail(INPUT_DATE_MISMATCH, "market_env.as_of_date does not equal signal date")
        if canonical_env.get("adjustment_mode") != PROVIDER_QFQ_SNAPSHOT:
            _fail("UNSUPPORTED_MODE", "market_env must retain PROVIDER_QFQ_SNAPSHOT semantics")
        object.__setattr__(self, "market_env", canonical_env)
        if not isinstance(self.provenance, Mapping):
            _fail(PROVIDER_FAILURE, "provenance must be a mapping")
        provenance = _copy_json(dict(self.provenance), "provenance")
        if provenance.get("contract") != PROSPECTIVE_PROVENANCE_CONTRACT:
            _fail(PROVIDER_FAILURE, "provenance contract is missing or unsupported")
        if provenance.get("observation_status") != LIVE_OBSERVED:
            _fail("UNSUPPORTED_MODE", "live input provenance must be LIVE_OBSERVED")
        retrieved_at = provenance.get("retrieved_at_bjt")
        if not isinstance(retrieved_at, str):
            _fail(INPUT_DATE_MISMATCH, "provenance.retrieved_at_bjt is missing")
        retrieved_at_dt = _canonical_timestamp(retrieved_at)
        if retrieved_at_dt.date().isoformat() != self.generation_input_manifest.signal_date:
            _fail(INPUT_DATE_MISMATCH, "provenance.retrieved_at_bjt does not equal signal date")
        candidate = provenance.get("candidate")
        if not isinstance(candidate, Mapping):
            _fail(INPUT_CONFLICT, "provenance candidate identity is missing")
        if (
            candidate.get("strategy_version") != STRATEGY_VERSION
            or candidate.get("spec_sha256") != STRATEGY_SPEC_SHA256
        ):
            _fail(INPUT_CONFLICT, "provenance candidate identity does not match the nominated candidate")
        calendar = provenance.get("calendar")
        if not isinstance(calendar, Mapping):
            _fail(PROVIDER_FAILURE, "provenance calendar evidence is missing")
        if calendar.get("name") != XSHG_CALENDAR or calendar.get("timezone") != ASIA_SHANGHAI:
            _fail("UNSUPPORTED_MODE", "provenance calendar must be XSHG in Asia/Shanghai")
        session_close = calendar.get("session_close")
        if not isinstance(session_close, str):
            _fail(PROVIDER_FAILURE, "provenance session-close evidence is missing")
        if retrieved_at_dt < _canonical_timestamp(session_close):
            _fail(SESSION_NOT_CLOSED, "provenance retrieval precedes XSHG session close")
        if calendar.get("earliest_execution_date") != self.generation_input_manifest.earliest_execution_date:
            _fail(INPUT_DATE_MISMATCH, "provenance T+1 identity does not match the generation manifest")
        checks = provenance.get("quality_checks")
        if not isinstance(checks, Mapping):
            _fail(PROVIDER_FAILURE, "provenance quality checks are missing")
        required_checks = (
            "observation_date",
            "freshness_and_session_close",
            "universe_non_empty_and_unique",
            "sector_definitions_membership_rank",
            "display_name_coverage_and_conflicts",
            "quote_t_date_and_coverage",
            "stock_kline_t_date_no_future_bar",
            "index_kline_t_date_no_future_bar",
        )
        if any(checks.get(name) != "PASS" for name in required_checks):
            _fail(PROVIDER_FAILURE, "provenance quality checks are not all PASS")
        if checks.get("generation_manifest") != READY_FOR_STRATEGY_EVALUATION:
            _fail(PROVIDER_FAILURE, "provenance generation manifest is not READY")
        recovery = provenance.get("recovery")
        if not isinstance(recovery, Mapping) or recovery.get("formal_output_created") is not False:
            _fail(PROVIDER_FAILURE, "live input package cannot claim formal output creation")
        object.__setattr__(self, "provenance", provenance)
        identity_payload = _generation_identity_payload(
            self.generation_input_manifest,
            self.display_names,
            self.market_env,
        )
        object.__setattr__(self, "generation_identity_payload", identity_payload)
        object.__setattr__(self, "generation_fingerprint", _sha256_json(identity_payload))
        object.__setattr__(self, "content_sha256", _sha256_json(self._payload_without_content_hash()))

    def _payload_without_content_hash(self) -> dict[str, Any]:
        return {
            "schema_version": LIVE_INPUT_PACKAGE_SCHEMA,
            "status": self.generation_input_manifest.status,
            "candidate": {
                "strategy_version": STRATEGY_VERSION,
                "spec_sha256": STRATEGY_SPEC_SHA256,
            },
            "generation_input_manifest": self.generation_input_manifest.to_dict(),
            "display_names": dict(self.display_names),
            "market_env": copy.deepcopy(dict(self.market_env)),
            "provenance": copy.deepcopy(dict(self.provenance)),
            "generation_identity_payload": copy.deepcopy(dict(self.generation_identity_payload)),
            "generation_fingerprint": self.generation_fingerprint,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload_without_content_hash()
        payload["content_sha256"] = self.content_sha256
        return payload

    def to_bytes(self) -> bytes:
        return _canonical_json(self.to_dict())


@dataclass(frozen=True)
class PersistedInputPackage:
    path: Path
    logical_path: str
    file_sha256: str
    content_sha256: str
    status: str


def _logical_package_path(package: LiveInputPackage) -> Path:
    return Path("prospective_inputs") / package.generation_input_manifest.signal_date.replace("-", "") / (
        f"{package.generation_input_manifest.signal_date}_{package.generation_fingerprint}.json"
    )


def persist_live_input_package(package: LiveInputPackage, output_root: Path) -> PersistedInputPackage:
    """Persist only a complete package, without creating canonical watchlist output."""

    if not isinstance(package, LiveInputPackage):
        _fail(PERSISTENCE_FAILURE, "only a LiveInputPackage can be persisted")
    if package.generation_input_manifest.status != READY_FOR_STRATEGY_EVALUATION:
        _fail(PERSISTENCE_FAILURE, "refusing to persist a non-READY generation package")
    root = Path(output_root)
    relative = _logical_package_path(package)
    path = root / relative
    payload = package.to_bytes()
    if path.exists():
        try:
            existing = path.read_bytes()
        except OSError as exc:
            _fail(PERSISTENCE_FAILURE, f"cannot read existing package: {type(exc).__name__}")
        if existing != payload:
            _fail(PERSISTENCE_CONFLICT, f"existing package differs at logical identity {relative.as_posix()}")
        return PersistedInputPackage(path, relative.as_posix(), _sha256_bytes(existing), package.content_sha256, "ALREADY_CURRENT")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        try:
            if "temporary" in locals() and temporary.exists():
                temporary.unlink()
        except OSError:
            pass
        _fail(PERSISTENCE_FAILURE, f"cannot persist live input package: {type(exc).__name__}")
    return PersistedInputPackage(path, relative.as_posix(), _sha256_bytes(payload), package.content_sha256, "PERSISTED")


def acquire_live_generation_inputs(
    as_of_date: date | datetime | str,
    *,
    calendar: TradingCalendar | None = None,
    now_bjt: datetime | str | None = None,
    akshare_module: ModuleType | Any | None = None,
    akshare_version: str | None = None,
    request_get: Callable[..., Any] | None = None,
    quote_timeout: float = 15.0,
    quote_retries: int = 3,
    kline_timeout: float = 15.0,
    kline_retries: int = 3,
    stock_bar_count: int = DEFAULT_STOCK_BAR_COUNT,
    index_bar_count: int = DEFAULT_INDEX_BAR_COUNT,
) -> LiveInputPackage:
    """Acquire one real T-close input package after all preconditions pass.

    The provider calls are intentionally after ``_validate_close_window``.  A
    caller cannot use this function to turn a pre-close, future-date, or
    retrospective call into a live observation.
    """

    target_date = _canonical_date(as_of_date)
    observed_at = _canonical_timestamp(now_bjt or datetime.now(_BJT))
    cal = calendar or default_calendar()
    _validate_close_window(target_date, observed_at, cal)
    if stock_bar_count <= 0 or index_bar_count <= 0:
        _fail(INCOMPLETE_COVERAGE, "bar counts must be positive")

    client = AkShareClient(akshare_module, akshare_version)
    retrieved_at_bjt = _timestamp_text(observed_at)
    try:
        universe_frame = client.universe()
    except Exception as exc:
        _fail(PROVIDER_FAILURE, f"AkShare universe acquisition failed: {type(exc).__name__}")
    universe, display_names = _build_universe(universe_frame, target_date, retrieved_at_bjt)
    try:
        sector = _build_sector(client, target_date, retrieved_at_bjt, display_names)
    except LiveAcquisitionError:
        raise
    except Exception as exc:
        _fail(PROVIDER_FAILURE, f"AkShare sector acquisition failed: {type(exc).__name__}")

    get = request_get or requests.get
    try:
        quotes = fetch_quotes(
            universe.symbols,
            expected_date=target_date,
            timeout=quote_timeout,
            retries=quote_retries,
            request_get=get,
        )
    except MissingQuoteError as exc:
        _fail(INCOMPLETE_COVERAGE, "Tencent quote coverage is incomplete")
        raise AssertionError from exc
    except StaleQuoteError as exc:
        _fail(INPUT_DATE_MISMATCH, "Tencent quote is not a T-date quote")
        raise AssertionError from exc
    except QuoteParseError as exc:
        if str(exc) == "empty Tencent quote response":
            _fail(INCOMPLETE_COVERAGE, "Tencent quote response is empty")
        _fail(PROVIDER_FAILURE, "Tencent quote response is malformed")
        raise AssertionError from exc
    except QuoteDataError as exc:
        _fail(PROVIDER_FAILURE, f"Tencent quote acquisition failed: {type(exc).__name__}")
        raise AssertionError from exc
    expected_symbols = set(universe.symbols)
    actual_symbols = set(quotes)
    if actual_symbols != expected_symbols:
        missing = sorted(expected_symbols - actual_symbols)
        extra = sorted(actual_symbols - expected_symbols)
        _fail(INPUT_CONFLICT, f"Tencent quote identity mismatch; missing={missing}, extra={extra}")
    quote_manifest = QuoteSnapshotManifest(
        as_of_date=target_date,
        retrieved_at_bjt=retrieved_at_bjt,
        source=TENCENT_QUOTE_SOURCE,
        provider="Tencent",
        quotes=quotes,
        temporal_semantics=LIVE_OBSERVED,
    )

    stock_klines: list[KlineManifest] = []
    for symbol in universe.symbols:
        bars = _fetch_qfq_bars(
            symbol,
            count=stock_bar_count,
            as_of_date=target_date,
            timeout=kline_timeout,
            retries=kline_retries,
            request_get=get,
        )
        stock_klines.append(
            KlineManifest(
                symbol=symbol,
                as_of_date=target_date,
                retrieved_at_bjt=retrieved_at_bjt,
                bars=bars,
                provider="Tencent",
                adjustment_mode=PROVIDER_QFQ_SNAPSHOT,
                source=TENCENT_KLINE_SOURCE,
                temporal_semantics=LIVE_OBSERVED,
            )
        )
    index_bars = _fetch_qfq_bars(
        INDEX_SYMBOL,
        count=index_bar_count,
        as_of_date=target_date,
        timeout=kline_timeout,
        retries=kline_retries,
        request_get=get,
    )
    index = IndexManifest(
        symbol=INDEX_SYMBOL,
        as_of_date=target_date,
        retrieved_at_bjt=retrieved_at_bjt,
        bars=index_bars,
        provider="Tencent",
        adjustment_mode=PROVIDER_QFQ_SNAPSHOT,
        source=TENCENT_KLINE_SOURCE,
        temporal_semantics=LIVE_OBSERVED,
    )
    market_env = _market_env(index)
    runtime_versions = _runtime_versions(client.package_version)
    provider_metadata = {
        "runtime": runtime_versions,
        "providers": {
            "universe": {"provider": "AkShare", "api": AKSHARE_UNIVERSE_API},
            "sector": {
                "provider": "AkShare",
                "definitions_api": AKSHARE_SECTOR_DEFINITIONS_API,
                "members_api": AKSHARE_SECTOR_MEMBERS_API,
            },
            "quotes": {"provider": "Tencent", "source": TENCENT_QUOTE_SOURCE},
            "stock_klines": {"provider": "Tencent", "source": TENCENT_KLINE_SOURCE, "adjustment_mode": PROVIDER_QFQ_SNAPSHOT},
            "index": {"provider": "Tencent", "source": TENCENT_KLINE_SOURCE, "adjustment_mode": PROVIDER_QFQ_SNAPSHOT},
        },
        "akshare_capability": client.capability_report(),
    }
    run_context = RunContext(
        as_of_date=target_date,
        mode="close",
        timezone=ASIA_SHANGHAI,
        calendar="XSHG",
        historical=False,
        provider_version_metadata=provider_metadata,
    )
    try:
        manifest = freeze_generation_inputs(
            run_context,
            universe,
            quote_manifest,
            tuple(stock_klines),
            index,
            sector,
            calendar=cal,
            provider_version_metadata=provider_metadata,
        )
    except GenerationContractError as exc:
        raise LiveAcquisitionError(exc.status, str(exc)) from exc
    provenance = {
        "contract": PROSPECTIVE_PROVENANCE_CONTRACT,
        "observation_status": LIVE_OBSERVED,
        "retrieved_at_bjt": retrieved_at_bjt,
        "known_at_rule": "acquisition occurs only when retrieved_at_bjt >= XSHG session close on T",
        "candidate": {"strategy_version": STRATEGY_VERSION, "spec_sha256": STRATEGY_SPEC_SHA256},
        "calendar": {
            "name": "XSHG",
            "timezone": ASIA_SHANGHAI,
            "session_close": _timestamp_text(_validate_close_window(target_date, observed_at, cal)),
            "earliest_execution_date": manifest.earliest_execution_date,
        },
        "provider_version_metadata": provider_metadata,
        "quality_checks": {
            "observation_date": "PASS",
            "freshness_and_session_close": "PASS",
            "universe_non_empty_and_unique": "PASS",
            "sector_definitions_membership_rank": "PASS",
            "display_name_coverage_and_conflicts": "PASS",
            "quote_t_date_and_coverage": "PASS",
            "stock_kline_t_date_no_future_bar": "PASS",
            "index_kline_t_date_no_future_bar": "PASS",
            "generation_manifest": manifest.status,
        },
        "recovery": {
            "status": "PERSISTABLE_IMMUTABLE_PACKAGE",
            "logical_identity": "generation_fingerprint",
            "formal_output_created": False,
        },
    }
    return LiveInputPackage(manifest, display_names, market_env, provenance)


__all__ = [
    "AKSHARE_SECTOR_DEFINITIONS_API",
    "AKSHARE_SECTOR_MEMBERS_API",
    "AKSHARE_UNIVERSE_API",
    "AkShareClient",
    "DEFAULT_INDEX_BAR_COUNT",
    "DEFAULT_STOCK_BAR_COUNT",
    "GENERATION_IDENTITY_SCHEMA",
    "INPUT_CONFLICT",
    "LiveAcquisitionError",
    "LiveInputPackage",
    "MARKET_ENV_SCHEMA",
    "PROSPECTIVE_PROVENANCE_CONTRACT",
    "PersistedInputPackage",
    "PERSISTENCE_CONFLICT",
    "PERSISTENCE_FAILURE",
    "PROVIDER_FAILURE",
    "PROVIDER_UNAVAILABLE",
    "TENCENT_KLINE_SOURCE",
    "acquire_live_generation_inputs",
    "akshare_runtime_capability",
    "persist_live_input_package",
]
