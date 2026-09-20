"""Provider-neutral market-data primitives used by production consumers.

The production pipeline deliberately keeps this module smaller than any
provider adapter.  It describes only the quote fields needed to establish a
trade state and to feed the existing close/tracker contracts.  Provider
specific schemas must be normalized before reaching these helpers.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


TRADE_STATE_TRADED = "TRADED"
TRADE_STATE_NO_TRADE = "NO_TRADE"
TRADE_STATE_UNKNOWN = "UNKNOWN"

QUOTE_CORE_FIELDS = (
    "price",
    "prev_close",
    "open",
    "high",
    "low",
    "volume",
)


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def classify_trade_state(quote: Mapping[str, Any]) -> str:
    """Classify a normalized quote without inferring from missing values.

    A complete explicit zero-volume shape is the only ordinary no-trade
    evidence accepted here.  An all-null or partially populated provider row
    remains ``UNKNOWN``; it is never silently treated as suspension.
    """

    if not isinstance(quote, Mapping):
        return TRADE_STATE_UNKNOWN

    explicit_state = quote.get("trade_state")
    if explicit_state in {TRADE_STATE_TRADED, TRADE_STATE_NO_TRADE}:
        return str(explicit_state)

    values = {field: _finite_number(quote.get(field)) for field in QUOTE_CORE_FIELDS}
    if any(values[field] is None for field in ("price", "prev_close")):
        return TRADE_STATE_UNKNOWN

    price = values["price"]
    prev_close = values["prev_close"]
    assert price is not None and prev_close is not None

    # This is an explicit provider row, not a missing/null row.  Optional
    # turnover and volume-ratio fields are intentionally not required.
    if (
        price > 0
        and price == prev_close
        and all(values[field] == 0 for field in ("open", "high", "low", "volume"))
    ):
        return TRADE_STATE_NO_TRADE

    if any(values[field] is None for field in ("open", "high", "low", "volume")):
        return TRADE_STATE_UNKNOWN
    opening = values["open"]
    high = values["high"]
    low = values["low"]
    volume = values["volume"]
    assert opening is not None and high is not None and low is not None and volume is not None
    if (
        price <= 0
        or prev_close <= 0
        or opening <= 0
        or high <= 0
        or low <= 0
        or volume <= 0
        or high < low
        or high < opening
        or high < price
        or low > opening
        or low > price
    ):
        return TRADE_STATE_UNKNOWN
    return TRADE_STATE_TRADED


def is_no_trade_snapshot(quote: Mapping[str, Any]) -> bool:
    """Return whether a normalized quote has explicit no-trade evidence."""

    return classify_trade_state(quote) == TRADE_STATE_NO_TRADE


def is_traded_snapshot(quote: Mapping[str, Any]) -> bool:
    """Return whether a normalized quote has a structurally valid trade row."""

    return classify_trade_state(quote) == TRADE_STATE_TRADED


__all__ = [
    "QUOTE_CORE_FIELDS",
    "TRADE_STATE_NO_TRADE",
    "TRADE_STATE_TRADED",
    "TRADE_STATE_UNKNOWN",
    "classify_trade_state",
    "is_no_trade_snapshot",
    "is_traded_snapshot",
]
