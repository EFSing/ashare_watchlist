# C_RULE_FUNNEL_STRICTNESS_AUDIT_V1 — outcome-blind protocol

Research question / STRICT PATH. Date: 2026-11-04 (Asia/Shanghai).

## Question, materiality and stop

Why are recent C candidates scarce: MARKET_SCARCITY, RULE_STRICTNESS, or both?
The product decision is whether to authorize a separate, bounded historical study
of one or two local conditions. This audit cannot authorize changing production.
No outcome, return, MFE/MAE, MODEL_P/MODEL_R result or sealed Final OOS is an input.

Primary input: latest 40 distinct real C report dates at or before 2026-11-04
from pinned runtime-state `ebe014748cfd3a551b0e3589124e08b2c154871d`.
Use all available dates if fewer than 40; report coverage honestly if fewer than
20. Deduplicate the dated alias and immutable version; a version is not a new
trading day. Verify exact manifest/version equality and HTML SHA before counting.
Report these as genuine runtime research outputs, not verified prospective
captures (`prospective_captured=false`). Source master is
`334f636a98c17d31c3f3251b8ce3d3859132c3b7` (#104 merged; exact-head CI success).

For full F0–F8 use original T-bound C observation records and/or B frozen input
packages, with T-known non-ST main-board identity and pre-T pivot confirmation.
Do not refetch current data or reconstruct from subsequent snapshots. Historical
reconstruction, if used, must be a separate cohort with its own limitations.
No secondary cohort is required to substitute for missing Primary evidence.

Intake identifies a likely evidence gap: public C manifests/HTML retain final
matches, not rejected stocks; runner inputs are ephemeral. If original inputs
cannot be recovered from existing project sources, finish the verifiable
frequency audit and selected-match diagnostics, mark the full funnel, margins,
near misses, causal decomposition and sensitivity `NOT_RUN_INPUTS_UNAVAILABLE`
with null counts. Do not infer the rejected population from selected matches.
Stop with NEEDS_MORE_EVIDENCE and specify exactly the evidence needed. This does
not block existing Formal B/C daily operation.

## Estimands and stages

Count stock-date matches (union of rules) separately from distinct symbols and
rule-date matches. Daily average and zero-day rate use successful C runs only;
pending/failed/unrun records are not zero candidates. Show all statuses/gaps.
Show rule-positive date frequency and match events / B evaluated stock-dates
as a labelled proxy; exact C eligible-stock hit rate is null unless recoverable.
The aggregate `c_st_or_rule_excluded` is not a distinct-symbol count: current
adapter can append a verified ST symbol twice. Other exclusions overlap and
history-prefix gaps bypass the identity checks. Do not subtract these aggregates
to manufacture a C eligible denominator. Compare first/last ten available dates
and the user's 2026-10-08..2026-11-03 expectation interval; avoid a long-run trend
claim from a short, irregular observed series.

For both frozen rules the intended sequential funnel is F0 eligible universe;
F1 sufficient history (including adapter minimum 90 bars, even for Balanced);
F2 four trend conditions; F3 confirmed pivot lows, distinct higher lows,
separation, pre-pullback peak; F4 recent peak and depth; F5 confirmed rebound
high and rebound-size range; F6 four T confirmation conditions; F7 intact close
support; F8 final price entry candidate. Give overlapping single failures and
joint pass counts separately from sequential attrition.

F3–F5 operate on candidate pairs in frozen enumeration order: later pairs can
rescue earlier failures. Per-pair failures must not be called stock failures;
full reconstruction must reproduce the canonical selected pair and match.
`PULLBACK_DEPTH_OUTSIDE_CANDIDATE` also covers over-age peaks and
`NO_CONFIRMED_REBOUND_HIGH` also covers out-of-range rebound size. Neither
status alone identifies its numeric cause. Support tolerance is DISPLAY_ONLY;
resistance tolerance is diagnostic, neither changes entry qualification.

F2 fields: close>fast, fast>slow, slope>0, up-close fraction. F6 fields:
close>rebound high, close>previous close, positive body, close location>=0.60.
Count exactly one/two missing confirmation tests, all four pass, and null for
conditions not evaluated. F7 distinguishes pullback/T close breaks from
recovered intraday punctures. Volume is observation/diagnostic, not an entry gate.

NEAR_MISS requires that all other final gates pass and exactly one specified
local condition fails. Numeric margins require full-precision original values;
two-decimal HTML values are unsuitable. For pivot radius/separation a genuine
one-field counterfactual reconstruction is required. Never label an unmatched
rule near-miss solely from its printed aggregate failure status.

## Optional candidate-count sensitivity

Only if full Primary inputs are recovered: rank bottlenecks by sequential
attrition, select up to three (fixed tie order: trend, pivot, depth, rebound,
confirmation), and apply a single predeclared local change independently.
Candidate changes: up-close minimum -0.02; depth maximum +0.02; rebound maximum
+0.02; remove positive-body condition; close-location minimum -0.05; pivot
radius -1 (minimum 1), or minimum separation -1. No combination, grid, outcome
optimization or best threshold. Count additions AND losses (pivot changes may
reselect pairs), union candidates and positive-date coverage. These are
`CANDIDATE_COUNT_SENSITIVITY_ONLY`, never production recommendations.
Without those inputs all sensitivity values remain null, not zero.

## Decisions and boundaries

Overall choose only C_RECENT_SCARCITY_PRIMARILY_MARKET_DRIVEN,
C_RECENT_SCARCITY_PRIMARILY_RULE_STRICTNESS_DRIVEN,
C_RECENT_SCARCITY_MIXED_MARKET_AND_RULE_EFFECT, or
C_SCARCITY_CAUSE_NEEDS_MORE_EVIDENCE. Conservative choose only
C_CONSERVATIVE_B_REMAINS_PLAUSIBLY_USEFUL,
C_CONSERVATIVE_B_APPEARS_OVERSTRICT_FOR_CURRENT_USE, or
C_CONSERVATIVE_B_STRICTNESS_NEEDS_MORE_EVIDENCE. Unknown causes stay unknown.
Conditional Conservative diagnostics within Balanced matches are descriptive
and selection-biased, not the whole-market counterfactual funnel.

Future B/C product direction: eligibility → structure state → independent
evidence → priority/explanation; no Score, weighted sum, points or new numeric
composite. Qualification and any future priority research remain separate.
This prospective direction does not modify existing Formal B behavior or
retroactively reinterpret #104's research-only prototype.

Change scope: this protocol, independent audit script/tests/artifacts/report and
minimal existing governance updates. Frozen C rules, Formal B, production
renderer, provider, scheduler, runtime-state and frozen studies unchanged.
No deployment, dispatch, provider write/read acquisition, merge or OOS access.
Verify focused tests, full pytest, compileall, diff boundary/check and deterministic
rerun/hash equality. Push independent branch; create Draft PR against live
master; read exact-head CI and mergeability. Stop at
`C_RULE_FUNNEL_STRICTNESS_AUDIT_READY_FOR_USER_DECISION`, with any evidence gap
explicitly retained. No automatic follow-on study.
