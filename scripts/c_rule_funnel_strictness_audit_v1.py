"""Outcome-blind audit of retained real C reports; missing inputs stay null.

Reads only data/reports/c_daily from an explicit Git revision. Never loads
trackers, outcomes, provider data, historical reconstructions or Final OOS.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
from datetime import date
import csv
import hashlib
from html import unescape
import io
import json
from pathlib import Path
import re
import subprocess
from typing import Any

from c_pre_outcome_design import RULE_CANDIDATES


STUDY = "C_RULE_FUNNEL_STRICTNESS_AUDIT_V1"
RUNTIME_SHA = "ebe014748cfd3a551b0e3589124e08b2c154871d"
BASE_SHA = "334f636a98c17d31c3f3251b8ce3d3859132c3b7"
PROTOCOL_COMMIT = "bedb730"
ROOT = "data/reports/c_daily"
RULES = tuple(RULE_CANDIDATES)
UNAVAILABLE = "NOT_RUN_INPUTS_UNAVAILABLE"
SUCCESS = {"C_SUCCESS_WITH_MATCHES", "C_SUCCESS_NO_MATCH"}
STAGES = (
    "F0_UNIVERSE", "F1_HISTORY", "F2_TREND", "F3_HIGHER_LOW_PIVOT",
    "F4_DEPTH_TIME", "F5_REBOUND", "F6_T_CONFIRMATION", "F7_SUPPORT", "F8_MATCH",
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")


def git(repo: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True).stdout


def _bool(value: str) -> bool | None:
    return {"True": True, "False": False, "—": None}[value]


def parse_matched_diagnostics(html: bytes, signal_date: str) -> list[dict[str, Any]]:
    """Extract only aggregate booleans/statuses, never rounded numeric margins."""
    rows = []
    for article in re.findall(r'''<article class=(?:"c-stock-card"|'card')>(.*?)</article>''',
                              html.decode("utf-8"), flags=re.S):
        symbol = re.search(r'<span class="c-stock-symbol">(\d{6})</span>', article)
        legacy = symbol is None
        if legacy:
            symbol = re.search(r'<h3>(\d{6}) ', article)
        if symbol is None:
            raise ValueError("unrecognized matched stock card")
        rules = {}
        for rule in RULES:
            block = re.search(r'<p><strong>' + rule + r'</strong> · 事件身份.*?'
                              r'(?=<p><strong>|<p>来源：|$)', article, re.S)
            if legacy:
                block = re.search(r'<section class="rule"><h4>' + rule +
                                  r' .*?</section>', article, re.S)
            if block is None:
                raise ValueError(f"missing matched-card diagnostic: {rule}")
            text = unescape(re.sub(r"<[^>]+>", "", block.group()))
            trend = re.search(r"趋势：([^；]+)；均线顺序 (True|False|—)；"
                              r"收盘高于快线 (True|False|—)；趋势合格 (True|False|—)", text)
            structure = re.search(r"回踩：([^；]+)；", text)
            confirm = re.search(r"反弹确认：(True|False|—)；.*?支撑判定 (True|False|—)", text)
            match = re.search(r"判定 ([^；]+)；", text)
            if not all((trend, structure, confirm)) or (not legacy and not match):
                raise ValueError("incomplete rendered rule diagnostic")
            match_status = ("PRICE_STRUCTURE_MATCH_VOLUME_GATE_UNVERIFIED"
                            if "价格结构研究匹配" in text else "RULE_NOT_MATCHED") if legacy else match[1]
            rules[rule] = {
                "research_match_status": match_status, "trend_status": trend[1],
                "ma_order_ok": _bool(trend[2]),
                "close_above_fast_average": _bool(trend[3]),
                "trend_qualified": _bool(trend[4]),
                "structure_status": structure[1],
                "confirmation_qualified": _bool(confirm[1]),
                "entry_support_ok": _bool(confirm[2]),
            }
        rows.append({"signal_date": signal_date, "symbol": symbol[1], "rules": rules,
                     "scope": "SELECTED_UNION_MATCHES_ONLY"})
    if len({row["symbol"] for row in rows}) != len(rows):
        raise ValueError("duplicate symbol in dated C report")
    return sorted(rows, key=lambda row: row["symbol"])


def _count(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("invalid report count")
    return value


def read_day(repo: Path, revision: str, path: str) -> tuple[dict, list, dict]:
    """Validate aliases, immutable version and counts before including a date."""
    raw = git(repo, "show", f"{revision}:{path}")
    manifest = json.loads(raw)
    day = date.fromisoformat(manifest["signal_date"]).strftime("%Y%m%d")
    if path != f"{ROOT}/{day}/manifest.json":
        raise ValueError("manifest date/path mismatch")
    if manifest.get("schema_version") != "C_DAILY_RESEARCH_WATCHLIST_V1":
        raise ValueError("unexpected C report schema")
    version = manifest["version_sha256"]
    if not re.fullmatch(r"[0-9a-f]{64}", version):
        raise ValueError("invalid C version")
    html_path = f"{ROOT}/{day}/index.html"
    html = git(repo, "show", f"{revision}:{html_path}")
    for name, expected in (("manifest.json", raw), ("index.html", html)):
        if git(repo, "show", f"{revision}:{ROOT}/{day}/{version}/{name}") != expected:
            raise ValueError("dated alias / immutable version mismatch")
    if sha(html) != manifest["html_sha256"]:
        raise ValueError("C HTML hash mismatch")
    total = _count(manifest["matched_stock_count"])
    counts = {rule: _count(manifest["matched_by_rule"][rule]) for rule in RULES}
    if not max(counts.values()) <= total <= sum(counts.values()):
        raise ValueError("invalid union match count")
    status = manifest.get("c_status")
    status_source = "MANIFEST"
    if status is None:
        # The first genuine report predates c_status; retained pending counters
        # must explicitly be zero before its counts can enter success statistics.
        rendered = html.decode("utf-8")
        if not all(f"{rule} 数据待核验 0" in rendered for rule in RULES):
            raise ValueError("legacy report has no verified success status")
        status = "C_SUCCESS_WITH_MATCHES" if total else "C_SUCCESS_NO_MATCH"
        status_source = "RECOVERED_FROM_HTML_EXPLICIT_ZERO_PENDING_COUNTS"
    if (status == "C_SUCCESS_NO_MATCH" and total != 0
            or status == "C_SUCCESS_WITH_MATCHES" and total == 0):
        raise ValueError("C success status / count mismatch")
    detail = parse_matched_diagnostics(html, manifest["signal_date"])
    if len(detail) != total:
        raise ValueError("rendered stock count / manifest mismatch")
    for rule in RULES:
        actual = sum(row["rules"][rule]["research_match_status"] ==
                     "PRICE_STRUCTURE_MATCH_VOLUME_GATE_UNVERIFIED" for row in detail)
        if actual != counts[rule]:
            raise ValueError("rendered rule count / manifest mismatch")
    coverage = manifest.get("coverage_breakdown") or {}
    row = {
        "signal_date": manifest["signal_date"],
        "b_evaluated": _count(coverage["b_evaluated"]),
        "c_eligible_universe": None,
        "c_eligible_status": "NOT_RECOVERABLE_FROM_AGGREGATE_COUNTS",
        "balanced_matched": counts["BALANCED_A"],
        "conservative_matched": counts["CONSERVATIVE_B"],
        "total_matched": total, "c_status": status,
        "c_status_source": status_source,
        "coverage_status": manifest["coverage_status"],
        "coverage_breakdown": coverage, "gaps": manifest.get("gaps", []),
        "package_sha256": manifest["package_sha256"],
        "prospective_captured": manifest["prospective_captured"],
        "input_status": manifest["input_status"],
    }
    identity = {"signal_date": row["signal_date"], "manifest_path": path,
                "manifest_sha256": sha(raw), "html_path": html_path,
                "html_sha256": sha(html), "version_sha256": version,
                "package_sha256": manifest["package_sha256"]}
    return row, detail, identity


def frequency(rows: list[dict]) -> dict:
    successful = [row for row in rows if row["c_status"] in SUCCESS]
    n = len(successful)
    denominator = sum(row["b_evaluated"] for row in successful)
    total = sum(row["total_matched"] for row in successful)
    return {
        "recorded_dates": len(rows), "successful_dates": n,
        "excluded_pending_failed_dates": len(rows) - n,
        "first_date": rows[0]["signal_date"] if rows else None,
        "last_date": rows[-1]["signal_date"] if rows else None,
        "matched_stock_dates": total,
        "average_per_successful_day": total / n if n else None,
        "zero_candidate_days": sum(row["total_matched"] == 0 for row in successful),
        "zero_candidate_day_fraction": (sum(row["total_matched"] == 0 for row in successful) / n
                                        if n else None),
        "b_evaluated_stock_dates": denominator,
        "by_rule": {rule: {
            "matched_stock_dates": sum(row[field] for row in successful),
            "positive_dates": sum(row[field] > 0 for row in successful),
            "positive_date_fraction": sum(row[field] > 0 for row in successful) / n if n else None,
            "matches_per_b_evaluated_proxy": (sum(row[field] for row in successful) / denominator
                                              if denominator else None),
            "matches_per_c_eligible": None,
        } for rule, field in (("BALANCED_A", "balanced_matched"),
                              ("CONSERVATIVE_B", "conservative_matched"))},
    }


def selected_comparison(detail: list[dict]) -> dict:
    balanced = [row for row in detail if row["rules"]["BALANCED_A"]["research_match_status"] ==
                "PRICE_STRUCTURE_MATCH_VOLUME_GATE_UNVERIFIED"]
    c = [row["rules"]["CONSERVATIVE_B"] for row in balanced]
    return {
        "scope": "CONSERVATIVE_DIAGNOSTICS_CONDITIONAL_ON_BALANCED_MATCH",
        "denominator": len(c),
        "trend_status": dict(sorted(Counter(row["trend_status"] for row in c).items())),
        "structure_status": dict(sorted(Counter(row["structure_status"] for row in c).items())),
        "overlapping_gate_failures": {
            "trend_false": sum(row["trend_qualified"] is False for row in c),
            "ma_order_false": sum(row["ma_order_ok"] is False for row in c),
            "close_below_or_equal_fast": sum(row["close_above_fast_average"] is False for row in c),
            "structure_not_ok": sum(row["structure_status"] != "OK" for row in c),
            "confirmation_false_where_evaluated": sum(row["confirmation_qualified"] is False for row in c),
            "support_false_where_evaluated": sum(row["entry_support_ok"] is False for row in c),
        },
        "trend_false_but_structure_confirmation_support_pass": sum(
            row["trend_qualified"] is False and row["structure_status"] == "OK"
            and row["confirmation_qualified"] is True and row["entry_support_ok"] is True for row in c),
        "trend_pass_count": sum(row["trend_qualified"] is True for row in c),
        "sequential_after_trend": {
            "structure_status": dict(sorted(Counter(row["structure_status"] for row in c
                                                     if row["trend_qualified"] is True).items())),
        },
        "population_counterfactual_funnel": UNAVAILABLE,
        "local_near_miss_count": None,
        "caution": "Selected matches only; statuses conflate causes; no population or numeric-margin inference.",
    }


def build(repo: Path, revision: str, cutoff: str, limit: int = 40) -> tuple[dict, list, list]:
    cutoff = date.fromisoformat(cutoff).strftime("%Y%m%d")
    if not 1 <= limit <= 40:
        raise ValueError("limit must be 1..40")
    # Resolve before any reads: no accidental movement of a branch mid-analysis.
    revision = git(repo, "rev-parse", "--verify", revision + "^{commit}").decode().strip()
    files = git(repo, "ls-tree", "-r", "--name-only", revision, "--", ROOT).decode().splitlines()
    paths = sorted(path for path in files if re.fullmatch(ROOT + r"/\d{8}/manifest.json", path)
                   and path.split("/")[-2] <= cutoff)[-limit:]
    if not paths:
        raise ValueError("no dated C records")
    days, details, identities = [], [], []
    for path in paths:
        row, detail, identity = read_day(repo, revision, path)
        days.append(row)
        details.extend(detail)
        identities.append(identity)
    stats = frequency(days)
    summary = {
        "schema_version": STUDY, "classification": "research question / STRICT PATH",
        "decision": "NEEDS_MORE_EVIDENCE",
        "overall_decision": "C_SCARCITY_CAUSE_NEEDS_MORE_EVIDENCE",
        "conservative_decision": "C_CONSERVATIVE_B_STRICTNESS_NEEDS_MORE_EVIDENCE",
        "CONSERVATIVE_B_ZERO_MATCH_DOMINANT_CAUSE": "UNRESOLVED_POPULATION_INPUTS_UNAVAILABLE",
        "source": {"master_intake_sha": BASE_SHA, "runtime_state_sha": revision,
                   "cutoff": date.fromisoformat(f"{cutoff[:4]}-{cutoff[4:6]}-{cutoff[6:]}").isoformat(),
                   "requested_dates": limit, "protocol_commit": PROTOCOL_COMMIT,
                   "identities": identities},
        "frequency": stats,
        "distinct_matched_symbols": len({row["symbol"] for row in details}),
        "comparison_windows": {
            "first_ten_recorded_dates": frequency(days[:10]),
            "last_ten_recorded_dates": frequency(days[-10:]),
            "user_expectation_oct08_nov03": frequency([row for row in days
                                                       if "2026-10-08" <= row["signal_date"] <= "2026-11-03"]),
        },
        "daily": days,
        "frozen_rules": {rule: asdict(config) for rule, config in RULE_CANDIDATES.items()},
        "rule_source_sha256": sha(Path(__file__).with_name("c_pre_outcome_design.py").read_bytes()),
        "population_funnel": {rule: [
            {"stage": stage, "enter": None,
             "pass": stats["by_rule"][rule]["matched_stock_dates"] if stage == "F8_MATCH" else None,
             "status": "OBSERVED_FINAL_COUNT_ONLY" if stage == "F8_MATCH" else UNAVAILABLE}
            for stage in STAGES] for rule in RULES},
        "selected_matched_comparison": selected_comparison(details),
        "near_miss": {"status": UNAVAILABLE, "count": None},
        "threshold_margin_distributions": {"status": UNAVAILABLE, "values": None},
        "sensitivity": {"label": "CANDIDATE_COUNT_SENSITIVITY_ONLY", "status": UNAVAILABLE,
                        "new_candidate_count": None, "added": None, "lost": None,
                        "date_coverage_change": None},
        "population_top_three_bottlenecks": None,
        "market_vs_rule_decomposition": None,
        "next_relaxation_conditions": None,
        "required_evidence": "Original full-universe T-bound C observations and/or matching B frozen packages with identity/price timing proof; rejected symbols and full precision included.",
        "boundary": {"production_semantics_change": 0, "production_dispatch": 0,
                     "provider_calls": 0, "runtime_state_writes": 0,
                     "outcomes_read": False, "final_oos": "SEALED / UNREAD",
                     "volume_is_entry_gate": False, "score_created": False,
                     "historical_secondary_run": False},
    }
    return summary, days, details


def write_outputs(output: Path, summary: dict, days: list, details: list) -> None:
    output.mkdir(parents=True, exist_ok=True)
    stream = io.StringIO(newline="")
    columns = ("signal_date", "b_evaluated", "c_eligible_universe", "balanced_matched",
               "conservative_matched", "total_matched", "c_status", "coverage_status")
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    writer.writerows(days)
    payloads = {"daily.csv": (stream.getvalue().encode("utf-8"), len(days)),
                "selected_match_diagnostics.jsonl": (
                    b"".join((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
                             for row in details), len(details))}
    summary["artifacts"] = {}
    for name, (payload, count) in payloads.items():
        (output / name).write_bytes(payload)
        summary["artifacts"][name] = {"sha256": sha(payload), "bytes": len(payload), "rows": count}
    (output / "summary.json").write_bytes(json_bytes(summary))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--runtime-ref", default=RUNTIME_SHA)
    parser.add_argument("--cutoff", default="2026-11-04")
    parser.add_argument("--output", type=Path, default=Path("data/validation/c_rule_funnel_strictness_audit_v1"))
    args = parser.parse_args()
    summary, days, details = build(args.repo, args.runtime_ref, args.cutoff)
    write_outputs(args.output, summary, days, details)
    print(json.dumps({"decision": summary["decision"], "frequency": summary["frequency"],
                      "selected_comparison": summary["selected_matched_comparison"],
                      "summary_sha256": sha((args.output / "summary.json").read_bytes())}, ensure_ascii=False))


if __name__ == "__main__":
    main()
