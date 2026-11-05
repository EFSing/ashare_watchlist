# B_STRUCTURE_FIRST_VOLUME_INCREMENTAL_SHADOW_V1

Status: FROZEN_BEFORE_CAPTURE_AND_OUTCOME_REVIEW. Classification: research
question / STRICT PATH, non-blocking. This is a separately authorized prospective
recording implementation, not a replacement of either #104 study.

## Question, materiality, inputs and stop

Within same-day `FORMAL_B_QUALIFIED ∩ W2_TO_W3_TRANSITION_PROXY`, does each of
the three existing report volume observations independently add stable candidate
quality information? The product decision is whether any single field merits
later priority research. Current Formal B and C remain usable without this
evidence. No new eligibility, entry, stop, target, T+10, Score, ranking or report.

Use only the genuine same-run T-close Formal B canonical watchlist, successful
run manifest, already acquired input package and existing report observation.
All qualified rows are recorded, including unavailable features; never select
the stored cohort by structure, volume or outcomes. No historical acquisition,
backfill, outcome files, provider request, tracker read or Final OOS access.
Ephemeral OHLCV is consumed but never copied into the durable artifact.

This task stops with an independent Draft PR, disabled and unmerged, at
`B_STRUCTURE_FIRST_VOLUME_INCREMENTAL_SHADOW_IMPLEMENTATION_READY_FOR_USER_DECISION`.
ADOPT this recording design only. Efficacy remains NEEDS_MORE_EVIDENCE: untouched
prospective, mature, identity-matched independent episodes are missing. A future
user-authorized priority-research decision consumes that evidence; existing
B/C daily operation continues. Merge, activation, outcome review, combinations
and production promotion require separate user authorization.

## Frozen structure, independent of qualification

Reuse the pure `structure_proxy` in `scripts/b_priority_w2w3_volume_v1.py`,
identity `B_W2W3_STRUCTURE_PROXY_V1`, originally frozen in protocol commit
`13008a3579a225af1f89f1facee1f22c48050195`. No subjective Elliott counting.
Recover only the original unconditional first breakout using
`b_phase_volume_path_diagnostic._first_breakout_trace`; do not search a better
later breakout or rerun eligibility. A missing/inconsistent trace marks structure
unavailable and retains the qualified row.

For breakout i and signal T, `L0=min(low[i-60:i])`, `H1=max(high[i:T])`,
`h1_index=first argmax`, `L2=min(low[h1_index+1:T])`. Require a complete day
after H1 before T and `L0 < L2 < H1`. Recovery is `(close_T-L2)/(H1-L2)`.

| Machine state | Meaning |
|---|---|
| EARLY_PULLBACK | recovery < 0.5 |
| W2_TO_W3_TRANSITION_PROXY | 0.5 <= recovery <= 1.0; primary cohort |
| POST_H1_CONTINUATION_PROXY | recovery > 1.0 |
| STRUCTURE_PROXY_UNAVAILABLE_OR_INVALID | missing/invalid structure, explicit reason |

H1/L2 exclude T high/low. Each row retains structure facts, state, transition
boolean and source identity. No future pivot confirmation or alternative proxy.

## VOLUME_FEATURE_HYPOTHESIS_V1: three separate hypotheses

Directly call `volume_observation.calculate_stock_volume_observation`, retaining
its exact version, original protocol commit, window_days and per-field missing
reasons. Compare against the same-run persisted report observation, including
partial cases, before writing. Identity mismatch refuses Shadow only.
R is exactly Python `i+1:T`, excluding T and including flat days in total volume.

| Field | Exact observable | Predeclared directional contrast |
|---|---|---|
| V1 down_volume_share | down-day volume sum / all R volume | LOW minus HIGH |
| V2 up_down_volume_ratio | mean up-day volume / mean down-day volume | HIGH minus LOW |
| V3 pullback_volume_decay_ratio | mean later-half volume / mean earlier-half volume | LOW minus HIGH; MID optimum explicitly possible |

Up/down compare each close to the preceding close. V2 needs both types. V3
needs >=4 days; for odd length the middle day belongs to the later half. Missing
denominators/windows remain null with the unchanged reason, never imputed.
V1 has only `PRIOR_EVIDENCE_RELATIVELY_MORE_PROMISING`, never PRESELECTED_WINNER;
all three are coequal independent hypotheses. Low/mid-low V1 and relative up-day
strength V2 are hypotheses, not validated quality. V3 is not assumed ever better
as it falls. Report monotone, U-shaped, middle-best, null and reverse possibilities
without choosing new thresholds or changing the preregistered contrast.

Within today's transition rows, for each field separately, ascending raw-value
percentile is average ordinal rank / that field's available N. No direction
inversion and no three-field complete-case requirement. N<3 -> null coordinate
and `INSUFFICIENT_CROSS_SECTION`. Otherwise fixed thirds: LOW p<=1/3, MID
1/3<p<=2/3, HIGH p>2/3. Equal values share the same coordinate/bucket; tied or
absent extreme buckets produce unavailable contrasts, never forced splitting.
Non-transition rows retain values with NOT_PRIMARY_COHORT coordinates.
These coordinates are not a Score or candidate priority. Rows retain canonical
order. No Top1/Top3, preferred/secondary/watch labels or new notification.

No composite is computed, imported, persisted or used. #104's equal-weight V0
stays an untouched LEGACY_EXPLORATORY_COMPARATOR in its old namespace and is
not collected here. No weights, optimization, winner preselection or combination
study, even if several fields eventually show evidence.

## Episodes and maturity without outcome access

Retain the existing B v1.1 `breakout_episode_id` (symbol, breakout_date,
window-local breakout_index, base_hi, frozen spec SHA). For independent-N and
review also freeze the existing V0 conservative dedup convention: same symbol
+ breakout_date + spec SHA is one analysis episode. This prevents rolling-window
index changes or T-anchor base changes splitting the same breakout. It is an
analysis key only and does not modify the existing observer's identity.

Keep every stock-date. Mark first observed signal in the episode and, separately,
the first transition observation in that episode. Primary episode analysis uses
the earliest captured transition row, never the best future result or volume.
Earlier non-transition observations cannot exclude that first transition. Unknown
episodes remain null and contribute no independent N. Capture gaps are explicit;
the first captured signal is not claimed to be the first ever historical signal.

Reuse XSHG and B v1.1's stricter checkpoint: >=60 completed real B T-close signal
sessions AND >=200 mature independent transition episodes; hard maximum 120
sessions. A successful real signal session with zero qualified rows still counts.
All dated post-activation completed B checkpoints count, including recorder gaps;
duplicate runs do not count again. Authorized weekend/historical backfill does
not count. Checkpoint metadata is read, tracker/outcome payloads are not.

The recorder can establish only T+10 calendar eligibility of the first transition
observation, not actual outcome maturity. At 60 sessions and >=200 calendar-eligible
episodes it pauses with REVIEW_REQUIRED_PENDING_OUTCOME_VERIFICATION. A separately
authorized review must verify >=200 actually mature, complete independent episodes
before efficacy conclusions. If verification is short, NEEDS_MORE_EVIDENCE; any
continuation needs user authorization and retains the original 120-session bound.
At session 120 recording stops; insufficient evidence yields
`B_STRUCTURE_VOLUME_PROSPECTIVE_EVIDENCE_INSUFFICIENT`, never lowered thresholds.
No early stopping for good returns. Recorder gaps do not extend the maximum.

## Frozen future evaluation, not implemented or run here

Primary horizon is 10D, reusing the stricter existing
`B_V1_1_PROSPECTIVE_OBSERVATION_PROTOCOL_V1` T+1 XSHG reference-open / future
T+10 close fixed-horizon convention, including its execution classifications,
corporate-action measurement, missingness and REFERENCE_EXECUTION_NOT_ACTUAL_FILL.
This reference-open endpoint is separately labelled; it is not relabelled as
MODEL_P's trigger-entry return. Secondary fixed horizons 3D/5D, 10D/5D MFE/MAE.
MODEL_P prospective trigger/entry/T+1-sellability/T+10 path target/stop and MODEL_R
read-only theoretical target/stop stay in separate panels/columns and denominators.
No model mixing, new execution model, changed entry/stop/target or fabricated fills.
Missing fixed-horizon evidence is unavailable rather than substituted with another
model's terminal return. Never read old outcome tables to select the endpoint.

For each V1/V2/V3 separately, report primary transition-only bucket means,
predeclared extreme contrast, hypothesis-favoured bucket minus the same-date
available-field transition baseline, all three buckets and nonlinearity. Report
stock-date and earliest-transition episode-dedup results; primary inference
date-equal-weights paired contrasts over common dates. Secondary EARLY/CONTINUATION
analyses get their own same-day field-specific coordinates at review; they cannot
replace primary or share pooled quantiles. Show all-qualified/transition baselines
and each field's missingness, cohort attrition and denominator at every step.

Freeze 95% date-cluster bootstrap CIs (10,000 resamples, seed 20261105), median
effects, date/month concentration, leave-one-date-out and largest-five-date
exclusion sensitivity. Use Holm correction across the three primary hypotheses;
report raw and adjusted p-values but never decide from p-value alone. Show each
calendar year, first/second calendar halves, board and symbol concentration.
Compare 2026 with later prospective years when present. Earlier-than-2026 evidence
is NOT_AVAILABLE_IN_NEW_PROSPECTIVE_COHORT; do not backfill a pre-activation
prospective period or mix old reconstructed V0 with this new cohort.

Trading-materiality research floor is 0.50 percentage points in primary 10D
date-equal episode-dedup extreme contrast AND positive favoured-bucket uplift
versus matched transition baseline. It is a research floor, not net profit or a
new gate. Costs are NOT_CALCULABLE absent an already authorized cost model.
Return, MFE, MAE, MODEL_P target/stop, MODEL_R target/stop, monotonicity, stability,
CI crossing zero and effective independent N must all be reported separately.

Per-field future decisions only:

- PROMOTE_FOR_PRIORITY_RESEARCH: minimum actual maturity met; primary favoured
  contrast CI above zero with Holm-adjusted p<0.05, materiality floor met, positive
  matched-baseline uplift, same direction raw/date-equal/dedup and calendar halves,
  and still positive after largest-five-date removal; no material opposite risk
  pattern (>=0.50pp worse MAE or >=5pp worse MODEL_P stop rate). Cross-year
  stability requires >=2 prospective calendar years with >=30 mature episodes
  each. If absent it remains NEEDS_MORE_EVIDENCE, never borrowed from V0.
- KEEP_AS_EXPLANATORY_ONLY: adequate evidence, no stable material priority gain,
  including nonlinear or small descriptive patterns that do not meet promotion.
- REJECT_AS_PRIORITY_SIGNAL: adequate evidence and stable reverse primary effect
  or a CI upper bound below the materiality floor; not a missing-data verdict.
- NEEDS_MORE_EVIDENCE: inadequate maturity/coverage/stability or wide uncertainty.

Any promotion above authorizes only a proposal for later research, never formal
report priority. If none qualifies, accept NO_VOLUME_FEATURE_PROMOTED. Combinations
need a new explicit user request after individual evidence. No outcome reader or
review command is supplied in this implementation.

## Lightweight storage and workflow boundary

Two immutable JSON artifacts per captured day under runtime-state:
`data/research/b_structure_volume_shadow_v1/{observations,daily}/YYYYMMDD.json`.
Observations contain all and only canonical qualified candidates, minimal
identities, structure and three separate volume observations/coordinates. Daily
receipt binds input/package/run/watchlist/report/protocol/source identities,
rows, SHA and bytes, checkpoint and gaps. No full OHLCV, full-universe data or
old Shadow overwrite. Each file <=256,000 bytes, combined <=500,000/day and
<=60,000,000 over 120 sessions (excluding Git overhead). Exceeding any cap
refuses the whole day, never truncates candidates. Typical tens of rows require
tens of KB; synthetic measurement is recorded with validation, not asserted as
an observed production size. Same-date mismatch fails closed for Shadow;
idempotent identical bytes are accepted. Only these two paths are staged/pushed
and remotely read back using the established narrow Git persistence pattern.

Separate post-delivery workflow step, after the existing C recorder, independent
of C success; default `ENABLE_B_STRUCTURE_VOLUME_SHADOW_V1=false`, explicit
`B_STRUCTURE_VOLUME_SHADOW_START_DATE` required. continue-on-error, 3 minutes,
CLI errors return a recording failure with B/C unchanged. No scheduler, provider,
delivery or health gate changes, no new notification. This PR never changes repo
variables, dispatches production or writes real runtime-state. Final OOS SEALED /
UNREAD. C lightweight recorder code, step and activation remain unchanged.
