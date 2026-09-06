# NEW_CONTROLLED_RIGHT_SIDE_REVERSAL_V1 — pre-outcome protocol

Status: `PRE_OUTCOME_PROTOCOL_COMMITTED`

Research identity: `NEW_CONTROLLED_RIGHT_SIDE_REVERSAL_V1`

Suggested short name: `CRSR_V1`

Labels: `DEVELOPMENT`, `RECONSTRUCTED_RETROSPECTIVE`, `DATE_ANCHORED`,
`DIAGNOSTIC_ONLY`, `NEW_RESEARCH_HYPOTHESIS`,
`PREDICTIVE_EVIDENCE_UNTESTED_AT_PROTOCOL`, `MECHANISM_EVIDENCE_HYPOTHESIS`,
`FINAL_OOS_UNREAD`, `NO_VINTAGE_PROOF`.

`CRSR_PRE_OUTCOME_PROTOCOL_COMMIT=123ef5299ef94411a0b1cb4ec5745ee2c472979e`

This document freezes the research before any CRSR forward outcome is read. It
is an independent evaluator. It is not a restoration, reconstruction or
replacement of old D, and it must not use old D names, samples, outcomes or
predictive provenance. It does not modify B, B prospective observation, RS
Leadership, VCB, Volume-Path, turnover/RV diagnostics, any production path,
the frozen state or Final OOS.

## 1. Research question and identification

The core question is:

> Among stocks in the same prior downside-extreme state that also have a
> positive T-day bounce, does a deterministic five-session right-side close
> reclaim provide stable future incremental predictive information relative to
> otherwise similar positive-bounce stocks that do not reclaim the prior
> five-session close high?

The primary comparison must control T-day bounce magnitude. This is required to
separate reclaim geometry from the simpler explanation that a candidate merely
rose more on T.

Observable state, not participant intent, consists of prior 20-session return,
same-date downside rank, T-day close-to-close return, prior five-session close
high, strict T-close reclaim and future return. Possible mechanisms such as
weakened forced-selling pressure, ending capitulation, re-emerging demand,
completed unwinding or information reassessment are hypotheses only:
`MECHANISM_EVIDENCE=HYPOTHESIS`. Price paths prove only that a reclaim occurred;
they do not prove panic selling exhaustion, a bottom, capital flow, a dominant
buyer or a causal reversal.

## 2. Authorized scope and hard boundaries

This research may perform, in order:

1. live governance and input/semantics audit;
2. pre-outcome protocol commit;
3. fixed signal implementation and signal-only audit;
4. DEVELOPMENT / RECONSTRUCTED_RETROSPECTIVE outcome analysis;
5. fixed report, independent research PR and exact-head CI.

Final OOS remains `SEALED / UNREAD`.

The following are prohibited: old D reconstruction or old D outcome access;
current-universe, current-sector or current-constituent historical backfill;
provider replacement or new provider acquisition; parameter search;
performance-driven rule selection; promotion; freeze; production strategy
change; and any automatic rescue after a weak result.

The directory `data/validation/continuous_speed_probe/` is forbidden: do not
list, read, stat, hash, modify, delete or upload it.

V1 qualification may not use RSI, MACD, KDJ, moving-average crossover,
Bollinger bands, volume contraction/expansion, turnover, turnover rate,
realized volatility, sector, support, candlestick pattern, B, VCB, RS or an ML
model. Volume and amount can appear only as descriptive diagnostics if already
lawfully present; `VOLUME_CONFIRMATION_DISABLED_IN_CRSR_V1` is fixed.

## 3. Input audit and provenance

The authoritative input is the existing date-anchored continuous development
replay, not today's universe. The no-outcome audit passed before this protocol
commit with the following identity:

- dataset: `core-signal-hithink-continuous-2023-06-30-to-2026-08-28-v1`;
- sessions: 769 completed XSHG sessions, 2023-06-30 through 2026-08-28;
- historical universe: 4,041,140 symbol-dates;
- universe identity SHA-256: `dbc5d220f24f51a0245d047b88733c961fc4f184d02ef6f5ac0fc795576217b0`;
- daily-K SHA-256: `61189a4850e2eb157453e28e5375e502e20d214508bbe70ea71066ca3e05e426`;
- adjustment-factor SHA-256: `a1b7d63c5826ccd3610dc9bdd949d82eeb0ba84ffad451bfb8bb30ca74962716`;
- core replay identity SHA-256: `0d23cf54843920f5fdcc05847e4b78c5d605b05c8793f878b6021c85b3ab0c2f`;
- raw stock rows/symbols: 10,252,571 / 5,551;
- adjustment rows/symbols: 57,027 / 5,420; future rows after dataset end: 42;
- calendar benchmark rows: 886; timezone: `Asia/Shanghai`.

Historical eligibility is a raw daily-K row present at T with at least 120 valid
bars through T. New listings and unavailable history are excluded by the
historical replay; no current constituent is backfilled, no interpolation is
used and no session is removed. Main is `00`/`60`, ChiNext is `30`, STAR is
`68`; other prefixes remain retained and reported descriptively.

Signal prices use the validated
`HISTORICAL_T_ANCHOR_PRICE_RAW_VOLUME` basis. For each signal date T, corporate
actions with `date < ex_date <= T` are applied in ascending ex-date order to
OHLC using:

```text
(price - dividend_per_share + allotment_price*allotment_ratio)
/ (1 + per_share_bonus + allotment_ratio)
```

Volume and amount remain raw unadjusted. Future events are excluded from signal
features. The source has no per-bar historical vintage timestamp, so
`NO_VINTAGE_PROOF` is retained. If the frozen universe or comparable signal
price path fails identity checks, stop with respectively
`CRSR_HISTORICAL_PIT_UNIVERSE_NOT_AVAILABLE` or
`CRSR_SIGNAL_PRICE_BASIS_NOT_AVAILABLE`; do not substitute a provider.

All lookbacks use completed XSHG signal sessions, never calendar-day windows.

## 4. Fixed design choices

These are pre-registered choices, not optimal parameters:

```text
DOWNSIDE_LOOKBACK = 20 sessions
DOWNSIDE_QUANTILE = bottom 20 percent
RECLAIM_LOOKBACK = prior 5 sessions
T_DAY_BOUNCE = close_T / close_T-1 - 1 > 0
BOUNCE_MAGNITUDE_STRATA = 5 same-date quintile bins
PRIMARY_HORIZON = 10D
SECONDARY_HORIZON = 5D
```

No alternative decline window, bottom percentile, reclaim window, or horizon
may be tested under this protocol. Any such change requires a new independent
protocol.

## 5. Exact signal definitions

### Prior downside state (T-1 only)

For each eligible symbol and T with at least 22 chronological valid bars
including T, define:

```text
R20_PRE_T = close_T-1 / close_T-21 - 1
```

The denominator must be a valid positive signal price. At each T, among all
historical eligible symbols with valid `R20_PRE_T`, sort ascending by return and
break exact ties by ascending canonical symbol. For `N` valid rows:

```text
BOTTOM_K = ceil(0.20 * N)
```

`R20_PRE_RANK=1` is the weakest row. The observable classification is:

```text
DOWNSIDE_EXTREME_T = (R20_PRE_RANK <= BOTTOM_K) AND (R20_PRE_T < 0)
```

The absolute `< 0` condition is required; a relative laggard in an all-rising
market is not thereby downside-extreme. T-day data cannot influence the
downside calculation or rank.

### T-day bounce and strict reclaim

```text
T_DAY_RETURN_T = close_T / close_T-1 - 1
SIMPLE_POSITIVE_BOUNCE_T = close_T > close_T-1

PRIOR_CLOSE_HIGH5_T = max(close_T-5, close_T-4, close_T-3, close_T-2, close_T-1)
RECLAIM5_T = close_T > PRIOR_CLOSE_HIGH5_T
RECLAIM_MARGIN_T = close_T / PRIOR_CLOSE_HIGH5_T - 1
```

The prior high excludes T and reclaim is strict `>`, not `>=`. Reclaim
automatically implies a positive T-day bounce.

### Candidate, baseline and primary control

```text
CRSR_CANDIDATE_T = DOWNSIDE_EXTREME_T AND RECLAIM5_T

DOWNSIDE_BOUNCE_BASELINE_T =
    DOWNSIDE_EXTREME_T AND SIMPLE_POSITIVE_BOUNCE_T

CRSR_PRIMARY_CONTROL_T =
    DOWNSIDE_EXTREME_T AND SIMPLE_POSITIVE_BOUNCE_T AND NOT RECLAIM5_T
```

Candidate and primary control share prior downside state and positive T-day
bounce; they differ only by strict reclaim. Candidate is a subset of the full
downside-bounce baseline, and candidate plus primary control equals that
baseline. The full baseline contains the candidate and is secondary, not an
independent control.

For each T, only inside the full downside-bounce baseline, sort by
`T_DAY_RETURN_T` ascending and break exact ties by symbol. If the baseline has
size M, assign:

```text
BOUNCE_BIN = min(5, floor((rank - 1) * 5 / M) + 1)
```

Bins are deterministic and outcome-blind. The candidate's strict reclaim is not
allowed to define or alter the bins.

### Generic reclaim context

To test whether the signal is merely generic short-term momentum, define a
second context with the same return stratification:

```text
NON_DOWNSIDE_T = NOT DOWNSIDE_EXTREME_T
GENERIC_RECLAIM_T = NON_DOWNSIDE_T AND RECLAIM5_T
GENERIC_BOUNCE_CONTROL_T =
    NON_DOWNSIDE_T AND SIMPLE_POSITIVE_BOUNCE_T AND NOT RECLAIM5_T
```

Compute the non-downside reclaim/control stratified spread with the same
five-bin construction. The context interaction is:

```text
CONTEXT_INTERACTION10_T =
    CRSR downside-context stratified spread
    - non-downside generic-reclaim stratified spread
```

Use it only on dates where both context spreads are computable. This is a
competing-explanation diagnostic, not causal identification.

### Invalidation reference

Before outcomes, record but do not qualify or truncate on:

```text
RECENT_LOW5_T = min(low_T-4, low_T-3, low_T-2, low_T-1, low_T)
INVALIDATION_REFERENCE_T = RECENT_LOW5_T
```

It is a research-only future execution/risk reference. No stop, P&L truncation,
promotion or post-outcome stop selection is allowed.

### Minimum history

The exact signal boundary is 22 chronological valid bars including T: T and
T-1 through T-21. `T-5` through `T-1` must be available for the prior high. A
row failing this boundary is explicitly `INSUFFICIENT_SIGNAL_HISTORY`; do not
interpolate, use a shorter window or use a future bar.

## 6. Signal output and readiness gate

The independent signal manifest is sorted `date ascending, symbol ascending`.
Each symbol-date records at least:

- date, symbol, board, eligibility and exclusion reason;
- R20_PRE, rank, bottom-K and downside-extreme flag;
- prior close high 5, T-day return and simple-bounce flag;
- reclaim flag and reclaim margin;
- candidate, full-baseline and primary-control flags;
- non-downside generic reclaim/control flags;
- bounce bin and invalidation reference;
- signal T-close and earliest T+1 XSHG session.

Before any forward outcome access, report sessions; total eligible rows;
valid/invalid history counts; downside-extreme, full baseline, candidate and
primary-control counts; candidate/control/shared-bin active dates; mean/median
group counts; unique symbols; year and board counts; symbol/month
concentration; reclaim-margin and T-day-return distributions; candidate/control
T-day-return distributions before stratification; and any lawful B/RS/VCB
membership-only overlap.

Readiness must satisfy all fixed gates:

```text
CANDIDATE_EVENTS >= 500
PRIMARY_CONTROL_EVENTS >= 1000
BOTH_GROUP_ACTIVE_DATES >= 200
SHARED_BOUNCE_BIN_DATES >= 200
```

Failure is `CRSR_SIGNAL_CONSTRUCTION_NOT_RESEARCH_READY`; do not change rules to
expand the sample.

## 7. Outcome contract and primary estimands

Outcome access is permitted only after this protocol commit and a passing
signal-only audit. Signal price is T close. Reference entry is T+1 XSHG open,
with `REFERENCE_EXECUTION_NOT_ACTUAL_FILL`. Reuse the validated DEVELOPMENT
corporate-action-adjusted outcome convention: future actions are used only
ex-post, with no forward-filled entry and no next-available-open substitution.
Report 5D and 10D return, mean, median, positive rate, MFE, MAE, missing T+1
open, suspension/execution uncertainty and outcome maturity. The reported
increment is gross unless a pre-existing validated transaction-cost convention
exists; otherwise record `TRANSACTION_COST_MODEL_NOT_PREEXISTING` and report
break-even differential execution cost only if mathematically meaningful.

For each T and bounce bin b that has both candidate and primary-control rows and
valid 10D outcomes:

```text
CandidateReturn10_T,b = equal-weight candidate mean return
ControlReturn10_T,b = equal-weight control mean return
BinSpread10_T,b = CandidateReturn10_T,b - ControlReturn10_T,b
```

The date-level primary spread is the equal-weight mean of all valid shared-bin
`BinSpread10_T,b`, not a stock-count-weighted mean. The primary estimand is the
equal-weight mean of date-level stratified spreads across valid dates. Do not
weight dates by stock counts or bins by bin size.

Also report raw date-level candidate, full baseline and primary-control means
and raw candidate-minus-control spread as
`RAW_UNSTRATIFIED_SECONDARY`; it cannot replace the stratified primary result.

The same date/bin construction is used for 5D secondary spread and for the
non-downside generic-reclaim context.

## 8. Fixed uncertainty and diagnostics

Primary uncertainty is a date-level 20-session moving-block bootstrap over
`StratifiedSpread10_T`:

```text
BLOCK_LENGTH = 20 XSHG sessions
REPETITIONS = 5000
SEED = 20260906
```

Report mean, median, 95% block-bootstrap CI, positive-spread date rate and
valid-date count. IID bootstrap, if shown, is `NAIVE_DIAGNOSTIC_ONLY`.

The continuous check is daily Spearman correlation inside the full downside
bounce baseline between `RECLAIM_MARGIN_T` and future 10D return, requiring at
least 5 valid observations per date. Report mean daily rho, median, positive-rho
rate and valid rho dates. It does not fully control T-day return and is
secondary evidence.

The fixed diagnostics are raw and stratified 10D, stratified 5D, continuous rho,
context interaction, ten-session cooldown, years 2023/2024/2025/2026, boards
Main/ChiNext/STAR, prior return and realized-volatility descriptive
distributions, traded amount when lawful, symbol/month concentration,
best/worst dates, post-stratification T-day-return balance, and B/RS/VCB
membership overlap when directly available. No new subgroup search is allowed.

Execution diagnostics report T limit state, T+1 open state and reference-entry
coverage only when authoritative historical limit-state semantics already exist.
Otherwise report `LIMIT_STATE_EXECUTION_CLASSIFICATION_NOT_AVAILABLE`. Do not
approximate historical limits with 9.9%, 19.9% or 29.9% thresholds.

## 9. Cooldown and alternatives

The fixed cooldown sensitivity is `TEN_SESSION_COOLDOWN_DEDUP`. For each symbol,
sort all downside-bounce events by date, retain the first, and exclude all
subsequent downside-bounce events within the next 10 XSHG signal sessions.
After cooldown, the next event may re-enter. Preserve the original day's
candidate/control classification; never choose events using outcomes. Recompute
the primary stratified 10D spread and CI when the retained sample permits.

Alternatives registered before outcomes are simple mean reversion after a large
loss; generic T-day rebound strength; generic five-session momentum/reclaim;
market regime; board composition; volatility exposure; liquidity/amount; size;
sector; new-listing/history availability; gap/news reversal; limit state or
suspension; repeated same-stock episodes; common calendar shocks; universe
construction; corporate-action artifacts; and price-level/tick-size effects.

Size and historical sector are not lawfully available for this identification
unless already present in the authoritative PIT inputs. If absent, report
`UNRESOLVED_ALTERNATIVE_EXPLANATION` or
`NOT_AVAILABLE_FOR_THIS_V1_IDENTIFICATION`; do not switch providers.

## 10. Falsification and fixed decision rule

The falsification question is:

> What result would show that right-side reclaim adds no useful information
> beyond a simple positive bounce after a downside-extreme state?

If, after T-day bounce-magnitude control, candidate versus primary control has
no stable positive 10D incremental spread, the hypothesis that reclaim provides
incremental predictive information is not retained. A weak result must not
trigger added indicators, volume/turnover filters, sector filters, new windows,
new horizons, board selection or another candidate; each would require a new
independent protocol.

Allowed final decisions are exactly:

```text
CONTROLLED_RIGHT_SIDE_REVERSAL_INCREMENTAL_SUPPORTED_FOR_FURTHER_VALIDATION
CONTROLLED_RIGHT_SIDE_REVERSAL_NEEDS_MORE_EVIDENCE
CONTROLLED_RIGHT_SIDE_REVERSAL_NO_CLEAR_INCREMENTAL_SIGNAL
```

Support requires all of: positive primary 10D mean; primary CI lower bound > 0;
positive mean continuous rho; non-negative cooldown primary mean; non-negative
mean context interaction; positive primary spread in at least 3 of 4 calendar
years; and the outcome/reference coverage gate. If CI upper bound <= 0, or both
primary mean and continuous rho are <= 0, decision is
`CONTROLLED_RIGHT_SIDE_REVERSAL_NO_CLEAR_INCREMENTAL_SIGNAL`. Otherwise the
decision is `CONTROLLED_RIGHT_SIDE_REVERSAL_NEEDS_MORE_EVIDENCE`.

Even a supported result is only DEVELOPMENT incremental predictive evidence
under the fixed design. It is not proof of seller exhaustion, panic clearing,
bottom formation, causal reversal, executable alpha, production readiness,
portfolio alpha, a frozen candidate or Final OOS validation.

## 11. Coverage gate, tests and artifacts

Before performance analysis, candidate and primary-control usable 10D outcome
coverage and shared-bin valid-date coverage must each be at least 95%, with
year and board coverage reported. Failure is
`CRSR_OUTCOME_COVERAGE_NOT_RESEARCH_READY`; do not delete rows to improve it.

Focused tests must cover exact R20_PRE and prior-high windows, T-1-only state,
ascending rank and symbol tie-break, ceil bottom-K, absolute negative filter,
strict positive bounce, strict reclaim, exact candidate/control complement,
candidate subset, deterministic bounce bins, no outcome leakage, exact 22-bar
boundary, no interpolation, disabled qualification features, equal-weight date
and bin aggregation, bootstrap seed, exact context interaction, cooldown,
invalidation non-qualification and Final OOS prohibition. Run focused pytest,
full pytest, compileall, JSON/schema/hash validation and `git diff --check`.

Required artifacts are the protocol, a signal manifest, summary JSON and
human-readable report. Large event detail remains local-only. Every manifest
records row count, byte size, file SHA-256, content-stream SHA when supported,
and deterministic sort semantics.

## 12. Governance stop state

The research branch is independent of production. The PR must state that this
is `NEW_RESEARCH_HYPOTHESIS`, not old D reconstruction; include protocol SHA,
input identity, fixed signal and outcome definitions, diagnostics, unresolved
alternatives, decision and all preserved strategy boundaries. Do not merge
automatically. The final terminal state is:

`CRSR_RESEARCH_PR_READY_FOR_USER_MERGE_DECISION`

At completion reconfirm: B and B prospective unchanged; RS, VCB,
Volume-Path and turnover/RV unchanged; C unread; old D not reconstructed; Final
OOS `SEALED / UNREAD`; frozen state and production semantics unchanged; forbidden
directory untouched; no tuning, promotion, freeze or automatic next candidate.
