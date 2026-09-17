# B False Breakout Path Diagnostic V1 Report

DEVELOPMENT / RECONSTRUCTED_RETROSPECTIVE / DIAGNOSTIC_ONLY. Research question; classification unchanged.

## Decision

`B_FALSE_BREAKOUT_PATH_DIAGNOSTIC_PROSPECTIVE_EVIDENCE_REQUIRED`

Research decision: `NEEDS_MORE_EVIDENCE`. Overall price-defense direction survives episode sensitivity,
but Main Board magnitude is negligible, 2023 reverses, the secondary all-STOP comparison reverses,
and reactivation fails the joint/return-conditioned support checks. The joint hypothesis is INCONCLUSIVE.
No B V2 protocol, filter, prospective deployment, or production change is authorized or created.

The frozen diagnostic definitions are the only candidate structure retained. Missing evidence is a
genuine pre-outcome prospective Main Board cohort with enough independent episodes across periods
to evaluate the same comparisons without redefining bins/features. It would inform a later separately
authorized B V2 decision; the existing daily Formal B path continues without this evidence.

## Cohort and labels

Exact frozen qualified identities: 17714; TARGET=4338; FAST_STOP=4623; all STOP=7953.
Unique (symbol, breakout_date) episodes=9766. Other outcomes: `{"AMBIGUOUS": 49, "EXPIRED_UNTRIGGERED": 1213, "INCOMPLETE_STOCK_WINDOW": 43, "INSUFFICIENT_FORWARD_COVERAGE": 119, "TIME_EXIT": 3926, "TIME_EXIT_T1_DEFERRED": 73}`.
FAST_STOP is a subset of STOP; it is not added to STOP when reporting total counts.
Formal track_perf replay supplies trigger/gap fills, entry+1 sellability, same-bar ambiguity and
T+10 time exit / T+11 deferred legal exit. V2 affine adjustment puts OHLC and frozen rule levels
on the same ex-post basis; future actions never enter features. This is a reconstructed DEVELOPMENT
execution diagnostic, not the earlier volume baseline's unconditional T+1-open return or prospective results.
Full T+11 stock coverage is required conservatively before path evaluation; 162 coverage-unavailable
rows are reported rather than assigning partial labels. This can introduce maturity/coverage selection.

## Increment and robustness

Rates are FAST_STOP/(TARGET+FAST_STOP); secondary rates are STOP/(TARGET+STOP).
Values below are percentage-point differences, high minus low defense within fixed volume bins.
Negative primary values indicate fewer FAST_STOP relative to TARGET. No independent-row p-values
or causal claims are made. All cells and per-side counts, including missing/sparse cells, are in summary.json.

| view | rows | episodes | price primary Δpp | price all-STOP Δpp | reactivation joint Δpp | reactivation within return Δpp |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| overall | 17714 | 9766 | -5.873 | 2.549 | 5.780 | 0.861 |
| main | 10779 | 5628 | -0.354 | 8.949 | INSUFFICIENT_DATA | 6.509 |
| earliest_episode | 9766 | 9766 | -8.683 | -1.463 | 5.546 | 3.441 |
| exclude_near_limit_proxy | 16924 | 9271 | -6.198 | 2.137 | 5.076 | 0.147 |
| singleton | 5805 | 5805 | -13.356 | -5.690 | INSUFFICIENT_DATA | 5.118 |
| repeated | 11909 | 3961 | -1.535 | 5.012 | INSUFFICIENT_DATA | -3.503 |
| inverse_episode_weight | 17714 | 9766 | -8.810 | -0.827 | 7.956 | 2.878 |
| year_2023 | 2590 | 1323 | 7.279 | 15.169 | INSUFFICIENT_DATA | INSUFFICIENT_DATA |
| year_2024 | 6197 | 3409 | -9.302 | -2.515 | INSUFFICIENT_DATA | 9.458 |
| year_2025 | 6697 | 3660 | -6.568 | 2.118 | INSUFFICIENT_DATA | -1.351 |
| year_2026 | 2230 | 1399 | -5.429 | -1.190 | INSUFFICIENT_DATA | -0.800 |
| regime_TREND_DOWN | 2200 | 1384 | 4.986 | 11.536 | INSUFFICIENT_DATA | -2.876 |
| regime_TREND_NEUTRAL | 4478 | 3079 | -3.394 | 7.327 | INSUFFICIENT_DATA | 4.015 |
| regime_TREND_UP | 11036 | 6249 | -8.095 | -1.223 | INSUFFICIENT_DATA | -0.463 |

Leave-one-month-out primary range: -7.138 to -3.036 pp; all retained negative.
Repeated-episode row share=67.23%; largest episode=11 rows; top ten episode share=0.59%.
The earliest-episode and inverse-size views retain the primary direction; Main Board and year
instability remain decisive falsification failures. Near-limit exclusion is only the existing
ordinary-board return proxy, not an exact exchange limit state; unknown-prefix rows are unavailable.
Regimes reuse the existing frozen shadow trend definition, reconstructed through T; no historical
prospective capture is fabricated. Regime episode counts can overlap across periods.

## Features, baseline and turnover

All five reused volume features reconcile in N/mean/median to the original frozen volume summary
within 1e-12 tolerance; its VOLUME_PATH_NEEDS_MORE_EVIDENCE decision is unchanged.
The complete 3×3 defense/contraction matrix and its boolean-reactivation split are reported, with
volume-only marginal rates as baseline. No cell was chosen as a rule and no threshold was swept.
Continuous distributions for TARGET, FAST_STOP and all STOP, and every missing reason, are in the artifact.
The empty pre-T retest interval affects 1,368 rows. No-breach reclaim time is missing with NO_BREACH,
not zero. Local-high crossing can only occur at T by definition; its time-to-cross is a trough-to-T
description, not an independently identified reactivation clock. MA5 timing was optional and omitted.
`TURNOVER_EVIDENCE_UNAVAILABLE`: HiThink turnover is amount; current circulating shares cannot
backfill history. Existing daily_basic gateway is DATE_ANCHORED / NO_VINTAGE_PROOF / THIRD_PARTY_GATEWAY
and does not satisfy this task's strict PIT proof. Existing Eastmoney acquisition recorded unavailable
responses. Bounded feasibility probe reused code and provenance only: external provider calls=0.
Price defense/volume/time are observables. Seller exhaustion, capital support or accumulation are
unproved hypotheses. Social-media integers were not adopted as thresholds.

## Provenance and verification

Base SHA: `9c3f011ebc06d33347372b3792ec28f11c505f40`. Branch: `codex/b-false-breakout-path-diagnostic-v1`.
Source implementation commit: `135fa7aa235fbc6a296e56f012207e7d78d9ede1`; code SHA-256: `932db2123948f1ad413d92a203a4c3511b6f3bb610c873052a3d07a8ce430bb2`.
Pre-comparison protocol commit: `ad975a0ff6e24921b0be8792d75c282700be1c50`; SHA-256: `77c3b26a48b5f07415fbd9753c9fed98eb5d98b4fc616f1d4972a7212c49b273`.
Summary file SHA-256: `dc9ec93e76f2e07b788e52d041748255ddec1bcd93967ee71c58d1a1b5284455`.
Event artifact: `data/validation/b_false_breakout_path_diagnostic_v1/events.jsonl.gz`; SHA-256: `d30f17e647ac9848af3b759956e450d72c222afe2787f5d5823f51511a4a3e4d`.
Frozen inputs and feature expressions are in summary.json. Detail is committed for remote recovery.
Focused tests=21 passed (final rerun after additional unknown-proxy regression); full pytest=611 passed, 2 existing fixture skips, 10 warnings; compileall
and git diff --check PASS. Final delivery head is resolved from the remote task branch and recorded
in the delivery response; source commit above is immutable implementation provenance, not a live-head invariant.
Reproduce: `python scripts/b_false_breakout_path_diagnostic.py --source-root <checkout-with-restored-frozen-daily-k>`.
Frozen daily-K restored from verified private Drive file 1lLxp0y_csfOczwEBNYo4ysdyItBgF4Ja;
exact SHA 61189a4850e2eb157453e28e5375e502e20d214508bbe70ea71066ca3e05e426 matched.
Production dispatch=0; runtime-state remote mutation=NO; PR #60 untouched; Formal B/spec/universe
unchanged; Final OOS SEALED / UNREAD; forbidden directory untouched.
