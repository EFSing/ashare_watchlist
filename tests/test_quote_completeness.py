import pytest

from tencent_quotes import (
    MissingQuoteError,
    StaleQuoteError,
    validate_quotes,
)


def quote(**overrides):
    value = {
        "code": "600519",
        "quote_date": "2026-08-27",
        "price": 123.45,
        "prev_close": 120.0,
        "open": 121.0,
        "chg_pct": 2.88,
        "high": 125.0,
        "low": 119.5,
        "turnover": 4.56,
        "vol_ratio": 1.78,
    }
    value.update(overrides)
    return value


def test_missing_requested_symbol_is_an_error():
    with pytest.raises(MissingQuoteError):
        validate_quotes({}, expected_codes=["600519"], expected_date="2026-08-27")


def test_stale_quote_date_is_an_error():
    with pytest.raises(StaleQuoteError):
        validate_quotes(
            {"600519": quote(quote_date="2026-08-26")},
            expected_codes=["600519"],
            expected_date="2026-08-27",
        )

