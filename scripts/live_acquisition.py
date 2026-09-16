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
import re
import tempfile
import time
import unicodedata
import urllib.parse
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

import requests

from b_breakout_retest_v1_1 import STRATEGY_SPEC_SHA256, STRATEGY_VERSION
from generation_contract import (
    AUTHORIZED_WEEKEND_BACKFILL,
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
    QuoteCaptureError,
    QuoteDataError,
    QuoteParseError,
    StaleQuoteError,
    fetch_quotes,
    is_no_trade_snapshot,
    to_symbol,
)
from trading_calendar import CalendarUnavailable, TradingCalendar, default_calendar
from universe_policy import (
    BOARD_UNKNOWN,
    UNIVERSE_POLICY_MAIN_BOARD_ONLY_V1,
    build_board_policy_audit,
    classify_board,
    is_live_universe_eligible,
    universe_policy_metadata,
    validate_board_policy_audit,
)
from watchlist_schema import (
    EXCLUDED_PROVIDER_STALE,
    INPUT_COVERAGE_COMPLETE,
    INPUT_COVERAGE_DEGRADED,
    INPUT_COVERAGE_SCHEMA,
    PER_SYMBOL_PROVIDER_FAILURE_ISOLATION_V1,
    TARGET_DAY_HISTORICAL_STALE,
    validate_input_coverage,
)


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
TARGET_DAY_HISTORICAL_STALE_LIMIT_EXCEEDED = "TARGET_DAY_HISTORICAL_STALE_LIMIT_EXCEEDED"

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
AKSHARE_SSE_LISTED_ROSTER_API = "stock_info_sh_name_code"
AKSHARE_SSE_MAIN_BOARD_SYMBOL = "主板A股"
AKSHARE_SSE_STAR_SYMBOL = "科创板"
AKSHARE_SZSE_LISTED_ROSTER_API = "stock_info_sz_name_code"
AKSHARE_SZSE_A_SHARE_SYMBOL = "A股列表"
SSE_OFFICIAL_LISTED_ROSTER_URL = "https://www.sse.com.cn/assortment/stock/list/share/"
SZSE_OFFICIAL_LISTED_ROSTER_URL = "https://www.szse.cn/market/product/stock/list/index.html"
EXCHANGE_OFFICIAL_LISTED_ROSTER_VERSION = "EXCHANGE_OFFICIAL_CURRENT_LISTED_ROSTER_V1"
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

# B's fixed evaluator reads the last 250 stock bars.  The retrieval target is
# deliberately buffered, while GenerationInputManifest accepts any non-empty
# stock history and B owns the separate 120-bar evaluation minimum.
DEFAULT_STOCK_BAR_COUNT = 260
# The shadow market-regime calculation needs the prior 60 closes plus the
# current close.  Keep this as an input sufficiency fix only; it does not
# change the formal B evaluator or the regime definition.
DEFAULT_INDEX_BAR_COUNT = 61
MIN_STOCK_BARS_FOR_GENERATION_INPUT = 1
MIN_INDEX_BARS_FOR_MARKET_ENV = 21

_BJT = timezone(timedelta(hours=8))

# Provider reads are not input semantics.  Keep the retry policy deliberately
# small and fixed: a transient read failure may be retried for the same read,
# but a malformed/empty/conflicting response is validated exactly once and is
# never hidden by another provider call.
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


CAPTURE_SCHEMA = "T_CLOSE_SOURCE_CAPTURE_V1"


@dataclass(frozen=True)
class CaptureRecord:
    """One immutable source capture and its machine-readable provenance."""

    path: Path
    metadata_path: Path
    payload: bytes
    metadata: Mapping[str, Any]


class TCloseEvidenceStore:
    """Small immutable store for source-level T-close evidence."""

    def __init__(
        self,
        root: str | Path,
        as_of_date: date | datetime | str,
        *,
        code_git_sha: str | None = None,
        actual_retrieved_at_bjt: datetime | str | None = None,
    ) -> None:
        self.root = Path(root)
        self.as_of_date = _canonical_date(as_of_date)
        self.code_git_sha = (
            code_git_sha or os.environ.get("ASHARE_CODE_GIT_SHA") or "UNKNOWN_ORIGIN"
        ).strip() or "UNKNOWN_ORIGIN"
        self.actual_retrieved_at_bjt = _timestamp_text(
            _canonical_timestamp(actual_retrieved_at_bjt or datetime.now(_BJT))
        )
        self._latest: dict[str, CaptureRecord] = {}
        self._records: dict[tuple[str, str], CaptureRecord] = {}

    @staticmethod
    def _json_ready(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                str(key): TCloseEvidenceStore._json_ready(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [TCloseEvidenceStore._json_ready(item) for item in value]
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        try:
            scalar = value.item() if callable(getattr(value, "item", None)) else value
        except Exception:
            scalar = value
        if scalar is not value:
            return TCloseEvidenceStore._json_ready(scalar)
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        raise TypeError(f"capture value is not JSON-compatible: {type(value).__name__}")

    @staticmethod
    def _component_path(root: Path, as_of_date: str, component: str, logical_identity: str) -> tuple[Path, Path]:
        digest = hashlib.sha256(logical_identity.encode("utf-8")).hexdigest()
        directory = root / as_of_date.replace("-", "") / component
        return directory / f"{digest}.raw", directory / f"{digest}.json"

    @staticmethod
    def _atomic_write(path: Path, payload: bytes) -> None:
        temporary: Path | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except OSError as exc:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
            _fail(PERSISTENCE_FAILURE, f"cannot atomically persist T-close evidence: {type(exc).__name__}")

    def capture_raw(
        self,
        component: str,
        logical_identity: str,
        payload: bytes,
        *,
        provider: str,
        source_identity: str,
        provider_version: str,
        request_identity: str | None = None,
        record_count: int | None = None,
        batch_count: int | None = None,
        effective_trading_date: str | None = None,
        completeness_status: str = "COMPLETE",
        content_type: str = "raw_bytes",
        encoding: str | None = None,
        metadata_extra: Mapping[str, Any] | None = None,
    ) -> CaptureRecord:
        if not isinstance(payload, bytes):
            _fail(PERSISTENCE_FAILURE, "T-close evidence payload must be bytes")
        raw_path, metadata_path = self._component_path(
            self.root, self.as_of_date, component, logical_identity
        )
        digest = _sha256_bytes(payload)
        if raw_path.exists() != metadata_path.exists():
            _fail(PERSISTENCE_CONFLICT, f"incomplete immutable T-close evidence pair for {logical_identity}")
        if raw_path.exists():
            try:
                existing = raw_path.read_bytes()
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                _fail(PERSISTENCE_FAILURE, f"cannot read existing T-close evidence: {type(exc).__name__}")
            if not isinstance(metadata, Mapping):
                _fail(PERSISTENCE_CONFLICT, f"T-close evidence metadata is not an object for {logical_identity}")
            if existing != payload or metadata.get("file_sha256") != digest:
                _fail(PERSISTENCE_CONFLICT, f"existing T-close evidence differs at logical identity {logical_identity}")
            record = CaptureRecord(raw_path, metadata_path, existing, metadata)
            self._latest[component] = record
            self._records[(component, logical_identity)] = record
            return record

        metadata: dict[str, Any] = {
            "schema_version": CAPTURE_SCHEMA,
            "target_date": self.as_of_date,
            "actual_retrieved_at_bjt": self.actual_retrieved_at_bjt,
            "provider": provider,
            "source_identity": source_identity,
            "provider_version": provider_version,
            "code_git_sha": self.code_git_sha,
            "logical_component_identity": logical_identity,
            "request_identity": request_identity or logical_identity,
            "byte_length": len(payload),
            "file_sha256": digest,
            "record_count": record_count,
            "batch_count": batch_count,
            "effective_trading_date": effective_trading_date,
            "completeness_status": completeness_status,
            "content_type": content_type,
        }
        if encoding is not None:
            metadata["encoding"] = encoding
        if metadata_extra:
            metadata.update(self._json_ready(dict(metadata_extra)))
        self._atomic_write(raw_path, payload)
        self._atomic_write(metadata_path, _canonical_json(metadata))
        record = CaptureRecord(raw_path, metadata_path, payload, metadata)
        self._latest[component] = record
        self._records[(component, logical_identity)] = record
        return record

    def capture_records(
        self,
        component: str,
        logical_identity: str,
        value: Any,
        *,
        provider: str,
        source_identity: str,
        provider_version: str,
        request_identity: str | None = None,
        effective_trading_date: str | None = None,
        metadata_extra: Mapping[str, Any] | None = None,
    ) -> CaptureRecord:
        if hasattr(value, "to_dict") and callable(getattr(value, "to_dict")):
            value = value.to_dict(orient="records")
        canonical = self._json_ready(value)
        record_count = len(canonical) if isinstance(canonical, list) else None
        return self.capture_raw(
            component,
            logical_identity,
            _canonical_json(canonical),
            provider=provider,
            source_identity=source_identity,
            provider_version=provider_version,
            request_identity=request_identity,
            record_count=record_count,
            effective_trading_date=effective_trading_date,
            content_type="canonical_adapter_records",
            encoding="utf-8",
            metadata_extra=metadata_extra,
        )

    def _load(self, component: str, logical_identity: str) -> CaptureRecord | None:
        raw_path, metadata_path = self._component_path(
            self.root, self.as_of_date, component, logical_identity
        )
        if not raw_path.exists() and not metadata_path.exists():
            return None
        if raw_path.exists() != metadata_path.exists():
            _fail(PERSISTENCE_CONFLICT, f"incomplete immutable T-close evidence pair for {logical_identity}")
        try:
            payload = raw_path.read_bytes()
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _fail(PERSISTENCE_FAILURE, f"cannot load T-close evidence: {type(exc).__name__}")
        if not isinstance(metadata, Mapping):
            _fail(PERSISTENCE_CONFLICT, f"T-close evidence metadata is not an object for {logical_identity}")
        if (
            metadata.get("schema_version") != CAPTURE_SCHEMA
            or metadata.get("target_date") != self.as_of_date
            or metadata.get("logical_component_identity") != logical_identity
            or metadata.get("byte_length") != len(payload)
            or metadata.get("file_sha256") != _sha256_bytes(payload)
        ):
            _fail(PERSISTENCE_CONFLICT, f"T-close evidence metadata/hash mismatch for {logical_identity}")
        record = CaptureRecord(raw_path, metadata_path, payload, metadata)
        self._latest[component] = record
        self._records[(component, logical_identity)] = record
        return record

    def load_raw(self, component: str, logical_identity: str) -> CaptureRecord | None:
        return self._load(component, logical_identity)

    def load_records(self, component: str, logical_identity: str) -> Any | None:
        record = self._load(component, logical_identity)
        if record is None:
            return None
        try:
            return json.loads(record.payload.decode(record.metadata.get("encoding", "utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            _fail(PERSISTENCE_CONFLICT, f"captured adapter records are not valid JSON: {type(exc).__name__}")

    def latest(self, component: str) -> CaptureRecord | None:
        return self._latest.get(component)

    def summary(self) -> list[dict[str, Any]]:
        """Return stable capture identities for package-level provenance."""

        return [
            {
                "component": component,
                "logical_component_identity": logical_identity,
                "file_sha256": record.metadata["file_sha256"],
                "byte_length": record.metadata["byte_length"],
                "content_type": record.metadata["content_type"],
                "completeness_status": record.metadata["completeness_status"],
                "provider": record.metadata["provider"],
                "source_identity": record.metadata["source_identity"],
                "provider_version": record.metadata["provider_version"],
                "code_git_sha": record.metadata["code_git_sha"],
                "request_identity": record.metadata["request_identity"],
                "effective_trading_date": record.metadata["effective_trading_date"],
            }
            for (component, logical_identity), record in sorted(self._records.items())
        ]

    def record_failure(
        self,
        component: str,
        *,
        provider: str,
        source_identity: str,
        provider_version: str,
        error_type: str,
        error_detail: str,
        request_identity: str | None = None,
        response_component: str | None = None,
    ) -> CaptureRecord:
        response = self.latest(response_component or component)
        response_sha = response.metadata.get("file_sha256") if response else None
        safe_detail = re.sub(
            r"(?i)(api[-_]?key|token|password|secret)=([^&\\s]+)",
            r"\1=<REDACTED>",
            str(error_detail),
        )[:1000]
        identity = (
            f"{request_identity or component}:failure:{error_type}:"
            f"{response_sha or 'NO_RESPONSE'}"
        )
        classification = (
            "PROVIDER_DATA_VALIDATION_FAILURE"
            if response
            else "PROVIDER_TRANSPORT_OR_NO_RESPONSE_FAILURE"
        )
        detail = {
            "provider": provider,
            "source_identity": source_identity,
            "request_identity": request_identity or component,
            "error_type": error_type,
            "error_detail": safe_detail,
            "response_sha256": response_sha,
            "error_classification": classification,
        }
        return self.capture_raw(
            component,
            identity,
            _canonical_json(detail),
            provider=provider,
            source_identity=source_identity,
            provider_version=provider_version,
            request_identity=request_identity or component,
            completeness_status="FAILED",
            content_type="failure_evidence",
            encoding="utf-8",
            metadata_extra={
                "error_type": error_type,
                "error_classification": classification,
                "response_sha256": response_sha,
            },
        )


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


def _response_bytes(response: Any) -> tuple[bytes, str]:
    content = getattr(response, "content", None)
    if isinstance(content, bytes):
        return content, "bytes"
    text = getattr(response, "text", None)
    if isinstance(text, str):
        return text.encode("utf-8"), "utf-8"
    _fail(PROVIDER_FAILURE, "provider response has neither bytes content nor text")


def _installed_version(package: str) -> str:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return "UNKNOWN_ORIGIN"


def _hithink_capture_identity(api_name: str, params: Mapping[str, Any]) -> str:
    query = urllib.parse.urlencode(sorted((str(key), str(value)) for key, value in params.items()))
    return f"{api_name}?{query}" if query else api_name


def _hithink_response_capture_identity(
    store: TCloseEvidenceStore,
    logical_identity: str,
    payload: bytes,
) -> str:
    """Preserve a changed retry response without overwriting prior evidence."""

    existing = store.load_raw("hithink_response", logical_identity)
    if existing is None or existing.payload == payload:
        return logical_identity
    return f"{logical_identity}:response_sha256={_sha256_bytes(payload)}"


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
        capture_store: TCloseEvidenceStore | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get(HITHINK_API_KEY_ENV)
        if not isinstance(self.api_key, str) or not self.api_key.strip():
            _fail(PROVIDER_UNAVAILABLE, f"{HITHINK_API_KEY_ENV} is missing or empty")
        self.request_get = request_get or requests.get
        self.max_attempts = max_attempts
        self.capture_store = capture_store
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
        return _is_hithink_transient(exc)

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
        logical_identity = _hithink_capture_identity(api_name, params)
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.request_get(
                    url,
                    timeout=timeout,
                    headers={"X-api-key": self.api_key},
                )
                if self.capture_store is not None:
                    payload, encoding = _response_bytes(response)
                    response_identity = _hithink_response_capture_identity(
                        self.capture_store,
                        logical_identity,
                        payload,
                    )
                    self.capture_store.capture_raw(
                        "hithink_response",
                        response_identity,
                        payload,
                        provider="HiThink Financial-API",
                        source_identity=path,
                        provider_version=HITHINK_API_VERSION,
                        request_identity=url.split("?", 1)[-1] if "?" in url else path,
                        encoding=encoding,
                        content_type="provider_response",
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
        logical_identity = "hithink_universe"
        if self.capture_store is not None:
            cached = self.capture_store.load_records("hithink_universe", logical_identity)
            if cached is not None:
                return cached
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
        if self.capture_store is not None:
            self.capture_store.capture_records(
                "hithink_universe",
                logical_identity,
                rows,
                provider="HiThink Financial-API",
                source_identity=HITHINK_UNIVERSE_API,
                provider_version=HITHINK_API_VERSION,
                request_identity=HITHINK_UNIVERSE_API,
                effective_trading_date=self.capture_store.as_of_date,
            )
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
        logical_identity = _hithink_capture_identity(path, params)
        if self.capture_store is not None:
            cached = self.capture_store.load_records("hithink_kline", logical_identity)
            if cached is not None:
                return cached
        data = self._read(path, path, params, timeout=timeout)
        returned_symbol = data.get("thscode")
        if returned_symbol is not None and str(returned_symbol).strip().upper() != thscode.upper():
            raise ValueError(f"HiThink historical response symbol mismatch for {thscode}")
        raw_bars = data.get("item")
        if not isinstance(raw_bars, list) or not raw_bars:
            raise ValueError(f"HiThink historical bars are empty for {thscode}")
        normalized = _normalize_hithink_bars(raw_bars, thscode)
        if self.capture_store is not None:
            self.capture_store.capture_records(
                "hithink_kline",
                logical_identity,
                normalized,
                provider="HiThink Financial-API",
                source_identity=path,
                provider_version=HITHINK_API_VERSION,
                request_identity=logical_identity,
                effective_trading_date=self.capture_store.as_of_date,
                metadata_extra={
                    "adjustment_mode": PROVIDER_RAW_SNAPSHOT if index else PROVIDER_QFQ_SNAPSHOT,
                    "selection": "PRIMARY",
                },
            )
        return normalized


class SinaSectorClient:
    """Small wrapper around the exact legacy Sina-industry APIs only."""

    def __init__(
        self,
        module: ModuleType | Any | None = None,
        package_version: str | None = None,
        capture_store: TCloseEvidenceStore | None = None,
    ) -> None:
        self.module, actual_version = _load_akshare(module)
        self.package_version = package_version or actual_version
        if not isinstance(self.package_version, str) or not self.package_version.strip():
            _fail(PROVIDER_UNAVAILABLE, "AkShare package version is empty")
        self.package_version = self.package_version.strip()
        self.capture_store = capture_store
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
        return _read_akshare(
            api_name,
            reader,
            read_attempts=self.read_attempts,
            is_transient=self._is_transient_read_error,
        )

    def sector_definitions(self) -> Any:
        logical_identity = f"{AKSHARE_SINA_SPOT_API}:indicator={SINA_TAXONOMY}"
        if self.capture_store is not None:
            cached = self.capture_store.load_records("sina_sector_spot", logical_identity)
            if cached is not None:
                return cached
        result = self._read(
            AKSHARE_SINA_SPOT_API,
            lambda: self.module.stock_sector_spot(indicator=SINA_TAXONOMY),
        )
        if self.capture_store is not None:
            self.capture_store.capture_records(
                "sina_sector_spot",
                logical_identity,
                result,
                provider="AkShare",
                source_identity=SINA_SPOT_SOURCE_URL,
                provider_version=self.package_version,
                request_identity=logical_identity,
                effective_trading_date=self.capture_store.as_of_date,
            )
        return result

    def sector_members(self, sector_code: str) -> Any:
        api_name = f"{AKSHARE_SINA_DETAIL_API}[{sector_code}]"
        logical_identity = f"{AKSHARE_SINA_DETAIL_API}:sector={sector_code}"
        if self.capture_store is not None:
            cached = self.capture_store.load_records("sina_sector_membership", logical_identity)
            if cached is not None:
                self.completed_sector_member_reads += 1
                return cached
        result = self._read(
            api_name,
            lambda: self.module.stock_sector_detail(sector=sector_code),
        )
        if self.capture_store is not None:
            self.capture_store.capture_records(
                "sina_sector_membership",
                logical_identity,
                result,
                provider="AkShare",
                source_identity=SINA_DETAIL_SOURCE_URL,
                provider_version=self.package_version,
                request_identity=logical_identity,
                effective_trading_date=self.capture_store.as_of_date,
            )
        self.completed_sector_member_reads += 1
        return result


def _read_akshare(
    api_name: str,
    reader: Callable[[], Any],
    *,
    read_attempts: list[dict[str, Any]],
    is_transient: Callable[[Exception], bool],
) -> Any:
    for attempt in range(1, AKSHARE_MAX_ATTEMPTS + 1):
        try:
            value = reader()
        except Exception as exc:
            transient = is_transient(exc)
            if not transient or attempt == AKSHARE_MAX_ATTEMPTS:
                read_attempts.append({"api": api_name, "attempts": attempt, "result": "FAILURE"})
                if transient:
                    raise _AkShareReadFailure(api_name, attempt, exc) from exc
                raise
            time.sleep(min(AKSHARE_RETRY_BACKOFF_SECONDS * attempt, 1.0))
        else:
            read_attempts.append({"api": api_name, "attempts": attempt, "result": "SUCCESS"})
            return value
    raise AssertionError("unreachable AkShare retry loop")


class ExchangeListedRosterClient:
    """AkShare wrapper for the two official exchange listed-stock rosters."""

    def __init__(
        self,
        module: ModuleType | Any | None = None,
        package_version: str | None = None,
        capture_store: TCloseEvidenceStore | None = None,
    ) -> None:
        self.module, actual_version = _load_akshare(module)
        self.package_version = package_version or actual_version
        if not isinstance(self.package_version, str) or not self.package_version.strip():
            _fail(PROVIDER_UNAVAILABLE, "AkShare package version is empty")
        self.package_version = self.package_version.strip()
        self.capture_store = capture_store
        self.read_attempts: list[dict[str, Any]] = []
        missing = [
            name
            for name in (AKSHARE_SSE_LISTED_ROSTER_API, AKSHARE_SZSE_LISTED_ROSTER_API)
            if not callable(getattr(self.module, name, None))
        ]
        if missing:
            _fail(PROVIDER_UNAVAILABLE, f"AkShare API capability missing: {', '.join(missing)}")

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
        return _read_akshare(
            api_name,
            reader,
            read_attempts=self.read_attempts,
            is_transient=self._is_transient_read_error,
        )

    def sse_main_board(self) -> Any:
        return self._roster_frame(
            "sse_main_board",
            f"{AKSHARE_SSE_LISTED_ROSTER_API}(symbol={AKSHARE_SSE_MAIN_BOARD_SYMBOL})",
            lambda: self.module.stock_info_sh_name_code(symbol=AKSHARE_SSE_MAIN_BOARD_SYMBOL),
        )

    def sse_star(self) -> Any:
        return self._roster_frame(
            "sse_star",
            f"{AKSHARE_SSE_LISTED_ROSTER_API}(symbol={AKSHARE_SSE_STAR_SYMBOL})",
            lambda: self.module.stock_info_sh_name_code(symbol=AKSHARE_SSE_STAR_SYMBOL),
        )

    def szse_a_share(self) -> Any:
        return self._roster_frame(
            "szse_a_share",
            f"{AKSHARE_SZSE_LISTED_ROSTER_API}(symbol={AKSHARE_SZSE_A_SHARE_SYMBOL})",
            lambda: self.module.stock_info_sz_name_code(symbol=AKSHARE_SZSE_A_SHARE_SYMBOL),
        )

    def _roster_frame(self, logical_identity: str, api_name: str, reader: Callable[[], Any]) -> Any:
        if self.capture_store is not None:
            cached = self.capture_store.load_records("official_listed_roster", logical_identity)
            if cached is not None:
                return cached
        result = self._read(api_name, reader)
        if self.capture_store is not None:
            self.capture_store.capture_records(
                "official_listed_roster",
                logical_identity,
                result,
                provider="AkShare",
                source_identity=(
                    SSE_OFFICIAL_LISTED_ROSTER_URL
                    if logical_identity.startswith("sse_")
                    else SZSE_OFFICIAL_LISTED_ROSTER_URL
                ),
                provider_version=self.package_version,
                request_identity=api_name,
                effective_trading_date=self.capture_store.as_of_date,
            )
        return result

    def capability_report(self) -> dict[str, Any]:
        return {
            "provider": "AkShare",
            "package": "akshare",
            "version": self.package_version,
            "identity": EXCHANGE_OFFICIAL_LISTED_ROSTER_VERSION,
            "sources": {
                "sse": {
                    "url": SSE_OFFICIAL_LISTED_ROSTER_URL,
                    "api": AKSHARE_SSE_LISTED_ROSTER_API,
                    "symbols": [AKSHARE_SSE_MAIN_BOARD_SYMBOL, AKSHARE_SSE_STAR_SYMBOL],
                },
                "szse": {
                    "url": SZSE_OFFICIAL_LISTED_ROSTER_URL,
                    "api": AKSHARE_SZSE_LISTED_ROSTER_API,
                    "symbol": AKSHARE_SZSE_A_SHARE_SYMBOL,
                },
            },
        }


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


def _validate_close_window(
    as_of_date: str,
    now_bjt: datetime,
    calendar: TradingCalendar,
    *,
    allow_weekend_backfill: bool = False,
) -> datetime:
    if not isinstance(allow_weekend_backfill, bool):
        _fail(INPUT_DATE_MISMATCH, "allow_weekend_backfill must be a boolean")
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
    observed_date = now_bjt.date()
    target_date = date.fromisoformat(as_of_date)
    if observed_date == target_date:
        if now_bjt < session_close:
            _fail(
                SESSION_NOT_CLOSED,
                f"now_bjt {now_bjt.isoformat()} is before session close {session_close.isoformat()}",
            )
        return session_close
    if not allow_weekend_backfill:
        _fail(INPUT_DATE_MISMATCH, f"observation date {observed_date.isoformat()} != as_of_date {as_of_date}")
    if observed_date < target_date:
        _fail(INPUT_DATE_MISMATCH, f"observation date {observed_date.isoformat()} precedes as_of_date {as_of_date}")
    try:
        if calendar.is_trading_day(observed_date):
            _fail(
                INPUT_DATE_MISMATCH,
                f"weekend backfill acquisition date {observed_date.isoformat()} is an XSHG trading session",
            )
        current = target_date + timedelta(days=1)
        while current < observed_date:
            if calendar.is_trading_day(current):
                _fail(
                    INPUT_DATE_MISMATCH,
                    "weekend backfill crosses an intervening XSHG trading session "
                    f"{current.isoformat()}",
                )
            current += timedelta(days=1)
    except LiveAcquisitionError:
        raise
    except CalendarUnavailable as exc:
        _fail("CALENDAR_ERROR", str(exc))
    except Exception as exc:
        _fail("CALENDAR_ERROR", f"XSHG calendar failed: {type(exc).__name__}")
    if now_bjt < session_close:
        _fail(SESSION_NOT_CLOSED, f"now_bjt {now_bjt.isoformat()} is before session close {session_close.isoformat()}")
    return session_close


def _build_official_listed_roster(
    client: ExchangeListedRosterClient,
    as_of_date: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    source_specs = (
        (
            "sse_main_board",
            client.sse_main_board,
            AKSHARE_SSE_LISTED_ROSTER_API,
            ("证券代码",),
            ("上市日期",),
            ("60",),
        ),
        (
            "sse_star",
            client.sse_star,
            AKSHARE_SSE_LISTED_ROSTER_API,
            ("证券代码",),
            ("上市日期",),
            ("68",),
        ),
        (
            "szse_a_share",
            client.szse_a_share,
            AKSHARE_SZSE_LISTED_ROSTER_API,
            ("A股代码",),
            ("A股上市日期",),
            ("00", "30"),
        ),
    )
    all_rows: list[dict[str, Any]] = []
    source_row_counts: dict[str, int] = {}
    seen: dict[str, dict[str, Any]] = {}
    pre_listing: list[dict[str, Any]] = []
    for source_name, reader, api_name, code_aliases, listing_aliases, code_prefixes in source_specs:
        rows = _records(
            reader(),
            api_name,
            {"symbol": code_aliases, "listing_date": listing_aliases},
        )
        source_row_counts[source_name] = len(rows)
        for index, row in enumerate(rows):
            symbol = _code(
                _field(row, code_aliases, f"{source_name}[{index}].symbol"),
                f"{source_name}[{index}].symbol",
            )
            if not symbol.startswith(code_prefixes):
                _fail(INPUT_CONFLICT, f"{source_name}[{index}] has an unexpected exchange code: {symbol}")
            listing_value = _field(
                row,
                listing_aliases,
                f"{source_name}[{index}].listing_date",
            )
            try:
                listing_date = _canonical_date(listing_value)
            except (TypeError, ValueError, OverflowError) as exc:
                _fail(
                    PROVIDER_FAILURE,
                    f"{source_name}[{index}].listing_date is not a canonical date: {exc}",
                )
            record = {
                "source": source_name,
                "symbol": symbol,
                "listing_date": listing_date,
            }
            if symbol in seen:
                _fail(
                    INPUT_CONFLICT,
                    f"duplicate official listed-roster symbol {symbol}: "
                    f"{seen[symbol]['source']} and {source_name}",
                )
            seen[symbol] = record
            all_rows.append(record)
            if listing_date > as_of_date:
                pre_listing.append(copy.deepcopy(record))

    if not all_rows:
        _fail(INCOMPLETE_COVERAGE, "official exchange listed roster is empty")
    eligible = {
        symbol: copy.deepcopy(record)
        for symbol, record in seen.items()
        if record["listing_date"] <= as_of_date
    }
    if not eligible:
        _fail(INCOMPLETE_COVERAGE, f"official exchange roster has no symbols listed by {as_of_date}")
    canonical_rows = sorted(all_rows, key=lambda item: item["symbol"])
    semantic_rows = [
        {"symbol": item["symbol"], "listing_date": item["listing_date"]}
        for item in canonical_rows
    ]
    audit = {
        "identity": EXCHANGE_OFFICIAL_LISTED_ROSTER_VERSION,
        "as_of_date": as_of_date,
        "listing_date_rule": "listing_date <= as_of_date",
        "source_row_counts": source_row_counts,
        "canonical_combined_symbol_count": len(canonical_rows),
        "official_listed_count": len(eligible),
        "pre_listing_count": len(pre_listing),
        "pre_listing_symbols": sorted(item["symbol"] for item in pre_listing),
        "content_sha256": _sha256_json({"as_of_date": as_of_date, "rows": canonical_rows}),
        "semantic_sha256": _sha256_json({"as_of_date": as_of_date, "rows": semantic_rows}),
    }
    return dict(sorted(eligible.items())), audit


def _build_universe(
    frame: Any,
    as_of_date: str,
    retrieved_at_bjt: str,
    official_roster: Mapping[str, Mapping[str, Any]],
    roster_audit: Mapping[str, Any],
) -> tuple[UniverseManifest, dict[str, str], dict[str, Any]]:
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
        if classify_board(symbol) == BOARD_UNKNOWN:
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
    hithink_symbols = set(names)
    official_symbols = set(official_roster)
    scope_symbols = hithink_symbols & official_symbols
    board_policy_audit = build_board_policy_audit(scope_symbols)
    retained_names = {
        symbol: name
        for symbol, name in names.items()
        if symbol in official_symbols and is_live_universe_eligible(symbol)
    }
    universe_quality = copy.deepcopy(dict(roster_audit))
    universe_quality.update(
        {
            "hithink_broad_count": len(names),
            "hithink_broad_symbols": sorted(hithink_symbols),
            "hithink_only_count": len(hithink_symbols - official_symbols),
            "hithink_only_symbols": sorted(hithink_symbols - official_symbols),
            "roster_only_count": len(official_symbols - hithink_symbols),
            "roster_only_symbols": sorted(official_symbols - hithink_symbols),
            "universe_policy": universe_policy_metadata(),
            "board_policy_audit": board_policy_audit,
            "retained_count": len(retained_names),
        }
    )
    if not retained_names:
        _fail(INCOMPLETE_COVERAGE, "HiThink universe and official roster have no Main Board symbols")
    return (
        UniverseManifest(
            as_of_date=as_of_date,
            retrieved_at_bjt=retrieved_at_bjt,
            source=(
                f"HiThink Financial-API {HITHINK_UNIVERSE_API} ∩ "
                f"{EXCHANGE_OFFICIAL_LISTED_ROSTER_VERSION}"
            ),
            symbols=tuple(retained_names),
            temporal_semantics=LIVE_OBSERVED,
            universe_scope=TRADABLE_UNIVERSE_SCOPE_V1,
            universe_scope_version=TRADABLE_UNIVERSE_SCOPE_VERSION,
        ),
        dict(sorted(retained_names.items())),
        universe_quality,
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


def _historical_window(as_of_date: str, requested_count: int) -> tuple[int, int]:
    start_date = date.fromisoformat(as_of_date) - timedelta(days=max(requested_count * 2 + 40, 120))
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
    client: SinaSectorClient | ExchangeListedRosterClient,
    exc: Exception,
    *,
    elapsed_seconds: float,
    universe_symbol_count: int,
    unexecuted_stage: str,
) -> str:
    read_attempts = getattr(client, "read_attempts", [])
    latest = read_attempts[-1] if read_attempts else {}
    api_name = getattr(exc, "api_name", latest.get("api", "UNKNOWN"))
    attempts = getattr(exc, "attempts", latest.get("attempts", 1))
    cause = getattr(exc, "cause", exc)
    sector_code = getattr(client, "current_sector_code", None) or "N/A"
    sector_name = getattr(client, "current_sector_name", None) or "N/A"
    return (
        "AkShare provider failure; "
        f"api={api_name}; sector_code={sector_code}; sector_name={sector_name}; "
        f"attempts={attempts}; elapsed_acquisition_seconds={elapsed_seconds:.3f}; "
        f"completed_sector_calls={getattr(client, 'completed_sector_member_reads', 'NOT_APPLICABLE')}; "
        f"sector_definition_count={getattr(client, 'sector_definition_count', 'NOT_APPLICABLE') if getattr(client, 'sector_definition_count', None) is not None else 'NOT_REACHED'}; "
        f"universe_symbol_count={universe_symbol_count}; "
        f"unexecuted_stage={unexecuted_stage}; cause={type(cause).__name__}"
    )


def _request_json(
    url: str,
    *,
    timeout: float,
    retries: int,
    request_get: Callable[..., Any],
    raw_response_callback: Callable[[Any], None] | None = None,
) -> Mapping[str, Any]:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = request_get(url, timeout=timeout)
            if raw_response_callback is not None:
                raw_response_callback(response)
            raise_for_status = getattr(response, "raise_for_status", None)
            if callable(raise_for_status):
                raise_for_status()
            payload = response.json()
            if not isinstance(payload, Mapping):
                raise ValueError("response JSON is not an object")
            return payload
        except LiveAcquisitionError:
            raise
        except Exception as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(attempt + 1)
    _fail(PROVIDER_FAILURE, f"Tencent Kline request failed after {retries} attempts: {type(last_error).__name__}")
    raise AssertionError


def _fetch_qfq_bars(
    symbol: str,
    *,
    requested_count: int,
    minimum_acceptable_history: int,
    as_of_date: str,
    require_last_bar_date: bool = True,
    timeout: float,
    retries: int,
    request_get: Callable[..., Any],
    raw_response_callback: Callable[[Any], None] | None = None,
) -> list[dict[str, Any]]:
    provider_symbol = to_symbol(symbol)
    url = f"https://{TENCENT_KLINE_SOURCE}?param={provider_symbol},day,,,{requested_count},qfq"
    payload = _request_json(
        url,
        timeout=timeout,
        retries=retries,
        request_get=request_get,
        raw_response_callback=raw_response_callback,
    )
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
    if len(bars) < minimum_acceptable_history:
        _fail(
            INCOMPLETE_COVERAGE,
            f"Tencent qfq coverage for {provider_symbol} is {len(bars)} < "
            f"{minimum_acceptable_history}",
        )
    if require_last_bar_date and bars[-1]["date"] != as_of_date:
        _fail(
            INPUT_DATE_MISMATCH,
            f"Tencent qfq latest bar for {provider_symbol} is {bars[-1]['date']} != {as_of_date}",
            {
                "classification": TARGET_DAY_HISTORICAL_STALE,
                "target_date": as_of_date,
                "latest_historical_date": bars[-1]["date"],
                "historical_bar_count": len(bars),
                "historical_quality": {
                    "non_empty": True,
                    "structure_valid": True,
                    "future_data": False,
                },
                "provider": "Tencent",
                "source": TENCENT_KLINE_SOURCE,
                "provider_symbol": provider_symbol,
            },
        )
    return bars


def _is_hithink_transient(exc: Exception) -> bool:
    if isinstance(
        exc,
        (
            ConnectionError,
            TimeoutError,
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        ),
    ):
        return True
    if not isinstance(exc, requests.exceptions.HTTPError):
        return False
    status_code = getattr(getattr(exc, "response", None), "status_code", None)
    return status_code in {408, 429} or isinstance(status_code, int) and 500 <= status_code <= 599


def _validate_historical_bars(
    bars: Any,
    thscode: str,
    *,
    minimum_acceptable_history: int,
    as_of_date: str,
    require_last_bar_date: bool,
    provider: str = "HiThink Financial-API",
) -> list[dict[str, Any]]:
    if not isinstance(bars, Sequence) or isinstance(bars, (str, bytes)):
        _fail(PROVIDER_FAILURE, f"HiThink historical bars are not a sequence for {thscode}")
    if len(bars) < minimum_acceptable_history:
        _fail(
            INCOMPLETE_COVERAGE,
            f"HiThink historical coverage for {thscode} is {len(bars)} < "
            f"{minimum_acceptable_history}",
        )
    normalized = list(bars)
    seen_dates: set[str] = set()
    for bar_index, bar in enumerate(normalized):
        if not isinstance(bar, Mapping) or not isinstance(bar.get("date"), str):
            _fail(PROVIDER_FAILURE, f"HiThink historical bar {thscode}[{bar_index}] has no canonical date")
        try:
            canonical_bar_date = _canonical_date(bar["date"])
        except (TypeError, ValueError, OverflowError) as exc:
            _fail(
                PROVIDER_FAILURE,
                f"HiThink historical bar {thscode}[{bar_index}] has no canonical date",
            )
            raise AssertionError from exc
        if bar["date"] != canonical_bar_date:
            _fail(
                PROVIDER_FAILURE,
                f"HiThink historical bar {thscode}[{bar_index}] date is not canonical: {bar['date']}",
            )
        if canonical_bar_date in seen_dates:
            _fail(INPUT_CONFLICT, f"duplicate HiThink historical bar date for {thscode}: {canonical_bar_date}")
        seen_dates.add(canonical_bar_date)
        opening = _number(bar.get("open"), f"{thscode}[{bar_index}].open", positive=True)
        high = _number(bar.get("high"), f"{thscode}[{bar_index}].high", positive=True)
        low = _number(bar.get("low"), f"{thscode}[{bar_index}].low", positive=True)
        closing = _number(bar.get("close"), f"{thscode}[{bar_index}].close", positive=True)
        _number(bar.get("volume"), f"{thscode}[{bar_index}].volume", non_negative=True)
        if high < low or high < opening or high < closing or low > opening or low > closing:
            _fail(INPUT_CONFLICT, f"HiThink historical OHLC conflict for {thscode} on {canonical_bar_date}")
    normalized.sort(key=lambda item: item["date"])
    future_dates = [bar["date"] for bar in normalized if bar["date"] > as_of_date]
    if future_dates:
        _fail(FUTURE_DATA_DETECTED, f"HiThink historical bar {thscode} is after {as_of_date}: {future_dates[0]}")
    if require_last_bar_date and normalized[-1].get("date") != as_of_date:
        _fail(
            INPUT_DATE_MISMATCH,
            f"HiThink historical latest bar for {thscode} is {normalized[-1].get('date')} != {as_of_date}",
            {
                "classification": TARGET_DAY_HISTORICAL_STALE,
                "target_date": as_of_date,
                "latest_historical_date": normalized[-1].get("date"),
                "historical_bar_count": len(normalized),
                "historical_quality": {
                    "non_empty": True,
                    "structure_valid": True,
                    "future_data": False,
                },
                "provider": provider,
                "thscode": thscode,
            },
        )
    return normalized


def _resolve_market_bars(
    client: HiThinkClient | Any,
    symbol: str,
    *,
    requested_count: int,
    minimum_acceptable_history: int,
    as_of_date: str,
    timeout: float,
    request_get: Callable[..., Any],
    retries: int,
    index: bool,
    allow_tencent_fallback: bool,
    allow_stale_as_of: bool = False,
    tencent_raw_response_callback: Callable[[Any], None] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if requested_count <= 0 or minimum_acceptable_history <= 0:
        _fail(INCOMPLETE_COVERAGE, "historical retrieval target and minimum history must be positive")
    start_ms, end_ms = _historical_window(as_of_date, requested_count)
    thscode = HITHINK_INDEX_SYMBOL if index else _hithink_thscode(symbol)
    try:
        bars = client.historical_bars(
            thscode,
            start=start_ms,
            end=end_ms,
            index=index,
            timeout=timeout,
        )
        normalized = _validate_historical_bars(
            bars,
            thscode,
            minimum_acceptable_history=minimum_acceptable_history,
            as_of_date=as_of_date,
            require_last_bar_date=index or not allow_stale_as_of,
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
            requested_count=requested_count,
            minimum_acceptable_history=minimum_acceptable_history,
            as_of_date=as_of_date,
            require_last_bar_date=index or not allow_stale_as_of,
            timeout=timeout,
            retries=retries,
            request_get=request_get,
            raw_response_callback=tencent_raw_response_callback,
        )
        return fallback, {
            "provider": "Tencent",
            "source": TENCENT_KLINE_SOURCE,
            "adjustment_mode": PROVIDER_QFQ_SNAPSHOT,
            "selection": "EXPLICIT_FALLBACK",
        }


def _history_capture_spec(
    symbol: str,
    *,
    requested_count: int,
    as_of_date: str,
    index: bool,
) -> tuple[str, str, int, int]:
    start_ms, end_ms = _historical_window(as_of_date, requested_count)
    thscode = HITHINK_INDEX_SYMBOL if index else _hithink_thscode(symbol)
    path = HITHINK_INDEX_KLINE_API if index else HITHINK_STOCK_KLINE_API
    params: dict[str, Any] = {
        "thscode": thscode,
        "interval": "1d",
        "start": start_ms,
        "end": end_ms,
    }
    if not index:
        params["adjust"] = "forward"
    return _hithink_capture_identity(path, params), thscode, start_ms, end_ms


def _load_captured_market_bars(
    store: TCloseEvidenceStore,
    logical_identity: str,
    thscode: str,
    *,
    minimum_acceptable_history: int,
    as_of_date: str,
    require_last_bar_date: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]] | None:
    record = store.load_raw("hithink_kline", logical_identity)
    if record is None:
        return None
    if record.metadata.get("content_type") != "canonical_adapter_records":
        _fail(PERSISTENCE_CONFLICT, f"Kline checkpoint is not canonical adapter records for {thscode}")
    required_metadata = ("provider", "source_identity", "provider_version", "adjustment_mode", "selection")
    if any(not record.metadata.get(field_name) for field_name in required_metadata):
        _fail(PERSISTENCE_CONFLICT, f"Kline checkpoint provenance is incomplete for {thscode}")
    try:
        bars = json.loads(record.payload.decode(str(record.metadata.get("encoding", "utf-8"))))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fail(PERSISTENCE_CONFLICT, f"Kline checkpoint cannot be decoded for {thscode}: {type(exc).__name__}")
    normalized = _validate_historical_bars(
        bars,
        thscode,
        minimum_acceptable_history=minimum_acceptable_history,
        as_of_date=as_of_date,
        require_last_bar_date=require_last_bar_date,
        provider=str(record.metadata["provider"]),
    )
    return normalized, {
        "provider": record.metadata["provider"],
        "source": record.metadata["source_identity"],
        "adjustment_mode": record.metadata["adjustment_mode"],
        "selection": record.metadata["selection"],
    }


def _quote_trade_state(quote: Mapping[str, Any], target_date: str) -> str:
    """Classify only a quote that proves ordinary target-day trading."""

    if not isinstance(quote, Mapping) or quote.get("quote_date") != target_date:
        return "UNKNOWN"
    if is_no_trade_snapshot(quote):
        return "NO_TRADE"
    required = ("price", "prev_close", "open", "high", "low", "volume")
    values: dict[str, float] = {}
    for field_name in required:
        value = quote.get(field_name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            return "UNKNOWN"
        values[field_name] = float(value)
    if any(values[field_name] <= 0 for field_name in ("price", "prev_close", "open", "high", "low")):
        return "UNKNOWN"
    if values["volume"] <= 0 or values["high"] < values["low"]:
        return "UNKNOWN"
    if values["high"] < values["open"] or values["high"] < values["price"]:
        return "UNKNOWN"
    if values["low"] > values["open"] or values["low"] > values["price"]:
        return "UNKNOWN"
    return "TRADED"


def _quote_trade_evidence(quote: Mapping[str, Any]) -> dict[str, Any]:
    fields = (
        "code",
        "symbol",
        "name",
        "quote_date",
        "timestamp",
        "price",
        "prev_close",
        "open",
        "high",
        "low",
        "volume",
        "turnover",
        "vol_ratio",
    )
    return {field_name: copy.deepcopy(quote[field_name]) for field_name in fields if field_name in quote}


def _target_day_historical_stale_record(
    exc: LiveAcquisitionError,
    *,
    symbol: str,
    thscode: str,
    logical_identity: str,
    target_date: str,
    quote: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Return an exclusion only for the fully proven narrow stale case."""

    diagnostics = exc.diagnostics
    if exc.status != INPUT_DATE_MISMATCH or diagnostics.get("classification") != TARGET_DAY_HISTORICAL_STALE:
        return None
    if diagnostics.get("target_date") != target_date:
        return None
    latest_date = diagnostics.get("latest_historical_date")
    if not isinstance(latest_date, str) or latest_date >= target_date:
        return None
    quality = diagnostics.get("historical_quality")
    if not isinstance(quality, Mapping) or quality.get("non_empty") is not True or quality.get("structure_valid") is not True or quality.get("future_data") is not False:
        return None
    provider = diagnostics.get("provider")
    if not isinstance(provider, str) or not provider.strip():
        return None
    if _quote_trade_state(quote, target_date) != "TRADED":
        return None
    record = {
        "symbol": symbol,
        "provider_symbol": thscode,
        "target_date": target_date,
        "provider": provider,
        "status": EXCLUDED_PROVIDER_STALE,
        "reason": TARGET_DAY_HISTORICAL_STALE,
        "latest_historical_date": latest_date,
        "quote_trade_state": "TRADED",
        "evidence": {
            "quote": {
                "provider": "Tencent",
                "source": TENCENT_QUOTE_SOURCE,
                **_quote_trade_evidence(quote),
            },
            "historical": {
                "provider": provider,
                "source": diagnostics.get("source") or HITHINK_STOCK_KLINE_API,
                "thscode": thscode,
                "logical_identity": logical_identity,
                "latest_historical_date": latest_date,
                "bar_count": diagnostics.get("historical_bar_count"),
                "validation": copy.deepcopy(dict(quality)),
            },
            "session": {
                "calendar": XSHG_CALENDAR,
                "target_date": target_date,
                "target_day_is_trading_session": True,
            },
            "provenance": {
                "quote_source": TENCENT_QUOTE_SOURCE,
                "historical_request_identity": logical_identity,
            },
            "classification": TARGET_DAY_HISTORICAL_STALE,
        },
        "policy_version": PER_SYMBOL_PROVIDER_FAILURE_ISOLATION_V1,
    }
    try:
        return validate_input_coverage(
            {
                "schema_version": INPUT_COVERAGE_SCHEMA,
                "coverage_status": INPUT_COVERAGE_DEGRADED,
                "evaluated_symbol_count": 1,
                "excluded_symbol_count": 1,
                "excluded_symbols": [record],
                "policy_version": PER_SYMBOL_PROVIDER_FAILURE_ISOLATION_V1,
            }
        )["excluded_symbols"][0]
    except ValueError:
        return None


def _build_input_coverage(
    evaluated_symbol_count: int,
    excluded_symbols: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    value = {
        "schema_version": INPUT_COVERAGE_SCHEMA,
        "coverage_status": INPUT_COVERAGE_DEGRADED if excluded_symbols else INPUT_COVERAGE_COMPLETE,
        "evaluated_symbol_count": evaluated_symbol_count,
        "excluded_symbol_count": len(excluded_symbols),
        "excluded_symbols": [copy.deepcopy(dict(item)) for item in excluded_symbols],
        "policy_version": PER_SYMBOL_PROVIDER_FAILURE_ISOLATION_V1,
    }
    try:
        return validate_input_coverage(
            value,
            expected_evaluated_symbol_count=evaluated_symbol_count,
        )
    except ValueError as exc:
        _fail(PROVIDER_FAILURE, f"input coverage metadata is invalid: {exc}")
        raise AssertionError from exc


def _filter_sector_symbols(sector: Any, excluded_symbols: set[str]) -> Any:
    if not excluded_symbols:
        return sector

    def retain(value: Any) -> Any:
        if isinstance(value, Mapping):
            if str(value.get("symbol", "")).strip().lower() in excluded_symbols:
                return None
            return {key: retain(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [item for item in (retain(item) for item in value) if item is not None]
        return copy.deepcopy(value)

    return replace(
        sector,
        members=retain(sector.members),
        rank_input=retain(sector.rank_input),
    )


def _capture_market_bars(
    store: TCloseEvidenceStore,
    logical_identity: str,
    bars: Sequence[Mapping[str, Any]],
    resolution: Mapping[str, Any],
    *,
    as_of_date: str,
) -> None:
    provider = str(resolution["provider"])
    store.capture_records(
        "hithink_kline",
        logical_identity,
        list(bars),
        provider=provider,
        source_identity=str(resolution["source"]),
        provider_version=(
            HITHINK_API_VERSION
            if provider == "HiThink Financial-API"
            else f"requests/{_installed_version('requests')}"
        ),
        request_identity=logical_identity,
        effective_trading_date=as_of_date,
        metadata_extra={
            "adjustment_mode": resolution["adjustment_mode"],
            "selection": resolution["selection"],
        },
    )


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


def _validate_universe_roster_quality(value: Any, as_of_date: str) -> None:
    if not isinstance(value, Mapping):
        _fail(PROVIDER_FAILURE, "manifest official-roster quality is missing")
    if value.get("identity") != EXCHANGE_OFFICIAL_LISTED_ROSTER_VERSION:
        _fail(PROVIDER_FAILURE, "manifest official-roster identity is unsupported")
    if value.get("as_of_date") != as_of_date:
        _fail(INPUT_DATE_MISMATCH, "official-roster as_of_date does not match the generation date")
    if value.get("listing_date_rule") != "listing_date <= as_of_date":
        _fail(PROVIDER_FAILURE, "official-roster listing-date rule is missing or unsupported")
    if value.get("universe_policy") != universe_policy_metadata():
        _fail(PROVIDER_FAILURE, "official-roster production universe policy is missing or unsupported")
    try:
        validate_board_policy_audit(value.get("board_policy_audit"))
    except ValueError as exc:
        _fail(PROVIDER_FAILURE, f"official-roster board policy audit is invalid: {exc}")
    counts = value.get("source_row_counts")
    if not isinstance(counts, Mapping) or set(counts) != {"sse_main_board", "sse_star", "szse_a_share"}:
        _fail(PROVIDER_FAILURE, "official-roster source row counts are invalid")
    if any(isinstance(count, bool) or not isinstance(count, int) or count <= 0 for count in counts.values()):
        _fail(PROVIDER_FAILURE, "official-roster source row counts are incomplete")
    for field_name in (
        "hithink_broad_symbols",
        "hithink_only_symbols",
        "roster_only_symbols",
        "pre_listing_symbols",
    ):
        symbols = value.get(field_name)
        if not isinstance(symbols, list) or symbols != sorted(set(symbols)):
            _fail(PROVIDER_FAILURE, f"official-roster diagnostic list is invalid: {field_name}")
    count_fields = (
        ("hithink_broad_count", "hithink_broad_symbols"),
        ("hithink_only_count", "hithink_only_symbols"),
        ("roster_only_count", "roster_only_symbols"),
        ("pre_listing_count", "pre_listing_symbols"),
    )
    for count_field, list_field in count_fields:
        count = value.get(count_field)
        if isinstance(count, bool) or not isinstance(count, int) or count != len(value[list_field]):
            _fail(PROVIDER_FAILURE, f"official-roster diagnostic count is invalid: {count_field}")
    for field_name in ("canonical_combined_symbol_count", "official_listed_count", "retained_count"):
        count = value.get(field_name)
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            _fail(PROVIDER_FAILURE, f"official-roster count is invalid: {field_name}")
    for field_name in ("content_sha256", "semantic_sha256"):
        digest = value.get(field_name)
        if not isinstance(digest, str) or len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            _fail(PROVIDER_FAILURE, f"official-roster {field_name} is not a SHA-256 digest")


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
    roster_quality = manifest.provider_version_metadata.get("universe_roster_quality")
    _validate_universe_roster_quality(roster_quality, manifest.signal_date)
    if manifest.provider_version_metadata.get("universe_policy") != UNIVERSE_POLICY_MAIN_BOARD_ONLY_V1:
        _fail(INPUT_CONFLICT, "manifest production universe policy is missing or unsupported")
    if manifest.provider_version_metadata.get("universe_policy_metadata") != universe_policy_metadata():
        _fail(INPUT_CONFLICT, "manifest production universe policy metadata is invalid")
    coverage = manifest.provider_version_metadata.get("input_coverage")
    if not isinstance(coverage, Mapping):
        _fail(PROVIDER_FAILURE, "manifest input coverage metadata is missing")
    try:
        normalized_coverage = validate_input_coverage(
            coverage,
            expected_evaluated_symbol_count=len(manifest.universe.symbols),
            expected_target_date=manifest.signal_date,
        )
    except ValueError as exc:
        _fail(PROVIDER_FAILURE, f"manifest input coverage metadata is invalid: {exc}")
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
        "universe_policy": universe_policy_metadata(),
        "input_coverage": normalized_coverage,
        "display_name_normalization": {
            "version": DISPLAY_NAME_NORMALIZATION_VERSION,
            "zero_width_codepoints": [
                f"U+{codepoint:04X}"
                for codepoint in DISPLAY_NAME_NORMALIZATION_ZERO_WIDTH_CODEPOINTS
            ],
            "rule": DISPLAY_NAME_NORMALIZATION_RULE,
        },
        "display_name_consistency_policy": _display_name_policy_metadata(),
        "universe_roster_quality": copy.deepcopy(dict(roster_quality)),
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
        if provenance.get("universe_policy") != UNIVERSE_POLICY_MAIN_BOARD_ONLY_V1:
            _fail(INPUT_CONFLICT, "provenance production universe policy is missing or unsupported")
        if provenance.get("universe_policy_metadata") != universe_policy_metadata():
            _fail(INPUT_CONFLICT, "provenance production universe policy metadata is invalid")
        manifest_metadata = self.generation_input_manifest.provider_version_metadata
        if manifest_metadata.get("universe_policy") != UNIVERSE_POLICY_MAIN_BOARD_ONLY_V1:
            _fail(INPUT_CONFLICT, "generation manifest production universe policy is missing or unsupported")
        if manifest_metadata.get("universe_policy_metadata") != universe_policy_metadata():
            _fail(INPUT_CONFLICT, "generation manifest production universe policy metadata is invalid")
        if provenance.get("display_name_consistency_policy") != _display_name_policy_metadata():
            _fail(INPUT_CONFLICT, "provenance display-name consistency policy is missing or unsupported")
        manifest_coverage = manifest_metadata.get("input_coverage")
        provenance_coverage = provenance.get("input_coverage")
        if not isinstance(manifest_coverage, Mapping) or not isinstance(provenance_coverage, Mapping):
            _fail(PROVIDER_FAILURE, "input coverage metadata is missing")
        try:
            normalized_coverage = validate_input_coverage(
                manifest_coverage,
                expected_evaluated_symbol_count=len(self.generation_input_manifest.universe.symbols),
                expected_target_date=self.generation_input_manifest.signal_date,
            )
        except ValueError as exc:
            _fail(PROVIDER_FAILURE, f"input coverage metadata is invalid: {exc}")
        if dict(provenance_coverage) != normalized_coverage:
            _fail(INPUT_CONFLICT, "provenance input coverage does not match the generation manifest")
        provenance_metadata = provenance.get("provider_version_metadata")
        if not isinstance(provenance_metadata, Mapping) or provenance_metadata.get("input_coverage") != normalized_coverage:
            _fail(INPUT_CONFLICT, "provenance provider metadata does not match input coverage")
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
        roster_quality = provenance.get("universe_roster_quality")
        _validate_universe_roster_quality(roster_quality, self.generation_input_manifest.signal_date)
        manifest_roster_quality = self.generation_input_manifest.provider_version_metadata.get(
            "universe_roster_quality"
        )
        if manifest_roster_quality != roster_quality:
            _fail(INPUT_CONFLICT, "provenance official-roster quality does not match the generation manifest")
        if provenance.get("observation_status") != LIVE_OBSERVED:
            _fail("UNSUPPORTED_MODE", "live input provenance must be LIVE_OBSERVED")
        retrieved_at = provenance.get("retrieved_at_bjt")
        if not isinstance(retrieved_at, str):
            _fail(INPUT_DATE_MISMATCH, "provenance.retrieved_at_bjt is missing")
        retrieved_at_dt = _canonical_timestamp(retrieved_at)
        acquisition_timing = provenance.get("acquisition_timing")
        manifest_timing = self.generation_input_manifest.run_context.provider_version_metadata.get(
            "acquisition_timing"
        )
        if acquisition_timing == AUTHORIZED_WEEKEND_BACKFILL:
            if manifest_timing != AUTHORIZED_WEEKEND_BACKFILL:
                _fail(INPUT_CONFLICT, "weekend backfill timing is missing from the generation manifest")
            actual_retrieved_at = provenance.get("actual_retrieved_at_bjt")
            if not isinstance(actual_retrieved_at, str):
                _fail(INPUT_DATE_MISMATCH, "weekend backfill actual_retrieved_at_bjt is missing")
            actual_retrieved_at_dt = _canonical_timestamp(actual_retrieved_at)
            if actual_retrieved_at_dt != retrieved_at_dt:
                _fail(INPUT_DATE_MISMATCH, "weekend backfill retrieval timestamps do not match")
            if actual_retrieved_at_dt.date().isoformat() <= self.generation_input_manifest.signal_date:
                _fail(INPUT_DATE_MISMATCH, "weekend backfill actual retrieval must follow the target session")
        else:
            if acquisition_timing is not None:
                _fail(INPUT_CONFLICT, "unsupported acquisition timing marker")
            if manifest_timing is not None:
                _fail(INPUT_CONFLICT, "generation manifest acquisition timing is unsupported")
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
            "universe_listing_eligibility",
            "sector_definitions_membership_rank",
            "sector_membership_resolved_exact_v0",
            "display_name_coverage_and_symbol_identity",
            "quote_t_date_and_coverage",
            "stock_kline_as_of_t_no_future_bar",
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
    allow_weekend_backfill: bool = False,
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
    evidence_root: str | Path | None = None,
    code_git_sha: str | None = None,
) -> LiveInputPackage:
    """Acquire one real T-close input package after all preconditions pass.

    The provider calls are intentionally after ``_validate_close_window``.  A
    caller cannot use this function to turn a pre-close, future-date, or
    retrospective call into a live observation.
    """

    target_date = _canonical_date(as_of_date)
    observed_at = _canonical_timestamp(now_bjt or datetime.now(_BJT))
    cal = calendar or default_calendar()
    _validate_close_window(
        target_date,
        observed_at,
        cal,
        allow_weekend_backfill=allow_weekend_backfill,
    )
    weekend_backfill = observed_at.date().isoformat() != target_date
    if stock_bar_count <= 0 or index_bar_count <= 0:
        _fail(INCOMPLETE_COVERAGE, "bar counts must be positive")

    evidence_store = (
        TCloseEvidenceStore(
            evidence_root,
            target_date,
            code_git_sha=code_git_sha,
            actual_retrieved_at_bjt=observed_at,
        )
        if evidence_root is not None
        else None
    )
    hithink = hithink_client or HiThinkClient(
        request_get=hithink_request_get,
        capture_store=evidence_store,
    )
    if not all(callable(getattr(hithink, name, None)) for name in ("universe", "historical_bars", "capability_report")):
        _fail(PROVIDER_UNAVAILABLE, "HiThink client capability is incomplete")
    sina = SinaSectorClient(
        sina_module if sina_module is not None else akshare_module,
        akshare_version,
        evidence_store,
    )
    roster_client = ExchangeListedRosterClient(
        sina.module,
        sina.package_version,
        evidence_store,
    )
    acquisition_started = time.monotonic()
    retrieved_at_bjt = _timestamp_text(observed_at)
    try:
        universe_frame = (
            evidence_store.load_records("hithink_universe", "hithink_universe")
            if evidence_store is not None
            else None
        )
        if universe_frame is None:
            universe_frame = hithink.universe(timeout=kline_timeout)
            if evidence_store is not None:
                evidence_store.capture_records(
                    "hithink_universe",
                    "hithink_universe",
                    universe_frame,
                    provider="HiThink Financial-API",
                    source_identity=HITHINK_UNIVERSE_API,
                    provider_version=HITHINK_API_VERSION,
                    request_identity=HITHINK_UNIVERSE_API,
                    effective_trading_date=target_date,
                )
    except Exception as exc:
        if evidence_store is not None:
            evidence_store.record_failure(
                "hithink_universe",
                provider="HiThink Financial-API",
                source_identity=HITHINK_UNIVERSE_API,
                provider_version=HITHINK_API_VERSION,
                error_type=type(exc).__name__,
                error_detail=str(exc),
                request_identity=HITHINK_UNIVERSE_API,
                response_component="hithink_response",
            )
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
    try:
        official_roster, roster_audit = _build_official_listed_roster(roster_client, target_date)
        universe, display_names, universe_quality = _build_universe(
            universe_frame,
            target_date,
            retrieved_at_bjt,
            official_roster,
            roster_audit,
        )
    except LiveAcquisitionError:
        raise
    except Exception as exc:
        if evidence_store is not None:
            evidence_store.record_failure(
                "official_listed_roster",
                provider="AkShare",
                source_identity="EXCHANGE_OFFICIAL_CURRENT_LISTED_ROSTER_V1",
                provider_version=roster_client.package_version,
                error_type=type(exc).__name__,
                error_detail=str(exc),
                request_identity="official_listed_roster",
            )
        _fail(
            PROVIDER_FAILURE,
            _akshare_failure_message(
                roster_client,
                exc,
                elapsed_seconds=time.monotonic() - acquisition_started,
                universe_symbol_count=0,
                unexecuted_stage="exact Sina sector, Tencent quotes, stock/index Kline, market_env, manifest, persistence",
            ),
        )
    try:
        sector = _build_sector(sina, target_date, retrieved_at_bjt, display_names)
    except LiveAcquisitionError:
        raise
    except Exception as exc:
        if evidence_store is not None:
            evidence_store.record_failure(
                "sina_sector",
                provider="AkShare",
                source_identity=SINA_SOURCE_URL,
                provider_version=sina.package_version,
                error_type=type(exc).__name__,
                error_detail=str(exc),
                request_identity="sina_sector",
            )
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
    quote_provider_version = f"requests/{_installed_version('requests')}"

    def quote_identity(batch_index: int, batch: Sequence[str]) -> str:
        return f"batch={batch_index};codes={','.join(batch)}"

    def capture_quote_response(
        batch_index: int,
        batch: list[str],
        url: str,
        response: Any,
    ) -> None:
        if evidence_store is None:
            return
        payload, encoding = _response_bytes(response)
        evidence_store.capture_raw(
            "tencent_quote",
            quote_identity(batch_index, batch),
            payload,
            provider="Tencent",
            source_identity=TENCENT_QUOTE_SOURCE,
            provider_version=quote_provider_version,
            request_identity=url,
            record_count=len(batch),
            batch_count=1,
            effective_trading_date=target_date,
            encoding=encoding,
            content_type="provider_response",
            metadata_extra={
                "decode_encoding": "gbk",
                "codes": list(batch),
            },
        )

    def load_quote_response(batch_index: int, batch: list[str], url: str) -> str | None:
        if evidence_store is None:
            return None
        record = evidence_store.load_raw("tencent_quote", quote_identity(batch_index, batch))
        if record is None:
            return None
        if record.metadata.get("content_type") != "provider_response":
            _fail(PERSISTENCE_CONFLICT, f"Tencent quote capture is not a provider response for batch {batch_index}")
        try:
            return record.payload.decode(str(record.metadata.get("decode_encoding", "gbk")))
        except UnicodeDecodeError as exc:
            _fail(PERSISTENCE_CONFLICT, f"Tencent quote capture cannot be decoded for batch {batch_index}: {type(exc).__name__}")

    try:
        quotes = fetch_quotes(
            universe.symbols,
            expected_date=target_date,
            timeout=quote_timeout,
            retries=quote_retries,
            request_get=get,
            raw_response_callback=capture_quote_response,
            cached_response_loader=load_quote_response,
        )
    except MissingQuoteError as exc:
        if evidence_store is not None:
            evidence_store.record_failure(
                "tencent_quote",
                provider="Tencent",
                source_identity=TENCENT_QUOTE_SOURCE,
                provider_version=quote_provider_version,
                error_type=type(exc).__name__,
                error_detail=str(exc),
                request_identity="tencent_quote_snapshot",
                response_component="tencent_quote",
            )
        _fail(INCOMPLETE_COVERAGE, "Tencent quote coverage is incomplete")
        raise AssertionError from exc
    except StaleQuoteError as exc:
        if evidence_store is not None:
            evidence_store.record_failure(
                "tencent_quote",
                provider="Tencent",
                source_identity=TENCENT_QUOTE_SOURCE,
                provider_version=quote_provider_version,
                error_type=type(exc).__name__,
                error_detail=str(exc),
                request_identity="tencent_quote_snapshot",
                response_component="tencent_quote",
            )
        _fail(INPUT_DATE_MISMATCH, "Tencent quote is not a T-date quote")
        raise AssertionError from exc
    except QuoteParseError as exc:
        if evidence_store is not None:
            evidence_store.record_failure(
                "tencent_quote",
                provider="Tencent",
                source_identity=TENCENT_QUOTE_SOURCE,
                provider_version=quote_provider_version,
                error_type=type(exc).__name__,
                error_detail=str(exc),
                request_identity="tencent_quote_snapshot",
                response_component="tencent_quote",
            )
        if str(exc) == "empty Tencent quote response":
            _fail(INCOMPLETE_COVERAGE, "Tencent quote response is empty")
        _fail(PROVIDER_FAILURE, "Tencent quote response is malformed")
        raise AssertionError from exc
    except QuoteDataError as exc:
        if evidence_store is not None:
            evidence_store.record_failure(
                "tencent_quote",
                provider="Tencent",
                source_identity=TENCENT_QUOTE_SOURCE,
                provider_version=quote_provider_version,
                error_type=type(exc).__name__,
                error_detail=str(exc),
                request_identity="tencent_quote_snapshot",
                response_component="tencent_quote",
            )
        detail = str(exc)
        diagnostics = {
            "provider": "Tencent",
            "stage": "tencent_quote_snapshot",
            "exception_type": type(exc).__name__,
            "exception_detail": detail,
        }
        _fail(
            PROVIDER_FAILURE,
            f"Tencent quote acquisition failed: {detail or type(exc).__name__}",
            diagnostics,
        )
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

    def capture_tencent_kline_response(
        symbol: str,
        requested_count: int,
        index: bool,
        response: Any,
    ) -> None:
        if evidence_store is None:
            return
        payload, encoding = _response_bytes(response)
        provider_symbol = to_symbol(symbol)
        url = f"https://{TENCENT_KLINE_SOURCE}?param={provider_symbol},day,,,{requested_count},qfq"
        evidence_store.capture_raw(
            "tencent_kline_response",
            f"{symbol};index={str(index).lower()};count={requested_count}",
            payload,
            provider="Tencent",
            source_identity=TENCENT_KLINE_SOURCE,
            provider_version=f"requests/{_installed_version('requests')}",
            request_identity=url,
            effective_trading_date=target_date,
            encoding=encoding,
            content_type="provider_response",
            metadata_extra={"decode_encoding": "utf-8", "provider_symbol": provider_symbol},
        )

    def record_kline_failure(
        component: str,
        symbol: str,
        logical_identity: str,
        exc: Exception,
    ) -> None:
        if evidence_store is None:
            return
        evidence_store.record_failure(
            component,
            provider="HiThink Financial-API",
            source_identity=logical_identity,
            provider_version=HITHINK_API_VERSION,
            error_type=type(exc).__name__,
            error_detail=str(exc),
            request_identity=f"{symbol}:{logical_identity}",
            response_component=(
                "tencent_kline_response"
                if evidence_store.latest("tencent_kline_response") is not None
                else "hithink_response"
            ),
        )

    stock_klines: list[KlineManifest] = []
    stock_resolutions: dict[str, dict[str, Any]] = {}
    excluded_provider_stale: list[dict[str, Any]] = []
    for symbol in universe.symbols:
        logical_identity, thscode, _, _ = _history_capture_spec(
            symbol,
            requested_count=stock_bar_count,
            as_of_date=target_date,
            index=False,
        )
        try:
            cached = (
                _load_captured_market_bars(
                    evidence_store,
                    logical_identity,
                    thscode,
                    minimum_acceptable_history=MIN_STOCK_BARS_FOR_GENERATION_INPUT,
                    as_of_date=target_date,
                    require_last_bar_date=not is_no_trade_snapshot(quotes[symbol]),
                )
                if evidence_store is not None
                else None
            )
            if cached is None:
                bars, resolution = _resolve_market_bars(
                    hithink,
                    symbol,
                    requested_count=stock_bar_count,
                    minimum_acceptable_history=MIN_STOCK_BARS_FOR_GENERATION_INPUT,
                    as_of_date=target_date,
                    timeout=kline_timeout,
                    retries=kline_retries,
                    request_get=get,
                    index=False,
                    allow_tencent_fallback=allow_tencent_fallback,
                    allow_stale_as_of=is_no_trade_snapshot(quotes[symbol]),
                    tencent_raw_response_callback=lambda response, symbol=symbol: capture_tencent_kline_response(
                        symbol, stock_bar_count, False, response
                    ),
                )
                if evidence_store is not None:
                    _capture_market_bars(
                        evidence_store,
                        logical_identity,
                        bars,
                        resolution,
                        as_of_date=target_date,
                    )
            else:
                bars, resolution = cached
        except LiveAcquisitionError as exc:
            record_kline_failure("stock_kline", symbol, logical_identity, exc)
            exclusion = _target_day_historical_stale_record(
                exc,
                symbol=symbol,
                thscode=thscode,
                logical_identity=logical_identity,
                target_date=target_date,
                quote=quotes[symbol],
            )
            if exclusion is not None:
                excluded_provider_stale.append(exclusion)
                if len(excluded_provider_stale) > 1:
                    _fail(
                        TARGET_DAY_HISTORICAL_STALE_LIMIT_EXCEEDED,
                        "more than one target-day historical stale symbol is not eligible for isolation",
                        {
                            "policy_version": PER_SYMBOL_PROVIDER_FAILURE_ISOLATION_V1,
                            "reason": TARGET_DAY_HISTORICAL_STALE,
                            "symbols": [item["symbol"] for item in excluded_provider_stale],
                        },
                    )
                continue
            raise
        except Exception as exc:
            record_kline_failure("stock_kline", symbol, logical_identity, exc)
            _fail(PROVIDER_FAILURE, f"Kline acquisition failed for {symbol}: {type(exc).__name__}")
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
    index_logical_identity, index_thscode, _, _ = _history_capture_spec(
        INDEX_SYMBOL,
        requested_count=index_bar_count,
        as_of_date=target_date,
        index=True,
    )
    try:
        cached_index = (
            _load_captured_market_bars(
                evidence_store,
                index_logical_identity,
                index_thscode,
                minimum_acceptable_history=MIN_INDEX_BARS_FOR_MARKET_ENV,
                as_of_date=target_date,
                require_last_bar_date=True,
            )
            if evidence_store is not None
            else None
        )
        if cached_index is None:
            index_bars, index_resolution = _resolve_market_bars(
                hithink,
                INDEX_SYMBOL,
                requested_count=index_bar_count,
                minimum_acceptable_history=MIN_INDEX_BARS_FOR_MARKET_ENV,
                as_of_date=target_date,
                timeout=kline_timeout,
                retries=kline_retries,
                request_get=get,
                index=True,
                allow_tencent_fallback=allow_tencent_fallback,
                tencent_raw_response_callback=lambda response: capture_tencent_kline_response(
                    INDEX_SYMBOL, index_bar_count, True, response
                ),
            )
            if evidence_store is not None:
                _capture_market_bars(
                    evidence_store,
                    index_logical_identity,
                    index_bars,
                    index_resolution,
                    as_of_date=target_date,
                )
        else:
            index_bars, index_resolution = cached_index
    except LiveAcquisitionError as exc:
        record_kline_failure("index_kline", INDEX_SYMBOL, index_logical_identity, exc)
        raise
    except Exception as exc:
        record_kline_failure("index_kline", INDEX_SYMBOL, index_logical_identity, exc)
        _fail(PROVIDER_FAILURE, f"Index Kline acquisition failed: {type(exc).__name__}")
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
    if excluded_provider_stale:
        excluded_set = {item["symbol"] for item in excluded_provider_stale}
        retained_symbols = tuple(symbol for symbol in universe.symbols if symbol not in excluded_set)
        if not retained_symbols:
            _fail(
                INCOMPLETE_COVERAGE,
                "provider-stale isolation would leave no symbol for strategy evaluation",
            )
        universe = replace(universe, symbols=retained_symbols)
        display_names = {
            symbol: display_names[symbol]
            for symbol in retained_symbols
        }
        quote_manifest = replace(
            quote_manifest,
            quotes={symbol: quote_manifest.quotes[symbol] for symbol in retained_symbols},
        )
        stock_klines = [item for item in stock_klines if item.symbol in set(retained_symbols)]
        sector = _filter_sector_symbols(sector, excluded_set)
    input_coverage = _build_input_coverage(len(universe.symbols), excluded_provider_stale)
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
        "universe_policy": UNIVERSE_POLICY_MAIN_BOARD_ONLY_V1,
        "universe_policy_metadata": universe_policy_metadata(),
        "display_name_consistency_policy": _display_name_policy_metadata(),
        "universe_roster_quality": copy.deepcopy(universe_quality),
        "input_coverage": copy.deepcopy(input_coverage),
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
                "broad_source": "HiThink Financial-API",
                "official_listed_roster": roster_client.capability_report(),
                "selection_rule": "HITHINK_BROAD_INTERSECT_OFFICIAL_ROSTER_EXCHANGE_LISTED_AS_OF_T",
                "production_policy": universe_policy_metadata(),
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
    if weekend_backfill:
        provider_metadata.update(
            {
                "acquisition_timing": AUTHORIZED_WEEKEND_BACKFILL,
                "target_session": target_date,
                "actual_acquisition_date": observed_at.date().isoformat(),
                "actual_retrieved_at_bjt": retrieved_at_bjt,
                "authorization": "explicit user-authorized weekend backfill",
            }
        )
    if evidence_store is not None:
        provider_metadata["t_close_evidence"] = {
            "schema_version": CAPTURE_SCHEMA,
            "target_date": target_date,
            "status": "T_CLOSE_VOLATILE_EVIDENCE_SECURED",
            "captures": evidence_store.summary(),
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
            allow_weekend_backfill=weekend_backfill,
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
        "universe_roster_quality": copy.deepcopy(universe_quality),
        "input_coverage": copy.deepcopy(input_coverage),
        "display_name_diagnostics": {
            "mismatch_count": len(sina.display_name_mismatches),
            "mismatches": copy.deepcopy(sina.display_name_mismatches),
        },
        "sector_membership_quality": copy.deepcopy(sector_quality),
        "universe_scope": _tradable_universe_scope_metadata(),
        "universe_policy": UNIVERSE_POLICY_MAIN_BOARD_ONLY_V1,
        "universe_policy_metadata": universe_policy_metadata(),
        "known_at_rule": (
            "acquisition occurs after XSHG session close on T during an explicitly authorized "
            "immediately-following non-trading-day backfill"
            if weekend_backfill
            else "acquisition occurs only when retrieved_at_bjt >= XSHG session close on T"
        ),
        "candidate": {"strategy_version": STRATEGY_VERSION, "spec_sha256": STRATEGY_SPEC_SHA256},
        "calendar": {
            "name": "XSHG",
            "timezone": ASIA_SHANGHAI,
            "session_close": _timestamp_text(
                _validate_close_window(
                    target_date,
                    observed_at,
                    cal,
                    allow_weekend_backfill=allow_weekend_backfill,
                )
            ),
            "earliest_execution_date": manifest.earliest_execution_date,
        },
        "provider_version_metadata": provider_metadata,
        "evidence_capture": (
            copy.deepcopy(provider_metadata["t_close_evidence"])
            if evidence_store is not None
            else {"schema_version": CAPTURE_SCHEMA, "status": "NOT_CONFIGURED"}
        ),
        "quality_checks": {
            "observation_date": "PASS",
            "freshness_and_session_close": "PASS",
            "universe_non_empty_and_unique": "PASS",
            "universe_listing_eligibility": "PASS",
            "sector_definitions_membership_rank": "PASS",
            "sector_membership_resolved_exact_v0": "PASS",
            "display_name_coverage_and_symbol_identity": "PASS",
            "quote_t_date_and_coverage": "PASS",
            "stock_kline_as_of_t_no_future_bar": "PASS",
            "index_kline_t_date_no_future_bar": "PASS",
            "generation_manifest": manifest.status,
        },
        "recovery": {
            "status": "PERSISTABLE_IMMUTABLE_PACKAGE",
            "logical_identity": "generation_fingerprint",
            "formal_output_created": False,
        },
    }
    if weekend_backfill:
        provenance.update(
            {
                "acquisition_timing": AUTHORIZED_WEEKEND_BACKFILL,
                "target_session": target_date,
                "actual_acquisition_date": observed_at.date().isoformat(),
                "actual_retrieved_at_bjt": retrieved_at_bjt,
                "authorization": "explicit user-authorized weekend backfill",
            }
        )
    return LiveInputPackage(manifest, display_names, market_env, provenance)


__all__ = [
    "AKSHARE_MAX_ATTEMPTS",
    "AKSHARE_RETRY_BACKOFF_SECONDS",
    "AKSHARE_SINA_DETAIL_API",
    "AKSHARE_SINA_SPOT_API",
    "AKSHARE_SSE_LISTED_ROSTER_API",
    "AKSHARE_SSE_MAIN_BOARD_SYMBOL",
    "AKSHARE_SSE_STAR_SYMBOL",
    "AKSHARE_SZSE_A_SHARE_SYMBOL",
    "AKSHARE_SZSE_LISTED_ROSTER_API",
    "ALLOW_TENCENT_KLINE_FALLBACK",
    "CAPTURE_SCHEMA",
    "CaptureRecord",
    "DEFAULT_INDEX_BAR_COUNT",
    "DEFAULT_STOCK_BAR_COUNT",
    "MIN_STOCK_BARS_FOR_GENERATION_INPUT",
    "DISPLAY_NAME_CONSISTENCY_POLICY",
    "DISPLAY_NAME_NORMALIZATION_VERSION",
    "DISPLAY_NAME_NORMALIZATION_ZERO_WIDTH_CODEPOINTS",
    "DISPLAY_NAME_NORMALIZATION_RULE",
    "EXCHANGE_OFFICIAL_LISTED_ROSTER_VERSION",
    "ExchangeListedRosterClient",
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
    "PER_SYMBOL_PROVIDER_FAILURE_ISOLATION_V1",
    "PROVIDER_FAILURE",
    "PROVIDER_UNAVAILABLE",
    "PROVIDER_RAW_SNAPSHOT",
    "SINA_TAXONOMY",
    "SINA_DETAIL_COUNT_SOURCE_URL",
    "SINA_DETAIL_SOURCE_URL",
    "SINA_SPOT_SOURCE_URL",
    "SSE_OFFICIAL_LISTED_ROSTER_URL",
    "SZSE_OFFICIAL_LISTED_ROSTER_URL",
    "SinaSectorClient",
    "TCloseEvidenceStore",
    "TENCENT_KLINE_SOURCE",
    "TARGET_DAY_HISTORICAL_STALE",
    "TARGET_DAY_HISTORICAL_STALE_LIMIT_EXCEEDED",
    "TRADABLE_UNIVERSE_SCOPE_V1",
    "TRADABLE_UNIVERSE_SCOPE_VERSION",
    "UNIVERSE_POLICY_MAIN_BOARD_ONLY_V1",
    "acquire_live_generation_inputs",
    "akshare_runtime_capability",
    "normalize_display_name",
    "persist_live_input_package",
]
