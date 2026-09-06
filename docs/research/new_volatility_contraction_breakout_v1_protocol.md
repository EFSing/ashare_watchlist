# NEW_VOLATILITY_CONTRACTION_BREAKOUT_V1 — pre-outcome protocol

Status: `PRE_OUTCOME_PROTOCOL_COMMITTED`

Research identity: `NEW_VOLATILITY_CONTRACTION_BREAKOUT_V1`

Labels: `DEVELOPMENT`, `RECONSTRUCTED_RETROSPECTIVE`, `DATE_ANCHORED`,
`DIAGNOSTIC_ONLY`, `NEW_RESEARCH_HYPOTHESIS`,
`PREDICTIVE_EVIDENCE_UNTESTED_AT_PROTOCOL`, `MECHANISM_EVIDENCE_HYPOTHESIS`,
`FINAL_OOS_UNREAD`, `NO_VINTAGE_PROOF`.

`VCB_PRE_OUTCOME_PROTOCOL_COMMIT=TO_BE_RECORDED_AFTER_COMMIT`

This document fixes the research before any forward outcome for this candidate is
read. It is an independent evaluator. It does not modify
`B_BREAKOUT_RETEST_LEGACY_V1_1`, its prospective observation path, RS leadership,
Volume-Path, turnover/RV diagnostics, any production watchlist path, frozen state,
or Final OOS.

## 1. Research question and identification boundary

Research question:

> Among stocks that have the same generic close-above-prior-20-session-high
> breakout on T, does a pre-breakout volatility contraction provide stable
> incremental information about the future outcome relative to generic-breakout
> stocks without that contraction?

This is not a test of whether breakout stocks subsequently rise. The primary
identification is candidate versus the mutually exclusive generic-breakout
control. A positive candidate return against the full generic-breakout baseline
is not sufficient because that baseline contains the candidate.

Observable definition/proxy claim:

- recent realized normalized true range;
- prior realized normalized true range;
- their contraction ratio;
- same-date cross-sectional contraction rank;
- generic close breakout above the prior 20-session high;
- future returns under the existing DEVELOPMENT reference-execution convention.

Possible mechanisms are hypotheses only: temporary information quietness,
positioning compression, supply/demand equilibrium, volatility clustering or
regime transition, and latent information arrival preceding expansion. The result
must not be described as proof of accumulation, locked-up chips, capital entry,
or causal breakout mechanics. `MECHANISM_EVIDENCE=HYPOTHESIS` remains fixed even
if predictive evidence is positive.

## 2. Input audit completed before outcome access

The evaluator reuses the existing frozen/development replay inputs. It does not
fetch a provider, use today's universe, backfill current constituents or sectors,
replace the provider, or read Final OOS. The VCB signal pass is independent of
the production/prospective generator and of the B/RS outcome artifacts.

### Historical point-in-time universe

- Source: existing date-anchored continuous replay universe, defined as
  historical daily-K rows present at T with at least 120 valid bars through T.
- Sessions: 769 completed XSHG sessions, 2023-06-30 through 2026-08-28.
- Existing replay symbol-date identities: 4,041,140.
- Existing identity hash over sorted `signal_date|symbol` identities:
  `dbc5d220f24f51a0245d047b88733c961fc4f184d02ef6f5ac0fc795576217b0`.
- This is a date-anchored historical cross-section, not today's universe
  backfilled into the past. A symbol is absent before its T-day raw bar exists.
- Listing/history handling is inherited from the frozen replay: symbols with a
  T-day bar but fewer than 120 bars are excluded from the authoritative replay
  universe; no interpolation, future fill, shorter-window substitution or whole
  session deletion is allowed.
- Board identity is descriptive only: Main=`00`/`60`, ChiNext=`30`, STAR=`68`,
  and other observed prefixes remain retained/reported as
  `OUT_OF_SCOPE_PREFIX` if present.

### OHLC and corporate-action basis

- Raw source: frozen HiThink Financial-API daily-K input,
  `data/validation/core_signal_validation/raw/daily_k.parquet`.
- Daily-K file SHA-256:
  `61189a4850e2eb157453e28e5375e502e20d214508bb70ea71066ca3e05e426`.
- Adjustment-factor file SHA-256:
  `a1b7d63c5826ccd3610dc9bdd949d82eeb0ba84ffad451bfb8bb30ca74962716`.
- Signal OHLC uses the already validated
  `HISTORICAL_T_ANCHOR_PRICE_RAW_VOLUME` convention: for each T, events with
  `ex_date <= T` are applied to pre-ex-date OHLC prices using the frozen affine
  transform; volume and traded amount remain raw unadjusted. No event after T
  enters the signal features.
- The raw dump has no per-bar historical vintage timestamp. The honest label is
  `NO_VINTAGE_PROOF`; the existing acquisition/content provenance is not upgraded
  to a stronger known-at claim.
- The audit must verify positive finite OHLC, duplicate-free symbol/date keys,
  non-negative volume, valid adjustment denominators, and that all signal bars end
  at T. Any mismatch is `VCB_INPUT_PROVENANCE_CONFLICT`.

### Calendar

All windows count completed XSHG signal sessions from the existing benchmark
calendar, not calendar days. Signal time is T close in `Asia/Shanghai`.

`NO_OUTCOME_INPUT_AUDIT=PASS` is valid only after the above identities, hashes,
coverage and calendar checks pass. If the replay universe cannot be legally
reused, stop with `VCB_HISTORICAL_PIT_UNIVERSE_NOT_AVAILABLE`. If a comparable
historical OHLC basis cannot be formed, stop with
`VCB_SIGNAL_OHLC_BASIS_NOT_AVAILABLE`.

## 3. Fixed signal specification

These are pre-registered design choices, not optimized parameters:

```text
RECENT_RANGE_WINDOW = 10 sessions
REFERENCE_RANGE_WINDOW = 40 sessions
BREAKOUT_WINDOW = 20 sessions
COMPRESSION_QUANTILE = 20%
ACTUAL_CONTRACTION_BOUNDARY = ratio < 1.0
```

No alternative window, percentile, breakout length, volume filter, turnover,
turnover rate, RV filter, amount threshold, moving average, sector, RS, B,
support, RR or score condition may be tried in this protocol. V1 has
`VOLUME_CONFIRMATION_DISABLED_IN_V1`: volume/traded amount may appear only as a
descriptive diagnostic when already-lawful inputs support it.

For each symbol and each historical signal session T, define normalized true
range only when OHLC and the previous close are finite and positive:

```text
TR_d = max(high_d - low_d,
           abs(high_d - close_{d-1}),
           abs(low_d - close_{d-1}))
TRP_d = TR_d / close_{d-1}
```

The compression feature excludes T itself:

```text
RECENT_TRP10_T = mean(TRP over T-10 ... T-1)
REFERENCE_TRP40_T = mean(TRP over T-50 ... T-11)
CONTRACTION_RATIO_T = RECENT_TRP10_T / REFERENCE_TRP40_T
```

The denominator must be finite and strictly positive. A missing bar, missing
previous close, invalid OHLC or invalid denominator makes the feature invalid;
the evaluator must not interpolate, forward-fill or use a shorter window.
`actual_contraction = contraction_ratio < 1.0`. Ratio equal to 1.0 is not a
contraction.

At each T, among all historical-universe eligible symbol-dates with a valid
contraction ratio, sort ascending by `contraction_ratio`, breaking exact ties by
ascending canonical symbol. Let `N` be the valid count and
`BOTTOM_K = ceil(0.20 * N)`. `compression_rank` is one-based with 1 meaning the
smallest ratio. `strong_compression` is true exactly when
`compression_rank <= BOTTOM_K` and `contraction_ratio < 1.0`. A ratio at or above
1.0 remains false even if it falls in the bottom K by rank.

The generic breakout is fixed as:

```text
PRIOR_HIGH20_T = max(high over T-20 ... T-1)
GENERIC_BREAKOUT_T = close_T > PRIOR_HIGH20_T
```

The comparison is strict `>`, excludes T high from the prior window, and has no
volume, MA, sector, RS, B, support, RR, score or tradability gate.

```text
VCB_CANDIDATE_T = GENERIC_BREAKOUT_T AND STRONG_COMPRESSION_T
VCB_PRIMARY_CONTROL_T = GENERIC_BREAKOUT_T AND NOT STRONG_COMPRESSION_T
```

Within valid feature rows, candidate and control are disjoint and their union is
exactly generic breakout. The primary control is the incremental identification
set; the full generic-breakout baseline contains the candidate and is secondary.

Signal construction requires T through T-50 and T-51 close for the earliest TRP,
equivalently at least 52 valid chronological bars including T. Rows failing the
exact boundary are `INSUFFICIENT_SIGNAL_HISTORY`. No shorter-window substitution
or future fill is allowed. The inherited replay universe normally has at least
120 bars; the explicit 52-bar boundary remains tested and reported.

## 4. Signal output and signal-only audit

The evaluator writes deterministic rows sorted by `date, symbol` and does not
connect to the prospective production path. Each row contains at least:

- `date`, `symbol`, board and signal timing;
- `trp_recent10`, `trp_reference40`, `contraction_ratio`, `compression_rank`,
  `actual_contraction`, `strong_compression`;
- `prior_high20`, `close_t`, `generic_breakout`, `candidate`,
  `primary_control`;
- eligibility and exclusion reason;
- lawful descriptive volume/traded-amount fields only if available, never used
  for qualification.

Before any VCB forward outcome is read, report total sessions, eligible
symbol-dates, valid feature count, insufficient-history count, generic breakouts,
candidate count, control count, active dates for each group, dates with both
groups, mean/median group N per date, year counts, board counts, unique symbols,
top-1/top-5 symbol concentration, candidate persistence and repeated generic
breakout frequency.

Research readiness is a sample gate, not a performance threshold:

```text
BOTH_GROUP_ACTIVE_DATES >= 200
CANDIDATE_EVENTS >= 500
CONTROL_EVENTS >= 500
```

Failure is `VCB_SIGNAL_CONSTRUCTION_NOT_RESEARCH_READY`; rules may not be changed
to enlarge the sample.

### Signal overlap diagnostic

The evaluator may read only existing signal membership for B and, if canonical
membership is lawfully available, RS leadership V1. It must not read B
prospective outcomes or rebuild any outcome artifact. Report candidate same-date
overlap, exact symbol-date overlap, candidate overlap share and counterpart share.
If canonical detail is not available, report `NOT_AVAILABLE`.

## 5. Timing and outcome contract

The signal is fixed at T close. Reference entry is the next XSHG session T+1
open, explicitly `REFERENCE_EXECUTION_NOT_ACTUAL_FILL`. The validated DEVELOPMENT
historical outcome convention is reused only after this protocol commit:

- primary horizon: 10D;
- secondary horizon: 5D;
- return is target close relative to T+1 open;
- report mean return, median return, positive rate, MFE and MAE when available;
- report missing reference open, suspension and execution-reference coverage;
- never forward-fill an entry and never replace T+1 open with the next available
  open;
- future corporate actions are outcome-only and ex post.

If authoritative historical limit-state semantics already exist, report T limit
state, T+1 reference-open limit state and group execution coverage. If not, write
`LIMIT_STATE_EXECUTION_CLASSIFICATION_NOT_AVAILABLE`; do not guess with 9.9% or
19.9% rules.

No pre-existing validated transaction-cost convention is assumed. Report gross
spread and `TRANSACTION_COST_MODEL_NOT_PREEXISTING`; a uniform common fee does not
identify the candidate/control difference, while gap/liquidity-dependent slippage
remains unresolved.

## 6. Primary statistical estimand and fixed diagnostics

The primary unit is signal date. For each T, equal-weight all valid 10D outcomes
within each group:

```text
Candidate10_T = mean(valid VCB candidate 10D returns)
Control10_T = mean(valid primary-control 10D returns)
Spread10_T = Candidate10_T - Control10_T
```

The primary estimand is the equal-weight mean of `Spread10_T` across dates where
both groups have valid outcomes. Dates are never weighted by their number of
stocks. Report mean and median spread, 95% moving-block-bootstrap CI, positive
spread-date rate and the number of both-group valid dates. Naive IID uncertainty,
if shown, is `NAIVE_DIAGNOSTIC_ONLY`.

Primary uncertainty is fixed to a non-circular moving-block bootstrap over the
ordered date spread series:

```text
BLOCK_LENGTH = 20 XSHG sessions
REPETITIONS = 5000
SEED = 20260906
```

The continuous diagnostic is computed within each T's valid generic-breakout
outcome cross-section, only when at least five observations exist:

```text
COMPRESSION_STRENGTH = -CONTRACTION_RATIO
rho_T = Spearman(COMPRESSION_STRENGTH, future 10D return)
```

Report equal-weight mean daily rho, valid rho dates, median daily rho and the
positive-rho date rate. It cannot be used to choose a threshold.

Report the simple baseline separately:

- A: VCB candidate = generic breakout + strong contraction;
- B: full generic breakout baseline;
- C: generic breakout without strong contraction (primary control).

B contains A, so A-vs-B is secondary and not an independent control.

## 7. Fixed cooldown and robustness

For the fixed ten-session sensitivity, within each symbol sort generic-breakout
events by date and retain the first event. All later generic-breakout events in
the next 10 XSHG signal sessions are excluded; after cooldown, the next event may
re-enter. Classification is the retained event's fixed signal-day classification;
outcomes never choose retention.

Report raw event counts, cooldown-retained counts, cooldown 10D candidate-control
spread, CI when the same bootstrap is supported, and its direction relative to
the primary estimate.

The only pre-registered robustness views are 5D spread; calendar years 2023,
2024, 2025 and 2026; Main, ChiNext and STAR boards; cooldown; continuous rho;
candidate/control prior 20-session return and volatility distributions; lawful
traded-amount distributions; monthly concentration; symbol concentration;
best/worst signal dates; B overlap; and RS overlap if available. No other
subgroup search is permitted.

## 8. Alternative explanations fixed before outcome access

The report must address or mark unresolved:

1. generic breakout/momentum;
2. low-volatility exposure;
3. pre-compression trend strength;
4. market regime;
5. board composition;
6. liquidity/traded amount;
7. size exposure;
8. sector exposure;
9. new-listing/history-availability effect;
10. gap/news-driven breakout;
11. repeated same-stock breakout signals;
12. common calendar shocks;
13. universe construction;
14. corporate-action artifacts;
15. price-level/tick-size effects.

Historical PIT size and historical sector membership are not available in the
lawful frozen inputs; label them `UNRESOLVED_ALTERNATIVE_EXPLANATION` or
`NOT_AVAILABLE_FOR_THIS_V1_IDENTIFICATION`. Do not use another provider to fill
the gap. Limit-state execution classification and differential slippage are also
unresolved if authoritative inputs are absent.

## 9. Falsification and fixed decisions

The fixed falsification question is:

> What result would show that volatility contraction adds no useful predictive
> information beyond a generic breakout?

If candidate versus same-date generic-breakout control has no stable positive 10D
incremental spread, especially if the fixed CI includes no useful positive signal,
the incremental hypothesis is not retained. In particular, no positive absolute
candidate return can rescue a non-positive candidate-control spread. Failure may
not trigger a volume filter, turnover, RV, ATR/window change, breakout-window
change, compression-percentile change, MA, sector, RS, B or board-only rule; each
would require a new independent protocol.

Allowed final decisions only:

- `VOLATILITY_CONTRACTION_BREAKOUT_INCREMENTAL_SUPPORTED_FOR_FURTHER_VALIDATION`
- `VOLATILITY_CONTRACTION_BREAKOUT_NEEDS_MORE_EVIDENCE`
- `VOLATILITY_CONTRACTION_BREAKOUT_NO_CLEAR_INCREMENTAL_SIGNAL`

Support requires all of: primary 10D mean date spread > 0; 95% moving-block CI
lower bound > 0; mean continuous rho > 0; cooldown 10D mean spread >= 0; positive
calendar-year sign in at least 3 of 4 years; and execution/reference coverage
adequate for the protocol's analysis.

If the primary CI upper bound <= 0, decide
`VOLATILITY_CONTRACTION_BREAKOUT_NO_CLEAR_INCREMENTAL_SIGNAL`. The same decision
applies when primary mean spread <= 0 and mean continuous rho <= 0. All other
cases are `VOLATILITY_CONTRACTION_BREAKOUT_NEEDS_MORE_EVIDENCE`.

Even support means only DEVELOPMENT incremental predictive evidence for this
fixed generic-breakout comparison. It does not mean production-ready, frozen,
portfolio alpha proven, causal, mechanistic proof, or Final OOS validation.

## 10. Required tests, artifacts and stop state

Focused tests must cover the exact TR/TRP formula; no T leakage; exact 10/40
windows and non-overlap; denominator handling; ratio `<1`; ascending rank and
symbol tie-break; `ceil(0.20*N)`; prior-20 high and strict breakout; candidate /
control conjunction, complement, disjointness and union; exact 52-bar boundary;
missing history and no interpolation; no volume qualification; outcome-independent
signals; date-equal-weight aggregation; deterministic bootstrap seed; deterministic
cooldown; and prohibited Final OOS path.

Required artifacts are this protocol, a signal manifest, research summary JSON
and human-readable report. Large signal/outcome detail may remain local-only, but
the manifest must record row count, bytes, file SHA-256, content-stream SHA when
supported, and deterministic sort semantics. The research must run focused pytest,
full pytest, compileall, JSON/schema/hash validation and `git diff --check`.

No automatic follow-up candidate, parameter tuning, promotion, freeze, production
path change, Final OOS read, B prospective outcome read or forbidden-directory
access is allowed. The final stop state is
`VCB_RESEARCH_PR_READY_FOR_USER_MERGE_DECISION` after exact-head CI succeeds; do
not merge the research PR automatically.
