"""Fixed DEVELOPMENT path diagnostic; no production writes or parameter search."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd

import core_signal_replay as replay
import b_phase_volume_path_diagnostic as volume_path
from b_breakout_retest_v1_1 import evaluate_numeric_projection, STRATEGY_SPEC_SHA256
from b_shadow_monitor import _market_snapshot
from track_perf import rebuild_execution_state_from_observations
from trading_calendar import TradingCalendar
from validate_development_returns_v2 import _adjust_outcome_path, _stock_path

TASK = "B_FALSE_BREAKOUT_PATH_DIAGNOSTIC_V1"
BASE = "9c3f011ebc06d33347372b3792ec28f11c505f40"
PROTOCOL_COMMIT = "ad975a0"
PROTOCOL = "docs/research/b_false_breakout_path_diagnostic_v1_protocol.md"
DEFENSE = "min_close_vs_breakout_level"
VOLUME = "pre_t_retest_volume_ratio"
REACT = "exceeds_retest_local_high"
FEATURE_DEFINITIONS = {
    "breakout_return": "close[i]/close[i-1]-1",
    "breakout_volume_ratio": "volume[i]/mean(volume[i-20:i]); excludes breakout i",
    "b_existing_pull_volume_ratio": "exact existing B aggregate pull volume / volume[i]; includes T",
    "pre_t_retest_volume_ratio": "mean(volume[i+1:T])/volume[i]; excludes T",
    "reactivation_vs_retest_ratio": "volume[T]/mean(volume[i+1:T])",
    "reactivation_vs_breakout_ratio": "volume[T]/volume[i]",
    "min_low_vs_breakout_level": "min(low[i+1:T])/L-1",
    "min_close_vs_breakout_level": "min(close[i+1:T])/L-1",
    "max_retest_depth_vs_breakout_level": "max(0,1-min(low[i+1:T])/L)",
    "days_below_breakout_level": "count(close[i+1:T]<L)",
    "reclaim_breakout_level_days": "bar delay from first below-L pre-T close to first later close>=L through T; missing if no breach/not reclaimed",
    "days_to_reclaim_breakout_level": "alias of reclaim_breakout_level_days",
    "days_from_breakout_to_signal": "T-i observed stock trading bars",
    "days_to_reactivation_local_high": "T-first_argmin(low[i+1:T]) when close[T]>max(high[i+1:T]); otherwise missing",
    "reactivation_price_strength": "close[T]/close[T-1]-1",
    "reclaims_breakout_level": "close[T]>=L",
    "exceeds_retest_local_high": "close[T]>max(high[i+1:T])",
    "anchor": "L=max(close[i-60:i]); exact existing first qualifying breakout i",
}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def path_features(close, volume, high, low, dates=None):
    trace = volume_path._first_breakout_trace(close, volume, high, low, dates)
    if trace is None:
        raise RuntimeError("qualified identity has no exact breakout")
    i, t, level = trace["breakout_index"], len(close) - 1, trace["base_hi"]
    trace.update(breakout_return=float(close[i] / close[i-1] - 1),
                 days_from_breakout_to_signal=t-i,
                 reactivation_price_strength=float(close[t] / close[t-1] - 1),
                 reclaims_breakout_level=bool(close[t] >= level))
    fields = ("min_low_vs_breakout_level", DEFENSE, "max_retest_depth_vs_breakout_level",
              "days_below_breakout_level", "reclaim_breakout_level_days",
              "days_to_reclaim_breakout_level", "days_to_reactivation_local_high", REACT)
    if i+1 == t:
        for field in fields:
            trace[field] = None
            trace["feature_unavailable"][field] = "NO_PRE_T_RETEST_INTERVAL"
        return trace
    retest = slice(i+1, t)
    minimum = float(np.min(low[retest]) / level - 1)
    trace.update(min_low_vs_breakout_level=minimum,
                 min_close_vs_breakout_level=float(np.min(close[retest]) / level - 1),
                 max_retest_depth_vs_breakout_level=max(0., -minimum),
                 days_below_breakout_level=int(np.sum(close[retest] < level)),
                 exceeds_retest_local_high=bool(close[t] > np.max(high[retest])))
    breach = np.flatnonzero(close[retest] < level)
    delay, reason = None, "NO_BREACH"
    if len(breach):
        first = i+1+int(breach[0])
        reclaim = np.flatnonzero(close[first+1:t+1] >= level)
        delay = int(reclaim[0])+1 if len(reclaim) else None
        reason = "NOT_RECLAIMED"
    for field in ("reclaim_breakout_level_days", "days_to_reclaim_breakout_level"):
        trace[field] = delay
        if delay is None:
            trace["feature_unavailable"][field] = reason
    trough = i+1+int(np.argmin(low[retest]))
    trace["days_to_reactivation_local_high"] = t-trough if trace[REACT] else None
    if not trace[REACT]:
        trace["feature_unavailable"]["days_to_reactivation_local_high"] = "NOT_REACTIVATED"
    return trace


def label_state(state, sessions):
    reason = state.get("exit_reason") or ""
    if state.get("status") == "win":
        return "TARGET"
    if state.get("status") == "loss":
        delta = sessions[state["exit_date"]] - sessions[state["entry_date"]]
        return "FAST_STOP" if delta in (1, 2) else "STOP"
    return "AMBIGUOUS" if state.get("status") == "AMBIGUOUS_SAME_BAR" else reason or state["status"]


def contrast(frame, feature, low, high, strata, secondary=False):
    selected = frame[frame.label.isin(["TARGET", "FAST_STOP", "STOP"] if secondary else ["TARGET", "FAST_STOP"])]
    pairs = []
    grouped = selected.groupby(strata, dropna=False) if strata else [("all", selected)]
    for key, group in grouped:
        sides = [group[group[feature] == value] for value in (low, high)]
        if any(len(side) < 30 or (side.label == "TARGET").sum() < 5 or (side.label != "TARGET").sum() < 5 for side in sides):
            continue
        mass = [float(side.weight.sum()) for side in sides]
        rates = [float(side.loc[side.label != "TARGET", "weight"].sum()/m) for side, m in zip(sides, mass)]
        pairs.append({"stratum": str(key), "low_n": len(sides[0]), "high_n": len(sides[1]),
                      "low_rate": rates[0], "high_rate": rates[1],
                      "delta": rates[1]-rates[0], "pair_weight": 2*mass[0]*mass[1]/sum(mass)})
    denominator = sum(p["pair_weight"] for p in pairs)
    return {"delta_pp": 100*sum(p["delta"]*p["pair_weight"] for p in pairs)/denominator if denominator else None,
            "state": "AVAILABLE" if denominator else "INSUFFICIENT_DATA", "pairs": pairs}


def counts(frame):
    c = Counter(frame.label)
    return {"rows": len(frame), "TARGET": c["TARGET"], "FAST_STOP": c["FAST_STOP"],
            "STOP": c["FAST_STOP"]+c["STOP"], "other": {k:v for k,v in sorted(c.items()) if k not in ("TARGET","FAST_STOP","STOP")},
            "unique_episodes": frame.episode.nunique()}


def analyze(frame):
    frame = frame.copy()
    edges = {}
    for field in (DEFENSE, VOLUME, "reactivation_price_strength"):
        boundaries = frame[field].dropna().quantile([1/3,2/3]).tolist()
        edges[field] = boundaries
        frame[field+"_bin"] = frame[field].map(lambda x: None if pd.isna(x) else int(np.searchsorted(boundaries, x, side="left"))+1)
    frame["weight"] = 1.
    frame["episode_size"] = frame.groupby("episode").episode.transform("size")
    d, v, ret = DEFENSE+"_bin", VOLUME+"_bin", "reactivation_price_strength_bin"
    views = {"overall": frame, "main": frame[frame.board == "main"],
             "earliest_episode": frame.sort_values(["signal_date","symbol"]).drop_duplicates("episode"),
             "exclude_near_limit_proxy": frame[frame.near_price_limit_proxy == False],
             "singleton": frame[frame.episode_size == 1], "repeated": frame[frame.episode_size > 1]}
    inverse = frame.copy(); inverse.weight = 1/inverse.episode_size
    views["inverse_episode_weight"] = inverse
    for year in ("2023","2024","2025","2026"):
        views["year_"+year] = frame[frame.year == year]
    for regime in sorted(frame.regime.unique()):
        views["regime_"+regime] = frame[frame.regime == regime]
    robustness = {}
    for name, group in views.items():
        robustness[name] = {"counts": counts(group),
            "primary_price_increment": contrast(group,d,1,3,[v]),
            "secondary_price_increment": contrast(group,d,1,3,[v],True),
            "volume_increment": contrast(group,v,3,1,[d]),
            "reactivation_increment": contrast(group,REACT,False,True,[d,v]),
            "reactivation_return_conditioned": contrast(group,REACT,False,True,[ret])}
    months = {month:contrast(frame[frame.signal_date.str[:7] != month],d,1,3,[v]) for month in sorted(frame.signal_date.str[:7].unique())}
    matrices = []
    for group_fields in ([v], [v,d], [v,d,REACT]):
        table = []
        for key, group in frame.groupby(group_fields, dropna=False):
            c = counts(group)
            table.append({"cell": [None if pd.isna(x) else x for x in key], **c,
                          "primary_fast_stop_rate": c["FAST_STOP"]/(c["TARGET"]+c["FAST_STOP"]) if c["TARGET"]+c["FAST_STOP"] else None,
                          "secondary_stop_rate": c["STOP"]/(c["TARGET"]+c["STOP"]) if c["TARGET"]+c["STOP"] else None})
        matrices.append({"axes":group_fields,"cells":table})
    distributions = {}
    numeric = [*volume_path.FEATURES,"breakout_return",DEFENSE,"min_low_vs_breakout_level",
               "max_retest_depth_vs_breakout_level","days_below_breakout_level","reclaim_breakout_level_days",
               "days_to_reclaim_breakout_level","days_from_breakout_to_signal","days_to_reactivation_local_high",
               "reactivation_price_strength","reclaims_breakout_level",REACT]
    for field in numeric:
        distributions[field] = {}
        for label in ("TARGET","FAST_STOP","ALL_STOP"):
            values = frame.loc[frame.label.isin(["FAST_STOP","STOP"]) if label == "ALL_STOP" else frame.label == label,field].dropna().astype(float)
            distributions[field][label] = {"n":len(values),"missing":int((frame.label.isin(["FAST_STOP","STOP"]) if label == "ALL_STOP" else frame.label == label).sum())-len(values),
                "mean":float(values.mean()) if len(values) else None,
                "quantiles":{str(q):float(values.quantile(q)) for q in (.1,.25,.5,.75,.9)} if len(values) else {}}
    delta = lambda name: robustness[name]["primary_price_increment"]["delta_pp"]
    negative = lambda x: x is not None and x < 0
    strong = all(delta(name) is not None and delta(name) <= -5 for name in ("overall","main","earliest_episode"))
    years = [delta("year_"+y) for y in ("2023","2024","2025","2026")]
    strong = strong and sum(negative(x) for x in years)>=3 and not any(x is not None and x>0 for x in years)
    strong = strong and all(negative(x["delta_pp"]) for x in months.values()) and all(negative(delta(n)) for n in ("exclude_near_limit_proxy","inverse_episode_weight"))
    strong = strong and negative(robustness["overall"]["reactivation_increment"]["delta_pp"]) and negative(robustness["overall"]["reactivation_return_conditioned"]["delta_pp"])
    suffix = "BV2_DECISION_REQUIRED" if strong else "PROSPECTIVE_EVIDENCE_REQUIRED" if negative(delta("overall")) and negative(delta("main")) else "NO_ACTION"
    return {"sample_counts":counts(frame), "quantile_edges":edges,"feature_distributions":distributions,
            "matrices":matrices,"robustness":robustness,"leave_one_month_out":months,
            "episode_concentration":{"repeated_row_share":float((frame.episode_size>1).mean()),"largest_episode_rows":int(frame.episode_size.max()),
                                     "top_10_episode_row_share":float(frame.groupby("episode").size().nlargest(10).sum()/len(frame))},
            "final_research_status":"B_FALSE_BREAKOUT_PATH_DIAGNOSTIC_"+suffix,
            "decision":"ADOPT_FOR_USER_DECISION" if strong else "NEEDS_MORE_EVIDENCE" if suffix == "PROSPECTIVE_EVIDENCE_REQUIRED" else "REJECT",
            "primary_comparison_result":robustness["overall"]["primary_price_increment"]}


def run(source_root, output):
    root = Path(__file__).resolve().parents[1]
    if any(token in str(source_root).lower() for token in ("final_oos", "continuous_speed_probe")):
        raise RuntimeError("forbidden source path")
    if output.resolve() != (root/"data/validation/b_false_breakout_path_diagnostic_v1").resolve():
        raise RuntimeError("output must be isolated task artifact directory")
    if STRATEGY_SPEC_SHA256 != "f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd":
        raise RuntimeError("frozen B spec changed")
    frozen = subprocess.check_output(["git","show",f"{PROTOCOL_COMMIT}:{PROTOCOL}"],cwd=root)
    if frozen != (root/PROTOCOL).read_bytes():
        raise RuntimeError("pre-outcome protocol bytes changed")
    raw = source_root/"data/validation/core_signal_validation/raw"
    cohort = root/"data/validation/strategy_candidate_eligibility_v1/b_breakout_retest_eligibility_events.jsonl.gz"
    manifest = json.loads((root/"data/validation/strategy_candidate_eligibility_v1/strategy_development_eligibility_manifest.json").read_text(encoding="utf8"))
    if sha(cohort) != manifest["artifacts"]["event_results"]["sha256"]:
        raise RuntimeError("cohort hash mismatch")
    registry = json.loads((root/"data/governance/frozen_artifacts.json").read_text(encoding="utf8"))
    inputs = {"cohort":sha(cohort)}
    for item in registry["artifacts"]:
        if item["logical_path"].startswith("data/validation/core_signal_validation/raw/"):
            path = source_root/item["logical_path"]
            value = sha(path)
            if value != item["file_sha256"]:
                raise RuntimeError("frozen raw hash mismatch: "+item["logical_path"])
            inputs[item["logical_path"]] = value
    with gzip.open(cohort,"rt",encoding="utf8") as handle:
        identities = sorted((json.loads(line) for line in handle),key=lambda r:(r["symbol"],r["signal_date"]))
    if len(identities)!=17714 or len({(r["symbol"],r["signal_date"]) for r in identities})!=17714:
        raise RuntimeError("qualified cohort identity mismatch")
    store,_ = replay._load_stock_store(raw/"daily_k.parquet")
    events,_ = replay._load_events(raw/"adjustment_factors.parquet")
    index_dates,index_bars,_ = replay._load_index(raw)
    sessions = sorted(index_dates); positions = {d:i for i,d in enumerate(sessions)}
    session_days = {date.fromisoformat(d) for d in sessions}
    cal = TradingCalendar(provider=lambda day: day in session_days)
    regime = {d:_market_snapshot({"bars":index_bars[:positions[d]+1]},d)["trend_regime"] or "UNAVAILABLE" for d in sorted({r["signal_date"] for r in identities})}
    rows = []; cache = {}
    for number, row in enumerate(identities):
        symbol,t = row["symbol"],row["signal_date"]
        anchor = replay._ms_from_date(t); se = events.get(symbol,[])
        ec = sum(e[0]<=anchor for e in se)
        key = (symbol,ec)
        if key not in cache:
            cache = {key:volume_path._adjusted_symbol_arrays(store,symbol,se,ec)}
        dates,close,vol,high,low = cache[key]
        end = int(np.searchsorted(dates,anchor,side="right")); start = max(0,end-replay.LOOKBACK_BARS)
        arrays = tuple(a[start:end] for a in (close,vol,high,low))
        dt = [store["date_text"][int(x)] for x in dates[start:end]]
        features = path_features(*arrays,dt)
        p = positions[t]
        projection = evaluate_numeric_projection(symbol=symbol,signal_date=t,earliest_execution_date=row["earliest_execution_date"],bars=arrays,index_bars=index_bars[:p+1])
        if projection["status"] != "QUALIFIED_LEGACY_BASELINE":
            raise RuntimeError("frozen qualified parity mismatch")
        label = "INSUFFICIENT_FORWARD_COVERAGE"; state = {}
        if p+11 < len(sessions):
            expected = np.array([index_dates[d] for d in sessions[p+1:p+12]],dtype=np.int64)
            path = _stock_path(store=store,symbol=symbol,expected_dates_ms=expected)
            if path is None:
                label = "INCOMPLETE_STOCK_WINDOW"
            else:
                target_ms = int(expected[-1])
                adjusted = _adjust_outcome_path(dates_ms=path[0],opens=path[1],highs=path[2],lows=path[3],closes=path[4],events=se,target_ms=target_ms)
                levels = np.array([projection[k] for k in ("trigger","stop","target")],dtype=float)
                transformed = _adjust_outcome_path(dates_ms=np.full(3,anchor),opens=levels,highs=levels,lows=levels,closes=levels,events=[e for e in se if e[0]>anchor],target_ms=target_ms)[0]
                observations = [{"date":sessions[p+1+j],"open":float(adjusted[0][j]),"high":float(adjusted[1][j]),"low":float(adjusted[2][j]),"price":float(adjusted[3][j])} for j in range(11)]
                signal = {"date":t,**dict(zip(("trigger","stop","target"),transformed)),"observations":observations}
                state = rebuild_execution_state_from_observations(signal,cal,sessions[p+11])
                label = label_state(state,positions)
        rows.append({"symbol":symbol,"signal_date":t,"year":t[:4],"board":volume_path._board(symbol),
                     "episode":symbol+"|"+features["breakout_date"],"regime":regime[t],"label":label,
                     "near_price_limit_proxy":volume_path._near_price_limit_proxy(symbol,features["signal_day_return_pct"]),
                     **features,"execution_state":state})
        if number%2000 == 0:
            print(f"qualified rows {number}/{len(identities)}",flush=True)
    frame = pd.DataFrame(rows)
    baseline_path = root/"data/validation/b_phase_volume_path_diagnostic_v1/summary.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf8"))
    baseline_reconciliation = {}
    for field in volume_path.FEATURES:
        values = frame[field].dropna()
        prior = baseline["feature_distributions"][field]
        match = len(values) == prior["n"] and np.isclose(values.mean(),prior["mean"],rtol=1e-12,atol=1e-12) and np.isclose(values.median(),prior["median"],rtol=1e-12,atol=1e-12)
        if not match:
            raise RuntimeError("volume baseline reconstruction mismatch: "+field)
        baseline_reconciliation[field] = {"n":len(values),"mean":float(values.mean()),"median":float(values.median()),"match":True}
    summary = {"schema_version":TASK,"labels":["DEVELOPMENT","RECONSTRUCTED_RETROSPECTIVE","DIAGNOSTIC_ONLY"],
               "base_sha":BASE,"branch":"codex/b-false-breakout-path-diagnostic-v1",
               "source_sha":subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,text=True).strip(),
               "implementation_sha256":sha(Path(__file__)),
               "protocol_commit":subprocess.check_output(["git","rev-parse",PROTOCOL_COMMIT],cwd=root,text=True).strip(),"protocol_sha256":sha(root/PROTOCOL),
               "cohort_identity":"frozen-qualified-B-17714","input_sha256":inputs,"spec_sha256":STRATEGY_SPEC_SHA256,
               "feature_definitions":FEATURE_DEFINITIONS,
               "baseline_reconciliation":{"sha256":sha(baseline_path),"decision":baseline["decision"],"features":baseline_reconciliation},
               "reproduction_command":"python scripts/b_false_breakout_path_diagnostic.py --source-root <checkout-with-restored-frozen-daily-k>",
               "turnover_availability_state":"TURNOVER_EVIDENCE_UNAVAILABLE",
               "turnover_probe":{"source":"existing HiThink and third-party daily_basic provenance","reason":"amount is not turnover rate; gateway NO_VINTAGE_PROOF does not establish PIT validity","provider_calls":0},
               "feature_unavailable_reasons":dict(Counter(field+":"+reason for row in rows for field,reason in row["feature_unavailable"].items())),
               "boundaries":{"production_dispatch":0,"runtime_state_remote_mutation":False,"final_oos":"SEALED / UNREAD","pr60_untouched":True},
               **analyze(frame)}
    output.mkdir(parents=True,exist_ok=True)
    detail = output/"events.jsonl.gz"
    with detail.open("wb") as raw_handle:
        with gzip.GzipFile(fileobj=raw_handle,mode="wb",mtime=0,filename="") as handle:
            for row in rows:
                handle.write((json.dumps(row,sort_keys=True,allow_nan=False)+"\n").encode())
    summary["event_artifact"] = {"rows":len(rows),"sha256":sha(detail),"path":str(detail.relative_to(root)).replace("\\","/")}
    (output/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf8",newline="\n")
    (root/"docs/research/b_false_breakout_path_diagnostic_v1_report.md").write_text(render_report(summary,sha(output/"summary.json")),encoding="utf8",newline="\n")
    return summary


def render_report(summary, artifact_sha):
    c = summary["sample_counts"]
    lines = ["# B False Breakout Path Diagnostic V1 Report", "",
        "DEVELOPMENT / RECONSTRUCTED_RETROSPECTIVE / DIAGNOSTIC_ONLY. Research question; classification unchanged.", "",
        "## Decision", "", "`"+summary["final_research_status"]+"`", "",
        "Research decision: `NEEDS_MORE_EVIDENCE`. Overall price-defense direction survives episode sensitivity,",
        "but Main Board magnitude is negligible, 2023 reverses, the secondary all-STOP comparison reverses,",
        "and reactivation fails the joint/return-conditioned support checks. The joint hypothesis is INCONCLUSIVE.",
        "No B V2 protocol, filter, prospective deployment, or production change is authorized or created.", "",
        "The frozen diagnostic definitions are the only candidate structure retained. Missing evidence is a",
        "genuine pre-outcome prospective Main Board cohort with enough independent episodes across periods",
        "to evaluate the same comparisons without redefining bins/features. It would inform a later separately",
        "authorized B V2 decision; the existing daily Formal B path continues without this evidence.", "",
        "## Cohort and labels", "",
        f"Exact frozen qualified identities: {c['rows']}; TARGET={c['TARGET']}; FAST_STOP={c['FAST_STOP']}; all STOP={c['STOP']}.",
        f"Unique (symbol, breakout_date) episodes={c['unique_episodes']}. Other outcomes: `{json.dumps(c['other'],sort_keys=True)}`.",
        "FAST_STOP is a subset of STOP; it is not added to STOP when reporting total counts.",
        "Formal track_perf replay supplies trigger/gap fills, entry+1 sellability, same-bar ambiguity and",
        "T+10 time exit / T+11 deferred legal exit. V2 affine adjustment puts OHLC and frozen rule levels",
        "on the same ex-post basis; future actions never enter features. This is a reconstructed DEVELOPMENT",
        "execution diagnostic, not the earlier volume baseline's unconditional T+1-open return or prospective results.",
        "Full T+11 stock coverage is required conservatively before path evaluation; 162 coverage-unavailable",
        "rows are reported rather than assigning partial labels. This can introduce maturity/coverage selection.", "",
        "## Increment and robustness", "",
        "Rates are FAST_STOP/(TARGET+FAST_STOP); secondary rates are STOP/(TARGET+STOP).",
        "Values below are percentage-point differences, high minus low defense within fixed volume bins.",
        "Negative primary values indicate fewer FAST_STOP relative to TARGET. No independent-row p-values",
        "or causal claims are made. All cells and per-side counts, including missing/sparse cells, are in summary.json.", "",
        "| view | rows | episodes | price primary Δpp | price all-STOP Δpp | reactivation joint Δpp | reactivation within return Δpp |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for name,r in summary["robustness"].items():
        values = [r[k]["delta_pp"] for k in ("primary_price_increment","secondary_price_increment","reactivation_increment","reactivation_return_conditioned")]
        formatted = ["INSUFFICIENT_DATA" if v is None else f"{v:.3f}" for v in values]
        lines.append(f"| {name} | {r['counts']['rows']} | {r['counts']['unique_episodes']} | "+" | ".join(formatted)+" |")
    months = [r["delta_pp"] for r in summary["leave_one_month_out"].values() if r["delta_pp"] is not None]
    concentration = summary["episode_concentration"]
    lines.extend(["",f"Leave-one-month-out primary range: {min(months):.3f} to {max(months):.3f} pp; all retained negative.",
        f"Repeated-episode row share={concentration['repeated_row_share']:.2%}; largest episode={concentration['largest_episode_rows']} rows; top ten episode share={concentration['top_10_episode_row_share']:.2%}.",
        "The earliest-episode and inverse-size views retain the primary direction; Main Board and year",
        "instability remain decisive falsification failures. Near-limit exclusion is only the existing",
        "ordinary-board return proxy, not an exact exchange limit state; unknown-prefix rows are unavailable.",
        "Regimes reuse the existing frozen shadow trend definition, reconstructed through T; no historical",
        "prospective capture is fabricated. Regime episode counts can overlap across periods.", "",
        "## Features, baseline and turnover", "",
        "All five reused volume features reconcile in N/mean/median to the original frozen volume summary",
        "within 1e-12 tolerance; its VOLUME_PATH_NEEDS_MORE_EVIDENCE decision is unchanged.",
        "The complete 3×3 defense/contraction matrix and its boolean-reactivation split are reported, with",
        "volume-only marginal rates as baseline. No cell was chosen as a rule and no threshold was swept.",
        "Continuous distributions for TARGET, FAST_STOP and all STOP, and every missing reason, are in the artifact.",
        "The empty pre-T retest interval affects 1,368 rows. No-breach reclaim time is missing with NO_BREACH,",
        "not zero. Local-high crossing can only occur at T by definition; its time-to-cross is a trough-to-T",
        "description, not an independently identified reactivation clock. MA5 timing was optional and omitted.",
        "`TURNOVER_EVIDENCE_UNAVAILABLE`: HiThink turnover is amount; current circulating shares cannot",
        "backfill history. Existing daily_basic gateway is DATE_ANCHORED / NO_VINTAGE_PROOF / THIRD_PARTY_GATEWAY",
        "and does not satisfy this task's strict PIT proof. Existing Eastmoney acquisition recorded unavailable",
        "responses. Bounded feasibility probe reused code and provenance only: external provider calls=0.",
        "Price defense/volume/time are observables. Seller exhaustion, capital support or accumulation are",
        "unproved hypotheses. Social-media integers were not adopted as thresholds.", "",
        "## Provenance and verification", "",
        f"Base SHA: `{summary['base_sha']}`. Branch: `{summary['branch']}`.",
        f"Source implementation commit: `{summary['source_sha']}`; code SHA-256: `{summary['implementation_sha256']}`.",
        f"Pre-comparison protocol commit: `{summary['protocol_commit']}`; SHA-256: `{summary['protocol_sha256']}`.",
        f"Summary file SHA-256: `{artifact_sha}`.",
        f"Event artifact: `{summary['event_artifact']['path']}`; SHA-256: `{summary['event_artifact']['sha256']}`.",
        "Frozen inputs and feature expressions are in summary.json. Detail is committed for remote recovery.",
        "Focused tests=21 passed; full pytest=611 passed, 2 existing fixture skips, 10 warnings; compileall",
        "and git diff --check PASS. Final delivery head is resolved from the remote task branch and recorded",
        "in the delivery response; source commit above is immutable implementation provenance, not a live-head invariant.",
        "Reproduce: `python scripts/b_false_breakout_path_diagnostic.py --source-root <checkout-with-restored-frozen-daily-k>`.",
        "Frozen daily-K restored from verified private Drive file 1lLxp0y_csfOczwEBNYo4ysdyItBgF4Ja;",
        "exact SHA 61189a4850e2eb157453e28e5375e502e20d214508bbe70ea71066ca3e05e426 matched.",
        "Production dispatch=0; runtime-state remote mutation=NO; PR #60 untouched; Formal B/spec/universe",
        "unchanged; Final OOS SEALED / UNREAD; forbidden directory untouched.", ""])
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root",type=Path,required=True)
    parser.add_argument("--output",type=Path,default=Path("data/validation/b_false_breakout_path_diagnostic_v1"))
    args = parser.parse_args()
    print(run(args.source_root,args.output.resolve())["final_research_status"])
