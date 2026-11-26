"""Acquire and validate the three bounded ETF input series for the preregistration."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

import exchange_calendars


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/validation/defensive_etf_non_g2_v1/raw"
START = "2022-06-01"
FIRST_SIGNAL = "2023-06-30"
CUTOFF = "2026-08-28"
SYMBOLS = ("511260.SH", "518880.SH", "512890.SH")
SHANGHAI = timezone(timedelta(hours=8))
TENCENT = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
HITHINK = "https://fuyao.aicubes.cn/api/fund"
NAV_TOLERANCE = 0.005


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_json(endpoint, params, label, key=None):
    request = Request(
        f"{endpoint}?{urlencode(params)}",
        headers={"X-api-key": key} if key else {},
    )
    try:
        with build_opener(NoRedirect()).open(request, timeout=30) as response:
            payload = json.load(response)
    except HTTPError as error:
        raise ValueError(f"{label}: HTTP {error.code}") from None
    except (URLError, TimeoutError, OSError, ValueError) as error:
        raise ValueError(f"{label}: {type(error).__name__}") from None
    code = payload.get("code") if isinstance(payload, dict) else None
    if type(code) is not int or code != 0:
        raise ValueError(f"{label}: provider code {code if type(code) is int else 'invalid'}")
    return payload.get("data")


def day(value):
    if type(value) is int:
        return datetime.fromtimestamp(value / 1000, SHANGHAI).date().isoformat()
    try:
        if isinstance(value, str) and date.fromisoformat(value).isoformat() == value:
            return value
    except ValueError:
        pass
    raise ValueError("invalid provider date")


def number(value, *, nonnegative=False):
    if isinstance(value, bool):
        raise ValueError("boolean numeric field")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("invalid numeric field") from None
    if not math.isfinite(result) or result < 0 or (result == 0 and not nonnegative):
        raise ValueError("invalid numeric field")
    return result


def add_row(rows, when, row):
    if when in rows and rows[when] != row:
        raise ValueError(f"conflicting duplicate on {when}")
    rows[when] = row


def sessions():
    calendar = exchange_calendars.get_calendar("XSHG")
    days = [stamp.date().isoformat() for stamp in calendar.sessions_in_range(START, CUTOFF)]
    if sum(when >= FIRST_SIGNAL for when in days) != 769:
        raise ValueError("XSHG evaluation window must contain exactly 769 sessions")
    return days


def fetch_prices(symbol):
    ticker = "sh" + symbol[:6]
    rows = {}
    for year in range(2022, 2027):
        start = max(START, f"{year}-01-01")
        end = min(CUTOFF, f"{year}-12-31")
        label = f"{symbol} Tencent unadjusted {year}"
        data = request_json(TENCENT, {"param": f"{ticker},day,{start},{end},640,"}, label)
        if not isinstance(data, dict) or not isinstance(data.get(ticker), dict):
            raise ValueError(f"{label}: missing symbol envelope")
        values = data[ticker].get("day")
        if not isinstance(values, list) or not values:
            raise ValueError(f"{label}: missing unadjusted day series")
        for value in values:
            when = day(value[0])
            if not START <= when <= CUTOFF:
                continue
            opening, close, high, low = map(number, value[1:5])
            if not low <= min(opening, close) <= max(opening, close) <= high:
                raise ValueError(f"{label}: invalid OHLC on {when}")
            volume = number(value[5], nonnegative=True)
            add_row(rows, when, {"date": when, "open": opening, "high": high, "low": low,
                                "close": close, "volume": volume})
    return [rows[when] for when in sorted(rows)]


def fund_items(symbol, key, endpoint, params):
    label = f"{symbol} HiThink {endpoint}"
    data = request_json(f"{HITHINK}/{endpoint}", {"thscode": symbol, **params}, label, key)
    items = data.get("item") if isinstance(data, dict) else None
    if not isinstance(items, list) or any(not isinstance(row, dict) for row in items):
        raise ValueError(f"{label}: invalid item list")
    return items


def fetch_dividends(symbol, key):
    rows = {}
    for item in fund_items(symbol, key, "corporate-actions/dividends", {}):
        value = item.get("ex_dividend_date_ms", item.get("ex_dividend_date"))
        if value in (None, 0, ""):
            if all(v in (None, "") for v in item.values()):
                continue  # The provider emits an empty placeholder alongside dated records.
            if item.get("progress") not in (None, "实施"):
                continue  # An undated proposal is not an executed dividend.
        when = day(value)
        if not START <= when <= CUTOFF:
            continue
        per_ten = number(item["per_ten_cash_before_tax"])
        payment = day(item["payment_date_ms"])
        if payment < when:
            raise ValueError(f"{symbol}: dividend payment precedes ex-date on {when}")
        add_row(rows, when, {"ex_dividend_date": when, "per_ten_cash_before_tax": per_ten,
                            "dividend_per_share": per_ten / 10.0,
                            "payment_date": payment if payment <= CUTOFF else None})
    return [rows[when] for when in sorted(rows)]


def fetch_nav(symbol, key):
    rows = {}
    for item in fund_items(symbol, key, "performance/nav", {"range": "fyear", "nav_type": "unit,adj"}):
        when = day(item["nav_date"])
        if not START <= when <= CUTOFF:
            continue
        add_row(rows, when, {"nav_date": when, "unit_nav": number(item["unit_nav"]),
                            "adj_nav": number(item["adj_nav"])})
    return [rows[when] for when in sorted(rows)]


def validate(prices, dividends, nav, days):
    price_dates = {row["date"] for row in prices if row["volume"] > 0}
    nav_by_day = {row["nav_date"]: row for row in nav}
    cash_by_day = {row["ex_dividend_date"]: row["dividend_per_share"] for row in dividends}
    expected = set(days)
    nav_dates = sorted(nav_by_day)
    diagnostics = {
        "evaluation_bars": sum(when in price_dates for when in days if when >= FIRST_SIGNAL),
        "warmup_bars": sum(when in price_dates for when in days if when < FIRST_SIGNAL),
        "off_calendar_bars": len({row["date"] for row in prices} - expected),
        "nav_missing_sessions": len(expected - nav_by_day.keys()),
        "nav_non_session_rows": len(nav_by_day.keys() - expected),
        "dividends": len(dividends),
        "dividends_without_nav_pair": len(cash_by_day.keys() - (set(nav_dates[1:]) & expected)),
        "dividend_nav_mismatch": 0,
        "nav_return_ratio_outside_tolerance": 0,
        "nav_return_ratio_undefined": 0,
        "nav_gross_return_ratio_outside_tolerance": 0,
        "max_nav_gross_return_ratio_gap_bps": 0.0,
    }
    for previous, current in zip(nav_dates, nav_dates[1:]):
        old = nav_by_day[previous]
        new = nav_by_day[current]
        unit_gross = new["unit_nav"] / old["unit_nav"]
        adj_gross = new["adj_nav"] / old["adj_nav"]
        if current in cash_by_day:
            dividend_gross = (new["unit_nav"] + cash_by_day[current]) / old["unit_nav"]
            diagnostics["dividend_nav_mismatch"] += abs(dividend_gross / adj_gross - 1) > NAV_TOLERANCE
            continue
        gap = abs(unit_gross / adj_gross - 1)
        diagnostics["nav_gross_return_ratio_outside_tolerance"] += gap > NAV_TOLERANCE
        diagnostics["max_nav_gross_return_ratio_gap_bps"] = max(
            diagnostics["max_nav_gross_return_ratio_gap_bps"], gap * 10_000
        )
        if adj_gross == 1:
            diagnostics["nav_return_ratio_undefined"] += 1
        else:
            diagnostics["nav_return_ratio_outside_tolerance"] += (
                abs((unit_gross - 1) / (adj_gross - 1) - 1) > NAV_TOLERANCE
            )
    diagnostics["passed"] = (
        diagnostics["evaluation_bars"] == 769 and diagnostics["warmup_bars"] >= 250
        and all(diagnostics[name] == 0 for name in (
            "off_calendar_bars", "nav_missing_sessions", "dividends_without_nav_pair",
            "dividend_nav_mismatch", "nav_gross_return_ratio_outside_tolerance",
        ))
    )
    return diagnostics


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def acquire():
    key = os.environ.get("HITHINK_FINANCE_API_KEY", "").strip()
    if not key:
        raise ValueError("HITHINK_FINANCE_API_KEY is missing")
    days = sessions()
    files = {}
    diagnostics = {}
    for symbol in SYMBOLS:
        acquired = {}
        failures = []
        for name, loader in (
            ("ohlcv", lambda: fetch_prices(symbol)),
            ("dividends", lambda: fetch_dividends(symbol, key)),
            ("nav", lambda: fetch_nav(symbol, key)),
        ):
            try:
                acquired[name] = loader()
            except ValueError as error:
                failures.append(f"{name}: {error}")
            except (KeyError, TypeError, IndexError, OverflowError):
                failures.append(f"{name}: malformed {symbol} provider record")
        if failures:
            diagnostics[symbol] = {"passed": False, "acquisition_errors": failures}
            continue
        diagnostics[symbol] = validate(acquired["ohlcv"], acquired["dividends"], acquired["nav"], days)
        for name, rows in acquired.items():
            files[f"{symbol.replace('.', '_')}_{name}.json"] = json_bytes(
                {"symbol": symbol, "rows": rows}
            )
    return files, diagnostics


def freeze(files, diagnostics):
    research_root = RAW.parent
    if research_root.resolve() != research_root or RAW.exists() or RAW.is_symlink():
        raise ValueError("raw output path is redirected or already exists")
    manifest = {
        "start": START,
        "cutoff": CUTOFF,
        "verification": diagnostics,
        "files": {name: {"bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
                  for name, value in sorted(files.items())},
    }
    RAW.mkdir(parents=True)
    for name, value in sorted(files.items()):
        (RAW / name).write_bytes(value)
    (RAW / "input_manifest.json").write_bytes(json_bytes(manifest))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        files, diagnostics = acquire()
        print(json_bytes(diagnostics).decode("utf-8"), flush=True)
        if any(not result["passed"] for result in diagnostics.values()):
            raise ValueError("ETF input verification failed; raw snapshot was not frozen")
        freeze(files, diagnostics)
    except ValueError as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
