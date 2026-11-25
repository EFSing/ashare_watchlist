"""Offline, outcome-blind B shortlist experiment; never a production buy list.

Read exactly one canonical list and its original structure/volume records from
Git. Rules were fixed in HANDOFF at 0f2d349 before inspecting these candidates.
No acquisition, holdings, delivery, historical outcomes or strategy changes.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
import math
from pathlib import Path
import subprocess
import tempfile

from typing import Any, Mapping

from b_breakout_retest_v1_1 import STRATEGY_SPEC_SHA256, STRATEGY_VERSION
import b_structure_volume_shadow as shadow
from b_structure_volume_observation import FIELDS, INVALID, TRANSITION, canonical, sha
from volume_observation import VOLUME_OBSERVATION_PROTOCOL_COMMIT_SHA, VOLUME_OBSERVATION_VERSION
from watchlist_schema import load_watchlist, validate_watchlist


VERSION = "B_SHORTLIST_PREVIEW_V1"
RULES_COMMIT = "0f2d349054df3cdc5f7756a59a83a82125f53890"
# Arithmetic tails of the same ratio must not invent dominance or tie order.
COMPARISON_DECIMALS = 12
ROOT = Path(__file__).resolve().parents[1]
STAGES = {
    "EARLY_PULLBACK": "回踩前段",
    TRANSITION: "回踩后重新走强（结构代理）",
    "POST_H1_CONTINUATION_PROXY": "已越过前高（结构代理）",
    INVALID: "结构待确认",
}
REASONS = {
    "SELECTED": "进入本次试验短名单",
    "OUTSIDE_COMPARISON_STAGE": "不在本轮比较的结构阶段",
    "V1_V2_UNAVAILABLE_OR_INVALID": "V1/V2 缺失、非法或带有缺失标记",
    "INVALID_REFERENCE_PRICES": "参考价格须满足 0 < 止损 < 触发价，且参考买价 < 目标",
    "LIMIT_REACHED": "按固定比较次序排在本次名额之后",
    "ACCOUNT_ALREADY_HOLDING": "已在单账户模拟持仓中，不重复占用重点名额",
    "ACCOUNT_SIGNAL_COOLDOWN": "近 5 个交易日内刚入选过，冷却期内不重复占重点名额",
    "ACCOUNT_PENDING_ORDER": "单账户已有未到期挂单观察中（10日内），不重复占重点名额",
    "ACCOUNT_EXIT_COOLDOWN": "单账户模拟仓位刚结案未满 5 个交易日，冷却期内不重复占重点名额",
    "ACCOUNT_PRIOR_UNRESOLVED": "单账户前序持仓因历史日线缺失待核验，暂不重复占重点名额",
}
ACCOUNT_REASON_MAP = {
    "ALREADY_HOLDING": "ACCOUNT_ALREADY_HOLDING",
    "RECENT_SIGNAL_COOLDOWN": "ACCOUNT_SIGNAL_COOLDOWN",
    "PENDING_ORDER_ACTIVE": "ACCOUNT_PENDING_ORDER",
    "RECENT_EXIT_COOLDOWN": "ACCOUNT_EXIT_COOLDOWN",
    "PRIOR_POSITION_UNRESOLVED": "ACCOUNT_PRIOR_UNRESOLVED",
}


def _finite(value) -> bool:
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value))


def build_preview(
    watchlist: dict,
    observations: dict,
    *,
    limit: int = 3,
    account_exclusions: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict:
    """Pure selection from identity-verified inputs, retaining every candidate."""
    if type(limit) is not int or limit not in (2, 3):
        raise ValueError("SHORTLIST_LIMIT_MUST_BE_2_OR_3")
    watch = validate_watchlist(watchlist)
    day = watch["date"]
    if watch["strategy_version"] != STRATEGY_VERSION or observations["signal_date"] != day:
        raise ValueError("SHORTLIST_DATE_OR_STRATEGY_MISMATCH")
    candidates = watch["candidates"]
    by_id = {row["signal_id"]: row for row in observations["rows"]}
    if (len(by_id) != len(observations["rows"])
            or set(by_id) != {c["signal_id"] for c in candidates}
            or len({c["code"] for c in candidates}) != len(candidates)):
        raise ValueError("SHORTLIST_CANDIDATE_SET_MISMATCH")
    rows = []
    for c in sorted(candidates, key=lambda item: item["code"]):
        observed = by_id[c["signal_id"]]
        stage = observed["structure"]["state"]
        volume = observed["volume"]
        if (observed["code"] != c["code"] or observed["signal_date"] != day
                or observed.get("formal_b_qualified") is not True
                or c["strategy_version"] != STRATEGY_VERSION or c["setup"] != "B_BREAKOUT_RETEST"
                or stage not in STAGES
                or observed.get("is_w2w3_transition") is not (stage == TRANSITION)
                or volume.get("observation_version") != VOLUME_OBSERVATION_VERSION
                or volume.get("protocol_commit_sha") != VOLUME_OBSERVATION_PROTOCOL_COMMIT_SHA):
            raise ValueError("SHORTLIST_OBSERVATION_IDENTITY_MISMATCH")
        missing = {field: volume.get("missing_reason", {}).get(field) for field in FIELDS}
        values = {}
        for field in FIELDS:
            value = volume.get(field)
            values[field] = value if _finite(value) else None
            if value is not None and not _finite(value):
                missing[field] = missing[field] or "NON_FINITE_OR_NON_NUMERIC_VALUE"
            elif value is None:
                missing[field] = missing[field] or "MISSING_VALUE"
        # Ignore unrelated inputs (including Score and frozen cohort coordinates).
        row = {"signal_id": c["signal_id"], "code": c["code"], "name": c["name"],
               "structure_state": stage, "selected": False, "comparison_order": None,
               "front": None, "dominated_by": [], "reasons": [],
               "volume": values,
               "volume_missing_reason": missing, "window_days": volume.get("window_days"),
               "target_type": c.get("target_type", "UNKNOWN"),
               "prices": {field: c[field] for field in ("price", "trigger", "stop", "target")},
               "reference_entry": max(c["price"], c["trigger"]),
               "reference_risk_fraction": None, "reference_reward_risk": None}
        entry, stop, target = row["reference_entry"], c["stop"], c["target"]
        if 0 < stop < c["trigger"] <= entry < target:
            risk, reward_risk = (entry - stop) / entry, (target - entry) / (entry - stop)
            if _finite(risk) and _finite(reward_risk):
                row["reference_risk_fraction"] = risk
                row["reference_reward_risk"] = reward_risk
        if row["reference_reward_risk"] is None:
            row["reasons"].append("INVALID_REFERENCE_PRICES")
        v1, v2 = (volume.get(field) for field in FIELDS[:2])
        if not (_finite(v1) and 0 <= v1 <= 1 and _finite(v2) and v2 >= 0
                and not any(missing[field] for field in FIELDS[:2])):
            row["reasons"].append("V1_V2_UNAVAILABLE_OR_INVALID")
        if stage != TRANSITION:
            row["reasons"].append("OUTSIDE_COMPARISON_STAGE")
        if account_exclusions is not None and c["code"] in account_exclusions:
            exclusion = dict(account_exclusions[c["code"]])
            mapped_reason = ACCOUNT_REASON_MAP.get(
                str(exclusion.get("skip_reason") or ""), "ACCOUNT_SIGNAL_COOLDOWN"
            )
            row["reasons"].insert(0, mapped_reason)
            row["account_exclusion"] = exclusion
        rows.append(row)

    eligible = [row for row in rows if not row["reasons"]]

    def vector(row):
        # All four coordinates below point toward the hypothesized preference.
        return tuple(round(value, COMPARISON_DECIMALS) for value in
                     (-row["volume"][FIELDS[0]], row["volume"][FIELDS[1]],
                      -row["reference_risk_fraction"], row["reference_reward_risk"]))

    def dominates(a, b):
        pairs = list(zip(vector(a), vector(b)))
        return all(x >= y for x, y in pairs) and any(x > y for x, y in pairs)

    for row in eligible:
        row["dominated_by"] = [other["code"] for other in eligible if dominates(other, row)]
    remaining = eligible[:]
    ordered = []
    front_number = 0
    while remaining:
        front_number += 1
        remaining_codes = {row["code"] for row in remaining}
        front = [row for row in remaining if not remaining_codes.intersection(row["dominated_by"])]
        front.sort(key=lambda row: (-vector(row)[3], -vector(row)[2], row["code"]))
        for row in front:
            row["front"] = front_number
            row["comparison_order"] = len(ordered) + 1
            row["selected"] = len(ordered) < limit
            row["reasons"] = ["SELECTED" if row["selected"] else "LIMIT_REACHED"]
            ordered.append(row)
        remaining = [row for row in remaining if row not in front]

    coverage = watch.get("input_coverage", {})
    payload = {"schema_version": VERSION, "signal_date": day, "mode": "OFFLINE_AS_OF_REPLAY",
               "evidence_status": "NEEDS_MORE_EVIDENCE", "production_validated": False,
               "outcome_accessed": False, "limit": limit,
               "rules_commit": RULES_COMMIT, "candidate_count": len(rows),
               "eligible_count": len(eligible), "selected_codes": [r["code"] for r in ordered[:limit]],
               "input_coverage": {key: coverage.get(key) for key in
                                  ("coverage_status", "evaluated_symbol_count", "excluded_symbol_count")},
               "market_grade": watch["market_env"].get("grade"),
               "preference_hypotheses": {FIELDS[0]: "LOWER", FIELDS[1]: "HIGHER",
                                         "reference_risk_fraction": "LOWER", "reference_reward_risk": "HIGHER"},
               "selection_method": "PARETO_FRONTS_THEN_REWARD_RISK_DESC_RISK_ASC_CODE_ASC",
               "comparison_decimal_places": COMPARISON_DECIMALS,
               "rows": rows}
    if account_exclusions is not None:
        payload["account_dedup_enabled"] = True
        payload["account_excluded_codes"] = [r["code"] for r in rows if "account_exclusion" in r]
    return payload


def _git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT, stderr=subprocess.PIPE)


def load_inputs(day: str, runtime_ref: str) -> tuple[dict, dict, dict]:
    """Verify original hashes and historical source identities; no data replay."""
    if date.fromisoformat(day).isoformat() != day:
        raise ValueError("SHORTLIST_CANONICAL_DATE_REQUIRED")
    commit = _git("rev-parse", "--verify", "--end-of-options", f"{runtime_ref}^{{commit}}").decode().strip()
    token = day.replace("-", "")
    paths = [f"data/watchlist_{token}.json",
             f"{shadow.RELATIVE_ROOT.as_posix()}/daily/{token}.json",
             f"{shadow.RELATIVE_ROOT.as_posix()}/observations/{token}.json"]
    blobs = {path: _git("show", f"{commit}:{path}") for path in paths}
    with tempfile.TemporaryDirectory(prefix="b-shortlist-input-") as temp:
        root = Path(temp)
        for path, raw in blobs.items():
            dest = root / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
        receipt, observations = shadow.verify_artifacts(root, day)
        if receipt.get("watchlist_sha256") != sha(blobs[paths[0]]):
            raise ValueError("SHORTLIST_WATCHLIST_HASH_MISMATCH")
        watch = load_watchlist(root / paths[0])
    if receipt.get("strategy_spec_sha256") != STRATEGY_SPEC_SHA256:
        raise ValueError("SHORTLIST_STRATEGY_SPEC_MISMATCH")
    identity = receipt["feature_identity"]
    expected = shadow.feature_identity()
    if ({k: v for k, v in identity.items() if k != "source_lf_sha256"}
            != {k: v for k, v in expected.items() if k != "source_lf_sha256"}
            or set(identity["source_lf_sha256"]) != set(expected["source_lf_sha256"])):
        raise ValueError("SHORTLIST_FEATURE_IDENTITY_MISMATCH")
    generation = receipt["generation_commit"]
    shadow._verify_generation_protocol(generation)
    for name, expected_hash in identity["source_lf_sha256"].items():
        if sha(_git("show", f"{generation}:scripts/{name}").replace(b"\r\n", b"\n")) != expected_hash:
            raise ValueError("SHORTLIST_HISTORICAL_SOURCE_MISMATCH")
    source = {"runtime_commit": commit, "generation_commit": generation,
              "input_sha256": {path: sha(raw) for path, raw in blobs.items()},
              "feature_identity": identity, "strategy_spec_sha256": STRATEGY_SPEC_SHA256,
              "preview_source_lf_sha256": sha(Path(__file__).read_bytes().replace(b"\r\n", b"\n")),
              "verification": "ORIGINAL_RECORD_HASHES_AND_HISTORICAL_SOURCE_IDENTITIES",
              "raw_bars_recomputed": False}
    return watch, observations, source


def render_markdown(preview: dict) -> str:
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")

    def number(value, *, percent=False):
        if value is None:
            return "缺失"
        return f"{value:.2%}" if percent else f"{value:.3f}"

    selected = sorted((r for r in preview["rows"] if r["selected"]), key=lambda r: r["comparison_order"])
    coverage = preview["input_coverage"]
    lines = [f"# B 候选试验短名单 · {preview['signal_date']}", "",
             f"**{preview['candidate_count']} 只正式候选 → {preview['eligible_count']} 只可比较 → "
             f"{len(selected)} 只入选（上限 {preview['limit']}）**。", "",
             "这是现在按当日已保存信息计算的离线重放，不是当时已记录的前瞻选择。"
             "优选收益仍为 NEEDS_MORE_EVIDENCE，不能据此宣称这几只未来收益最好。", "",
             f"原始覆盖：{coverage['coverage_status'] or 'UNKNOWN'}；已评估 "
             f"{coverage['evaluated_symbol_count']}，排除 {coverage['excluded_symbol_count']}；"
             f"原始市场分级：{preview['market_grade'] or 'UNKNOWN'}（仅展示，未用于选择）。", "",
             "## 本轮入选", "",
             "| 次序 | 股票 | V1 下跌量占比 | V2 涨跌日均量比 | 参考风险距离 | 参考收益风险比 | 比较层 |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in selected:
        lines.append(f"| {r['comparison_order']} | {r['code']} {cell(r['name'])} | "
                     f"{number(r['volume'][FIELDS[0]], percent=True)} | {number(r['volume'][FIELDS[1]])} | "
                     f"{number(r['reference_risk_fraction'], percent=True)} | "
                     f"{number(r['reference_reward_risk'])} | {r['front']} |")
    if not selected:
        lines += ["", "本轮没有符合比较条件的候选，不补足名额。"]
    elif (len(selected) > 1 and len({r["front"] for r in selected}) == 1
          and len({round(r["reference_reward_risk"], COMPARISON_DECIMALS) for r in selected}) == 1):
        lines += ["", "本轮入选者在同一比较层，参考收益风险比相同，因此次序由参考风险距离决定；"
                  "这不表示其量能表现全面领先。"]
    lines += ["", "## 为什么这样选", "",
              "先限于‘回踩后重新走强’的结构代理阶段，并要求 V1/V2 可用、参考价格关系合法。"
              "四个暂定偏好是：V1 较低、V2 较高、参考风险距离较低、参考收益风险比较高。", "",
              "第一层保留没有被另一只在四项上同时不差、且至少一项更好地超过的候选；"
              "移除该层后重复比较。同层存在取舍，按参考收益风险比降序、风险距离升序、代码升序取到上限。"
              "同层次序是未验证的操作约定，不表示胜率更高；V3 只展示，旧 Score 不参与。", "",
              "参考买价 = max(T 日收盘价, 原 Trigger)；风险距离 = (参考买价 − Stop) / 参考买价；"
              "收益风险比 = (Target − 参考买价) / (参考买价 − Stop)。"
              "不含费用与滑点，也不代表次日成交价、最高买价或实际损失上限。"
              "目标由原策略规则给出，收益风险比不是收益预测；若目标均按同一风险倍数生成，此项不提供额外区分。"
              "比较统一保留 12 位小数以消除浮点尾差，原值仍保留在 JSON。", "",
              "## 全部候选与原因", "",
              "| 股票 | 结构阶段 | 次序 / 层 | V1 | V2 | V3（不参与） | 参考买价 / 止损 / 目标 | 原因 |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in preview["rows"]:
        values = []
        for field in FIELDS:
            value = number(r["volume"][field], percent=field == FIELDS[0])
            if r["volume_missing_reason"][field]:
                value += f" ({r['volume_missing_reason'][field]})"
            values.append(cell(value))
        reason = "；".join(REASONS[key] for key in r["reasons"])
        if r["dominated_by"]:
            reason += "；四项比较被 " + ", ".join(r["dominated_by"]) + " 超过"
        order = f"{r['comparison_order']} / {r['front']}" if r["front"] else "不比较"
        prices = f"{r['reference_entry']:.2f} / {r['prices']['stop']:.2f} / {r['prices']['target']:.2f}"
        lines.append(f"| {r['code']} {cell(r['name'])} | {STAGES[r['structure_state']]} | {order} | "
                     + " | ".join(values) + f" | {prices} | {cell(reason)} |")
    lines += ["", "## 使用边界与复现", "",
              "这是候选筛选试验，尚未纳入实际持仓、跨日去重、行业集中度和成交约束，不能直接当作每日购入清单。"
              "此处仅复核原始记录及其源码身份，未重算原始 K 线；没有读取后续涨跌。", "",
              f"规则预先记录于 `{preview['rules_commit']}` 的 HANDOFF；"
              "输入提交与逐文件校验值保存在同名 JSON。"]
    if "source" in preview:
        lines += ["", "```powershell",
                  f"python scripts/preview_b_shortlist.py --date {preview['signal_date']} "
                  f"--runtime-ref {preview['source']['runtime_commit']} --limit {preview['limit']} "
                  "--output-dir docs/examples", "```"]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    parser.add_argument("--runtime-ref", default="origin/runtime-state")
    parser.add_argument("--limit", type=int, choices=(2, 3), default=3)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output_dir.resolve()
    if output.is_relative_to(ROOT / "data") or {".git", "final_oos", "continuous_speed_probe"}.intersection(
            p.lower() for p in output.parts):
        parser.error("预览须写入独立目录，不能写入生产 data、Git 或封存研究目录")
    watch, observations, source = load_inputs(args.date, args.runtime_ref)
    preview = build_preview(watch, observations, limit=args.limit)
    preview["source"] = source
    output.mkdir(parents=True, exist_ok=True)
    stem = f"b_shortlist_preview_{args.date.replace('-', '')}_top{args.limit}"
    json_path, md_path = output / f"{stem}.json", output / f"{stem}.md"
    if json_path.is_symlink() or md_path.is_symlink():
        parser.error("预览输出不能是符号链接")
    json_path.write_bytes(canonical(preview))
    md_path.write_text(render_markdown(preview), encoding="utf-8", newline="\n")
    print(json.dumps({"status": "OFFLINE_PREVIEW_WRITTEN", "selected_codes": preview["selected_codes"],
                      "json": str(json_path), "markdown": str(md_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
