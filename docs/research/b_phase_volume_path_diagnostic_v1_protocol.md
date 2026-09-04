# B Phase Volume Path Diagnostic V1 Protocol

Status: `FROZEN_BEFORE_OUTCOME_READ`  
Task identity: `B_PHASE_VOLUME_PATH_DIAGNOSTIC_V1`  
Evidence labels: `DEVELOPMENT` / `RECONSTRUCTED_RETROSPECTIVE` / `DIAGNOSTIC_ONLY`

## Purpose and materiality

This diagnostic asks whether the volume path inside the corrected
`B_BREAKOUT_RETEST_LEGACY_V1_1` structure contains candidate-quality information beyond
the current aggregate pull-volume condition. The result can support or reject only a
later, separately authorized validation study. It cannot change B, select a threshold,
promote a strategy, alter the prospective pipeline, or read Final OOS.

The product-directed reason is narrow: determine whether one pre-defined diagnostic
hypothesis is sufficiently stable to justify spending another validation cycle on it.
This research is not a correctness or product blocker.

## Frozen inputs and invariants

- Corrected strategy: `B_BREAKOUT_RETEST_LEGACY_V1_1`.
- Strategy spec SHA-256:
  `f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd`.
- Frozen DEVELOPMENT daily-K SHA-256:
  `61189a4850e2eb157453e28e5375e502e20d214508bbe70ea71066ca3e05e426`.
- Frozen continuous dataset:
  `core-signal-hithink-continuous-2023-06-30-to-2026-08-28-v1`.
- Signal timing is T close. Entry and outcomes use the existing T+1 XSHG-open and
  corporate-action-adjusted V2 outcome machinery.
- Features use bars through T only. Future bars and future corporate actions may be used
  only for ex-post outcomes.
- Evaluation-level observations remain canonical; repeated breakout episodes are not
  deduplicated from the primary result.
- Frozen input bytes, B evaluator/spec/score/thresholds, universe, sector and ST rules are
  immutable for this task.

## Primary question

Within current corrected B-like breakout-to-retest observations, do:

1. pre-T retest volume contraction relative to breakout volume, and
2. T-day reactivation volume relative to pre-T retest volume

show stable continuous relationships with 5D/10D return and 5D/10D MFE/MAE measured
from T+1 XSHG open?

The 1D and 3D outcomes are secondary diagnostics and will not drive the decision.

## Secondary question

After an exact current-B first qualifying breakout, is the volume path systematically
different between observations that form a B pullback/retest and structurally comparable
observations whose first-breakout pullback stage fails?

Pattern-stage classification is reported separately from downstream B hard-gate status.
Near-misses are not required to pass downstream risk/RR/overhang gates.

## Exact first-breakout semantics

For an evaluation window of length `n`, scan exactly:

`range(max(61, n - 15), n - 1)`

The first `i` satisfying all three breakout conditions is selected:

- `close[i] > max(close[i-60:i])`;
- `volume[i] >= 1.8 * mean(volume[i-20:i])`;
- `close[i] / close[i-1] - 1 >= 0.03`.

The scan ends unconditionally after that first qualifying breakout, even when the later
pullback stage fails. Signal evaluation day is `T = n - 1`. Current B scan, breakout,
pullback and outcome timing semantics are not rewritten.

## Frozen feature definitions

For the exact first qualifying breakout index `i`:

1. `breakout_volume_ratio = volume[i] / mean(volume[i-20:i])`.
2. `b_existing_pull_volume_ratio = mean(volume[i+1:n]) / volume[i]` when
   `n - 1 > i + 1`, otherwise `volume[n-1] / volume[i]`. This is exact parity with
   current B's existing pull-volume semantics.
3. `pre_t_retest_volume_ratio = mean(volume[i+1:n-1]) / volume[i]` only when
   `i + 1 <= n - 2`; signal-day T is excluded.
4. `reactivation_vs_retest_ratio = volume[n-1] / mean(volume[i+1:n-1])` only when
   the pre-T interval has at least one bar and its mean volume is positive.
5. `reactivation_vs_breakout_ratio = volume[n-1] / volume[i]`.

If breakout occurs at T-1, both pre-T retest features are unavailable with reason
`NO_PRE_T_RETEST_INTERVAL`; no zero, one or interpolation is inserted. Any zero or
non-finite denominator produces an unavailable value and an explicit reason, never
infinity or a fabricated value.

Minimal price context, used only for interpretation, is fixed as signal-day return,
close/previous-close, close/MA5, close position in the signal-day high-low range when the
range is positive, distance from `base_hi`, and existing `pos250`.

## Cohorts

### A. QUALIFIED-B

The authoritative evaluation-level qualified event identity is the existing 17,714-event
DEVELOPMENT B lineage, reconciled to corrected V1_1 by the established invariant-event-set
audit. Qualification is not changed. The report must include input, matched, feature-
computable, symbol, signal-date, unavailable-reason and year counts.

### B. FIRST-BREAKOUT STRUCTURAL

Across every evaluation row in the frozen DEVELOPMENT evaluation universe, retain rows
with an exact first qualifying breakout. Evaluate these three pullback dimensions at T:

- price structure: both close floor and within-platform tests pass;
- volume: the exact current aggregate pull-volume test passes;
- turn strength: the exact current turn-strength test passes.

Assign one mutually exclusive label:

- `PULLBACK_ALL_PASS`: all three dimensions pass;
- `PULLBACK_VOLUME_FAIL_ONLY`: only volume fails;
- `PULLBACK_TURN_STRENGTH_FAIL_ONLY`: only turn strength fails;
- `PULLBACK_PRICE_STRUCTURE_FAIL`: only price structure fails;
- `PULLBACK_MULTIPLE_FAIL`: two or three dimensions fail.

`final_b_qualified` is reported independently from these pattern-stage labels. It requires
the existing downstream hard gates but is not part of the structural label.

## Outcomes

The implementation must call the existing adjusted V2 outcome builder. Primary fields are
5D/10D return, MFE and MAE; secondary fields are 1D/3D. Entry is T+1 XSHG open. No second
adjustment or entry implementation is permitted.

## Analysis plan frozen before outcome read

- Overall distributions for all five volume features: N, unavailable N, mean, standard
  deviation, minimum, 10th/25th/50th/75th/90th percentiles and maximum.
- Qualified-B equal-frequency deciles for each primary feature. If a feature has fewer
  than 1,000 computable qualified observations or any decile has fewer than 100 rows,
  use quintiles for that feature and record the reason. Binning is deterministic with
  rank-first tie handling; it is not changed after results are seen.
- For each bin and primary horizon: N, mean/median return, positive rate, mean/median MFE,
  and mean/median MAE.
- Spearman rank correlation between each primary feature and every 5D/10D return/MFE/MAE.
- Top-versus-bottom bin descriptive spreads.
- A quintile-by-quintile matrix of `pre_t_retest_volume_ratio` by
  `reactivation_vs_retest_ratio`, with N and the same 5D/10D outcome statistics per cell.
- The structural cohort uses fixed quintiles, stage counts and stage-level outcome tables;
  it is descriptive and does not define a rule.
- Year robustness is reported for 2023, 2024, 2025 and 2026. Board robustness uses exact
  prefixes: main=`00` or `60`, ChiNext=`30`, STAR=`68`; other prefixes are reported as
  unavailable/out-of-scope, not reassigned.
- Dependence audit reports unique `(symbol, breakout_date)` episodes and the share of
  evaluation rows belonging to repeated episodes.

No cutoff search, parameter sweep, optimization, model fitting, feature selection,
score change or Top-N analysis is allowed.

## Near-price-limit proxy sensitivity

No external trading-status data will be acquired. A diagnostic proxy, not an exchange
state, is fixed as absolute T-day close-to-previous-close return at least 9.5% for main-board
symbols and at least 19.0% for ChiNext/STAR symbols. Unknown ST/special-treatment and exact
daily limit regimes are not inferred. Results are reported including and excluding these
proxy observations under the title
`NEAR_PRICE_LIMIT_PROXY_SENSITIVITY_NOT_EXACT_LIMIT_STATE`. The proxy is not a B filter and
cannot drive threshold selection. If required OHLCV is unavailable, exact limit analysis is
recorded as `DEFERRED_REQUIRES_PIT_TRADING_STATUS_DATA`.

## Pre-registered decision rubric

The final research decision must be exactly one of the following three.

### `VOLUME_PATH_SUPPORTED_FOR_FURTHER_VALIDATION`

At least one of the two primary decomposed features must meet all of these descriptive
coherence checks on the qualified cohort for at least one primary horizon:

1. its overall Spearman sign agrees with both the top-minus-bottom mean-return and median-
   return spreads;
2. at least three of four adjacent quintile transitions follow that same direction (decile
   output is collapsed to fixed quintiles only for this coherence check), so the result is
   not a single-bin spike;
3. the end-quintile mean-return spread has that direction in at least three of the four
   named years with at least 30 available observations per end bin;
4. the end-quintile mean-return spread has that direction in at least two of the three
   named boards with at least 30 available observations per end bin;
5. the 2D matrix is directionally compatible rather than reversing the univariate result;
6. excluding the near-price-limit proxy rows preserves the overall Spearman sign and the
   top-minus-bottom mean-return spread sign.

This decision means only that an independently authorized validation is worthwhile.

### `VOLUME_PATH_NEEDS_MORE_EVIDENCE`

Use this when there is an overall relationship but any required coherence check above is
not met, the relationship is weak/unstable, extremes dominate, qualified and structural
cohorts conflict, the near-limit proxy materially changes the direction, or a non-monotonic
/ inverted-U pattern is observed. A non-monotonic finding is labeled
`NON_MONOTONIC_RELATIONSHIP_OBSERVED`; no best cutoff is sought.

### `VOLUME_PATH_NO_CLEAR_INCREMENTAL_SIGNAL`

Use this when both decomposed primary relationships are broadly flat or directionally
inconsistent across 5D/10D, years and boards, are driven by an isolated bin, and the
reactivation decomposition supplies no coherent information beyond the current aggregate
pull-volume measure.

## Expected outputs and stop

- `docs/research/b_phase_volume_path_diagnostic_v1_report.md`;
- `data/validation/b_phase_volume_path_diagnostic_v1/summary.json`;
- a deterministic derived event artifact only if its committed size is reasonable;
  otherwise the summary records row count, content SHA and reproduction command.

The report must include cohort reconciliation, feature distributions, three primary
quantile tables, the 2D matrix, year/board robustness, near-price-limit sensitivity,
dependence counts, feature availability, the three-way decision and artifact identities.

Stop at `B_VOLUME_PATH_DIAGNOSTIC_PR_READY_FOR_USER_DECISION`. Do not merge the research PR
and do not start a second validation or add deferred turnover/distribution hypotheses.
