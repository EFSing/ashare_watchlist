# B_PRIORITY_W2W3_VOLUME_EXPLORATORY_V0 — pre-outcome protocol

Date: 2026-11-04 Asia/Shanghai. Classification: research question / STRICT PATH.
Evidence: **DEVELOPMENT / RECONSTRUCTED_RETROSPECTIVE / EXPLORATORY /
LOW_CONFIDENCE / NOT_PRODUCTION_VALIDATED**.

## Authorization, question and stop

`USER_AUTHORIZED_EXPLORATORY_RELAXATION_OF_PARITY_GATE`: the user explicitly
permits this independent exploratory study without recovering real observation
T-day inputs or proving production-observation parity. Strict study
`B_PRIORITY_W2W3_VOLUME_RESEARCH_V1`, its protocol, report, artifacts,
`B_PRIORITY_RESEARCH_BLOCKED_BY_DATA_GAP` and three NEEDS_MORE_EVIDENCE markers
remain unchanged. This permission neither passes nor removes strict parity.

Question: accepting the frozen reconstructed structure and three volume values
as approximate features, can they directionally improve same-day qualified B
Top1/Top3 and demonstrate a research priority prototype? Materiality: inform
whether to propose a separately authorized production shadow observation and
make the future daily review ordering concrete. This is not a usable-gate
blocker. Stop after the fixed comparisons, prototype and decisions. A CI
including zero does not stop this study. Invalid identity/hash or forbidden
data access still fails closed. No new research phase, feature/weight search,
provider call, original observation-input recovery, production promotion or merge.

## Lock and frozen inputs

Commit this file before reading exploratory outcomes; its resulting SHA is
`EXPLORATORY_PRE_OUTCOME_PROTOCOL_COMMIT`, recorded subsequently in the runner,
summary and report (not self-referentially in this file). Verify committed
LF-normalized bytes on every run. Intake branch/PR head:
`codex/b-priority-w2w3-volume-v1` / Draft #104 /
`6322674c2aed49071fa0019ef34b6ea5841e7d41`; exact-head correctness run
41807685100 SUCCESS. Master `7d7b6c9f2de1c45e1a4b1a493395ac81646489d8`;
runtime-state `ebe014748cfd3a551b0e3589124e08b2c154871d`. Live snapshots only.

Reuse `data/validation/b_priority_w2w3_volume_v1/input_features.jsonl.gz`,
17,714 rows / 763 dates, compressed SHA-256
`1c4f70aff7cf9d6262ccbc89507b6ec35483f6207dc644279ca3e2ae4ae4dd82`,
content-stream SHA-256
`4b20355d1ca6b1a19db3d3d11374090f62e40fdb57a3e5a31f6305f06299e11d`.
Verify against the preserved strict summary. Its existing causal/future-append
and public-wrapper evidence is reused; do not reconstruct features differently.
Main: 10,779 rows / 749 dates, structure defined 9,085, volume complete 7,861 /
719 dates, structure-plus-volume intersection 7,541. Recheck counts live.
Primary Main Board; separate ChiNext and STAR robustness. Beijing 706 stays
out of scope. Frozen signal interval 2023-06-30..2026-08-28.

Outcome source is the already frozen, manifest/hash-verified B qualified event
stream named in the strict protocol, with its corrected V1_1 membership proof.
Inspect its schema and provenance after this lock. Require DEVELOPMENT V2
corporate-action-adjusted outcomes; if those are absent, use only the existing
V2 `_build_event_record` and exact frozen raw inputs to compute them, recording
which route was used. Never substitute raw V1 or A outcomes. Entry T+1 XSHG
open, exit T+5 / T+10 close; MFE/MAE over T+1 through that horizon. Missing
windows remain unavailable. Fixed-horizon outcomes are not executable fills.
Stop/target secondary is unavailable unless already frozen with proven B
semantics; no new path model. No MODEL_P/MODEL_R mixing.

## Fixed features and methods

Reuse `B_W2W3_STRUCTURE_PROXY_V1` exactly: L0/H1/L2, first breakout trace and
0.5 threshold unchanged. Four states: EARLY_PULLBACK,
W2_TO_W3_TRANSITION_PROXY, POST_H1_CONTINUATION_PROXY and existing explicit
invalid/unavailable state. Never tune them from outcomes. Historical feature
vintage is unverified and production-semantic drift is possible; causal prefix
invariance is not production parity or prospective validation.

Only down_volume_share (lower good), up_down_volume_ratio (higher good),
pullback_volume_decay_ratio (lower good). Average percentile ties divided by n;
good rank = 1-percentile for lower-good, percentile for higher-good.
`volume_quality = mean(three good ranks)`. No imputation, fitted weights,
turnover, RV, sector, Wave breadth, old Score or other features.

- R0: date-equal mean of same-day comparable B, plus full-cohort descriptive R0.
- R1: transition vs EARLY+CONTINUATION on dates with both groups, paired
  date-level contrast; all four states individually. Report both full
  structure-available and volume-complete intersection; never force Top1.
- R2: descending volume_quality, Top1/3/5, paired same-day R0 uplift,
  positive rate, MFE/MAE, date Spearman Rank IC and five rank groups.
- R3: descending `(is_transition, volume_quality)` only. Invalid structure is
  retained as non-transition, explicitly marked. No ordering between EARLY
  and CONTINUATION other than volume; show their actual outcomes separately.
  Also report paired R3-minus-R2 increment on identical eligible dates.
- Each individual volume field: its own valid rows and good direction;
  also compare the fields on the same three-field-complete rows to avoid
  presenting coverage differences as feature superiority.

For each horizon remove missing outcomes before rebuilding statistical ranks
and same-day benchmarks. All R2/R3 metrics use identical volume-complete rows
and dates; their R0 is matched, never the full-universe R0. Top1 needs >=2,
Top3 >=3, Top5 >=5 candidates. Fractional equal weights across a boundary tie;
no outcome-based tie breaking. R3 IC uses lexicographic ordinal ties. Five
groups use average ordinal rank midpoint into five bins on >=5-candidate,
nonconstant days; equal scores never split. Report empty-bin availability,
all five returns, paired top-bottom spread and monotonicity without tuning.

## Statistics and decisions

Overall and 2023/2024/2025/2026 frozen-cutoff views: eligible dates, rows,
date-level mean and median, date-equal positive fraction, MFE/MAE. Returns and
uplifts in percent / percentage points, positive rates explicitly percent.
95% signal-date cluster bootstrap CI: 10,000 resamples, seed 20261104, joint
date resampling of paired comparisons. No independent-stock inference. Date
clustering does not resolve serial dependence from overlapping forward windows.

Episode sensitivity: earliest `(symbol, breakout_date)` signal, then rebuild
complete-case cohorts, ranks, eligible dates and benchmarks. Report Main R1,
R2/R3 Top1/3/5 after deduplication. Secondary ChiNext/STAR use their own ranks.

Predeclare qualitative classification for R1 paired 5D contrast and R2/R3
Top1/Top3 5D matched uplifts: POSITIVE (方向明确) if all relevant overall
and dedup means >0, all relevant lower CIs >0 and each has >=3 positive years;
NEGATIVE (方向负面) for the symmetric negative conditions; MIXED
(方向偏正但不稳定 / 方向不稳定) if a mean is nonzero with conflicting signs,
years, CI or dedup; NONE (无明显方向) if no eligible evidence or all absolute
means <0.05 pp. These are descriptive exploratory buckets, not validation.
10D/risk/IC and multiple-comparison limitations must be disclosed even if the
5D marker is positive. No significance filtering of reported cells.

Emit three separate exploratory markers:
`EXPLORATORY_W2W3_SIGNAL_{POSITIVE|MIXED|NONE|NEGATIVE}`,
`EXPLORATORY_VOLUME_SIGNAL_{POSITIVE|MIXED|NONE|NEGATIVE}`,
`EXPLORATORY_W2W3_VOLUME_PRIORITY_{POSITIVE|MIXED|NONE|NEGATIVE}`.
Record ADOPT only for the fixed research demonstration; production remains
NEEDS_MORE_EVIDENCE. Recommend or reject a bounded future shadow proposal from
the total direction/stability/risk evidence; do not activate one.

## B_PRIORITY_PROTOTYPE_V0 (always generate)

Research only, `RESEARCH_PROTOTYPE_LABEL`. Rank same-day Main three-volume
complete candidates by R3; ties deterministically by symbol then setup_id for
display only. Statistics retain fractional ties. No outcome availability or
outcome value enters prototype selection, ranks, labels or explanations.
`priority_rank=1..N`: when N>=2 rank1 首选; ranks2–3 次选; others 观察.
When N=1 label 观察 (insufficient peer comparison), never duplicate securities.
Incomplete volume rows stay explicitly unavailable outside the ranked table.
Show state, three raw volume values, volume_quality, rank, label and deterministic
rationale; no old Score, A/B/C priority or Formal B renderer change.

Representative dates fixed without outcomes: earliest eligible, upper-middle
eligible (`sorted_dates[len//2]`), latest eligible and largest complete candidate
count (earliest date breaks ties); eligibility N>=2. Deduplicate date choices.
Generate research-only HTML/Markdown with 股票 / 结构阶段 / 回踩量能 /
今日优先级 / 原因 and audit values. Do not cherry-pick profitable dates.

## Delivery and boundaries

Independent runner, small tracked summary, Chinese report, prototype and
deterministic detail with byte/stream hashes and reproduction command. Strict
artifacts are immutable. Existing frozen raw recovery reference remains valid;
new outputs are reproducible with existing inputs, never another repo.
Full pytest, compileall, diff boundary check, deterministic rerun/hash, push and
exact-head CI readback. Keep #104 Draft/open; update its title/body to include
strict parity blocker + user-authorized exploratory V0. No new branch/PR/merge.
End `B_PRIORITY_EXPLORATORY_V0_READY_FOR_USER_DECISION`.

Final OOS **SEALED / UNREAD**; continuous_speed_probe prohibited. Formal B
qualification, Score/report/tracker, runtime-state, provider, scheduler, C and
production semantics unchanged. Production dispatch=0; production ranking=0.
All results are directional low-confidence evidence, never production-valid or
prospectively validated. Strict parity remains NOT_RUN_INPUTS_UNAVAILABLE.
