# B signal entry-validity decay research

> Protocol: `B_SIGNAL_ENTRY_VALIDITY_DECAY_V1` / SHA-256 `19e5511fbb9b6abbd62192978485fc190f27283e7736c42db7b830be7db7ec99`
> Strategy: `B_BREAKOUT_RETEST_LEGACY_V1_1`；data cutoff: `2026-09-30`；prospective epoch: `2026-09-03`
> Research-only. No production rule, tracker state, runtime-state, Formal B output, or prospective evidence was changed.
> Final OOS: `SEALED / UNREAD`; C outcome data: `NOT_READ`.

## Decision

`SIGNAL_VALIDITY_RESEARCH_BLOCKED_BY_DATA_GAP`

The available evidence does not contain enough complete post-signal sessions to classify the late-trigger cohorts reliably. This is a data-gap stop, not evidence supporting a shorter production validity window.

## 1. Current semantics audit

| Area | Current behavior | Interpretation |
|---|---|---|
| prospective tracker | Searches first trigger on T+1 through T+10 XSHG sessions | Earliest entry T+1; latest first trigger T+10 |
| prospective T+10 untriggered | `EXPIRED_UNTRIGGERED` at T+10 | T+10 is an operational entry-expiry boundary |
| prospective T+10 triggered | Entry is allowed; entry-day sell is forbidden; exit is handled on the next legal sellable session | T+10 is also an entry day, not only a review node |
| prospective time exit | Earlier entries close at T+10 close; a T+10 entry is deferred to the next sellable session | Current operational path has time-exit semantics |
| strategy-rule performance | `_rule_sessions_after` searches through report date; `time_exit=False`; no entry expiry | A first trigger after T+10 is currently possible |
| fixed horizons | T+3/T+5/T+10 are signal-date fixed-horizon snapshots | Independent of actual entry validity |

`ENTRY_VALIDITY_SEMANTICS_MISMATCH`: prospective tracker expiry/search is bounded at T+10, while strategy-rule performance waits through the report date without entry expiry or time exit.
The current tracker therefore mixes two meanings at T+10: an operational expiry/time-exit boundary and a fixed-horizon research node. They are kept separate in this study.

## 2. Signal and data-quality counts

Canonical signal-level sample: **210** signals across **14** signal dates, keyed only by `signal_id`.
Delay classification: known **118**; complete untriggered **0**; censored **9**; incomplete **82**; source conflicts **1**.

| Cohort | Total | Triggered | Delay-known | Operational complete path | Delay censored | Delay incomplete/conflict | Ambiguous | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| T+1 | 109 | 109 | 109 | 67 | 0 | 0 | 0 | OK |
| T+2 | 7 | 7 | 7 | 3 | 0 | 0 | 0 | INSUFFICIENT_SAMPLE |
| T+3 | 1 | 1 | 1 | 0 | 0 | 0 | 0 | INSUFFICIENT_SAMPLE |
| T+4-T+5 | 1 | 1 | 1 | 0 | 0 | 0 | 0 | INSUFFICIENT_SAMPLE |
| T+6-T+10 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | INSUFFICIENT_SAMPLE |
| UNTRIGGERED | 0 | 0 | 0 | 0 | 0 | 0 | 0 | INSUFFICIENT_SAMPLE |
| CENSORED_OR_INCOMPLETE | 92 | 0 | 0 | 0 | 9 | 82 | 0 | INSUFFICIENT_SAMPLE |

`INSUFFICIENT_SAMPLE` is pre-registered for metric samples below 10. The LATE group has only the one delay-known T+5 signal; no T+6–T+10 signal is delay-classifiable with complete prior observations. Analysis B additionally has 48 known-delay rows with incomplete operational paths.

## 3. Analysis A — fixed entry-relative horizon

The fixed-node results below use actual first-trigger entry `E`, current prospective fill semantics, A-share T+1, terminal target/stop handling, and close mark-to-market only when no terminal event occurred by the node. Missing nodes remain missing.

| Group | E+1 mean / median / positive rate (n) | E+3 mean / median / positive rate (n) | E+5 mean / median / positive rate (n) |
|---|---|---|---|
| EARLY (n=117) | -0.3050 / -0.9881 / 36.4486% (107) | -1.4128 / -2.5719 / 18.6813% (91) | -1.6321 / -2.7674 / 15.5844% (77) |
| LATE (n=1) | -1.5559 / -1.5559 / 0.0000% (1) | — / — / —% (0) | — / — / —% (0) |

| Comparison | Early | Late | Late − Early |
|---|---:|---:|---:|
| average_return_pct | -1.8463 | — | — |
| median_return_pct | -2.9837 | — | — |
| win_rate_pct | 11.4286 | — | — |
| profit_factor | 0.4101 | — | — |
| average_mfe_pct | 3.5711 | — | — |
| average_mae_pct | -4.6363 | — | — |
| E+3 | -1.4128 | — | — |
| E+5 | -1.6321 | — | — |

Comparison status: `INSUFFICIENT_SAMPLE`; bootstrap: `NOT_RUN_INSUFFICIENT_SAMPLE`. No CI is reported because the LATE comparison group is below the fixed minimum sample.

## 4. Analysis B — current operational path

The operational cohort metrics use the existing T+10 prospective replay, including T+10 expiry and T+10 closure semantics. Incomplete and censored paths are excluded from realized-return denominators and remain visible in the counts.

| Cohort | Win rate | Avg return | Median return | Avg winner | Avg loser | Payoff | PF | Target hit | Stop hit | Avg holding | MFE | MAE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| T+1 | 11.9403% | -1.7074% | -2.8386% | 11.2295% | -3.4616% | 3.2441 | 0.4399 | 11.9403% | 88.0597% | 2.8507 | 3.6354% | -4.6044% |
| T+2 | 0.0000% | -4.9476% | -4.7059% | —% | -4.9476% | — | 0.0000 | 0.0000% | 100.0000% | 2.3333 | 2.1356% | -5.3489% |
| T+3 | —% | —% | —% | —% | —% | — | — | —% | —% | — | —% | —% |
| T+4-T+5 | —% | —% | —% | —% | —% | — | — | —% | —% | — | —% | —% |
| T+6-T+10 | —% | —% | —% | —% | —% | — | — | —% | —% | — | —% | —% |
| UNTRIGGERED | —% | —% | —% | —% | —% | — | — | —% | —% | — | —% | —% |

## 5. Bounded descriptive diagnostics

These are descriptive only; they do not add a filter, score, RR rule, model, or second strategy.

| Delay | n | Trigger distance mean | Score mean | RR mean | Pre-trigger max high mean | Pre-trigger max low mean | Pre-trigger close drift mean | Stop touched before entry |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| T+1 | 109 | -0.3803% | 52.0917 | 3.1520 | —% | —% | —% | 0 |
| T+2 | 7 | 1.7148% | 51.5714 | 3.1698 | 0.5471% | -1.9237% | -1.3016% | 1 |
| T+3 | 1 | 2.3066% | 60.0000 | 3.1478 | 0.8141% | -2.3066% | -1.6282% | 0 |
| T+5 | 1 | 0.7511% | 57.0000 | 2.9342 | -0.3919% | -5.2253% | -3.4944% | 1 |

## 6. Counterfactual cutoff sensitivity

This table is a sensitivity table only. It does not select a production cutoff and does not mutate canonical rows.

| Cutoff | Retained triggered | Retained terminal | Expired untriggered | Excluded known-late | Excluded unclassified trigger | Avg return | Win rate | PF | Expectancy |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| T+1 | 109 | 67 | 0 | 9 | 23 | -1.7074% | 11.9403% | 0.4399 | -1.7074% |
| T+2 | 116 | 70 | 0 | 2 | 23 | -1.8463% | 11.4286% | 0.4101 | -1.8463% |
| T+3 | 117 | 70 | 0 | 1 | 23 | -1.8463% | 11.4286% | 0.4101 | -1.8463% |
| T+5 | 118 | 70 | 0 | 0 | 23 | -1.8463% | 11.4286% | 0.4101 | -1.8463% |
| T+10 | 118 | 70 | 0 | 0 | 23 | -1.8463% | 11.4286% | 0.4101 | -1.8463% |

## 7. T+10 semantic impact audit

Current runtime tracker waiting-for-trigger count: **133**. Current tracker status counts: `{"loss": 21, "pending": 133, "triggered": 52, "win": 4}`.
Prospective replay at cutoff: `{"ambiguity_count": 0, "eligible_signal_count": 201, "entered_count": 118, "expectancy_pct": -1.846278, "expired_untriggered_count": 0, "open_or_pending_count": 139, "profit_factor": 0.410069, "stop_count": 62, "target_count": 8, "time_exit_count": 0, "trigger_rate_pct": 58.706468, "waiting_trigger_count": 91, "win_rate_pct": 11.428571}`.
Strategy-rule performance at the same cutoff: `{"ambiguous": 0, "avg_return_pct": -1.149709, "eligible_signals": 201, "expectancy_pct": -1.149709, "open_rule_trades": 0, "performance_data_incomplete": 131, "profit_factor": 0.517546, "resolved_closed_trades": 70, "time_exit_count": 0, "total_signals": 210, "trigger_rate": 58.706468, "triggered": 118, "untriggered": 0, "win_rate": 11.428571}`.
These counts expose the mismatch but are not a causal performance comparison because the same source has missing XSHG observations; see `CENSORED_OR_INCOMPLETE` and `PERFORMANCE_DATA_INCOMPLETE`.

## 8. Reproducibility and boundaries

- Signal-level artifact SHA-256: `a8175bf4115b09db29fa32061c4f20f368773be334b571cef18b4b3f98d59db0`.
- Cohort summary SHA-256: `580ab10ad26f65eeb0def30e8260155af1f83bfdd8f7e6c40e8bfd0a411cde69`.
- Evidence manifest SHA-256: `77b8b07e9b3fbbeda01425c7ac135221b8324f045978ab0cf6a91ba6330ae78a`; missing evidence codes: `0`.
- No Final OOS, C outcome, old D, or forbidden validation directory was read.
- No candidate generation, score, threshold, trigger, stop, target, RR, tracker state machine, entry expiry, T+10 closure, Formal B output, workflow, delivery, runtime-state, or prospective evidence was modified.

Terminal marker: `SIGNAL_VALIDITY_RESEARCH_BLOCKED_BY_DATA_GAP`
