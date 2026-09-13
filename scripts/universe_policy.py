"""Canonical production universe policy and A-share board taxonomy."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


UNIVERSE_POLICY_MAIN_BOARD_ONLY_V1 = "ASHARE_MAIN_BOARD_ONLY_V1"
BOARD_TAXONOMY_VERSION = "ASHARE_BOARD_TAXONOMY_V1"

BOARD_MAIN = "Main"
BOARD_CHINEXT = "ChiNext"
BOARD_STAR = "STAR"
BOARD_UNKNOWN = "Unknown"


def _canonical_code(value: Any) -> str | None:
    text = str(value).strip().upper()
    if text.endswith((".SH", ".SZ", ".BJ")):
        text = text[:-3]
    if text.startswith(("SH", "SZ", "BJ")):
        text = text[2:]
    return text if len(text) == 6 and text.isdigit() else None


def classify_board(symbol: Any) -> str:
    """Return the project's canonical board taxonomy for one A-share code."""

    code = _canonical_code(symbol)
    if code is None:
        return BOARD_UNKNOWN
    # Check the specialized boards before the broad 60/00 main-board ranges.
    if code.startswith("68"):
        return BOARD_STAR
    if code.startswith("30"):
        return BOARD_CHINEXT
    if code.startswith(("00", "60")):
        return BOARD_MAIN
    return BOARD_UNKNOWN


def is_live_universe_eligible(symbol: Any) -> bool:
    """Return whether a symbol is admitted by the production policy."""

    return classify_board(symbol) == BOARD_MAIN


def universe_policy_metadata() -> dict[str, Any]:
    """Return the immutable semantic metadata for the production policy."""

    return {
        "name": UNIVERSE_POLICY_MAIN_BOARD_ONLY_V1,
        "display_name": "Main Board Only",
        "display_name_zh": "沪深主板",
        "base_universe": "existing eligible universe",
        "allowed_boards": [BOARD_MAIN],
        "excluded_boards": [BOARD_CHINEXT, BOARD_STAR],
        "effective_from": "FIRST_GENUINE_T_CLOSE_RUN_AFTER_DEPLOYMENT",
    }


def policy_display_label(policy: Any) -> str:
    """Return user-facing text without exposing the technical policy literal."""

    if policy == UNIVERSE_POLICY_MAIN_BOARD_ONLY_V1:
        return "沪深主板 / Main Board Only"
    return "未记录（历史 artifact）"


def build_board_policy_audit(symbols: Iterable[Any]) -> dict[str, Any]:
    """Build deterministic board counts and exclusions for an input universe."""

    normalized = sorted({
        _canonical_code(symbol) or str(symbol).strip().upper()
        for symbol in symbols
    })
    counts = {
        BOARD_MAIN: 0,
        BOARD_CHINEXT: 0,
        BOARD_STAR: 0,
        BOARD_UNKNOWN: 0,
    }
    excluded = {
        BOARD_CHINEXT: [],
        BOARD_STAR: [],
        BOARD_UNKNOWN: [],
    }
    retained: list[str] = []
    for symbol in normalized:
        board = classify_board(symbol)
        counts[board] += 1
        if board == BOARD_MAIN:
            retained.append(symbol)
        else:
            excluded[board].append(symbol)
    return {
        "classifier": BOARD_TAXONOMY_VERSION,
        "policy": UNIVERSE_POLICY_MAIN_BOARD_ONLY_V1,
        "allowed_board": BOARD_MAIN,
        "input_symbol_count": len(normalized),
        "retained_count": len(retained),
        "board_counts": counts,
        "excluded_symbols": excluded,
    }


def validate_board_policy_audit(value: Any) -> None:
    """Validate the structural identity of a persisted board-policy audit."""

    if not isinstance(value, Mapping):
        raise ValueError("board policy audit must be a mapping")
    if value.get("classifier") != BOARD_TAXONOMY_VERSION:
        raise ValueError("board policy classifier is unsupported")
    if value.get("policy") != UNIVERSE_POLICY_MAIN_BOARD_ONLY_V1:
        raise ValueError("board policy identity is unsupported")
    if value.get("allowed_board") != BOARD_MAIN:
        raise ValueError("board policy allowed board is unsupported")
    counts = value.get("board_counts")
    if not isinstance(counts, Mapping) or set(counts) != {
        BOARD_MAIN,
        BOARD_CHINEXT,
        BOARD_STAR,
        BOARD_UNKNOWN,
    }:
        raise ValueError("board policy counts are invalid")
    for count in counts.values():
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("board policy count is invalid")
    input_count = value.get("input_symbol_count")
    retained_count = value.get("retained_count")
    if (
        isinstance(input_count, bool)
        or not isinstance(input_count, int)
        or input_count < 0
        or isinstance(retained_count, bool)
        or not isinstance(retained_count, int)
        or retained_count != counts[BOARD_MAIN]
        or input_count != sum(counts.values())
    ):
        raise ValueError("board policy aggregate counts are invalid")
    excluded = value.get("excluded_symbols")
    if not isinstance(excluded, Mapping) or set(excluded) != {
        BOARD_CHINEXT,
        BOARD_STAR,
        BOARD_UNKNOWN,
    }:
        raise ValueError("board policy exclusions are invalid")
    for board, symbols in excluded.items():
        if not isinstance(symbols, list) or symbols != sorted(set(symbols)):
            raise ValueError(f"board policy exclusion list is invalid: {board}")
        if len(symbols) != counts[board]:
            raise ValueError(f"board policy exclusion count is invalid: {board}")


__all__ = [
    "BOARD_CHINEXT",
    "BOARD_MAIN",
    "BOARD_STAR",
    "BOARD_TAXONOMY_VERSION",
    "BOARD_UNKNOWN",
    "UNIVERSE_POLICY_MAIN_BOARD_ONLY_V1",
    "build_board_policy_audit",
    "classify_board",
    "is_live_universe_eligible",
    "policy_display_label",
    "universe_policy_metadata",
    "validate_board_policy_audit",
]
