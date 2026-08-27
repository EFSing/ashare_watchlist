from pathlib import Path

import pytest

from tencent_quotes import (
    QuoteFieldError,
    parse_quote_response,
)
from preopen_review import review_one


FIXTURE = Path(__file__).parent / "fixtures" / "tencent_quote_response.txt"


def test_tencent_fixture_uses_documented_field_indexes():
    quotes = parse_quote_response(FIXTURE.read_text(encoding="utf-8"))
    quote = quotes["600519"]

    assert quote["price"] == 123.45
    assert quote["prev_close"] == 120.00
    assert quote["open"] == 121.00
    assert quote["chg_pct"] == 2.88
    assert quote["high"] == 125.00
    assert quote["low"] == 119.50
    assert quote["turnover"] == 4.56
    assert quote["vol_ratio"] == 1.78


def test_tencent_parser_reports_bad_numeric_fields_instead_of_skipping():
    raw = FIXTURE.read_text(encoding="utf-8").replace("~2.88~125.00", "~not-a-number~125.00")

    with pytest.raises(QuoteFieldError):
        parse_quote_response(raw)


def test_preopen_review_consumes_canonical_prev_close_and_volume_ratio():
    quote = parse_quote_response(FIXTURE.read_text(encoding="utf-8"))["600519"]
    result = review_one(
        {
            "code": "600519",
            "name": "测试股份",
            "trigger": 120.0,
        },
        quote,
    )

    assert result["今开涨%"] == 0.83
    assert result["现价"] == 123.45
    assert result["量比"] == 1.78
