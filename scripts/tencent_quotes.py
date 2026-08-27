"""唯一的腾讯行情快照解析与完整性校验模块."""

from __future__ import annotations

import math
import re
import time
from datetime import date, datetime
from typing import Any, Callable, Iterable

import requests


QUOTE_URL = "https://qt.gtimg.cn/q="
QUOTE_FIELD_INDEX = {
    "price": 3,
    "prev_close": 4,
    "open": 5,
    "chg_pct": 32,
    "high": 33,
    "low": 34,
    "turnover": 38,
    "vol_ratio": 49,
}
_RE_SYMBOL = re.compile(r"^(sh|sz|bj)(\d{6})$")
_RE_CODE = re.compile(r"^\d{6}$")


class QuoteDataError(RuntimeError):
    """Base class for quote transport, parsing, and freshness failures."""


class QuoteFieldError(QuoteDataError):
    """A required Tencent field is missing, malformed, or inconsistent."""


class QuoteParseError(QuoteDataError):
    """The response could not be parsed as a Tencent snapshot."""


class QuoteRequestError(QuoteDataError):
    """The quote endpoint could not be reached after retries."""


class MissingQuoteError(QuoteDataError):
    """A requested symbol is absent from the response."""


class StaleQuoteError(QuoteDataError):
    """A quote belongs to a different trading date than requested."""


def _code_only(code_or_symbol: str) -> str:
    value = str(code_or_symbol).strip().lower()
    if _RE_CODE.fullmatch(value):
        return value
    match = _RE_SYMBOL.fullmatch(value)
    if match:
        return match.group(2)
    raise ValueError(f"invalid A-share code/symbol: {code_or_symbol!r}")


def to_symbol(code_or_symbol: str) -> str:
    """Convert a six-digit A-share code to Tencent's market-prefixed symbol."""

    value = str(code_or_symbol).strip().lower()
    if _RE_SYMBOL.fullmatch(value):
        return value
    code = _code_only(value)
    if code.startswith(("6", "9", "5")):
        return "sh" + code
    if code.startswith(("0", "1", "2", "3")):
        return "sz" + code
    if code.startswith(("4", "8")):
        return "bj" + code
    raise ValueError(f"unsupported A-share market code: {code}")


def _number(fields: list[str], index: int, field: str, code: str) -> float:
    try:
        raw = fields[index].strip()
    except IndexError as exc:
        raise QuoteFieldError(f"{code}: missing Tencent field p[{index}] ({field})") from exc
    if not raw:
        raise QuoteFieldError(f"{code}: empty Tencent field p[{index}] ({field})")
    try:
        value = float(raw)
    except ValueError as exc:
        raise QuoteFieldError(f"{code}: invalid Tencent field p[{index}] ({field})={raw!r}") from exc
    if not math.isfinite(value):
        raise QuoteFieldError(f"{code}: non-finite Tencent field p[{index}] ({field})")
    return value


def parse_quote_line(line: str) -> dict[str, Any]:
    """Parse one ``v_sh600519=\"...~...\"`` line using canonical indexes."""

    source = line.strip().rstrip(";")
    if "=" not in source:
        raise QuoteParseError(f"invalid Tencent quote line without '=': {line!r}")
    lhs, rhs = source.split("=", 1)
    symbol = lhs.strip().replace("v_", "", 1).lower()
    match = _RE_SYMBOL.fullmatch(symbol)
    if not match:
        raise QuoteParseError(f"invalid Tencent quote symbol: {symbol!r}")
    body = rhs.strip()
    if len(body) < 2 or not (body.startswith('"') and body.endswith('"')):
        raise QuoteParseError(f"invalid Tencent quote body for {symbol}")
    fields = body[1:-1].split("~")
    if len(fields) < 50:
        raise QuoteParseError(f"{symbol}: Tencent field count {len(fields)} < 50")

    code = fields[2].strip()
    if not _RE_CODE.fullmatch(code) or code != match.group(2):
        raise QuoteFieldError(f"{symbol}: code field p[2] does not match symbol")
    name = fields[1].strip()
    if not name:
        raise QuoteFieldError(f"{code}: empty name field p[1]")
    timestamp = fields[30].strip()
    if not re.fullmatch(r"\d{14}", timestamp):
        raise QuoteFieldError(f"{code}: invalid timestamp field p[30]={timestamp!r}")
    try:
        quote_date = datetime.strptime(timestamp[:8], "%Y%m%d").date().isoformat()
    except ValueError as exc:
        raise QuoteFieldError(f"{code}: invalid quote date in p[30]={timestamp!r}") from exc

    quote = {
        "code": code,
        "symbol": symbol,
        "name": name,
        "price": _number(fields, QUOTE_FIELD_INDEX["price"], "price", code),
        "prev_close": _number(fields, QUOTE_FIELD_INDEX["prev_close"], "prev_close", code),
        "open": _number(fields, QUOTE_FIELD_INDEX["open"], "open", code),
        "chg_pct": _number(fields, QUOTE_FIELD_INDEX["chg_pct"], "chg_pct", code),
        "high": _number(fields, QUOTE_FIELD_INDEX["high"], "high", code),
        "low": _number(fields, QUOTE_FIELD_INDEX["low"], "low", code),
        "turnover": _number(fields, QUOTE_FIELD_INDEX["turnover"], "turnover", code),
        "vol_ratio": _number(fields, QUOTE_FIELD_INDEX["vol_ratio"], "vol_ratio", code),
        "volume": _number(fields, 6, "volume", code),
        "timestamp": timestamp,
        "quote_date": quote_date,
    }
    validate_quote(quote)
    return quote


def validate_quote(quote: dict[str, Any]) -> None:
    code = str(quote.get("code", "?"))
    required = (
        "price",
        "prev_close",
        "open",
        "chg_pct",
        "high",
        "low",
        "turnover",
        "vol_ratio",
        "quote_date",
    )
    for field in required:
        if field not in quote:
            raise QuoteFieldError(f"{code}: missing canonical quote field {field}")
        value = quote[field]
        if field != "quote_date" and (isinstance(value, bool) or not isinstance(value, (int, float))):
            raise QuoteFieldError(f"{code}: canonical quote field {field} is not numeric")
        if field != "quote_date" and not math.isfinite(float(value)):
            raise QuoteFieldError(f"{code}: canonical quote field {field} is non-finite")
    if not _RE_CODE.fullmatch(code):
        raise QuoteFieldError(f"invalid quote code: {code!r}")
    if not isinstance(quote["quote_date"], str):
        raise QuoteFieldError(f"{code}: invalid quote_date {quote['quote_date']!r}")
    try:
        parsed_date = datetime.strptime(quote["quote_date"], "%Y-%m-%d").date()
    except ValueError as exc:
        raise QuoteFieldError(f"{code}: invalid quote_date {quote['quote_date']!r}") from exc
    if parsed_date.isoformat() != quote["quote_date"]:
        raise QuoteFieldError(f"{code}: non-canonical quote_date {quote['quote_date']!r}")
    if quote["price"] <= 0 or quote["prev_close"] <= 0 or quote["open"] <= 0:
        raise QuoteFieldError(f"{code}: price/prev_close/open must be positive")
    if quote["high"] <= 0 or quote["low"] <= 0 or quote["high"] < quote["low"]:
        raise QuoteFieldError(f"{code}: high/low fields are inconsistent")
    if quote["turnover"] < 0 or quote["vol_ratio"] < 0:
        raise QuoteFieldError(f"{code}: turnover/vol_ratio must be non-negative")


def _date_text(value: date | datetime | str) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip().replace("/", "-")
    if len(text) == 8 and text.isdigit():
        return datetime.strptime(text, "%Y%m%d").date().isoformat()
    return datetime.strptime(text, "%Y-%m-%d").date().isoformat()


def parse_quote_response(
    text: str,
    expected_codes: Iterable[str] | None = None,
    expected_date: date | datetime | str | None = None,
) -> dict[str, dict[str, Any]]:
    """Parse and validate a full response; malformed requested data is fatal."""

    if not isinstance(text, str) or not text.strip():
        raise QuoteParseError("empty Tencent quote response")
    quotes: dict[str, dict[str, Any]] = {}
    errors: list[QuoteDataError] = []
    for line in text.replace("\r", "").replace("\n", ";").split(";"):
        if not line.strip():
            continue
        if "=" not in line or "~" not in line:
            continue
        try:
            quote = parse_quote_line(line)
        except QuoteDataError as exc:
            errors.append(exc)
            continue
        quotes[quote["code"]] = quote
    if errors:
        raise errors[0]
    validate_quotes(quotes, expected_codes=expected_codes, expected_date=expected_date)
    return quotes


def validate_quotes(
    quotes: dict[str, dict[str, Any]],
    expected_codes: Iterable[str] | None = None,
    expected_date: date | datetime | str | None = None,
) -> None:
    expected = [_code_only(code) for code in (expected_codes or [])]
    missing = sorted(set(expected) - set(quotes))
    if missing:
        raise MissingQuoteError(f"missing Tencent quotes for: {', '.join(missing)}")
    expected_date_text = _date_text(expected_date) if expected_date is not None else None
    for code, quote in quotes.items():
        if not isinstance(quote, dict) or str(quote.get("code")) != code:
            raise QuoteFieldError(f"quote map key {code!r} does not match quote code")
        validate_quote(quote)
        if expected_date_text is not None and quote["quote_date"] != expected_date_text:
            raise StaleQuoteError(
                f"stale Tencent quote for {code}: {quote['quote_date']} != {expected_date_text}"
            )


def fetch_quotes(
    codes: Iterable[str],
    expected_date: date | datetime | str | None = None,
    timeout: float = 15,
    retries: int = 3,
    request_get: Callable[..., Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Fetch complete quote batches or raise a concrete data-integrity error."""

    normalized = [_code_only(code) for code in codes]
    if not normalized:
        return {}
    get = request_get or requests.get
    all_quotes: dict[str, dict[str, Any]] = {}
    for start in range(0, len(normalized), 50):
        batch = normalized[start:start + 50]
        url = QUOTE_URL + ",".join(to_symbol(code) for code in batch)
        last_error: Exception | None = None
        for attempt in range(retries):
            try:
                response = get(url, timeout=timeout)
                response.encoding = "gbk"
                all_quotes.update(
                    parse_quote_response(
                        response.text,
                        expected_codes=batch,
                        expected_date=expected_date,
                    )
                )
                last_error = None
                break
            except QuoteDataError:
                raise
            except Exception as exc:  # request transport errors only
                last_error = exc
                if attempt + 1 < retries:
                    time.sleep(attempt + 1)
        if last_error is not None:
            raise QuoteRequestError(f"Tencent quote request failed after {retries} attempts: {last_error}") from last_error
    validate_quotes(all_quotes, expected_codes=normalized, expected_date=expected_date)
    return all_quotes
