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
OOS。当前精确定义的 A legacy V1 不进入 prospective/frozen candidate：

`REJECT_A_PLATFORM_BREAKOUT_LEGACY_V1_AS_FROZEN_CANDIDATE`

A 保留为 research baseline / regression witness；该 decision 不外推为平台突破
思想、所有 A 类未来版本或 Research V2 无效。

## 3. 有限 candidate inventory

固定 V0 来源：`EFSing/ashare_watchlist-V0` commit
`c8406c393c0b135eafb0aec763576ae869fddcff`，文件
`ashare_watchlist/scripts/screen_system.py`，SHA-256
`6cac746123e315199cbeeb1a612868ef77b50af6c7c64b0d80eb387ae1d19f9`；机器可读
canonical identity 见候选 spec。

| candidate family | exact V0 rule | unknown core origin | Phase 2B input | current-data backfill | immutable spec/SHA | engineering disposition |
| --- | --- | --- | --- | --- | --- | --- |
| `A_PLATFORM_BREAKOUT_LEGACY_V1` | complete and already audited | no new unknown; V2 evidence is retrospective | compatible | no | existing SHA `7ce0bf…` | reject as frozen candidate; retain baseline |
| `B_BREAKOUT_RETEST_LEGACY_V1` | complete: first qualifying breakout in 15-session scan, exact pullback/volume/strength gates | none in core formula | compatible | no | `5bbeb345…` | nominated and eligible under fixed gate |
| `C_MAIN_TREND_RETEST_LEGACY_V1` | complete: exact 60-session peak/run-up/drawdown, Fib/MA20, pullback-volume and MA5 gates | none in core formula | compatible | no | fixed V0 mapping | inventory only; not evaluated |
| `D_OVERSOLD_RIGHT_SIDE` | fixed V0 code says removed; no executable formula | `UNKNOWN_ORIGIN` | not reproducible | would require guessing | no | excluded |
| old generic `watchlist_history.type` families | outputs have no generator/version/rule mapping | `UNKNOWN_ORIGIN` | not reproducible | would require guessing | no | excluded |

No wave, Fibonacci, QQQ, SETUP_03, or other-project rule was added. No B/C returns
were compared before nomination. No C evaluation follows the B decision.

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
“research B first”; it is not a predictive ranking. B has the lower complexity, so the
only nomination is:

`NOMINATE_B_BREAKOUT_RETEST_LEGACY_V1_FOR_DEVELOPMENT_ELIGIBILITY`

## 5. Candidate-bound reconstruction identity

The nominated research-only implementation is
`B_BREAKOUT_RETEST_LEGACY_V1` in `scripts/b_breakout_retest.py`.

- V0 source commit: `c8406c393c0b135eafb0aec763576ae869fddcff`
- V0 source file SHA-256: `6cac746123e315199cbeeb1a612868ef77b50af6c7c64b0d80eb387ae1d19f9`
- canonical strategy spec SHA-256:
  `5bbeb345ebd8883149138d2f29f8606f919949ae285aa2839fa337921dfc7112`
- role: `RESEARCH_ONLY_LEGACY_CANDIDATE_RECONSTRUCTION`
- timing: signal at T close; execution remains T+1 XSHG open

Exact reconstruction, semantic hash, edge behavior, numeric projection and parity
tests passed. The V0 unconditional `break` after the first qualifying breakout is
preserved, including when its later pullback checks fail.

## 6. Frozen eligibility protocol

The one-time protocol is `STRATEGY_DEVELOPMENT_ELIGIBILITY_V1`. It is fixed before
reading B returns and is not result-dependent:

`ELIGIBILITY_RULE_FROZEN_BEFORE_B_RETURNS_READ = true`

| Threshold | Frozen value |
| --- | ---: |
| minimum_total_event_count | 30 |
| minimum_available_events_per_horizon | 30 |
| primary_horizon | 10D |
| 10D positive rate | >= 50% |
| 10D mean return | > 0 |
| 10D median return | > 0 |
| robust years | >= 3 with >= 10 events each |
| positive robust-year means | >= 2 |

No threshold may be changed because a result is close to or beyond a gate. The
protocol permits exactly one fixed B replay. It forbids rule changes, parameter or
threshold sweeps, TOP-N optimization, Phase 2F, C returns, Final OOS, and promotion.

## 7. Fixed B eligibility result

The earlier environment stop is correctly named:

- `CANDIDATE_ELIGIBILITY_BLOCKED_ENVIRONMENT`
- `B_ELIGIBILITY_NOT_EXECUTED_MISSING_PARQUET_READER`

After installing the declared `research` extra, the same single B replay completed in
Python 3.12.13 / pandas 2.2.3 / pyarrow 17.0.0. The result is:

`CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES`

Event N is 17,714. Available events are 17,689 / 17,635 / 17,602 / 17,558 for 1D /
3D / 5D / 10D. Primary 10D results are positive rate 51.6403%, mean return +1.4603%,
and median return +0.3226%. Robust 10D years are 2023–2026 (4 total); 2024 and 2025
have positive means (2 total). Signal concentration is low: 4,454 unique symbols,
top-1 share 0.1186%, top-5 share 0.5758%, HHI 0.00035472.

The complete metrics, gate table, input verification, and artifact hashes are in
[`strategy_candidate_eligibility_report.md`](strategy_candidate_eligibility_report.md).

## 8. Candidate-bound prospective contract and stop

Because B passed the fixed eligibility gates, the contract is defined in
[`candidate_bound_prospective_input_contract_v1.md`](candidate_bound_prospective_input_contract_v1.md).
It binds B strategy version/spec SHA, T close/T+1, universe, sector semantics, names,
market_env, provider/version, calendar, availability/fail-closed, recovery and
generation fingerprint/output identity.

No prospective live instance has been fabricated. Rejudged
`FROZEN_CANDIDATE_PREREQUISITES` remains:

- decision: `FROZEN_CANDIDATE_BLOCKED`;
- sole P1: `P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE`;
- waiting for the first real candidate-bound `LIVE_OBSERVED` T-close package with
  `known_at <= T`;
- `FROZEN_CANDIDATE_CONTRACT_V1` is not created;
- Formal Delivery Ladder remains `development candidate`.

If B had failed any fixed gate, the decision would have been `CANDIDATE_REJECTED` and
the nomination work would have stopped. The observed result passed, so no C returns
evaluation follows; the next action is only the first real prospective package and
its fail-closed audit.
