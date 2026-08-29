# CURRENT STATUS

更新时间：2026-08-30（Asia/Shanghai）
Formal Delivery Ladder：`research`（当前 master；PR #12 merge 后条件性晋级为 `development candidate`）
Product-governance milestone：PR #9 / `7a27484293cbcb791c6b8407949e9e71257e016b`；PR #12 为待 merge 的 development-candidate gate
Phase 2E research baseline：PR #6 / `74ccf86dfdea3b9d4b0124fb54346aa429735508`
职责：记录项目正式处于什么状态，以及哪些研究结论已经成立。长期产品目标和 usable gate 见 [`PRODUCT_CHARTER.md`](PRODUCT_CHARTER.md)，接手动作见 [`HANDOFF.md`](../HANDOFF.md)，决策理由见 [`DECISION_LOG.md`](DECISION_LOG.md)。

## Formal project status

项目当前 master 正式处于 Phase 2E 完成后的 `research` 层。PR #12 建立了受控的
development-candidate product path；若 PR #12 merge，正式 Delivery Ladder 才晋级
为 `development candidate`。该晋级只表示 deterministic generation → canonical
watchlist → fail-closed → provenance/versioning → monitoring/rollback 的受控产品
路径已经建立，不是 strategy promotion。active PR 的最终 head、CI 和 merge state
仍属于每次 intake 的 live state，不在本文件维护。

- Phase 2A：legacy strategy audit 完成；缺失历史 provenance 的部分保持 `UNKNOWN_ORIGIN` / `NOT_REPRODUCIBLE_WITH_CURRENT_DATA`。
- Phase 2B：generation input/timing contract 已冻结：仅 T 日收盘、`Asia/Shanghai`、XSHG T+1、`exchange-calendars==4.13.2`。
- Phase 2C：`A_PLATFORM_BREAKOUT_LEGACY_V1` 仍是 research-only wiring witness；PR #12
  的 product-ladder 晋级不改变 strategy semantics，不是生产规则。
- Phase 2D：PIT validation protocol 已冻结；任何输入必须证明 `known_at <= T`，当前值不能回填历史。
- Phase 2E：HiThink CORE replay、continuous replay 和 adjusted DEVELOPMENT returns V2 已提交并合并到 master（PR #6）。

## Product readiness

- 已有：canonical watchlist schema、盘前/盘后复核、表现追踪、持仓/配对工具；Phase 2B 的 T close / XSHG T+1 contract；Phase 2D PIT contract；Phase 2E CORE / DEVELOPMENT artifacts、registry、hash 和 recovery governance。
- PR #12 的 development-candidate path 已在受控输入上证明端到端 deterministic
  generation → canonical watchlist output → explicit failure → monitoring/rollback/
  versioning；在 PR #12 merge 前，这一产品里程碑尚未写入 master 的正式 Ladder。
- 即使 PR #12 merge，仍未达到 frozen candidate、prospective/paper observation 或
  production strategy promotion；下一层必须另行核验 frozen-candidate prerequisites。
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
- 本机 Phase 2F diagnostic commit `3eeb5df9f7cf4ef5c30b3380b323f26f2491f873` 尚未 push、无 PR、无 CI；它是 local candidate work，不改变 formal master status。
- Phase 2F local diagnostic 的研究边界保持不变：它没有修改 legacy strategy、冻结阈值或 Final OOS；其退出 decision 为 `NEEDS_MORE_EVIDENCE`，不能直接形成 production threshold 或 promotion。

## Production boundary

生产 ingest/review 的 canonical watchlist schema 和 `ASHARE_DATA_ROOT` 路径约定保持不变。Phase 2E CORE / returns harness 与生产 review 路径分离，不写 canonical watchlist，不改变 `perf_tracker`，不接 scheduler，也不代表可直接交易。

## Current blockers and deferred items

1. **Conditional product transition**：PR #12 merge 后进入 `development candidate`；在此之前当前 master 仍是 `research`。这不是 frozen candidate 或 production strategy gate。
2. **P1 next-ladder work — frozen candidate prerequisites**：需要核验冻结候选的输入、策略、依赖、数据、执行和运营边界，明确仍需解决的 P0/P1，并定义 frozen candidate contract/gate。
3. **Scope-local correctness blocker — FULL legacy only**：历史新浪行业 membership / effective-date evidence 缺失，阻止 `FULL_LEGACY_OUTPUT_VALIDATION`、完整 85-score parity 和 legacy sector report；它不阻止 development-candidate product path，不能写成整个系统 blocker。
4. **Scope-local provenance limitation**：retrospective official dump 没有 per-bar historical vintage timestamp，限制历史 known-at 结论的强度；live prospective inputs 仍必须按 T 的 observed-at contract 处理。

已解决：`daily_k.parquet` recovery evidence 与 registry exact SHA 匹配，状态为 `FULLY_RECOVERABLE`。

Deferred（当前不阻止 usable milestone）：Phase 2F 后续 Research V2、历史新浪 membership acquisition 的完整研究、完整 legacy 85-score parity、任何参数选择/调参、performance-based rule change，以及 later production hardening 中不影响 P0/P1 的运营增强。

## Phase 2F product rationale and exit decision

Phase 2E V2 的 DEVELOPMENT returns 是描述性、`RECONSTRUCTED_RETROSPECTIVE`、非 promotion 证据；Phase 2F 值得做，是因为它能在不改策略/阈值的前提下回答当前候选的失败结构是否足以拒绝候选，或是否值得另立一个预注册、范围受限的 research protocol。local-only Phase 2F diagnostic 已给出边界内画像，但未证明稳定可迁移 edge。

**Decision：`NEEDS_MORE_EVIDENCE`。** 不 adopt 当前诊断为 production rule，不自动启动 Research V2；若未来要继续，只能先定义 materiality、预注册比较和 exit gate。该 decision 不阻止当前 product path 的 development work，也不授权读取 Final OOS。

## Current next action

若 PR #12 merge，下一步按 `development candidate` → 核验 frozen-candidate
prerequisites → 明确必须解决的 P0/P1 → 定义 frozen candidate contract/gate
推进。不要自动启动 Phase 2F，不调参，不读 Final OOS，不把 product-ladder 晋级
写成 strategy promotion。
