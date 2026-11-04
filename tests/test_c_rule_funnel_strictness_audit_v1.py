"""Retained-report audit: integrity, population limits and missingness."""

from copy import deepcopy
import json
import subprocess

import pytest

import c_rule_funnel_strictness_audit_v1 as audit


def diagnostic(rule, *, matched=False, trend=True, structure="OK", confirmation=True):
    state = "PRICE_STRUCTURE_MATCH_VOLUME_GATE_UNVERIFIED" if matched else "RULE_NOT_MATCHED"
    return (f'<p><strong>{rule}</strong> · 事件身份 <code>synthetic</code></p>'
            f'<p>判定 {state}；原因 synthetic。</p>'
            f'<p>趋势：OK；均线顺序 True；收盘高于快线 True；趋势合格 {trend}。</p>'
            f'<p>回踩：{structure}；深度 0.12。</p>'
            f'<p>反弹确认：{confirmation}；支撑参考 synthetic；支撑判定 True。</p>')


def report(*, overlap=False):
    return ('<article class="c-stock-card"><span class="c-stock-symbol">600001</span>'
            + diagnostic("BALANCED_A", matched=True)
            + diagnostic("CONSERVATIVE_B", matched=overlap, trend=overlap)
            + '<p>来源：synthetic</p></article>').encode()


@pytest.fixture
def repository(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    for args in (("init",), ("config", "user.email", "test@example.invalid"),
                 ("config", "user.name", "Synthetic audit test")):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    return repo


def add_day(repo, day, *, html=None, balanced=0, conservative=0, total=0,
            status="C_SUCCESS_NO_MATCH", legacy_status=False):
    html = b"<html>synthetic empty report</html>" if html is None else html
    manifest = {
        "schema_version": "C_DAILY_RESEARCH_WATCHLIST_V1", "signal_date": day,
        "version_sha256": "a" * 64, "package_sha256": "b" * 64,
        "html_sha256": audit.sha(html), "matched_stock_count": total,
        "matched_by_rule": {"BALANCED_A": balanced, "CONSERVATIVE_B": conservative},
        "coverage_breakdown": {"b_evaluated": 100, "c_st_or_rule_excluded": 8},
        "coverage_status": "PARTIAL_UNVERIFIED", "gaps": ["SYNTHETIC_GAP"],
        "prospective_captured": False, "input_status": "PRICE_OBSERVATION_VOLUME_UNVERIFIED",
    }
    if not legacy_status:
        manifest["c_status"] = status
    root = repo / audit.ROOT / day.replace("-", "")
    for folder in (root, root / manifest["version_sha256"]):
        folder.mkdir(parents=True)
        (folder / "manifest.json").write_bytes(audit.json_bytes(manifest))
        (folder / "index.html").write_bytes(html)
    return root


def commit(repo):
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "synthetic"],
                   check=True, capture_output=True)


def test_unique_dates_union_counts_cutoff_and_null_population(repository, tmp_path):
    add_day(repository, "2026-10-08", html=report(overlap=True), balanced=1,
            conservative=1, total=1, status="C_SUCCESS_WITH_MATCHES")
    add_day(repository, "2026-10-09")
    add_day(repository, "2026-11-05")
    commit(repository)
    summary, days, details = audit.build(repository, "HEAD", "2026-11-04")
    assert len(days) == 2  # immutable version and alias are the same date
    assert summary["frequency"]["matched_stock_dates"] == 1  # not 1+1
    assert summary["frequency"]["average_per_successful_day"] == 0.5
    assert summary["frequency"]["zero_candidate_day_fraction"] == 0.5
    assert all(day["c_eligible_universe"] is None for day in days)
    assert summary["population_funnel"]["BALANCED_A"][2]["pass"] is None
    assert summary["near_miss"]["count"] is None
    assert summary["sensitivity"]["added"] is None
    assert summary["overall_decision"] == "C_SCARCITY_CAUSE_NEEDS_MORE_EVIDENCE"
    first, second = tmp_path / "first", tmp_path / "second"
    audit.write_outputs(first, deepcopy(summary), days, details)
    audit.write_outputs(second, deepcopy(summary), days, details)
    assert {p.name: p.read_bytes() for p in first.iterdir()} == {
        p.name: p.read_bytes() for p in second.iterdir()}


def test_pending_and_failure_are_not_zero_days(repository):
    add_day(repository, "2026-10-08", status="C_DATA_PENDING")
    add_day(repository, "2026-10-09", status="C_FAILED")
    commit(repository)
    summary, _, _ = audit.build(repository, "HEAD", "2026-11-04")
    assert summary["frequency"]["successful_dates"] == 0
    assert summary["frequency"]["average_per_successful_day"] is None
    assert summary["frequency"]["zero_candidate_day_fraction"] is None


@pytest.mark.parametrize("corruption", ["hash", "version", "count", "status"])
def test_report_corruption_fails_closed(repository, corruption):
    root = add_day(repository, "2026-10-08", html=report(), balanced=1,
                   total=1, status="C_SUCCESS_WITH_MATCHES")
    payload = json.loads((root / "manifest.json").read_bytes())
    if corruption == "hash":
        payload["html_sha256"] = "0" * 64
    elif corruption == "count":
        payload["matched_stock_count"] = 2
    elif corruption == "status":
        payload["c_status"] = "C_SUCCESS_NO_MATCH"
    for folder in (root, root / ("a" * 64)):
        (folder / "manifest.json").write_bytes(audit.json_bytes(payload))
    if corruption == "version":
        (root / "index.html").write_bytes(b"changed alias")
    commit(repository)
    with pytest.raises(ValueError):
        audit.build(repository, "HEAD", "2026-11-04")


def test_missing_legacy_status_requires_explicit_pending_evidence(repository):
    add_day(repository, "2026-09-24", legacy_status=True)
    commit(repository)
    with pytest.raises(ValueError, match="legacy report"):
        audit.build(repository, "HEAD", "2026-11-04")


def test_legacy_rendered_status_and_rounded_values_are_not_numeric_evidence(repository):
    html = ("<article class='card'><h3>600001 synthetic</h3>"
            + "".join(f'<section class="rule"><h4>{rule} <span>价格结构研究匹配</span></h4>'
                      '<p>趋势：OK；均线顺序 True；收盘高于快线 True；趋势合格 True。</p>'
                      '<p>回踩：OK；深度 0.12。</p><p>反弹确认：True；支撑判定 True。</p></section>'
                      for rule in audit.RULES)
            + '</article>BALANCED_A 数据待核验 0；CONSERVATIVE_B 数据待核验 0').encode()
    add_day(repository, "2026-09-24", html=html, balanced=1, conservative=1,
            total=1, legacy_status=True)
    commit(repository)
    summary, days, details = audit.build(repository, "HEAD", "2026-11-04")
    assert days[0]["c_status_source"].startswith("RECOVERED_FROM_HTML")
    assert summary["frequency"]["matched_stock_dates"] == 1
    assert "depth" not in details[0]["rules"]["BALANCED_A"]


def test_aggregate_trend_failure_is_not_one_local_near_miss():
    rows = audit.parse_matched_diagnostics(report(), "2026-10-08")
    comparison = audit.selected_comparison(rows)
    assert comparison["overlapping_gate_failures"]["trend_false"] == 1
    assert comparison["trend_false_but_structure_confirmation_support_pass"] == 1
    assert comparison["local_near_miss_count"] is None
    assert comparison["population_counterfactual_funnel"] == audit.UNAVAILABLE


def test_unrecognized_nonempty_card_does_not_silently_disappear():
    with pytest.raises(ValueError, match="missing matched-card diagnostic"):
        audit.parse_matched_diagnostics(
            b'<article class="c-stock-card"><span class="c-stock-symbol">600001</span></article>',
            "2026-10-08")
