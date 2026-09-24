"""C-only live HiThink adapter with an explicit independent-quota gate.

No B acquisition client, credential fallback, production runner, or scheduler
is imported here. Successful provider responses are journaled immutably under
the C research root so a same-day retry can reuse them and fetch only gaps.
"""

from __future__ import annotations

import base64
from datetime import date, datetime, time, timedelta, timezone
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import time as time_module
from typing import Any, Callable, Mapping
from urllib.parse import urlencode
import uuid

import requests

from c_pre_outcome_design import classify_c_universe_row
from c_prospective_capture import (
    C_PROVIDER_HOST,
    C_PROVIDER_NAME,
    C_PROVIDER_VERSION,
    C_PROVIDER_SNAPSHOT_SCHEMA,
    _C_PROVIDER_ADAPTER_TOKEN,
    _BJT,
    _MIN_HISTORY_BARS,
    _safe_output_root,
    _safe_store_path,
    _write_immutable_json,
    capture_t_close_snapshot,
    sha256_bytes,
)
from trading_calendar import CalendarUnavailable, default_calendar
from universe_policy import BOARD_MAIN, classify_board


BASE_URL = f"https://{C_PROVIDER_HOST}"
UNIVERSE_ENDPOINT = "/api/meta/tickers/list"
HISTORY_ENDPOINT = "/api/a-share/prices/historical"
PAGE_SIZE = 10000
MAX_EXPECTED_DAILY_REQUESTS = 6000
QUOTA_PROFILE_ENV = "C_HITHINK_QUOTA_PROFILE_JSON"
# HiThink documents a shared API-key contract and dynamic request limits; no provider-issued
# independent C allocation evidence is available in this delivery. Keep live requests blocked
# until that allocation can be verified in a reviewed follow-up.
C_PROVIDER_INDEPENDENT_QUOTA_VERIFIED = False


class ProviderGateError(RuntimeError):
    """The independent live C provider path is not ready to make requests."""


def _quota_profile(environ: Mapping[str, str], now_bjt: datetime) -> tuple[str, dict[str, Any]]:
    if environ.get("C_PROSPECTIVE_CAPTURE_ENABLED", "").lower() != "true":
        raise ProviderGateError("C live capture is disabled")
    api_key = environ.get("C_HITHINK_FINANCE_API_KEY", "").strip()
    if not api_key:
        raise ProviderGateError("C_HITHINK_FINANCE_API_KEY is missing; B credentials are never used as fallback")
    if api_key == environ.get("HITHINK_FINANCE_API_KEY", ""):
        raise ProviderGateError("C API key matches the B key; independent credentials are required")
    if not C_PROVIDER_INDEPENDENT_QUOTA_VERIFIED:
        raise ProviderGateError("provider-issued independent C request quota is not verified; live requests are blocked")
    try:
        profile = json.loads(environ.get(QUOTA_PROFILE_ENV, ""))
    except json.JSONDecodeError as exc:
        raise ProviderGateError(f"{QUOTA_PROFILE_ENV} must contain the operator-reviewed JSON quota profile") from exc
    if not isinstance(profile, Mapping):
        raise ProviderGateError(f"{QUOTA_PROFILE_ENV} must be an object")
    required_text = ("quota_scope_id", "provider_allocation_id", "evidence_ref")
    for field in required_text:
        if not isinstance(profile.get(field), str) or not profile[field].strip():
            raise ProviderGateError(f"quota profile is missing {field}")
    if profile.get("provider_confirmed_independent_of_b") is not True:
        raise ProviderGateError("provider-confirmed quota independence from B is required")
    rpm = profile.get("max_requests_per_minute")
    daily = profile.get("max_requests_per_day")
    concurrency = profile.get("max_concurrency")
    if any(isinstance(value, bool) or not isinstance(value, int) for value in (rpm, daily, concurrency)):
        raise ProviderGateError("quota profile limits must be integers")
    if rpm <= 0 or daily < MAX_EXPECTED_DAILY_REQUESTS or concurrency != 1:
        raise ProviderGateError(
            f"C full-universe capture needs at least {MAX_EXPECTED_DAILY_REQUESTS} requests/day and concurrency=1"
        )
    midnight = datetime.combine(now_bjt.date() + timedelta(days=1), time.min, tzinfo=_BJT)
    minutes_left = min(max((midnight - now_bjt).total_seconds() / 60, 0), 330)
    required_rpm = math.ceil(MAX_EXPECTED_DAILY_REQUESTS / minutes_left) if minutes_left else MAX_EXPECTED_DAILY_REQUESTS
    if rpm < required_rpm:
        raise ProviderGateError(
            f"quota rate {rpm}/min cannot cover the conservative {MAX_EXPECTED_DAILY_REQUESTS}-request plan "
            f"before T-day ends; at least {required_rpm}/min is required"
        )
    return api_key, {
        "quota_scope_id": profile["quota_scope_id"],
        "provider_allocation_id": profile["provider_allocation_id"],
        "evidence_ref": profile["evidence_ref"],
        "max_requests_per_minute": rpm,
        "max_requests_per_day": daily,
        "max_concurrency": concurrency,
        "provider_confirmed_independent_of_b": True,
    }


def _url(endpoint: str, params: Mapping[str, Any]) -> str:
    return f"{BASE_URL}{endpoint}?{urlencode(params)}"


def _cache_path(root: Path, target_date: str, request: Mapping[str, Any]) -> Path:
    identity = f"{request['url']}\n{request['response_sha256']}"
    cache_sha = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return _safe_store_path(root, Path("provider_responses") / target_date.replace("-", "") / f"response_{cache_sha}.json")


def _load_cached_requests(root: Path, target_date: str) -> dict[str, dict[str, Any]]:
    folder = _safe_store_path(root, Path("provider_responses") / target_date.replace("-", ""))
    cached: dict[str, dict[str, Any]] = {}
    if not folder.exists():
        return cached
    for path in sorted(folder.glob("response_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            request = payload.get("request") if isinstance(payload, Mapping) else None
            if not isinstance(request, Mapping) or request.get("received_at", "")[:10] != target_date:
                continue
            url = request.get("url")
            if not isinstance(url, str):
                continue
            request = dict(request)
            document = _load_response_body(request, root=root)
            if document.get("request_id") != request.get("request_id") or document.get("code") != 0:
                continue
            previous = cached.get(url)
            if previous is None or str(request.get("received_at", "")) > str(previous.get("received_at", "")):
                cached[url] = request
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError, EOFError):
            continue
    return cached


def _persist_request(root: Path, target_date: str, request: Mapping[str, Any]) -> None:
    stored = dict(request)
    raw_body = stored.pop("_raw_response_body")
    compressed = gzip.compress(raw_body, mtime=0)
    body_path = _cache_path(root, target_date, stored)
    stored["response_body_path"] = body_path.resolve().relative_to(root.resolve()).as_posix()
    payload = {
        "schema_version": "C_PROVIDER_RESPONSE_JOURNAL_V1",
        "namespace": "C_PROSPECTIVE_CAPTURE_V1",
        "target_date": target_date,
        "request": stored,
        "response_body_gzip_base64": base64.b64encode(compressed).decode("ascii"),
    }
    _write_immutable_json(_cache_path(root, target_date, stored), payload)
    if isinstance(request, dict):
        request.pop("_raw_response_body", None)
    request.update(stored)


def _request(
    *,
    endpoint: str,
    params: Mapping[str, Any],
    api_key: str,
    request_get: Callable[..., Any],
    timeout: float,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    url = _url(endpoint, params)
    requested_at = datetime.now(_BJT)
    response = None
    try:
        response = request_get(url, headers={"X-api-key": api_key}, timeout=timeout)
        received_at = datetime.now(_BJT)
        body = bytes(response.content)
        try:
            document = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            document = None
        request_id = document.get("request_id") if isinstance(document, Mapping) else None
        http_status = int(response.status_code)
        request = {
            "request_id": request_id,
            "source": C_PROVIDER_NAME,
            "endpoint": endpoint,
            "method": "GET",
            "url": url,
            "requested_at": requested_at.isoformat(timespec="seconds"),
            "received_at": received_at.isoformat(timespec="seconds"),
            "http_status": http_status,
            "response_bytes": len(body),
            "response_sha256": sha256_bytes(body),
            "_raw_response_body": body,
        }
        if http_status != 200 or not isinstance(document, Mapping) or document.get("code") != 0 or not isinstance(request_id, str):
            failure = {
                "endpoint": endpoint,
                "url": url,
                "requested_at": request["requested_at"],
                "failed_at": request["received_at"],
                "http_status": http_status,
                "provider_request_id": request_id,
                "response_bytes": len(body),
                "response_sha256": request["response_sha256"],
                "response_body_gzip_base64": base64.b64encode(gzip.compress(body, mtime=0)).decode("ascii"),
                "reason": "HTTP_OR_PROVIDER_RESPONSE_FAILURE",
            }
            return None, failure
        request["request_id"] = request_id
        request["provider"] = C_PROVIDER_NAME
        request["provider_version"] = C_PROVIDER_VERSION
        return request, None
    except Exception as exc:
        failed_at = datetime.now(_BJT)
        body = bytes(getattr(response, "content", b"")) if response is not None else b""
        return None, {
            "endpoint": endpoint,
            "url": url,
            "requested_at": requested_at.isoformat(timespec="seconds"),
            "failed_at": failed_at.isoformat(timespec="seconds"),
            "http_status": getattr(response, "status_code", None),
            "response_bytes": len(body),
            "response_sha256": sha256_bytes(body),
            "response_body_gzip_base64": base64.b64encode(gzip.compress(body, mtime=0)).decode("ascii") if body else "",
            "reason": f"{type(exc).__name__}: provider request failed",
        }


def _load_response_body(request: Mapping[str, Any], *, root: Path) -> Mapping[str, Any]:
    path = _safe_store_path(root, str(request["response_body_path"]))
    envelope = json.loads(path.read_text(encoding="utf-8"))
    raw = gzip.decompress(base64.b64decode(str(envelope["response_body_gzip_base64"]), validate=True))
    if sha256_bytes(raw) != request.get("response_sha256") or len(raw) != request.get("response_bytes"):
        raise ValueError("cached provider response identity mismatch")
    document = json.loads(raw.decode("utf-8"))
    if (
        not isinstance(document, Mapping)
        or document.get("request_id") != request.get("request_id")
        or document.get("code") != 0
    ):
        raise ValueError("cached provider response identity or status mismatch")
    return document


def _bar_rows(request: Mapping[str, Any], target_date: str, *, root: Path) -> list[dict[str, Any]]:
    document = _load_response_body(request, root=root)
    data = document.get("data")
    items = data.get("item") if isinstance(data, Mapping) else None
    if not isinstance(items, list):
        return []
    bars: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, Mapping) or isinstance(item.get("date_ms"), bool) or not isinstance(item.get("date_ms"), (int, float)):
            continue
        day = datetime.fromtimestamp(float(item["date_ms"]) / 1000, timezone.utc).astimezone(_BJT).date().isoformat()
        if day <= target_date:
            bars.append(
                {
                    "date": day,
                    "open": item.get("open_price"),
                    "high": item.get("high_price"),
                    "low": item.get("low_price"),
                    "close": item.get("close_price"),
                    "volume": item.get("volume"),
                }
            )
    return sorted(bars, key=lambda bar: bar["date"])


def build_provider_snapshot(
    *,
    target_date: str,
    environ: Mapping[str, str] | None = None,
    request_get: Callable[..., Any] | None = None,
    sleep: Callable[[float], None] = time_module.sleep,
    timeout: float = 25.0,
) -> dict[str, Any]:
    """Acquire or same-day resume C provider data after independently gated preflight."""

    env = os.environ if environ is None else environ
    now_bjt = datetime.now(_BJT)
    if now_bjt.date().isoformat() != target_date:
        raise ProviderGateError("C provider capture only runs for the current Shanghai date")
    try:
        calendar = default_calendar()
        if not calendar.is_trading_day(target_date) or now_bjt < calendar.session_close(target_date).astimezone(_BJT):
            raise ProviderGateError("C provider requests are allowed only after the T trading session closes")
    except CalendarUnavailable as exc:
        raise ProviderGateError(f"trading calendar unavailable before provider request: {exc}") from exc

    api_key, quota = _quota_profile(env, now_bjt)
    rate_per_minute = quota["max_requests_per_minute"]
    get = request_get or requests.get
    root = _safe_output_root()
    cached = _load_cached_requests(root, target_date)
    requests_used: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    ticker_pages: list[dict[str, Any]] = []
    last_request_at: datetime | None = None

    def load_or_fetch(endpoint: str, params: Mapping[str, Any]) -> dict[str, Any] | None:
        nonlocal last_request_at
        url = _url(endpoint, params)
        request = cached.get(url)
        if request is None:
            if last_request_at is not None:
                delay = max(0.0, 60.0 / rate_per_minute - (datetime.now(_BJT) - last_request_at).total_seconds())
                if delay:
                    sleep(delay)
            last_request_at = datetime.now(_BJT)
            request, failure = _request(
                endpoint=endpoint,
                params=params,
                api_key=api_key,
                request_get=get,
                timeout=timeout,
            )
            if failure is not None:
                failures.append(failure)
                failure_path = _safe_store_path(
                    root,
                    Path("provider_failures") / target_date.replace("-", "") / f"failure_{uuid.uuid4().hex}.json",
                )
                _write_immutable_json(failure_path, {"namespace": "C_PROSPECTIVE_CAPTURE_V1", "target_date": target_date, **failure})
                return None
            assert request is not None
            _persist_request(root, target_date, request)
            cached[url] = request
        requests_used.append(request)
        return request

    offset = 0
    while True:
        request = load_or_fetch(UNIVERSE_ENDPOINT, {"asset_type": "a-share", "limit": PAGE_SIZE, "offset": offset})
        if request is None:
            break
        document = _load_response_body(request, root=root)
        data = document.get("data")
        items = data.get("item") if isinstance(data, Mapping) else None
        if not isinstance(items, list):
            failures.append({"endpoint": UNIVERSE_ENDPOINT, "reason": "TICKER_PAGE_ITEM_MISSING"})
            break
        ticker_pages.append(request)
        if len(items) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    ticker_rows: dict[str, tuple[Mapping[str, Any], dict[str, Any]]] = {}
    for request in ticker_pages:
        document = _load_response_body(request, root=root)
        data = document.get("data")
        items = data.get("item") if isinstance(data, Mapping) else []
        for item in items:
            if not isinstance(item, Mapping):
                continue
            symbol = item.get("thscode")
            if isinstance(symbol, str) and classify_board(symbol) == BOARD_MAIN and item.get("asset_type") == "a-share":
                ticker_rows[symbol] = (item, request)

    now_date = date.fromisoformat(target_date)
    start_date = now_date - timedelta(days=420)
    start_ms = int(datetime.combine(start_date, time.min, tzinfo=_BJT).timestamp() * 1000)
    end_ms = int(datetime.combine(now_date, time(23, 59, 59), tzinfo=_BJT).timestamp() * 1000)
    histories: dict[str, tuple[dict[str, Any], list[dict[str, Any]]]] = {}
    for symbol, (ticker, _ticker_request) in sorted(ticker_rows.items()):
        params = {"thscode": symbol, "interval": "1d", "start": start_ms, "end": end_ms, "adjust": "none"}
        request = load_or_fetch(HISTORY_ENDPOINT, params)
        if request is None:
            # A rate/credential/service failure stops the batch; cached successes remain resumable.
            break
        histories[symbol] = (request, _bar_rows(request, target_date, root=root))

    securities: list[dict[str, Any]] = []
    for symbol, (ticker, ticker_request) in sorted(ticker_rows.items()):
        history = histories.get(symbol)
        bars = history[1] if history is not None else []
        source_document = _load_response_body(ticker_request, root=root)
        source_data = source_document.get("data")
        source_timestamp = source_data.get("timestamp") if isinstance(source_data, Mapping) else None
        if isinstance(source_timestamp, (int, float)) and not isinstance(source_timestamp, bool):
            source_as_of_date = datetime.fromtimestamp(float(source_timestamp) / 1000, timezone.utc).astimezone(_BJT).date().isoformat()
        else:
            source_as_of_date = None
        classification = classify_c_universe_row(
            {"symbol": symbol, "name": ticker.get("name"), "st_status_known_at_t": source_as_of_date == target_date}
        )
        if classification.get("status") == "EXCLUDED_ST_OR_STAR_ST":
            st_status = "ST"
        elif classification.get("status") == "ELIGIBLE":
            st_status = "NOT_ST"
        else:
            st_status = "UNKNOWN"
        security: dict[str, Any] = {
            "request_id": history[0]["request_id"] if history else None,
            "security_identity": {
                "security_id": symbol,
                "code": symbol.split(".", 1)[0],
                "symbol": symbol,
                "exchange": ticker.get("exchange"),
                "name": ticker.get("name"),
            },
            "st_status": {
                "status": st_status,
                "source": f"{C_PROVIDER_NAME}:{UNIVERSE_ENDPOINT}",
                "source_request_id": ticker_request["request_id"],
                "as_of_date": source_as_of_date,
                "known_at": ticker_request["received_at"],
            },
            "historical_prefix": [bar for bar in bars if bar["date"] < target_date],
            "t_ohlcv": next((bar for bar in reversed(bars) if bar["date"] == target_date), None),
            "adjustment_basis": {
                "status": "KNOWN_AT_T",
                "price_basis": "UNADJUSTED_OHLCV",
                "volume_basis": "RAW_UNADJUSTED_VOLUME",
                "corporate_action_policy": "NOT_ADJUSTED",
                "source": f"{C_PROVIDER_NAME}:{HISTORY_ENDPOINT}?adjust=none",
            },
        }
        if history is None or len(bars) < _MIN_HISTORY_BARS:
            # Persist missing/history-short records as partial; never fill them from later dates.
            security["acquisition_note"] = "HISTORY_NOT_CAPTURED_OR_TOO_SHORT"
        securities.append(security)

    if not ticker_pages:
        failures.append({"endpoint": UNIVERSE_ENDPOINT, "reason": "NO_VERIFIED_TICKER_PAGE"})
    return {
        "schema_version": C_PROVIDER_SNAPSHOT_SCHEMA,
        "target_date": target_date,
        "capture": {
            "mode": "SAME_DAY_T_CLOSE",
            "provider": C_PROVIDER_NAME,
            "provider_version": C_PROVIDER_VERSION,
            "provider_quota": quota,
            "requests": requests_used,
            "failures": failures,
            "plan": {
                "universe_symbol_count": len(ticker_rows),
                "history_requests_completed": len(histories),
                "history_requests_required": len(ticker_rows),
                "cached_responses_reused": sum(1 for request in requests_used if request.get("received_at", "") < now_bjt.isoformat(timespec="seconds")),
                "historical_adjustment": "none",
                "max_concurrency": 1,
            },
        },
        "universe": {
            "request_ids": [request["request_id"] for request in ticker_pages],
            "symbols": sorted(ticker_rows),
        },
        "securities": securities,
    }


def main() -> int:
    now = datetime.now(_BJT)
    target_date = now.date().isoformat()
    try:
        snapshot = build_provider_snapshot(target_date=target_date)
    except ProviderGateError as exc:
        print(json.dumps({"status": "C_LIVE_CAPTURE_BLOCKED", "reason": str(exc)}, ensure_ascii=False, sort_keys=True))
        return 2
    result = capture_t_close_snapshot(
        snapshot,
        target_date=target_date,
        _provider_adapter_token=_C_PROVIDER_ADAPTER_TOKEN,
    )
    public = {key: value for key, value in result.items() if key != "input_snapshot"}
    print(json.dumps(public, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") in {"PROSPECTIVE_CAPTURED", "ALREADY_CAPTURED"} else 1


__all__ = ["ProviderGateError", "build_provider_snapshot", "main"]
