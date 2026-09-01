# CURRENT STATUS

更新时间：2026-09-01（Asia/Shanghai）
Formal Delivery Ladder：`development candidate`
Product-governance milestone：PR #17 squash merge `91e9ec76e3f4ea8ffaa1badeb759c1d2a7f5f73b`；post-merge master correctness run `33399324692` success（last-verified provenance snapshot）
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

## Provider architecture correction — 2026-08-31

Sol identified `P0-LIVE-SECTOR-TAXONOMY-MISMATCH` in the merged live adapter: its
Eastmoney industry endpoints could not satisfy B's frozen exact `新浪行业` provenance.
PR #17 subsequently merged this correction to formal master at
`91e9ec76e3f4ea8ffaa1badeb759c1d2a7f5f73b`; the merge exact-head correctness run
`33399324692` succeeded. The two pre-merge `2026-08-31` attempts
remain fail-closed before package construction, so no contaminated prospective artifact
exists.

Current capability decisions are `HITHINK_LIVE_PRIMARY = SUPPORTED` and
`EXACT_SINA_SECTOR_SOURCE = AVAILABLE`. The branch uses HiThink metadata for current
universe/names, HiThink stock/index K as primary (stock forward-adjusted, index explicitly
`PROVIDER_RAW_SNAPSHOT`), exact AkShare Sina sector APIs, and a separately versioned
Tencent Kline transport fallback. EM/THS/SW substitution is rejected; provider, API,
taxonomy, adjustment and fallback identities are included in manifest provenance.

This is a correctness/product architecture correction. B strategy/spec/thresholds and the
`5bbeb345ebd8883149138d2f29f8606f919949ae285aa2839fa337921dfc7112` spec SHA are unchanged;
T-close/T+1 semantics are unchanged. No prospective package was run by this correction.

## Product readiness

- 已有：canonical watchlist schema、盘前/盘后复核、表现追踪、持仓/配对工具；Phase 2B 的 T close / XSHG T+1 contract；Phase 2D PIT contract；Phase 2E CORE / DEVELOPMENT artifacts、registry、hash 和 recovery governance。
- PR #12 的 development-candidate path 已在受控输入上证明端到端 deterministic
  generation → canonical watchlist output → explicit failure → monitoring/rollback/
  versioning；该产品里程碑现已写入 master 的正式 Ladder。
- PR #17 已将 HiThink/exact-Sina/Tencent live acquisition adapter 合并到 master；
  首个正式 master-baseline T-close acquisition 在 exact Sina display-name consistency
  阶段以 `INPUT_CONFLICT` fail closed，未形成 live package。当前 source audit 已将
  display-name 从 security hard gate 改为 V2 symbol-authoritative diagnostic；sector
  coverage/ambiguity 仍保持 required fail-closed。
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

1. **P0 live sector taxonomy mismatch**：已由 PR #17 修复并合并到 master；merge
   master correctness run `33399324692` 对 merge SHA 精确成功。
2. **P1 first prospective input blocker**：source audit 已证明 B 不消费 display name，
   exact symbol 是 security identity；PR #18 采用
   `DISPLAY_NAME_CONSISTENCY_POLICY_V2_SYMBOL_AUTHORITATIVE`，保留 raw/normalized
   mismatch diagnostics，不改变 B executable semantics。
3. **P1 candidate-bound prospective input**：B 确实消费 sector membership/rank/change，
   且 missing sector evidence 为 `INSUFFICIENT_DATA`；当前 exact Sina snapshot 有
   coverage failure 与同一 symbol 多 sector 歧义，具体 decision 为
   `FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_SECTOR_MEMBERSHIP_AMBIGUITY`。在完整、无歧义
   的 future T-close READY package 前，不得进入 frozen candidate。
4. **Scope-local correctness blocker — FULL legacy only**：历史新浪行业 membership /
   effective-date evidence 缺失，阻止 `FULL_LEGACY_OUTPUT_VALIDATION`、完整 85-score
   parity 和 legacy sector report；它不阻止 development-candidate product path 或当前
   candidate-bound gate，不能写成整个系统 blocker。
5. **Scope-local provenance limitation**：retrospective official dump 没有 per-bar
   historical vintage timestamp，限制历史 known-at 结论的强度；live prospective
   inputs 仍必须按 T 的 observed-at contract 处理。

已解决：`daily_k.parquet` recovery evidence 与 registry exact SHA 匹配，状态为 `FULLY_RECOVERABLE`。

Deferred（当前不阻止 usable milestone）：Phase 2F 后续 Research V2、历史新浪 membership acquisition 的完整研究、完整 legacy 85-score parity、任何参数选择/调参、performance-based rule change，以及 later production hardening 中不影响 P0/P1 的运营增强。

## Current continuation audit — 2026-09-01

本机已从 repository declaration 重建 workspace-local `.venv`，并以
`.[test,research]` 安装验证 Python 3.12.13、pandas 2.2.3、requests 2.32.3、
exchange-calendars 4.13.2、AkShare 1.18.94、pytest 8.3.5 和 pyarrow 17.0.0；
XSHG/Asia/Shanghai、数据根目录和 HiThink credential presence 已核对。当前 Codex
app 的 Google Drive profile、private backup metadata/raw streamed reference 以及临时
upload/readback/delete probe 已完成；正式 `daily_k.parquet` 未在本轮重新物化 byte hash。

`scripts/development_preflight.py --probe-provider` 的结果明确标记为
`LOCAL_CURRENT_SNAPSHOT_DIAGNOSTIC_NOT_PROSPECTIVE_EVIDENCE`。当前 HiThink 返回 5,565
raw rows / 5,221 个 SH/SZ A-share symbols，snapshot、adjustment-events、stock/index
historical capability 均 PASS；exact Sina 返回 49 definitions / 49 member calls。
sector audit 为 2,983 raw rows、2,978 unique member symbols、2,539 common symbols、
2,682 个 universe symbols 缺 sector、439 个 sector symbols 在 universe 外、47 个
raw-name mismatch（registered normalization 解决 0 个），并发现 000587、000602、
002217、002617、600714 五个同一 symbol 多 sector membership。完整 source/dependency
matrix 与当前计数见 [`b_dependency_audit_20260901.md`](b_dependency_audit_20260901.md)。

本次 decision：`ADOPT` symbol-authoritative display-name policy；`NEEDS_MORE_EVIDENCE`
for complete and unambiguous exact-Sina sector evidence at a legitimate future T-close。
当前 formal blocker 为
`FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_SECTOR_MEMBERSHIP_AMBIGUITY`，并伴随 exact
coverage failure。PR #18 尚未合并，故没有构造 T=`2026-08-31` 或 T=`2026-09-01` package，
没有 canonical output、promotion、Phase 2F、C evaluation 或 Final OOS access；Formal
Delivery Ladder 仍为 `development candidate`。
   `P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE`；2026-08-31 正式
   master-baseline acquisition 在 AkShare sector membership 阶段发生
   `ConnectionError`，未形成 package。后续需要一个 candidate-bound、
   `LIVE_OBSERVED`、`known_at <= T` 的真实 T-close package，并证明
   universe/sector/names/market_env、provider/version、calendar、availability/recovery
   和 output identity。
3. **Scope-local correctness blocker — FULL legacy only**：历史新浪行业 membership /
   effective-date evidence 缺失，阻止 `FULL_LEGACY_OUTPUT_VALIDATION`、完整 85-score
   parity 和 legacy sector report；它不阻止 development-candidate product path 或当前
   candidate-bound gate，不能写成整个系统 blocker。
4. **Scope-local provenance limitation**：retrospective official dump 没有 per-bar
   historical vintage timestamp，限制历史 known-at 结论的强度；live prospective
   inputs 仍必须按 T 的 observed-at contract 处理。

已解决：`daily_k.parquet` recovery evidence 与 registry exact SHA 匹配，状态为 `FULLY_RECOVERABLE`。

Deferred（当前不阻止 usable milestone）：Phase 2F 后续 Research V2、历史新浪 membership acquisition 的完整研究、完整 legacy 85-score parity、任何参数选择/调参、performance-based rule change，以及 later production hardening 中不影响 P0/P1 的运营增强。

治理校验注意：现有、非 replay-required 的 `phase2e.hithink_probe` registry record
预存 `working_tree_sha256=af694b...`，但当前 exact bytes 的 SHA 为其 registered
`file_sha256=395601b...`。本轮未修改 frozen registry，也未用该 provider probe 作为
live package/recovery evidence；该 pre-existing provenance discrepancy 需另行显式
修复或决策，不改变本轮正式 acquisition 的 provider blocker。

## Phase 2F product rationale and exit decision

Phase 2E V2 的 DEVELOPMENT returns 是描述性、`RECONSTRUCTED_RETROSPECTIVE`、非 promotion 证据；Phase 2F 值得做，是因为它能在不改策略/阈值的前提下回答当前候选的失败结构是否足以拒绝候选，或是否值得另立一个预注册、范围受限的 research protocol。local-only Phase 2F diagnostic 已给出边界内画像，但未证明稳定可迁移 edge。

**Decision：`NEEDS_MORE_EVIDENCE`。** 不 adopt 当前诊断为 production rule，不自动启动 Research V2；若未来要继续，只能先定义 materiality、预注册比较和 exit gate。该 decision 不阻止当前 product path 的 development work，也不授权读取 Final OOS。

## First prospective acquisition attempt — 2026-08-31

正式 master baseline 为 `f1fed4608210aa175ac268189a8d7f032b0b88e0`。T=`2026-08-31`
是 XSHG session，session close=`2026-08-31T15:00:00+08:00`，下一交易日
T+1=`2026-09-01`。调用开始于实际运行时 `2026-08-31T15:21:18.969554+08:00`；
AkShare universe/sector acquisition 在 sector membership 请求阶段以
`ConnectionError` fail closed，状态为 `PROVIDER_FAILURE`。

没有形成 READY `GenerationInputManifest`，没有 `LIVE_OBSERVED` package，没有
input/generation fingerprint、package content/file SHA 或 logical path，
`data/prospective_inputs/` 未创建；没有 canonical watchlist，也没有 recovery
artifact 可登记。未进入 Tencent quote/Kline、market_env、persistence 或
frozen-candidate prerequisite 的后续 checks。Formal Delivery Ladder 仍为
`development candidate`；不创建 `FROZEN_CANDIDATE_CONTRACT_V1`。

## PR #16 — same-day retry semantics and AkShare bounded retry

Sol review 将 `PROJECT_GOVERNANCE_STATE_CONFLICT` 限定为旧草稿把 retry 语义写成
“只能等下一个 T-close session”。Phase 2B contract 没有这个限制：在同一北京时间
日期 T、正式收盘后，可以发起新的独立 live acquisition attempt。每次 attempt 必须
使用新的真实 `observed_at`，不复用失败 attempt 的 partial provider responses，也不把
第一次失败改写为成功；跨到 `2026-09-01` 后，当前 live provider 数据绝不能构造
`T=2026-08-31` package。

PR #16 的最小代码 hardening 只对 AkShare
`stock_info_a_code_name`、`stock_board_industry_name_em` 和每个
`stock_board_industry_cons_em` provider read 提供固定最多 3 次的 transient
network/connection retry，并使用 bounded backoff。schema、empty、duplicate、name/
sector conflict 和 coverage 等语义错误仍在 retry 边界外 fail closed；attempt/backoff
不进入 canonical input/generation/package identity。新增回归覆盖 transient recovery、
3-attempt exhaustion、sector-member recovery、semantic/schema no-retry 和 no-output。

执行规模审计（execution diagnostics，不是筛选规则）保持完整 universe：AkShare
universe 1 次 read、sector definitions 1 次 read、每个 definition 1 次逻辑 member
read（transient retry 只增加同一 read 的 provider attempts）、Tencent quote 每 50
个 symbol 一个 batch，即 `ceil(universe_symbol_count / 50)`，planned stock Kline
request 数为 `universe_symbol_count`，另加 1 次 index Kline request。此前正式失败发生
在 sector membership，尚无真实 universe/definition 完成计数或后续 quote/Kline 计数；
不得用缩小 universe、跳过股票或改 strategy 解决潜在规模问题。

PR #16 合并后，在 clean merged master `c9d5e50be833bf5bb1c3c83c0a2fa1b3e83979c1`
上于新的真实 `observed_at_bjt=2026-08-31T16:27:36.974203+08:00` 重新获取全部
required input。第二次 attempt 的 AkShare `stock_info_a_code_name` 在固定 attempts
`3/3` 后仍以 `ConnectionError` 失败，adapter acquisition elapsed 为 `0.782s`；
sector code/name 不适用，completed sector calls `0`，sector definition count
`NOT_REACHED`，universe symbol count `0`，Tencent quote batch、stock/index Kline、
market_env、manifest 和 persistence 均 `NOT_REACHED`。没有创建
`data/prospective_inputs/` 或任何 partial formal evidence。

## Current next action

当前已在 `development candidate`。B 已通过一次且仅一次的冻结 eligibility，结果为
`CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES`。candidate-bound contract 已定义，
但 `FROZEN_CANDIDATE_PREREQUISITES` 仍为 `FROZEN_CANDIDATE_BLOCKED`，当前 P1 是
`P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE`，具体 blocker 为 AkShare sector
provider failure；本次已完成同日独立 retry attempt 并在 attempts `3/3` 后再次 fail closed，
本任务停在该真实 blocker，不自动无限重试。后续若得到新的明确运行授权且 provider 可用，
必须重新获取全部 input；跨到下一北京时间日后，不得再用当前 live provider 数据构造
本次 T 的 package。不启动 Phase 2F、不调参、不读 Final OOS、不把 product-ladder 晋级写成
strategy promotion。

PR #17 的 review-branch snapshot 已结束；该 PR 已从 final head
`ef48d192c7709a7194348369c689070c665da2b4` squash-merged to master at
`91e9ec76e3f4ea8ffaa1badeb759c1d2a7f5f73b`，merge master exact-head correctness run
`33399324692` succeeded。后续 acquisition 结果见本文末的 post-merge decision。

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

## Governance correctness closure — 2026-08-31

已修复 active PR metadata 与正式 B evidence 的 `PROJECT_GOVERNANCE_STATE_CONFLICT`：
B decision 为 `CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES`；Formal Delivery Ladder
仍为 `development candidate`；尚未创建 `FROZEN_CANDIDATE_CONTRACT_V1`；唯一当前
P1 仍为 `P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE`；不 promotion。

eligibility provenance 已改为稳定 repo-relative logical paths。不同 filesystem root、
relative/absolute invocation 的 canonical identity 回归均通过；绝对 path 与
`Path.resolve()` machine-specific result 不进入 semantic/content/manifest hash。

正式 B decision artifacts 已在 `data/governance/frozen_artifacts.json` 登记：event
file SHA `8940a4a346ac6911ba669f84a9ceba7ef878b0ed0ce51edf673439b52aa056b9`、event
semantic SHA `a16e48dfbe8a93f64d8bf1bad6e00d3eaf32c10fd60eed09dc5574247b8119bc`；manifest
manifest semantic SHA `f79ec9baa494f2f0256843c2540988bd25c94269ed9a1fd4ada228759bd8e0a2`、
payload content SHA `e754787836b28316430278372ab2d84817091d4608da394f9207f695a4c27aee`、
manifest file SHA `5e0a557c1930de7b4f182f09f43b45c0c11b19b2d7c992bf9e7fa7e6cc6de048`。
两项均为 `required_for_decision=true`、`required_for_replay=false`。

同一冻结输入与固定 B protocol 的 deterministic reproducibility verification 证明
event count、event identities、全部 metrics、fixed thresholds、gate audit 和
eligibility decision 与修复前完全一致；这不是第二次 candidate-selection experiment。
Phase 2B T-close/T+1、anti-lookahead、Final OOS sealed invariants 未改变。

## Live acquisition adapter readiness — 2026-08-31

本任务对当前 master 做了执行路径审计：原有代码只有 Phase 2B
`freeze_generation_inputs()` validator 和旧 Tencent quote/Kline utility，没有能从
AkShare/HiThink/Tencent provider 构造完整 candidate-bound `GenerationInputManifest` 的
acquisition adapter。因此 `P1-FC-LIVE-ACQUISITION-ADAPTER_MISSING` 被识别为本轮
真正的产品 P1，并在未改变任何 B strategy/spec/threshold 的单一实现分支中补齐。

[`live_acquisition_adapter_v1.md`](live_acquisition_adapter_v1.md) 和
[`scripts/live_acquisition.py`](../scripts/live_acquisition.py) 定义并测试了
HiThink SH/SZ A-share universe/names、exact Sina sector definitions/membership/rank、
Tencent T quote、HiThink forward stock / raw index daily K（Tencent qfq fallback）、display names、market_env、runtime/
provider provenance、T-close/T+1、freshness/completeness/conflict、deterministic
identity、immutable input persistence 和 fail-closed 行为。实际 runtime 的 AkShare
版本为 `1.18.94`；pyarrow 保持 `25.0.1`，没有为 prospective path 降级。

这是 implementation/runtime readiness；PR #15 已合并到 master；PR #17 随后完成 provider correction。合并前本分支和
测试没有调用 live endpoint；合并后首个正式 master-baseline acquisition 已在
AkShare sector membership 阶段以 `PROVIDER_FAILURE / ConnectionError` fail closed，
没有冻结 `LIVE_OBSERVED` T 日数据、没有生成 canonical watchlist 或 prospective
package。Formal Delivery Ladder 仍为 `development candidate`，prerequisite
decision 仍为 `FROZEN_CANDIDATE_BLOCKED`；provider 可用时，可以在同一 T 日正式收盘后
以新的 observed_at 独立重试并重新审计；本轮 post-merge attempt 的失败结果见本文末。

## PR #17 final contract hardening — 2026-08-31 (historical review snapshot)

PR #17 在现有 provider correction 上补齐最后一个 correctness boundary：stock
`KlineManifest` 只接受 `PROVIDER_QFQ_SNAPSHOT`；HiThink index primary 只接受
`HiThink Financial-API` + `PROVIDER_RAW_SNAPSHOT`；Tencent index fallback 只接受
`Tencent` + `PROVIDER_QFQ_SNAPSHOT`，其他 provider/adjustment 配对 fail closed。

当前 live universe contract 正式版本化为
`TRADABLE_UNIVERSE_SCOPE_V1 = SH_SZ_A_SHARE_ONLY`：沪市/深市 A 股 included，北交所
explicitly excluded，BJ absence 不计为 incomplete coverage。scope/version 进入
UniverseManifest content identity、GenerationInput input fingerprint、live generation
identity、provider metadata 和 prospective provenance。未来纳入 BJ 必须形成新的
scope/version identity。

既有 B development eligibility 的历史 universe scope 不被重跑、改写或用来选择新
candidate；若其历史输入包含 BJ，只保留
`KNOWN_DEVELOPMENT_VS_PROSPECTIVE_UNIVERSE_SCOPE_DIFFERENCE` 作为 scope 差异记录，
不据此否定既有 B decision。B strategy/spec/threshold、冻结历史 artifact 和 Final OOS
sealed 状态均不变。

## Post-merge formal acquisition decision — 2026-08-31

PR #17 was squash-merged at `91e9ec76e3f4ea8ffaa1badeb759c1d2a7f5f73b` from final
head `ef48d192c7709a7194348369c689070c665da2b4`; merge master exact-head correctness
run `33399324692` succeeded. A new `LIVE_OBSERVED` attempt for T=`2026-08-31`
used fresh `observed_at_bjt=2026-08-31T22:01:28.307161+08:00` and T+1=`2026-09-01`.

The attempt failed closed at exact Sina sector/member display-name consistency:

    INPUT_CONFLICT: display-name conflict for 000012: universe/member

The final frozen-candidate prerequisites status is
`FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_INPUT_CONFLICT`. This is an
`INPUT_PROVIDER_DATA_CONSISTENCY_CONFLICT`, not provider connectivity. No READY manifest
or package was created; quotes, Klines, hashes, persistence, Google Drive backup/recovery,
canonical watchlist, prospective returns, C, Phase 2F, tuning, paper/live trading,
and production promotion were not performed. The attempt evidence is recorded in
[`prospective_acquisition_evidence_20260831.md`](prospective_acquisition_evidence_20260831.md)
and the machine-readable record is explicitly not a frozen artifact.

The formal Delivery Ladder remains `development candidate`; B remains
`CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES` at candidate eligibility. Strategy/spec/
thresholds, frozen artifacts, Final OOS sealed/unread status, and all no-backfill/no-future
boundaries are unchanged.

## PR #18 continuation — display-name blocker diagnosis and minimal fix

The 2026-08-31 formal attempt remains a failed `LIVE_OBSERVED` attempt; it is not
rewritten as success. Its `INPUT_CONFLICT` is classified as
`INPUT_PROVIDER_DATA_CONSISTENCY_CONFLICT`, with final decision
`FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_INPUT_CONFLICT`. Provider connectivity is
explicitly false. The original attempt did not record raw names or execution counts,
so those fields remain unrecorded rather than being backfilled from a later current
diagnostic.

The 2026-09-01 fresh-machine current capability diagnostic read the complete HiThink
`SH_SZ_A_SHARE_ONLY` universe and exact Sina sector/member source: 5,565 raw universe
rows / 5,221 scoped symbols, 49 definitions, 49 completed member calls, 2,539 common
symbols, 2,492 exact raw-name matches, and 47 raw-name mismatches. The registered
normalization resolved zero mismatches. The current snapshot also has 2,682 universe
symbols without sector membership, 439 sector symbols outside the universe, and five
multi-sector symbols: `000587`, `000602`, `002217`, `002617`, `600714`. There were no
exact duplicate symbols in this snapshot. All of these counts are current diagnostics
only and are not a rewrite of the 2026-08-31 historical diagnostic or attempt.

PR #18 keeps `B_BREAKOUT_RETEST_LEGACY_V1`, its spec SHA and thresholds,
`TRADABLE_UNIVERSE_SCOPE_V1 = SH_SZ_A_SHARE_ONLY`, exact Sina taxonomy, T-close/T+1,
Final OOS sealed/unread, C exclusion, and no-tuning/no-promotion boundaries unchanged.
The live adapter retains both raw provider names, compares normalized values, keeps
symbol as the security identity, versions the normalization and policy in generation
identity/provenance, and exposes safe structured mismatch diagnostics. Exact duplicate
same-sector provider rows may be deterministically deduplicated with raw row/count
provenance; distinct sector memberships remain fail closed. No partial formal package
is persisted. The source audit confirms B consumes sector evidence/rank/change, so the
sector requirement remains executable and cannot be relaxed or substituted.

At the pre-merge snapshot, the decision was
`FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_SECTOR_MEMBERSHIP_AMBIGUITY`, with independent
exact-Sina coverage failure. The active contract is
`CANDIDATE_BOUND_PROSPECTIVE_INPUT_PROVENANCE_CONTRACT_V2`; V1 remains historical.
At that snapshot, PR #18 had not been merged, so no T=`2026-08-31` or T=`2026-09-01`
package had been constructed. The full source matrix and current snapshot audit are in
[`b_dependency_audit_20260901.md`](b_dependency_audit_20260901.md).

## 2026-09-01 sector-provenance closure — current status

Formal Delivery Ladder remains `development candidate`. PR #18 is now merged at
`17371fde39a6b24241532b131caf5927cb9b8933`; exact merge push correctness run
`33476256589` succeeded. The current closure branch was created from that clean
merged master.

The current blocker is `B_RECONSTRUCTION_SEMANTIC_MISMATCH`: exact V0 missing-sector
behavior defaults to `("-", 50, 0.0)` and continues evaluation, while the current B
evaluator returns per-symbol `INSUFFICIENT_DATA`. The current V2 live adapter also
has package-level full-coverage and distinct-multi-sector fail-close rules; these
are recorded separately and are not treated as proof that Model S/V3 is adopted.

Current exact-Sina diagnostics remain non-prospective: 49/49 definitions audited,
2,983 raw and wrapper rows, 2,978 raw unique symbols, 2,682 scoped-universe symbols
without membership, 439 outside-scope symbols, and five distinct multi-sector
symbols. No safe wrapper correction was found. No formal `LIVE_OBSERVED` T-close
capture, READY manifest, package, canonical watchlist, prospective result, C,
Phase 2F, promotion, or Final OOS read was performed. Final OOS remains
`SEALED / UNREAD`.

Closure evidence and the machine-readable decision are in
[`sector_provenance_closure_20260901.md`](sector_provenance_closure_20260901.md).
