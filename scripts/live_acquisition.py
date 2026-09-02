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
import unicodedata
import urllib.parse
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

import requests

from b_breakout_retest_v1_1 import STRATEGY_SPEC_SHA256, STRATEGY_VERSION
from generation_contract import (
    ASIA_SHANGHAI,
    EXCHANGE_CALENDARS_VERSION,
    FUTURE_DATA_DETECTED,
    GenerationContractError,
    INCOMPLETE_COVERAGE,
    INPUT_DATE_MISMATCH,
    LIVE_OBSERVED,
    PROVIDER_QFQ_SNAPSHOT,
    PROVIDER_RAW_SNAPSHOT,
    READY_FOR_STRATEGY_EVALUATION,
    SESSION_NOT_CLOSED,
    TRADABLE_UNIVERSE_SCOPE_V1,
    TRADABLE_UNIVERSE_SCOPE_VERSION,
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


LIVE_INPUT_PACKAGE_SCHEMA = "CANDIDATE_BOUND_LIVE_INPUT_PACKAGE_V4"
GENERATION_IDENTITY_SCHEMA = "CANDIDATE_BOUND_GENERATION_IDENTITY_V4"
MARKET_ENV_SCHEMA = "MARKET_ENV_FROM_PROVIDER_INDEX_V2"
PROSPECTIVE_PROVENANCE_CONTRACT = "CANDIDATE_BOUND_PROSPECTIVE_INPUT_PROVENANCE_CONTRACT_V3"
SECTOR_RESOLUTION_POLICY = "LEGACY_PROVIDER_ORDER_LAST_WRITE_WINS_V1"
DISPLAY_NAME_CONSISTENCY_POLICY = "DISPLAY_NAME_CONSISTENCY_POLICY_V2_SYMBOL_AUTHORITATIVE"
DISPLAY_NAME_NORMALIZATION_VERSION = "DISPLAY_NAME_NORMALIZATION_NFKC_TRIM_EXPLICIT_ZERO_WIDTH_V1"
DISPLAY_NAME_NORMALIZATION_ZERO_WIDTH_CODEPOINTS = (0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF)
DISPLAY_NAME_NORMALIZATION_RULE = (
    "remove explicit zero-width formatting characters; Unicode NFKC; "
    "trim leading/trailing whitespace"
)

PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
PROVIDER_FAILURE = "PROVIDER_FAILURE"
INPUT_CONFLICT = "INPUT_CONFLICT"
MISSING_DISPLAY_NAME = "MISSING_DISPLAY_NAME"
PERSISTENCE_CONFLICT = "PERSISTENCE_CONFLICT"
PERSISTENCE_FAILURE = "PERSISTENCE_FAILURE"

HITHINK_BASE_URL = "https://fuyao.aicubes.cn"
HITHINK_API_KEY_ENV = "HITHINK_FINANCE_API_KEY"
HITHINK_API_VERSION = "FINANCIAL_API_REST_V1"
HITHINK_UNIVERSE_API = "/api/meta/tickers/list"
HITHINK_QUOTE_API = "/api/a-share/prices/snapshot"
HITHINK_STOCK_KLINE_API = "/api/a-share/prices/historical"
HITHINK_INDEX_KLINE_API = "/api/a-share-index/prices/historical"
HITHINK_ADJUSTMENT_API = "/api/a-share/corporate-actions/adjustment-factors"
AKSHARE_SINA_SPOT_API = "stock_sector_spot"
AKSHARE_SINA_DETAIL_API = "stock_sector_detail"
SINA_TAXONOMY = "新浪行业"
SINA_SOURCE_URL = "http://finance.sina.com.cn/stock/sl/"
SINA_SPOT_SOURCE_URL = "http://vip.stock.finance.sina.com.cn/q/view/newSinaHy.php"
SINA_DETAIL_COUNT_SOURCE_URL = "http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeStockCount"
SINA_DETAIL_SOURCE_URL = "http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
HITHINK_LIVE_PRIMARY = "SUPPORTED"
EXACT_SINA_SECTOR_SOURCE = "AVAILABLE"
MARKET_DATA_FAILOVER_POLICY_VERSION = "LIVE_MARKET_DATA_FAILOVER_POLICY_V1"
TENCENT_FALLBACK_VERSION = "TENCENT_QFQ_FALLBACK_V1"
TENCENT_QUOTE_SOURCE = "qt.gtimg.cn"
TENCENT_KLINE_SOURCE = "web.ifzq.gtimg.cn/appstock/app/fqkline/get"
INDEX_SYMBOL = "sh000001"
HITHINK_INDEX_SYMBOL = "000001.SH"


def _tradable_universe_scope_metadata() -> dict[str, Any]:
    return {
        "version": TRADABLE_UNIVERSE_SCOPE_VERSION,
        "name": TRADABLE_UNIVERSE_SCOPE_V1,
        "asset_type": "a-share",
        "included_exchanges": ["SH", "SZ"],
        "excluded_exchanges": ["BJ"],
    }


def _display_name_policy_metadata() -> dict[str, Any]:
    return {
        "version": DISPLAY_NAME_CONSISTENCY_POLICY,
        "security_identity": "exact_symbol",
        "comparison_normalization_version": DISPLAY_NAME_NORMALIZATION_VERSION,
        "mismatch_action": "RETAIN_RAW_AND_AUDIT;DO_NOT_JOIN_OR_FILTER_BY_NAME",
        "fuzzy_reconciliation": False,
        "interior_whitespace_removed": False,
        "status_suffixes_removed": False,
    }

# B's fixed evaluator reads the last 250 stock bars.  The index market-env
# calculation reads a 20-session moving average and therefore needs 21 bars.
DEFAULT_STOCK_BAR_COUNT = 260
DEFAULT_INDEX_BAR_COUNT = 60
MIN_INDEX_BARS_FOR_MARKET_ENV = 21

_BJT = timezone(timedelta(hours=8))

# AkShare reads are provider calls, not input semantics.  Keep the retry
# policy deliberately small and fixed: a transient transport failure may be
# retried for the same read, but a malformed/empty/conflicting response is
# validated exactly once and is never hidden by another provider call.
AKSHARE_MAX_ATTEMPTS = 3
AKSHARE_RETRY_BACKOFF_SECONDS = 0.25
HITHINK_MAX_ATTEMPTS = 3
HITHINK_RETRY_BACKOFF_SECONDS = 0.25
ALLOW_TENCENT_KLINE_FALLBACK = True


class LiveAcquisitionError(GenerationContractError):
    """A fail-closed provider, completeness, or persistence violation."""

    def __init__(
        self,
        status: str,
        message: str,
        diagnostics: Mapping[str, Any] | None = None,
    ) -> None:
        self.diagnostics = copy.deepcopy(dict(diagnostics or {}))
        super().__init__(status, message)


class _AkShareReadFailure(RuntimeError):
    """A transient AkShare read exhausted its bounded attempts."""

    def __init__(self, api_name: str, attempts: int, cause: Exception) -> None:
        self.api_name = api_name
        self.attempts = attempts
        self.cause = cause
        super().__init__(f"{api_name} failed after {attempts} attempts: {type(cause).__name__}")


def _fail(
    status: str,
    message: str,
    diagnostics: Mapping[str, Any] | None = None,
) -> None:
    raise LiveAcquisitionError(status, message, diagnostics)


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


def _hithink_thscode(symbol: str) -> str:
    code = _code(symbol, "symbol")
    exchange = "SH" if code.startswith("6") else "SZ"
    return f"{code}.{exchange}"


def _text(value: Any, field_name: str) -> str:
    value = _python_scalar(value)
    if _missing(value) or not isinstance(value, str):
        _fail(INCOMPLETE_COVERAGE, f"{field_name} is missing")
    return value.strip()


def _display_name(value: Any, field_name: str) -> str:
    """Validate a provider name while preserving its exact raw value."""

    value = _python_scalar(value)
    if _missing(value) or not isinstance(value, str):
        _fail(INCOMPLETE_COVERAGE, f"{field_name} is missing")
    return value


def normalize_display_name(value: str) -> str:
    """Apply only the pre-registered, semantics-preserving name cleanup."""

    if not isinstance(value, str):
        raise TypeError("display name must be a string")
    without_zero_width = "".join(
        character
        for character in value
        if ord(character) not in DISPLAY_NAME_NORMALIZATION_ZERO_WIDTH_CODEPOINTS
    )
    return unicodedata.normalize("NFKC", without_zero_width).strip()


def _code_points(value: str) -> str:
    return " ".join(f"U+{ord(character):04X}" for character in value)


def _display_name_mismatch_diagnostics(
    client: SinaSectorClient,
    names: Mapping[str, str],
    symbol: str,
    sector_name: str,
    *,
    sector_code: str,
    sector_label: str,
) -> dict[str, Any]:
    universe_name = names[symbol]
    return {
        "symbol": symbol,
        "sector_code": sector_code,
        "sector_name": sector_label,
        "universe_raw_name": universe_name,
        "sector_raw_name": sector_name,
        "normalized_universe_name": normalize_display_name(universe_name),
        "normalized_sector_name": normalize_display_name(sector_name),
        "universe_name_code_points": _code_points(universe_name),
        "sector_name_code_points": _code_points(sector_name),
        "normalization_version": DISPLAY_NAME_NORMALIZATION_VERSION,
        "policy_version": DISPLAY_NAME_CONSISTENCY_POLICY,
        "universe_count_reached": len(names),
        "sector_definition_count_reached": (
            client.sector_definition_count
            if client.sector_definition_count is not None
            else "NOT_REACHED"
        ),
        "completed_sector_member_calls": client.completed_sector_member_reads,
    }


def _sector_membership_diagnostics(
    client: SinaSectorClient,
    symbol: str,
    existing: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "memberships": [
            {
                key: copy.deepcopy(record.get(key))
                for key in (
                    "sector_code",
                    "sector_name",
                    "sector_rank",
                    "sector_chg",
                    "display_name",
                )
            }
            for record in (existing, candidate)
        ],
        "duplicate_row_count": len(client.duplicate_sector_rows),
        "sector_definition_count_reached": (
            client.sector_definition_count
            if client.sector_definition_count is not None
            else "NOT_REACHED"
        ),
        "completed_sector_member_calls": client.completed_sector_member_reads,
    }


def _records(
    frame: Any,
    field_name: str,
    required_columns: Mapping[str, Sequence[str]],
    *,
    allow_empty: bool = False,
) -> list[dict[str, Any]]:
    if frame is None:
        _fail(INCOMPLETE_COVERAGE, f"{field_name} returned no frame")
    try:
        if bool(getattr(frame, "empty")):
            if allow_empty:
                return []
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
        if allow_empty:
            return []
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


def _hithink_bar_date(value: Any, field_name: str) -> str:
    value = _python_scalar(value)
    if _missing(value) or isinstance(value, bool):
        _fail(INCOMPLETE_COVERAGE, f"{field_name} is missing")
    try:
        timestamp_ms = int(value)
    except (TypeError, ValueError) as exc:
        _fail(PROVIDER_FAILURE, f"{field_name} is not a millisecond timestamp")
        raise AssertionError from exc
    if timestamp_ms <= 0:
        _fail(PROVIDER_FAILURE, f"{field_name} is not positive")
    try:
        return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).astimezone(_BJT).date().isoformat()
    except (OverflowError, OSError, ValueError) as exc:
        _fail(PROVIDER_FAILURE, f"{field_name} is outside the supported date range")
        raise AssertionError from exc


def _normalize_hithink_bars(raw_bars: Sequence[Any], thscode: str) -> list[dict[str, Any]]:
    bars: list[dict[str, Any]] = []
    seen_dates: set[str] = set()
    for index, raw_bar in enumerate(raw_bars):
        if not isinstance(raw_bar, Mapping):
            _fail(PROVIDER_FAILURE, f"HiThink historical bar {thscode}[{index}] is not a mapping")
        bar_date = _hithink_bar_date(raw_bar.get("date_ms"), f"{thscode}[{index}].date_ms")
        if bar_date in seen_dates:
            _fail(INPUT_CONFLICT, f"duplicate HiThink historical bar date for {thscode}: {bar_date}")
        seen_dates.add(bar_date)
        opening = _number(raw_bar.get("open_price"), f"{thscode}[{index}].open", positive=True)
        closing = _number(raw_bar.get("close_price"), f"{thscode}[{index}].close", positive=True)
        high = _number(raw_bar.get("high_price"), f"{thscode}[{index}].high", positive=True)
        low = _number(raw_bar.get("low_price"), f"{thscode}[{index}].low", positive=True)
        volume = _number(raw_bar.get("volume"), f"{thscode}[{index}].volume", non_negative=True)
        turnover = _number(raw_bar.get("turnover"), f"{thscode}[{index}].turnover", non_negative=True)
        if high < low or high < opening or high < closing or low > opening or low > closing:
            _fail(INPUT_CONFLICT, f"HiThink historical OHLC conflict for {thscode} on {bar_date}")
        bars.append(
            {
                "date": bar_date,
                "open": opening,
                "high": high,
                "low": low,
                "close": closing,
                "volume": volume,
                "turnover": turnover,
            }
        )
    bars.sort(key=lambda item: item["date"])
    return bars


class _HiThinkReadFailure(RuntimeError):
    """A transient HiThink read exhausted its bounded attempts."""

    def __init__(self, api_name: str, attempts: int, cause: Exception) -> None:
        self.api_name = api_name
        self.attempts = attempts
        self.cause = cause
        super().__init__(f"{api_name} failed after {attempts} attempts: {type(cause).__name__}")


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


class HiThinkClient:
    """Injectable client for the authenticated HiThink Financial-API path."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        request_get: Callable[..., Any] | None = None,
        max_attempts: int = HITHINK_MAX_ATTEMPTS,
    ) -> None:
        self.api_key = api_key or os.environ.get(HITHINK_API_KEY_ENV)
        if not isinstance(self.api_key, str) or not self.api_key.strip():
            _fail(PROVIDER_UNAVAILABLE, f"{HITHINK_API_KEY_ENV} is missing or empty")
        self.request_get = request_get or requests.get
        self.max_attempts = max_attempts
        self.read_attempts: list[dict[str, Any]] = []

    def capability_report(self) -> dict[str, Any]:
        return {
            "provider": "HiThink Financial-API",
            "base_url": HITHINK_BASE_URL,
            "api_version": HITHINK_API_VERSION,
            "authenticated": True,
            "live_primary_status": HITHINK_LIVE_PRIMARY,
            "apis": {
                "universe": HITHINK_UNIVERSE_API,
                "quotes": HITHINK_QUOTE_API,
                "stock_klines": HITHINK_STOCK_KLINE_API,
                "index_klines": HITHINK_INDEX_KLINE_API,
                "adjustment_events": HITHINK_ADJUSTMENT_API,
            },
        }

    @staticmethod
    def _is_transient_read_error(exc: Exception) -> bool:
        return isinstance(
            exc,
            (
                ConnectionError,
                TimeoutError,
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
            ),
        )

    def _read(
        self,
        api_name: str,
        path: str,
        params: Mapping[str, Any],
        *,
        timeout: float,
    ) -> Mapping[str, Any]:
        query = urllib.parse.urlencode(params)
        url = f"{HITHINK_BASE_URL}{path}?{query}" if query else f"{HITHINK_BASE_URL}{path}"
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.request_get(
                    url,
                    timeout=timeout,
                    headers={"X-api-key": self.api_key},
                )
                raise_for_status = getattr(response, "raise_for_status", None)
                if callable(raise_for_status):
                    raise_for_status()
                payload = response.json()
                if not isinstance(payload, Mapping):
                    raise ValueError("response JSON is not an object")
                if payload.get("code") != 0:
                    raise ValueError("response code is not zero")
                data = payload.get("data")
                if not isinstance(data, Mapping):
                    raise ValueError("response data is not an object")
            except Exception as exc:
                transient = self._is_transient_read_error(exc)
                if not transient or attempt == self.max_attempts:
                    self.read_attempts.append(
                        {"api": api_name, "attempts": attempt, "result": "FAILURE"}
                    )
                    if transient:
                        raise _HiThinkReadFailure(api_name, attempt, exc) from exc
                    raise
                time.sleep(min(HITHINK_RETRY_BACKOFF_SECONDS * attempt, 1.0))
            else:
                self.read_attempts.append(
                    {"api": api_name, "attempts": attempt, "result": "SUCCESS"}
                )
                return data
        raise AssertionError("unreachable HiThink retry loop")

    def universe(self, *, timeout: float = 15.0) -> list[dict[str, Any]]:
        limit = 10000
        offset = 0
        rows: list[dict[str, Any]] = []
        while True:
            data = self._read(
                HITHINK_UNIVERSE_API,
                HITHINK_UNIVERSE_API,
                {"exchange": "SH,SZ", "asset_type": "a-share", "limit": limit, "offset": offset},
                timeout=timeout,
            )
            page = data.get("item")
            if not isinstance(page, list):
                raise ValueError("HiThink universe item is not a list")
            rows.extend(item for item in page if isinstance(item, Mapping))
            if len(page) < limit:
                break
            offset += limit
        return rows

    def historical_bars(
        self,
        thscode: str,
        *,
        start: int,
        end: int,
        index: bool,
        timeout: float = 15.0,
    ) -> list[dict[str, Any]]:
        path = HITHINK_INDEX_KLINE_API if index else HITHINK_STOCK_KLINE_API
        params: dict[str, Any] = {
            "thscode": thscode,
            "interval": "1d",
            "start": start,
            "end": end,
        }
        if not index:
            params["adjust"] = "forward"
        data = self._read(path, path, params, timeout=timeout)
        returned_symbol = data.get("thscode")
        if returned_symbol is not None and str(returned_symbol).strip().upper() != thscode.upper():
            raise ValueError(f"HiThink historical response symbol mismatch for {thscode}")
        raw_bars = data.get("item")
        if not isinstance(raw_bars, list) or not raw_bars:
            raise ValueError(f"HiThink historical bars are empty for {thscode}")
        return _normalize_hithink_bars(raw_bars, thscode)


class SinaSectorClient:
    """Small wrapper around the exact legacy Sina-industry APIs only."""

    def __init__(self, module: ModuleType | Any | None = None, package_version: str | None = None) -> None:
        self.module, actual_version = _load_akshare(module)
        self.package_version = package_version or actual_version
        if not isinstance(self.package_version, str) or not self.package_version.strip():
            _fail(PROVIDER_UNAVAILABLE, "AkShare package version is empty")
        self.package_version = self.package_version.strip()
        self._apis = (AKSHARE_SINA_SPOT_API, AKSHARE_SINA_DETAIL_API)
        missing = [name for name in self._apis if not callable(getattr(self.module, name, None))]
        if missing:
            _fail(PROVIDER_UNAVAILABLE, f"AkShare API capability missing: {', '.join(missing)}")
        self.read_attempts: list[dict[str, Any]] = []
        self.sector_definition_count: int | None = None
        self.completed_sector_member_reads = 0
        self.current_sector_code: str | None = None
        self.current_sector_name: str | None = None
        self.display_name_mismatches: list[dict[str, Any]] = []
        self.duplicate_sector_rows: list[dict[str, Any]] = []
        self.sector_member_traversal: list[dict[str, Any]] = []
        self.resolved_sector_memberships: dict[str, dict[str, Any]] = {}
        self.multi_sector_symbols: set[str] = set()
        self.outside_universe_memberships: list[dict[str, Any]] = []
        self.missing_universe_symbols: list[str] = []

    def capability_report(self) -> dict[str, Any]:
        return {
            "package": "akshare",
            "version": self.package_version,
            "source_url": SINA_SOURCE_URL,
            "source_urls": {
                "spot": SINA_SPOT_SOURCE_URL,
                "detail_count": SINA_DETAIL_COUNT_SOURCE_URL,
                "detail": SINA_DETAIL_SOURCE_URL,
            },
            "taxonomy": SINA_TAXONOMY,
            "source_status": EXACT_SINA_SECTOR_SOURCE,
            "exact_legacy_taxonomy": True,
            "forbidden_substitutions": ["申万行业", "同花顺行业"],
            "apis": {name: True for name in self._apis},
        }

    @staticmethod
    def _is_transient_read_error(exc: Exception) -> bool:
        return isinstance(
            exc,
            (
                ConnectionError,
                TimeoutError,
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
            ),
        )

    def _read(self, api_name: str, reader: Callable[[], Any]) -> Any:
        for attempt in range(1, AKSHARE_MAX_ATTEMPTS + 1):
            try:
                value = reader()
            except Exception as exc:
                transient = self._is_transient_read_error(exc)
                if not transient or attempt == AKSHARE_MAX_ATTEMPTS:
                    self.read_attempts.append(
                        {"api": api_name, "attempts": attempt, "result": "FAILURE"}
                    )
                    if transient:
                        raise _AkShareReadFailure(api_name, attempt, exc) from exc
                    raise
                time.sleep(min(AKSHARE_RETRY_BACKOFF_SECONDS * attempt, 1.0))
            else:
                self.read_attempts.append(
                    {"api": api_name, "attempts": attempt, "result": "SUCCESS"}
                )
                return value
        raise AssertionError("unreachable AkShare retry loop")

    def sector_definitions(self) -> Any:
        return self._read(
            AKSHARE_SINA_SPOT_API,
            lambda: self.module.stock_sector_spot(indicator=SINA_TAXONOMY),
        )

    def sector_members(self, sector_code: str) -> Any:
        api_name = f"{AKSHARE_SINA_DETAIL_API}[{sector_code}]"
        result = self._read(
            api_name,
            lambda: self.module.stock_sector_detail(sector=sector_code),
        )
        self.completed_sector_member_reads += 1
        return result


def akshare_runtime_capability() -> dict[str, Any]:
    """Import-only exact-Sina capability probe; it never calls a data API."""

    return SinaSectorClient().capability_report()


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
        HITHINK_UNIVERSE_API,
        {
            "thscode": ("thscode",),
            "ticker": ("ticker",),
            "name": ("name",),
            "exchange": ("exchange",),
            "asset_type": ("asset_type",),
        },
    )
    names: dict[str, str] = {}
    for index, row in enumerate(rows):
        asset_type = _text(_field(row, ("asset_type",), f"universe[{index}].asset_type"), "universe asset_type")
        exchange = _text(_field(row, ("exchange",), f"universe[{index}].exchange"), "universe exchange").upper()
        if asset_type.lower() != "a-share":
            continue
        # BJ is intentionally outside the current tradable product scope;
        # its absence is not an incomplete SH/SZ coverage signal.
        if exchange == "BJ":
            continue
        if exchange not in {"SH", "SZ"}:
            continue
        symbol = _code(_field(row, ("ticker", "thscode"), f"universe[{index}].ticker"), f"universe[{index}].ticker")
        thscode = _text(_field(row, ("thscode",), f"universe[{index}].thscode"), "universe thscode").upper()
        if not thscode.endswith(f".{exchange}"):
            _fail(INPUT_CONFLICT, f"HiThink universe exchange/thscode conflict for {symbol}")
        if not symbol.startswith(("60", "68", "00", "30")):
            continue
        name = _display_name(
            _field(row, ("name",), f"universe[{index}].name"),
            f"universe[{index}].name",
        )
        if symbol in names:
            _fail(INPUT_CONFLICT, f"duplicate universe symbol: {symbol}")
        names[symbol] = name
    if not names:
        _fail(INCOMPLETE_COVERAGE, "universe has no symbols")
    return (
        UniverseManifest(
            as_of_date=as_of_date,
            retrieved_at_bjt=retrieved_at_bjt,
            source=f"HiThink Financial-API {HITHINK_UNIVERSE_API}",
            symbols=tuple(names),
            temporal_semantics=LIVE_OBSERVED,
            universe_scope=TRADABLE_UNIVERSE_SCOPE_V1,
            universe_scope_version=TRADABLE_UNIVERSE_SCOPE_VERSION,
        ),
        dict(sorted(names.items())),
    )


def _build_sector(
    client: SinaSectorClient,
    as_of_date: str,
    retrieved_at_bjt: str,
    names: Mapping[str, str],
) -> SectorManifest:
    definition_rows = _records(
        client.sector_definitions(),
        AKSHARE_SINA_SPOT_API,
        {
            "sector_code": ("label",),
            "sector_name": ("板块",),
            "sector_chg": ("涨跌幅",),
        },
    )
    raw_definitions: list[dict[str, Any]] = []
    for index, row in enumerate(definition_rows):
        for marker in ("taxonomy", "行业分类", "industry_taxonomy", "分类"):
            if marker in row and _text(row[marker], f"sector definition[{index}].{marker}") != SINA_TAXONOMY:
                _fail(INPUT_CONFLICT, f"sector definition taxonomy is not {SINA_TAXONOMY}")
        sector_code = _text(_field(row, ("label",), f"sector definition[{index}].label"), "sector label")
        sector_name = _text(_field(row, ("板块",), f"sector definition[{index}].name"), "sector name")
        change = _number(_field(row, ("涨跌幅",), f"sector definition[{index}].change"), "sector change")
        if any(item["sector_code"] == sector_code or item["sector_name"] == sector_name for item in raw_definitions):
            _fail(INPUT_CONFLICT, f"duplicate sector definition: {sector_code}/{sector_name}")
        raw_definitions.append({
            "sector_code": sector_code,
            "sector_name": sector_name,
            "sector_chg": change,
        })
    if not raw_definitions:
        _fail(INCOMPLETE_COVERAGE, "sector definitions are empty")
    ordered_definitions = sorted(raw_definitions, key=lambda item: (-item["sector_chg"], item["sector_code"]))
    definitions = {
        item["sector_code"]: {**item, "sector_rank": rank}
        for rank, item in enumerate(ordered_definitions, start=1)
    }
    client.sector_definition_count = len(definitions)

    members: dict[str, list[dict[str, Any]]] = {}
    by_symbol: dict[str, dict[str, Any]] = {}
    for raw_definition in raw_definitions:
        sector_code = raw_definition["sector_code"]
        definition = definitions[sector_code]
        client.current_sector_code = sector_code
        client.current_sector_name = definition["sector_name"]
        rows = _records(
            client.sector_members(sector_code),
            f"{AKSHARE_SINA_DETAIL_API}[{sector_code}]",
            {"code": ("代码", "code"), "name": ("名称", "name")},
            allow_empty=True,
        )
        sector_members: list[dict[str, Any]] = []
        for index, row in enumerate(rows):
            for marker in ("taxonomy", "行业分类", "industry_taxonomy", "分类"):
                if marker in row and _text(row[marker], f"{sector_code}[{index}].{marker}") != SINA_TAXONOMY:
                    _fail(INPUT_CONFLICT, f"sector member taxonomy is not {SINA_TAXONOMY}")
            symbol = _code(_field(row, ("代码", "code"), f"{sector_code}[{index}].code"), f"{sector_code}[{index}].code")
            member_name = _display_name(
                _field(row, ("名称", "name"), f"{sector_code}[{index}].name"),
                f"{sector_code}[{index}].name",
            )
            universe_name = names.get(symbol)
            record = {
                "symbol": symbol,
                "display_name": member_name,
                "display_name_normalized": normalize_display_name(member_name),
                "universe_display_name": universe_name,
                "universe_display_name_normalized": (
                    normalize_display_name(universe_name) if universe_name is not None else None
                ),
                "sector_code": sector_code,
                "sector_name": definition["sector_name"],
                "sector_rank": definition["sector_rank"],
                "sector_chg": definition["sector_chg"],
            }
            client.sector_member_traversal.append(copy.deepcopy(record))
            if symbol not in names:
                client.outside_universe_memberships.append(copy.deepcopy(record))
            if symbol in by_symbol:
                previous = by_symbol[symbol]
                semantic_fields = (
                    "symbol",
                    "display_name",
                    "sector_code",
                    "sector_name",
                    "sector_rank",
                    "sector_chg",
                )
                if all(previous[field] == record[field] for field in semantic_fields):
                    client.duplicate_sector_rows.append(
                        {
                            "symbol": symbol,
                            "sector_code": sector_code,
                            "row_index": index,
                            "classification": "EXACT_DUPLICATE_PROVIDER_ROW",
                            "raw_row": copy.deepcopy(row),
                        }
                    )
                else:
                    client.multi_sector_symbols.add(symbol)
            if (
                symbol in names
                and record["display_name_normalized"] != record["universe_display_name_normalized"]
            ):
                client.display_name_mismatches.append(
                    _display_name_mismatch_diagnostics(
                        client,
                        names,
                        symbol,
                        member_name,
                        sector_code=sector_code,
                        sector_label=definition["sector_name"],
                    )
                )
            by_symbol[symbol] = record
            client.resolved_sector_memberships[symbol] = copy.deepcopy(record)
            sector_members.append(record)
        members[sector_code] = sector_members

    client.missing_universe_symbols = sorted(set(names) - set(by_symbol))
    for symbol in client.missing_universe_symbols:
        client.resolved_sector_memberships[symbol] = {
            "symbol": symbol,
            "display_name": None,
            "display_name_normalized": None,
            "universe_display_name": names[symbol],
            "universe_display_name_normalized": normalize_display_name(names[symbol]),
            "sector_code": None,
            "sector_name": "-",
            "sector_rank": 50,
            "sector_chg": 0.0,
            "resolution": "V0_MISSING_DEFAULT",
        }
    rank_input = copy.deepcopy(client.sector_member_traversal)
    return SectorManifest(
        as_of_date=as_of_date,
        retrieved_at_bjt=retrieved_at_bjt,
        source=(
            f"AkShare.{AKSHARE_SINA_SPOT_API}(indicator={SINA_TAXONOMY})+"
            f"AkShare.{AKSHARE_SINA_DETAIL_API}(taxonomy={SINA_TAXONOMY})"
        ),
        definitions=definitions,
        members=members,
        rank_input=rank_input,
        temporal_semantics=LIVE_OBSERVED,
    )


def _utc_midnight_ms(value: str) -> int:
    return int(datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)


def _historical_window(as_of_date: str, count: int) -> tuple[int, int]:
    start_date = date.fromisoformat(as_of_date) - timedelta(days=max(count * 2 + 40, 120))
    return _utc_midnight_ms(start_date.isoformat()), _utc_midnight_ms(as_of_date)


def _hithink_failure_message(
    client: HiThinkClient | Any,
    exc: Exception,
    *,
    elapsed_seconds: float,
    universe_symbol_count: int,
    unexecuted_stage: str,
) -> str:
    latest = getattr(client, "read_attempts", [])[-1] if getattr(client, "read_attempts", []) else {}
    api_name = getattr(exc, "api_name", latest.get("api", "UNKNOWN"))
    attempts = getattr(exc, "attempts", latest.get("attempts", 1))
    cause = getattr(exc, "cause", exc)
    return (
        "HiThink Financial-API provider failure; "
        f"api={api_name}; attempts={attempts}; elapsed_acquisition_seconds={elapsed_seconds:.3f}; "
        f"universe_symbol_count={universe_symbol_count}; "
        f"unexecuted_stage={unexecuted_stage}; cause={type(cause).__name__}"
    )


def _akshare_failure_message(
    client: SinaSectorClient,
    exc: Exception,
    *,
    elapsed_seconds: float,
    universe_symbol_count: int,
    unexecuted_stage: str,
) -> str:
    latest = client.read_attempts[-1] if client.read_attempts else {}
    api_name = getattr(exc, "api_name", latest.get("api", "UNKNOWN"))
    attempts = getattr(exc, "attempts", latest.get("attempts", 1))
    cause = getattr(exc, "cause", exc)
    sector_code = client.current_sector_code or "N/A"
    sector_name = client.current_sector_name or "N/A"
    return (
        "AkShare provider failure; "
        f"api={api_name}; sector_code={sector_code}; sector_name={sector_name}; "
        f"attempts={attempts}; elapsed_acquisition_seconds={elapsed_seconds:.3f}; "
        f"completed_sector_calls={client.completed_sector_member_reads}; "
        f"sector_definition_count={client.sector_definition_count if client.sector_definition_count is not None else 'NOT_REACHED'}; "
        f"universe_symbol_count={universe_symbol_count}; "
        f"unexecuted_stage={unexecuted_stage}; cause={type(cause).__name__}"
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


def _is_hithink_transient(exc: Exception) -> bool:
    return isinstance(
        exc,
        (
            ConnectionError,
            TimeoutError,
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        ),
    )


def _resolve_market_bars(
    client: HiThinkClient | Any,
    symbol: str,
    *,
    count: int,
    as_of_date: str,
    timeout: float,
    request_get: Callable[..., Any],
    retries: int,
    index: bool,
    allow_tencent_fallback: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    start_ms, end_ms = _historical_window(as_of_date, count)
    thscode = HITHINK_INDEX_SYMBOL if index else _hithink_thscode(symbol)
    try:
        bars = client.historical_bars(
            thscode,
            start=start_ms,
            end=end_ms,
            index=index,
            timeout=timeout,
        )
        if not isinstance(bars, Sequence) or isinstance(bars, (str, bytes)):
            _fail(PROVIDER_FAILURE, f"HiThink historical bars are not a sequence for {thscode}")
        if len(bars) < count:
            _fail(INCOMPLETE_COVERAGE, f"HiThink historical coverage for {thscode} is {len(bars)} < {count}")
        normalized = list(bars)
        for bar_index, bar in enumerate(normalized):
            if not isinstance(bar, Mapping) or not isinstance(bar.get("date"), str):
                _fail(PROVIDER_FAILURE, f"HiThink historical bar {thscode}[{bar_index}] has no canonical date")
        future_dates = [bar["date"] for bar in normalized if bar["date"] > as_of_date]
        if future_dates:
            _fail(FUTURE_DATA_DETECTED, f"HiThink historical bar {thscode} is after {as_of_date}: {future_dates[0]}")
        if normalized[-1].get("date") != as_of_date:
            _fail(
                INPUT_DATE_MISMATCH,
                f"HiThink historical latest bar for {thscode} is {normalized[-1].get('date')} != {as_of_date}",
            )
        return normalized, {
            "provider": "HiThink Financial-API",
            "source": (
                f"{HITHINK_INDEX_KLINE_API}(unadjusted)"
                if index
                else f"{HITHINK_STOCK_KLINE_API}(adjust=forward)"
            ),
            "adjustment_mode": PROVIDER_RAW_SNAPSHOT if index else PROVIDER_QFQ_SNAPSHOT,
            "selection": "PRIMARY",
        }
    except LiveAcquisitionError:
        raise
    except Exception as exc:
        if not _is_hithink_transient(exc) and not isinstance(exc, _HiThinkReadFailure):
            _fail(PROVIDER_FAILURE, f"HiThink historical acquisition failed for {thscode}: {type(exc).__name__}")
        if not allow_tencent_fallback:
            _fail(PROVIDER_FAILURE, f"HiThink historical acquisition failed for {thscode}: fallback disabled")
        tencent_symbol = INDEX_SYMBOL if index else symbol
        fallback = _fetch_qfq_bars(
            tencent_symbol,
            count=count,
            as_of_date=as_of_date,
            timeout=timeout,
            retries=retries,
            request_get=request_get,
        )
        return fallback, {
            "provider": "Tencent",
            "source": TENCENT_KLINE_SOURCE,
            "adjustment_mode": PROVIDER_QFQ_SNAPSHOT,
            "selection": "EXPLICIT_FALLBACK",
        }


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
    diagnostics = manifest.provider_version_metadata.get("display_name_diagnostics")
    if not isinstance(diagnostics, Mapping):
        _fail(PROVIDER_FAILURE, "manifest display-name diagnostics are missing")
    mismatches = diagnostics.get("mismatches")
    mismatch_count = diagnostics.get("mismatch_count")
    if (
        not isinstance(mismatches, list)
        or isinstance(mismatch_count, bool)
        or not isinstance(mismatch_count, int)
        or mismatch_count != len(mismatches)
    ):
        _fail(PROVIDER_FAILURE, "manifest display-name diagnostics are invalid")
    sector_quality = manifest.provider_version_metadata.get("sector_membership_quality")
    if not isinstance(sector_quality, Mapping):
        _fail(PROVIDER_FAILURE, "manifest sector membership quality is missing")
    resolved_memberships = sector_quality.get("resolved_memberships")
    resolved_memberships_sha256 = sector_quality.get("resolved_memberships_sha256")
    if (
        not isinstance(resolved_memberships, Mapping)
        or any(not isinstance(key, str) for key in resolved_memberships)
        or not isinstance(resolved_memberships_sha256, str)
        or resolved_memberships_sha256
        != _sha256_json(dict(sorted(resolved_memberships.items())))
    ):
        _fail(PROVIDER_FAILURE, "manifest resolved sector membership identity is invalid")
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
        "universe_scope": {
            "name": manifest.universe.universe_scope,
            "version": manifest.universe.universe_scope_version,
        },
        "display_name_normalization": {
            "version": DISPLAY_NAME_NORMALIZATION_VERSION,
            "zero_width_codepoints": [
                f"U+{codepoint:04X}"
                for codepoint in DISPLAY_NAME_NORMALIZATION_ZERO_WIDTH_CODEPOINTS
            ],
            "rule": DISPLAY_NAME_NORMALIZATION_RULE,
        },
        "display_name_consistency_policy": _display_name_policy_metadata(),
        "display_name_diagnostics": {
            "mismatch_count": mismatch_count,
            "mismatches": copy.deepcopy(mismatches),
        },
        "sector_membership_resolution": {
            "policy": sector_quality.get("resolution_policy"),
            "resolved_memberships_sha256": resolved_memberships_sha256,
            "raw_membership_row_count": sector_quality.get("raw_membership_row_count"),
        },
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
        names = {
            str(key).strip().lower(): _display_name(value, f"display_names[{key}]")
            for key, value in self.display_names.items()
        }
        expected = set(self.generation_input_manifest.universe.symbols)
        if set(names) != expected:
            missing = sorted(expected - set(names))
            extra = sorted(set(names) - expected)
            _fail(MISSING_DISPLAY_NAME, f"display name coverage mismatch; missing={missing}, extra={extra}")
        object.__setattr__(self, "display_names", dict(sorted(names.items())))
        canonical_env = _copy_json(dict(self.market_env), "market_env")
        if canonical_env.get("as_of_date") != self.generation_input_manifest.signal_date:
            _fail(INPUT_DATE_MISMATCH, "market_env.as_of_date does not equal signal date")
        if canonical_env.get("adjustment_mode") not in {PROVIDER_QFQ_SNAPSHOT, PROVIDER_RAW_SNAPSHOT}:
            _fail(
                "UNSUPPORTED_MODE",
                "market_env must retain a supported provider snapshot adjustment mode",
            )
        object.__setattr__(self, "market_env", canonical_env)
        if not isinstance(self.provenance, Mapping):
            _fail(PROVIDER_FAILURE, "provenance must be a mapping")
        provenance = _copy_json(dict(self.provenance), "provenance")
        if provenance.get("contract") != PROSPECTIVE_PROVENANCE_CONTRACT:
            _fail(PROVIDER_FAILURE, "provenance contract is missing or unsupported")
        if provenance.get("display_name_consistency_policy") != _display_name_policy_metadata():
            _fail(INPUT_CONFLICT, "provenance display-name consistency policy is missing or unsupported")
        display_name_diagnostics = provenance.get("display_name_diagnostics")
        if not isinstance(display_name_diagnostics, Mapping):
            _fail(PROVIDER_FAILURE, "provenance display-name diagnostics are missing")
        mismatches = display_name_diagnostics.get("mismatches")
        mismatch_count = display_name_diagnostics.get("mismatch_count")
        if (
            not isinstance(mismatches, list)
            or isinstance(mismatch_count, bool)
            or not isinstance(mismatch_count, int)
            or mismatch_count != len(mismatches)
        ):
            _fail(PROVIDER_FAILURE, "provenance display-name diagnostics are invalid")
        sector_quality = provenance.get("sector_membership_quality")
        if not isinstance(sector_quality, Mapping):
            _fail(PROVIDER_FAILURE, "provenance sector membership quality is missing")
        duplicate_rows = sector_quality.get("duplicate_rows")
        duplicate_count = sector_quality.get("duplicate_row_count")
        if (
            not isinstance(duplicate_rows, list)
            or isinstance(duplicate_count, bool)
            or not isinstance(duplicate_count, int)
            or duplicate_count != len(duplicate_rows)
        ):
            _fail(PROVIDER_FAILURE, "provenance sector duplicate diagnostics are invalid")
        ambiguous_count = sector_quality.get("ambiguous_membership_count")
        if (
            isinstance(ambiguous_count, bool)
            or not isinstance(ambiguous_count, int)
            or ambiguous_count != 0
        ):
            _fail(INPUT_CONFLICT, "provenance contains unresolved sector memberships")
        multi_sector_symbols = sector_quality.get("multi_sector_symbols")
        multi_sector_count = sector_quality.get("multi_sector_symbol_count")
        if (
            not isinstance(multi_sector_symbols, list)
            or isinstance(multi_sector_count, bool)
            or not isinstance(multi_sector_count, int)
            or multi_sector_count != len(multi_sector_symbols)
            or multi_sector_symbols != sorted(set(multi_sector_symbols))
        ):
            _fail(PROVIDER_FAILURE, "provenance multi-sector diagnostics are invalid")
        if sector_quality.get("resolution_policy") != SECTOR_RESOLUTION_POLICY:
            _fail(PROVIDER_FAILURE, "provenance sector resolution policy is missing or unsupported")
        resolved_memberships = sector_quality.get("resolved_memberships")
        resolved_memberships_sha256 = sector_quality.get("resolved_memberships_sha256")
        if (
            not isinstance(resolved_memberships, Mapping)
            or any(not isinstance(key, str) for key in resolved_memberships)
            or not isinstance(resolved_memberships_sha256, str)
            or resolved_memberships_sha256
            != _sha256_json(dict(sorted(resolved_memberships.items())))
        ):
            _fail(PROVIDER_FAILURE, "provenance resolved sector membership identity is invalid")
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
        provenance_scope = provenance.get("universe_scope")
        expected_scope = {
            "name": self.generation_input_manifest.universe.universe_scope,
            "version": self.generation_input_manifest.universe.universe_scope_version,
        }
        if not isinstance(provenance_scope, Mapping) or any(
            provenance_scope.get(key) != value for key, value in expected_scope.items()
        ):
            _fail(INPUT_CONFLICT, "provenance universe scope does not match the generation manifest")
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
            "sector_membership_resolved_exact_v0",
            "display_name_coverage_and_symbol_identity",
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
        if identity_payload.get("display_name_consistency_policy") != _display_name_policy_metadata():
            _fail(INPUT_CONFLICT, "generation identity display-name policy is missing or unsupported")
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
    hithink_client: HiThinkClient | Any | None = None,
    hithink_request_get: Callable[..., Any] | None = None,
    sina_module: ModuleType | Any | None = None,
    allow_tencent_fallback: bool = ALLOW_TENCENT_KLINE_FALLBACK,
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

    hithink = hithink_client or HiThinkClient(request_get=hithink_request_get)
    if not all(callable(getattr(hithink, name, None)) for name in ("universe", "historical_bars", "capability_report")):
        _fail(PROVIDER_UNAVAILABLE, "HiThink client capability is incomplete")
    sina = SinaSectorClient(sina_module if sina_module is not None else akshare_module, akshare_version)
    acquisition_started = time.monotonic()
    retrieved_at_bjt = _timestamp_text(observed_at)
    try:
        universe_frame = hithink.universe(timeout=kline_timeout)
    except Exception as exc:
        _fail(
            PROVIDER_FAILURE,
            _hithink_failure_message(
                hithink,
                exc,
                elapsed_seconds=time.monotonic() - acquisition_started,
                universe_symbol_count=0,
                unexecuted_stage="exact Sina sector, Tencent quotes, stock/index Kline, market_env, manifest, persistence",
            ),
        )
    universe, display_names = _build_universe(universe_frame, target_date, retrieved_at_bjt)
    try:
        sector = _build_sector(sina, target_date, retrieved_at_bjt, display_names)
    except LiveAcquisitionError:
        raise
    except Exception as exc:
        _fail(
            PROVIDER_FAILURE,
            _akshare_failure_message(
                sina,
                exc,
                elapsed_seconds=time.monotonic() - acquisition_started,
                universe_symbol_count=len(universe.symbols),
                unexecuted_stage="Tencent quotes, stock/index Kline, market_env, manifest, persistence",
            ),
        )

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
    stock_resolutions: dict[str, dict[str, Any]] = {}
    for symbol in universe.symbols:
        bars, resolution = _resolve_market_bars(
            hithink,
            symbol,
            count=stock_bar_count,
            as_of_date=target_date,
            timeout=kline_timeout,
            retries=kline_retries,
            request_get=get,
            index=False,
            allow_tencent_fallback=allow_tencent_fallback,
        )
        stock_resolutions[symbol] = resolution
        stock_klines.append(
            KlineManifest(
                symbol=symbol,
                as_of_date=target_date,
                retrieved_at_bjt=retrieved_at_bjt,
                bars=bars,
                provider=resolution["provider"],
                adjustment_mode=resolution["adjustment_mode"],
                source=resolution["source"],
                temporal_semantics=LIVE_OBSERVED,
            )
        )
    index_bars, index_resolution = _resolve_market_bars(
        hithink,
        INDEX_SYMBOL,
        count=index_bar_count,
        as_of_date=target_date,
        timeout=kline_timeout,
        retries=kline_retries,
        request_get=get,
        index=True,
        allow_tencent_fallback=allow_tencent_fallback,
    )
    index = IndexManifest(
        symbol=INDEX_SYMBOL,
        as_of_date=target_date,
        retrieved_at_bjt=retrieved_at_bjt,
        bars=index_bars,
        provider=index_resolution["provider"],
        adjustment_mode=index_resolution["adjustment_mode"],
        source=index_resolution["source"],
        temporal_semantics=LIVE_OBSERVED,
    )
    market_env = _market_env(index)
    runtime_versions = _runtime_versions(sina.package_version)
    sector_quality = {
        "duplicate_row_count": len(sina.duplicate_sector_rows),
        "duplicate_rows": copy.deepcopy(sina.duplicate_sector_rows),
        "ambiguous_membership_count": 0,
        "multi_sector_symbol_count": len(sina.multi_sector_symbols),
        "multi_sector_symbols": sorted(sina.multi_sector_symbols),
        "resolution_policy": SECTOR_RESOLUTION_POLICY,
        "raw_membership_row_count": len(sina.sector_member_traversal),
        "resolved_memberships": dict(sorted(sina.resolved_sector_memberships.items())),
        "resolved_memberships_sha256": _sha256_json(
            dict(sorted(sina.resolved_sector_memberships.items()))
        ),
        "outside_universe_membership_count": len(sina.outside_universe_memberships),
        "missing_universe_symbol_count": len(sina.missing_universe_symbols),
        "missing_universe_symbols": copy.deepcopy(sina.missing_universe_symbols),
    }
    provider_metadata = {
        "runtime": runtime_versions,
        "display_name_consistency_policy": _display_name_policy_metadata(),
        "display_name_diagnostics": {
            "mismatch_count": len(sina.display_name_mismatches),
            "mismatches": copy.deepcopy(sina.display_name_mismatches),
        },
        "sector_membership_quality": copy.deepcopy(sector_quality),
        "market_data_failover": {
            "policy_version": MARKET_DATA_FAILOVER_POLICY_VERSION,
            "tencent_fallback_allowed": bool(allow_tencent_fallback),
            "tencent_fallback_version": TENCENT_FALLBACK_VERSION,
            "fallback_symbols": sorted(
                [symbol for symbol, resolution in stock_resolutions.items() if resolution["selection"] == "EXPLICIT_FALLBACK"]
                + ([INDEX_SYMBOL] if index_resolution["selection"] == "EXPLICIT_FALLBACK" else [])
            ),
        },
        "providers": {
            "universe": {
                "provider": "HiThink Financial-API",
                "api_version": HITHINK_API_VERSION,
                "base_url": HITHINK_BASE_URL,
                "api": HITHINK_UNIVERSE_API,
                "selection": "PRIMARY",
                "scope": _tradable_universe_scope_metadata(),
            },
            "sector": {
                "provider": "AkShare",
                "api_version": sina.package_version,
                "source_url": SINA_SOURCE_URL,
                "source_urls": {
                    "spot": SINA_SPOT_SOURCE_URL,
                    "detail_count": SINA_DETAIL_COUNT_SOURCE_URL,
                    "detail": SINA_DETAIL_SOURCE_URL,
                },
                "taxonomy": SINA_TAXONOMY,
                "exact_legacy_taxonomy": True,
                "spot_api": AKSHARE_SINA_SPOT_API,
                "detail_api": AKSHARE_SINA_DETAIL_API,
                "forbidden_substitutions": ["申万行业", "同花顺行业"],
            },
            "quotes": {"provider": "Tencent", "source": TENCENT_QUOTE_SOURCE},
            "stock_klines": {
                "provider": "HiThink Financial-API",
                "api_version": HITHINK_API_VERSION,
                "base_url": HITHINK_BASE_URL,
                "api": HITHINK_STOCK_KLINE_API,
                "adjust": "forward",
                "primary": "HiThink Financial-API",
                "fallback": "Tencent",
            },
            "index": {
                "provider": "HiThink Financial-API",
                "api_version": HITHINK_API_VERSION,
                "base_url": HITHINK_BASE_URL,
                "api": HITHINK_INDEX_KLINE_API,
                "adjustment_mode": PROVIDER_RAW_SNAPSHOT,
                "primary": "HiThink Financial-API",
                "fallback": "Tencent",
            },
        },
        "hithink_capability": hithink.capability_report(),
        "akshare_sina_capability": sina.capability_report(),
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
        "display_name_consistency_policy": _display_name_policy_metadata(),
        "display_name_normalization": {
            "version": DISPLAY_NAME_NORMALIZATION_VERSION,
            "zero_width_codepoints": [
                f"U+{codepoint:04X}"
                for codepoint in DISPLAY_NAME_NORMALIZATION_ZERO_WIDTH_CODEPOINTS
            ],
            "rule": DISPLAY_NAME_NORMALIZATION_RULE,
        },
        "display_name_diagnostics": {
            "mismatch_count": len(sina.display_name_mismatches),
            "mismatches": copy.deepcopy(sina.display_name_mismatches),
        },
        "sector_membership_quality": copy.deepcopy(sector_quality),
        "universe_scope": _tradable_universe_scope_metadata(),
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
            "sector_membership_resolved_exact_v0": "PASS",
            "display_name_coverage_and_symbol_identity": "PASS",
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
    "AKSHARE_MAX_ATTEMPTS",
    "AKSHARE_RETRY_BACKOFF_SECONDS",
    "AKSHARE_SINA_DETAIL_API",
    "AKSHARE_SINA_SPOT_API",
    "ALLOW_TENCENT_KLINE_FALLBACK",
    "DEFAULT_INDEX_BAR_COUNT",
    "DEFAULT_STOCK_BAR_COUNT",
    "DISPLAY_NAME_CONSISTENCY_POLICY",
    "DISPLAY_NAME_NORMALIZATION_VERSION",
    "DISPLAY_NAME_NORMALIZATION_ZERO_WIDTH_CODEPOINTS",
    "DISPLAY_NAME_NORMALIZATION_RULE",
    "EXACT_SINA_SECTOR_SOURCE",
    "GENERATION_IDENTITY_SCHEMA",
    "HITHINK_API_KEY_ENV",
    "HITHINK_API_VERSION",
    "HITHINK_BASE_URL",
    "HITHINK_INDEX_KLINE_API",
    "HITHINK_LIVE_PRIMARY",
    "HITHINK_MAX_ATTEMPTS",
    "HITHINK_STOCK_KLINE_API",
    "HITHINK_UNIVERSE_API",
    "HiThinkClient",
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
    "PROVIDER_RAW_SNAPSHOT",
    "SINA_TAXONOMY",
    "SINA_DETAIL_COUNT_SOURCE_URL",
    "SINA_DETAIL_SOURCE_URL",
    "SINA_SPOT_SOURCE_URL",
    "SinaSectorClient",
    "TENCENT_KLINE_SOURCE",
    "TRADABLE_UNIVERSE_SCOPE_V1",
    "TRADABLE_UNIVERSE_SCOPE_VERSION",
    "acquire_live_generation_inputs",
    "akshare_runtime_capability",
    "normalize_display_name",
    "persist_live_input_package",
]
