# CURRENT STATUS

更新时间：2026-08-30（Asia/Shanghai）
Formal Delivery Ladder：`development candidate`
Product-governance milestone：PR #12 squash merge `7dfb59b9f379c7d74f95c3e522fde55bcdf49ba1`；post-merge master correctness run `33268086906` success（last-verified provenance snapshot）
Phase 2E research baseline：PR #6 / `74ccf86dfdea3b9d4b0124fb54346aa429735508`
职责：记录项目正式处于什么状态，以及哪些研究结论已经成立。长期产品目标和 usable gate 见 [`PRODUCT_CHARTER.md`](PRODUCT_CHARTER.md)，接手动作见 [`HANDOFF.md`](../HANDOFF.md)，决策理由见 [`DECISION_LOG.md`](DECISION_LOG.md)。

## Formal project status

PR #12 已 squash merge，项目正式处于 `development candidate` 层。该晋级只表示
deterministic generation → canonical watchlist → fail-closed → provenance/versioning
→ monitoring/rollback 的受控产品路径已经建立，不是 strategy promotion。active PR
的最终 head、CI 和 merge state 仍属于每次 intake 的 live state；本文件中的 merge
commit 和 CI 仅是历史/last-verified provenance snapshot，不是永久 current-state
invariant。

- Phase 2A：legacy strategy audit 完成；缺失历史 provenance 的部分保持 `UNKNOWN_ORIGIN` / `NOT_REPRODUCIBLE_WITH_CURRENT_DATA`。
- Phase 2B：generation input/timing contract 已冻结：仅 T 日收盘、`Asia/Shanghai`、XSHG T+1、`exchange-calendars==4.13.2`。
- Phase 2C：`A_PLATFORM_BREAKOUT_LEGACY_V1` 仍是 research-only wiring witness；PR #12
  的 product-ladder 晋级不改变 strategy semantics，不是 production strategy。
- Phase 2D：PIT validation protocol 已冻结；任何输入必须证明 `known_at <= T`，当前值不能回填历史。
- Phase 2E：HiThink CORE replay、continuous replay 和 adjusted DEVELOPMENT returns V2 已提交并合并到 master（PR #6）。

## Product readiness

- 已有：canonical watchlist schema、盘前/盘后复核、表现追踪、持仓/配对工具；Phase 2B 的 T close / XSHG T+1 contract；Phase 2D PIT contract；Phase 2E CORE / DEVELOPMENT artifacts、registry、hash 和 recovery governance。
- PR #12 的 development-candidate path 已在受控输入上证明端到端 deterministic
  generation → canonical watchlist output → explicit failure → monitoring/rollback/
  versioning；该产品里程碑现已写入 master 的正式 Ladder。
- 当前已达到 `development candidate`，仍未达到 frozen candidate、prospective/paper
  observation 或 production strategy promotion；下一层须通过
  [`frozen_candidate_prerequisites_audit.md`](frozen_candidate_prerequisites_audit.md)。
- 进入 observation / paper-use 必须满足 [`docs/PRODUCT_CHARTER.md`](PRODUCT_CHARTER.md) 的十项 Definition of Usable；deferred research 不要求全部先完成。

## What is established

- Continuous CORE replay 覆盖 769 个连续 XSHG sessions（2023-06-30 至 2026-08-28）、4,041,140 个 candidate evaluations。
- CORE projection 只包含 A match、hard reject、support、stop、target、RR、trigger 和 signal identity；没有 score、P&L、return、MFE 或 MAE。
- DEVELOPMENT returns V2 对 8,463 个 qualified events 完成 corporate-action-adjusted outcome measurement；entry 是 T+1 open。
- V2 的正式标签是 `DEVELOPMENT` / `RECONSTRUCTED_RETROSPECTIVE`，不是 Final OOS；旧 V1 raw outcome 只保留作 diagnostic。
- signal 只使用 T 及以前数据；未来 corporate actions 只用于事后 outcome measurement。

## What is not established

- 历史新浪行业 membership / effective-date membership 仍不可得，因此 `FULL_LEGACY_OUTPUT_VALIDATION`、完整 85-score parity 和 legacy sector report 均为 `BLOCKED_HISTORICAL_SINA_MEMBERSHIP`。
- sector score/report 为 `UNVERIFIED`；不得使用当前 sector constituents、其他 taxonomy 或 current data backfill。
- retrospective official dump 没有 per-bar historical vintage timestamp；该 known-at 限制仍需在后续 validation decision 中单独接受或解决。
- `A_PLATFORM_BREAKOUT_LEGACY_V1` 没有 production promotion；没有参数有效性证明，
  未做参数选择、调参或 Final OOS read。
- 当前没有正式 nominated、经资格决策批准、值得进入 prospective/frozen gate 的
  strategy candidate；A baseline 仍只是 research-only wiring witness。
- development path 只有 READY manifest 与受控 fixture 证据，尚无 candidate-bound
  prospective input identity/provenance package；这不因 pipeline 能运行而自动通过。
- 本机 Phase 2F diagnostic commit `3eeb5df9f7cf4ef5c30b3380b323f26f2491f873` 尚未 push、无 PR、无 CI；它是 local candidate work，不改变 formal master status。
- Phase 2F local diagnostic 的研究边界保持不变：它没有修改 legacy strategy、冻结阈值或 Final OOS；其退出 decision 为 `NEEDS_MORE_EVIDENCE`，不能直接形成 production threshold 或 promotion。

## Production boundary

生产 ingest/review 的 canonical watchlist schema 和 `ASHARE_DATA_ROOT` 路径约定保持不变。Phase 2E CORE / returns harness 与生产 review 路径分离，不写 canonical watchlist，不改变 `perf_tracker`，不接 scheduler，也不代表可直接交易。

## Current blockers and deferred items

1. **P1 frozen-candidate decision blocker**：当前没有正式批准的 strategy candidate，且现有 DEVELOPMENT/retrospective evidence 不足以支持任何候选进入 prospective/frozen gate；详见审计 decision `FROZEN_CANDIDATE_BLOCKED_NO_APPROVED_STRATEGY_CANDIDATE`。
2. **P1 candidate-bound input blocker**：尚无一个候选绑定的 prospective input identity/provenance package，需证明 T close、`LIVE_OBSERVED`/known-at、universe/sector/names/market_env、provider/version、calendar、availability/recovery 和 output identity。
3. **Scope-local correctness blocker — FULL legacy only**：历史新浪行业 membership / effective-date evidence 缺失，阻止 `FULL_LEGACY_OUTPUT_VALIDATION`、完整 85-score parity 和 legacy sector report；它不阻止 development-candidate product path，也不自动阻止 frozen-candidate decision，不能写成整个系统 blocker。
4. **Scope-local provenance limitation**：retrospective official dump 没有 per-bar historical vintage timestamp，限制历史 known-at 结论的强度；live prospective inputs 仍必须按 T 的 observed-at contract 处理。

已解决：`daily_k.parquet` recovery evidence 与 registry exact SHA 匹配，状态为 `FULLY_RECOVERABLE`。

Deferred（当前不阻止 usable milestone）：Phase 2F 后续 Research V2、历史新浪 membership acquisition 的完整研究、完整 legacy 85-score parity、任何参数选择/调参、performance-based rule change，以及 later production hardening 中不影响 P0/P1 的运营增强。

## Phase 2F product rationale and exit decision

Phase 2E V2 的 DEVELOPMENT returns 是描述性、`RECONSTRUCTED_RETROSPECTIVE`、非 promotion 证据；Phase 2F 值得做，是因为它能在不改策略/阈值的前提下回答当前候选的失败结构是否足以拒绝候选，或是否值得另立一个预注册、范围受限的 research protocol。local-only Phase 2F diagnostic 已给出边界内画像，但未证明稳定可迁移 edge。

**Decision：`NEEDS_MORE_EVIDENCE`。** 不 adopt 当前诊断为 production rule，不自动启动 Research V2；若未来要继续，只能先定义 materiality、预注册比较和 exit gate。该 decision 不阻止当前 product path 的 development work，也不授权读取 Final OOS。

## Current next action

当前已在 `development candidate`。frozen-candidate prerequisites audit 的 decision
为 `FROZEN_CANDIDATE_BLOCKED`，未定义 `FROZEN_CANDIDATE_CONTRACT_V1`；下一步只
在明确的 candidate nomination/eligibility 和 candidate-bound prospective evidence
到位后回到同一 decision point。不要自动启动 Phase 2F，不调参，不读 Final OOS，
不把 product-ladder 晋级写成 strategy promotion。

## Strategy Candidate Nomination V1 — 2026-08-30

PR #13 已按 expected head `0f5629765ef0eebbae0c6981f2d7ccafab7f7e35` squash merge；
merge commit 为 `005fa552b046ee35d35f51e0c7da430a9dc17fbe`，master correctness CI
run `33295618615` 已成功。这是 last-verified provenance，不替代后续 live state 核对。

本轮先正式处置 A：
`REJECT_A_PLATFORM_BREAKOUT_LEGACY_V1_AS_FROZEN_CANDIDATE`。依据是冻结 Phase 2E V2
的 DEVELOPMENT / RECONSTRUCTED_RETROSPECTIVE primary evidence；A 保留为 research
baseline / regression witness，不外推为平台突破思想、未来 A 版本或 Research V2 无效。

有限 inventory 仅包含已有明确来源的 A、B breakout-retest、C main-trend-retest，
以及被 provenance 排除的 D / generic old history types。预先固定的 engineering
lexicographic rule 唯一提名：
`NOMINATE_B_BREAKOUT_RETEST_LEGACY_V1_FOR_DEVELOPMENT_ELIGIBILITY`。B 已完成 exact
reconstruction、canonical semantic spec、SHA-256、逐 gate 记录和 parity tests；C
没有被自动测试。

一次固定的 `STRATEGY_DEVELOPMENT_ELIGIBILITY_V1` 尝试因当前 bundled Python 缺少
`pyarrow` / `fastparquet` 且没有本地可用 parquet reader，在读取 frozen DEVELOPMENT
数据前 fail closed。因而没有 event、收益、MFE/MAE、concentration 或 year robustness
结果，也没有把 B 错误地判为 performance rejected。最终 decision 是
`NO_REPRODUCIBLE_STRATEGY_CANDIDATE`，P1 blocker 为
`P1-ENV-FROZEN-DATA-PARQUET-READER`；完整报告见
[`strategy_candidate_eligibility_report.md`](strategy_candidate_eligibility_report.md)。

Formal Delivery Ladder 仍为 `development candidate`；没有创建 frozen candidate
contract 或 candidate-bound prospective package。最短下一步是恢复批准的离线
parquet reader 后，用相同 B 规则和相同 frozen inputs 重跑一次固定 eligibility，
之后按单一 decision 停止或进入 candidate-bound prospective package。
