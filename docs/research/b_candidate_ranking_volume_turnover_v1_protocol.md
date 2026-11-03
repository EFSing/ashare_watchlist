# B candidate ranking: volume / turnover V1 — pre-outcome protocol

Identity: `B_CANDIDATE_RANKING_VOLUME_TURNOVER_DIAGNOSTIC_V1`.
Classification: `research question`, STRICT PATH. Evidence labels: `DEVELOPMENT` /
`RECONSTRUCTED_RETROSPECTIVE` / `SAME_DAY_CROSS_SECTIONAL_RANKING` / `DIAGNOSTIC_ONLY`.

## Question and materiality

When several corrected B candidates qualify on the same day, can the three existing
report volume observations or the existing turnover/RV block improve selection beyond
the existing B `score_total`? This informs a user decision about a separate Ranking
design/validation task; it is not a release gate or permission to alter production.
Older studies have already observed outcomes. Their findings are not concealed or
rewritten. No new ranking outcome statistics have been read/calculated before this
protocol. Record this file's first commit as `PRE_OUTCOME_PROTOCOL_COMMIT`.

## Cohort and identity prerequisites

- Only `B_BREAKOUT_RETEST_LEGACY_V1_1`, spec SHA-256
  `f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd`.
- Reuse frozen DEVELOPMENT qualified identities and corrected-reconstruction membership
  proof, existing raw daily K, corporate actions, benchmark and canonical turnover.
  Verify actual identities, counts, date coverage and hashes; historical 17,714 and
  17,008 are expectations, not values to inject into results. No provider refetch.
- The authoritative historical qualified stream is
  `data/validation/strategy_candidate_eligibility_v1/b_breakout_retest_eligibility_events.jsonl.gz`;
  its older strategy label is usable only through the existing corrected-reconstruction
  event-set-invariance proof. Identity is `(symbol, signal_date, setup_id)`.
- **First gate:** recover exact existing `score_total` for every qualified identity,
  either as provenance-bound saved scores or through the unchanged full evaluator with
  exact historical inputs. Audit replay schemas and historical sector evidence first.
  Numeric projection is not evidence of full-score recovery. A neutral sector sentinel,
  today's membership, approximate score, default-filled missing historical inputs or a
  newly invented score are prohibited. A genuine evidenced V0 missing-symbol mapping
  and an unavailable historical mapping are different facts.
- If this gate fails, stop with
  `B_RANKING_BASELINE_SCORE_IDENTITY_NOT_RECOVERABLE`. Do not open outcome fields or
  fit/evaluate rankings. Publish the evidence gap and null metrics, not invented zeroes.

## Feature identities and parity

Use exactly `B_VOLUME_PROSPECTIVE_REPORT_OBSERVATION_V1` and its current
`scripts/volume_observation.py` pure calculator and `_first_breakout_trace`. Window
is `R=i+1:T-1`, excluding T. Parity must cover trace/window, empty/short windows,
flat days, denominator failures and exclusion of T. No fourth report variable.

Fixed quality hypotheses: lower `down_volume_share`, higher `up_down_volume_ratio`,
lower `pullback_volume_decay_ratio`. Do not reverse hypotheses after seeing outcomes;
opposite fitted relationships count as contradictions, not a revised hypothesis.

Reuse `B_TURNOVER_X_RELATIVE_VOLUME_INCREMENTAL_V1`: `turnover_rate_pct` from the
canonical third-party Tushare-compatible gateway dataset (DATE_ANCHORED /
NO_VINTAGE_PROOF); `RV20_T=volume_T/mean(volume[T-20:T-1])` from raw frozen volume.
Require 20 preceding valid bars and positive denominator. Neither has a prior
high-is-good hypothesis. Freeze interaction as the product of the **centered within-date
percentile ranks**, retaining both main effects; it is a statistical interaction,
not `turnover*RV` as a trading score.

## Baseline, models, missingness and estimation

M0 ranks exact existing B Score descending, ties by symbol ascending. M1 uses Score
and the three report observations; M2 uses Score, turnover, RV and the fixed
interaction; M3 uses all those fields. M0 is recalculated on each model's exact
complete-case cohort; also present all four on their common complete-case intersection.
No mean/zero imputation; non-finite is missing. Report missing counts/reasons by
feature, year, board, date and window length, plus available/missing outcome descriptives
only after the identity gate passes. Full Score-only cohort remains a separate result.

Within each comparison cohort and signal_date, continuous main effects use average-tie
percentile ranks `(average_rank-0.5)/n-0.5`; volume hypotheses orient the first/third
by multiplying by -1. Interaction is the turnover rank times the RV rank. No
future-date normalization. Dates with fewer than two candidates do not train/evaluate.
M1–M3 use fixed linear ridge, no intercept after date demeaning of 5D returns:
minimize date-equal mean squared error plus `0.01*sum(beta**2)`. Each row has weight
`1/(number_of_training_dates * candidates_on_that_date)`. No tuning, trees, search,
alternative windows, new features, threshold selection, best-cell or board selection.
Report all coefficients including hypothesis contradictions; do not refit to rescue them.

## Time separation and outcomes

Expected signal span 2023-06-30..2026-08-28 must be measured from identities.
Expanding folds: train 2023 → test 2024; train 2023–24 → test 2025;
train 2023–25 → test 2026 through frozen cutoff. Training rows must have their
5D outcome end strictly before the first test date (purge year-boundary overlap).
No test outcome selects coefficients, direction, model or hyperparameter.

Reuse existing V2 T+1 XSHG-open, corporate-action-adjusted fixed-horizon machinery:
primary 5D return; secondary 10D return, 5D/10D MFE and MAE. Missing/immature
outcomes remain unavailable; preserve separate denominators for each horizon.
These reconstructed outcomes are neither MODEL_P nor production performance.

## Ranking evaluation and uncertainty

Primary metrics: date-equal mean 5D Spearman IC and Top1/Top3 5D return uplift
versus paired M0. Also report median IC, each fold's IC, Top5, positive rate,
MFE/MAE, Top-K versus that day's entire comparable cohort mean, and incremental
Top-K versus M0. Top1 requires n>=2, Top3 n>=3, Top5 n>=5, each with its own
eligible date and row count. Undefined constant-rank IC is missing, not zero.
CI: 2,000 signal_date bootstrap resamples, seed 20261103; paired comparisons
resample the same dates. No row bootstrap. These intervals do not remove
serial/episode dependence; report that limitation.

Report date-equal ranked quintile mean returns and adjacent differences (no claim
of monotonicity from endpoints alone); fold/year consistency; fixed Main/ChiNext/STAR
sensitivities without selecting a board; earliest `(symbol, breakout_date)` episode
dedup sensitivity using existing deterministic identity, retaining only past-trained
predictions. Recompute comparable M0 and date counts in every sensitivity.

Each of the six features (three report fields, turnover, RV, interaction) must have
individual oriented/raw within-date IC, direction, quintile monotonicity, Top/Bottom
spread, year stability and coverage. Score-controlled increment uses the same
fixed walk-forward ridge with Score plus that feature (interaction also retains both
main effects), paired against the same-cohort M0. Distinguish descriptive association
from useful same-day ranking. Existing `VOLUME_PATH_NEEDS_MORE_EVIDENCE` and
`TURNOVER_X_RELATIVE_VOLUME_NEEDS_MORE_EVIDENCE` remain unchanged.

## Allowed decisions and stop conditions

Only these terminal research decisions are allowed:

- `B_VOLUME_TURNOVER_RANKING_SUPPORTED_FOR_FURTHER_VALIDATION`;
- `B_VOLUME_TURNOVER_RANKING_NEEDS_MORE_EVIDENCE`;
- `B_VOLUME_TURNOVER_RANKING_NO_CLEAR_INCREMENTAL_SIGNAL`.

Support requires a positive paired mean-IC increment with 95% date-bootstrap lower
bound >0 and positive Top1 and Top3 paired uplifts with at least one corresponding
95% lower bound >0; positive mean-IC and Top1/Top3 direction in at least two of three
folds; positive episode-dedup IC and Top1/Top3 increment; no MFE/MAE deterioration
larger than the return uplift magnitude; no reliance on an extreme small cell. Report
all four versions, never just the winning model. Conflicted/partial/inadequate evidence
maps to NEEDS_MORE_EVIDENCE. Broad absence or systematic opposite direction across
models/folds maps to NO_CLEAR_INCREMENTAL_SIGNAL. Missing exact baseline maps to
NEEDS_MORE_EVIDENCE **with the baseline blocker marker**, not a negative efficacy result.

Stop for unverified required identity/hash, nonrecoverable exact Score, incompatible
feature/outcome semantics, forbidden data exposure or required permissions. Do not
repair a missing baseline by collecting new data in this task. On blockage report
precisely missing evidence, the consuming Ranking decision, and product paths that
remain open. Do not declare support from legacy descriptive studies.

## Optional prospective sanity and absolute boundaries

Only after historical prerequisites pass, optionally inspect separately pinned runtime
T-close captured observations and mature MODEL_P, never MODEL_R. No backfill or zero
for immature paths. Report N/dates/maturity/missingness. Fewer than 20 multi-candidate
mature dates or 100 complete observations is
`PROSPECTIVE_RANKING_SANITY_CHECK_INSUFFICIENT_SAMPLE`; it never drives the primary
decision. A failed baseline gate stops before this optional check.

Final OOS remains SEALED / UNREAD; never read `continuous_speed_probe`. No change to
B spec/qualification/Score/gates/Top-N/levels/RR/T+1/T+10/tracker, MODEL_P/R definitions,
Formal B output, canonical schema, C, scheduler, provider production path or runtime-state.
No Wave/defensive-sector study, Phase 2F, promotion, production dispatch or auto-merge.
Deliver one branch/PR against live master with only this study and minimal #102
reconciliation; exact-head CI/mergeability are live checks. Stop for user decision.
