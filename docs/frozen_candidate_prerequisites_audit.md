# Frozen Candidate Prerequisites Audit V1

更新时间：2026-08-30（Asia/Shanghai）

## 1. 研究问题、范围与停止条件

研究问题：在 development eligibility 已完成后，当前项目是否已经具备一个可以
进入 frozen candidate gate 的真实 strategy candidate？

materiality：这个判断决定项目能否从 `development candidate` 进入下一层。它不是
对 A 股收益、参数或新 research hypothesis 的扩展研究，也不授权读取 Final OOS、
Phase 2F、调参或 strategy promotion。

输入证据：[`PRODUCT_CHARTER.md`](PRODUCT_CHARTER.md)、
[`generation_input_contract.md`](generation_input_contract.md)、
[`development_candidate_contract.md`](development_candidate_contract.md)、
[`strategy_candidate_nomination_v1.md`](strategy_candidate_nomination_v1.md)、
[`strategy_candidate_eligibility_report.md`](strategy_candidate_eligibility_report.md)、
[`candidate_bound_prospective_input_contract_v1.md`](candidate_bound_prospective_input_contract_v1.md)、
[`FROZEN_ARTIFACT_POLICY.md`](FROZEN_ARTIFACT_POLICY.md)、
[`data/governance/frozen_artifacts.json`](../data/governance/frozen_artifacts.json) 和
PR #12 的 development-candidate regression evidence。

停止条件：一旦候选资格和当前最小 prerequisites 缺口可以判断，不继续切分指标、
优化参数或扩大 research scope。

## 2. Decision

**`FROZEN_CANDIDATE_BLOCKED`**

唯一剩余阻塞原因：

**`P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE`**

B 已经通过冻结的 `STRATEGY_DEVELOPMENT_ELIGIBILITY_V1`，因此它是获资格进入
prerequisites 的 candidate；但尚未出现首个真实 candidate-bound、
`LIVE_OBSERVED`、`known_at <= T` 的 prospective T-close input instance。不能用
retrospective DEVELOPMENT artifact 或 contract 文档替代该 instance。

因此本审计仍不创建也不宣称满足 `FROZEN_CANDIDATE_CONTRACT_V1`。已定义的
`CANDIDATE_BOUND_PROSPECTIVE_INPUT_PROVENANCE_CONTRACT_V1` 只是下一次真实输入的
验收 contract，不是已发生的 prospective evidence。

## 3. Product infrastructure audit

下表的 PASS 只表示既有 development product path 已有受控证据；它不等价于
production readiness。

| prerequisite | 结论 | 证据与边界 |
| --- | --- | --- |
| deterministic generation | `PASS`（development scope） | PR #12 的 deterministic generation、canonical output、immutable version 与 output identity 回归。 |
| canonical output | `PASS`（development scope） | schema-valid watchlist、zero-candidate success、downstream ingest 回归已覆盖。 |
| complete generation identity | `PASS`（development scope） | fingerprint 覆盖 contract/schema、strategy identity、实际 names、canonical market_env 和 output-affecting inputs。 |
| fail-closed | `PASS`（development scope） | READY、evaluator failure、缺名字、非法/冲突输出和 write failure 均有明确失败路径。 |
| monitoring / rollback | `PASS`（development scope） | schema、output SHA、immutable provenance、known-good rollback 与 HEALTHY monitor 有回归。 |
| T close / T+1 | `PASS`（contract scope） | `Asia/Shanghai`、XSHG session close、下一交易日 T+1 和错误时 fail closed 已冻结；B 的真实 prospective instance 尚未发生。 |
| artifact recovery | `PASS`（现有 artifact scope） | Phase 2E registry required artifacts hash/recovery 已核对；daily_k 为 `FULLY_RECOVERABLE`。 |

结论：产品基础支持 `development candidate`，B 的 eligibility 也已通过，但 frozen
candidate 仍需要首个真实候选绑定的 prospective input instance。

## 4. Strategy candidate eligibility audit

### 4.1 Nomination and reconstruction

唯一 nomination：
`NOMINATE_B_BREAKOUT_RETEST_LEGACY_V1_FOR_DEVELOPMENT_ELIGIBILITY`。

B exact reconstruction、V0 parity、edge behavior、semantic spec SHA 和 numeric
projection parity 均 PASS。B spec SHA 为
`5bbeb345ebd8883149138d2f29f8606f919949ae285aa2839fa337921dfc7112`。A 仍为
`REJECT_A_PLATFORM_BREAKOUT_LEGACY_V1_AS_FROZEN_CANDIDATE`；C 未被评估。

### 4.2 Fixed eligibility decision

`STRATEGY_DEVELOPMENT_ELIGIBILITY_V1` 的 thresholds 在读取 B returns 之前已经冻结：

`ELIGIBILITY_RULE_FROZEN_BEFORE_B_RETURNS_READ = true`

Python 3.12.13 / pandas 2.2.3 / `pyarrow==17.0.0` 的单次 replay 结果为：

- Event N：`17,714`；available N 1D/3D/5D/10D：`17,689` / `17,635` / `17,602` / `17,558`；
- 10D positive rate / mean / median：`51.6403%` / `+1.4603%` / `+0.3226%`；
- robust 10D years：4；positive-mean robust years：2（2024、2025）；
- fixed gates：全部 PASS；
- final decision：`CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES`。

详细 1D/3D/5D/10D MFE/MAE、concentration、year robustness、input verification 和
event/manifest SHA 见 [`strategy_candidate_eligibility_report.md`](strategy_candidate_eligibility_report.md)。

### 4.3 Boundaries retained

- B 仍是 research/development candidate，不是 production strategy；
- 该 eligibility 不是 parameter validation、调参或 Final OOS；
- 不自动评估 C，不启动 Phase 2F，不创建 TOP-N 或 promotion path；
- retrospective output 仍标记 `DEVELOPMENT` / `RECONSTRUCTED_RETROSPECTIVE`。

## 5. Candidate-bound prospective input contract

Contract：[`candidate_bound_prospective_input_contract_v1.md`](candidate_bound_prospective_input_contract_v1.md)。
它绑定：

- B strategy version/spec SHA 与 eligibility protocol；
- T close / T+1；
- exact universe、sector semantics、names、market_env；
- provider/version、calendar；
- availability、fail-closed、recovery；
- generation fingerprint 与 canonical output identity。

contract 当前状态为 `CONTRACT_DEFINED_NO_LIVE_INSTANCE`。没有伪造 T、payload、
prospective output 或 live observation。

## 6. Minimum P0 / P1

### P0

本轮没有发现新的全局 P0 correctness/safety defect。PIT、T close/T+1、fail-closed、
identity/hash 规则在受控 path 上保持明确；历史新浪 membership 缺失仍只限制
FULL legacy retrospective scope。

### P1

1. **`P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE`**：等待首个真实、候选绑定、
   `LIVE_OBSERVED` 的 T-close package，并验证 `known_at <= T`、universe/sector/
   names/market_env、provider/version、calendar、availability/recovery 和 output
   identity。它是当前唯一剩余 frozen-candidate prerequisite P1。

不需要先建设 scheduler、broker、自动交易或复杂告警。历史新浪 membership 仍是
FULL legacy validation 的 scope-local blocker，不升级为全局或 B eligibility blocker。

## 7. Next decision, deferred research and shortest product path

下一步只等待并审计首个真实 prospective package；package 通过后回到
`FROZEN_CANDIDATE_PREREQUISITES` decision point。若 package 缺失、陈旧、冲突、
不可恢复、时间语义不符或 identity 不一致，必须 fail closed。

可以 DEFER：Phase 2F/Research V2、参数选择和调参、performance-based rule change、
完整 legacy 85-score parity、历史新浪 membership acquisition、scheduler、broker、
自动交易、复杂告警和不影响 P0/P1 的 later production hardening。

当前不创建 `FROZEN_CANDIDATE_CONTRACT_V1`，不把 development eligibility 写成
strategy promotion，不读取 Final OOS，也不自动测试 C。
