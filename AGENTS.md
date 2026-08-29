# Agent Development Contract

本文件是本项目长期开发代理的强制工作契约。它定义代理如何判断任务、控制边界和结束工作；产品长期目标与 usable gate 见 [`docs/PRODUCT_CHARTER.md`](docs/PRODUCT_CHARTER.md)。

## Required intake

任何新 Codex / agent 在采取任务动作前，必须先读取：

1. `AGENTS.md`
2. `HANDOFF.md`
3. `docs/CURRENT_STATUS.md`
4. `docs/DECISION_LOG.md`
5. 当前任务相关的 governance / protocol 文件，例如 `docs/FROZEN_ARTIFACT_POLICY.md`、`docs/generation_input_contract.md`、`docs/phase2d_validation_protocol.md` 或对应 research protocol。

然后实时核对适用的 Git branch、HEAD、remote、PR、CI 和 artifact/hash 状态。文档快照不能替代真实仓库状态；若不一致，先标记 `PROJECT_GOVERNANCE_STATE_CONFLICT`，停止依赖冲突字段继续推进。

## Task classification

每个任务开始时必须明确归类，并在结束时说明归类是否改变：

- **correctness blocker**：会造成 look-ahead、current-data backfill、错误的 T/T+1 语义、数据污染、错误 hash/provenance、错误输出或安全风险；必须 fail closed。
- **product blocker**：阻止当前已定义的 usable milestone，例如没有可重复的每日执行路径、没有 actionable canonical 输出、没有数据失败处理或没有回滚/版本能力。
- **research question**：用于回答预先定义的策略/证据问题；没有证据表明它阻止 correctness 或当前 usable gate 时，不得升级为项目 blocker。
- **deferred improvement**：有价值但不影响当前 correctness 或 usable gate 的改进、优化或未来研究，进入 backlog，不自动开新 Phase。

普通 research question 不得自动升级成项目 blocker。只有 P0/P1（定义见 `docs/PRODUCT_CHARTER.md`）默认允许阻止下一产品阶段。

## Product-directed execution

所有新任务必须能够回答：

> 这个任务具体如何推动系统更接近可实际使用状态？

回答必须指向一个具体的 usable gate、correctness 风险或预先定义的 product decision。如果无法回答，不得默认开启新 Phase；应记录为 `DEFER` 或 deferred backlog，等待明确的产品理由。

每个 research task 开始前必须写明研究问题、materiality justification、输入和停止条件；结束时必须形成且记录一个明确 decision：

- `ADOPT`
- `REJECT`
- `DEFER`
- `NEEDS_MORE_EVIDENCE`

不能只留下“建议继续研究”。`NEEDS_MORE_EVIDENCE` 也必须写清楚缺什么证据、谁/什么 gate 会使用它，以及没有该证据时哪些产品路径仍可继续。

## Hard boundaries

代理禁止：

- 无限扩大研究范围；
- 因为发现新指标、分组差异或潜在优化变量就自动调参；
- 为追求完美而阻止满足既定 gate 的版本进入下一阶段；
- 把 deferred research 当成 release blocker；
- 静默修改 frozen strategy、protocol、dataset、artifact 或 hash；
- 读取 sealed `Final OOS`；
- 把一个项目、provider、数据集或策略的事实混入另一个项目；
- 把 research / development artifact 写成 production、paper observation 或 Final OOS 结论；
- 在没有明确授权时启动 Phase 2F、promotion、参数选择或正式数据获取。

缺失证据必须使用项目已有的保守状态词，例如 `UNRESOLVED`、`PARTIAL_UNVERIFIED`、`NOT_REPRODUCIBLE_WITH_CURRENT_DATA`、`UNKNOWN_ORIGIN` 或 `INSUFFICIENT_DATA`，不得用猜测填补。

## Change and handoff rules

策略、数据和已冻结 Phase 2F 研究结果不属于本治理任务的可修改范围。治理变更完成后，必须让 `HANDOFF.md`、`docs/CURRENT_STATUS.md` 和 `docs/DECISION_LOG.md` 各自保持职责分离：

- `HANDOFF.md`：当前正在执行什么、接手边界、真实 Git/PR/CI/artifact 快照；
- `CURRENT_STATUS.md`：正式达到 Delivery Ladder 哪一级，以及当前 blockers/deferred；
- `DECISION_LOG.md`：为什么进入、退出或拒绝某项研究/产品决策；
- `docs/PRODUCT_CHARTER.md`：长期使命、范围、usable definition 和交付原则；
- `AGENTS.md`：代理必须遵守的行为契约。

声明完成前，检查变更文件边界、测试、`compileall`、JSON/hash validation、`git diff --check`、最终 commit、PR head 和 exact-head CI。若任务允许合并，只有 exact-head CI 成功且 PR 为 `CLEAN` / `MERGEABLE` 才能 squash merge；合并后刷新 handoff。
