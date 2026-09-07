from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace

import pytest
import requests

import live_acquisition as live
from b_breakout_retest_v1_1 import evaluate_candidate as evaluate_b_candidate
from generation_contract import (
    FUTURE_DATA_DETECTED,
    INCOMPLETE_COVERAGE,
    INPUT_DATE_MISMATCH,
    SESSION_NOT_CLOSED,
)
from tencent_quotes import StaleQuoteError
from trading_calendar import TradingCalendar


AS_OF = "2026-08-27"
NOW = "2026-08-27T15:05:00+08:00"
SYMBOL = "600519"
INDEX_SYMBOL = "sh000001"


class FakeFrame:
    def __init__(self, rows):
        self._rows = list(rows)
        self.columns = tuple(self._rows[0]) if self._rows else ()

    @property
    def empty(self):
        return not self._rows

    def to_dict(self, orient="records"):
        assert orient == "records"
        return list(self._rows)


class FakeAkShare:
    def __init__(self, *, universe=None, definitions=None, members=None, official_roster=None, failures=None):
        self._universe = universe
        self._definitions = definitions
        self._members = members
        self._official_roster = official_roster or {}
        self._failures = {key: list(values) for key, values in (failures or {}).items()}
        self.universe_calls = 0
        self.definition_calls = 0
        self.member_calls = []
        self.roster_calls = []

    def _maybe_fail(self, api_name):
        failures = self._failures.get(api_name, [])
        if failures:
            failure = failures.pop(0)
            if isinstance(failure, BaseException):
                raise failure
            raise RuntimeError(failure)

    def stock_sector_spot(self, indicator):
        assert indicator == "新浪行业"
        self.definition_calls += 1
        self._maybe_fail("definitions")
        return FakeFrame(
            self._definitions
            if self._definitions is not None
            else [{"label": "new_bank", "板块": "银行", "涨跌幅": 1.5}]
        )

    def stock_sector_detail(self, sector):
        self.member_calls.append(sector)
        self._maybe_fail("members")
        return FakeFrame(
            self._members
            if self._members is not None
            else [{"代码": SYMBOL, "名称": "测试股份"}]
        )

    def stock_info_sh_name_code(self, symbol):
        self.roster_calls.append(("sse", symbol))
        self._maybe_fail({"主板A股": "sse_main", "科创板": "sse_star"}[symbol])
        if symbol == "主板A股":
            default = [{"证券代码": SYMBOL, "上市日期": "2001-08-23"}]
        else:
            default = [{"证券代码": "688001", "上市日期": "2020-07-22"}]
        return FakeFrame(self._official_roster.get(symbol, default))

    def stock_info_sz_name_code(self, symbol):
        assert symbol == "A股列表"
        self.roster_calls.append(("szse", symbol))
        self._maybe_fail("szse_a_share")
        return FakeFrame(
            self._official_roster.get(
                symbol,
                [{"A股代码": "000001", "A股上市日期": "1991-04-03"}],
            )
        )


class FakeHiThink:
    def __init__(self, *, universe=None, bars=None, index_bars=None, failures=None):
        self._universe = universe
        self._bars = bars
        self._index_bars = index_bars
        self._failures = {key: list(values) for key, values in (failures or {}).items()}
        self.universe_calls = 0
        self.kline_calls = []
        self.kline_requests = []

    def _maybe_fail(self, api_name):
        failures = self._failures.get(api_name, [])
        if failures:
            failure = failures.pop(0)
            if isinstance(failure, BaseException):
                raise failure
            raise RuntimeError(failure)

    def capability_report(self):
        return {
            "provider": "HiThink Financial-API",
            "api_version": "FINANCIAL_API_REST_V1",
            "authenticated": True,
            "live_primary_status": "SUPPORTED",
            "apis": {
                "universe": "/api/meta/tickers/list",
                "quotes": "/api/a-share/prices/snapshot",
                "stock_klines": "/api/a-share/prices/historical",
                "index_klines": "/api/a-share-index/prices/historical",
                "adjustment_events": "/api/a-share/corporate-actions/adjustment-factors",
            },
        }

    def universe(self, timeout):
        del timeout
        self.universe_calls += 1
        self._maybe_fail("universe")
        return self._universe if self._universe is not None else [
            {
                "thscode": "600519.SH",
                "ticker": SYMBOL,
                "name": "测试股份",
                "exchange": "SH",
                "asset_type": "a-share",
            }
        ]

    def historical_bars(self, thscode, *, start, end, index, timeout):
        self.kline_requests.append((thscode, start, end, index))
        del start, end, timeout
        self.kline_calls.append((thscode, index))
        self._maybe_fail("index" if index else "stock")
        bars = (
            self._index_bars
            if index and self._index_bars is not None
            else (self._bars if self._bars is not None else _bars())
        )
        result = []
        for row in bars:
            result.append(
                {
                    "date": row[0],
                    "open": float(row[1]),
                    "high": float(row[3]),
                    "low": float(row[4]),
                    "close": float(row[2]),
                    "volume": row[5],
                    "turnover": "1000000",
                }
            )
        return result


class FakeResponse:
    def __init__(self, payload=None, text=""):
        self._payload = payload
        self.text = text
        self.encoding = None

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def raise_for_status(self):
        return None


def _hithink_http_error_response(status_code):
    response = requests.Response()
    response.status_code = status_code
    response.url = "https://fuyao.aicubes.cn/api/a-share/prices/historical"
    response._content = b'{"code": 1, "message": "redacted test response", "data": null}'
    return response


def _bars(last_date: str = AS_OF, count: int = 21):
    end = date.fromisoformat(last_date)
    return [
        [
            (end - timedelta(days=count - index - 1)).isoformat(),
            "10.0",
            "10.3",
            "10.4",
            "9.9",
            "100",
        ]
        for index in range(count)
    ]


def _quote_line(quote_date: str = AS_OF, *, no_trade: bool = False) -> str:
    fields = ["0"] * 50
    fields[0] = "1"
    fields[1] = "测试股份"
    fields[2] = "600519"
    fields[3] = "0.77" if no_trade else "123.45"
    fields[4] = "0.77" if no_trade else "120.00"
    fields[5] = "0" if no_trade else "121.00"
    fields[6] = "0" if no_trade else "10000"
    fields[30] = f'{quote_date.replace("-", "")}153000'
    fields[32] = "0" if no_trade else "2.88"
    fields[33] = "0" if no_trade else "125.00"
    fields[34] = "0" if no_trade else "119.50"
    fields[38] = "0" if no_trade else "4.56"
    fields[49] = "0" if no_trade else "1.78"
    return f'v_sh600519="{"~".join(fields)}";'


def _request_get(*, quote_date: str = AS_OF, bars=None, calls=None, no_trade: bool = False):
    bars = _bars() if bars is None else bars

    def request_get(url, timeout):
        del timeout
        if calls is not None:
            calls.append(url)
        if url.startswith("https://qt.gtimg.cn"):
            return FakeResponse(text=_quote_line(quote_date, no_trade=no_trade))
        provider_symbol = url.split("param=", 1)[1].split(",", 1)[0]
        return FakeResponse({"data": {provider_symbol: {"qfqday": bars}}})

    return request_get


def _calendar(holidays=None):
    return TradingCalendar(holidays=set(holidays or ()), session_close_time=time(15, 0))


def _acquire(
    *,
    now_bjt=NOW,
    akshare_module=None,
    hithink_client=None,
    request_get=None,
    calendar=None,
    stock_bar_count=21,
    index_bar_count=21,
    **kwargs,
):
    return live.acquire_live_generation_inputs(
        AS_OF,
        now_bjt=now_bjt,
        calendar=calendar or _calendar(),
        sina_module=akshare_module or FakeAkShare(),
        akshare_version="1.18.94",
        hithink_client=hithink_client or FakeHiThink(),
        request_get=request_get or _request_get(),
        quote_retries=1,
        kline_retries=1,
        stock_bar_count=stock_bar_count,
        index_bar_count=index_bar_count,
        **kwargs,
    )


def test_pre_close_is_rejected_before_any_provider_call():
    calls = []

    with pytest.raises(live.LiveAcquisitionError) as caught:
        _acquire(now_bjt="2026-08-27T14:59:59+08:00", request_get=_request_get(calls=calls))

    assert caught.value.status == SESSION_NOT_CLOSED
    assert calls == []


def test_wrong_observation_date_is_rejected_without_current_data_backfill():
    calls = []
    ak = FakeAkShare()

    with pytest.raises(live.LiveAcquisitionError) as caught:
        _acquire(now_bjt="2026-08-28T15:05:00+08:00", akshare_module=ak, request_get=_request_get(calls=calls))

    assert caught.value.status == INPUT_DATE_MISMATCH
    assert ak.member_calls == []
    assert calls == []


def test_sector_provider_unavailable_fails_closed():
    with pytest.raises(live.LiveAcquisitionError) as caught:
        _acquire(akshare_module=SimpleNamespace())

    assert caught.value.status == live.PROVIDER_UNAVAILABLE


def test_hithink_provider_unavailable_fails_closed():
    with pytest.raises(live.LiveAcquisitionError) as caught:
        _acquire(hithink_client=SimpleNamespace())

    assert caught.value.status == live.PROVIDER_UNAVAILABLE


def test_official_roster_provider_unavailable_fails_closed_before_sector_or_quote():
    ak = FakeAkShare(failures={"sse_main": [ConnectionError("down")] * live.AKSHARE_MAX_ATTEMPTS})
    calls = []

    with pytest.raises(live.LiveAcquisitionError) as caught:
        _acquire(akshare_module=ak, request_get=_request_get(calls=calls))

    assert caught.value.status == live.PROVIDER_FAILURE
    assert ak.roster_calls == [("sse", "主板A股")] * live.AKSHARE_MAX_ATTEMPTS
    assert ak.member_calls == []
    assert calls == []


def test_official_roster_missing_listing_date_fails_closed():
    ak = FakeAkShare(
        official_roster={
            "主板A股": [{"证券代码": SYMBOL}],
        }
    )

    with pytest.raises(live.LiveAcquisitionError) as caught:
        _acquire(akshare_module=ak)

    assert caught.value.status == live.PROVIDER_FAILURE
    assert ak.member_calls == []


def test_official_roster_duplicate_symbol_fails_closed():
    ak = FakeAkShare(
        official_roster={
            "主板A股": [
                {"证券代码": SYMBOL, "上市日期": "2001-08-23"},
                {"证券代码": SYMBOL, "上市日期": "2001-08-23"},
            ],
        }
    )

    with pytest.raises(live.LiveAcquisitionError) as caught:
        _acquire(akshare_module=ak)

    assert caught.value.status == live.INPUT_CONFLICT
    assert ak.member_calls == []


def test_empty_universe_fails_closed():
    with pytest.raises(live.LiveAcquisitionError) as caught:
        _acquire(hithink_client=FakeHiThink(universe=[]))

    assert caught.value.status == INCOMPLETE_COVERAGE


def test_bj_is_excluded_by_explicit_sh_sz_scope_without_coverage_failure():
    hithink = FakeHiThink(
        universe=[
            {
                "thscode": "600519.SH",
                "ticker": SYMBOL,
                "name": "测试股份",
                "exchange": "SH",
                "asset_type": "a-share",
            },
            {
                "thscode": "430047.BJ",
                "ticker": "430047",
                "name": "北交测试",
                "exchange": "BJ",
                "asset_type": "a-share",
            },
        ]
    )

    package = _acquire(hithink_client=hithink)

    assert package.generation_input_manifest.universe.symbols == (SYMBOL,)
    assert package.generation_input_manifest.universe.universe_scope == "SH_SZ_A_SHARE_ONLY"
    assert package.generation_input_manifest.universe.universe_scope_version == "TRADABLE_UNIVERSE_SCOPE_V1"
    assert package.generation_identity_payload["universe_scope"] == {
        "name": "SH_SZ_A_SHARE_ONLY",
        "version": "TRADABLE_UNIVERSE_SCOPE_V1",
    }
    assert package.provenance["universe_scope"] == {
        "version": "TRADABLE_UNIVERSE_SCOPE_V1",
        "name": "SH_SZ_A_SHARE_ONLY",
        "asset_type": "a-share",
        "included_exchanges": ["SH", "SZ"],
        "excluded_exchanges": ["BJ"],
    }
    assert package.provenance["provider_version_metadata"]["providers"]["universe"]["scope"] == package.provenance[
        "universe_scope"
    ]
    quality = package.provenance["universe_roster_quality"]
    assert quality["hithink_broad_count"] == 1
    assert quality["retained_count"] == 1
    assert quality["hithink_only_symbols"] == []
    assert quality["roster_only_count"] == 2


def test_prelisting_symbol_is_excluded_before_quote_and_kline():
    calls = []
    hithink = FakeHiThink(
        universe=[
            {
                "thscode": "600519.SH",
                "ticker": "600519",
                "name": "测试股份",
                "exchange": "SH",
                "asset_type": "a-share",
            },
            {
                "thscode": "301686.SZ",
                "ticker": "301686",
                "name": "中塑股份",
                "exchange": "SZ",
                "asset_type": "a-share",
            },
        ]
    )
    ak = FakeAkShare(
        official_roster={
            "主板A股": [{"证券代码": "600519", "上市日期": "2001-08-23"}],
            "科创板": [{"证券代码": "688001", "上市日期": "2020-07-22"}],
            "A股列表": [
                {"A股代码": "000001", "A股上市日期": "1991-04-03"},
                {"A股代码": "301686", "A股上市日期": "2026-08-28"},
            ],
        }
    )

    package = _acquire(
        hithink_client=hithink,
        akshare_module=ak,
        request_get=_request_get(calls=calls),
    )

    assert package.generation_input_manifest.universe.symbols == ("600519",)
    assert "sz301686" not in " ".join(calls)
    assert all(call[0] != "301686.SZ" for call in hithink.kline_calls)
    quality = package.provenance["universe_roster_quality"]
    assert quality["hithink_only_symbols"] == ["301686"]
    assert quality["pre_listing_symbols"] == ["301686"]


def test_listed_suspended_st_symbol_is_retained_before_final_user_eligibility():
    frame = FakeFrame(
        [
            {
                "thscode": "600519.SH",
                "ticker": "600519",
                "name": "测试股份",
                "exchange": "SH",
                "asset_type": "a-share",
            },
            {
                "thscode": "002731.SZ",
                "ticker": "002731",
                "name": "*ST萃华",
                "exchange": "SZ",
                "asset_type": "a-share",
            },
        ]
    )
    roster = {
        "600519": {"source": "sse_main_board", "symbol": "600519", "listing_date": "2001-08-23"},
        "002731": {"source": "szse_a_share", "symbol": "002731", "listing_date": "2011-12-16"},
    }
    universe, names, _ = live._build_universe(
        frame,
        AS_OF,
        NOW,
        roster,
        {
            "identity": live.EXCHANGE_OFFICIAL_LISTED_ROSTER_VERSION,
            "as_of_date": AS_OF,
            "listing_date_rule": "listing_date <= as_of_date",
        },
    )

    assert universe.symbols == ("002731", "600519")
    assert names["002731"] == "*ST萃华"


def test_ordinary_sh_sz_and_star_listed_symbols_are_retained_by_exact_symbol_join():
    frame = FakeFrame(
        [
            {"thscode": "600519.SH", "ticker": "600519", "name": "沪市", "exchange": "SH", "asset_type": "a-share"},
            {"thscode": "688001.SH", "ticker": "688001", "name": "科创", "exchange": "SH", "asset_type": "a-share"},
            {"thscode": "000001.SZ", "ticker": "000001", "name": "深市", "exchange": "SZ", "asset_type": "a-share"},
        ]
    )
    roster = {
        "600519": {"source": "sse_main_board", "symbol": "600519", "listing_date": "2001-08-23"},
        "688001": {"source": "sse_star", "symbol": "688001", "listing_date": "2020-07-22"},
        "000001": {"source": "szse_a_share", "symbol": "000001", "listing_date": "1991-04-03"},
    }

    universe, _, _ = live._build_universe(
        frame,
        AS_OF,
        NOW,
        roster,
        {"identity": live.EXCHANGE_OFFICIAL_LISTED_ROSTER_VERSION, "as_of_date": AS_OF},
    )

    assert universe.symbols == ("000001", "600519", "688001")


def test_official_roster_invalid_listing_date_fails_closed():
    ak = FakeAkShare(
        official_roster={
            "主板A股": [{"证券代码": SYMBOL, "上市日期": "not-a-date"}],
        }
    )

    with pytest.raises(live.LiveAcquisitionError) as caught:
        _acquire(akshare_module=ak)

    assert caught.value.status == live.PROVIDER_FAILURE
    assert ak.member_calls == []


def test_missing_universe_name_fails_closed():
    with pytest.raises(live.LiveAcquisitionError) as caught:
        _acquire(
            hithink_client=FakeHiThink(
                universe=[
                    {
                        "thscode": "600519.SH",
                        "ticker": SYMBOL,
                        "name": "",
                        "exchange": "SH",
                        "asset_type": "a-share",
                    }
                ]
            )
        )

    assert caught.value.status == INCOMPLETE_COVERAGE


def test_hithink_transient_universe_connection_fails_closed(monkeypatch):
    sleeps = []
    monkeypatch.setattr(live.time, "sleep", sleeps.append)
    hithink = FakeHiThink(failures={"universe": [ConnectionError("temporary")]})

    with pytest.raises(live.LiveAcquisitionError) as caught:
        _acquire(hithink_client=hithink)

    assert caught.value.status == live.PROVIDER_FAILURE
    assert hithink.universe_calls == 1
    assert sleeps == []


def test_akshare_transient_sector_definition_connection_retries_then_succeeds(monkeypatch):
    sleeps = []
    monkeypatch.setattr(live.time, "sleep", sleeps.append)
    ak = FakeAkShare(failures={"definitions": [ConnectionError("temporary")]})

    package = _acquire(akshare_module=ak)

    assert package.generation_input_manifest.status == "READY_FOR_STRATEGY_EVALUATION"
    assert ak.definition_calls == 2
    assert sleeps == [live.AKSHARE_RETRY_BACKOFF_SECONDS]


def test_em_sector_substitution_is_rejected_before_any_sector_read():
    em_only = SimpleNamespace(
        stock_board_industry_name_em=lambda: FakeFrame([]),
        stock_board_industry_cons_em=lambda symbol: FakeFrame([]),
    )

    with pytest.raises(live.LiveAcquisitionError) as caught:
        _acquire(akshare_module=em_only)

    assert caught.value.status == live.PROVIDER_UNAVAILABLE


@pytest.mark.parametrize("taxonomy", ["东方财富行业", "同花顺行业", "申万行业"])
def test_ths_em_sw_taxonomy_markers_are_rejected(taxonomy):
    sina = FakeAkShare(
        definitions=[
            {"label": "new_bank", "板块": "银行", "涨跌幅": 1.5, "taxonomy": taxonomy}
        ]
    )

    with pytest.raises(live.LiveAcquisitionError) as caught:
        _acquire(akshare_module=sina)

    assert caught.value.status == live.INPUT_CONFLICT


def test_persistent_akshare_connection_failure_stops_after_three_attempts_without_output(tmp_path, monkeypatch):
    monkeypatch.setattr(live.time, "sleep", lambda seconds: None)
    ak = FakeAkShare(
        failures={"definitions": [ConnectionError("down")] * live.AKSHARE_MAX_ATTEMPTS}
    )

    with pytest.raises(live.LiveAcquisitionError) as caught:
        _acquire(akshare_module=ak)

    assert caught.value.status == live.PROVIDER_FAILURE
    assert ak.definition_calls == live.AKSHARE_MAX_ATTEMPTS
    assert "api=stock_sector_spot" in str(caught.value)
    assert "attempts=3" in str(caught.value)
    assert "universe_symbol_count=1" in str(caught.value)
    assert "unexecuted_stage=Tencent quotes" in str(caught.value)
    assert list(tmp_path.rglob("*.json")) == []


def test_transient_sector_member_connection_retries_current_read_only(monkeypatch):
    sleeps = []
    monkeypatch.setattr(live.time, "sleep", sleeps.append)
    ak = FakeAkShare(failures={"members": [ConnectionError("temporary")]})

    package = _acquire(akshare_module=ak)

    assert package.generation_input_manifest.status == "READY_FOR_STRATEGY_EVALUATION"
    assert ak.member_calls == ["new_bank", "new_bank"]
    assert sleeps == [live.AKSHARE_RETRY_BACKOFF_SECONDS]


def test_hithink_stock_failure_uses_only_explicitly_versioned_tencent_fallback():
    hithink = FakeHiThink(failures={"stock": [ConnectionError("down")]})

    package = _acquire(hithink_client=hithink)

    assert package.generation_input_manifest.stock_klines[0].provider == "Tencent"
    policy = package.provenance["provider_version_metadata"]["market_data_failover"]
    assert policy["tencent_fallback_allowed"] is True
    assert policy["tencent_fallback_version"] == "TENCENT_QFQ_FALLBACK_V1"
    assert policy["fallback_symbols"] == [SYMBOL]


def test_tencent_stock_fallback_accepts_stale_non_empty_history_for_listed_suspension():
    hithink = FakeHiThink(failures={"stock": [ConnectionError("down")]})
    package = _acquire(
        hithink_client=hithink,
        request_get=_request_get(
            bars=_bars(last_date="2026-08-26", count=141),
            no_trade=True,
        ),
    )

    stock = package.generation_input_manifest.stock_klines[0]
    assert stock.provider == "Tencent"
    assert stock.bar_count == 141
    assert stock.last_bar_date == "2026-08-26"


def test_tencent_stock_fallback_rejects_stale_history_for_ordinary_trade():
    with pytest.raises(live.LiveAcquisitionError) as caught:
        _acquire(
            hithink_client=FakeHiThink(failures={"stock": [ConnectionError("down")]}),
            request_get=_request_get(bars=_bars(last_date="2026-08-26", count=141)),
        )

    assert caught.value.status == INPUT_DATE_MISMATCH


def test_hithink_stock_failure_is_fail_closed_when_fallback_is_disabled():
    with pytest.raises(live.LiveAcquisitionError) as caught:
        _acquire(
            hithink_client=FakeHiThink(failures={"stock": [ConnectionError("down")]}),
            allow_tencent_fallback=False,
        )

    assert caught.value.status == live.PROVIDER_FAILURE


@pytest.mark.parametrize("status_code", [408, 429, 500, 503])
def test_hithink_transient_http_status_retries_within_bounded_attempts(status_code, monkeypatch):
    sleeps = []
    calls = []
    monkeypatch.setattr(live.time, "sleep", sleeps.append)

    def request_get(url, timeout, headers):
        del timeout, headers
        calls.append(url)
        return _hithink_http_error_response(status_code)

    client = live.HiThinkClient(api_key="test-only-key", request_get=request_get)

    with pytest.raises(live._HiThinkReadFailure) as caught:
        client._read(
            live.HITHINK_STOCK_KLINE_API,
            live.HITHINK_STOCK_KLINE_API,
            {"thscode": "000002.SZ", "interval": "1d"},
            timeout=1.0,
        )

    assert caught.value.attempts == live.HITHINK_MAX_ATTEMPTS
    assert len(calls) == live.HITHINK_MAX_ATTEMPTS
    assert sleeps == [
        live.HITHINK_RETRY_BACKOFF_SECONDS,
        live.HITHINK_RETRY_BACKOFF_SECONDS * 2,
    ]


@pytest.mark.parametrize("status_code", [400, 401, 403, 404])
def test_hithink_regular_http_4xx_does_not_retry_or_fallback(status_code, monkeypatch):
    sleeps = []
    hithink_calls = []
    tencent_calls = []
    monkeypatch.setattr(live.time, "sleep", sleeps.append)

    def request_get(url, timeout, headers=None):
        del timeout
        if headers is None:
            tencent_calls.append(url)
            provider_symbol = url.split("param=", 1)[1].split(",", 1)[0]
            return FakeResponse({"data": {provider_symbol: {"qfqday": _bars()}}})
        hithink_calls.append(url)
        return _hithink_http_error_response(status_code)

    client = live.HiThinkClient(api_key="test-only-key", request_get=request_get)

    with pytest.raises(live.LiveAcquisitionError) as caught:
        live._resolve_market_bars(
            client,
            SYMBOL,
            requested_count=21,
            minimum_acceptable_history=1,
            as_of_date=AS_OF,
            timeout=1.0,
            retries=1,
            request_get=request_get,
            index=False,
            allow_tencent_fallback=True,
        )

    assert caught.value.status == live.PROVIDER_FAILURE
    assert len(hithink_calls) == 1
    assert tencent_calls == []
    assert sleeps == []


@pytest.mark.parametrize(
    "failure_type",
    [ConnectionError, TimeoutError, requests.exceptions.ConnectionError, requests.exceptions.Timeout],
)
def test_hithink_connection_and_timeout_failures_keep_bounded_retry(failure_type, monkeypatch):
    sleeps = []
    calls = []
    monkeypatch.setattr(live.time, "sleep", sleeps.append)
    responses = [failure_type("temporary"), FakeResponse({"code": 0, "data": {}})]

    def request_get(url, timeout, headers):
        del url, timeout, headers
        calls.append(True)
        result = responses.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    client = live.HiThinkClient(api_key="test-only-key", request_get=request_get)

    assert client._read(
        live.HITHINK_STOCK_KLINE_API,
        live.HITHINK_STOCK_KLINE_API,
        {"thscode": "000002.SZ", "interval": "1d"},
        timeout=1.0,
    ) == {}
    assert len(calls) == 2
    assert sleeps == [live.HITHINK_RETRY_BACKOFF_SECONDS]


def test_hithink_transient_http_exhaustion_enters_existing_tencent_fallback(monkeypatch):
    sleeps = []
    hithink_calls = []
    tencent_calls = []
    monkeypatch.setattr(live.time, "sleep", sleeps.append)

    def request_get(url, timeout, headers=None):
        del timeout
        if headers is not None:
            hithink_calls.append(url)
            return _hithink_http_error_response(503)
        tencent_calls.append(url)
        provider_symbol = url.split("param=", 1)[1].split(",", 1)[0]
        return FakeResponse({"data": {provider_symbol: {"qfqday": _bars()}}})

    client = live.HiThinkClient(api_key="test-only-key", request_get=request_get)
    bars, resolution = live._resolve_market_bars(
        client,
        SYMBOL,
        requested_count=21,
        minimum_acceptable_history=1,
        as_of_date=AS_OF,
        timeout=1.0,
        retries=1,
        request_get=request_get,
        index=False,
        allow_tencent_fallback=True,
    )

    assert len(bars) == 21
    assert resolution["provider"] == "Tencent"
    assert resolution["selection"] == "EXPLICIT_FALLBACK"
    assert len(hithink_calls) == live.HITHINK_MAX_ATTEMPTS
    assert len(tencent_calls) == 1
    assert sleeps == [
        live.HITHINK_RETRY_BACKOFF_SECONDS,
        live.HITHINK_RETRY_BACKOFF_SECONDS * 2,
    ]


def test_hithink_transient_http_exhaustion_remains_fail_closed_when_fallback_disabled(monkeypatch):
    sleeps = []
    hithink_calls = []
    tencent_calls = []
    monkeypatch.setattr(live.time, "sleep", sleeps.append)

    def request_get(url, timeout, headers=None):
        del timeout
        if headers is not None:
            hithink_calls.append(url)
            return _hithink_http_error_response(429)
        tencent_calls.append(url)
        raise AssertionError("Tencent fallback must remain disabled")

    client = live.HiThinkClient(api_key="test-only-key", request_get=request_get)
    with pytest.raises(live.LiveAcquisitionError) as caught:
        live._resolve_market_bars(
            client,
            SYMBOL,
            requested_count=21,
            minimum_acceptable_history=1,
            as_of_date=AS_OF,
            timeout=1.0,
            retries=1,
            request_get=request_get,
            index=False,
            allow_tencent_fallback=False,
        )

    assert caught.value.status == live.PROVIDER_FAILURE
    assert len(hithink_calls) == live.HITHINK_MAX_ATTEMPTS
    assert tencent_calls == []
    assert sleeps == [
        live.HITHINK_RETRY_BACKOFF_SECONDS,
        live.HITHINK_RETRY_BACKOFF_SECONDS * 2,
    ]


def test_retry_attempts_are_not_part_of_package_identity(monkeypatch):
    monkeypatch.setattr(live.time, "sleep", lambda seconds: None)
    first = _acquire()
    retried = _acquire(
        akshare_module=FakeAkShare(failures={"members": [ConnectionError("temporary")]})
    )

    assert first.generation_fingerprint == retried.generation_fingerprint
    assert first.content_sha256 == retried.content_sha256
    assert first.to_bytes() == retried.to_bytes()


def test_missing_sector_rank_fails_closed():
    ak = FakeAkShare(
        definitions=[{"label": "new_bank", "板块": "银行"}]
    )
    with pytest.raises(live.LiveAcquisitionError) as caught:
        _acquire(akshare_module=ak)

    assert caught.value.status == live.PROVIDER_FAILURE
    assert ak.definition_calls == 1
    assert ak.member_calls == []


def test_missing_sector_membership_uses_exact_v0_default():
    ak = FakeAkShare(members=[])
    package = _acquire(akshare_module=ak)

    assert ak.member_calls == ["new_bank"]
    quality = package.provenance["sector_membership_quality"]
    assert quality["missing_universe_symbol_count"] == 1
    assert quality["missing_universe_symbols"] == [SYMBOL]
    assert quality["resolution_policy"] == live.SECTOR_RESOLUTION_POLICY
    assert quality["resolved_memberships"][SYMBOL]["resolution"] == "V0_MISSING_DEFAULT"
    assert quality["resolved_memberships"][SYMBOL]["sector_name"] == "-"
    assert quality["resolved_memberships"][SYMBOL]["sector_rank"] == 50
    assert quality["resolved_memberships"][SYMBOL]["sector_chg"] == 0.0


def test_sector_member_name_mismatch_is_symbol_authoritative_diagnostic():
    ak = FakeAkShare(members=[{"代码": SYMBOL, "名称": "另一名称"}])
    package = _acquire(akshare_module=ak)

    assert ak.member_calls == ["new_bank"]
    assert package.generation_input_manifest.status == "READY_FOR_STRATEGY_EVALUATION"
    assert package.display_names == {SYMBOL: "测试股份"}
    assert package.provenance["display_name_consistency_policy"]["version"] == (
        live.DISPLAY_NAME_CONSISTENCY_POLICY
    )
    assert package.provenance["display_name_diagnostics"]["mismatch_count"] == 1
    assert package.provenance["display_name_diagnostics"]["mismatches"][0] == {
        "symbol": SYMBOL,
        "sector_code": "new_bank",
        "sector_name": "银行",
        "universe_raw_name": "测试股份",
        "sector_raw_name": "另一名称",
        "normalized_universe_name": "测试股份",
        "normalized_sector_name": "另一名称",
        "universe_name_code_points": "U+6D4B U+8BD5 U+80A1 U+4EFD",
        "sector_name_code_points": "U+53E6 U+4E00 U+540D U+79F0",
        "normalization_version": live.DISPLAY_NAME_NORMALIZATION_VERSION,
        "policy_version": live.DISPLAY_NAME_CONSISTENCY_POLICY,
        "universe_count_reached": 1,
        "sector_definition_count_reached": 1,
        "completed_sector_member_calls": 1,
    }


@pytest.mark.parametrize(
    ("universe_name", "sector_name"),
    [
        ("ＡＢＣ", "ABC"),
        ("  测试股份  ", "测试股份"),
        ("测\u200b试股份", "测试股份"),
        ("测试股份", "测试股份"),
    ],
)
def test_display_name_normalization_accepts_only_registered_representation_variants(
    universe_name, sector_name
):
    assert live.normalize_display_name(universe_name) == live.normalize_display_name(sector_name)


def _custom_name_universe(name):
    return [
        {
            "thscode": "600519.SH",
            "ticker": SYMBOL,
            "name": name,
            "exchange": "SH",
            "asset_type": "a-share",
        }
    ]


def test_normalized_name_match_preserves_raw_names_and_symbol_identity():
    package = _acquire(
        hithink_client=FakeHiThink(universe=_custom_name_universe(" 测试Ａ股 ")),
        akshare_module=FakeAkShare(members=[{"代码": SYMBOL, "名称": "测试A股"}]),
    )

    assert package.display_names == {SYMBOL: " 测试Ａ股 "}
    assert package.generation_input_manifest.universe.symbols == (SYMBOL,)
    assert package.generation_input_manifest.sector.rank_input[0]["display_name"] == "测试A股"
    assert package.generation_identity_payload["display_name_normalization"]["version"] == (
        live.DISPLAY_NAME_NORMALIZATION_VERSION
    )
    assert package.provenance["display_name_normalization"]["version"] == (
        live.DISPLAY_NAME_NORMALIZATION_VERSION
    )


@pytest.mark.parametrize(
    ("universe_name", "sector_name"),
    [
        ("ST测试", "*ST测试"),
        ("南玻Ａ", "南 玻Ａ"),
        ("测试股份", "另一家中国公司"),
    ],
)
def test_substantive_name_difference_is_retained_as_diagnostic_without_identity_gate(
    universe_name, sector_name
):
    package = _acquire(
        hithink_client=FakeHiThink(universe=_custom_name_universe(universe_name)),
        akshare_module=FakeAkShare(members=[{"代码": SYMBOL, "名称": sector_name}]),
    )

    assert package.generation_input_manifest.status == "READY_FOR_STRATEGY_EVALUATION"
    assert package.display_names == {SYMBOL: universe_name}
    diagnostic = package.provenance["display_name_diagnostics"]["mismatches"][0]
    assert diagnostic["universe_raw_name"] == universe_name
    assert diagnostic["sector_raw_name"] == sector_name
    assert diagnostic["normalized_universe_name"] != diagnostic["normalized_sector_name"]


def test_exact_duplicate_sector_row_is_retained_in_raw_traversal_and_diagnostics():
    ak = FakeAkShare(
        members=[
            {"代码": SYMBOL, "名称": "测试股份"},
            {"代码": SYMBOL, "名称": "测试股份"},
        ]
    )

    package = _acquire(akshare_module=ak)

    assert len(package.generation_input_manifest.sector.rank_input) == 2
    assert package.generation_input_manifest.sector.rank_input[0]["sector_code"] == "new_bank"
    assert package.generation_input_manifest.sector.rank_input[1]["sector_code"] == "new_bank"
    quality = package.provenance["sector_membership_quality"]
    assert quality["duplicate_row_count"] == 1
    assert quality["duplicate_rows"][0]["classification"] == "EXACT_DUPLICATE_PROVIDER_ROW"
    assert quality["duplicate_rows"][0]["raw_row"] == {"代码": SYMBOL, "名称": "测试股份"}


def test_same_symbol_in_multiple_sectors_uses_exact_v0_last_write_wins_with_provenance():
    ak = FakeAkShare(
        definitions=[
            {"label": "new_bank", "板块": "银行", "涨跌幅": 1.5},
            {"label": "new_insurance", "板块": "保险", "涨跌幅": 1.0},
        ]
    )

    package = _acquire(akshare_module=ak)

    assert package.generation_input_manifest.sector.rank_input[0]["sector_code"] == "new_bank"
    assert package.generation_input_manifest.sector.rank_input[1]["sector_code"] == "new_insurance"
    quality = package.provenance["sector_membership_quality"]
    assert quality["multi_sector_symbol_count"] == 1
    assert quality["multi_sector_symbols"] == [SYMBOL]
    assert quality["resolution_policy"] == live.SECTOR_RESOLUTION_POLICY
    assert quality["resolved_memberships"][SYMBOL]["sector_code"] == "new_insurance"
    assert quality["resolved_memberships_sha256"] == live._sha256_json(quality["resolved_memberships"])
    assert package.generation_identity_payload["sector_membership_resolution"]["resolved_memberships_sha256"] == (
        quality["resolved_memberships_sha256"]
    )


def test_sector_membership_outside_tradable_scope_is_retained_without_shrinking_universe():
    package = _acquire(
        akshare_module=FakeAkShare(
            members=[
                {"代码": SYMBOL, "名称": "测试股份"},
                {"代码": "000001", "名称": "范围外股份"},
            ]
        )
    )
    assert package.generation_input_manifest.universe.symbols == (SYMBOL,)
    assert [row["symbol"] for row in package.generation_input_manifest.sector.rank_input] == [
        SYMBOL,
        "000001",
    ]
    quality = package.provenance["sector_membership_quality"]
    assert quality["outside_universe_membership_count"] == 1


def test_normalized_display_name_identity_is_deterministic():
    first = _acquire(
        hithink_client=FakeHiThink(universe=_custom_name_universe(" 测试Ａ股 ")),
        akshare_module=FakeAkShare(members=[{"代码": SYMBOL, "名称": "测试A股"}]),
    )
    second = _acquire(
        hithink_client=FakeHiThink(universe=_custom_name_universe(" 测试Ａ股 ")),
        akshare_module=FakeAkShare(members=[{"代码": SYMBOL, "名称": "测试A股"}]),
    )

    assert first.generation_fingerprint == second.generation_fingerprint
    assert first.content_sha256 == second.content_sha256
    assert first.to_bytes() == second.to_bytes()


def test_stale_t_quote_fails_closed():
    with pytest.raises(live.LiveAcquisitionError) as caught:
        _acquire(request_get=_request_get(quote_date="2026-08-26"))

    assert caught.value.status == INPUT_DATE_MISMATCH


def test_tencent_quote_field_failure_preserves_exact_detail_and_batch():
    def request_get(url, timeout):
        del timeout
        if url.startswith("https://qt.gtimg.cn"):
            return FakeResponse(text=_quote_line().replace("~2.88~125.00", "~not-a-number~125.00"))
        provider_symbol = url.split("param=", 1)[1].split(",", 1)[0]
        return FakeResponse({"data": {provider_symbol: {"qfqday": _bars()}}})

    with pytest.raises(live.LiveAcquisitionError) as caught:
        _acquire(request_get=request_get)

    assert caught.value.status == live.PROVIDER_FAILURE
    assert "600519: invalid Tencent field p[32] (chg_pct)='not-a-number'" in str(caught.value)
    assert "failure_batch=600519" in str(caught.value)
    assert "tencent_batch=sh600519" in str(caught.value)
    assert caught.value.diagnostics == {
        "provider": "Tencent",
        "stage": "tencent_quote_snapshot",
        "exception_type": "QuoteFieldError",
        "exception_detail": (
            "600519: invalid Tencent field p[32] (chg_pct)='not-a-number'; "
            "failure_batch=600519; tencent_batch=sh600519"
        ),
    }


def test_missing_t_quote_fails_closed():
    def request_get(url, timeout):
        del timeout
        if url.startswith("https://qt.gtimg.cn"):
            return FakeResponse(text="")
        provider_symbol = url.split("param=", 1)[1].split(",", 1)[0]
        return FakeResponse({"data": {provider_symbol: {"qfqday": _bars()}}})

    with pytest.raises(live.LiveAcquisitionError) as caught:
        _acquire(request_get=request_get)

    assert caught.value.status == INCOMPLETE_COVERAGE


def test_tclose_quote_response_is_captured_before_parse_failure(tmp_path):
    def request_get(url, timeout):
        del timeout
        if url.startswith("https://qt.gtimg.cn"):
            return FakeResponse(text=_quote_line().replace("~2.88~125.00", "~not-a-number~125.00"))
        provider_symbol = url.split("param=", 1)[1].split(",", 1)[0]
        return FakeResponse({"data": {provider_symbol: {"qfqday": _bars()}}})

    with pytest.raises(live.LiveAcquisitionError):
        _acquire(request_get=request_get, evidence_root=tmp_path)

    provider_raw = []
    failure_evidence = []
    for metadata_path in tmp_path.rglob("*.json"):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("content_type") == "provider_response":
            provider_raw.append((metadata, metadata_path.with_suffix(".raw")))
        if metadata.get("content_type") == "failure_evidence":
            failure_evidence.append(metadata)
    assert len(provider_raw) == 1
    metadata, raw_path = provider_raw[0]
    assert metadata["completeness_status"] == "COMPLETE"
    assert metadata["target_date"] == AS_OF
    assert "not-a-number" in raw_path.read_text(encoding="utf-8")
    assert failure_evidence[0]["error_classification"] == "PROVIDER_DATA_VALIDATION_FAILURE"
    assert failure_evidence[0]["response_sha256"] == metadata["file_sha256"]


def test_tclose_resume_reuses_frozen_sources_after_stock_failure(tmp_path):
    evidence_root = tmp_path / "evidence"
    with pytest.raises(live.LiveAcquisitionError):
        _acquire(
            evidence_root=evidence_root,
            hithink_client=FakeHiThink(failures={"stock": [RuntimeError("stock blocked")]}),
        )

    ak = FakeAkShare(
        failures={
            "definitions": [RuntimeError("must use cached sector")],
            "members": [RuntimeError("must use cached sector")],
            "sse_main": [RuntimeError("must use cached roster")],
            "sse_star": [RuntimeError("must use cached roster")],
            "szse_a_share": [RuntimeError("must use cached roster")],
        }
    )
    hithink = FakeHiThink()
    quote_calls = []

    def no_quote_refetch(url, timeout):
        del timeout
        quote_calls.append(url)
        raise AssertionError("successful Tencent quote must be resumed from the checkpoint")

    package = _acquire(
        evidence_root=evidence_root,
        akshare_module=ak,
        hithink_client=hithink,
        request_get=no_quote_refetch,
    )

    assert package.provenance["evidence_capture"]["status"] == "T_CLOSE_VOLATILE_EVIDENCE_SECURED"
    assert quote_calls == []
    assert ak.definition_calls == 0
    assert ak.member_calls == []
    assert ak.roster_calls == []
    assert hithink.universe_calls == 0
    assert hithink.kline_calls == [("600519.SH", False), ("000001.SH", True)]


def test_tclose_successful_stock_checkpoint_survives_later_index_failure(tmp_path):
    evidence_root = tmp_path / "evidence"
    with pytest.raises(live.LiveAcquisitionError) as caught:
        _acquire(
            evidence_root=evidence_root,
            hithink_client=FakeHiThink(failures={"index": [RuntimeError("index blocked")]}),
        )

    assert caught.value.status == live.PROVIDER_FAILURE
    kline_checkpoints = []
    failure_checkpoints = []
    for metadata_path in tmp_path.rglob("*.json"):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata_path.parent.name == "hithink_kline":
            kline_checkpoints.append(metadata)
        if metadata_path.parent.name == "index_kline":
            failure_checkpoints.append(metadata)
    assert len(kline_checkpoints) == 1
    assert kline_checkpoints[0]["completeness_status"] == "COMPLETE"
    assert failure_checkpoints[0]["completeness_status"] == "FAILED"


def test_stale_index_kline_fails_closed():
    with pytest.raises(live.LiveAcquisitionError) as caught:
        _acquire(hithink_client=FakeHiThink(index_bars=_bars(last_date="2026-08-26")))

    assert caught.value.status == INPUT_DATE_MISMATCH


def test_stale_non_empty_stock_kline_is_accepted_for_listed_suspension():
    package = _acquire(
        hithink_client=FakeHiThink(
            bars=_bars(last_date="2026-08-26", count=141),
            index_bars=_bars(),
        ),
        request_get=_request_get(no_trade=True),
    )

    stock = package.generation_input_manifest.stock_klines[0]
    assert stock.bar_count == 141
    assert stock.last_bar_date == "2026-08-26"
    assert package.generation_input_manifest.status == "READY_FOR_STRATEGY_EVALUATION"


def test_stale_non_empty_stock_kline_is_rejected_for_ordinary_trade():
    with pytest.raises(live.LiveAcquisitionError) as caught:
        _acquire(
            hithink_client=FakeHiThink(
                bars=_bars(last_date="2026-08-26", count=141),
                index_bars=_bars(),
            ),
        )

    assert caught.value.status == INPUT_DATE_MISMATCH


@pytest.mark.parametrize("available_bars", [260, 141, 120])
def test_hithink_stock_history_can_be_shorter_than_retrieval_target(available_bars):
    hithink = FakeHiThink(bars=_bars(count=available_bars))

    package = _acquire(
        hithink_client=hithink,
        stock_bar_count=live.DEFAULT_STOCK_BAR_COUNT,
    )

    stock = package.generation_input_manifest.stock_klines[0]
    assert live.DEFAULT_STOCK_BAR_COUNT == 260
    assert hithink.kline_requests[0][1:3] == live._historical_window(AS_OF, live.DEFAULT_STOCK_BAR_COUNT)
    assert stock.bar_count == available_bars
    assert stock.provider == "HiThink Financial-API"
    assert stock.adjustment_mode == "PROVIDER_QFQ_SNAPSHOT"


def test_hithink_stock_history_below_b_minimum_remains_manifest_valid_and_b_reports_insufficient_data():
    package = _acquire(
        hithink_client=FakeHiThink(bars=_bars(count=119)),
        stock_bar_count=live.DEFAULT_STOCK_BAR_COUNT,
    )

    result = evaluate_b_candidate(package.generation_input_manifest, SYMBOL)

    assert package.generation_input_manifest.stock_klines[0].bar_count == 119
    assert result.status == "INSUFFICIENT_DATA"
    assert result.failed_conditions == ("MINIMUM_BARS_120",)
    assert result.reject_reasons == ("INSUFFICIENT_DATA",)


def test_hithink_duplicate_stock_bar_date_fails_closed():
    bars = _bars()
    bars[-1][0] = bars[-2][0]

    with pytest.raises(live.LiveAcquisitionError) as caught:
        _acquire(hithink_client=FakeHiThink(bars=bars))

    assert caught.value.status == live.INPUT_CONFLICT


@pytest.mark.parametrize("malformed_bar", [None, {"date": "20260827"}])
def test_hithink_malformed_or_noncanonical_stock_bar_fails_closed(malformed_bar):
    bars = [
        {
            "date": row[0],
            "open": float(row[1]),
            "high": float(row[3]),
            "low": float(row[4]),
            "close": float(row[2]),
            "volume": float(row[5]),
        }
        for row in _bars()
    ]
    bars[0] = malformed_bar

    def historical_bars(thscode, *, start, end, index, timeout):
        del thscode, start, end, index, timeout
        return bars

    client = SimpleNamespace(historical_bars=historical_bars)
    with pytest.raises(live.LiveAcquisitionError) as caught:
        live._resolve_market_bars(
            client,
            SYMBOL,
            requested_count=21,
            minimum_acceptable_history=1,
            as_of_date=AS_OF,
            timeout=1.0,
            retries=1,
            request_get=_request_get(),
            index=False,
            allow_tencent_fallback=False,
        )

    assert caught.value.status == live.PROVIDER_FAILURE


def test_future_kline_bar_fails_closed():
    future_bars = _bars()
    future_bars[-1][0] = "2026-08-28"

    with pytest.raises(live.LiveAcquisitionError) as caught:
        _acquire(hithink_client=FakeHiThink(bars=future_bars))

    assert caught.value.status == FUTURE_DATA_DETECTED


def test_complete_package_has_t_plus_one_market_env_and_provenance():
    package = _acquire(calendar=_calendar(holidays={date(2026, 8, 28)}))

    assert package.generation_input_manifest.status == "READY_FOR_STRATEGY_EVALUATION"
    assert package.generation_input_manifest.earliest_execution_date == "2026-08-31"
    assert package.display_names == {SYMBOL: "测试股份"}
    assert package.market_env["as_of_date"] == AS_OF
    assert package.market_env["adjustment_mode"] == "PROVIDER_RAW_SNAPSHOT"
    assert package.provenance["observation_status"] == "LIVE_OBSERVED"
    assert package.provenance["quality_checks"]["generation_manifest"] == "READY_FOR_STRATEGY_EVALUATION"
    assert package.provenance["provider_version_metadata"]["runtime"]["packages"]["akshare"] == "1.18.94"
    assert package.generation_input_manifest.universe.source == (
        "HiThink Financial-API /api/meta/tickers/list ∩ "
        "EXCHANGE_OFFICIAL_CURRENT_LISTED_ROSTER_V1"
    )
    assert package.generation_input_manifest.universe.universe_scope == "SH_SZ_A_SHARE_ONLY"
    assert package.generation_input_manifest.universe.universe_scope_version == "TRADABLE_UNIVERSE_SCOPE_V1"
    assert package.generation_input_manifest.index.provider == "HiThink Financial-API"
    assert package.generation_input_manifest.index.adjustment_mode == "PROVIDER_RAW_SNAPSHOT"
    assert package.provenance["provider_version_metadata"]["providers"]["sector"]["taxonomy"] == "新浪行业"
    assert package.provenance["provider_version_metadata"]["market_data_failover"]["fallback_symbols"] == []
    assert package.provenance["provider_version_metadata"]["providers"]["stock_klines"]["primary"] == "HiThink Financial-API"


def test_exact_sina_provider_is_accepted_and_identified():
    client = live.SinaSectorClient(FakeAkShare(), "1.18.94")

    report = client.capability_report()

    assert report["taxonomy"] == "新浪行业"
    assert report["exact_legacy_taxonomy"] is True
    assert report["source_urls"] == {
        "spot": live.SINA_SPOT_SOURCE_URL,
        "detail_count": live.SINA_DETAIL_COUNT_SOURCE_URL,
        "detail": live.SINA_DETAIL_SOURCE_URL,
    }
    assert report["apis"] == {
        "stock_sector_spot": True,
        "stock_sector_detail": True,
    }


def test_official_exchange_roster_source_is_explicitly_identified():
    client = live.ExchangeListedRosterClient(FakeAkShare(), "1.18.94")

    report = client.capability_report()

    assert report["identity"] == "EXCHANGE_OFFICIAL_CURRENT_LISTED_ROSTER_V1"
    assert report["sources"] == {
        "sse": {
            "url": live.SSE_OFFICIAL_LISTED_ROSTER_URL,
            "api": "stock_info_sh_name_code",
            "symbols": ["主板A股", "科创板"],
        },
        "szse": {
            "url": live.SZSE_OFFICIAL_LISTED_ROSTER_URL,
            "api": "stock_info_sz_name_code",
            "symbol": "A股列表",
        },
    }


def test_hithink_client_auth_and_stock_adjustment_mapping():
    calls = []
    date_ms = int(datetime(2026, 8, 26, 16, tzinfo=timezone.utc).timestamp() * 1000)

    def request_get(url, timeout, headers):
        calls.append((url, timeout, headers))
        return FakeResponse(
            {
                "code": 0,
                "data": {
                    "thscode": "600519.SH",
                    "item": [
                        {
                            "date_ms": date_ms,
                            "open_price": "10",
                            "high_price": "11",
                            "low_price": "9",
                            "close_price": "10.5",
                            "volume": "100",
                            "turnover": "1000000",
                        }
                    ],
                },
            }
        )

    client = live.HiThinkClient(api_key="test-only-key", request_get=request_get)
    bars = client.historical_bars(
        "600519.SH",
        start=date_ms,
        end=date_ms,
        index=False,
    )

    assert bars == [
        {
            "date": AS_OF,
            "open": 10.0,
            "high": 11.0,
            "low": 9.0,
            "close": 10.5,
            "volume": 100.0,
            "turnover": 1000000.0,
        }
    ]
    assert len(calls) == 1
    assert calls[0][2] == {"X-api-key": "test-only-key"}
    assert "thscode=600519.SH" in calls[0][0]
    assert "adjust=forward" in calls[0][0]


def test_hithink_retry_preserves_prior_response_bytes_on_resume(tmp_path):
    date_ms = int(datetime(2026, 8, 27, 8, tzinfo=timezone.utc).timestamp() * 1000)
    payload = {
        "code": 0,
        "data": {
            "thscode": "600519.SH",
            "item": [
                {
                    "date_ms": date_ms,
                    "open_price": "10",
                    "high_price": "11",
                    "low_price": "9",
                    "close_price": "10.5",
                    "volume": "100",
                    "turnover": "1000000",
                }
            ],
        },
    }

    class ErrorResponse(FakeResponse):
        def raise_for_status(self):
            raise RuntimeError("HTTP 503")

    responses = [
        ErrorResponse(text="first-error"),
        FakeResponse(payload, text="second-response"),
    ]

    def request_get(url, timeout, headers):
        del url, timeout, headers
        return responses.pop(0)

    store = live.TCloseEvidenceStore(tmp_path, AS_OF, code_git_sha="test-sha")
    client = live.HiThinkClient(
        api_key="test-only-key",
        request_get=request_get,
        capture_store=store,
    )
    with pytest.raises(RuntimeError, match="HTTP 503"):
        client.historical_bars("600519.SH", start=date_ms, end=date_ms, index=False)

    bars = client.historical_bars("600519.SH", start=date_ms, end=date_ms, index=False)

    assert bars[0]["date"] == AS_OF
    base_identity = live._hithink_capture_identity(
        live.HITHINK_STOCK_KLINE_API,
        {"thscode": "600519.SH", "interval": "1d", "start": date_ms, "end": date_ms, "adjust": "forward"},
    )
    response_records = [
        record for record in store.summary() if record["component"] == "hithink_response"
    ]
    assert len(response_records) == 2
    assert {record["logical_component_identity"] for record in response_records} == {
        base_identity,
        f"{base_identity}:response_sha256={live._sha256_bytes(b'second-response')}",
    }
    assert store.load_raw("hithink_response", base_identity).payload == b"first-error"


def test_hithink_client_requires_authenticated_key(monkeypatch):
    monkeypatch.delenv(live.HITHINK_API_KEY_ENV, raising=False)

    with pytest.raises(live.LiveAcquisitionError) as caught:
        live.HiThinkClient(api_key="")

    assert caught.value.status == live.PROVIDER_UNAVAILABLE


def test_same_complete_input_has_deterministic_fingerprint_and_bytes():
    first = _acquire()
    second = _acquire()

    assert first.generation_input_manifest.input_fingerprint == second.generation_input_manifest.input_fingerprint
    assert first.generation_fingerprint == second.generation_fingerprint
    assert first.to_bytes() == second.to_bytes()
    assert json.loads(first.to_bytes()) == json.loads(second.to_bytes())


def test_official_roster_evidence_is_part_of_input_identity():
    first = _acquire()
    changed_roster = FakeAkShare(
        official_roster={
            "主板A股": [{"证券代码": SYMBOL, "上市日期": "2001-08-24"}],
            "科创板": [{"证券代码": "688001", "上市日期": "2020-07-22"}],
            "A股列表": [{"A股代码": "000001", "A股上市日期": "1991-04-03"}],
        }
    )
    changed = _acquire(akshare_module=changed_roster)

    assert first.provenance["universe_roster_quality"]["content_sha256"] != changed.provenance[
        "universe_roster_quality"
    ]["content_sha256"]
    assert first.generation_input_manifest.input_fingerprint != changed.generation_input_manifest.input_fingerprint
    assert first.generation_fingerprint != changed.generation_fingerprint


def test_package_rejects_provenance_that_cannot_support_formal_audit():
    package = _acquire()
    bad_provenance = dict(package.provenance)
    bad_provenance.pop("contract")

    with pytest.raises(live.LiveAcquisitionError) as caught:
        live.LiveInputPackage(
            package.generation_input_manifest,
            package.display_names,
            package.market_env,
            bad_provenance,
        )

    assert caught.value.status == live.PROVIDER_FAILURE


def test_different_input_identity_does_not_share_generation_identity():
    first = _acquire()
    changed = _acquire(hithink_client=FakeHiThink(bars=[row[:-1] + [101] for row in _bars()]))

    assert first.generation_fingerprint != changed.generation_fingerprint
    assert first.generation_input_manifest.input_fingerprint != changed.generation_input_manifest.input_fingerprint


def test_same_identity_is_immutable_and_different_file_content_cannot_overwrite(tmp_path):
    package = _acquire()
    persisted = live.persist_live_input_package(package, tmp_path)
    assert persisted.status == "PERSISTED"
    assert persisted.file_sha256 == live._sha256_bytes(persisted.path.read_bytes())

    persisted.path.write_bytes(b"tampered")
    with pytest.raises(live.LiveAcquisitionError) as caught:
        live.persist_live_input_package(package, tmp_path)

    assert caught.value.status == live.PERSISTENCE_CONFLICT


def test_no_formal_output_is_created_when_manifest_is_incomplete(tmp_path):
    with pytest.raises(live.LiveAcquisitionError):
        _acquire(hithink_client=FakeHiThink(universe=[]))

    assert list(tmp_path.rglob("*.json")) == []
