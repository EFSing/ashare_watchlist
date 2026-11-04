"""Outcome-blind prerequisite audit for B same-day ranking V1.

This entry point deliberately stops at the exact-Score identity gate. It does
not implement a proxy score or fit a model when frozen score inputs are absent.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess

from b_breakout_retest_v1_1 import STRATEGY_SPEC_SHA256, STRATEGY_VERSION
from b_turnover_x_relative_volume_incremental import _board_for_symbol


TASK = "B_CANDIDATE_RANKING_VOLUME_TURNOVER_DIAGNOSTIC_V1"
BLOCKER = "B_RANKING_BASELINE_SCORE_IDENTITY_NOT_RECOVERABLE"
DECISION = "B_VOLUME_TURNOVER_RANKING_NEEDS_MORE_EVIDENCE"
PROTOCOL_COMMIT = "24609f3eeea879a58d8f61acfdea0497947b4d56"
PROTOCOL = "docs/research/b_candidate_ranking_volume_turnover_v1_protocol.md"
BASE = "data/validation/"
QUALIFIED = BASE + "strategy_candidate_eligibility_v1/b_breakout_retest_eligibility_events.jsonl.gz"
ELIGIBILITY = BASE + "strategy_candidate_eligibility_v1/strategy_development_eligibility_manifest.json"
CORE = BASE + "core_signal_validation_continuous_parts/core_replay_results.jsonl.gz"
CORE_MANIFEST = BASE + "core_signal_validation_continuous_parts/core_signal_validation_manifest.json"
IMPACT = BASE + "strategy_candidate_eligibility_v1_1/b_reconstruction_impact_audit.json"
TURNOVER_MANIFEST = BASE + "b_turnover_x_relative_volume_incremental_v1/tushare_gateway/manifest/full_acquisition_manifest.json"
OUTPUT = BASE + "b_candidate_ranking_volume_turnover_v1/summary.json"
SPEC = "f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd"
SCORE_KEY = re.compile(rb'"(?:score|score_total|score_85|score_breakdown|sector_rank|sector_chg)"\s*:')
IDENTITY_KEYS = {
    key: re.compile(rb'"' + key.encode() + rb'"\s*:\s*"([^"\\]+)"')
    for key in ("symbol", "signal_date", "setup_id")
}


def file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def scan_stream(path: Path, *, identities: bool = False) -> tuple[dict, set]:
    """Hash bytes and inspect identity/score keys only; never JSON-decode outcomes.

    Absence of a score key anywhere is sufficient evidence of absence at the
    top level. Any occurrence fails closed for manual schema/provenance review.
    """
    digest = hashlib.sha256()
    rows = 0
    score_key_rows = 0
    keys: set[tuple[str, str, str]] = set()
    with gzip.open(path, "rb") as stream:
        for line in stream:
            rows += 1
            digest.update(line)
            score_key_rows += bool(SCORE_KEY.search(line))
            if identities:
                parts = []
                for field, pattern in IDENTITY_KEYS.items():
                    matches = pattern.findall(line)
                    if len(matches) != 1:
                        raise RuntimeError(f"ambiguous/missing identity {field} at row {rows}")
                    parts.append(matches[0].decode("utf-8"))
                key = tuple(parts)
                if key in keys:
                    raise RuntimeError(f"duplicate qualified identity: {key}")
                keys.add(key)
    return {
        "path": path.name, "rows": rows, "bytes": path.stat().st_size,
        "file_sha256": file_sha256(path),
        "content_stream_sha256": digest.hexdigest(),
        "rows_with_any_score_or_sector_key": score_key_rows,
    }, keys


def verify_stream(actual: dict, declared: dict, *, stream_hash_key: str | None = None) -> None:
    checks = [("rows", "rows"), ("bytes", "bytes"), ("file_sha256", "sha256")]
    if stream_hash_key is not None:
        checks.append(("content_stream_sha256", stream_hash_key))
    for observed, expected in checks:
        if actual[observed] != declared[expected]:
            raise RuntimeError(f"frozen stream identity mismatch: {observed}")


def run(root: Path) -> dict:
    root = root.resolve()
    def metadata(relative: str) -> dict:
        return json.loads((root / relative).read_text(encoding="utf-8"))

    locked = subprocess.check_output(["git", "show", f"{PROTOCOL_COMMIT}:{PROTOCOL}"], cwd=root)
    if locked.replace(b"\r\n", b"\n") != (root / PROTOCOL).read_bytes().replace(b"\r\n", b"\n"):
        raise RuntimeError("pre-outcome protocol changed after lock")
    if STRATEGY_SPEC_SHA256 != SPEC:
        raise RuntimeError("corrected B spec changed")
    eligibility, core, impact = metadata(ELIGIBILITY), metadata(CORE_MANIFEST), metadata(IMPACT)
    corrected = impact["corrected_reconstruction"]
    comparison = impact["comparison"]
    if (corrected["strategy_version"] != STRATEGY_VERSION or corrected["spec_sha256"] != SPEC
            or impact["decision"] != "ELIGIBILITY_ARTIFACT_EVENT_SET_INVARIANT"
            or not comparison["corrected_projection_shared_callable_identity"]
            or comparison["qualification_event_membership_differences"] != 0):
        raise RuntimeError("corrected qualified membership proof not valid")
    qualified, keys = scan_stream(root / QUALIFIED, identities=True)
    # The old content_sha256 hashes a JSON array, not the decompressed JSONL
    # stream. Exact compressed SHA binds all bytes without decoding outcomes.
    verify_stream(qualified, eligibility["artifacts"]["event_results"])
    if (qualified["file_sha256"] != impact["old_reconstruction"]["event_artifact_sha256"]
            or len(keys) != comparison["corrected_qualified_event_count"]):
        raise RuntimeError("corrected membership proof refers to different events")
    qualified["path"] = QUALIFIED
    print(f"qualified identities verified: {len(keys)}; scanning core schema", flush=True)
    projection, _ = scan_stream(root / CORE)
    verify_stream(projection, eligibility["input_provenance"]["core_output"],
                  stream_hash_key="projection_stream_sha256")
    projection["path"] = CORE
    if qualified["rows_with_any_score_or_sector_key"] or projection["rows_with_any_score_or_sector_key"]:
        raise RuntimeError("unexpected saved score/sector keys: audit exact identity before proceeding")
    sector = core["sector_semantics"]
    if (sector["historical_membership_included"] is not False
            or sector["sector_score_status"] != "UNVERIFIED"
            or sector["neutral_evaluator_sentinel_used"] is not True
            or "score_total" in core["replay"]["core_output_fields"]):
        raise RuntimeError("frozen score evidence changed; rerun recoverability audit")
    # Verify the existing canonical pair source, but do not compute features or outcomes
    # after the baseline prerequisite fails. No local-only raw K is needed for this audit.
    turnover = metadata(TURNOVER_MANIFEST)["canonical_dataset"]
    turnover_path = root / turnover["path"]
    if (file_sha256(turnover_path) != turnover["file_sha256"]
            or turnover_path.stat().st_size != turnover["bytes"]):
        raise RuntimeError("canonical turnover identity mismatch")
    by_date = Counter(key[1] for key in keys)
    by_year = Counter(key[1][:4] for key in keys)
    by_board = Counter(_board_for_symbol(key[0]) for key in keys)
    evidence_paths = [PROTOCOL, CORE_MANIFEST, ELIGIBILITY, IMPACT, TURNOVER_MANIFEST,
                      "scripts/b_candidate_ranking_volume_turnover_v1.py",
                      "scripts/b_turnover_x_relative_volume_incremental.py",
                      "scripts/b_breakout_retest.py", "scripts/b_breakout_retest_v1_1.py",
                      "scripts/core_signal_replay.py", "scripts/volume_observation.py",
                      "docs/phase2e_pit_source_audit.md", "scripts/historical_validation_layers.py"]
    return {
        "task": TASK, "status": BLOCKER, "decision": DECISION,
        "task_classification": "research question", "path": "STRICT",
        "labels": ["DEVELOPMENT", "RECONSTRUCTED_RETROSPECTIVE",
                   "SAME_DAY_CROSS_SECTIONAL_RANKING", "DIAGNOSTIC_ONLY"],
        "PRE_OUTCOME_PROTOCOL_COMMIT": PROTOCOL_COMMIT,
        "strategy": corrected,
        "cohort": {"qualified_rows": len(keys), "candidate_dates": len(by_date),
                   "start": min(by_date), "end": max(by_date), "rows_by_year": dict(sorted(by_year.items())),
                   "rows_by_board": dict(sorted(by_board.items())),
                   "rows_in_existing_turnover_board_scope": sum(
                       n for board, n in by_board.items() if board != "OUT_OF_SCOPE_PREFIX"),
                   "eligible_candidate_dates_before_score_and_outcome_gates": {
                       "Top1": sum(n >= 2 for n in by_date.values()),
                       "Top3": sum(n >= 3 for n in by_date.values()),
                       "Top5": sum(n >= 5 for n in by_date.values())},
                   "per_date_candidate_count": dict(sorted(by_date.items())),
                   "exact_saved_score_rows": 0, "exact_baseline_missing_rows": len(keys),
                   "ranking_evaluated_rows": 0, "ranking_evaluated_dates": 0,
                   "pair_complete_rows": None, "common_complete_case_rows": None,
                   "missingness_status": "NOT_EVALUATED_AFTER_BASELINE_IDENTITY_STOP"},
        "baseline_audit": {
            "saved_scores": "ABSENT_IN_VERIFIED_QUALIFIED_AND_CORE_STREAMS",
            "historical_sector": sector,
            "full_output_validation": core["full_legacy_output_validation"],
            "affected_score_components": {"strong_sector": "2/6/10 from historical sector_rank",
                                           "sector_linkage": "1/5/10 from historical sector_chg"},
            "why_default_is_invalid": "No historical mapping loaded is not evidence of a V0 missing-symbol mapping.",
            "required_evidence": "Provenance-bound exact score_total for every qualified identity, or exact T-known V0 Sina membership/traversal/rank/change inputs for unchanged full evaluator parity.",
        },
        "artifacts": {"qualified_identity_source": qualified, "core_projection_source": projection,
                      "canonical_turnover_source": {**turnover, "file_hash_verified": True,
                                                    "row_count_basis": "EXISTING_FROZEN_MANIFEST_NOT_NEW_SCAN"}},
        "metadata_and_code_sha256": {p: file_sha256(root / p) for p in evidence_paths},
        "models": {name: {"status": "NOT_RUN_BASELINE_IDENTITY_BLOCKED",
                           "Top1_increment_pp": None, "Top3_increment_pp": None,
                           "Top5_increment_pp": None, "mean_rank_ic": None,
                           "cross_year_stability": None} for name in ("M0", "M1", "M2", "M3")},
        "features": {name: {"status": "NOT_EVALUATED_BASELINE_IDENTITY_BLOCKED",
                              "rank_ic": None, "score_controlled_increment": None}
                     for name in ("down_volume_share", "up_down_volume_ratio", "pullback_volume_decay_ratio",
                                  "RV20_T", "turnover_rate_pct", "turnover_x_RV_interaction")},
        "prospective_sanity": "NOT_RUN_BASELINE_GATE_FAILED",
        "decision_meaning": "Missing comparator evidence; no positive or negative ranking efficacy conclusion.",
        "next_decision": "Recover exact historical baseline evidence before Ranking validation; no Wave study started.",
        "product_paths_still_open": ["Existing Formal B daily path", "Existing three report observations",
                                     "Genuine prospective capture under existing contracts"],
        "boundaries": {"new_outcome_values_accessed": False, "models_fitted": False,
                       "provider_calls": 0, "final_oos_read": False, "production_semantics_changed": False,
                       "runtime_state_modified": False, "wave_research_started": False},
        "reproducibility_command": "python scripts/b_candidate_ranking_volume_turnover_v1.py",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(OUTPUT))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    # Bounded audit output: never overwrite production or other frozen artifacts.
    output = args.output.resolve()
    allowed = (root / Path(OUTPUT).parent).resolve()
    if output.parent != allowed or output.suffix != ".json":
        raise ValueError("output must be a JSON file in this research's validation directory")
    result = run(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": result["status"], "summary_sha256": file_sha256(output)}))


if __name__ == "__main__":
    main()
