# B Volume Prospective Report Observation V1

Status: `FROZEN_BEFORE_PROSPECTIVE_CAPTURE`

Identity: `B_VOLUME_PROSPECTIVE_REPORT_OBSERVATION_V1`

Classification: `PROSPECTIVE_OBSERVATION / REPORT_ONLY / NO_STRATEGY_CHANGE`.

## Source and stopping boundary

This protocol freezes the report-only observables derived from PR #68,
`research: pullback volume asymmetry diagnostic V1`.

- Source PR: `#68`
- Source branch: `codex/b-pullback-volume-asymmetry-diagnostic-v1`
- Source head SHA: `916916426f3af6d5e8a451c4baea0fa69a119378`
- Source protocol commit SHA: `d0a477db3f375ef19fdec51bb091ac3162ea6278`
- Source terminal: `B_PULLBACK_VOLUME_ASYMMETRY_PROSPECTIVE_EVIDENCE_REQUIRED`

The existing Formal B T-close candidate and its exact breakout trace are the
only source of candidates.  The breakout day is `i`, the signal day is `T`,
and the observation window is exactly `R = i+1:T-1` (Python slice
`i+1:T`).  The signal day `T` is excluded.  The breakout level remains
`L = max(close[i-60:i])`, recovered through the existing deterministic
breakout helper.  This preserves T-close point-in-time and no-lookahead
semantics.

If the existing breakout/window semantics cannot be reconciled with the
frozen #68 definition, stop with
`B_VOLUME_PROSPECTIVE_REPORT_BLOCKED_BY_SEMANTIC_RECONCILIATION`; do not infer
an alternative window or trace.

## Frozen observables

Only the following three metrics enter this prospective report observation.
They are descriptive values, not strategy inputs.

### Primary: `up_down_volume_ratio`

For each day `d` in `R`:

- an up day satisfies `close[d] > close[d-1]`;
- a down day satisfies `close[d] < close[d-1]`.

`mean_up_volume` is the mean volume on up days and `mean_down_volume` is the
mean volume on down days.  The primary observable is
`mean_up_volume / mean_down_volume`.  It is missing unless `R` contains at
least one up day and one down day and the denominator is valid and finite.

### Secondary: `down_volume_share`

`sum(volume on down days) / sum(volume in R)`.  It is missing for an empty
window or an invalid/non-finite denominator.

### Secondary: `pullback_volume_decay_ratio`

It is missing when `len(R) < 4`.  Otherwise split `R` into an earlier and a
later half; for an odd number of days the middle day belongs to the later
half.  The value is `mean(volume in later half) /
mean(volume in earlier half)`, missing if either mean or the resulting ratio
is invalid/non-finite.

No fourth or fifth volume metric is frozen.  In particular,
`worst_price_day_volume_ratio` and `reactivation_vs_pullback_volume` are not
prospective report fields.

## Missing and report semantics

Observation calculation is fail-soft.  Missing volume observations must not
remove a Formal B candidate, change candidate order/rank, fail the production
run, or fail the canonical report.  The report displays:

- no pullback window: `样本不足`;
- no simultaneous up and down days: `上涨/下跌日均量比：—`;
- a window shorter than four days: `回踩后半/前半均量比：—`.

The report renders the three values as two descriptive cards:

- `回踩量能`: `下跌日成交量占比` and `上涨/下跌日均量比`;
- `量能衰减`: `回踩后半/前半均量比`.

The cards may show `观察窗口：N 个交易日`.  Explanations are neutral and
descriptive: ratios above/below/near one describe relative volume only and
must not use health, strength, weakness, buy, avoid, score, or risk labels.
Both areas end with `观察指标 · 不参与筛选/排名`.

The report presentation removes only the legacy `市场` and
`再启动量能 → breakout` display.  Existing market/universe metadata,
Main Board gating, manifests, validation fields, and generation identity are
unchanged.

## Persistence and boundaries

When the existing shadow monitor pre-outcome metadata slot can carry the
values, it records `observation_version` and the three frozen fields plus
field-level missing reasons.  This metadata remains observational and
fail-soft.  No new framework or canonical runtime-state schema is created.

The protocol does not modify `B_BREAKOUT_RETEST_LEGACY_V1_1`, qualification,
pullback gates, score, ranking, trigger, stop, target, RR, T+1, same-bar
semantics, the Main Board-only universe, or its spec SHA.  It introduces no
threshold, filter, ranking input, historical threshold search, retrospective
optimization, B V2, provider change, delivery change, production dispatch,
runtime-state mutation, or historical report rewrite.  Final OOS remains
`SEALED / UNREAD`.
