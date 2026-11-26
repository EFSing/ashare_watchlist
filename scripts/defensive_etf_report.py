"""Read-only, T-known inputs for the daily defensive ETF reference card."""

from __future__ import annotations

import math
import os
from datetime import date, datetime, timedelta, timezone
from statistics import mean

import requests

from generation_contract import next_execution_date
from live_acquisition import HITHINK_API_KEY_ENV, HITHINK_BASE_URL
from preview_b_shortlist import build_market_gate
from trading_calendar import previous_trading_day


ETFS = (("511260.SH", "十年国债 ETF"), ("518880.SH", "黄金 ETF"))
TENCENT_KLINES = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
HITHINK_DIVIDENDS = f"{HITHINK_BASE_URL}/api/fund/corporate-actions/dividends"
_BJT = timezone(timedelta(hours=8))


def _provider_data(url, params, *, headers=None):
    response = requests.get(url, params=params, headers=headers, timeout=5, allow_redirects=False)
    response.raise_for_status()
    payload = response.json()
    if response.status_code != 200 or type(payload["code"]) is not int or payload["code"] != 0:
        raise ValueError("ETF provider response failed")
    return payload["data"]


def _day(value):
    if type(value) is int:
        return datetime.fromtimestamp(value / 1000, _BJT).date().isoformat()
    if date.fromisoformat(value).isoformat() != value:
        raise ValueError("invalid ETF provider date")
    return value


def _positive(value):
    if isinstance(value, bool):
        raise ValueError("invalid ETF numeric field")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError("invalid ETF numeric field")
    return number


def _etf_trend(price_rows, dividend_rows, sessions):
    """Use only the expected sessions and implemented ex-dates through T."""
    start, target = sessions[0], sessions[-1]
    if not isinstance(price_rows, list) or not isinstance(dividend_rows, list):
        raise ValueError("missing ETF price or dividend series")
    closes, dividends = {}, {}
    for row in price_rows:
        day = _day(row[0])
        if not start <= day <= target:
            continue
        if day in closes:
            raise ValueError("duplicate ETF close")
        closes[day] = _positive(row[2])
    if sorted(closes) != sessions:
        raise ValueError("ETF closes do not match the XSHG sessions through T")
    for row in dividend_rows:
        if all(value in (None, "") for value in row.values()):
            continue
        ex_date = row.get("ex_dividend_date_ms") or row.get("ex_dividend_date")
        if row.get("progress") not in (None, "", "实施"):
            continue
        day = _day(ex_date)
        if not start < day <= target:
            continue
        if row.get("progress") != "实施":
            raise ValueError("ETF dividend implementation status is missing")
        if day not in closes or day in dividends:
            raise ValueError("invalid or duplicate ETF ex-date")
        dividends[day] = _positive(row["per_ten_cash_before_tax"]) / 10
    adjusted = [
        _positive(closes[day] - sum(cash for ex_date, cash in dividends.items() if day < ex_date))
        for day in sessions[-20:]
    ]
    close, ma20 = adjusted[-1], mean(adjusted)
    return close, ma20, close > ma20


def _load_etfs(sessions, calendar):
    target = sessions[-1]
    now = datetime.now(_BJT)
    if now.date().isoformat() != target or now < calendar.session_close(target):
        raise ValueError("ETF references require the current session after close")
    key = os.environ[HITHINK_API_KEY_ENV].strip()
    if not key:
        raise ValueError("missing ETF dividend credentials")
    results = []
    for symbol, name in ETFS:
        ticker = "sh" + symbol[:6]
        prices = _provider_data(TENCENT_KLINES, {
            "param": f"{ticker},day,{sessions[0]},{target},25,",
        })[ticker]["day"]
        dividends = _provider_data(
            HITHINK_DIVIDENDS, {"thscode": symbol}, headers={"X-api-key": key},
        )["item"]
        close, ma20, above = _etf_trend(prices, dividends, sessions)
        results.append(dict(symbol=symbol, name=name, close=close, ma20=ma20, above=above,
                            weight=50 if above else 0))
    return results


def build_defensive_etf_card(watchlist, index, calendar):
    """Return display data only; a failure in any optional input degrades the card."""
    try:
        target = watchlist["date"]
        bars = index["bars"]
        current = build_market_gate(watchlist, index)
        if current["status"] == "UNAVAILABLE" or len(bars) < 27:
            return None
        # Three G2 evaluations need 27 bars. The fourth resolves today's
        # first activation or whether yesterday had already activated R1.
        sessions = [target]
        for _ in range(min(len(bars), 28) - 1):
            previous = previous_trading_day(sessions[-1], calendar)
            sessions.append(datetime.strptime(previous, "%Y%m%d").date().isoformat())
        sessions.reverse()
        if [bar["date"] for bar in bars[-len(sessions):]] != sessions:
            return None
        previous_g2 = [
            build_market_gate({**watchlist, "date": sessions[-1 - offset]}, {
                "symbol": index["symbol"], "bars": bars[-25 - offset:-offset],
            })["g2_pass"]
            for offset in range(1, len(sessions) - 24)
        ]
        if any(previous_g2[:2]):
            if current["g2_pass"]:
                return {"status": "G2"}
            return {"status": "BUFFER", "days": previous_g2.index(True) + 1}
        if len(previous_g2) < 3:
            return None
        if current["g2_pass"]:
            return {"status": "G2" if previous_g2[2] else "RECOVERY"}
        if previous_g2[2]:
            schedule = "FIRST"
        else:
            next_day = date.fromisoformat(next_execution_date(target, calendar))
            target_week = date.fromisoformat(target).isocalendar()[:2]
            schedule = "WEEKLY" if next_day.isocalendar()[:2] != target_week else "DAILY"
        etfs = _load_etfs(sessions[-25:], calendar)
        return {"status": "ACTIVE", "schedule": schedule, "etfs": etfs,
                "cash": 100 - sum(etf["weight"] for etf in etfs)}
    except Exception:
        # This reference must never block the formal report or its delivery.
        return None
