"""Outcome-blind input audit for B_PRIORITY_W2W3_VOLUME_RESEARCH_V1.

This entry point has no outcome reader. A missing real-observation parity input
stops the study; synthetic agreement cannot authorize historical comparisons.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np

from b_breakout_retest import _b_match
from b_breakout_retest_v1_1 import STRATEGY_SPEC_SHA256
from b_candidate_ranking_volume_turnover_v1 import (
    CORE_MANIFEST, ELIGIBILITY, IMPACT, QUALIFIED, file_sha256,
    scan_stream, verify_stream,
)
from b_phase_volume_path_diagnostic import _first_breakout_trace
from b_turnover_x_relative_volume_incremental import _board_for_symbol
import core_signal_replay as replay
from volume_observation import (
    VOLUME_OBSERVATION_FIELDS as FIELDS,
    calculate_pullback_volume_observation,
    calculate_stock_volume_observation,
)

TASK = "B_PRIORITY_W2W3_VOLUME_RESEARCH_V1"
BLOCKER = "B_PRIORITY_RESEARCH_BLOCKED_BY_DATA_GAP"
INVALID = "STRUCTURE_PROXY_UNAVAILABLE_OR_INVALID"
STATES = ("EARLY_PULLBACK", "W2_TO_W3_TRANSITION_PROXY",
          "POST_H1_CONTINUATION_PROXY", INVALID)
RUNTIME_REF = "ebe014748cfd3a551b0e3589124e08b2c154871d"
PROTOCOL = "docs/research/b_priority_w2w3_volume_v1_protocol.md"
PROTOCOL_COMMIT = "13008a3579a225af1f89f1facee1f22c48050195"
OUTPUT = "data/validation/b_priority_w2w3_volume_v1"


def structure_proxy(close, high, low, breakout_index: int) -> dict:
    """Consume a validated T-ending prefix and the existing first-breakout index."""
    t, i = len(close) - 1, breakout_index
    invalid = {"state": INVALID, "recovery_ratio": None}
    if not (len(high) == len(low) == len(close) and 60 <= i < t):
        return {**invalid, "reason": "BASE_OR_BREAKOUT_WINDOW_UNAVAILABLE"}
    l0 = float(np.min(low[i - 60:i]))
    h1_idx = i + int(np.argmax(high[i:t]))  # numpy argmax chooses first equal high.
    if h1_idx + 1 >= t:
        return {**invalid, "reason": "NO_COMPLETE_POST_H1_PULLBACK_DAY"}
    h1 = float(high[h1_idx])
    l2 = float(np.min(low[h1_idx + 1:t]))
    facts = {"L0": l0, "H1": h1, "L2": l2, "h1_index": h1_idx}
    if not all(np.isfinite(x) for x in (l0, h1, l2, close[t])) or not l0 < l2 < h1:
        return {**invalid, **facts, "reason": "INVALID_L0_L2_H1_ORDER_OR_DENOMINATOR"}
    recovery = float((close[t] - l2) / (h1 - l2))
    state = STATES[0] if recovery < 0.5 else STATES[1] if recovery <= 1.0 else STATES[2]
    return {**facts, "state": state, "recovery_ratio": recovery, "reason": None}


def t_prefix(bars, signal_date: str) -> list[dict]:
    """Do not read any future OHLCV, even when future bars are appended."""
    prefix = []
    for bar in bars:
        day = str(bar["date"])
        if day > signal_date:
            break
        if prefix and day <= prefix[-1]["date"]:
            raise ValueError("duplicate or unordered bars")
        values = {field: float(bar[field]) for field in ("close", "high", "low", "volume")}
        if (not all(np.isfinite(v) for v in values.values())
                or min(values[f] for f in ("close", "high", "low")) <= 0
                or values["volume"] < 0
                or not values["low"] <= values["close"] <= values["high"]):
            raise ValueError("invalid OHLCV")
        prefix.append({"date": day, **values})
    if not prefix or prefix[-1]["date"] != signal_date or len(prefix) < 120:
        raise ValueError("T close or minimum history missing")
    return prefix


def reconstruct(identity: tuple[str, str, str], bars) -> dict:
    """Preserve frozen identity and compute only the allowed pre-outcome fields."""
    symbol, day, setup = identity
    prefix = t_prefix(bars, day)
    c, h, l, v = (np.asarray([b[f] for b in prefix]) for f in ("close", "high", "low", "volume"))
    trace = _first_breakout_trace(c, v, h, l, [b["date"] for b in prefix])
    base, _, _ = _b_match(c, v, float(np.mean(c[-5:])))
    if trace is None or base is None or trace["base_hi"] != base or trace["pullback_stage"] != "PULLBACK_ALL_PASS":
        raise RuntimeError(f"frozen qualified B trace not recovered: {identity}")
    i = int(trace["breakout_index"])
    observation = calculate_pullback_volume_observation(c, v, i)
    return {"symbol": symbol, "signal_date": day, "setup_id": setup,
            "board": _board_for_symbol(symbol), "breakout_date": prefix[i]["date"],
            "structure": structure_proxy(c, h, l, i), "volume": observation}


def parity_difference(actual: dict, expected: dict) -> list[str]:
    """Compare all frozen numeric fields, the window and exact missing reasons."""
    different = []
    for field in (*FIELDS, "window_days", "missing_reason"):
        a, e = actual.get(field), expected.get(field)
        if field in FIELDS and a is not None and e is not None:
            equal = bool(np.isclose(a, e, rtol=1e-12, atol=1e-12))
        else:
            equal = a == e
        if not equal:
            different.append(field)
    return different


def git_bytes(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=root)


def runtime_inventory(root: Path) -> dict:
    paths = git_bytes(root, "ls-tree", "-r", "--name-only", RUNTIME_REF, "--", "data").decode().splitlines()
    observation_paths = [p for p in paths if p.startswith("data/volume_observations/")]
    rows, files, missing = 0, [], Counter()
    for path in observation_paths:
        payload = git_bytes(root, "show", f"{RUNTIME_REF}:{path}")
        store = json.loads(payload)
        complete = 0
        if len(store["observations"]) != store["candidate_count"]:
            raise RuntimeError("runtime observation count mismatch")
        for signal_id, record in store["observations"].items():
            expected_id = f"B_BREAKOUT_RETEST_LEGACY_V1_1:{store['report_date']}:{record['code']}:B_BREAKOUT_RETEST"
            if signal_id != record["signal_id"] or signal_id != expected_id:
                raise RuntimeError("runtime observation identity mismatch")
            obs = record["observation"]
            complete += all(obs[f] is not None for f in FIELDS)
            missing.update(obs["missing_reason"].values())
        if complete != store["complete_count"]:
            raise RuntimeError("runtime complete count mismatch")
        rows += store["candidate_count"]
        files.append({"path": path, "sha256": hashlib.sha256(payload).hexdigest(),
                      "bytes": len(payload), "date": store["report_date"],
                      "candidates": store["candidate_count"], "complete": complete,
                      "incomplete": store["candidate_count"] - complete})
    return {"ref": RUNTIME_REF, "files": files, "dates": len(files), "candidates": rows,
            "complete": sum(f["complete"] for f in files), "missing_reasons": dict(sorted(missing.items())),
            "earliest": min(f["date"] for f in files), "latest": max(f["date"] for f in files),
            "matching_input_packages_in_runtime_state": [p for p in paths if "input_package" in p or "generation_input" in p or "t_close_evidence/" in p],
            "status": "NOT_REPRODUCIBLE_WITH_CURRENT_DATA",
            "real_rows_reconstructed": 0, "real_dates_reconstructed": 0,
            "parity_status": "NOT_RUN_INPUTS_UNAVAILABLE", "parity_mismatches": None}


def _coverage(rows: list[dict]) -> dict:
    dates = Counter(r["signal_date"] for r in rows)
    complete = [r for r in rows if all(r["volume"][f] is not None for f in FIELDS)]
    states = {}
    for state in STATES:
        group = [r for r in rows if r["structure"]["state"] == state]
        states[state] = {"rows": len(group), "dates": len({r["signal_date"] for r in group})}
    complete_dates = Counter(r["signal_date"] for r in complete)
    return {"rows": len(rows), "dates": len(dates),
            "start": min(dates) if dates else None, "end": max(dates) if dates else None,
            "structure_states": states,
            "structure_available": len(rows) - states[INVALID]["rows"],
            "structure_available_dates": len({r["signal_date"] for r in rows if r["structure"]["state"] != INVALID}),
            "structure_available_volume_complete": sum(r["structure"]["state"] != INVALID for r in complete),
            "volume_complete_structure_states": dict(sorted(Counter(r["structure"]["state"] for r in complete).items())),
            "volume_available": {f: sum(r["volume"][f] is not None for r in rows) for f in FIELDS},
            "volume_complete": len(complete), "volume_complete_dates": len(complete_dates),
            "complete_case_eligible_dates_before_outcomes": {f"Top{k}": sum(n >= max(2, k) for n in complete_dates.values()) for k in (1, 3, 5)},
            "volume_missing_reasons": dict(sorted(Counter(reason for r in rows for reason in r["volume"]["missing_reason"].values()).items()))}


def run(root: Path, raw_dir: Path) -> dict:
    if any(t in str(raw_dir).lower() for t in ("final_oos", "continuous_speed_probe")):
        raise ValueError("forbidden input path")
    def metadata(path):
        return json.loads((root / path).read_text(encoding="utf-8"))
    locked = git_bytes(root, "show", f"{PROTOCOL_COMMIT}:{PROTOCOL}")
    if locked.replace(b"\r\n", b"\n") != (root / PROTOCOL).read_bytes().replace(b"\r\n", b"\n"):
        raise RuntimeError("pre-outcome protocol changed after lock")
    impact, manifest = metadata(IMPACT), metadata(CORE_MANIFEST)
    if (STRATEGY_SPEC_SHA256 != "f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd"
            or impact["corrected_reconstruction"]["spec_sha256"] != STRATEGY_SPEC_SHA256
            or impact["decision"] != "ELIGIBILITY_ARTIFACT_EVENT_SET_INVARIANT"
            or impact["comparison"]["qualification_event_membership_differences"] != 0
            or not impact["comparison"]["corrected_projection_shared_callable_identity"]):
        raise RuntimeError("corrected frozen membership proof invalid")
    audit, identities = scan_stream(root / QUALIFIED, identities=True)
    verify_stream(audit, metadata(ELIGIBILITY)["artifacts"]["event_results"])
    if audit["file_sha256"] != impact["old_reconstruction"]["event_artifact_sha256"]:
        raise RuntimeError("qualified event hash disagrees with corrected membership proof")
    raw_audit = []
    for declared in manifest["provenance"]["raw_inputs"]["files"]:
        path = raw_dir / declared["filename"]
        digest = file_sha256(path)
        if digest != declared["sha256"] or path.stat().st_size != declared["bytes"]:
            raise RuntimeError(f"frozen raw identity mismatch: {path.name}")
        raw_audit.append({"filename": path.name, "sha256": digest, "bytes": path.stat().st_size})
    print(f"verified {len(identities)} frozen identities; reconstructing T-only features", flush=True)
    # Read only allowed OHLCV, excluding the source's unrelated turnover column.
    import pandas as pd
    columns = ["thscode", "date_ms", "close_price", "high_price", "low_price", "volume"]
    frame = pd.read_parquet(raw_dir / "daily_k.parquet", columns=columns).sort_values(["thscode", "date_ms"], kind="mergesort")
    date_text = {int(ms): replay._date_from_ms(int(ms)) for ms in frame["date_ms"].unique()}
    events, _ = replay._load_events(raw_dir / "adjustment_factors.parquet")
    by_symbol = {}
    for identity in sorted(identities):
        by_symbol.setdefault(identity[0], []).append(identity)
    records = []
    for symbol, group in frame.groupby("thscode", sort=True):
        symbol = str(symbol).strip().lower()
        if symbol not in by_symbol:
            continue
        ms = group["date_ms"].to_numpy(dtype=np.int64)
        if np.any(ms[1:] <= ms[:-1]):
            raise RuntimeError("duplicate or unordered source dates")
        source = {f: group[col].to_numpy(dtype=float) for f, col in (("close", "close_price"), ("high", "high_price"), ("low", "low_price"), ("volume", "volume"))}
        for identity in by_symbol[symbol]:
            anchor = replay._ms_from_date(identity[1])
            end = int(np.searchsorted(ms, anchor, side="right"))
            if end == 0 or int(ms[end - 1]) != anchor:
                raise RuntimeError("frozen signal has no T bar")
            start = max(0, end - replay.LOOKBACK_BARS)
            local_ms = ms[start:end]
            arrays = {f: values[start:end].copy() for f, values in source.items()}
            for ex_date, dividend, bonus, allotment, price in events.get(symbol, []):
                if ex_date > anchor:
                    break
                mask = local_ms < ex_date
                denominator = 1 + bonus + allotment
                if denominator <= 0:
                    raise RuntimeError("invalid corporate-action denominator")
                for field in ("close", "high", "low"):
                    arrays[field][mask] = (arrays[field][mask] - dividend + price * allotment) / denominator
            bars = [{"date": date_text[int(day)], **{f: float(a[j]) for f, a in arrays.items()}} for j, day in enumerate(local_ms)]
            record = reconstruct(identity, bars)
            # Independent public stock wrapper must agree before any real parity claim.
            if parity_difference(record["volume"], calculate_stock_volume_observation(bars, identity[1], code=symbol.split(".")[0])):
                raise RuntimeError("historical array/public volume wrapper mismatch")
            # Real historical prefixes also exercise deterministic/future-append invariance.
            if reconstruct(identity, bars + [{"date": "2099-01-01"}]) != record:
                raise RuntimeError("future-append invariance failed")
            records.append(record)
    if {(r["symbol"], r["signal_date"], r["setup_id"]) for r in records} != identities:
        raise RuntimeError("qualified identity preservation failed")
    records.sort(key=lambda r: (r["signal_date"], r["symbol"], r["setup_id"]))
    output = root / OUTPUT
    output.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    detail = output / "input_features.jsonl.gz"
    with detail.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as stream:
            for record in records:
                payload = (json.dumps(record, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
                digest.update(payload)
                stream.write(payload)
    boards = {b: _coverage([r for r in records if r["board"] == b]) for b in ("Main", "ChiNext", "STAR", "OUT_OF_SCOPE_PREFIX")}
    runtime = runtime_inventory(root)
    if runtime["matching_input_packages_in_runtime_state"]:
        raise RuntimeError("new parity inputs found: inspect before declaring a gap")
    return {"task": TASK, "classification": "research question", "path": "STRICT",
            "status": BLOCKER, "decision": "NEEDS_MORE_EVIDENCE",
            "PRE_OUTCOME_PROTOCOL_COMMIT": PROTOCOL_COMMIT,
            "metadata_lf_sha256": {p: hashlib.sha256((root / p).read_bytes().replace(b"\r\n", b"\n")).hexdigest() for p in (CORE_MANIFEST, ELIGIBILITY, IMPACT)},
            "prior_plan": {"identity": "B_OPERATIONAL_SCORE_VOLUME_RANKING_V1", "status": "NOT_STARTED / SUPERSEDED_BY_USER_DECISION"},
            "qualified_source": audit, "raw_inputs": raw_audit,
            "price_basis": manifest["adjustment_semantics"],
            "historical_vintage_proof": manifest["provenance"]["known_at_vintage_proof"],
            "cohort": _coverage(records), "boards": boards,
            "frozen_signal_sessions": len(manifest["signal_dates"]),
            "exchange_identity_counts": dict(sorted(Counter(r["symbol"].split(".")[-1] for r in records).items())),
            "primary_main_by_year": {y: _coverage([r for r in records if r["board"] == "Main" and r["signal_date"].startswith(y)]) for y in ("2023", "2024", "2025", "2026")},
            "secondary_main_chinext_star": _coverage([r for r in records if r["board"] != "OUT_OF_SCOPE_PREFIX"]),
            "episode_counts": {b: len({(r["symbol"], r["breakout_date"]) for r in records if r["board"] == b}) for b in boards},
            "real_observation_parity": runtime,
            "causality": {"real_prefix_checks": len(records), "future_append_checks": len(records), "identity_preservation": "PASS", "public_volume_wrapper_checks": len(records)},
            "detail": {"path": f"{OUTPUT}/input_features.jsonl.gz", "rows": len(records),
                       "bytes": detail.stat().st_size, "sha256": file_sha256(detail), "content_stream_sha256": digest.hexdigest()},
            "methods": {method: {"status": "NOT_RUN_REAL_VOLUME_PARITY_INPUTS_UNAVAILABLE",
                                  "5D": None, "10D": None, "Top1_uplift_pp": None,
                                  "Top3_uplift_pp": None, "Top5_uplift_pp": None} for method in ("R0", "R1", "R2", "R3")},
            "decisions": ["B_W2W3_TRANSITION_PRIORITY_NEEDS_MORE_EVIDENCE", "B_REPORT_VOLUME_PRIORITY_NEEDS_MORE_EVIDENCE", "B_W2W3_VOLUME_PRIORITY_NEEDS_MORE_EVIDENCE"],
            "product_design": "DEFER_INPUT_PARITY_REQUIRED", "old_score": "KEEP_CURRENT_PRODUCTION_BEHAVIOR",
            "boundaries": {"outcome_values_accessed": False, "production_semantics_changed": False,
                           "production_score_change": 0, "provider_calls": 0, "runtime_state_modified": False,
                           "final_oos": "SEALED / UNREAD", "production_dispatch": 0},
            "reproduction": "python scripts/b_priority_w2w3_volume_v1.py --raw-dir <restored frozen core_signal_validation/raw>"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=Path("data/validation/core_signal_validation/raw"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    summary = run(root, args.raw_dir.resolve())
    target = root / OUTPUT / "summary.json"
    target.write_text(json.dumps(summary, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": summary["status"], "summary_sha256": file_sha256(target)}))


if __name__ == "__main__":
    main()
