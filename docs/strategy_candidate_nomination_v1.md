# Strategy Candidate Nomination V1

更新时间：2026-08-30（Asia/Shanghai）

## 1. 研究问题、边界与停止条件

研究问题：在不发明新策略、不调参、不读取 Final OOS 的前提下，当前项目已有
明确 V0 provenance 的 strategy family 中，哪一个候选值得进入正式 development
eligibility 验证？

本任务只服务于 `development candidate` → frozen-candidate prerequisites 的最短
证据路径。它不改变 Formal Delivery Ladder，不是 Phase 2F，不是 Final OOS，也
不是 production promotion。

候选 inventory 只来自当前项目固定的 V0 provenance。不得加入其他项目的规则、
波浪、Fib、QQQ 或 SETUP_03；不得用 historical returns 先比较候选；不得用当前
数据回填历史。研究停止条件是：形成有限 inventory、在看 returns 前确定最多一个
候选、完成该候选的一次固定 eligibility evaluation，并写出唯一 final decision。

## 2. A legacy V1 的正式处置

对象：`A_PLATFORM_BREAKOUT_LEGACY_V1`。

唯一使用已经冻结的 Phase 2E V2 primary evidence：

| horizon | positive rate | mean return |
| --- | ---: | ---: |
| 1D | 42.4594% | -0.1270% |
| 3D | 42.6095% | -0.2281% |
| 5D | 40.6703% | -0.5085% |
| 10D | 41.3134% | -0.4631% |

该 evidence 的身份是 `DEVELOPMENT` / `RECONSTRUCTED_RETROSPECTIVE`，不是 Final
OOS。当前没有新的 correctness 证据推翻这些结果，因此正式记录：

`REJECT_A_PLATFORM_BREAKOUT_LEGACY_V1_AS_FROZEN_CANDIDATE`

该 decision 只表示当前精确定义的 A legacy V1 不值得直接进入
prospective/frozen candidate；不外推为平台突破思想、所有 A 类未来版本或
Research V2 无效。A 保留为 `research baseline / regression witness`。

## 3. 有限 candidate inventory

固定 V0 来源：`EFSing/ashare_watchlist-V0` commit
`c8406c393c0b135eafb0aec763576ae869fddcff`，文件
`ashare_watchlist/scripts/screen_system.py`，SHA-256
`6cac746123e315199cbeeb1a612868ef77b50af6c7c64b0d80eb387ae1d19f9`；机器可读
canonical identity 见下方候选 spec。

| candidate family | exact V0 rule | unknown core origin | Phase 2B input | current-data backfill | immutable spec/SHA | engineering disposition |
| --- | --- | --- | --- | --- | --- | --- |
| `A_PLATFORM_BREAKOUT_LEGACY_V1` | complete and already audited | no new unknown; V2 evidence is retrospective | compatible | no | existing SHA `7ce0bf…` | reject as frozen candidate by section 2; retain baseline |
| `B_BREAKOUT_RETEST_LEGACY_V1` | complete: first qualifying breakout in 15-session scan, exact pullback/volume/strength gates | none in core formula | compatible: stock OHLCV, quote, index, sector sentinel/record | no | yes, `5bbeb345ebd8883149138d2f29f8606f919949ae285aa2839fa337921dfc7112` | nominated |
| `C_MAIN_TREND_RETEST_LEGACY_V1` | complete: exact 60-session peak/run-up/drawdown, Fib/MA20, pullback-volume and MA5 gates | none in core formula | compatible: stock OHLCV, quote, index, sector sentinel/record | no | yes in principle from fixed V0 rule | eligible inventory, not selected because deterministic B → C tie-break |
| `D_OVERSOLD_RIGHT_SIDE` | fixed V0 code says removed; no executable formula | `UNKNOWN_ORIGIN` | not reproducible | would require guessing | no | excluded |
| old generic `watchlist_history.type` families | outputs have no generator/version/rule mapping | `UNKNOWN_ORIGIN` | not reproducible | would require guessing | no | excluded |

For B and C, “complete” means the fixed V0 source and Phase 2A audit specify every
condition and threshold required for a research implementation. It does not mean the
strategy has predictive validity.

## 4. Pre-returns nomination rule and decision

Nomination is lexicographic engineering order, evaluated before reading B/C development
returns:

1. exact legacy provenance complete;
2. no correctness-critical `UNKNOWN_ORIGIN`;
3. required data present in frozen/recoverable inputs;
4. no current-data backfill;
5. compatible with Phase 2B T-close/T+1 contract;
6. lower implementation/inference complexity.

If all six remain tied, the fixed legacy order is B → C. This tie-break means only
“research B first”; it is not a predictive ranking.

The inventory leaves B and C tied on the first five gates. B has the lower complexity:
one first-qualifying-breakout scan followed by four pullback conditions, whereas C
requires peak/run-up/drawdown and two alternative retracement tests. Therefore the
only nomination is:

`NOMINATE_B_BREAKOUT_RETEST_LEGACY_V1_FOR_DEVELOPMENT_ELIGIBILITY`

C is not evaluated for returns in this task. No second candidate is automatically
tested after the B decision.

## 5. Candidate-bound reconstruction identity

The nominated research-only implementation is
`B_BREAKOUT_RETEST_LEGACY_V1` in `scripts/b_breakout_retest.py`.

- V0 source commit: `c8406c393c0b135eafb0aec763576ae869fddcff`
- V0 source file SHA-256: `6cac746123e315199cbeeb1a612868ef77b50af6c7c64b0d80eb387ae1d19f9`
- canonical strategy spec SHA-256:
  `5bbeb345ebd8883149138d2f29f8606f919949ae285aa2839fa337921dfc7112`
- role: `RESEARCH_ONLY_LEGACY_CANDIDATE_RECONSTRUCTION`
- input: existing Phase 2B `READY_FOR_STRATEGY_EVALUATION` `GenerationInputManifest`
- timing: signal at T close; execution remains T+1 XSHG open

The implementation retains the V0 unconditional `break` after the first qualifying
breakout, including when its subsequent pullback checks fail. Independent parity tests
cover the rule, this edge behavior, semantic hash mutation, and the fast replay
projection against the manifest evaluator.

## 6. `STRATEGY_DEVELOPMENT_ELIGIBILITY_V1` (fixed before evaluation)

This is a one-time viability evaluation, not a tuning protocol. It uses the existing
frozen DEVELOPMENT data package without changing any input bytes:

- continuous CORE dataset: `core-signal-hithink-continuous-2023-06-30-to-2026-08-28-v1`;
- 769 fixed XSHG signal sessions, 2023-06-30 through 2026-08-28;
- frozen raw input content SHA:
  `68d10afc4a0e3341c124f8a5e896292faf8ca271ab15cfbb7ac55fe485db8ccb`;
- existing core projection stream SHA:
  `882b8925e787d67d7035de07f91cd3c941b7394661bd32d5d534cc62e3996c1b`;
- adjustment semantics: T-anchored price transform from the frozen corporate-action
  input, only for ex-post outcomes;
- outcome contract: T+1 XSHG session open, 1D/3D/5D/10D close returns, MFE and MAE;
- result label: `DEVELOPMENT` / `RECONSTRUCTED_RETROSPECTIVE`;
- `Final OOS`: false; future outcomes never enter signal evaluation.

### Fixed eligibility decision rule

The candidate is `CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES` only if every item below
passes:

1. exact V0 parity, semantic SHA, input/provenance and T-close/T+1 audit pass;
2. event N is at least 30 and each of the four outcome horizons has at least 30
   available events;
3. 10D adjusted primary outcome has positive rate at least 50%, mean return above 0,
   and median return above 0;
4. year robustness has at least three signal years with at least 10 available 10D
   events each, and at least two of those years have positive 10D mean return.

Otherwise the single final decision is `CANDIDATE_REJECTED`, with the failed fixed
gate(s) recorded. The four horizons, MFE/MAE, concentration and year robustness are
reported regardless of the outcome. No threshold search, parameter sweep, TOP-N
optimization, post-result rule change, Phase 2F, or Final OOS is allowed.

## 7. Result and stopping record

The one fixed eligibility attempt was made with the frozen DEVELOPMENT input package
and stopped fail-closed before reading any parquet rows. The bundled runtime has no
`pyarrow` or `fastparquet`, and no local parquet-capable reader was available. The
offline-only check for a cached reader also found none. Therefore no event artifact
was emitted and no return statistic is asserted.

- nominated candidate: `B_BREAKOUT_RETEST_LEGACY_V1`;
- exact reconstruction/parity: PASS (`7` focused tests);
- fixed protocol: `STRATEGY_DEVELOPMENT_ELIGIBILITY_V1`;
- evaluation status: `NOT_EXECUTED_FAIL_CLOSED`;
- event N and all requested return/concentration/year metrics: `NOT_COMPUTED`;
- final decision: `NO_REPRODUCIBLE_STRATEGY_CANDIDATE`;
- blocker: `P1-ENV-FROZEN-DATA-PARQUET-READER`.

This is an execution-environment reproducibility blocker, not a performance rejection
of B and not evidence against C. C is not evaluated automatically. The complete
stopping record is in
[`strategy_candidate_eligibility_report.md`](strategy_candidate_eligibility_report.md).
