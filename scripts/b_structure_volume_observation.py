"""Frozen T-known structure and volume observations for qualified Formal B."""
from __future__ import annotations

import hashlib
import json

import numpy as np

from b_breakout_retest_v1_1 import STRATEGY_SPEC_SHA256
from b_phase_volume_path_diagnostic import _first_breakout_trace
from b_priority_w2w3_volume_v1 import INVALID, STATES, structure_proxy, t_prefix
from b_prospective_observation import breakout_episode_id
from volume_observation import VOLUME_OBSERVATION_FIELDS as FIELDS, calculate_stock_volume_observation


TRANSITION = STATES[1]


def canonical(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def observe(candidate: dict, bars, day: str) -> dict:
    """A qualified candidate is retained even when its feature trace is absent."""
    code = candidate["code"]
    volume = calculate_stock_volume_observation(bars, day, code=code)
    structure = {"state": INVALID, "recovery_ratio": None, "reason": "STOCK_KLINE_UNAVAILABLE"}
    episode = None
    if bars:
        try:
            prefix = t_prefix(bars, day)
            # The package is a genuine T-ending input. Do not silently discard
            # appended future rows or give them a valid prospective identity.
            if len(prefix) != len(bars):
                raise ValueError("FUTURE_INPUT_REFUSED")
            c, h, l, v = (np.asarray([b[f] for b in prefix]) for f in ("close", "high", "low", "volume"))
            trace = _first_breakout_trace(c, v, h, l, [b["date"] for b in prefix])
            if trace is None or trace["pullback_stage"] != "PULLBACK_ALL_PASS":
                structure["reason"] = "QUALIFIED_TRACE_UNAVAILABLE_OR_INCONSISTENT"
            else:
                i = int(trace["breakout_index"])
                structure = structure_proxy(c, h, l, i)
                facts = {"breakout_date": prefix[i]["date"], "breakout_index": i, "base_hi": trace["base_hi"]}
                episode = {**facts, "breakout_episode_id": breakout_episode_id(code, facts),
                           "analysis_episode_key": sha(canonical([code, facts["breakout_date"], STRATEGY_SPEC_SHA256]))}
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            structure = {"state": INVALID, "recovery_ratio": None,
                         "reason": f"STRUCTURE_INPUT_UNAVAILABLE:{type(exc).__name__}"}
    return {"signal_id": candidate["signal_id"], "code": code, "signal_date": day,
            "formal_b_qualified": True, "structure": structure,
            "is_w2w3_transition": structure["state"] == TRANSITION,
            "volume": volume, "episode": episode}


def add_coordinates(rows: list[dict]) -> None:
    """Ascending raw coordinates only, independently available per field."""
    for row in rows:
        row["coordinates"] = {}
    for field in FIELDS:
        available = [r for r in rows if r["is_w2w3_transition"] and r["volume"][field] is not None]
        n = len(available)
        for row in rows:
            value = row["volume"][field]
            coordinate = {"available": value is not None, "cross_section_n": n,
                          "percentile": None, "bucket": None}
            if not row["is_w2w3_transition"]:
                coordinate["status"] = "NOT_PRIMARY_COHORT"
            elif value is None:
                coordinate["status"] = "FEATURE_UNAVAILABLE"
            elif n < 3:
                coordinate["status"] = "INSUFFICIENT_CROSS_SECTION"
            else:
                values = [r["volume"][field] for r in available]
                p = (sum(v < value for v in values) + (sum(v == value for v in values) + 1) / 2) / n
                coordinate.update(percentile=p, bucket="LOW" if p <= 1/3 else "MID" if p <= 2/3 else "HIGH",
                                  status="ANALYSIS_COORDINATE_ONLY")
            row["coordinates"][field] = coordinate
