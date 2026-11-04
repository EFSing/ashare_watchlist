"""Fixed, research-only B priority exploration; never imported by production."""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

import b_priority_w2w3_volume_v1 as strict
from b_candidate_ranking_volume_turnover_v1 import (
    ELIGIBILITY, IMPACT, QUALIFIED, file_sha256, scan_stream, verify_stream,
)

TASK = "B_PRIORITY_W2W3_VOLUME_EXPLORATORY_V0"
PROTOCOL = "docs/research/b_priority_w2w3_volume_exploratory_v0_protocol.md"
PROTOCOL_COMMIT = "f717b6e9e41f3ceb23a5bca8a19356923bfabeb2"
OUTPUT = "data/validation/b_priority_w2w3_volume_exploratory_v0"
REPORT = "docs/research/b_priority_w2w3_volume_exploratory_v0_report.md"
PROTOTYPE = "docs/examples/b_priority_prototype_v0.md"
TRANSITION = strict.STATES[1]
FIELDS = tuple(strict.FIELDS)
METRICS = ("return_pct", "positive_pct", "mfe_pct", "mae_pct")
YEARS = ("2023", "2024", "2025", "2026")
LABELS = ["DEVELOPMENT", "RECONSTRUCTED_RETROSPECTIVE", "EXPLORATORY",
          "LOW_CONFIDENCE", "NOT_PRODUCTION_VALIDATED"]


def canonical(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode()


def load_inputs(root: Path) -> tuple[pd.DataFrame, list[dict], dict]:
    locked = strict.git_bytes(root, "show", f"{PROTOCOL_COMMIT}:{PROTOCOL}")
    if locked.replace(b"\r\n", b"\n") != (root / PROTOCOL).read_bytes().replace(b"\r\n", b"\n"):
        raise RuntimeError("exploratory protocol changed after pre-outcome lock")
    summary_path = root / strict.OUTPUT / "summary.json"
    if file_sha256(summary_path) != "beebccfe664c53f6738404fa25644432f9bd6c2446bd59b19ec86031f19332a5":
        raise RuntimeError("strict frozen summary changed")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    detail = root / summary["detail"]["path"]
    if file_sha256(detail) != summary["detail"]["sha256"] or detail.stat().st_size != summary["detail"]["bytes"]:
        raise RuntimeError("frozen reconstructed feature bytes mismatch")
    with gzip.open(detail, "rb") as stream:
        payload = stream.read()
    if hashlib.sha256(payload).hexdigest() != summary["detail"]["content_stream_sha256"]:
        raise RuntimeError("feature content mismatch")
    features = [json.loads(line) for line in payload.splitlines()]
    keys = [(r["symbol"], r["signal_date"], r["setup_id"]) for r in features]
    if len(keys) != len(set(keys)) or len(keys) != 17714:
        raise RuntimeError("feature identities duplicated or missing")
    audit, identities = scan_stream(root / QUALIFIED, identities=True)
    eligibility = json.loads((root / ELIGIBILITY).read_text(encoding="utf-8"))
    impact = json.loads((root / IMPACT).read_text(encoding="utf-8"))
    verify_stream(audit, eligibility["artifacts"]["event_results"])
    if (set(keys) != identities or audit["file_sha256"] != impact["old_reconstruction"]["event_artifact_sha256"]
            or impact["decision"] != "ELIGIBILITY_ARTIFACT_EVENT_SET_INVARIANT"
            or impact["corrected_reconstruction"]["spec_sha256"] != strict.STRATEGY_SPEC_SHA256
            or impact["comparison"]["qualification_event_membership_differences"] != 0
            or not impact["comparison"]["corrected_projection_shared_callable_identity"]
            or eligibility["scope"]["price_semantics"] != "CORPORATE_ACTION_ADJUSTED_OUTCOME_PATH_AFFINE_V1"):
        raise RuntimeError("frozen B membership/outcome provenance mismatch")
    outcomes = {}
    statuses = {h: {} for h in ("5D", "10D")}
    with gzip.open(root / QUALIFIED, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            key = tuple(row[k] for k in ("symbol", "signal_date", "setup_id"))
            if row["as_of_date"] != row["signal_date"] or row["entry_date"] != row["earliest_execution_date"]:
                raise RuntimeError("frozen outcome timing identity mismatch")
            outcomes[key] = row["outcomes"]
            for h in statuses:
                status = row["outcomes"][h]["status"]
                statuses[h][status] = statuses[h].get(status, 0) + 1
    records = []
    for r, key in zip(features, keys):
        item = {k: r[k] for k in ("symbol", "signal_date", "setup_id", "board", "breakout_date")}
        item.update(structure_state=r["structure"]["state"], **{f: r["volume"][f] for f in FIELDS})
        for h in statuses:
            outcome = outcomes[key][h]
            available = outcome["status"] == "AVAILABLE"
            for metric in ("return_pct", "mfe_pct", "mae_pct"):
                value = outcome[metric]
                if available and (value is None or not np.isfinite(value)):
                    raise RuntimeError("nonfinite available outcome")
                item[f"{h}_{metric}"] = value if available else None
        records.append(item)
    frame = pd.DataFrame(records).sort_values(["signal_date", "symbol", "setup_id"]).reset_index(drop=True)
    counts = frame.groupby("board").size().to_dict()
    complete = frame.dropna(subset=list(FIELDS))
    common = complete[(complete.board == "Main") & (complete.structure_state != strict.INVALID)]
    if counts != {"Main": 10779, "ChiNext": 4416, "STAR": 1813, "OUT_OF_SCOPE_PREFIX": 706} or len(common) != 7541:
        raise RuntimeError("frozen cohort counts changed")
    return frame, features, {"qualified": audit, "feature_detail": summary["detail"],
                             "strict_summary_sha256": file_sha256(summary_path),
                             "causality_reused": summary["causality"], "outcome_statuses": statuses,
                             "outcome_route": "EXISTING_FROZEN_B_V2_ADJUSTED_OUTCOMES",
                             "outcome_contract": eligibility["scope"],
                             "boards": summary["boards"]}


def quality(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    counts = result.groupby("signal_date")["symbol"].transform("size")
    points = []
    for f in FIELDS:
        rank = result.groupby("signal_date")[f].rank(method="average")
        valid_counts = result.groupby("signal_date")[f].transform("count")
        good_points = rank if f == "up_down_volume_ratio" else valid_counts - rank
        result[f"good_{f}"] = good_points / valid_counts
        points.append(good_points)
    # Ordinal ties are exact half integers. Sum before division so mathematically
    # equal composites remain exact ties instead of depending on float addition.
    # The composite is used only on complete cases, where all counts agree.
    result["volume_quality"] = (points[0] + points[1] + points[2]) / (3 * counts)
    return result


def order_score(frame: pd.DataFrame, method: str) -> np.ndarray:
    if method == "R3":
        # quality is in [0,1]; the +2 fixes transition precedence without fitting.
        return frame.volume_quality.to_numpy() + 2 * (frame.structure_state == TRANSITION).to_numpy()
    return frame["volume_quality" if method == "R2" else f"good_{method}"].to_numpy()


def top_weights(score: np.ndarray, k: int) -> np.ndarray:
    boundary = np.sort(score)[-k]
    above, equal = score > boundary, score == boundary
    return (above.astype(float) + equal * ((k - above.sum()) / equal.sum())) / k


def bootstrap_means(values: np.ndarray) -> list[list[float | None]]:
    """Joint date resampling preserves selected/baseline/uplift pairing."""
    if len(values) == 0:
        return [[None, None] for _ in range(values.shape[1])]
    rng = np.random.default_rng(20261104)
    draws = []
    for start in range(0, 10000, 250):
        indices = rng.integers(0, len(values), (min(250, 10000 - start), len(values)))
        draws.append(values[indices].mean(axis=1))
    return np.quantile(np.concatenate(draws), [0.025, 0.975], axis=0).T.tolist()


def describe(daily: pd.DataFrame) -> dict:
    if daily.empty:
        return {"eligible_dates": 0, "candidate_rows": 0, "mean": None,
                "median": None, "return_ci95": [None, None]}
    return {"eligible_dates": len(daily), "candidate_rows": int(daily["n"].sum()),
            "mean_candidates": float(daily["n"].mean()),
            "mean": {m: float(daily[m].mean()) for m in METRICS},
            "median": {m: float(daily[m].median()) for m in METRICS},
            "return_ci95": bootstrap_means(daily[["return_pct"]].to_numpy())[0]}


def paired(daily: pd.DataFrame) -> dict:
    if daily.empty:
        return {"eligible_dates": 0, "candidate_rows": 0, "selected": None,
                "baseline": None, "uplift": None, "uplift_ci95": [None, None]}
    selected = daily[list(METRICS)]
    baseline = daily[[f"base_{m}" for m in METRICS]].copy()
    baseline.columns = list(METRICS)
    delta = selected - baseline
    ci = bootstrap_means(np.column_stack((selected.return_pct, baseline.return_pct, delta.return_pct)))
    return {"eligible_dates": len(daily), "candidate_rows": int(daily.n.sum()),
            "mean_candidates": float(daily.n.mean()),
            "selected": {m: float(selected[m].mean()) for m in METRICS},
            "baseline": {m: float(baseline[m].mean()) for m in METRICS},
            "uplift": {m: float(delta[m].mean()) for m in METRICS},
            "median_selected": {m: float(selected[m].median()) for m in METRICS},
            "median_uplift": {m: float(delta[m].median()) for m in METRICS},
            "selected_return_ci95": ci[0], "baseline_return_ci95": ci[1], "uplift_ci95": ci[2]}


def by_year(daily: pd.DataFrame, function) -> dict:
    return {"overall": function(daily), "years": {
        y: function(daily[daily.signal_date.str.startswith(y)]) if not daily.empty else function(daily)
        for y in YEARS}}


def metrics_for(frame: pd.DataFrame, horizon: str) -> pd.DataFrame:
    f = frame.dropna(subset=[f"{horizon}_{m}" for m in ("return_pct", "mfe_pct", "mae_pct")]).copy()
    for m in ("return_pct", "mfe_pct", "mae_pct"):
        f[m] = f[f"{horizon}_{m}"]
    f["positive_pct"] = (f.return_pct > 0).astype(float) * 100
    return f


def daily_equal(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    return frame.groupby("signal_date").agg(**{m: (m, "mean") for m in METRICS}, n=("symbol", "size")).reset_index()


def r1(frame: pd.DataFrame) -> dict:
    available = frame[frame.structure_state != strict.INVALID]
    rows = []
    for day, g in available.groupby("signal_date", sort=True):
        t = g[g.structure_state == TRANSITION]
        other = g[g.structure_state != TRANSITION]
        if t.empty or other.empty:
            continue
        rows.append({"signal_date": day, "n": len(g), **t[list(METRICS)].mean().to_dict(),
                     **{f"base_{m}": float(other[m].mean()) for m in METRICS}})
    return {"contrast": by_year(pd.DataFrame(rows), paired),
            "states": {s: by_year(daily_equal(frame[frame.structure_state == s]), describe) for s in strict.STATES}}


def ranked_daily(frame: pd.DataFrame, method: str) -> tuple[dict[int, pd.DataFrame], pd.DataFrame, pd.DataFrame]:
    tops = {k: [] for k in (1, 3, 5)}
    ics, bins = [], []
    for day, g in frame.groupby("signal_date", sort=True):
        score = order_score(g, method)
        values = g[list(METRICS)].to_numpy()
        baseline = values.mean(axis=0)
        for k in tops:
            if len(g) >= max(2, k):
                chosen = top_weights(score, k) @ values
                tops[k].append({"signal_date": day, "n": len(g), **dict(zip(METRICS, chosen)),
                                **dict(zip((f"base_{m}" for m in METRICS), baseline))})
        if len(g) >= 3 and np.ptp(score) > 0 and g.return_pct.nunique() > 1:
            rho = np.corrcoef(pd.Series(score).rank(), g.return_pct.rank())[0, 1]
            ics.append({"signal_date": day, "ic": float(rho)})
        if len(g) >= 5 and np.ptp(score) > 0:
            ranks = pd.Series(score).rank(method="average").to_numpy()
            groups = np.minimum(4, np.floor((ranks - 0.5) / len(g) * 5)).astype(int)
            b = {"signal_date": day}
            for q in range(5):
                mask = groups == q
                b[f"Q{q + 1}"] = float(values[mask, 0].mean()) if mask.any() else np.nan
            bins.append(b)
    return {k: pd.DataFrame(rows) for k, rows in tops.items()}, pd.DataFrame(ics), pd.DataFrame(bins)


def ranking_analysis(frame: pd.DataFrame, method: str, detail: list, scope: str, horizon: str) -> dict:
    tops, ic, bins = ranked_daily(frame, method)
    result = {f"Top{k}": by_year(d, paired) for k, d in tops.items()}
    for k, daily in tops.items():
        for row in daily.to_dict("records"):
            detail.append({"scope": scope, "horizon": horizon, "method": method, "top_k": k, **row})
    def ic_summary(d):
        return {"eligible_dates": len(d), "mean": float(d.ic.mean()) if len(d) else None,
                "median": float(d.ic.median()) if len(d) else None,
                "ci95": bootstrap_means(d[["ic"]].to_numpy())[0] if len(d) else [None, None]}
    result["rank_ic"] = by_year(ic, ic_summary)
    def bin_summary(d):
        means = [float(d[f"Q{q}"].mean()) if len(d) and d[f"Q{q}"].notna().any() else None for q in range(1, 6)]
        spread = d.dropna(subset=["Q1", "Q5"]) if len(d) else d
        values = (spread.Q5 - spread.Q1).to_numpy()[:, None] if len(spread) else np.empty((0, 1))
        return {"eligible_dates": len(d), "means_low_to_high": means,
                "bin_eligible_dates": [int(d[f"Q{q}"].notna().sum()) if len(d) else 0 for q in range(1, 6)],
                "strictly_monotone": all(means[i] is not None and means[i + 1] is not None and means[i] <= means[i + 1] for i in range(4)),
                "paired_spread_dates": len(spread), "paired_Q5_minus_Q1": float(values.mean()) if len(values) else None,
                "spread_ci95": bootstrap_means(values)[0]}
    result["monotonicity"] = by_year(bins, bin_summary)
    return result


def analyze(frame: pd.DataFrame, scope: str, detail: list, single_fields: bool = False) -> dict:
    result = {"rows": len(frame), "dates": frame.signal_date.nunique(), "horizons": {}}
    for h in ("5D", "10D"):
        valid = metrics_for(frame, h)
        complete = quality(valid.dropna(subset=list(FIELDS)))
        methods = {m: ranking_analysis(complete, m, detail, scope, h) for m in ("R2", "R3")}
        increment = {}
        t2, _, _ = ranked_daily(complete, "R2")
        t3, _, _ = ranked_daily(complete, "R3")
        for k in t2:
            d = t3[k].copy()
            if not d.empty:
                other = t2[k].set_index("signal_date").loc[d.signal_date]
                for metric in METRICS:
                    d[f"base_{metric}"] = other[metric].to_numpy()
            increment[f"Top{k}"] = by_year(d, paired)
        result["horizons"][h] = {
            "R0_full": by_year(daily_equal(valid), describe),
            "R0_complete": by_year(daily_equal(complete), describe),
            "R1_full": r1(valid), "R1_complete": r1(complete),
            **methods, "R3_minus_R2": increment}
        if single_fields:
            result["horizons"][h]["individual_volume"] = {
                f: {"own_available": ranking_analysis(quality(valid.dropna(subset=[f])), f, detail, scope + "/field_own", h),
                    "common_complete": ranking_analysis(complete, f, detail, scope + "/field_common", h)}
                for f in FIELDS}
    return result


def prototype(frame: pd.DataFrame) -> tuple[list[dict], str]:
    """Feature-only input: this function cannot access outcome columns."""
    allowed = ["symbol", "signal_date", "setup_id", "structure_state", *FIELDS]
    features = frame[allowed].copy()
    complete = quality(features.dropna(subset=list(FIELDS)))
    counts = complete.groupby("signal_date").size()
    dates = sorted(counts[counts >= 2].index)
    choices = [("earliest", dates[0]), ("median", dates[len(dates) // 2]), ("latest", dates[-1]),
               ("most_candidates", sorted(dates, key=lambda d: (-counts[d], d))[0])]
    selected_dates = list(dict.fromkeys(day for _, day in choices))
    state_names = {strict.STATES[0]: "早期回踩代理", TRANSITION: "2→3切换代理",
                   strict.STATES[2]: "H1后延续代理", strict.INVALID: "结构不可用"}
    all_rows = []
    lines = ["# B_PRIORITY_PROTOTYPE_V0：历史研究样例", "",
             "仅供研究展示：DEVELOPMENT / RECONSTRUCTED_RETROSPECTIVE / EXPLORATORY / LOW_CONFIDENCE / NOT_PRODUCTION_VALIDATED。",
             "标签为 RESEARCH_PROTOTYPE_LABEL，不是买入建议或生产排名。未接入真实 Formal B 日报。", "",
             "规则：主板三项量能完整候选；先2→3切换代理，再 volume_quality 降序；同分按代码及 setup_id 展示。",
             "同日≥2只时 rank1=首选，rank2–3=次选，其余=观察；仅1只时=观察。量能不完整不进入排名。",
             "样例按最早／中位／最新／候选最多（同数取最早）选日，不读取收益。", "",
             "| 选日规则 | 日期 | 完整候选数 |", "|---|---|---:|"]
    lines.extend(f"| {reason} | {day} | {counts[day]} |" for reason, day in choices)
    for day, g in complete.groupby("signal_date", sort=True):
        g = g.assign(is_transition=g.structure_state == TRANSITION).sort_values(
            ["is_transition", "volume_quality", "symbol", "setup_id"], ascending=[False, False, True, True])
        volume_ranks = g.volume_quality.rank(method="min", ascending=False)
        for rank, (idx, r) in enumerate(g.iterrows(), 1):
            label = "首选" if rank == 1 and len(g) >= 2 else "次选" if rank in (2, 3) else "观察"
            state = state_names[r.structure_state]
            rationale = f"{label}：处于{state}，同日量能质量第{int(volume_ranks.loc[idx])}名；按固定结构优先规则列第{rank}。"
            item = {"signal_date": day, "symbol": r.symbol, "setup_id": r.setup_id,
                    "structure_state": r.structure_state, "volume_quality": float(r.volume_quality),
                    **{f: float(r[f]) for f in FIELDS}, "priority_rank": rank,
                    "prototype_label": label, "label_kind": "RESEARCH_PROTOTYPE_LABEL", "rationale": rationale}
            all_rows.append(item)
        if day in selected_dates:
            rows = [r for r in all_rows if r["signal_date"] == day]
            missing = len(features[features.signal_date == day]) - len(g)
            lines += ["", f"## {day} · 主板 · 完整{len(g)}只 · 量能不完整{missing}只", "",
                      "| 股票 | 结构阶段 | 回踩量能 | 今日优先级 | 原因 |", "|---|---|---|---|---|"]
            for r in rows:
                volume = f"quality={r['volume_quality']:.4f}；下跌占比={r[FIELDS[0]]:.4f}；涨跌量比={r[FIELDS[1]]:.4f}；衰减比={r[FIELDS[2]]:.4f}"
                lines.append(f"| {r['symbol']} | {state_names[r['structure_state']]} | {volume} | {r['priority_rank']} · {r['prototype_label']} | {r['rationale']} |")
    return all_rows, "\n".join(lines) + "\n"


def direction(primary: list[dict], dedup: list[dict]) -> str:
    if any(p["uplift"] is None for p in primary + dedup):
        return "NONE"
    means = [p["uplift"]["return_pct"] for p in primary]
    if all(abs(v) < 0.05 for v in means):
        return "NONE"
    for sign, label in ((1, "POSITIVE"), (-1, "NEGATIVE")):
        if (all(sign * p["uplift"]["return_pct"] > 0 for p in primary + dedup)
                and all(sign * p["uplift_ci95"][0 if sign == 1 else 1] > 0 for p in primary)):
            return label
    return "MIXED"


def markers(main: dict, dedup: dict) -> list[str]:
    h, d = main["horizons"]["5D"], dedup["horizons"]["5D"]
    result = []
    for method, stem in (("R1_full", "EXPLORATORY_W2W3_SIGNAL"), ("R2", "EXPLORATORY_VOLUME_SIGNAL"),
                         ("R3", "EXPLORATORY_W2W3_VOLUME_PRIORITY")):
        cases = [h[method]["contrast"]] if method.startswith("R1") else [h[method][f"Top{k}"] for k in (1, 3)]
        dcases = [d[method]["contrast"]] if method.startswith("R1") else [d[method][f"Top{k}"] for k in (1, 3)]
        value = direction([c["overall"] for c in cases], [c["overall"] for c in dcases])
        if value in ("POSITIVE", "NEGATIVE"):
            sign = 1 if value == "POSITIVE" else -1
            if any(sum(y["uplift"] is not None and sign * y["uplift"]["return_pct"] > 0 for y in c["years"].values()) < 3 for c in cases):
                value = "MIXED"
        result.append(f"{stem}_{value}")
    return result


def write_gzip(path: Path, rows: list[dict]) -> dict:
    payload = b"".join(canonical(r) for r in rows)
    with path.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as stream:
            stream.write(payload)
    return {"path": "data/" + path.as_posix().split("/data/", 1)[-1] if "/data/" in path.as_posix() else path.name,
            "rows": len(rows), "bytes": path.stat().st_size, "sha256": file_sha256(path),
            "content_stream_sha256": hashlib.sha256(payload).hexdigest()}


def fmt(value) -> str:
    return "NA" if value is None else f"{value:.3f}"


def table(headers, rows) -> list[str]:
    return ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers),
            *["| " + " | ".join(map(str, row)) + " |" for row in rows]]


def report(summary: dict) -> str:
    summary = json.loads(json.dumps(summary, sort_keys=True))
    main = summary["analyses"]["Main"]
    def number(h, method, k, group="uplift", metric="return_pct"):
        return fmt(main["horizons"][h][method][f"Top{k}"]["overall"][group][metric])
    lines = ["# B 优先级探索 V0：固定结构与三项量能", "",
             "**研究展示已完成；生产未验证。** 这是近似、低置信度的 DEVELOPMENT 历史重建，不能证明实盘收益或 production parity。",
             "严格研究继续为 `B_PRIORITY_RESEARCH_BLOCKED_BY_DATA_GAP` / `NEEDS_MORE_EVIDENCE`。", "",
             "`USER_AUTHORIZED_EXPLORATORY_RELAXATION_OF_PARITY_GATE` 仅授权独立 exploratory V0。",
             f"探索性 protocol 在读取 outcome 前提交：`{PROTOCOL_COMMIT}`。", "",
             "三个独立探索性结论：", "", *[f"- `{m}`" for m in summary["exploratory_markers"]], "",
             "方向分类依据预先冻结的5D均值、CI、年份和去重规则；MIXED 表示方向不稳定，不代表通过验证。",
             "Primary 主板10,779条/749日；结构可用9,085，量能完整7,861/719日，共同可用7,541。",
             "冻结信号区间2023-06-30..2026-08-28；2026只含该cutoff前数据。各horizon缺未来窗口者从选股与benchmark两端同时排除；原型仍可展示最新特征日。",
             "所有均值对信号日等权；收益/MFE/MAE单位%，uplift单位百分点。正收益率是每日组合内正收益股票比例的日期均值。",
             "Top1要求≥2只，Top3≥3只，Top5≥5只；相同 horizon/样本/日期的无排序 R0 为对照。", ""]
    lines += ["## 直接回答十个问题", "",
              "1. **2→3切换有没有方向性优势？** 5D偏正：对其他有效结构的同日差+0.416pp（576日，95%CI −0.032..+0.865）；10D约+0.002pp，基本无差。量能共同样本5D差+0.634pp，但2026反转，不能称稳定优势。",
              "2. **三项量能哪个最有用？** down_volume_share相对最值得观察：共同样本5D Top3 +0.171pp，Top1仅+0.005pp；up_down_volume_ratio的共同样本Top3为−0.208pp；pullback_volume_decay_ratio的Top1/3均偏负。单项自身可用样本的两个Top1约+0.26pp，但换到共同样本消失，不能宣布赢家或调权。",
              f"3. **R2好多少？** 5D Top1/3为{number('5D', 'R2', 1)}/{number('5D', 'R2', 3)}pp；10D为{number('10D', 'R2', 1)}/{number('10D', 'R2', 3)}pp，未见稳定改善。",
              f"4. **R3好多少？** 5D Top1/3为{number('5D', 'R3', 1)}/{number('5D', 'R3', 3)}pp；10D为{number('10D', 'R3', 1)}/{number('10D', 'R3', 3)}pp，主要改善在5D及10D Top3，所有这些uplift CI均跨零。",
              "5. **哪些年份好/差？** R1与R3的5D在2023–2025偏正、2026为负；R2的5D在2025最差、2026反而转正。R3的10D Top1四年全负，Top3在2023负、2024–2026正。逐年数值见表。",
              f"6. **MFE/MAE是否变好？** R3的5D Top1/3 MFE约{number('5D', 'R3', 1, metric='mfe_pct')}/{number('5D', 'R3', 3, metric='mfe_pct')}pp，MAE约{number('5D', 'R3', 1, metric='mae_pct')}/{number('5D', 'R3', 3, metric='mae_pct')}pp（更少负值）；R2两者均轻微变差。R3的10D Top1 MFE反而−0.307pp，不能概括为风险全面改善。",
              "7. **今天若展示粗糙版怎么排？** 只演示预先固定R3：transition先，其余不额外分层，再按三项good rank等权均值；不根据本次收益调整方向、权重或结构。",
              "8. **标签规则？** ≥2个量能完整主板候选时rank1首选，rank2–3次选，其余观察；1个候选观察，缺量能不排名。标签始终RESEARCH_PROTOTYPE_LABEL。",
              "9. **最大可靠性缺口？** historical与production observation未经真实语义parity，且是反复使用的DEVELOPMENT回顾数据；2026反转、10D Top1负、CI跨零、无量能单调性进一步限制可信度。",
              "10. **值得shadow吗？** 值得用户另行批准一个仅记录、固定规则的主板shadow，以验证特征语义和未来稳定性；不值得现在接入生产排名或推广到科创板。先解决原始输入留存/独立readback和观察验收边界，本次不启动shadow。", "",
              "Episode去重结果见独立敏感性表；R2对重复episode敏感，不能只引用未去重或去重中较好的版本。",
              f"R2的5D Rank IC为{fmt(main['horizons']['5D']['R2']['rank_ic']['overall']['mean'])}、R3为{fmt(main['horizons']['5D']['R3']['rank_ic']['overall']['mean'])}，五组收益均不单调；科创板R2/R3的5D Top1/3均负。", ""]
    for h in ("5D", "10D"):
        data = main["horizons"][h]
        lines += [f"## {h}：主板 R0 / R1 / R2 / R3", ""]
        rows = []
        for name in ("R0_full", "R0_complete"):
            r = data[name]["overall"]
            rows.append([name, r["eligible_dates"], r["candidate_rows"], *[fmt(r["mean"][m]) for m in METRICS], fmt(r["median"]["return_pct"])])
        lines += table(["R0口径", "日期", "候选条数", "收益", "正收益率%", "MFE", "MAE", "日期收益中位数"], rows) + [""]
        rows = []
        for state, case in data["R1_full"]["states"].items():
            r = case["overall"]
            rows.append([state, r["eligible_dates"], r["candidate_rows"], *[fmt(r["mean"][m]) if r["mean"] else "NA" for m in METRICS]])
        lines += table(["结构状态", "日期", "条数", "收益", "正收益率%", "MFE", "MAE"], rows) + [""]
        rows = []
        for view in ("R1_full", "R1_complete"):
            for period, r in [("overall", data[view]["contrast"]["overall"]), *data[view]["contrast"]["years"].items()]:
                if r["selected"]:
                    rows.append([view, period, r["eligible_dates"], fmt(r["selected"]["return_pct"]), fmt(r["baseline"]["return_pct"]),
                                 fmt(r["uplift"]["return_pct"]), str([round(x, 3) for x in r["uplift_ci95"]]),
                                 fmt(r["uplift"]["mfe_pct"]), fmt(r["uplift"]["mae_pct"])])
        lines += table(["R1 transition vs其他有效状态", "年份", "配对日", "transition收益", "其他收益", "差", "差95%CI", "MFE差", "MAE差"], rows) + [""]
        rows = []
        for method in ("R2", "R3"):
            for k in (1, 3, 5):
                r = data[method][f"Top{k}"]["overall"]
                rows.append([method, f"Top{k}", r["eligible_dates"], r["candidate_rows"],
                             fmt(r["selected"]["return_pct"]), fmt(r["baseline"]["return_pct"]), fmt(r["uplift"]["return_pct"]),
                             str([round(x, 3) for x in r["uplift_ci95"]]),
                             fmt(r["selected"]["positive_pct"]), fmt(r["selected"]["mfe_pct"]), fmt(r["selected"]["mae_pct"]),
                             fmt(r["uplift"]["mfe_pct"]), fmt(r["uplift"]["mae_pct"]), fmt(r["median_selected"]["return_pct"])])
        lines += table(["方法", "TopK", "日期", "候选条数", "收益", "同日R0", "uplift", "uplift95%CI", "正收益率%", "MFE", "MAE", "MFE差", "MAE差", "日期收益中位数"], rows) + [""]
        rows = []
        for method in ("R2", "R3", "R3_minus_R2"):
            for k in (1, 3, 5):
                for year, r in data[method][f"Top{k}"]["years"].items():
                    if r["selected"]:
                        rows.append([method, f"Top{k}", year, r["eligible_dates"], fmt(r["selected"]["return_pct"]), fmt(r["baseline"]["return_pct"]),
                                     fmt(r["uplift"]["return_pct"]), fmt(r["selected"]["positive_pct"]), fmt(r["selected"]["mfe_pct"]), fmt(r["selected"]["mae_pct"])])
        lines += table(["方法", "TopK", "年份", "日期", "收益", "对照", "差", "正收益率%", "MFE", "MAE"], rows) + [""]
        lines += ["### 三项量能（单项可用 / 三项共同样本）", ""]
        rows = []
        for f, views in data["individual_volume"].items():
            for view, values in views.items():
                for k in (1, 3, 5):
                    r = values[f"Top{k}"]["overall"]
                    rows.append([f, view, f"Top{k}", r["eligible_dates"], fmt(r["selected"]["return_pct"]), fmt(r["uplift"]["return_pct"]),
                                 fmt(values["rank_ic"]["overall"]["mean"]), fmt(r["selected"]["mfe_pct"]), fmt(r["selected"]["mae_pct"])])
        lines += table(["量能", "样本", "TopK", "日期", "收益", "uplift", "Rank IC", "MFE", "MAE"], rows) + [""]
        rows = []
        for method in ("R2", "R3"):
            for period, b in [("overall", data[method]["monotonicity"]["overall"]), *data[method]["monotonicity"]["years"].items()]:
                rows.append([method, period, b["eligible_dates"], *map(fmt, b["means_low_to_high"]), fmt(b["paired_Q5_minus_Q1"]), b["strictly_monotone"]])
        lines += table(["方法", "年份", "分组日", "Q1", "Q2", "Q3", "Q4", "Q5", "配对Q5-Q1", "单调"], rows) + [""]
    lines += ["## Episode去重与板块稳健性", "", "去重先保留每个(symbol, breakout_date)最早信号，再重算排名和R0。创业板/科创板各自在板内排名；不替代主板结论。", ""]
    rows = []
    for scope in ("Main_episode_dedup", "ChiNext", "STAR"):
        for h in ("5D", "10D"):
            data = summary["analyses"][scope]["horizons"][h]
            for method in ("R2", "R3"):
                for k in (1, 3, 5):
                    r = data[method][f"Top{k}"]["overall"]
                    if r["selected"]:
                        rows.append([scope, h, method, f"Top{k}", r["eligible_dates"], fmt(r["selected"]["return_pct"]), fmt(r["uplift"]["return_pct"]),
                                     str([round(x, 3) for x in r["uplift_ci95"]]), fmt(r["uplift"]["mfe_pct"]), fmt(r["uplift"]["mae_pct"])])
    lines += table(["样本", "horizon", "方法", "TopK", "日期", "收益", "uplift", "95%CI", "MFE差", "MAE差"], rows) + ["",
             "主板去重R1、逐年单项量能/Rank IC/CI、各状态风险和所有日期统计详见同名summary.json。", "",
             "## Prototype与可靠性边界", "", "[历史样例日报](../examples/b_priority_prototype_v0.md)。规则只用输入特征：先transition，再等权量能质量；不从收益调权或改结构。",
             "首选=当日≥2个complete candidates时rank1；次选=rank2–3；观察=其余，单候选也观察。缺量能不补值、不排名。",
             "无效结构保留为非transition并明确显示。POST_H1_CONTINUATION与EARLY仅按量能排序，未按本次收益另设层级。",
             "展示同分按代码/setup_id，统计同分使用边界分数权重；展示排序不冒充统计Top1。", "",
             "最大缺口：historical reconstructed features与production observation语义/known-at vintage未经验证；存活/样本口径、重叠窗口序列相关、重复使用DEVELOPMENT和多重比较均限制外推。",
             "日期cluster bootstrap为10,000次、seed=20261104；没有处理相邻日期重叠窗口的全部依赖；不是独立未来验证。",
             "未计交易成本/滑点/涨跌停成交限制；无法从固定horizon收益声称可实现利润。stop/target secondary=UNAVAILABLE（现有输入无已证明的冻结B路径）。",
             "ADOPT仅指研究展示原型；生产采用=NEEDS_MORE_EVIDENCE。下一步是否授权独立shadow observation由用户决定，本次不启动。", "",
             "## 可恢复证据", "", f"`EXPLORATORY_PRE_OUTCOME_PROTOCOL_COMMIT={PROTOCOL_COMMIT}`。",
             "复现：`python scripts/b_priority_w2w3_volume_exploratory_v0.py`；先按strict报告恢复/重建原有input_features（不更改strict结果）。",
             "冻结数据恢复来源与6项raw hash沿用strict报告；本研究直接复用已冻结feature detail和已冻结B V2 outcomes，无provider请求。",
             "summary记录所有输入/output SHA、detail行数/字节/stream SHA；两次确定性运行必须完全相同。", "",
             "Strict三项NEEDS_MORE_EVIDENCE及blocked marker保留；exploratory marker不替代它们。Final OOS SEALED / UNREAD；continuous_speed_probe未访问；",
             "Formal B qualification / Score / report / tracker / runtime-state / provider / scheduler / C不变；production semantics change=0，dispatch=0，ranking=0；不merge。", "",
             "终态：`B_PRIORITY_EXPLORATORY_V0_READY_FOR_USER_DECISION`。分类始终research question / STRICT PATH。", ""]
    return "\n".join(lines)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    frame, _, provenance = load_inputs(root)
    detail = []
    analyses = {}
    main_frame = frame[frame.board == "Main"]
    dedup = main_frame.drop_duplicates(["symbol", "breakout_date"], keep="first")
    for scope, subset in (("Main", main_frame), ("Main_episode_dedup", dedup),
                          ("ChiNext", frame[frame.board == "ChiNext"]), ("STAR", frame[frame.board == "STAR"])):
        print(f"analyzing {scope}: {len(subset)} rows", flush=True)
        analyses[scope] = analyze(subset, scope, detail, single_fields=scope == "Main")
    prototype_rows, preview = prototype(main_frame)
    output = root / OUTPUT
    output.mkdir(parents=True, exist_ok=True)
    artifacts = {"daily_comparisons": write_gzip(output / "daily_comparisons.jsonl.gz", detail),
                 "prototype_candidates": write_gzip(output / "prototype_candidates.jsonl.gz", prototype_rows)}
    summary = {"task": TASK, "evidence_labels": LABELS, "classification": "research question / STRICT PATH",
               "status": "B_PRIORITY_EXPLORATORY_V0_READY_FOR_USER_DECISION",
               "EXPLORATORY_PRE_OUTCOME_PROTOCOL_COMMIT": PROTOCOL_COMMIT,
               "authorization": "USER_AUTHORIZED_EXPLORATORY_RELAXATION_OF_PARITY_GATE",
               "strict_status": strict.BLOCKER, "strict_decision": "NEEDS_MORE_EVIDENCE",
               "strict_markers": ["B_W2W3_TRANSITION_PRIORITY_NEEDS_MORE_EVIDENCE", "B_REPORT_VOLUME_PRIORITY_NEEDS_MORE_EVIDENCE", "B_W2W3_VOLUME_PRIORITY_NEEDS_MORE_EVIDENCE"],
               "provenance": provenance, "analyses": analyses, "artifacts": artifacts,
               "exploratory_markers": markers(analyses["Main"], analyses["Main_episode_dedup"]),
               "decision": {"research_demonstration": "ADOPT", "production": "NEEDS_MORE_EVIDENCE",
                            "missing_evidence": "prospective production feature semantics, untouched inputs, out-of-sample directional stability and executable costs",
                            "continuing_product_paths": "existing Formal B operation and report observations remain unblocked"},
               "boundaries": {"final_oos": "SEALED / UNREAD", "production_semantics_change": 0,
                              "production_dispatch": 0, "production_ranking": 0, "provider_calls": 0,
                              "production_observation_parity": "NOT_RUN_INPUTS_UNAVAILABLE",
                              "stop_target_secondary": "UNAVAILABLE_NO_PROVEN_FROZEN_B_PATH"}}
    (root / REPORT).write_text(report(summary), encoding="utf-8", newline="\n")
    (root / PROTOTYPE).write_text(preview, encoding="utf-8", newline="\n")
    summary["report_sha256"] = file_sha256(root / REPORT)
    summary["prototype_sha256"] = file_sha256(root / PROTOTYPE)
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"markers": summary["exploratory_markers"], "summary_sha256": file_sha256(output / "summary.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
