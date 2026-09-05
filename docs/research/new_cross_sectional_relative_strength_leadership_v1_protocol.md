# NEW_CROSS_SECTIONAL_RELATIVE_STRENGTH_LEADERSHIP_V1 — pre-outcome protocol

Status: `PRE_OUTCOME_PROTOCOL_COMMITTED`

Research identity: `NEW_CROSS_SECTIONAL_RELATIVE_STRENGTH_LEADERSHIP_V1`

Labels: `DEVELOPMENT`, `RECONSTRUCTED_RETROSPECTIVE`, `DATE_ANCHORED`,
`DIAGNOSTIC_ONLY`, `NEW_RESEARCH_HYPOTHESIS`,
`PREDICTIVE_EVIDENCE_UNTESTED_AT_PROTOCOL`, `MECHANISM_EVIDENCE_HYPOTHESIS`,
`FINAL_OOS_UNREAD`.

`RS_LEADERSHIP_PRE_OUTCOME_PROTOCOL_COMMIT=TO_BE_RECORDED_AFTER_COMMIT`

This document fixes the research before any forward outcome for this candidate is
read. It is an independent research evaluator. It does not modify
`B_BREAKOUT_RETEST_LEGACY_V1_1`, its prospective observation path, any production
watchlist path, frozen prerequisites, or Final OOS.

## 1. Research question and epistemic boundary

Research question:

> Among stocks that are already medium-term 60-session cross-sectional momentum
> leaders on the same T date, does also requiring short-term 20-session leadership
> provide stable incremental information about the future 10-session outcome,
> relative to the simple 60-session momentum baseline?

The signal is `CROSS_SECTIONAL_RELATIVE_RANK`: each stock is ranked against the
eligible stock cross-section on the same T date by its trailing return. It is not
`stock_return - same_market_benchmark_return` used as a cross-sectional rank
feature. A common benchmark subtraction is a constant for every stock on T and is
therefore rank-invariant:
`COMMON_BENCHMARK_SUBTRACTION_IS_RANK_INVARIANT`.

Observable features are R20, R60, same-date cross-sectional ranks, top-quintile
membership, and multi-horizon leadership persistence. Persistent capital
allocation, information diffusion, momentum persistence, and positioning/flow
continuation are mechanism hypotheses only:
`MECHANISM_EVIDENCE=HYPOTHESIS`. No result may be written as proof of “资金持续
流入”, “主力正在加仓”, or causal “强者恒强”. At this commit,
`PREDICTIVE_EVIDENCE=UNTESTED`.

## 2. Input audit completed before outcome access

The audit uses only existing frozen/development replay inputs and existing input
semantics. It does not fetch a provider, current constituents, current sector
data, or any new data source.

### Historical point-in-time universe

- Authoritative identity: the existing continuous replay universe, whose manifest
  semantics are `historical daily-K rows present at T with >=120 bars through T`.
- Sessions: 769 continuous XSHG sessions, 2023-06-30 through 2026-08-28.
- Candidate-evaluation identity: 4,041,140 session×symbol rows.
- Per-session eligible symbol count: minimum 4,908, maximum 5,466, mean
  5,255.0585, median 5,276.
- Raw T-day rows before the >=120-bar eligibility gate: minimum 5,087 and maximum
  5,547 per session.
- Universe identity hash, over sorted `signal_date|symbol` rows:
  `dbc5d220f24f51a0245d047b88733c961fc4f184d02ef6f5ac0fc795576217b0`.
- Source is date-anchored replay input, not today's universe backfilled into the
  past. A symbol is absent before it has a T-day bar; no listing-date table,
  current constituent list, or current-data backfill is used.
- The canonical replay universe contains Main, ChiNext, STAR, and a separately
  reported `OUT_OF_SCOPE_PREFIX` bucket (the observed extra prefix is Beijing
  `92`). The research keeps the exact existing replay universe so that universe
  construction is not silently changed; Main=`00`/`60`, ChiNext=`30`, STAR=`68`.
- Missing or insufficient history is excluded at the symbol-date level and does
  not delete an entire session. There is no interpolation and no future-bar
  search.

### Price and corporate-action basis

- Raw daily-K source: `HiThink Financial-API`, dataset range 2016-08-29 through
  2026-08-28, 10,252,571 rows, 5,551 raw symbols, duplicate key count 0, null
  numeric count 0, negative volume count 0.
- Frozen `daily_k.parquet` SHA-256:
  `61189a4850e2eb157453e28e5375e502e20d214508bb70ea71066ca3e05e426`.
- Frozen `adjustment_factors.parquet` SHA-256:
  `a1b7d63c5826ccd3610dc9bdd949d82eeb0ba84ffad451bfb8bb30ca74962716`.
- Signal prices use the validated replay `HISTORICAL_T_ANCHOR_PRICE_RAW_VOLUME`
  convention: for each T, corporate-action transforms with ex-date `<= T` are
  applied to pre-ex-date OHLC prices; volume remains raw unadjusted volume. No
  event after T enters the signal. The source manifest records 42 adjustment
  rows after the dataset end; they are not signal inputs.
- This is the existing validated retrospective convention. The source has no
  per-bar historical vintage timestamp, so vintage proof is limited as recorded
  in the source manifest; this is not silently upgraded to a stronger known-at
  claim.
- The T-close signal is a reference signal, not a same-bar fill. Reference entry
  is the next XSHG session T+1 open; `REFERENCE_EXECUTION_NOT_ACTUAL_FILL`.

### Benchmark and identity inputs

The existing 000001.SH benchmark files and 886 benchmark rows are retained for
the XSHG session calendar and descriptive market-regime diagnostics. Benchmark
return is not subtracted from R20/R60 for ranking because that would not change
the cross-sectional order. The four frozen benchmark file hashes are recorded in
the canonical core replay manifest and are inherited without refetch.

### Provenance decisions

`NO_OUTCOME_INPUT_AUDIT=PASS`.

No current-universe backfill, current-constituent backfill, provider re-fetch,
future corporate-action information, current sector backfill, missing-value
interpolation, or new provider acquisition is permitted. If the raw universe,
calendar, price basis, or symbol identity later conflicts with these facts, stop
with `RS_LEADERSHIP_INPUT_PROVENANCE_CONFLICT`. If the date-anchored universe or
validated price basis cannot be legally reused, stop with
`RS_LEADERSHIP_HISTORICAL_PIT_UNIVERSE_NOT_AVAILABLE` or
`RS_LEADERSHIP_SIGNAL_PRICE_BASIS_NOT_AVAILABLE`.

## 3. Fixed signal specification

All lookbacks count completed XSHG signal sessions and include T as the endpoint.

```text
SHORT_LOOKBACK = 20
MEDIUM_LOOKBACK = 60
```

For every eligible symbol and T:

```text
R20_T = signal_price_T / signal_price_{T-20} - 1
R60_T = signal_price_T / signal_price_{T-60} - 1
```

R20 requires at least 21 valid signal-price bars. R60 requires at least 61 valid
signal-price bars. A symbol failing either requirement is explicitly classified
`INSUFFICIENT_SIGNAL_HISTORY`; it is not interpolated, forward-filled, or moved
to a different date. The inherited replay universe normally has >=120 bars, but
the explicit gate remains part of this evaluator.

For each T, only symbols with valid R20/R60 participate. Let N be the number of
valid participants and define `TOP_K = ceil(0.20 * N)`. Sort descending by return;
an exact return tie is broken by ascending canonical symbol. No alternate 10%,
15%, 25%, or 30% threshold is tested.

```text
Q20_LEADER_T = top TOP_K symbols by R20
Q60_LEADER_T = top TOP_K symbols by R60
CANDIDATE_T = Q20_LEADER_T intersection Q60_LEADER_T
SIMPLE_60D_MOMENTUM_BASELINE_T = Q60_LEADER_T
PRIMARY_CONTROL_T = Q60_LEADER_T minus CANDIDATE_T
```

The candidate is therefore `MULTI_HORIZON_CROSS_SECTIONAL_LEADERSHIP_PERSISTENCE`.
The primary comparison is candidate versus primary control, not candidate versus
the full baseline that contains the candidate itself. The full Q60 baseline is a
secondary comparison only.

## 4. Timing, outcomes, and statistical unit

The signal is evaluated at T close. Reference entry is T+1 XSHG open. Outcomes
are read only after this protocol commit and use the existing DEVELOPMENT /
RECONSTRUCTED_RETROSPECTIVE V2 outcome convention:

- primary horizon: 10D;
- secondary horizon: 5D;
- return is target close relative to T+1 open;
- MFE and MAE use the same corporate-action-adjusted path basis;
- future corporate actions are outcome-only, ex post;
- missing T+1 open is unavailable; no forward-fill and no next-available-open
  substitution;
- suspension and execution uncertainty remain explicit;
- this is reference execution coverage, not actual fill coverage.

The primary statistical unit is the signal date, not the symbol-date event. For
each T, calculate equal-weight means over valid symbol outcomes:

```text
CandidateReturn10_T = mean(valid candidate 10D returns)
ControlReturn10_T   = mean(valid primary-control 10D returns)
PrimarySpread10_T   = CandidateReturn10_T - ControlReturn10_T
```

The primary estimand is the equal-weight mean of `PrimarySpread10_T` across
signal dates. Dates are never weighted by their number of stocks.

Uncertainty is fixed as a 20-XSHG-session moving-block bootstrap with 5,000
repetitions and seed 20260906. The primary report contains mean spread, median
spread, 95% moving-block-bootstrap CI, and positive-spread date rate. Any IID
standard error is `NAIVE_DIAGNOSTIC_ONLY`.

The secondary continuous diagnostic is, within the Q60 universe on each T,
Spearman correlation between R20 cross-sectional rank and future 10D return,
followed by equal-weight averaging across dates. It is not used to select a
threshold.

## 5. Alternative explanations fixed before outcome access

The study must report or explicitly mark:

1. generic 60D momentum;
2. short-term 20D momentum;
3. market regime;
4. board composition;
5. volatility exposure;
6. liquidity/traded-amount exposure;
7. size exposure;
8. sector momentum;
9. new-listing/history-availability effect;
10. repeated daily membership/persistence;
11. common-calendar shock;
12. cross-sectional universe construction effect.

Historical PIT size and historical PIT sector membership are not available in the
frozen inputs. They remain `UNRESOLVED_ALTERNATIVE_EXPLANATION` and
`NOT_AVAILABLE_FOR_THIS_V1_IDENTIFICATION`; no provider is switched and no
current sector is backfilled. Therefore even a positive result is only
`incremental relative to the fixed simple baseline`, not fully factor-identified
causal alpha.

The report will include fixed candidate/control 20D realized-volatility and
median traded-amount distributions when legally derivable from the same frozen
inputs, plus year, board, membership persistence, concentration, best/worst
dates, monthly concentration, and B signal-overlap diagnostics.

## 6. Signal-only gate and B overlap

Before candidate outcomes are read, the evaluator must emit deterministic
membership rows sorted by `date, symbol`, with R20, R60, rank20, rank60, and
candidate/control classification. It must report per T eligible N, valid R20 N,
valid R60 N, Q20 N, Q60 N, candidate N, primary-control N, and insufficient-history
N.

Candidate and primary control must both be non-empty on at least 98% of eligible
sessions. Otherwise stop with `RS_LEADERSHIP_SIGNAL_CONSTRUCTION_NOT_RESEARCH_READY`;
thresholds must not be changed to repair sample size.

B overlap is a no-outcome diagnostic only. It may read B signal membership and
must not read B prospective outcomes. It reports same-date overlap, same
symbol-date overlap, candidate share overlapping B, and B share overlapping
candidate. The overlap cannot alter this rule.

## 7. Pre-registered falsification and fixed decision

The added complexity is the 20D top-quintile persistence condition on top of the
60D top-quintile baseline. The falsification question is:

> What result would show that multi-horizon cross-sectional leadership adds no
> useful information beyond simple 60D momentum?

The answer is fixed: no positive and stable candidate-versus-primary-control
10D date spread, no positive continuous R20-rank Spearman within Q60, or a result
that is only a single year, month, regime, board, or concentration artifact shows
that the added condition is not useful. The research may not respond by changing
lookbacks, quintile, horizon, board slice, or adding volume, turnover, sector,
size, MA, or B filters. Such changes require a new protocol.

Allowed final decisions only:

- `RS_LEADERSHIP_INCREMENTAL_SUPPORTED_FOR_FURTHER_VALIDATION`
- `RS_LEADERSHIP_NEEDS_MORE_EVIDENCE`
- `RS_LEADERSHIP_NO_CLEAR_INCREMENTAL_SIGNAL`

Support requires all of: primary 10D mean date spread > 0; 95% block-bootstrap
lower bound > 0; average continuous rho > 0; valid reference execution coverage;
and positive calendar-year sign in at least 3 of 4 years (2023–2026).

If the 95% CI upper bound is <= 0, decide
`RS_LEADERSHIP_NO_CLEAR_INCREMENTAL_SIGNAL`. If point estimate <= 0 and continuous
rho <= 0 while the CI crosses zero, use the same decision. All other cases are
`RS_LEADERSHIP_NEEDS_MORE_EVIDENCE`.

`SUPPORTED_FOR_FURTHER_VALIDATION` does not mean adopted, frozen, production,
causal mechanism proven, or fully factor-neutral alpha. It means only that this
fixed candidate showed sufficiently stable DEVELOPMENT incremental evidence to
merit a later independent validation decision.

## 8. Costs, artifact, and governance boundary

No pre-existing validated transaction-cost convention is assumed for this V1.
Record `TRANSACTION_COST_MODEL_NOT_PREEXISTING`, report gross returns, execution
reference coverage, and mathematically meaningful break-even round-trip cost.
Equal proportional costs would largely cancel in the A-vs-C spread, while
liquidity/slippage differences remain unresolved.

Required artifacts are a signal manifest, research summary JSON, human-readable
report, and focused tests. Large event detail may remain local-only but its row
count, byte size, file SHA, and content-stream SHA must be recorded if produced.
No production/prospective path is changed, no B rule is changed, and no automatic
follow-up candidate, tuning, promotion, freeze, C research, Phase 2F, or Final
OOS read is allowed.

Final state after PR and exact-head CI:
`RS_LEADERSHIP_RESEARCH_PR_READY_FOR_USER_MERGE_DECISION`.
