from pathlib import Path
from types import SimpleNamespace

import pytest

from tencent_quotes import (
    QuoteFieldError,
    fetch_quotes,
    parse_quote_response,
)
from preopen_review import review_one


FIXTURE = Path(__file__).parent / "fixtures" / "tencent_quote_response.txt"

REAL_NO_TRADE_FIXTURE = (
    'v_sz002731="51~*ST\u8403\u534e~002731~0.77~0.77~0.00~0~0~0~0.00~0~0.00~0~0.00~0~0.00~0~0.00~0~0.00~0~0.00~0~0.00~0~0.00~0~0.00~0~~20260902161439~0.00~0.00~0.00~0.00~0.77/0/0~0~0~0.00~0.72~S~0.00~0.00~0.00~1.77~1.97~0.11~0.85~0.69~0.00~0~0.00~0.85~0.91~~~0.46~0.0000~0.0000~0~   A~GP-A~-93.87~-25.96~0.00~14.64~4.35~17.28~0.77~-46.15~-61.31~-82.30~229656400~256156000~~-94.32~229656400~~~-94.48~0.00~~CNY~0~AE~0.00~0~";'
)


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


def test_tencent_field_failure_keeps_requested_and_provider_batches():
    raw = FIXTURE.read_text(encoding="utf-8").replace("~2.88~125.00", "~not-a-number~125.00")

    def request_get(url, timeout):
        del url, timeout
        return SimpleNamespace(text=raw, encoding=None)

    with pytest.raises(QuoteFieldError) as caught:
        fetch_quotes(["600519", "600520"], request_get=request_get)

    assert str(caught.value) == (
        "600519: invalid Tencent field p[32] (chg_pct)='not-a-number'; "
        "failure_batch=600519,600520; tencent_batch=sh600519,sh600520"
    )


def test_tencent_accepts_real_no_trade_provider_snapshot():
    quotes = parse_quote_response(
        REAL_NO_TRADE_FIXTURE,
        expected_codes=["002731"],
        expected_date="2026-09-02",
    )
    quote = quotes["002731"]

    assert quote["price"] == 0.77
    assert quote["prev_close"] == 0.77
    assert quote["open"] == 0.0
    assert quote["volume"] == 0.0
    assert quote["high"] == 0.0
    assert quote["low"] == 0.0
    assert quote["turnover"] == 0.0
    assert quote["vol_ratio"] == 0.0


def test_tencent_no_trade_acceptance_requires_complete_zero_trade_pattern():
    raw = REAL_NO_TRADE_FIXTURE.replace(
        "~0.77~0.77~0.00~0~0~0~0.00",
        "~0.77~0.77~0.00~1~0~0~0.00",
        1,
    )

    with pytest.raises(QuoteFieldError) as caught:
        parse_quote_response(raw, expected_codes=["002731"], expected_date="2026-09-02")

    assert "002731: price/prev_close/open must be positive" in str(caught.value)


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
