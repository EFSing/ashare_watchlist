# CURRENT STATUS

更新时间：2026-08-29（Asia/Shanghai）
正式基线：`master@7a27484293cbcb791c6b8407949e9e71257e016b`（PR #9 squash merge）
正式 Delivery Ladder：`research`
职责：记录项目正式处于什么状态，以及哪些研究结论已经成立。长期产品目标和 usable gate 见 [`PRODUCT_CHARTER.md`](PRODUCT_CHARTER.md)，接手动作见 [`HANDOFF.md`](../HANDOFF.md)，决策理由见 [`DECISION_LOG.md`](DECISION_LOG.md)。

## Formal project status

项目当前正式处于 Phase 2E 完成后的 `research` 层，带有 development harness 和可运行的 manual review utility，但尚未达到 development candidate / frozen candidate，更不是 production strategy promotion 状态。PR #1–#9 已 squash merge；当前无 active PR（`PR: NONE`）。

- Phase 2A：legacy strategy audit 完成；缺失历史 provenance 的部分保持 `UNKNOWN_ORIGIN` / `NOT_REPRODUCIBLE_WITH_CURRENT_DATA`。
- Phase 2B：generation input/timing contract 已冻结：仅 T 日收盘、`Asia/Shanghai`、XSHG T+1、`exchange-calendars==4.13.2`。
- Phase 2C：`A_PLATFORM_BREAKOUT_LEGACY_V1` 已恢复为可审计 evaluator，但仍是 research baseline，不是生产规则。
- Phase 2D：PIT validation protocol 已冻结；任何输入必须证明 `known_at <= T`，当前值不能回填历史。
- Phase 2E：HiThink CORE replay、continuous replay 和 adjusted DEVELOPMENT returns V2 已提交并合并到 master（PR #6）。

## Product readiness

- 已有：canonical watchlist schema、盘前/盘后复核、表现追踪、持仓/配对工具；Phase 2B 的 T close / XSHG T+1 contract；Phase 2D PIT contract；Phase 2E CORE / DEVELOPMENT artifacts、registry、hash 和 recovery governance。
- 尚未达到 usable：没有被正式证明的 frozen daily strategy candidate 及端到端每日 generation → canonical watchlist output → explicit failure → monitoring/rollback 闭环；因此当前不是 prospective/paper observation 或 usable watchlist version。
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
- `A_PLATFORM_BREAKOUT_LEGACY_V1` 没有 production promotion；未做参数选择、调参或 Final OOS read。
- 本机 Phase 2F diagnostic commit `3eeb5df9f7cf4ef5c30b3380b323f26f2491f873` 尚未 push、无 PR、无 CI；它是 local candidate work，不改变 formal master status。
- Phase 2F local diagnostic 的研究边界保持不变：它没有修改 legacy strategy、冻结阈值或 Final OOS；其退出 decision 为 `NEEDS_MORE_EVIDENCE`，不能直接形成 production threshold 或 promotion。

## Production boundary

生产 ingest/review 的 canonical watchlist schema 和 `ASHARE_DATA_ROOT` 路径约定保持不变。Phase 2E CORE / returns harness 与生产 review 路径分离，不写 canonical watchlist，不改变 `perf_tracker`，不接 scheduler，也不代表可直接交易。

## Current blockers and deferred items

1. **P1 product blocker — end-to-end usable path**：需要把明确版本的策略候选接到确定性的每日执行、canonical watchlist 输出、显式 data failure、monitoring/rollback/versioning；当前仓库尚未证明这一完整路径。
2. **Scope-local correctness blocker — FULL legacy only**：历史新浪行业 membership / effective-date evidence 缺失，阻止 `FULL_LEGACY_OUTPUT_VALIDATION`、完整 85-score parity 和 legacy sector report；它不阻止 CORE research 或 prospective product progression，不能写成整个系统 blocker。
3. **Scope-local provenance limitation**：retrospective official dump 没有 per-bar historical vintage timestamp，限制历史 known-at 结论的强度；live prospective inputs 仍必须按 T 的 observed-at contract 处理。

已解决：`daily_k.parquet` recovery evidence 与 registry exact SHA 匹配，状态为 `FULLY_RECOVERABLE`。

Deferred（当前不阻止 usable milestone）：Phase 2F 后续 Research V2、历史新浪 membership acquisition 的完整研究、完整 legacy 85-score parity、任何参数选择/调参、performance-based rule change，以及 later production hardening 中不影响 P0/P1 的运营增强。

## Phase 2F product rationale and exit decision

Phase 2E V2 的 DEVELOPMENT returns 是描述性、`RECONSTRUCTED_RETROSPECTIVE`、非 promotion 证据；Phase 2F 值得做，是因为它能在不改策略/阈值的前提下回答当前候选的失败结构是否足以拒绝候选，或是否值得另立一个预注册、范围受限的 research protocol。local-only Phase 2F diagnostic 已给出边界内画像，但未证明稳定可迁移 edge。

**Decision：`NEEDS_MORE_EVIDENCE`。** 不 adopt 当前诊断为 production rule，不自动启动 Research V2；若未来要继续，只能先定义 materiality、预注册比较和 exit gate。该 decision 不阻止当前 product path 的 development work，也不授权读取 Final OOS。

## Current next action

先完成 usable path 的产品设计/开发候选入口和其 fail-closed、版本、监控/回滚 gate；不要启动 Phase 2F，不读 Final OOS，不修改策略、数据或 Phase 2F 结果。
