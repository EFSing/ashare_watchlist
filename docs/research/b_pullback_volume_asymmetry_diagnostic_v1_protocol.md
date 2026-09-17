# B Pullback Volume Asymmetry Diagnostic V1 Protocol

Status: `FROZEN_BEFORE_OUTCOME_COMPARISON`

Identity: `B_PULLBACK_VOLUME_ASYMMETRY_DIAGNOSTIC_V1`

Classification: research question; `DEVELOPMENT / DIAGNOSTIC_ONLY / INDEPENDENT_PROTOCOL`.

## Question and stopping condition

Question: within the already frozen Formal B qualified cohort, do observable pullback volume
structures distinguish `TARGET` from `FAST_STOP` after the existing price-defense observable is
reported, without changing Formal B?

Materiality: determine whether a separately authorized prospective observation could be justified.
This diagnostic cannot select a threshold, create B V2, modify Formal B, or change production.
Stop after this one fixed analysis and record exactly one terminal decision. If the frozen cohort,
pullback window, or breakout level cannot be reconciled exactly, stop with
`B_PULLBACK_VOLUME_ASYMMETRY_BLOCKED_BY_COHORT_RECONCILIATION`.

## Frozen source and boundaries

- Source branch: `codex/b-false-breakout-path-diagnostic-v1`; source head at intake:
  `9dcd93f6460006eed9f1d0e421b45c3abe5adc99`.
- This stacked branch reuses #66's committed diagnostic artifact and does not rewrite #66's
  protocol, report, summary, or conclusion.
- The cohort is the exact existing qualified Formal B cohort: 17,714 unique
  `(symbol, signal_date)` identities. The authoritative identity source is
  `data/validation/strategy_candidate_eligibility_v1/b_breakout_retest_eligibility_events.jsonl.gz`;
  #66's `events.jsonl.gz` supplies the frozen reconstructed labels and path identity.
- Expected cohort reconciliation is 17,714 rows; `TARGET=4,338`, `FAST_STOP=4,623`,
  `all STOP=7,953` (including `FAST_STOP`), and 9,766 unique `(symbol, breakout_date)` episodes.
  `FAST_STOP` is not added again to the all-STOP count.
- Formal strategy `B_BREAKOUT_RETEST_LEGACY_V1_1`, its qualification, score, ranking, trigger,
  stop, target, RR, T+1, same-bar semantics, universe, and spec SHA remain unchanged.
- No provider acquisition, production dispatch, runtime-state mutation, historical canonical rewrite,
  threshold sweep, grid search, model fitting, turnover, MACD, RSI, candlestick, new moving-average,
  sector, or turnover-proxy work is permitted. `Final OOS` and
  `data/validation/continuous_speed_probe/` are not read or touched.

## Exact existing window and level

The implementation must reuse #66's existing helpers rather than infer equivalent semantics:

- `scripts/b_phase_volume_path_diagnostic.py:_first_breakout_trace` identifies the first qualifying
  breakout `i` and returns `base_hi`.
- #66's array reconstruction uses `_adjusted_symbol_arrays`, the same corporate-action state through
  signal day `T`, and the same `LOOKBACK_BARS` slice.
- `T` is the last passed bar, the signal day. The pullback/retest window `R` is the observed bars
  `i+1` through `T-1`; Python slice notation is `i+1:T`, so the signal day is excluded.
- The breakout level is exactly `L=trace["base_hi"]=max(close[i-60:i])`. No alternate level or
  horizon is permitted.
- The existing `max_retest_depth_vs_breakout_level` from
  `scripts/b_false_breakout_path_diagnostic.py:path_features` is the only price-defense control.

## Five pre-registered features

Only these five features are added to this diagnostic. Missing means unavailable; no missing value
is replaced by zero or another value.

1. `down_volume_share`: on each `d` in `R`, classify a down day as
   `close[d] < close[d-1]`; compute the volume sum on down days divided by the volume sum on all
   `R` days. An empty window, non-finite sum, or invalid denominator is missing.
2. `up_down_volume_ratio`: classify up days as `close[d] > close[d-1]` and down days as
   `close[d] < close[d-1]`; compute mean up-day volume divided by mean down-day volume. It is
   computed only when both classes exist and both means are finite with a valid denominator.
   A ratio above one only means that average up-day volume is greater than average down-day volume.
3. `worst_price_day_volume_ratio`: choose the `R` day minimizing `low[d]/L`; an exact tie uses the
   earliest date. Compute that day's volume divided by breakout-day volume. An empty window,
   non-finite price ratio, or breakout volume `<=0` is missing.
4. `pullback_volume_decay_ratio`: only when `len(R) >= 4`, divide mean volume in the later half
   of `R` by mean volume in the earlier half. For an odd window, `R[len(R)//2:]` is the later half,
   so the middle day belongs to the later half. A window shorter than four days is missing.
5. `reactivation_vs_pullback_volume`: reuse #66's exact
   `reactivation_vs_retest_ratio` without recomputing it. It is
   `volume[T] / mean(volume[i+1:T])`, with the existing helper's missing semantics. It is not
   `reactivation / breakout volume`.

The report may include descriptive counts for the requested observable day-pair categories only:

- A: `close[d] < close[d-1]` and `volume[d] < volume[d-1]`;
- B: `close[d] >= close[d-1]` and `volume[d] < volume[d-1]`;
- C: `close[d] > close[d-1]` and `volume[d] > volume[d-1]`;
- D: `close[d] < close[d-1]` and `volume[d] >= volume[d-1]`.

Unclassified equal-volume/doji pairs are counted as descriptive `OTHER` only. These counts are not
features and cannot become a strategy rule.

## Labels and fixed comparisons

Primary comparison: `TARGET` versus `FAST_STOP`. Secondary comparison: `TARGET` versus all `STOP`.
Rows with other #66 labels remain in cohort counts but are excluded from each outcome comparison.
Report row-level counts, unique episode-level counts using the earliest qualified signal per
`(symbol, breakout_date)`, Main Board (`00`/`60`), and the fixed year split `2023`, `2024`, `2025`,
`2026`. No other subgroup is added.

For every feature, report eligible count, missing count, TARGET median/IQR, FAST_STOP median/IQR,
and the same fixed-tertile comparison for both label pairs. IQR is Q3 minus Q1 using the ordinary
numeric quantiles. Tertiles are assigned on all non-missing eligible rows before looking at outcome;
the existing deterministic equal-frequency ordering is value, symbol, signal date, and source row
order. The same full-cohort edges/assignment are reused for Main Board, years, and unique episodes.
Report every LOW/MID/HIGH cell and its count/rate; do not search for a cut point or select a best cell.

The two and only two 2D matrices are:

- Matrix A: `max_retest_depth_vs_breakout_level` tertile × `down_volume_share` tertile;
- Matrix B: `max_retest_depth_vs_breakout_level` tertile ×
  `worst_price_day_volume_ratio` tertile.

Every 3×3 cell reports count, `FAST_STOP/(TARGET+FAST_STOP)`, and the secondary
`STOP/(TARGET+STOP)` rate. No cell is promoted into a rule.

For the bounded incremental check, use only these same two matrices: a volume feature is
`matrix_consistent` when its expected endpoint-rate direction appears in at least two of the three
price-defense rows with usable endpoint cells and no usable row has the opposite direction. This is
a fixed summary of all matrix rows, not a best-cell selection; no additional matrix or conditional
model is permitted.

## Pre-registered directions and falsification

- H1: TARGET `down_volume_share` is lower than FAST_STOP.
- H2: TARGET `up_down_volume_ratio` is higher than FAST_STOP.
- H3: TARGET `worst_price_day_volume_ratio` is lower than FAST_STOP.
- H4: TARGET `pullback_volume_decay_ratio` is lower than FAST_STOP.
- H5: `reactivation_vs_pullback_volume` may be higher in TARGET, but only matters after H1-H4
  provide stable direction; because it aliases #66's existing baseline, no incremental mechanism or
  new model is inferred from it.

The fixed report must mark `NEEDS_MORE_EVIDENCE` if any of the following occurs: overall direction
does not persist on Main Board; a year split is clearly reversed; the direction disappears after
unique-episode reduction; TARGET versus all STOP reverses; most of H1-H4 disagree; the result exists
in only one year; a matrix effect is driven by a few small cells; or reactivation adds no stable
increment beyond the existing volume baseline. No feature, window, tertile, label, or indicator may
be changed in response.

Terminal rubric:

- `B_PULLBACK_VOLUME_ASYMMETRY_NO_SIGNAL` when the fixed comparisons show no stable directional
  information.
- `B_PULLBACK_VOLUME_ASYMMETRY_PROSPECTIVE_EVIDENCE_REQUIRED` when directional evidence exists but
  Main Board/year/unique-episode or incremental checks are insufficient for any strategy change.
- `B_PULLBACK_VOLUME_ASYMMETRY_RESEARCH_CANDIDATE_SUPPORTED` only when at least three of H1-H4 are
  stable, Main Board agrees, most years do not reverse, unique episodes retain the direction,
  TARGET versus FAST_STOP is clear, no small matrix cell drives it, and an interpretable increment
  over the #66 existing baseline is observable. Even then, stop for a separate user decision; do
  not create B V2 or change Formal B.
