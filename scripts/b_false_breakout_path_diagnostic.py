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
             "exclude_near_limit_proxy": frame[~frame.near_price_limit_proxy],
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
        dt = [replay._date_from_ms(int(x)) for x in dates[start:end]]
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
    summary = {"schema_version":TASK,"labels":["DEVELOPMENT","RECONSTRUCTED_RETROSPECTIVE","DIAGNOSTIC_ONLY"],
               "base_sha":BASE,"branch":"codex/b-false-breakout-path-diagnostic-v1",
               "source_sha":subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,text=True).strip(),
               "implementation_sha256":sha(Path(__file__)),
               "protocol_commit":subprocess.check_output(["git","rev-parse",PROTOCOL_COMMIT],cwd=root,text=True).strip(),"protocol_sha256":sha(root/PROTOCOL),
               "cohort_identity":"frozen-qualified-B-17714","input_sha256":inputs,"spec_sha256":STRATEGY_SPEC_SHA256,
               "feature_definitions":{"protocol":PROTOCOL,"volume_baseline":"b_phase_volume_path_diagnostic_v1_protocol.md","anchor":"exact first breakout base_hi","retest":"i+1:T-1"},
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
    (output/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root",type=Path,required=True)
    parser.add_argument("--output",type=Path,default=Path("data/validation/b_false_breakout_path_diagnostic_v1"))
    args = parser.parse_args()
    print(run(args.source_root,args.output.resolve())["final_research_status"])
