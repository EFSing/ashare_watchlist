from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace

import pytest

import live_acquisition as live
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
    def __init__(self, *, universe=None, bars=None, failures=None):
        self._universe = universe
        self._bars = bars
        self._failures = {key: list(values) for key, values in (failures or {}).items()}
        self.universe_calls = 0
        self.kline_calls = []

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
        del start, end, timeout
        self.kline_calls.append((thscode, index))
        self._maybe_fail("index" if index else "stock")
        bars = self._bars if self._bars is not None else _bars()
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


def _quote_line(quote_date: str = AS_OF) -> str:
    return (
        'v_sh600519="1~测试股份~600519~123.45~120.00~121.00~10000~1000000~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~'
        f'{quote_date.replace("-", "")}153000~0~2.88~125.00~119.50~0~0~0~4.56~0~0~0~0~0~0~0~0~0~0~1.78";'
    )


def _request_get(*, quote_date: str = AS_OF, bars=None, calls=None):
    bars = _bars() if bars is None else bars

    def request_get(url, timeout):
        del timeout
        if calls is not None:
            calls.append(url)
        if url.startswith("https://qt.gtimg.cn"):
            return FakeResponse(text=_quote_line(quote_date))
        provider_symbol = url.split("param=", 1)[1].split(",", 1)[0]
        return FakeResponse({"data": {provider_symbol: {"qfqday": bars}}})

    return request_get


def _calendar(holidays=None):
    return TradingCalendar(holidays=set(holidays or ()), session_close_time=time(15, 0))


def _acquire(*, now_bjt=NOW, akshare_module=None, hithink_client=None, request_get=None, calendar=None, **kwargs):
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
        stock_bar_count=21,
        index_bar_count=21,
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


def test_hithink_stock_failure_is_fail_closed_when_fallback_is_disabled():
    with pytest.raises(live.LiveAcquisitionError) as caught:
        _acquire(
            hithink_client=FakeHiThink(failures={"stock": [ConnectionError("down")]}),
            allow_tencent_fallback=False,
        )

    assert caught.value.status == live.PROVIDER_FAILURE


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


def test_missing_or_stale_t_kline_fails_closed():
    with pytest.raises(live.LiveAcquisitionError) as caught:
        _acquire(hithink_client=FakeHiThink(bars=_bars(last_date="2026-08-26")))

    assert caught.value.status == INPUT_DATE_MISMATCH


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
