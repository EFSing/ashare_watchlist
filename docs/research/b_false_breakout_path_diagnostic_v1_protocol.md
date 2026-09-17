# B False Breakout Path Diagnostic V1 Protocol

Status: FROZEN_BEFORE_OUTCOME_COMPARISON
Identity: B_FALSE_BREAKOUT_PATH_DIAGNOSTIC_V1
Classification: research question; DEVELOPMENT / RECONSTRUCTED_RETROSPECTIVE / DIAGNOSTIC_ONLY.

Question: do TARGET and FAST_STOP have repeatable breakout–retest–reactivation path differences,
and does price defense add stable information to the existing volume-only baseline?
Materiality: decide whether evidence justifies a separately authorized B V2 candidate study;
this is not a correctness/product blocker. Stop after one fixed analysis and terminal decision.

## Inputs and boundaries

Base origin/master: 9c3f011ebc06d33347372b3792ec28f11c505f40.
Independent branch: codex/b-false-breakout-path-diagnostic-v1. PR #60 untouched.
Frozen spec: f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd.
Frozen daily-K: 61189a4850e2eb157453e28e5375e502e20d214508bbe70ea71066ca3e05e426.
Cohort: exact existing 17,714 qualified DEVELOPMENT identities, not the structural near-miss cohort.
Reuse b_phase_volume_path_diagnostic_v1_protocol.md and report.md (VOLUME_PATH_NEEDS_MORE_EVIDENCE).
Reuse exact first-breakout trace and all five volume features. Verify frozen registry/cohort identities.
No new acquisition, production dispatch, runtime-state mutation, historical canonical rewrites,
B changes, Final OOS access or continuous_speed_probe access. No threshold/horizon/subgroup search.

## PIT feature definitions

i is the existing trace's first qualifying breakout, T the last passed bar, L=base_hi=
max(close[i-60:i]). All prices are adjusted using only corporate actions effective through T.
Volume baseline is mean(volume[i-20:i]), excluding i. No feature uses any bar after T.
Pre-T retest R is i+1 through T-1. Empty R is unavailable, never zero-filled.

- breakout_return = close[i]/close[i-1]-1; breakout_volume_ratio is reused.
- min_low_vs_breakout_level = min(low[R])/L-1.
- max_retest_depth_vs_breakout_level = max(0,-min_low_vs_breakout_level).
- min_close_vs_breakout_level = min(close[R])/L-1 (primary price defense).
- days_below_breakout_level = number of R closes strictly below L.
- reclaim_breakout_level_days = trading-bar delay from first below-L close to first later
  close >= L through T. None with NO_BREACH or NOT_RECLAIMED reason.
- days_to_reclaim_breakout_level aliases that delay; no second definition.
- days_from_breakout_to_signal = T-i, in observed stock trading bars.
- retest-local high = max(high[R]), fixed from pre-T bars only.
- days_to_reactivation_local_high = delay from first minimum-low R bar to first subsequent
  close exceeding this fixed pre-T high, through T; unavailable if not reached. Because the
  reference includes all R highs, any crossing can occur only at T; report this limitation.
- days_to_reclaim_ma5 is omitted; it is optional and no new MA research is needed.
- reactivation_price_strength = close[T]/close[T-1]-1.
- reclaims_breakout_level = close[T]>=L.
- exceeds_retest_local_high = close[T]>max(high[R]).
- reactivation relative volume: reuse reactivation_vs_retest_ratio and
  reactivation_vs_breakout_ratio; existing pull ratio and pre_t_retest_volume_ratio unchanged.

Social-media 3x, 40/50/33%, 10% turnover and MA5 timing are hypothesis provenance only.
Observable price/volume/time are facts; seller exhaustion/accumulation are unproven mechanisms.

## Labels and execution

Primary TARGET vs FAST_STOP; secondary TARGET vs all STOP (including FAST_STOP).
Reuse track_perf.rebuild_execution_state_from_observations with its formal rule fills,
open-first gaps, first sellable entry+1 XSHG session, same-bar ambiguity and T+10 closure
(including T+11 legal exit when entry is T+10). FAST_STOP is STOP at entry+1 or entry+2
XSHG session; ambiguous/time/untriggered/incomplete paths are separately counted.
Reuse V2 affine outcome adjustment for OHLC and transform frozen T rule levels to the
same ex-post basis using the identical helper. Future actions are outcome-only.
The fixed endpoint is existing T+10 plus required T+11, never expanded after results.

## Fixed comparisons and dependence

Report counts, missingness and median/distribution differences for every feature, both label pairs.
No significance claim from independent-row assumptions. Stable value-based terciles use pooled
feature 1/3 and 2/3 quantiles without labels, same edges in all sensitivities; ties stay together.
Report all cells, including sparse cells. No best-cell selection.
Only joint matrices: (1) volume contraction tercile × price-defense tercile;
(2) same matrix × boolean exceeds_retest_local_high. Volume-only baseline is matrix (1)
marginalized over defense. Contrasts use FAST_STOP/(TARGET+FAST_STOP), and separately
STOP/(TARGET+STOP), never FAST_STOP/STOP as primary discrimination.
Price contrast: defense Q3 minus Q1 within each volume bin, weighted by harmonic pair count.
Volume contrast: contraction Q1 minus Q3 within each defense bin, same weights.
Reactivation contrast: true minus false within each defense × volume cell, same weights.
Also condition reactivation on signal-return terciles to detect contemporaneous-return restatement.
Only cells with >=30 rows and >=5 each compared label per side enter contrasts; all counts shown.

Execute overall; named years 2023/2024/2025/2026; Main Board (00/60);
earliest qualified signal per (symbol, breakout_date) episode; inverse episode-size weights;
singleton/repeated episode split; existing near-price-limit proxy exclusion (not exact limit state);
existing b_shadow_monitor._market_snapshot trend regime (same frozen definition, reconstructed,
not fabricated prospective capture). Report leave-one-month-out primary contrasts and episode
concentration. Quantile edges never change between these views.

## Falsification and terminal rubric

Expected price-defense contrast is negative. Strong support needs <=-5 percentage points overall,
Main Board and earliest-episode, negative in >=3 named years and no supported positive year,
negative in every supported leave-one-month-out view, retained after proxy exclusion and
inverse episode weighting. It must remain negative within volume strata rather than merely
repeat the volume baseline. Joint reactivation support additionally needs negative conditional
contrast within return strata; otherwise label contemporaneous-return alternative UNRESOLVED.
Unsupported strata (<required cells/counts) are INSUFFICIENT_DATA, not supporting evidence.
Year flips, lack of Main support, disappearing episode contrast, isolated months/episodes,
no conditioned price increment, or return-restatement falsify strong support; no rescue changes.
Turnover is included only with historical/date-valid/reproducible/PIT source evidence. Existing
third-party daily_basic NO_VINTAGE_PROOF is insufficient; amount is never turnover rate.
Bounded probe: existing provider code/provenance and package capability only, zero data calls.

A: B_FALSE_BREAKOUT_PATH_DIAGNOSTIC_NO_ACTION if price increment absent/reversed or unstable;
research decision REJECT (claim), no automatic follow-up. Insufficient input is explicitly
NEEDS_MORE_EVIDENCE and cannot masquerade as evidence of no effect.
B: B_FALSE_BREAKOUT_PATH_DIAGNOSTIC_PROSPECTIVE_EVIDENCE_REQUIRED if overall and Main price
contrasts are negative but strong checks fail; NEEDS_MORE_EVIDENCE, freeze definitions only.
C: B_FALSE_BREAKOUT_PATH_DIAGNOSTIC_BV2_DECISION_REQUIRED only if all strong checks plus joint
reactivation/non-restatement checks pass; stop for user approval of a separate B V2 protocol.
No terminal changes Formal B. No automatic prospective deployment or B V2 creation.
