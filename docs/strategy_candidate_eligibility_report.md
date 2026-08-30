# Strategy Candidate Nomination / Development Eligibility V1 Report

Date: 2026-08-30 (Asia/Shanghai)  
Formal Delivery Ladder: `development candidate`  
Protocol: `STRATEGY_DEVELOPMENT_ELIGIBILITY_V1`

## Final decision

`NO_REPRODUCIBLE_STRATEGY_CANDIDATE`

The engineering nomination was uniquely fixed before any B/C development return was
read:

`NOMINATE_B_BREAKOUT_RETEST_LEGACY_V1_FOR_DEVELOPMENT_ELIGIBILITY`

B was nominated because its exact V0 provenance is complete, it has no
correctness-critical `UNKNOWN_ORIGIN`, it uses the frozen/recoverable Phase 2B input
contract, requires no current-data backfill, remains compatible with T-close/T+1
execution, and has lower implementation/inference complexity than C. The fixed legacy
tie-break is B → C; it is a deterministic research order, not a predictive ranking.

The fixed eligibility evaluation could not read the frozen DEVELOPMENT parquet input in
this environment. It stopped before producing events or metrics. Consequently this
report does not call B eligible or rejected on performance, and it does not start a
second candidate evaluation.

## A legacy disposition

The current exact A legacy V1 is formally rejected as a frozen candidate:

`REJECT_A_PLATFORM_BREAKOUT_LEGACY_V1_AS_FROZEN_CANDIDATE`

This uses only the already frozen Phase 2E V2 primary evidence:

| Horizon | Positive rate | Mean return |
| --- | ---: | ---: |
| 1D | 42.4594% | -0.1270% |
| 3D | 42.6095% | -0.2281% |
| 5D | 40.6703% | -0.5085% |
| 10D | 41.3134% | -0.4631% |

Evidence scope is `DEVELOPMENT` / `RECONSTRUCTED_RETROSPECTIVE`, not Final OOS.
The decision means only that the current frozen A spec is not worth entering
prospective/frozen-candidate work. A remains a research baseline and regression
witness. It does not invalidate platform-breakout research generally, future A
versions, or Research V2.

## Finite candidate inventory

| Candidate | Exact V0 provenance | Unknown-origin risk | Frozen-input compatibility | Current-data backfill | Spec/parity path | Disposition |
| --- | --- | --- | --- | --- | --- | --- |
| A platform breakout legacy V1 | complete | none for the reconstructed rule | yes | no | complete | rejected by frozen Phase 2E V2 evidence |
| B breakout-retest legacy V1 | complete | none identified | yes | no | complete | nominated; fixed eligibility blocked by environment |
| C main-trend-retest legacy V1 | complete | none identified | yes | no | complete | inventory only; not evaluated |
| D / generic old history types | incomplete or removed | `UNKNOWN_ORIGIN` / no exact mapping | not established | not established | no | excluded |

No wave, Fibonacci, QQQ, SETUP_03, or other-project rule was added. No B/C returns
were compared before nomination. No C evaluation follows the B stop.

## Exact reconstruction and provenance

Candidate: `B_BREAKOUT_RETEST_LEGACY_V1`  
Implementation: [`scripts/b_breakout_retest.py`](../scripts/b_breakout_retest.py)  
V0 source commit: `c8406c393c0b135eafb0aec763576ae869fddcff`  
V0 source file SHA-256: `6cac746123e315199cbeeb1a612868ef77b50af6c7c64b0d80eb387ae1d19f9`  
Canonical semantic spec SHA-256: `5bbeb345ebd8883149138d2f29f8606f919949ae285aa2839fa337921dfc7112`  
Role: `RESEARCH_ONLY_LEGACY_CANDIDATE_RECONSTRUCTION`

Exact reconstruction is PASS. The implementation preserves the V0 first qualifying
breakout scan and unconditional `break` even when later pullback checks fail. It
consumes the existing Phase 2B `GenerationInputManifest`; it does not modify frozen
inputs. Parity, semantic-hash mutation, edge-break, and fixed decision tests pass:

`7 passed`

## Fixed eligibility evaluation

The protocol was written before attempting the run. It permits one fixed replay only;
there is no threshold search, parameter sweep, TOP-N optimization, result-driven rule
change, Phase 2F, or Final OOS access. Signal timing is T close and execution is the
next XSHG session open.

Frozen input identity:

- dataset: `core-signal-hithink-continuous-2023-06-30-to-2026-08-28-v1`;
- fixed signal sessions: 769, 2023-06-30 through 2026-08-28;
- raw input content SHA-256: `68d10afc4a0e3341c124f8a5e896292faf8ca271ab15cfbb7ac55fe485db8ccb`;
- core projection stream SHA-256: `882b8925e787d67d7035de07f91cd3c941b7394661bd32d5d534cc62e3996c1b`;
- outcome scope: `DEVELOPMENT` / `RECONSTRUCTED_RETROSPECTIVE`;
- Final OOS: `false`.

The attempt was `NOT_EXECUTED_FAIL_CLOSED`: pandas could not open the frozen
`daily_k.parquet` because the bundled runtime has neither `pyarrow` nor
`fastparquet`. An offline-only package-cache check found no usable reader. No parquet
rows were consumed, no frozen input was rewritten, and no output event artifact or
eligibility manifest was manufactured.

| Required output | Result |
| --- | --- |
| Event N | `NOT_COMPUTED` |
| 1D positive / mean / median | `NOT_COMPUTED` |
| 3D positive / mean / median | `NOT_COMPUTED` |
| 5D positive / mean / median | `NOT_COMPUTED` |
| 10D positive / mean / median | `NOT_COMPUTED` |
| MFE / MAE | `NOT_COMPUTED` |
| Signal concentration | `NOT_COMPUTED` |
| Year robustness | `NOT_COMPUTED` |

The actual blocker is `P1-ENV-FROZEN-DATA-PARQUET-READER`. This is not a candidate
performance result. The final decision is therefore `NO_REPRODUCIBLE_STRATEGY_CANDIDATE`
for this run, rather than `CANDIDATE_REJECTED`.

## Governance and next product path

- Formal Delivery Ladder remains `development candidate`.
- No `FROZEN_CANDIDATE_CONTRACT_V1` was created.
- No candidate-bound prospective input package was created.
- No Final OOS, Phase 2F, parameter tuning, or second/third candidate evaluation was
  performed.
- Shortest next product path: restore an approved offline parquet-capable reader in
  the execution environment, rerun this same fixed B protocol without changing the
  rule or frozen inputs, then make exactly one of the three allowed candidate
  decisions. Only an eligible result may proceed to a candidate-bound prospective
  input package and a fresh `FROZEN_CANDIDATE_PREREQUISITES` gate; a performance
  rejection stops the nomination work.
