import json
from datetime import date, datetime, time, timedelta

import pytest

import defensive_etf_report as etf
from c_daily_watchlist import compose_delivery_html, render_unavailable_section
from render_daily_close_html import _defensive_etf_html, render_daily_close
from test_b_shortlist_preview import daily_inputs
from trading_calendar import TradingCalendar


def _sessions(target, count, calendar):
    day = date.fromisoformat(target)
    sessions = []
    while len(sessions) < count:
        if calendar.is_trading_day(day):
            sessions.append(day.isoformat())
        day -= timedelta(days=1)
    return list(reversed(sessions))


def _index(target, closes, calendar):
    return {"symbol": "sh000001", "bars": [
        {"date": day, "close": close}
        for day, close in zip(_sessions(target, len(closes), calendar), closes)
    ]}


def _watch(target):
    return {"date": target, "market_env": {}, "candidates": []}


@pytest.mark.parametrize(("closes", "message"), [
    (list(range(100, 127)), "防守袖套休眠（目标 0%）"),
    ([100] * 27 + [120], "次一交易日开盘先清空防守 ETF"),
    (list(range(100, 125)) + [1, 1, 500], "防守袖套休眠（目标 0%）"),
    (list(range(100, 126)) + [1], "连续第 1 日非 G2"),
    (list(range(100, 125)) + [1, 1], "连续第 2 日非 G2"),
])
def test_market_states_render_without_etf_requests(monkeypatch, closes, message):
    target = "2026-11-05"
    cal = TradingCalendar(holidays=[])
    monkeypatch.setattr(etf.requests, "get", lambda *a, **k: pytest.fail("unexpected ETF request"))
    card = etf.build_defensive_etf_card(_watch(target), _index(target, closes, cal), cal)
    assert message in _defensive_etf_html(card)


@pytest.mark.parametrize(("target", "holidays", "closes", "schedule", "gold_above", "bond_above"), [
    ("2026-11-06", [], list(range(100, 125)) + [1, 1, 1], "首次激活日", True, True),
    ("2026-11-06", [], [100] * 28, "周度调仓检查日", False, True),
    ("2026-11-05", ["2026-11-06"], [100] * 28, "周度调仓检查日", False, False),
    ("2026-11-05", [], [100] * 28, "日常持仓观察日", False, True),
])
def test_active_schedule_and_cash(monkeypatch, target, holidays, closes, schedule, gold_above, bond_above):
    cal = TradingCalendar(holidays=holidays)

    def load(sessions, calendar):
        assert sessions == _sessions(target, 25, cal)
        return [dict(symbol=symbol, name=name, close=10, ma20=9 if above else 10,
                     above=above, weight=50 if above else 0)
                for (symbol, name), above in zip(etf.ETFS, (bond_above, gold_above))]

    monkeypatch.setattr(etf, "_load_etfs", load)
    card = etf.build_defensive_etf_card(_watch(target), _index(target, closes, cal), cal)
    html = _defensive_etf_html(card)
    assert schedule in html
    assert f'现金留白 <strong>{100 - 50 * (gold_above + bond_above)}%</strong>' in html
    assert all(symbol in html for symbol, _ in etf.ETFS)
    assert "真实空闲现金槽位，不加杠杆" in html
    if "周度" in schedule:
        assert "总账户权益的 10%" in html and "次日开盘调仓" in html


def test_index_rejects_future_and_gap_and_requires_t_minus_three_when_ambiguous(monkeypatch):
    target = "2026-11-05"
    cal = TradingCalendar(holidays=[])
    monkeypatch.setattr(etf, "_load_etfs", lambda *a: pytest.fail("unverified index"))
    index = _index(target, [100] * 28, cal)
    index["bars"].append({"date": "2026-11-06", "close": 1000})
    assert etf.build_defensive_etf_card(_watch(target), index, cal) is None
    index["bars"].pop()
    del index["bars"][-7]
    assert etf.build_defensive_etf_card(_watch(target), index, cal) is None
    assert etf.build_defensive_etf_card(_watch(target), _index(target, [100] * 27, cal), cal) is None


def test_cash_dividends_use_only_the_through_t_implemented_ex_dates():
    dates = _sessions("2026-11-05", 25, TradingCalendar(holidays=[]))
    prices = [[day, "0", "10" if day < dates[-5] else "9.7"] for day in dates]
    dividends = [
        {"progress": "实施", "ex_dividend_date_ms": int(
            datetime.fromisoformat(dates[-5] + "T00:00:00+08:00").timestamp() * 1000
        ), "per_ten_cash_before_tax": "4"},
        {"progress": "实施", "ex_dividend_date": dates[-1], "per_ten_cash_before_tax": "1"},
        {"progress": "预案", "ex_dividend_date": dates[-2], "per_ten_cash_before_tax": "100"},
        {"progress": "实施", "ex_dividend_date": "2026-11-06", "per_ten_cash_before_tax": "100"},
    ]
    future = ["2026-11-06", "0", "125"]
    close, ma20, above = etf._etf_trend(prices + [future], dividends, dates)
    assert close == 9.7
    assert ma20 == pytest.approx((15 * 9.5 + 4 * 9.6 + 9.7) / 20)
    assert above is True
    with pytest.raises(ValueError, match="XSHG sessions through T"):
        etf._etf_trend(prices[:-1] + [future], dividends, dates)
    with pytest.raises(ValueError, match="dividend implementation"):
        etf._etf_trend(prices, [{"ex_dividend_date": dates[-1], "per_ten_cash_before_tax": "1"}], dates)


@pytest.mark.parametrize("failure", [None, "timeout", "missing-dividends", "stale-quote", "preclose"])
def test_optional_etf_data_through_formal_html_and_bc_composition(daily_inputs, monkeypatch, failure):
    day, cal, paths, watch_path, run_path = daily_inputs
    run = json.loads(run_path.read_bytes())
    run["input_manifest"]["index"] = _index(day, [100] * 28, cal)
    run_path.write_text(json.dumps(run), encoding="utf-8")
    original_watchlist = watch_path.read_bytes()
    dates = _sessions(day, 25, cal)
    calls = []

    class Clock(datetime):
        @classmethod
        def now(cls, tz):
            return cls.combine(date.fromisoformat(day), time(14 if failure == "preclose" else 17), tz)

    class Response:
        status_code = 200

        def __init__(self, data):
            self.data = data

        def raise_for_status(self):
            pass

        def json(self):
            return {"code": 0, "data": self.data}

    def get(url, *, params, headers, timeout, allow_redirects):
        assert timeout == 5 and not allow_redirects
        calls.append(url)
        if url == etf.HITHINK_DIVIDENDS:
            assert headers == {"X-api-key": "fixture"}
            assert params in ({"thscode": "511260.SH"}, {"thscode": "518880.SH"})
            if failure == "timeout":
                raise etf.requests.Timeout()
            return Response({} if failure == "missing-dividends" else {"item": []})
        assert url == etf.TENCENT_KLINES and headers is None
        ticker = params["param"].split(",")[0]
        assert ticker in ("sh511260", "sh518880")
        assert params["param"] == f"{ticker},day,{dates[0]},{day},25,"
        rows = [[session, "10", "10"] for session in dates]
        rows[-1][2] = "11" if ticker == "sh511260" else "9"
        return Response({ticker: {"day": rows[:-1] if failure == "stale-quote" else rows}})

    monkeypatch.setenv(etf.HITHINK_API_KEY_ENV, "fixture")
    monkeypatch.setattr(etf, "datetime", Clock)
    monkeypatch.setattr(etf.requests, "get", get)
    model, dated, latest = render_daily_close(day, paths=paths, calendar=cal, research_run_manifest=run_path)
    formal = dated.read_bytes()
    assert formal == latest.read_bytes() and watch_path.read_bytes() == original_watchlist
    composite = compose_delivery_html(formal, render_unavailable_section(day, "C_FAILED")).decode("utf-8")
    assert "G2 轮空防守承接参考卡（R1/A1）" in composite
    assert "今日复盘" in composite and "C_FAILED" in composite
    assert "其余候选 · 5" in composite and model.metadata["candidate_count"] == 5
    if failure:
        assert model.defensive_etf is None
        assert "防守 ETF 行情待核验，今日不生成配比建议" in composite
        assert "今日 A1 参考配比" not in composite
        assert len(calls) == (0 if failure == "preclose" else 2)
    else:
        assert model.defensive_etf["cash"] == 50
        assert "511260.SH 十年国债 ETF" in composite and "518880.SH 黄金 ETF" in composite
        assert len(calls) == 4
