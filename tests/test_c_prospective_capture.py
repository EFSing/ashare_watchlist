from __future__ import annotations

import ast
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import gzip
import json
from pathlib import Path
from urllib.parse import urlencode

import pytest

import c_prospective_capture as capture
import c_provider_adapter as provider_adapter
from c_prospective_capture import (
    C_ALREADY_CAPTURED,
    C_CAPTURED,
    C_CAPTURE_FAILED,
    C_CAPTURE_READY,
    C_INPUT_CONFLICT,
    C_NOT_PROSPECTIVE_BACKFILL,
    C_PARTIAL_UNVERIFIED,
    CaptureError,
    verify_persisted_capture,
)
from c_provider_adapter import ProviderGateError, _quota_profile
from trading_calendar import TradingCalendar


_BJT = timezone(timedelta(hours=8))
_TARGET = date(2026, 9, 22)
_CALENDAR = TradingCalendar(holidays=[], session_close_time=time(15, 0))
_NOW = datetime(2026, 9, 22, 15, 8, tzinfo=_BJT)


@pytest.fixture
def c_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "data" / "research" / "c_prospective_capture_v1"
    monkeypatch.setattr(capture, "C_OUTPUT_ROOT", root)
    return root


def _sessions_ending(end: date, count: int) -> list[str]:
    values: list[date] = []
    current = end
    while len(values) < count:
        if current.weekday() < 5:
            values.append(current)
        current -= timedelta(days=1)
    return [item.isoformat() for item in reversed(values)]


def _bar(day: str, close: float, *, opening: float | None = None, high: float | None = None, low: float | None = None, volume: float = 100.0) -> dict[str, object]:
    opening = close if opening is None else opening
    high = max(opening, close) + 0.8 if high is None else high
    low = min(opening, close) - 0.8 if low is None else low
    return {"date": day, "open": opening, "high": high, "low": low, "close": close, "volume": volume}


def _bars() -> list[dict[str, object]]:
    dates = _sessions_ending(_TARGET, 102)
    bars = [
        _bar(day, 80.0 + index * 0.55, high=81.0 + index * 0.55, low=79.0 + index * 0.55)
        for index, day in enumerate(dates[:90])
    ]
    bars.extend(
        [
            _bar(dates[90], 129.0, high=135.0, low=127.0, volume=90.0),
            _bar(dates[91], 125.0, high=127.0, low=123.0, volume=75.0),
            _bar(dates[92], 127.0, high=128.0, low=125.0, volume=70.0),
            _bar(dates[93], 126.0, high=127.0, low=125.0, volume=68.0),
            _bar(dates[94], 128.0, high=129.0, low=127.0, volume=72.0),
            _bar(dates[95], 125.5, high=127.0, low=124.0, volume=70.0),
            _bar(dates[96], 129.0, high=130.0, low=126.0, volume=80.0),
            _bar(dates[97], 132.0, high=133.0, low=129.0, volume=90.0),
            _bar(dates[98], 130.0, high=131.0, low=128.0, volume=95.0),
            _bar(dates[99], 129.5, high=131.0, low=128.0, volume=92.0),
            _bar(dates[100], 130.0, high=131.0, low=128.0, volume=95.0),
            _bar(dates[101], 134.0, opening=131.0, high=135.0, low=131.0, volume=250.0),
        ]
    )
    return bars


def _ms(day: str, at: time = time.min) -> int:
    value = datetime.combine(date.fromisoformat(day), at, tzinfo=_BJT)
    return int(value.timestamp() * 1000)


def _request(request_id: str, endpoint: str, params: dict[str, object], received_at: str, document: dict[str, object]) -> dict[str, object]:
    requested_at = (datetime.fromisoformat(received_at) - timedelta(minutes=1)).isoformat(timespec="seconds")
    body = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return {
        "request_id": request_id,
        "source": "HiThink Financial-API",
        "endpoint": endpoint,
        "method": "GET",
        "url": f"https://fuyao.aicubes.cn{endpoint}?{urlencode(params)}",
        "requested_at": requested_at,
        "received_at": received_at,
        "http_status": 200,
        "response_bytes": len(body),
        "response_sha256": hashlib.sha256(body).hexdigest(),
        "response_body_base64": base64.b64encode(body).decode("ascii"),
    }


def _snapshot(*, missing_st: bool = False, future_bar: bool = False) -> dict[str, object]:
    bars = _bars()
    if future_bar:
        bars[-2] = dict(bars[-2], date="2026-09-23")
    ticker_received = "2026-09-22T15:02:00+08:00"
    history_received = "2026-09-22T15:03:00+08:00"
    ticker_id = "c-fixture-universe-1"
    history_id = "c-fixture-history-1"
    ticker_params = {"asset_type": "a-share", "limit": 10000, "offset": 0}
    ticker_doc: dict[str, object] = {
        "code": 0,
        "message": "success",
        "request_id": ticker_id,
        "data": {
            "timestamp": _ms(_TARGET.isoformat(), time(15, 1)),
            "item": [{"thscode": "600001.SH", "ticker": "600001", "name": "样本银行", "exchange": "SH", "asset_type": "a-share"}],
        },
    }
    history_params = {
        "thscode": "600001.SH",
        "interval": "1d",
        "start": _ms((_TARGET - timedelta(days=420)).isoformat()),
        "end": _ms(_TARGET.isoformat(), time(23, 59, 59)),
        "adjust": "none",
    }
    history_items = [
        {
            "date_ms": _ms(str(row["date"])),
            "open_price": row["open"],
            "high_price": row["high"],
            "low_price": row["low"],
            "close_price": row["close"],
            "volume": row["volume"],
        }
        for row in bars
    ]
    history_doc: dict[str, object] = {
        "code": 0,
        "message": "success",
        "request_id": history_id,
        "data": {"timestamp": _ms(_TARGET.isoformat(), time(15, 0)), "item": history_items},
    }
    received = "2026-09-22T15:02:00+08:00"
    security: dict[str, object] = {
        "request_id": history_id,
        "security_identity": {
            "security_id": "600001.SH",
            "code": "600001",
            "symbol": "600001.SH",
            "exchange": "SH",
            "name": "样本银行",
        },
        "st_status": {
            "status": "NOT_ST",
            "known_at_t": False,
            "as_of_date": _TARGET.isoformat(),
            "known_at": received,
            "source": "HiThink Financial-API:/api/meta/tickers/list",
            "source_request_id": ticker_id,
        },
        "historical_prefix": bars[:-1],
        "t_ohlcv": bars[-1],
        "adjustment_basis": {
            "status": "KNOWN_AT_T",
            "price_basis": "UNADJUSTED_OHLCV",
            "volume_basis": "RAW_UNADJUSTED_VOLUME",
            "corporate_action_policy": "NOT_ADJUSTED",
            "source": "HiThink Financial-API:/api/a-share/prices/historical?adjust=none",
        },
    }
    if missing_st:
        security["st_status"] = {"status": "NOT_ST", "known_at_t": True}
    return {
        "schema_version": "C_PROVIDER_SNAPSHOT_V2",
        "target_date": _TARGET.isoformat(),
        "capture": {
            "mode": "SAME_DAY_T_CLOSE",
            "provider": "HiThink Financial-API",
            "provider_version": "FINANCIAL_API_REST_V1",
            "provider_quota": {"quota_scope_id": "fixture-c-only"},
            "requests": [
                _request(ticker_id, "/api/meta/tickers/list", ticker_params, ticker_received, ticker_doc),
                _request(history_id, "/api/a-share/prices/historical", history_params, history_received, history_doc),
            ],
            "failures": [],
            "plan": {"history_requests_completed": 1, "history_requests_required": 1},
        },
        "universe": {"request_ids": [ticker_id], "symbols": ["600001.SH"]},
        "securities": [security],
    }


def _capture(snapshot: dict[str, object], root: Path, now: datetime = _NOW) -> dict[str, object]:
    assert root == capture._safe_output_root()
    return capture._capture_snapshot_at(
        snapshot,
        target_date=_TARGET.isoformat(),
        runner_now=now,
        calendar=_CALENDAR,
    )


def _load(root: Path, relative: str) -> dict[str, object]:
    return json.loads((root / relative).read_text(encoding="utf-8"))


def test_verified_same_day_capture_binds_raw_provider_responses_and_c_only_store(c_root: Path):
    result = _capture(_snapshot(), c_root)
    assert result["status"] == C_CAPTURED
    assert result["quality_failure_count"] == 0
    verified = verify_persisted_capture(result["manifest"])
    assert verified["status"] == "PASS"
    observation = _load(c_root, result["observation"])
    assert observation["full_comparable_universe"]["scope"] == "FULL_COMPARABLE_UNIVERSE"
    assert observation["matched_event_samples"]["BALANCED_A"]["scope"] == "MATCHED_EVENT_SAMPLE"
    assert observation["boundary"]["b_runtime_state_written"] is False
    security = observation["securities"][0]
    assert security["st_status"]["known_at_t"] is True
    assert security["st_status"]["as_of_date"] == _TARGET.isoformat()
    assert security["source"]["response_identity"]["response_sha256"]
    assert security["t_ohlcv"]["date"] == _TARGET.isoformat()
    assert security["historical_prefix"][-1]["date"] < _TARGET.isoformat()
    assert "captured_index" in result


def test_each_rule_records_confirmation_day_volume_separately(c_root: Path):
    result = _capture(_snapshot(), c_root)
    observation = _load(c_root, result["observation"])
    for rule_id in ("BALANCED_A", "CONSERVATIVE_B"):
        volume = observation["securities"][0]["observations"][rule_id]["volume_observation"]
        assert volume["rv_t_scope"] == "CONFIRMATION_DAY_ONLY"
        assert volume["rv_t_does_not_represent_complete_pullback_volume_path"] is True
        assert volume["t_day_relative_volume"]["relative_volume_ratio"] >= 2.0


def test_known_at_t_true_without_t_day_st_source_remains_partial(c_root: Path):
    result = _capture(_snapshot(missing_st=True), c_root)
    assert result["status"] == C_PARTIAL_UNVERIFIED
    assert not (c_root / "captures" / "20260922" / "captured.json").exists()
    observation = _load(c_root, result["observation"])
    security = observation["securities"][0]
    assert security["st_status"]["known_at_t"] is False
    assert "UNRESOLVED_ST_STATUS" in security["failure_reasons"]
    assert observation["full_comparable_universe"]["count"] == 0


def test_missing_response_body_identity_fails_closed(c_root: Path):
    snapshot = _snapshot()
    snapshot["capture"]["requests"][1].pop("response_body_base64")
    result = _capture(snapshot, c_root)
    assert result["status"] == C_CAPTURE_FAILED
    assert result["failure_code"] == "PROVIDER_RESPONSE_BODY_MISSING"
    assert not (c_root / "captures" / "20260922" / "captured.json").exists()


def test_response_hash_must_match_exact_provider_body(c_root: Path):
    snapshot = _snapshot()
    snapshot["capture"]["requests"][1]["response_sha256"] = "a" * 64
    result = _capture(snapshot, c_root)
    assert result["status"] == C_CAPTURE_FAILED
    assert result["failure_code"] == "PROVIDER_RESPONSE_HASH_MISMATCH"


def test_compressed_provider_response_store_is_rechecked_during_verification(c_root: Path):
    snapshot = _snapshot()
    request = snapshot["capture"]["requests"][1]
    raw = base64.b64decode(request.pop("response_body_base64"))
    relative = "provider_responses/20260922/fixture-history.json"
    body_path = c_root / relative
    body_path.parent.mkdir(parents=True)
    wrapper = {"response_body_gzip_base64": base64.b64encode(gzip.compress(raw, mtime=0)).decode("ascii")}
    body_path.write_text(json.dumps(wrapper), encoding="utf-8")
    request["response_body_path"] = relative
    result = _capture(snapshot, c_root)
    assert result["status"] == C_CAPTURED
    body_path.write_text(json.dumps({"response_body_gzip_base64": base64.b64encode(b"not-gzip").decode("ascii")}), encoding="utf-8")
    with pytest.raises(CaptureError, match="PROVIDER_RESPONSE_BODY_INVALID"):
        verify_persisted_capture(result["manifest"])


def test_provider_request_id_must_match_raw_response_envelope(c_root: Path):
    snapshot = _snapshot()
    request = snapshot["capture"]["requests"][1]
    body = base64.b64decode(request["response_body_base64"])
    document = json.loads(body)
    document["request_id"] = "forged"
    forged = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request["response_body_base64"] = base64.b64encode(forged).decode("ascii")
    request["response_bytes"] = len(forged)
    request["response_sha256"] = hashlib.sha256(forged).hexdigest()
    result = _capture(snapshot, c_root)
    assert result["status"] == C_CAPTURE_FAILED
    assert result["failure_code"] == "PROVIDER_RESPONSE_IDENTITY_MISMATCH"


def test_live_capture_has_no_fake_clock_or_arbitrary_snapshot_cli(c_root: Path):
    snapshot = _snapshot()
    with pytest.raises(CaptureError, match="C_LIVE_ADAPTER_REQUIRED"):
        capture.capture_t_close_snapshot(snapshot, target_date=_TARGET.isoformat())
    with pytest.raises(TypeError):
        capture.capture_t_close_snapshot(snapshot, target_date=_TARGET.isoformat(), now_bjt=_NOW)
    with pytest.raises(SystemExit):
        capture._parser().parse_args(["capture", "--date", _TARGET.isoformat(), "--now-bjt", _NOW.isoformat()])
    late = _capture(snapshot, c_root, _NOW + timedelta(days=1))
    assert late["status"] == C_NOT_PROSPECTIVE_BACKFILL
    assert not (c_root / "captures" / "20260922" / "captured.json").exists()


def test_wrong_output_root_is_rejected_before_any_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(capture, "C_OUTPUT_ROOT", tmp_path / "data" / "reports")
    with pytest.raises(CaptureError, match="FORBIDDEN_DIRECTORY_REFUSED"):
        _capture(_snapshot(), tmp_path / "data" / "reports")
    assert not (tmp_path / "data" / "reports").exists()


def test_partial_capture_can_be_completed_later_same_day_with_prior_history(c_root: Path):
    partial = _capture(_snapshot(missing_st=True), c_root)
    assert partial["status"] == C_PARTIAL_UNVERIFIED
    assert not (c_root / "captures" / "20260922" / "captured.json").exists()
    complete = _capture(_snapshot(), c_root, _NOW + timedelta(minutes=15))
    assert complete["status"] == C_CAPTURED
    manifest = _load(c_root, complete["manifest"])
    prior = manifest["prior_attempts"]
    assert any(item["input_sha256"] == partial["input_sha256"] for item in prior)
    assert any("UNRESOLVED_ST_STATUS" in str(item["failure_reasons"]) for item in prior)
    assert len(list((c_root / "input_snapshots" / "20260922").glob("*.json"))) == 2


def test_same_input_is_idempotent_and_new_complete_input_conflicts(c_root: Path):
    snapshot = _snapshot()
    first = _capture(snapshot, c_root)
    index_before = (c_root / first["captured_index"]).read_bytes()
    second = _capture(snapshot, c_root, _NOW + timedelta(minutes=1))
    assert second["status"] == C_ALREADY_CAPTURED
    assert (c_root / first["captured_index"]).read_bytes() == index_before
    changed = _snapshot()
    changed["capture"]["operator_note"] = "new complete packet identity"
    conflict = _capture(changed, c_root)
    assert conflict["status"] == C_INPUT_CONFLICT
    assert (c_root / first["captured_index"]).read_bytes() == index_before


def test_concurrent_different_inputs_yield_one_capture_and_one_conflict(c_root: Path):
    left = _snapshot()
    right = _snapshot()
    left["capture"]["operator_note"] = "left"
    right["capture"]["operator_note"] = "right"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda item: _capture(item, c_root), (left, right)))
    assert sorted(result["status"] for result in results) == sorted([C_CAPTURED, C_INPUT_CONFLICT])


def test_atomic_finalize_interruption_never_writes_captured_status(c_root: Path, monkeypatch: pytest.MonkeyPatch):
    real_link = capture.os.link

    def interrupted_link(source: str, destination: str | Path) -> None:
        if Path(destination).name == "captured.json":
            raise OSError("simulated final index write interruption")
        real_link(source, destination)

    monkeypatch.setattr(capture.os, "link", interrupted_link)
    result = _capture(_snapshot(), c_root)
    assert result["status"] == C_CAPTURE_FAILED
    assert not (c_root / "captures" / "20260922" / "captured.json").exists()
    assert _load(c_root, result["manifest"])["capture_status"] == C_CAPTURE_READY
    assert _load(c_root, result["log"])["status"] == C_CAPTURE_READY


def test_missing_manifest_and_hash_corruption_do_not_replay_as_captured(c_root: Path):
    result = _capture(_snapshot(), c_root)
    manifest_path = c_root / result["manifest"]
    manifest_path.unlink()
    replay = _capture(_snapshot(), c_root, _NOW + timedelta(minutes=1))
    assert replay["status"] == C_CAPTURE_FAILED
    assert replay["failure_code"] == "CAPTURE_ARTIFACT_MISSING"


def test_persisted_observation_hash_mismatch_is_detected(c_root: Path):
    result = _capture(_snapshot(), c_root)
    (c_root / result["observation"]).write_text("{}\n", encoding="utf-8")
    with pytest.raises(CaptureError, match="CAPTURE_HASH_MISMATCH"):
        verify_persisted_capture(result["manifest"])


def test_capture_and_provider_modules_do_not_import_b_runtime_or_production_chain():
    forbidden = {"b_breakout_retest_v1_1", "b_shadow_monitor", "track_perf", "t_close_runner", "live_acquisition"}
    for name in ("c_prospective_capture.py", "c_provider_adapter.py", "run_c_prospective_capture.py"):
        source = Path(__file__).parents[1] / "scripts" / name
        tree = ast.parse(source.read_text(encoding="utf-8"))
        imported = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported.update(
            node.module.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        assert not imported.intersection(forbidden)


def test_live_adapter_fails_closed_without_c_secret_and_quota_evidence(monkeypatch: pytest.MonkeyPatch):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return _NOW

    class Calendar:
        @staticmethod
        def is_trading_day(_day: str) -> bool:
            return True

        @staticmethod
        def session_close(day: str) -> datetime:
            return datetime.combine(date.fromisoformat(day), time(15, 0), tzinfo=_BJT)

    monkeypatch.setattr(provider_adapter, "datetime", FixedDateTime)
    monkeypatch.setattr(provider_adapter, "default_calendar", lambda: Calendar())
    calls: list[str] = []

    def should_not_call(url: str, **_kwargs: object) -> None:
        calls.append(url)
        raise AssertionError("provider request must not run without verified independent quota")

    with pytest.raises(ProviderGateError, match="disabled"):
        _quota_profile({}, _NOW)
    with pytest.raises(ProviderGateError, match="B credentials are never used"):
        _quota_profile({"C_PROSPECTIVE_CAPTURE_ENABLED": "true", "HITHINK_FINANCE_API_KEY": "b-key"}, _NOW)
    with pytest.raises(ProviderGateError, match="provider-issued independent C request quota is not verified"):
        _quota_profile(_adapter_env(), _NOW)
    with pytest.raises(ProviderGateError, match="provider-issued independent C request quota is not verified"):
        provider_adapter.build_provider_snapshot(
            target_date=_TARGET.isoformat(), environ=_adapter_env(), request_get=should_not_call
        )
    assert calls == []


def _adapter_env() -> dict[str, str]:
    return {
        "C_PROSPECTIVE_CAPTURE_ENABLED": "true",
        "C_HITHINK_FINANCE_API_KEY": "independent-c-key",
        "HITHINK_FINANCE_API_KEY": "b-key",
        "C_HITHINK_QUOTA_PROFILE_JSON": json.dumps({
            "quota_scope_id": "provider-c-allocation",
            "provider_allocation_id": "allocation-c-1",
            "evidence_ref": "provider-confirmation://allocation-c-1",
            "provider_confirmed_independent_of_b": True,
            "max_requests_per_minute": 20,
            "max_requests_per_day": 6000,
            "max_concurrency": 1,
        }),
    }


def _adapter_provider(monkeypatch: pytest.MonkeyPatch, c_root: Path, *, fail_first_history: bool = False):
    # Synthetic transport tests exercise the adapter after preflight; production remains hard-blocked.
    monkeypatch.setattr(provider_adapter, "C_PROVIDER_INDEPENDENT_QUOTA_VERIFIED", True)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return _NOW

    class Calendar:
        @staticmethod
        def is_trading_day(_day: str) -> bool:
            return True

        @staticmethod
        def session_close(day: str) -> datetime:
            return datetime.combine(date.fromisoformat(day), time(15, 0), tzinfo=_BJT)

    monkeypatch.setattr(provider_adapter, "datetime", FixedDateTime)
    monkeypatch.setattr(provider_adapter, "default_calendar", lambda: Calendar())
    monkeypatch.setattr(capture, "C_OUTPUT_ROOT", c_root)
    bars = _bars()
    ticker_doc = {
        "code": 0,
        "request_id": "c-adapter-tickers-1",
        "data": {
            "timestamp": _ms(_TARGET.isoformat(), time(15, 1)),
            "item": [{"thscode": "600001.SH", "name": "样本银行", "exchange": "SH", "asset_type": "a-share"}],
        },
    }
    history_doc = {
        "code": 0,
        "request_id": "c-adapter-history-1",
        "data": {
            "timestamp": _ms(_TARGET.isoformat(), time(15, 0)),
            "item": [
                {
                    "date_ms": _ms(str(bar["date"])),
                    "open_price": bar["open"],
                    "high_price": bar["high"],
                    "low_price": bar["low"],
                    "close_price": bar["close"],
                    "volume": bar["volume"],
                }
                for bar in bars
            ],
        },
    }
    calls: list[str] = []

    class Response:
        def __init__(self, status_code: int, document: dict[str, object]):
            self.status_code = status_code
            self.content = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    def request_get(url: str, **_kwargs: object) -> Response:
        from urllib.parse import urlsplit

        endpoint = urlsplit(url).path
        calls.append(endpoint)
        if endpoint == provider_adapter.UNIVERSE_ENDPOINT:
            return Response(200, ticker_doc)
        if endpoint == provider_adapter.HISTORY_ENDPOINT:
            if fail_first_history and calls.count(provider_adapter.HISTORY_ENDPOINT) == 1:
                return Response(503, {"code": 1, "request_id": "c-adapter-history-failed", "message": "temporary"})
            return Response(200, history_doc)
        raise AssertionError(f"unexpected C provider endpoint: {endpoint}")

    return calls, request_get


def test_c_provider_adapter_captures_and_reuses_its_immutable_raw_response_cache(c_root: Path, monkeypatch: pytest.MonkeyPatch):
    calls, request_get = _adapter_provider(monkeypatch, c_root)
    snapshot = provider_adapter.build_provider_snapshot(
        target_date=_TARGET.isoformat(), environ=_adapter_env(), request_get=request_get, sleep=lambda _delay: None
    )
    first = _capture(snapshot, c_root)
    assert first["status"] == C_CAPTURED
    assert calls == [provider_adapter.UNIVERSE_ENDPOINT, provider_adapter.HISTORY_ENDPOINT]

    resumed = provider_adapter.build_provider_snapshot(
        target_date=_TARGET.isoformat(), environ=_adapter_env(), request_get=request_get, sleep=lambda _delay: None
    )
    second = _capture(resumed, c_root, _NOW + timedelta(minutes=1))
    assert second["status"] == C_ALREADY_CAPTURED
    assert calls == [provider_adapter.UNIVERSE_ENDPOINT, provider_adapter.HISTORY_ENDPOINT]


def test_c_provider_adapter_retries_only_the_missing_history_after_partial_capture(c_root: Path, monkeypatch: pytest.MonkeyPatch):
    calls, request_get = _adapter_provider(monkeypatch, c_root, fail_first_history=True)
    partial_snapshot = provider_adapter.build_provider_snapshot(
        target_date=_TARGET.isoformat(), environ=_adapter_env(), request_get=request_get, sleep=lambda _delay: None
    )
    partial = _capture(partial_snapshot, c_root)
    assert partial["status"] == C_PARTIAL_UNVERIFIED
    assert not (c_root / "captures" / "20260922" / "captured.json").exists()

    resumed_snapshot = provider_adapter.build_provider_snapshot(
        target_date=_TARGET.isoformat(), environ=_adapter_env(), request_get=request_get, sleep=lambda _delay: None
    )
    complete = _capture(resumed_snapshot, c_root, _NOW + timedelta(minutes=1))
    assert complete["status"] == C_CAPTURED
    assert calls == [
        provider_adapter.UNIVERSE_ENDPOINT,
        provider_adapter.HISTORY_ENDPOINT,
        provider_adapter.HISTORY_ENDPOINT,
    ]
    manifest = _load(c_root, complete["manifest"])
    assert any(item["input_sha256"] == partial["input_sha256"] for item in manifest["prior_attempts"])
