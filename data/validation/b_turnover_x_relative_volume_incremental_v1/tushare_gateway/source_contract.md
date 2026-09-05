# Third-party Tushare-compatible gateway source contract

Status: `DEVELOPMENT` / `RECONSTRUCTED_RETROSPECTIVE` / `DATE_ANCHORED` /
`NO_VINTAGE_PROOF` / `THIRD_PARTY_GATEWAY` / `DIAGNOSTIC_ONLY`

This contract authorizes a bounded research acquisition through a
`THIRD_PARTY_TUSHARE_COMPATIBLE_GATEWAY`. It is not an official Tushare
endpoint, is not strict point-in-time verified, and is not production
validated.

| item | fixed contract |
| --- | --- |
| gateway | `https://tuaremax.top` |
| Python package | `tushare==1.4.24` |
| endpoint | `daily_basic` |
| request fields | `ts_code,trade_date,turnover_rate,float_share` |
| research variable | `turnover_rate` only, canonicalized as `turnover_rate_pct` |
| turnover unit | percent |
| `float_share` unit | 万股 |
| research window | `2023-06-30` through `2026-08-28`, inclusive |
| request grain | one full-market request per frozen XSHG session date |
| universe | frozen daily-K date universe, Main/ChiNext/STAR only |
| symbol mapping | `.SZ`/`.SH` to lowercase `.sz`/`.sh`; no universe expansion |
| duplicate policy | conflicting duplicate symbol/date rows fail closed; exact duplicates are deterministically deduplicated and counted |
| missing policy | null turnover remains null; no imputation; missing symbol/date remains unmatched |
| retry policy | at most 3 attempts per date, then fail closed |
| checkpoint | resumable per-trade-date; completed date is skipped only with a valid raw-file SHA |
| raw persistence | response is persisted before its date is marked complete |
| token handling | environment-only; `credential_present=true` may be recorded; token is never persisted, printed, hashed, or uploaded |
| vintage status | `NO_VINTAGE_PROOF` |

The pilot is fixed to the first frozen research-window session, the first
session of 2024, 2025 and 2026, and the last frozen research-window session.
Pilot readiness requires schema, date-universe coverage and turnover/float-share
semantics checks before full acquisition. `turnover_rate_f` is not requested
or used as an additional research variable.

This source contract does not alter B, the B score, threshold, hard gates,
Top-N, prospective pipeline, frozen data, frozen registry, universe policy,
Final OOS, or production status.
