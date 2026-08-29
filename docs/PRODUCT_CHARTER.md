# PRODUCT CHARTER

本章程定义项目的长期产品方向和“什么时候算能用”。它基于当前仓库的真实能力与边界；它不是新的策略、数据集、参数或 Phase 计划。

## Product Mission

本项目最终要形成一个可以实际每日运行的 A 股观察名单 / 交易研究系统，而不是无限扩大的历史研究平台。

研究、provenance、point-in-time（PIT）、hash 和 validation 都是为了让每日系统可靠、可解释、可恢复；它们是手段，不是项目终点。产品价值在于每天能在明确的时序和数据失败边界内，产生可行动、可复核、可回滚的观察名单与研究记录。

## Product Scope

当前仓库的核心范围包括：

- canonical `data/watchlist_YYYYMMDD.json` 观察名单及其 `candidates` / `trigger` schema；
- 盘前复核 `scripts/preopen_review.py`、盘后/午盘复核 `scripts/review_after.py`；
- `scripts/track_perf.py` 的 signal identity / 表现跟踪、`data/positions.json` 持仓与风控记录，以及指数/个股配对指标；
- `Asia/Shanghai`、T 日收盘输入和 XSHG T+1 执行边界的 generation contract；
- `A_PLATFORM_BREAKOUT_LEGACY_V1`、CORE replay 和 DEVELOPMENT returns V2 作为有 provenance 的 research / development harness；
- 冻结 artifact registry、输入/输出 hash、恢复和交接治理。

当前产品范围不等于所有研究结果都已成为生产策略。仓库中已有可运行的手工观察名单和复核工具，但 A evaluator 仍是 research baseline；现状没有证明一个冻结策略已经接通每日生成、canonical watchlist 写入、监控与回滚的完整 usable flow。

非目标包括：

- 无限历史研究、无预先 decision 的指标扩张或自动参数优化；
- 用 current constituents、current sector 或当前数据回填历史 T 日证据；
- 将 `RECONSTRUCTED_RETROSPECTIVE` DEVELOPMENT 结果或未验证的 85-score/full legacy 结果包装成 Final OOS 或 production proof；
- 自动下单、券商执行、收益保证或投资建议。

## Definition of Usable

一个版本只有在以下 gate 全部满足时，才允许进入 prospective observation / paper-use 阶段。这里的“可用”是可控的观察和纸面使用，不等于已获准自动交易，也不要求所有 deferred research 完成。

1. **Deterministic daily execution**：有明确、可重复的每日执行入口；相同的冻结输入和版本必须得到相同的输出，失败以非成功状态结束。
2. **Frozen/versioned strategy**：策略、协议、依赖和适用数据版本都有明确 identity/hash；任何变化都产生新版本并保留旧版本。
3. **No look-ahead/current-data backfill**：信号只消费在 T 时已知的数据；current universe/sector/事件不得回填历史；sealed Final OOS 不进入开发路径。
4. **T close / T+1 execution semantics**：generation 只在 T 正式收盘后完成，最早执行为真实 XSHG 下一交易日 T+1；禁止盘中、same-bar 或人工时间替代正式 session close。
5. **Data failure explicit**：缺失、陈旧、冲突、非法或 hash 不匹配的数据必须显式失败/不可用；不得用静默中性值、近似文件或当前值继续产出。
6. **Actionable watchlist output**：输出符合 canonical `watchlist_YYYYMMDD.json` schema，包含可供人工 review 的 candidates/trigger 和必要的买点、止损、目标等字段；不能只留下 research table。
7. **Reproducible inputs/artifacts**：运行保存输入 manifest、source/version、known-at/provenance、hash 和输出 identity，能够在约束范围内重现并恢复。
8. **Development validation completed**：相关单元/回归测试、compile、JSON/hash/provenance checks 和固定的 development validation 已完成；未通过的检查必须阻止进入该 gate。
9. **Known limitations documented**：已知限制、适用范围、未验证层和人工 review 责任已经写入版本文档；`UNRESOLVED` 不得被写成通过。
10. **Monitoring / rollback / versioning available**：能够发现每日数据/运行/输出异常，保留上一已知良好版本，并明确如何停止使用、回退和恢复。

当前仓库已经有部分 schema、timing、PIT、hash 和 research validation 基础，但上述十项作为完整 end-to-end usable gate 尚未全部被证明；因此不能仅凭 Phase 2E 研究完成就宣布 usable。

## Research Exit Principle

研究必须服务于一个预先定义的 decision：例如是否保留当前候选、是否拒绝一个假设、是否进入一个明确的 development gate，或是否把问题放入 deferred backlog。

- 结果不完美本身不是无限追加变量的理由。
- 新研究必须给出 materiality justification：它可能改变哪个 correctness 判断或下一 product decision；若不能改变，就进入 Deferred Research Backlog。
- 当证据已经足够回答当前 decision，必须停止，不因还可以切更多分组、指标或窗口而继续扩大范围。
- 未解决但不影响 correctness 或 usable gate 的问题，记录为 `DEFER`；不把它升级为 release blocker。
- 每项研究结束必须记录 `ADOPT`、`REJECT`、`DEFER` 或 `NEEDS_MORE_EVIDENCE` 之一，并写明下一步是否属于产品交付、限定研究或 backlog。

## Blocking Severity

- **P0**：correctness / safety / data contamination 风险，例如 look-ahead、错误的 T/T+1 语义、错误 hash/provenance 或将未来/当前数据写入历史；必须阻止继续。
- **P1**：阻止当前 usable milestone 的产品缺口，例如没有确定性每日执行、没有 actionable canonical 输出、数据失败不显式或无法监控/回滚；默认阻止进入下一产品阶段。
- **P2**：有价值但可以延期的证据、兼容性、运营或研究完整性改进；不默认阻止下一阶段。
- **P3**：优化、易用性、性能或 nice-to-have；不阻止交付。

只有 P0/P1 默认允许阻止进入下一产品阶段。一个问题的严重性必须针对具体 milestone 判断：例如历史新浪 membership 缺失是 FULL legacy / 85-score validation 的范围性 correctness blocker，但不是 CORE research 或 prospective product progression 的全局 blocker。

## Delivery Ladder

交付阶梯只描述产品 exit criteria，不预设不存在的 Phase 或 SHA。

### 1. research

研究问题、数据边界、provenance 和停止条件已定义，结果能支持一个明确 decision。退出条件是记录四种 decision 之一，并明确哪些结论不可外推。当前正式仓库处于这一层：Phase 2E research/development artifacts 已完成，但策略尚未成为冻结的每日候选；local-only Phase 2F diagnostic 也不改变 formal master。

### 2. development candidate

把一个明确候选接到端到端开发路径：输入 manifest、T close/T+1 contract、策略评估、canonical watchlist 输出和显式失败处理能够在 development fixtures 或受控数据上重复运行。退出条件是产品路径可演示、回归覆盖通过、没有未分类的 P0/P1；新的研究问题不能作为进入下一步的默认前置条件。

### 3. frozen candidate

冻结候选的策略 spec、协议、依赖、数据身份、输出 schema 和限制说明；旧版本可追溯，新版本不覆盖旧 artifact。退出条件是 Definition of Usable 的 correctness/versioning 前置 gate 通过，且没有未接受的 P0/P1。

### 4. prospective / paper observation

在真实时间前缀上运行 frozen candidate，只记录当时可见的输入和 signal-time 输出；结果/收益不回流到当日决策，观察记录 append-only，并有数据失败、人工 review 和版本记录。退出条件是预先定义的 observation/paper-use acceptance criteria 被满足，且没有 P0/P1。

### 5. usable watchlist version

满足 Definition of Usable 的完整版本，可在明确的 observation / paper-use 范围内每日运行，输出 canonical watchlist，具备监控、停止、回滚和恢复说明。它仍不代表自动交易或收益保证。

### 6. later production hardening

在 usable 之后再处理部署调度、密钥/权限、告警、容量、运行手册、灾备和更严格的操作审计。它们不能被倒置成无限 research 的前置条件；但如果某项直接影响 P0/P1 安全或数据正确性，则按严重度提前处理。

## Anti-Research-Loop Rule

发现新的指标、分组差异、失败画像或潜在优化方向，本身不足以开启新研究。

只有至少满足以下一项，才允许申请限定的新研究：

- 当前 evidence 显示核心策略不可用；
- 存在 correctness 风险；
- 预注册 gate 未通过；
- 结果能够明确改变下一 product decision。

否则只记录到 Deferred Research Backlog。Phase 2F 的 product justification 是：Phase 2E DEVELOPMENT outcome 仍是描述性、非 promotion 证据，需要判断失败结构是否足以拒绝当前候选，或是否值得另立一个有明确 gate 的 research protocol。Phase 2F 完成后的 decision 必须至少回答“是否 adopt 当前候选、是否启动限定 Research V2、哪些问题继续不阻塞产品”；当前 local diagnostic 的实际边界是 `NEEDS_MORE_EVIDENCE`，不支持自动形成 production threshold。

## Current product decision

截至本章程建立时，正式 master 的结论是：保留现有 research / development artifacts 和 manual review utility，**不 promotion**；将端到端每日 generation、canonical output、monitoring/rollback/versioning 作为到达 usable 前的 P1 产品工作；将历史新浪 membership、完整 legacy 85-score parity、Phase 2F 后续 Research V2 以及其他未改变当前 usable gate 的研究列为 scope-local correctness / deferred items，不能把它们统称为整个系统 blocker。
