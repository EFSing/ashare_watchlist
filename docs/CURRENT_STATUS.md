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
- B `BREAKOUT_RETEST_LEGACY_V1` 已通过冻结的 development eligibility gate；这只是
  candidate eligibility，不是 frozen strategy、production promotion 或 Final OOS。
- candidate-bound prospective input/provenance contract 已定义，但尚无首个真实
  `LIVE_OBSERVED` T-close input instance；在该实例出现并完成 fail-closed audit 前，
  不进入 frozen candidate。
- 本机 Phase 2F diagnostic commit `3eeb5df9f7cf4ef5c30b3380b323f26f2491f873` 尚未 push、无 PR、无 CI；它是 local candidate work，不改变 formal master status。
- Phase 2F local diagnostic 的研究边界保持不变：它没有修改 legacy strategy、冻结阈值或 Final OOS；其退出 decision 为 `NEEDS_MORE_EVIDENCE`，不能直接形成 production threshold 或 promotion。

## Production boundary

生产 ingest/review 的 canonical watchlist schema 和 `ASHARE_DATA_ROOT` 路径约定保持不变。Phase 2E CORE / returns harness 与生产 review 路径分离，不写 canonical watchlist，不改变 `perf_tracker`，不接 scheduler，也不代表可直接交易。

## Current blockers and deferred items

1. **P1 first prospective input blocker**：唯一剩余的 frozen-candidate prerequisite 是
   `P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE`；需要一个 candidate-bound、
   `LIVE_OBSERVED`、`known_at <= T` 的真实 T-close package，并证明
   universe/sector/names/market_env、provider/version、calendar、availability/recovery
   和 output identity。
2. **Scope-local correctness blocker — FULL legacy only**：历史新浪行业 membership /
   effective-date evidence 缺失，阻止 `FULL_LEGACY_OUTPUT_VALIDATION`、完整 85-score
   parity 和 legacy sector report；它不阻止 development-candidate product path 或当前
   candidate-bound gate，不能写成整个系统 blocker。
3. **Scope-local provenance limitation**：retrospective official dump 没有 per-bar
   historical vintage timestamp，限制历史 known-at 结论的强度；live prospective
   inputs 仍必须按 T 的 observed-at contract 处理。

已解决：`daily_k.parquet` recovery evidence 与 registry exact SHA 匹配，状态为 `FULLY_RECOVERABLE`。

Deferred（当前不阻止 usable milestone）：Phase 2F 后续 Research V2、历史新浪 membership acquisition 的完整研究、完整 legacy 85-score parity、任何参数选择/调参、performance-based rule change，以及 later production hardening 中不影响 P0/P1 的运营增强。

## Phase 2F product rationale and exit decision

Phase 2E V2 的 DEVELOPMENT returns 是描述性、`RECONSTRUCTED_RETROSPECTIVE`、非 promotion 证据；Phase 2F 值得做，是因为它能在不改策略/阈值的前提下回答当前候选的失败结构是否足以拒绝候选，或是否值得另立一个预注册、范围受限的 research protocol。local-only Phase 2F diagnostic 已给出边界内画像，但未证明稳定可迁移 edge。

**Decision：`NEEDS_MORE_EVIDENCE`。** 不 adopt 当前诊断为 production rule，不自动启动 Research V2；若未来要继续，只能先定义 materiality、预注册比较和 exit gate。该 decision 不阻止当前 product path 的 development work，也不授权读取 Final OOS。

## Current next action

当前已在 `development candidate`。B 已通过一次且仅一次的冻结 eligibility，结果为
`CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES`。candidate-bound contract 已定义，
但 `FROZEN_CANDIDATE_PREREQUISITES` 仍为 `FROZEN_CANDIDATE_BLOCKED`，唯一 P1 是
`P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE`。等待首个真实 input instance 后
才可再次审计；不启动 Phase 2F、不调参、不读 Final OOS、不把 product-ladder 晋级
写成 strategy promotion。

## Strategy Candidate Nomination V1 — 2026-08-30 — final eligibility update

唯一 nomination 仍为
`NOMINATE_B_BREAKOUT_RETEST_LEGACY_V1_FOR_DEVELOPMENT_ELIGIBILITY`；A 仍为
`REJECT_A_PLATFORM_BREAKOUT_LEGACY_V1_AS_FROZEN_CANDIDATE`，C 未被评估。

B exact reconstruction 已完成，spec SHA 为
`5bbeb345ebd8883149138d2f29f8606f919949ae285aa2839fa337921dfc7112`。固定
`STRATEGY_DEVELOPMENT_ELIGIBILITY_V1` 在 parquet 环境修复后只运行一次，并保持
`ELIGIBILITY_RULE_FROZEN_BEFORE_B_RETURNS_READ = true`。环境为 Python 3.12.13、
pandas 2.2.3、pyarrow 17.0.0；registry required artifacts 13/13 通过校验，
daily_k SHA 为 `61189a4850e2eb157453e28e5375e502e20d214508bbe70ea71066ca3e05e426`。

结果：Event N `17,714`；1D/3D/5D/10D available N 为 `17,689` / `17,635` /
`17,602` / `17,558`；10D positive rate / mean / median 为 `51.6403%` /
`+1.4603%` / `+0.3226%`；4 个 robust years 中 2 个 mean 为正。固定 gates 全部
PASS，最终 B decision 为 `CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES`。完整指标、
MFE/MAE、concentration、year robustness、gate audit 和 event/manifest SHA 见
[`strategy_candidate_eligibility_report.md`](strategy_candidate_eligibility_report.md)。

已定义 [`candidate_bound_prospective_input_contract_v1.md`](candidate_bound_prospective_input_contract_v1.md)，
但没有伪造 prospective live instance。重新判断后的
`FROZEN_CANDIDATE_PREREQUISITES` 为 `FROZEN_CANDIDATE_BLOCKED`，唯一 P1 为
`P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE`；在首个真实
`LIVE_OBSERVED` T-close package 到来前，不创建 `FROZEN_CANDIDATE_CONTRACT_V1`，
不测试 C、不启动 Phase 2F、不调参、不读 Final OOS。
