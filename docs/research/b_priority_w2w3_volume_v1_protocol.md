# B_PRIORITY_W2W3_VOLUME_RESEARCH_V1 — pre-outcome protocol

Classification: **research question / STRICT PATH / DEVELOPMENT /
RECONSTRUCTED_RETROSPECTIVE / DIAGNOSTIC_ONLY**. Date: 2026-11-04, Asia/Shanghai.

## Question, materiality and exit

Among existing qualified Formal B candidates on the same signal date, does the
fixed B-native 2→3 price-structure proxy, the three existing report volume
observations, or their fixed lexicographic ordering identify a better small
priority list than no ranking? This answers whether a separate product design
for `今日优先级：首选 / 次选 / 观察` is warranted. It does not qualify securities,
predict Elliott waves, decide a production label mapping, or promote a strategy.

The earlier `B_OPERATIONAL_SCORE_VOLUME_RANKING_V1` was **NOT_STARTED /
SUPERSEDED_BY_USER_DECISION**, not a failed study or an efficacy finding.
`B_CANDIDATE_RANKING_VOLUME_TURNOVER_DIAGNOSTIC_V1` and
`B_RANKING_BASELINE_SCORE_IDENTITY_NOT_RECOVERABLE` remain unchanged for their
own identities. This study never uses old Score as baseline, control, feature
or tie breaker, and never reconstructs Sina membership.

Stop after the fixed analyses and three decisions, or immediately at a real
definition, input, provenance or parity blocker. No feature search, alternate
structure definitions, weight fitting, threshold optimization, new Phase,
provider acquisition, production dispatch, merge or deployment is authorized.
Missing evidence does not become a global product blocker; existing Formal B,
report observations and genuine prospective operations may continue.

## Intake and inputs

Live intake: master `7d7b6c9f2de1c45e1a4b1a493395ac81646489d8`, runtime-state
`ebe014748cfd3a551b0e3589124e08b2c154871d`; #103 squash-merged into that master;
master correctness run `41767491750` completed SUCCESS on that exact head.
Open PRs: #60, #66, #67, #68, #71, #84, #87, #89; none is imported or modified.
Independent branch: `codex/b-priority-w2w3-volume-v1`, based on live master.
These identities are intake provenance, not future live-state invariants.

Only this repository's frozen historical raw OHLCV and corporate actions,
qualified identity stream and existing B trace are used. No data or state from
`EFSing/stock-data-pipeline` is imported. Frozen inputs:

- Qualified B stream: `data/validation/strategy_candidate_eligibility_v1/b_breakout_retest_eligibility_events.jsonl.gz`,
  17,714 identities; compressed SHA-256
  `8940a4a346ac6911ba669f84a9ceba7ef878b0ed0ce51edf673439b52aa056b9`.
- Its historical V1 filename is reconciled by the existing V1_1 membership proof
  in `data/validation/strategy_candidate_eligibility_v1_1/b_reconstruction_impact_audit.json`.
  Corrected spec SHA is
  `f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd`.
  This proves qualified event membership, not old full Score parity.
- Frozen raw `daily_k.parquet`: 180,203,424 bytes, SHA-256
  `61189a4850e2eb157453e28e5375e502e20d214508bbe70ea71066ca3e05e426`.
- Frozen `adjustment_factors.parquet`: 295,284 bytes, SHA-256
  `a1b7d63c5826ccd3610dc9bdd949d82eeb0ba84ffad451bfb8bb30ca74962716`.
- Existing raw-input manifest:
  `data/validation/core_signal_validation_continuous_parts/core_signal_validation_manifest.json`;
  verify bytes/SHA for its six raw members. Hashing an outcome-bearing compressed
  file or extracting identity bytes is permitted; decoding its outcome is not.

Historical signal interval is 2023-06-30..2026-08-28, 769 frozen sessions;
qualified candidates need not exist on every session. Primary is Main Board
using the existing deterministic `_board_for_symbol`: `00`/`60` = Main,
`30` = ChiNext, `68` = STAR, other prefixes = OUT_OF_SCOPE_PREFIX. Retain the
Beijing identities separately; never relabel them Main. Secondary: combined
Main + ChiNext + STAR, plus ChiNext and STAR separately. Secondary cannot
overturn Primary or select a different primary universe.

Historical prices use the existing T-anchor affine adjustment, ascending events
with `bar_date < ex_date <= T`; volume stays raw. All input windows end at T
and use the existing 260-bar lookback. Known-at vintage is explicitly unverified
for the retrospective official dump. Causal prefix tests do not repair that
limitation or make retrospective data prospective evidence. Invalid dates,
duplicate keys, nonfinite OHLCV, absent T or insufficient history fail closed.
An absent exchange-date bar cannot silently be fabricated or called a suspension.

## Mandatory order before outcomes

1. Audit input availability, exact identities/SHA, trace recovery, allowed volume
   coverage and causal structure behavior. Do not decode B outcomes.
2. Compare reconstruction against multiple **real** persisted
   `data/volume_observations/volume_observations_YYYYMMDD.json` stores from the
   pinned runtime-state, including complete and incomplete candidates. Use the
   original, provenance-bound T-day stock prefix; check three values (rtol/atol
   1e-12), exact `window_days` and exact `missing_reason`, preserving signal_id.
   Reusing the frozen pure calculation is required. Same-code agreement on
   historical/synthetic inputs alone is not real-observation parity.
3. Commit this protocol. The resulting commit is `PRE_OUTCOME_PROTOCOL_COMMIT`;
   record its exact SHA in the script/summary/report after commit. Require the
   committed protocol bytes (LF-normalized) to remain identical.
4. Only after the protocol commit **and all input/parity gates pass** may the
   research read its DEVELOPMENT outcomes and run R0–R3.

Actual parity mismatch → `B_VOLUME_OBSERVATION_HISTORICAL_PARITY_FAILED`.
Unavailable original parity inputs → `B_PRIORITY_RESEARCH_BLOCKED_BY_DATA_GAP`,
with `NOT_RUN_INPUTS_UNAVAILABLE`, null mismatch count and null efficacy metrics.
Never invent an input window from an aggregate observation, copy stored results
as a reconstruction, fetch current history as old T input, or label missing
evidence a parity pass/failure. No requested comparison may bypass this gate.

## One B-native structure proxy

Identity: `B_W2W3_STRUCTURE_PROXY_V1`. The existing
`b_phase_volume_path_diagnostic._first_breakout_trace` supplies the deterministic
first qualifying breakout index `i`, with its unconditional first-breakout
rule. Do not search a later/better breakout. Check its qualification-stage/base
against the existing `_b_match`; structure never enters B qualification.

For signal index T (Python slice endpoints exclude T):

```text
L0 = min(low[i-60:i])
H1 = max(high[i:T])
h1_idx = first index attaining H1
L2 = min(low[h1_idx+1:T])
```

H1 needs at least one complete following day before T. Require `L0 < L2 < H1`.
Otherwise use `STRUCTURE_PROXY_UNAVAILABLE_OR_INVALID`, retaining the reason.
For valid structure, `recovery_ratio = (close_T-L2)/(H1-L2)`:

- `< 0.5`: `EARLY_PULLBACK`;
- `0.5 <= ratio <= 1.0`: `W2_TO_W3_TRANSITION_PROXY`;
- `> 1.0`: `POST_H1_CONTINUATION_PROXY`.

H1/L2 exclude signal-day high/low; close_T is allowed. No T+1 OHLCV or future
pivot confirmation. Equal highs always choose the earliest index. Test future
append invariance, determinism, exact endpoints, H1/L2 exclusion, equal-high
ties, no pullback, invalid denominator, missing/invalid bars and identity.
If this unique causal definition cannot be reconciled before outcome access,
stop `B_W2W3_STRUCTURE_PROXY_DEFINITION_BLOCKED`; no competing definitions.
Every report describes a **结构代理 / 结构状态**, never a certain wave prediction.

## Three report volume observations only

Reuse `B_VOLUME_PROSPECTIVE_REPORT_OBSERVATION_V1` and its frozen pure
`calculate_pullback_volume_observation`. R = `i+1:T` in Python, excluding T.

| Field | Fixed good direction |
|---|---|
| down_volume_share | lower |
| up_down_volume_ratio | higher |
| pullback_volume_decay_ratio | lower |

Within each signal date and declared board cohort, percentile rank uses average
ordinal ties divided by n (`rank(method='average', pct=True)`). Good rank is
`1-percentile_rank` for the two lower-is-better fields and `percentile_rank`
for up_down_volume_ratio. `volume_quality` is their arithmetic mean with fixed
equal weights. R2/R3 percentiles are computed on the identical three-field
complete-case cohort. Single-field analyses rank that field's own valid rows.
No zero/mean imputation. No breakout/reactivation/worst-day volume, turnover,
RV20_T, sector, regime, RSI/MACD, other indicators or machine learning search.

## Fixed analyses and fair denominators

**R0 — NO_RANKING_BASELINE**: same-day equal-weight comparable qualified B.
Random Top-K expectation equals that day's comparable candidate mean; no
simulated random sequence is needed. All primary inference equally weights
signal dates rather than stock rows.

**R1**: transition vs other available states (EARLY and CONTINUATION) on dates
containing both groups; report their paired date-level contrast. Also report
each of the four states separately, including invalid/unavailable, with row
and date counts. Show structure-available full cohort and R2/R3 intersection
separately. Do not merge continuation into transition or force a Top1 from
R1's large ties.

**R2**: descending volume_quality. Report each of the three fields separately
as well as the composite: Top1/3/5, daily Spearman rank IC, top-bottom spread
and monotonicity, 5D/10D return, positive rate, MFE/MAE and year consistency.

**R3**: lexicographic descending `(is_transition, volume_quality)`. Invalid
structure is retained as non-transition, explicitly labeled unavailable;
non-transition states are never renamed transition. No artificial total score.

R2/R3 and their R0 have exactly the same rows/dates after volume availability
and horizon-specific outcome availability. Do not compare full R0 with a
complete-case R3. On every horizon, remove missing outcomes from both selection
and benchmark before measuring K. Top1 requires >=2 comparable candidates,
Top3 >=3, Top5 >=5. Ties straddling a Top-K boundary receive equal fractional
selection weight; do not use old Score or outcomes to break ties. Report mean
Top-K outcome, same-day R0, uplift, positive rate, MFE/MAE, candidate counts
and eligible dates. R3−R2 paired differences also assess structural increment.

For each daily ordering, rank IC excludes constant feature/outcome days and
requires >=3 comparable candidates. Daily top-bottom/monotonicity uses five
ordered rank groups on dates with >=5 candidates; exclude constant-score days,
never split equal scores using outcomes. Empty groups remain unavailable.
Report eligible counts so small-date coverage is visible.

## Outcome and statistics frozen before reading

Primary: 5D return. Secondary: 10D return and 5D/10D MFE/MAE. Reuse the existing
DEVELOPMENT V2 outcome machinery (`validate_development_returns_v2._build_event_record`)
for exactly the frozen B identities, or identity/hash-verified already frozen
B outcomes with the same convention. Entry = T+1 XSHG open, exit measurement =
T+5/T+10 close; use its corporate-action-adjusted path consistently. No new
entry, actual-fill claim, MODEL_P/MODEL_R mixture, or A-strategy outcome
substitution. Canonical stop/target may be reported only as a separately
proven existing frozen B secondary path; otherwise mark unavailable, do not
create one. Missing forward windows retain frozen missing statuses.

Report date-level mean, median, positive-return proportion, 95% cluster
bootstrap CI, eligible signal dates and candidate count. Bootstrap 10,000
signal-date resamples with seed 20261104; resample each complete date cluster
jointly across paired methods. No row-wise independent-stock inference. Show
2023, 2024, 2025 and 2026 frozen cutoff separately. Report per-year sample size
and reversals. No claim of independent unseen validation from these reused
DEVELOPMENT data; all results remain exploratory with no parameter selection.

Episode sensitivity retains the earliest signal_date per
`(symbol, existing breakout_date)` before rebuilding the cohort's complete
cases, ranks, same-day benchmarks and statistics. Also omit the five dates
with largest absolute daily primary uplift (predeclared influence diagnostic),
and report the remaining mean; do not use it to redefine methods. Run separate
ChiNext/STAR and combined in-scope board sensitivity without changing Primary.

## Decisions and stopping rules

Record three independent markers, each from its own allowed set:

```text
B_W2W3_TRANSITION_PRIORITY_SUPPORTED_FOR_FURTHER_VALIDATION
B_W2W3_TRANSITION_PRIORITY_NEEDS_MORE_EVIDENCE
B_W2W3_TRANSITION_PRIORITY_NO_CLEAR_SIGNAL

B_REPORT_VOLUME_PRIORITY_SUPPORTED_FOR_FURTHER_VALIDATION
B_REPORT_VOLUME_PRIORITY_NEEDS_MORE_EVIDENCE
B_REPORT_VOLUME_PRIORITY_NO_CLEAR_SIGNAL

B_W2W3_VOLUME_PRIORITY_SUPPORTED_FOR_FURTHER_VALIDATION
B_W2W3_VOLUME_PRIORITY_NEEDS_MORE_EVIDENCE
B_W2W3_VOLUME_PRIORITY_NO_CLEAR_INCREMENTAL_SIGNAL
```

SUPPORTED requires Main primary evidence: positive 5D direction with 95% CI
excluding zero for the relevant R1 contrast / R2 Top1 and Top3 / R3 Top1 and
Top3 vs matched R0; direction positive in at least three of the four years;
both Top1/Top3 consistent where applicable; episode-dedup and omission of the
five influential dates retain positive direction; mean MAE does not worsen.
R3 must have an actual paired increment over matched R0 and report R3−R2,
even if the latter is inconclusive. Report magnitude and all failed conditions;
statistical significance alone does not authorize a production implementation.
Insufficient paired-date coverage, missing parity/provenance or uncertain
robustness means NEEDS_MORE_EVIDENCE. Adequate completed evidence without a
consistent direction means NO_CLEAR_SIGNAL / NO_CLEAR_INCREMENTAL_SIGNAL.
Three feature analyses are exploratory; do not select a winner from a lone
significant cell or optimize direction/weights after results.

Only if combined evidence supports further validation may the report propose
`PRIORITY_PRODUCT_DESIGN_WARRANTED`. A separate user-approved product PR must
decide structure/volume display wording, `首选 / 次选 / 观察` mapping and any
old Score demotion. Otherwise keep old Score's production behavior. In all
cases `production Score change = 0`. Turnover research is not launched; any
next suggestion is a separate decision/backlog item.

Deliver the Chinese report with the eleven requested plain-language answers,
three core tables and explicit uncomputed metrics if blocked. Store the small
summary in Git. Detail uses deterministic gzip (mtime=0), canonical sorted
JSONL, row count, byte count, compressed and content-stream SHA-256 and a
reproduction command. Never overwrite a frozen input or other study artifact.
Run focused/relevant/full tests, compileall, diff boundary checks, deterministic
rerun/hash equality, causal and parity checks (or their explicit blocked state).
Update HANDOFF/CURRENT_STATUS; Decision Log only for a lasting decision.
Push this independent branch, create one Draft against then-live master,
verify exact diff/CI/mergeability, never auto-merge. Normal success terminal:
`B_PRIORITY_W2W3_VOLUME_PR_READY_FOR_USER_DECISION`; real input/definition
blockers take precedence. Final OOS remains **SEALED / UNREAD**.
