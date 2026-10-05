# B_ENTRY_VALIDITY_SEMANTICS_IMPACT_V1

Decision marker: `DUAL_MODEL_SEMANTICS_INTENTIONAL_REPORTING_SEPARATION_READY_FOR_USER_DECISION`

This is a research-quality correctness audit. It does not change production execution semantics, tracker state, entry validity, T+10 behavior, Formal B, runtime-state, or formal performance definitions.

## 1. Fixed intake and universe

- Data cutoff: `2026-09-30`; strategy: `B_BREAKOUT_RETEST_LEGACY_V1_1`; unit: canonical `signal_id`.
- Live audit base: `origin/master=fb05327289fed9d13961b162a1c76c97c39f220d`.
- Runtime source: `origin/runtime-state=1a0a1fa8331cd88ce9e4a16673a60ea3624af761`.
- Canonical signal count: `210`; canonical rows mutated: `false`.
- Existing source protocol: `B_SIGNAL_ENTRY_VALIDITY_DECAY_V1` / `19e5511fbb9b6abbd62192978485fc190f27283e7736c42db7b830be7db7ec99`.
- Final OOS: `SEALED / UNREAD`; C outcome, old D and forbidden validation data: `NOT_READ`.

PR #95/#96/#97 were read as live OPEN independent work; PR #98 and PR #99 were read as MERGED historical checkpoints. Their CI and merge identities are provenance only; this audit does not merge or cherry-pick any of them.

## 2. Call-chain contract evidence

| Concern | MODEL_P prospective tracker | MODEL_R strategy-rule performance |
|---|---|---|
| earliest first entry | T+1 | T+1 opportunity after signal date |
| latest first trigger | T+10 | report date; may exceed T+10 |
| trigger window | `_execution_horizon_sessions` / T+1..T+10 | `_rule_sessions_after` / T+1..report date |
| T+10 untriggered | `EXPIRED_UNTRIGGERED` | no expiry; `UNTRIGGERED` only if complete through report date |
| T+10 first trigger | allowed; next XSHG session is first sellable session | allowed if report date contains it |
| earlier entry at T+10 | T+10 close `TIME_EXIT` unless earlier terminal event | no time exit; continues |
| entry-day sellability | cannot sell on entry day | cannot sell on entry day |
| stop/target | open-first gap, then low/high; same-bar ambiguous | canonical rule price low/high; same-bar ambiguous |
| missing observation | incomplete/unverified; no zero-fill/future repair | `PERFORMANCE_DATA_INCOMPLETE`; no zero-fill |
| fixed T+3/T+5/T+10 | signal-date fixed-horizon observation | independent of execution validity |

Evidence is from `scripts/track_perf.py::rebuild_execution_state_from_observations`, `::_execution_horizon_sessions`, `::_sellable_exit_decision`, `::_time_exit_t1_decision`, `::_rule_sessions_after`, `::_strategy_rule_trade_row`, `::build_strategy_rule_performance`; renderer wiring is `scripts/render_daily_close_html.py::build_report_model`.

## 3. Category A — ENTRY_EXPIRY_MISMATCH

Definition: MODEL_P is complete `EXPIRED_UNTRIGGERED` at T+10 while MODEL_R first triggers after T+10.

- Exact count: **0**.
- Complete-evidence count: **0**.
- Incomplete/censored within exact rows: **0**.
- Unresolved candidates with an incomplete MODEL_P expiry decision: **92**; potentially affected eligible count: **83**.
- Unresolved MODEL_P delay-status breakdown: `{"CENSORED": 9, "DATA_CONFLICT": 1, "INCOMPLETE": 82}`; `9` censored rows are excluded from potentially affected impact because they have no T+1 opportunity by the cutoff.
- New rule trades outside the prospective contract: **0** exact observable trades.
- Exact signal rows: `None`.
- Exact trigger/open/closed impact: `{"closed_count_delta_MODEL_R_minus_MODEL_P": 0, "common_eligible_denominator": 201, "open_count_delta_MODEL_R_minus_MODEL_P": 0, "trigger_rate_delta_pct_points_MODEL_R_minus_MODEL_P": 0.0, "triggered_count_delta_MODEL_R_minus_MODEL_P": 0}`.

The 83 potentially affected eligible rows are unresolved because the prospective T+10 expiry path and the rule path are incomplete; 9 additional censored rows are not yet T+1-eligible by the cutoff and are not counted as potentially affected. The full per-signal state, including all missing sessions, is in `signal_level_comparison.csv`.

## 4. Category B — TIME_EXIT_MISMATCH

Definition: same signal and first-entry date, first entry T+1..T+9, MODEL_P completes with T+10 time exit, and MODEL_R continues after that exit.

- Entry-identity-comparable rows (first entry known): `118`.
- Exact count: **0**.
- Complete-evidence count: **0**.
- Incomplete/censored within exact rows: **0**.
- Unresolved early-entry candidates: **48**.
- Exact signal rows: `None`.
- Exact later outcome counts: `{}`.
- Exact trigger/open/closed impact: `{"closed_count_delta_MODEL_R_minus_MODEL_P": 0, "common_eligible_denominator": 201, "open_count_delta_MODEL_R_minus_MODEL_P": 0, "trigger_rate_delta_pct_points_MODEL_R_minus_MODEL_P": 0.0, "triggered_count_delta_MODEL_R_minus_MODEL_P": 0}`.

The 48 unresolved candidates have known early entry identity but missing post-entry observations, so the audit does not guess whether MODEL_P would time-exit or MODEL_R would later hit target, stop, or remain open.

## 5. Primary apples-to-apples intersection

The primary denominator requires both models to have complete observations at the same cutoff and matching first-entry identity. Missing, censored, conflict, not-yet-eligible and ambiguous rows are not added to realized-return denominators.

| Metric | MODEL_P | MODEL_R | MODEL_R - MODEL_P |
|---|---:|---:|---:|
| eligible signals | 70 | 70 | N/A |
| triggered | 70 | 70 | N/A |
| trigger rate % | 100 | 100 | 0 |
| expired untriggered | 0 | N/A | N/A |
| open trades | 0 | 0 | 0 |
| closed trades | 70 | 70 | 0 |
| target count | 8 | 8 | 0 |
| target rate % | 11.428571 | 11.428571 | 0 |
| stop count | 62 | 62 | 0 |
| stop rate % | 88.571429 | 88.571429 | 0 |
| time-exit count | 0 | 0 | 0 |
| time-exit rate % | 0 | 0 | 0 |
| win rate % | 11.428571 | 11.428571 | 0 |
| average return % | -1.846278 | -1.149709 | 0.696569 |
| median return % | -2.983723 | -2.001684 | 0.982039 |
| average winner % | 11.22952 | 10.791683 | -0.437837 |
| average loser % | -3.533478 | -2.690534 | 0.842944 |
| payoff ratio | 3.178036 | 4.010982 | 0.832946 |
| profit factor | 0.410069 | 0.517546 | 0.107477 |
| expectancy % | -1.846278 | -1.149709 | 0.696569 |
| average holding sessions | 2.828571 | 2.828571 | 0 |

Primary intersection count: **70**. Entry-price equality is a separate orthogonal difference: `35` of these rows have different current-model entry prices (MODEL_P gap/open fill vs MODEL_R canonical trigger); this is not classified as Category A or B.

## 6. Secondary full-universe state counts

- Universe: `210`; eligible by cutoff: `201`.
- MODEL_P delay statuses: `{"CENSORED": 9, "DATA_CONFLICT": 1, "INCOMPLETE": 82, "KNOWN": 118}`.
- MODEL_P terminal classes: `{"INCOMPLETE_OR_CENSORED": 140, "STOP": 62, "TARGET": 8}`.
- MODEL_R statuses: `{"CLOSED": 70, "NOT_YET_ELIGIBLE": 9, "PERFORMANCE_DATA_INCOMPLETE": 131}`.
- MODEL_R terminal classes: `{"INCOMPLETE_OR_CENSORED": 131, "NOT_YET_ELIGIBLE": 9, "STOP": 62, "TARGET": 8}`.

These counts expose incomplete/censored/conflict states; they are not complete performance metrics and do not treat missing observations as zero return.

## 7. Current renderer impact

| Report field / surface | Audit result | Current source |
|---|---|---|
| 今日总览 candidate/earliest-execution facts | UNAFFECTED_BY_ENTRY_VALIDITY_SEMANTICS; prospective daily rows drive them | `build_report_model` overview/daily_summary |
| 规则模拟未结案 / historical closed | AFFECTED by MODEL_R no-expiry/no-time-exit state | `trade_performance` from `build_strategy_rule_performance` |
| 胜率、平均收益、平均赢家/输家、payoff ratio、PF、expectancy、holding | AFFECTED in the rule-simulation block; denominators must remain MODEL_R-labelled | `render_daily_close_html.py::_performance_cards/_performance_metric_strip` |
| waiting-trigger count | prospective waiting count is separate and unaffected; rule funnel `untriggered` is MODEL_R-specific and affected | `build_trade_performance_summary` vs `trade_performance` funnel |
| cumulative strategy performance | NOT_PRESENT in current master renderer; no cumulative series was found | no current renderer field |
| fixed T+3/T+5/T+10 | `UNAFFECTED_BY_ENTRY_VALIDITY_SEMANTICS` when kept as fixed-horizon research snapshots | `track_perf.py` review points / renderer research panels |

The current page places the theoretical rule-price block near prospective review data and uses a generic performance heading. That is a reporting-separation risk even though the code/doc contract says the rule model is theoretical and not actual trades.

## 8. Contract-intent decision

The repository contract supports **B — independent rule simulation**: `docs/CURRENT_STATUS.md` calls the formal performance model theoretical strategy performance and not the user's actual trades; `docs/DECISION_LOG.md` records theoretical rule-price performance as read-only and independent from prospective observations; `track_perf.py::build_strategy_rule_performance` documents independence, and `tests/test_strategy_rule_performance.py` explicitly asserts no T+10 forced exit, open theoretical trades, and no mutation/backfill of prospective observations.

Terminal marker: `DUAL_MODEL_SEMANTICS_INTENTIONAL_REPORTING_SEPARATION_READY_FOR_USER_DECISION`.

Recommended reporting boundary for user decision: keep MODEL_P as the prospective execution/path model; label MODEL_R as `THEORETICAL_RULE_PRICE_SIMULATION_NO_ENTRY_EXPIRY_NO_TIME_EXIT`; expose separate denominators and separate open/closed/waiting counts; do not merge the two into one cumulative or realized-performance series. No production semantic change is implemented in this audit.

## 9. Reproducibility and artifacts

- Protocol SHA-256: `c053926e56c5e08ded3e3b9ee34ec4e6fe4490f0967204f32c5a06426659d67e`.
- `protocol.json`: `c053926e56c5e08ded3e3b9ee34ec4e6fe4490f0967204f32c5a06426659d67e`; `signal_level_comparison.csv`: `7ceb737026dccacc24828c1c4f648c9dcf06516782ff75e5be0711fe7789c085`; `impact_summary.json`: `36574c05598ba40cd31b750e937407ef07269011ab1e42ece0b9633de590a598`. The report hash is recorded in `manifest.json` after report generation.
- Manifest is generated after artifact hashes and records the command, live refs, source artifact identities and read-only evidence boundary.
- Final OOS remains SEALED / UNREAD; no C outcome, old D, forbidden validation data, provider call, runtime-state write, prospective backfill, merge, or production semantic change was performed.
