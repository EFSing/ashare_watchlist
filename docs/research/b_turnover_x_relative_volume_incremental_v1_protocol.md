# B Turnover × Relative Volume Incremental Diagnostic V1

Status: `DEVELOPMENT` / `RECONSTRUCTED_RETROSPECTIVE` / `DATE_ANCHORED` /
`NO_VINTAGE_PROOF` / `THIRD_PARTY_GATEWAY` / `DIAGNOSTIC_ONLY`

## Research question

Within the unchanged corrected `B_BREAKOUT_RETEST_LEGACY_V1_1` structural and
qualified cohorts, does T-day `turnover_rate_pct` provide stable incremental
information after conditioning on the frozen T-day relative-volume feature?
The result is a research diagnostic only. It cannot change B, its score,
threshold, hard gate, Top-N, universe or prospective pipeline.

## Inputs and source boundary

- turnover source: `THIRD_PARTY_TUSHARE_COMPATIBLE_GATEWAY` at
  `https://tuaremax.top`, package `tushare==1.4.24`, endpoint `daily_basic`;
- requested fields: `ts_code,trade_date,turnover_rate,float_share`; only
  `turnover_rate` is a research variable; `turnover_rate_f` is not used;
- canonical symbol mapping: `.SZ`/`.SH` to `.sz`/`.sh`; only Main, ChiNext and
  STAR are in scope; the frozen universe is not expanded;
- source semantics: `turnover_rate` is percent and `float_share` is 万股;
- input audit must retain exact frozen reconciliation of 17,714 qualified and
  573,586 structural identities. Non-Main/ChiNext/STAR cohort rows are
  excluded by the fixed universe boundary, not imputed or reclassified;
- no vintage proof is available. Final OOS remains sealed and unread.

## Feature definitions

The primary pair is:

1. `turnover_rate_pct`: canonical provider `turnover_rate` percent at T;
2. `RV20_T = volume_T / mean(volume[T-20:T-1])`, using raw frozen `daily_k`
   volume, excluding T from the baseline, requiring 20 valid preceding bars
   and a positive denominator. No interpolation or adjusted volume is allowed.

Both features are known at T close. Missing or invalid values remain
unavailable; no imputation is permitted.

## Pre-registered summaries

All summaries use the qualified in-scope cohort unless explicitly labelled
structural. Feature quintiles are assigned independently by stable ascending
rank: `(feature value, symbol, signal_date, original row index)`, with the
first fifth labelled Q1 and the last fifth Q5. There is no threshold search,
best-cell search, parameter sweep, model fitting or provider switching.

The diagnostic must report:

- turnover quintiles `TQ1`–`TQ5` and relative-volume quintiles `RVQ1`–`RVQ5`;
- the complete 5×5 `TQ × RVQ` matrix;
- turnover conditional on RV: within each RV quintile, fixed `TQ5 - TQ1`;
- RV conditional on turnover: within each turnover quintile, fixed `RVQ5 - RVQ1`;
- the corner interaction contrast
  `(TQ5,RVQ5) - (TQ5,RVQ1) - (TQ1,RVQ5) + (TQ1,RVQ1)`;
- primary 5D return, secondary 10D return, 5D/10D MFE and 5D/10D MAE;
- year strata 2023/2024/2025/2026 and board strata Main/ChiNext/STAR;
- structural-cohort coherence using the same fixed features and 5D/10D return;
- episode-deduplicated sensitivity: retain the earliest qualified row per
  `(symbol, breakout_date)` after stable sorting by signal date and row index;
- fixed top-1% sensitivity for each feature and the joint top-1% intersection,
  where top 1% is the highest stable-ranked 1% of eligible rows. These are
  descriptive checks, not selected thresholds.

For every applicable group, report N, mean, median, positive rate, mean MFE,
mean MAE, and rank correlation where defined. Report unavailable counts and
do not silently drop them from cohort reconciliation.

## Outcomes and allowed decisions

The outcome fields are read only after this protocol is committed:

- primary: 5D return;
- secondary: 10D return, 5D MFE, 5D MAE, 10D MFE, 10D MAE.

The only allowed final decisions are:

- `TURNOVER_X_RELATIVE_VOLUME_INCREMENTAL_SUPPORTED_FOR_FURTHER_VALIDATION`;
- `TURNOVER_X_RELATIVE_VOLUME_NEEDS_MORE_EVIDENCE`;
- `TURNOVER_X_RELATIVE_VOLUME_NO_CLEAR_INCREMENTAL_SIGNAL`.

Support means a fixed turnover relationship remains directionally coherent in
the conditioned summaries and the pre-registered year, board, structural,
episode and top-1% checks. Partial or non-monotonic evidence maps to
`NEEDS_MORE_EVIDENCE`; absent aligned evidence maps to `NO_CLEAR_INCREMENTAL_SIGNAL`.
No decision authorizes production use, parameter selection, freeze, promotion,
Final OOS access, C or Phase 2F.

## Provenance and stop conditions

The source labels remain `DEVELOPMENT`, `RECONSTRUCTED_RETROSPECTIVE`,
`DATE_ANCHORED`, `NO_VINTAGE_PROOF`, `THIRD_PARTY_GATEWAY` and
`DIAGNOSTIC_ONLY`. The token is environment-only and is never persisted,
printed, hashed or uploaded. A source identity change, invalid input audit,
missing outcome construction, or any violation of the fixed feature/strata
contract fails closed. The protocol commit SHA must be recorded as
`PRE_OUTCOME_PROTOCOL_COMMIT` before any outcome value is read for analysis.
