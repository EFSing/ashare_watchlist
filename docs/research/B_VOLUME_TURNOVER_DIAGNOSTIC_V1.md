# B_VOLUME_TURNOVER_DIAGNOSTIC_V1

Status: `BLOCKED` / `NEEDS_MORE_EVIDENCE`

Terminal marker:

`B_VOLUME_TURNOVER_DIAGNOSTIC_BLOCKED_BY_TURNOVER_DATA_GAP`

This is an independent retrospective diagnostic. It did not modify formal B,
production, PR #60, `runtime-state`, historical artifacts, or the prospective
volume-focus layer.

## 1. Question, materiality, and stop condition

Question: within the existing formal-B resolved sample, does turnover add
information beyond `vol_ratio >= 1.20`, especially inside the volume-confirmed
cohort, for TARGET versus STOP / FAST_STOP?

Materiality: a valid answer could inform a future observational layer, but it
must not change B qualification, Score, ranking, trigger, stop, target, RR,
T+1, same-bar semantics, or the PR #60 experiment.

The pre-registered stop condition is met when signal-date turnover and enough
point-in-time history for `turnover_percentile_60d` are not reliably available.
The available files also lack a row-level binding for the 43 resolved outcomes,
so no outcome-conditioned statistic can be computed without inventing labels.

## 2. Live intake and boundary

| item | live value |
| --- | --- |
| research branch | `codex/b-volume-turnover-diagnostic-v1` |
| source base | `origin/master=040e077bbf208921798d2d5b1fa0bd2d51ba9a20` |
| production-state branch | `runtime-state=1c8b2eca3792aebf327557fe9279b88a177b0545` |
| PR #60 | `OPEN`, head `0a829193af5a761d3190d02543e9edd5b9312550`, exact-head checks `success`; untouched |
| PR #61 | `MERGED`, head `699b84a2367c3fabfc6df4c7639a0527c2bb6c3c` |
| PR #62 | `MERGED`, head `1ec066408d07843cbeebd295005b8c484d6acb1e` |
| Final OOS | `SEALED / UNREAD` |
| forbidden directory | `data/validation/continuous_speed_probe/` not read or touched |
| market-provider calls | `0` |

GitHub/PR queries were used only for live repository provenance. No market
provider or historical-market acquisition was attempted.

## 3. Existing evidence re-read

PR #60's committed baseline research output reports 43 resolved trades:
4 TARGET and 39 STOP. It also reports 31 FAST_STOP among the 39 STOP rows and
the existing `vol_ratio` summary. That document is an aggregate research
output, not a machine-readable 43-row outcome table. The exact per-signal
fields required by this diagnostic—outcome, FAST_STOP flag, Score, signal date,
and signal ID—are not available in the current Git-tracked checkout or the
live `runtime-state` tracker.

The current live runtime-state tracker has 91 signals, all `pending` or
`triggered`; it does not supply the missing 43 resolved rows. PR #60's CI runs
have no downloadable research artifact containing those rows.

## 4. Feature availability audit

The four canonical lists cited by the baseline contain 75 candidates in total:

| signal dates | candidates | numeric `turnover` | numeric `vol_ratio` |
| --- | ---: | ---: | ---: |
| 2026-09-03, 2026-09-07, 2026-09-08, 2026-09-11 | 75 | 75/75 | 75/75 |

The canonical quote parser maps `turnover` from Tencent field `p[38]` and
`vol_ratio` from `p[49]`. These snapshot fields are sufficient to establish
that a numeric T-day value is present in the lists, but they do not provide a
recoverable, independently bound 60-session turnover history for each signal.
The raw quote captures and point-in-time float-share history for the 43
resolved rows are not present in the research checkout.

The existing turnover research acquisition is not sufficient for this sample:

| item | observed value |
| --- | --- |
| artifact | `data/validation/b_turnover_x_relative_volume_incremental_v1/tushare_gateway/` |
| source | third-party Tushare-compatible gateway, `daily_basic` |
| fields | `ts_code, trade_date, turnover_rate, float_share` |
| unit | turnover percent; float shares in 万股 |
| coverage | 769 sessions, `2023-06-30` through `2026-08-28` |
| vintage status | `NO_VINTAGE_PROOF` |
| required signal dates present | `NO` for `2026-09-03`, `2026-09-07`, `2026-09-08`, `2026-09-11` |

Therefore it cannot produce an as-of-signal-date 60d percentile for the
target sample. Using current float shares, volume as a turnover proxy, or a
post-signal value would violate the point-in-time contract.

## 5. Leakage and contamination controls applied

- No provider acquisition, proxy probe, or network market-data call was made.
- No outcome was reconstructed from future data or from an unbound aggregate.
- No correlation, threshold, cohort, 2D table, ROC/AUC, Fisher test, or
  non-linearity claim was computed.
- Final OOS remained sealed and unread.
- `runtime-state` was read-only; it was not written.
- PR #60 was read-only and unchanged.
- No production workflow, Cloudflare Worker, formal B specification, universe,
  score, ranking, or historical artifact was modified.

## 6. Missing evidence and minimum correct next step

To resume, the user must authorize a separate bounded research acquisition and
provide or restore both of the following:

1. A point-in-time turnover source covering every resolved signal and the
   preceding up-to-60 XSHG sessions, with T-day `turnover_rate` (or validated
   `volume / free_float`), units, symbol/date coverage, raw-before-complete
   persistence, source/version metadata, and hashes. A current float-share
   snapshot must not be used to backfill history.
2. The existing formal performance output as a machine-readable, exact
   `signal_id`-bound table for the 43 resolved rows, including TARGET/STOP,
   FAST_STOP, Score, `vol_ratio`, signal date, and outcome provenance. It must
   be restored from existing immutable evidence or another already-authorized
   artifact; it must not be fabricated or recomputed by calling a provider in
   this task.

After those inputs are available, the diagnostic can resume from the fixed
coarse definitions in the user request. Until then, the only valid product
paths are to leave formal B and PR #60 unchanged and keep the turnover idea
`OBSERVATIONAL_ONLY / NOT_FORMAL_B`.

## 7. Decision

`NEEDS_MORE_EVIDENCE`

This is a data/provenance stop, not `RESULT_A`, `RESULT_B`, `RESULT_C`, or
`RESULT_D`. No claim about incremental turnover value is supported by this
run, and no recommendation to add turnover to the PR #60 observational layer
or to formal B is made.
