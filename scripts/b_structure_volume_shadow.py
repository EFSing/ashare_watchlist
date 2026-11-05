"""Disabled-by-default, T-known-only observations of canonical qualified B.

No outcome reader, provider, ranking or delivery output. Recording failures are
isolated after production delivery; immutable conflicts refuse only Shadow.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

import numpy as np

from b_breakout_retest_v1_1 import STRATEGY_SPEC_SHA256, STRATEGY_VERSION
from b_phase_volume_path_diagnostic import _first_breakout_trace
from b_priority_w2w3_volume_v1 import INVALID, STATES, structure_proxy, t_prefix
from b_prospective_observation import (
    _next_horizon_date, _source_identity, _source_validation, breakout_episode_id,
    MINIMUM_SIGNAL_SESSIONS, MINIMUM_MATURE_INDEPENDENT_EPISODES, MAXIMUM_SIGNAL_SESSIONS,
)
from c_state_store import _copy_missing
from cloud_runtime_state import validate_state_tree
from trading_calendar import default_calendar
from volume_observation import VOLUME_OBSERVATION_FIELDS as FIELDS, calculate_stock_volume_observation
from watchlist_schema import load_watchlist

VERSION = "B_STRUCTURE_FIRST_VOLUME_INCREMENTAL_SHADOW_V1"
RELATIVE_ROOT = Path("data/research/b_structure_volume_shadow_v1")
PROTOCOL = "docs/research/b_structure_first_volume_incremental_shadow_v1_protocol.md"
PROTOCOL_COMMIT = "b6d2adf6412dc722861acfb8902eb0c10347b1ee"
PROTOCOL_SHA256 = "dc78be572fcd47d714ce187ba6667d590d0bd467f79e5f298e22af230ea55b67"
TRANSITION = STATES[1]
MAX_FILE_BYTES = 256_000
MAX_DAY_BYTES = 500_000
BJT = timezone(timedelta(hours=8))
SOURCE_ROOT = Path(__file__).resolve().parents[1]


def canonical(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read(path: Path, expected: str | None = None):
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("SHADOW_SYMLINK_REFUSED")
    if {"final_oos", "continuous_speed_probe"}.intersection(p.lower() for p in path.parts):
        raise ValueError("FORBIDDEN_INPUT_PATH")
    raw = path.read_bytes()
    if expected is not None and sha(raw) != expected:
        raise ValueError("SHADOW_INPUT_SHA_MISMATCH")
    return json.loads(raw)


@lru_cache(maxsize=128)
def _verify_generation_protocol(commit: str) -> None:
    # Survives squash merge: bind the generation commit's protocol bytes rather
    # than requiring the original PR lock commit to be its ancestor.
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("SHADOW_GENERATION_COMMIT_REQUIRED")
    raw = subprocess.check_output(["git", "show", f"{commit}:{PROTOCOL}"], cwd=SOURCE_ROOT,
                                  stderr=subprocess.PIPE)
    if sha(raw.replace(b"\r\n", b"\n")) != PROTOCOL_SHA256:
        raise ValueError("SHADOW_GENERATION_PROTOCOL_MISMATCH")


def feature_identity() -> dict:
    paths = ("b_structure_volume_shadow.py", "b_priority_w2w3_volume_v1.py",
             "b_phase_volume_path_diagnostic.py", "volume_observation.py")
    if sha((SOURCE_ROOT / PROTOCOL).read_bytes().replace(b"\r\n", b"\n")) != PROTOCOL_SHA256:
        raise ValueError("SHADOW_FROZEN_PROTOCOL_CHANGED")
    return {"structure": "B_W2W3_STRUCTURE_PROXY_V1", "hypothesis": "VOLUME_FEATURE_HYPOTHESIS_V1",
            "protocol_commit": PROTOCOL_COMMIT, "protocol_lf_sha256": PROTOCOL_SHA256,
            "source_lf_sha256": {p: sha((SOURCE_ROOT / "scripts" / p).read_bytes().replace(b"\r\n", b"\n"))
                                 for p in paths}}


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


def _relative(day: str, kind: str) -> Path:
    return RELATIVE_ROOT / kind / f"{day.replace('-', '')}.json"


def verify_artifacts(root: Path, day: str) -> tuple[dict, dict]:
    receipt_path = root / _relative(day, "daily")
    receipt = _read(receipt_path)
    body = {k: v for k, v in receipt.items() if k != "record_sha256"}
    if receipt.get("record_sha256") != sha(canonical(body)):
        raise ValueError("SHADOW_RECEIPT_HASH_MISMATCH")
    info = receipt["observations"]
    expected = _relative(day, "observations")
    if (receipt.get("schema_version") != VERSION or receipt.get("signal_date") != day
            or info["path"] != expected.as_posix()):
        raise ValueError("SHADOW_ARTIFACT_IDENTITY_MISMATCH")
    path = root / expected
    observations = _read(path, info["sha256"])
    sizes = (receipt_path.stat().st_size, path.stat().st_size)
    if (max(sizes) > MAX_FILE_BYTES or sum(sizes) > MAX_DAY_BYTES or sizes[1] != info["bytes"]
            or len(observations["rows"]) != info["rows"] or observations["signal_date"] != day
            or observations["schema_version"] != VERSION
            or observations["feature_identity"] != receipt["feature_identity"]):
        raise ValueError("SHADOW_ROWS_OR_BYTES_MISMATCH")
    return receipt, observations


def _real_dates(state_root: Path, start: str, day: str, calendar) -> set[str]:
    """Read completed B checkpoint metadata and canonical T-known lists only."""
    result = set()
    for path in sorted((state_root / "data/checkpoints").glob("daily_checkpoint_????????.json")):
        token = path.stem[-8:]
        signal = f"{token[:4]}-{token[4:6]}-{token[6:]}"
        if not start <= signal <= day:
            continue
        meta = _read(path)
        created = datetime.fromisoformat(meta["created_at_bjt"])
        if (meta.get("schema_version") != "DAILY_LIGHTWEIGHT_CLOUD_CHECKPOINT_V1"
                or meta.get("strategy_version") != STRATEGY_VERSION or meta.get("list_date") != signal
                or created.tzinfo is None or created.astimezone(BJT).date().isoformat() != signal
                or not calendar.is_trading_day(signal) or created < calendar.session_close(signal)):
            continue
        _verify_generation_protocol(meta["code_git_sha"])
        _read(state_root / "data" / f"watchlist_{token}.json", meta["watchlist"]["sha256"])
        result.add(signal)
    return result


def checkpoint(sessions: int, eligible: int) -> dict:
    enough = eligible >= MINIMUM_MATURE_INDEPENDENT_EPISODES
    ready = sessions >= MINIMUM_SIGNAL_SESSIONS and enough
    maximum = sessions >= MAXIMUM_SIGNAL_SESSIONS
    return {"real_b_signal_sessions": sessions, "calendar_eligible_transition_episodes": eligible,
            "actual_mature_episodes": None, "outcome_maturity": "NOT_ACCESSED_REQUIRES_SEPARATE_REVIEW",
            "minimum_sessions": MINIMUM_SIGNAL_SESSIONS,
            "minimum_actual_mature_transition_episodes": MINIMUM_MATURE_INDEPENDENT_EPISODES,
            "maximum_sessions": MAXIMUM_SIGNAL_SESSIONS,
            "status": "REVIEW_REQUIRED_PENDING_OUTCOME_VERIFICATION" if ready else
                      "B_STRUCTURE_VOLUME_PROSPECTIVE_EVIDENCE_INSUFFICIENT" if maximum else "COLLECTING"}


def capture(b_result: dict, delivery: dict, *, state_root: Path, output_root: Path,
            start_date: str, now: datetime | None = None, calendar=None) -> dict:
    day = b_result["as_of_date"]
    current = (now or datetime.now(BJT)).astimezone(BJT)
    cal = calendar or default_calendar()
    if (date.fromisoformat(start_date).isoformat() != start_date or day < start_date
            or current.date().isoformat() != day or current < cal.session_close(day)):
        raise ValueError("NO_BACKFILL_OR_PRE_CLOSE_CAPTURE")
    if (b_result.get("status") != "T_CLOSE_EVIDENCE_PACKAGE_AND_WATCHLIST_PERSISTED"
            or b_result.get("acquisition_timing") == "AUTHORIZED_WEEKEND_BACKFILL"
            or delivery.get("report_date") != day
            or delivery.get("status") not in {"DELIVERY_SUCCESS", "ALREADY_DELIVERED"}):
        raise ValueError("GENUINE_DELIVERED_B_RUN_REQUIRED")
    _verify_generation_protocol(b_result["code_git_sha"])
    identity = feature_identity()
    package_info, watch_info = b_result["input_package"], b_result["watchlist"]
    package = _read(Path(package_info["path"]), package_info["file_sha256"])
    watch_path, run_path = Path(watch_info["path"]), Path(watch_info["run_manifest_path"])
    _read(watch_path, watch_info["file_sha256"])
    watch = load_watchlist(watch_path)
    run = _read(run_path)
    source = _source_identity(watch_path, run_path, watch, run)
    signal, _, manifest, by_code = _source_validation(watch, run, calendar=cal)
    acquired = datetime.fromisoformat(package["provenance"]["retrieved_at_bjt"])
    if (signal != day or package["generation_input_manifest"] != manifest
            or package.get("candidate") != {"strategy_version": STRATEGY_VERSION, "spec_sha256": STRATEGY_SPEC_SHA256}
            or acquired.tzinfo is None or acquired.astimezone(BJT).date().isoformat() != day
            or not cal.session_close(day) <= acquired <= current
            or package["provenance"].get("acquisition_timing") is not None
            or watch_info["candidate_count"] != len(watch["candidates"])):
        raise ValueError("SHADOW_SAME_RUN_INPUT_IDENTITY_MISMATCH")
    _read(state_root / "data" / f"watchlist_{day.replace('-', '')}.json", watch_info["file_sha256"])
    volume_info = b_result["volume_observations"]
    report = _read(Path(volume_info["path"]), volume_info["file_sha256"])
    if report["report_date"] != day or report["candidate_count"] != len(watch["candidates"]):
        raise ValueError("SHADOW_REPORT_COHORT_MISMATCH")
    previous = []
    for path in sorted((state_root / RELATIVE_ROOT / "daily").glob("????????.json")):
        prior_day = f"{path.stem[:4]}-{path.stem[4:6]}-{path.stem[6:]}"
        if prior_day > day:
            raise ValueError("SHADOW_NON_CHRONOLOGICAL_CAPTURE")
        if prior_day == day:
            continue
        receipt, observed = verify_artifacts(state_root, prior_day)
        if receipt["start_date"] != start_date or receipt["feature_identity"] != identity:
            raise ValueError("SHADOW_FROZEN_IDENTITY_CHANGED")
        previous.append((receipt, observed))
    if any(r["checkpoint"]["status"] != "COLLECTING" for r, _ in previous):
        return {"status": "B_SHADOW_CHECKPOINT_REACHED_NO_FURTHER_CAPTURE"}
    real_dates = _real_dates(state_root, start_date, day, cal)
    if day not in real_dates:
        raise ValueError("SHADOW_COMPLETED_REAL_B_CHECKPOINT_REQUIRED")
    prior_rows = [r for _, payload in previous for r in payload["rows"]]
    seen = {r["episode"]["analysis_episode_key"] for r in prior_rows if r["episode"]}
    transitions = {}
    for row in prior_rows:
        if row["episode"] and row["is_w2w3_transition"]:
            transitions.setdefault(row["episode"]["analysis_episode_key"], row["signal_date"])
    if len(real_dates) > MAXIMUM_SIGNAL_SESSIONS:
        eligible = sum(_next_horizon_date(d, 10, cal) <= day for d in transitions.values())
        return {"status": "B_SHADOW_HARD_MAXIMUM_REACHED_NO_FURTHER_CAPTURE",
                "checkpoint": checkpoint(len(real_dates), eligible)}
    rows = []
    for candidate in watch["candidates"]:
        code = candidate["code"]
        row = observe(candidate, by_code.get(code, {}).get("bars"), day)
        if report["observations"].get(candidate["signal_id"], {}).get("observation") != row["volume"]:
            raise ValueError("SHADOW_REPORT_VOLUME_SEMANTIC_MISMATCH")
        episode = row["episode"]
        if episode:
            key = episode["analysis_episode_key"]
            episode["first_observed_signal"] = key not in seen
            episode["first_transition_observation"] = row["is_w2w3_transition"] and key not in transitions
            seen.add(key)
            if row["is_w2w3_transition"]:
                transitions.setdefault(key, day)
        rows.append(row)
    if set(report["observations"]) != {r["signal_id"] for r in rows}:
        raise ValueError("SHADOW_REPORT_IDENTITY_SET_MISMATCH")
    add_coordinates(rows)
    eligible = sum(_next_horizon_date(d, 10, cal) <= day for d in transitions.values())
    observed = {"schema_version": VERSION, "signal_date": day, "feature_identity": identity, "rows": rows}
    observed_raw = canonical(observed)
    receipt = {"schema_version": VERSION, "signal_date": day, "start_date": start_date,
               "feature_identity": identity, "strategy_spec_sha256": STRATEGY_SPEC_SHA256,
               "package_sha256": package_info["file_sha256"], "generation_commit": b_result["code_git_sha"],
               "package_generation_fingerprint": package["generation_fingerprint"],
               "input_fingerprint": source["input_fingerprint"], "generation_fingerprint": source["generation_fingerprint"],
               "watchlist_sha256": source["watchlist_sha256"], "run_manifest_sha256": source["run_manifest_sha256"],
               "report_observation_sha256": volume_info["file_sha256"],
               "observations": {"path": _relative(day, "observations").as_posix(), "sha256": sha(observed_raw),
                                "bytes": len(observed_raw), "rows": len(rows)},
               "structure_counts": {state: sum(r["structure"]["state"] == state for r in rows) for state in STATES},
               "available_by_field": {f: sum(r["volume"][f] is not None for r in rows) for f in FIELDS},
               "recorder_gap_dates": sorted(real_dates - {day} - {r["signal_date"] for r, _ in previous}),
               "checkpoint": checkpoint(len(real_dates), eligible), "outcome_accessed": False,
               "production_semantics_change": False, "final_oos": "SEALED / UNREAD"}
    receipt["record_sha256"] = sha(canonical(receipt))
    payloads = ((_relative(day, "observations"), observed_raw), (_relative(day, "daily"), canonical(receipt)))
    sizes = [len(raw) for _, raw in payloads]
    if max(sizes) > MAX_FILE_BYTES or sum(sizes) > MAX_DAY_BYTES:
        raise ValueError("SHADOW_SIZE_LIMIT_NO_CANDIDATE_TRUNCATION")
    for relative, raw in payloads:
        target = state_root / relative
        if any(p.is_symlink() for p in (target, *target.parents)):
            raise ValueError("SHADOW_SYMLINK_REFUSED")
        if target.exists() and target.read_bytes() != raw:
            raise ValueError("SHADOW_SAME_DATE_IMMUTABILITY_CONFLICT")
    for relative, raw in payloads:
        path = output_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        _copy_missing(path, state_root / relative)
    verify_artifacts(state_root, day)
    return {"status": "B_SHADOW_STAGED_READBACK_VERIFIED", "signal_date": day,
            "paths": [p.as_posix() for p, _ in payloads], "rows": len(rows), "combined_bytes": sum(sizes),
            "receipt_sha256": sha(payloads[1][1]), "receipt_bytes": sizes[1],
            "observations_sha256": sha(observed_raw), "observations_bytes": sizes[0],
            "checkpoint": receipt["checkpoint"]}


def publish(state_root: Path, staged: dict) -> dict:
    """Only the two verified new B Shadow paths may reach runtime-state."""
    if not staged.get("paths"):
        return staged
    from run_c_daily_watchlist import _git

    expected = {_relative(staged["signal_date"], kind).as_posix() for kind in ("observations", "daily")}
    paths = staged["paths"]
    if set(paths) != expected or len(paths) != 2:
        raise ValueError("SHADOW_PUBLISH_PATHS_REFUSED")
    verify_artifacts(state_root, staged["signal_date"])
    validate_state_tree(state_root)
    if _git(state_root, "diff", "--cached", "--name-only").strip():
        raise ValueError("RUNTIME_STATE_ALREADY_HAS_STAGED_PATHS")
    if _git(state_root, "diff", "--name-only", "--", *paths).strip():
        raise ValueError("SHADOW_APPEND_ONLY_EXISTING_PATH_CHANGED")
    _git(state_root, "add", "--", *paths)
    changed = set(_git(state_root, "diff", "--cached", "--name-only").decode().splitlines())
    if not changed.issubset(expected):
        raise ValueError("NON_SHADOW_RUNTIME_PATH_STAGED")
    _git(state_root, "diff", "--cached", "--check")
    if changed:
        _git(state_root, "config", "user.name", "github-actions[bot]")
        _git(state_root, "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
        _git(state_root, "commit", "-m", "runtime: append independent B structure volume observations")
        _git(state_root, "push", "origin", "HEAD:runtime-state", timeout=60)
    _git(state_root, "fetch", "origin", "runtime-state", timeout=60)
    for path in paths:
        if _git(state_root, "show", f"FETCH_HEAD:{path}") != (state_root / path).read_bytes():
            raise ValueError("SHADOW_REMOTE_READBACK_MISMATCH")
    return {**staged, "status": "B_SHADOW_REMOTE_READBACK_VERIFIED",
            "runtime_state_sha": _git(state_root, "rev-parse", "FETCH_HEAD").decode().strip()}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--b-result", type=Path, required=True)
    parser.add_argument("--delivery-result", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    args = parser.parse_args(argv)
    result = {"status": "B_STRUCTURE_VOLUME_SHADOW_DISABLED"}
    if os.environ.get("ENABLE_B_STRUCTURE_VOLUME_SHADOW_V1", "").lower() == "true":
        try:
            load = lambda path: json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
            with tempfile.TemporaryDirectory(prefix="b-structure-volume-", dir=os.environ.get("RUNNER_TEMP")) as temp:
                result = capture(load(args.b_result), load(args.delivery_result), state_root=args.state_root,
                                 output_root=Path(temp), start_date=os.environ.get("B_STRUCTURE_VOLUME_SHADOW_START_DATE", ""))
                result = publish(args.state_root, result)
        except Exception as exc:
            result = {"status": "B_STRUCTURE_VOLUME_SHADOW_FAILED_B_C_UNCHANGED", "reason": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
