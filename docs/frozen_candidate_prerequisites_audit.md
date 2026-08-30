# Frozen Candidate Prerequisites Audit V1

更新时间：2026-08-30（Asia/Shanghai）

## 1. 研究问题、范围与停止条件

研究问题：当前项目是否已经具备一个可以进入 frozen candidate gate 的真实
strategy candidate？

materiality：这个判断决定项目能否从 `development candidate` 进入下一层。它
不是对 A 股收益、参数或新 research hypothesis 的扩展研究，也不授权读取
Final OOS、Phase 2F、调参或 strategy promotion。

输入证据：[`PRODUCT_CHARTER.md`](PRODUCT_CHARTER.md) 的 Definition of Usable
和 Delivery Ladder；[`generation_input_contract.md`](generation_input_contract.md)；
[`development_candidate_contract.md`](development_candidate_contract.md)；
`A_PLATFORM_BREAKOUT_LEGACY_V1` 的 strategy spec 和现有 Phase 2D/2E
provenance；[`FROZEN_ARTIFACT_POLICY.md`](FROZEN_ARTIFACT_POLICY.md)；
[`data/governance/frozen_artifacts.json`](../data/governance/frozen_artifacts.json)；
PR #12 已合并后的 development-candidate regression evidence。

停止条件：只审计冻结候选真正需要的 correctness、identity、data/provenance 和
最小 operational controls；一旦能判断候选资格，不继续切分指标、优化参数或
扩大 research scope。

## 2. Decision

**`FROZEN_CANDIDATE_BLOCKED`**

阻塞原因：

**`FROZEN_CANDIDATE_BLOCKED_NO_APPROVED_STRATEGY_CANDIDATE`**

当前不存在正式 nominated、经资格决策批准、值得进入 prospective/frozen
candidate gate 的 strategy candidate。不得因为 `A_PLATFORM_BREAKOUT_LEGACY_V1`
能跑通 development harness，就把它默认晋级为 frozen candidate。

因此本审计**不创建也不宣称满足** `FROZEN_CANDIDATE_CONTRACT_V1`。该 contract
只有在候选资格通过后，作为下一 decision 的 gate 定义工作，不能反向补足当前
缺失的候选资格。

## 3. Product infrastructure audit

下表的 PASS 只表示既有 development product path 已有受控证据；它不等价于
strategy candidate eligibility，也不等价于 production readiness。

| prerequisite | 结论 | 证据与边界 |
| --- | --- | --- |
| deterministic generation | `PASS`（development scope） | PR #12 的 `DevelopmentCandidateStore.generate()` 对同一完整 identity 产生相同 bytes；重复运行保持 output SHA 和 immutable version。当前输入范围仍是 READY manifest 与受控 fixture。 |
| canonical output | `PASS`（development scope） | schema-valid `watchlist_YYYYMMDD.json`、`candidates`/`trigger` 和 downstream ingest 回归已覆盖；zero-candidate 是 `SUCCESS` + `NO_CANDIDATES`，不是失败伪装。 |
| complete generation identity | `PASS`（development scope） | `generation_fingerprint` 覆盖 Phase 2B `input_fingerprint`、contract/schema version、strategy identity、实际 display names、canonical `market_env` 和辅助输入；run manifest 同时保存 input/output identity。 |
| fail-closed | `PASS`（development scope） | READY 状态、evaluator failure、缺名字、非法/冲突输出和 write failure 都不产出或覆盖 canonical output，并写机器可读 failure provenance。 |
| monitoring / rollback | `PASS`（development scope） | monitor 校验 schema、output SHA 和 immutable generation provenance；known-good version 可以按完整 fingerprint rollback 并再次校验为 `HEALTHY`。 |
| T close / T+1 | `PASS`（contract scope） | Phase 2B 要求 `Asia/Shanghai`、XSHG 正式 session close 后生成，最早执行为真实下一交易日 T+1；盘中、历史 replay 和日历错误 fail closed。尚未证明某个 nominated candidate 的真实 prospective run。 |
| artifact recovery | `PASS`（现有 artifact scope） | registry 中正式 Phase 2E artifacts 已做 content/file SHA 与 recovery 记录；`daily_k.parquet` 为 `FULLY_RECOVERABLE`。Phase 2F local-only diagnostics 不属于 frozen-candidate evidence。 |

结论：产品基础已经足够支持 `development candidate`，但这些证据只证明管线
可控，不能提供“哪个 strategy 值得冻结”的决策。

## 4. Strategy candidate eligibility audit

### 4.1 正式 nomination

结论：`BLOCKED`。仓库有 strategy spec identity，但没有正式 nominated strategy
candidate 的批准记录、candidate scope 和资格 decision。当前正式记录明确：
`A_PLATFORM_BREAKOUT_LEGACY_V1` 是 research-only wiring witness。

### 4.2 Semantic identity

结论：`PARTIAL_UNVERIFIED`。`A_PLATFORM_BREAKOUT_LEGACY_V1` 有可复核的
`STRATEGY_SPEC_SHA256`：

`7ce0bf660e3ae685405e01fb9d1ef8e27e7dec44a201ab290da5d8fa8079068d`

Phase 2D protocol 也有固定 semantic SHA，依赖版本和 T close/T+1 contract
已记录。但“identity 可 hash”只说明对象可辨认，不说明该对象已经获得 frozen
candidate eligibility；不能把 hash 的存在写成 nomination 或 promotion。

### 4.3 Development evidence

结论：`INSUFFICIENT_DATA` / `BLOCKED`。现有 evidence 是 CORE signal replay 和
`DEVELOPMENT` / `RECONSTRUCTED_RETROSPECTIVE` outcome measurement；sector
score/report 仍 `UNVERIFIED`，完整 legacy 85-score output 仍因历史新浪
membership 缺失而 blocked。Phase 2F local diagnostic 的退出 decision 是
`NEEDS_MORE_EVIDENCE`，没有形成稳定 edge、参数有效性或 production rule。

因此当前 evidence 不足以支持“值得进入 prospective/frozen candidate”的
资格判断。缺口是一个候选资格 decision package，不是“再优化更多指标”。

### 4.4 明确保持的边界

在本审计结束时，`A_PLATFORM_BREAKOUT_LEGACY_V1` 仍同时是：

- research-only wiring witness / research baseline；
- 不是 production strategy；
- 不是 frozen strategy candidate；
- 不是 parameter validation，也不授权调参；
- 不是 Final OOS；
- 不是 paper/live promotion。

## 5. Data and provenance prerequisites

| prerequisite | 结论 | 审计判断 |
| --- | --- | --- |
| prospective live input known-at semantics | `PARTIAL_UNVERIFIED` | Phase 2B 已定义 `LIVE_OBSERVED`、T 日 retrieved-at、正式 session close 和 `known_at <= T` 约束；但 PR #12 只证明 READY manifest/受控 fixture，没有候选绑定的真实 prospective input instance。 |
| universe / sector / names / market_env identity | `PARTIAL_UNVERIFIED` | input manifest、generation fingerprint、display-name mapping 和 market environment 都可被记录；尚无正式 candidate package 把 universe、sector taxonomy/membership、names 与 market_env 一起批准并冻结。 |
| provider / version dependencies | `PARTIAL_UNVERIFIED` | runtime 依赖已 pin（包括 `exchange-calendars==4.13.2`），manifest 可记录 provider/version；但尚无 nominated candidate 的完整依赖闭包与数据 provider identity。 |
| calendar | `PASS`（baseline scope） | XSHG calendar、`Asia/Shanghai`、T close/T+1 和不可用时 `CALENDAR_ERROR` 已有 contract/regression evidence。 |
| data availability / recovery | `PARTIAL_UNVERIFIED` | 历史 research artifacts 的 registry recovery 已有证据；候选绑定的 prospective provider availability、缺失/陈旧/冲突处理和恢复实例尚未证明。 |
| historical Sina membership | `SCOPE-LOCAL BLOCKER` | 只阻止 `FULL_LEGACY_OUTPUT_VALIDATION`、完整 85-score parity 和 legacy sector report。它不是 development-candidate product path 或整个 frozen-candidate decision 的自动全局 blocker；不得用 current constituents、其他 taxonomy 或当前值替代。 |

## 6. Minimum P0 / P1

严重度按 frozen-candidate gate 判断，不把 deferred research 当 blocker。

### P0

本轮没有发现新的全局 P0 correctness/safety defect。已有 PIT、T close/T+1、
fail-closed、identity/hash 规则在受控 path 上是明确的；历史新浪 membership
仅在尝试 FULL legacy retrospective claim 时构成该 scope 的 correctness blocker。

### P1

1. **P1-FC-STRATEGY-NOMINATION**：没有正式批准的 strategy candidate。最小
   补充证据是一个明确 scope 的 nomination/eligibility decision，包含 immutable
   strategy/protocol/dependency identity、适用数据范围、限制说明和接受/拒绝
   结论；不能以 harness 可运行替代它。
2. **P1-FC-DEVELOPMENT-ELIGIBILITY-EVIDENCE**：没有足够的固定 development
   evidence 支持“值得进入 prospective/frozen candidate”。最小补充证据是
   对一个已提名候选应用预先写明的资格标准，并用非 Final OOS、固定且可恢复的
   evidence 给出明确 decision；不需要因此启动新 Phase、调参或读取 Final OOS。
3. **P1-FC-PROSPECTIVE-INPUT-BINDING**：没有候选绑定的 prospective input
   identity/evidence。最小补充证据是一个符合 T close/`LIVE_OBSERVED`/known-at
   contract 的 input package，明确 universe、sector、names、market_env、
   provider/version、calendar、availability/recovery 和 output identity，并
   在下一次 frozen-candidate prerequisites decision 中核验。

这三个 P1 是同一个最短 gate 所需的最小证据链，不要求先建设 scheduler、broker、
自动交易或复杂告警。

## 7. Next decision, deferred research and shortest product path

缺少的证据全部由下一次 `FROZEN_CANDIDATE_PREREQUISITES` decision 使用；不是
Phase 2F 的默认启动条件，也不是 Final OOS 的读取授权。

可以 DEFER：Phase 2F/Research V2、参数选择和调参、performance-based rule
change、完整 legacy 85-score parity、历史新浪 membership acquisition（除非未来
明确把 FULL legacy retrospective claim 纳入 candidate scope）、scheduler、broker
接入、自动交易、复杂告警和不影响 P0/P1 的 later production hardening。

最短产品路径：

1. 对一个明确 scope 的候选形成 nomination/eligibility decision；不默认提名或
   晋级 `A_PLATFORM_BREAKOUT_LEGACY_V1`。
2. 为该候选绑定最小 prospective input/provenance package，并用既有
   development path 完成一次可复核的固定验证；不改 strategy、不调参、不接
   scheduler/broker。
3. 回到同一个 prerequisites decision point。只有 P1 链条全部关闭，才定义
   `FROZEN_CANDIDATE_CONTRACT_V1`；否则保持
   `FROZEN_CANDIDATE_BLOCKED`，不伪造 contract 已满足。
