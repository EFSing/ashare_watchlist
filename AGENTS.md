# Agent Development Contract

本文件是本项目长期开发代理的强制工作契约。它定义代理如何判断任务、控制边界和结束工作；产品长期目标与 usable gate 见 [`docs/PRODUCT_CHARTER.md`](docs/PRODUCT_CHARTER.md)。

## Source of truth and required intake

远端 Git（`origin`）是代码、测试、配置以及跨设备可恢复开发状态的事实源。任何任务的
live state 都以实时 Git/GitHub 查询为准；Git-tracked 治理文档中的 milestone SHA、CI run
和快照都只是 persisted provenance，不是 live-state invariant，也不得要求它们永久等于
未来实时状态。

### FAST PATH（普通开发默认）

普通 bugfix、字段/映射修正、CLI 修复、局部 acquisition 修复、测试维护、文档同步，
以及不改变交易语义或研究结论的局部优化，一律走 FAST PATH。

开始工作时只检查：

1. `git status`（当前 working tree）；
2. current branch；
3. `HEAD`；
4. `git remote -v` + `git fetch`；
5. 读取 `HANDOFF.md`。

FAST PATH 不得默认重新核验全部历史 PR、CI、artifact SHA、数据血缘或旧 Phase。

### STRICT PATH

以下任一情况升级为 STRICT PATH：

- 交易决策语义改变；
- 排名、过滤、阈值含义改变；
- research/live 数据口径改变；
- universe、样本、标签改变；
- look-ahead / OOS 风险；
- 数据污染或研究结论污染风险；
- 正式 artifact 作为研究依据；
- 不可逆写入；
- merge / release；
- 资金、交易或生产相关高风险变更。

STRICT PATH 也只读取并验证当前任务真正依赖的 governance / protocol 文件、PR、CI、
artifact、数据血缘和研究证据，不进行无边界历史审计。

### 何时读取治理文档

- `HANDOFF.md`：会话/任务的恢复入口，按上文 FAST PATH 步骤读取。
- `docs/CURRENT_STATUS.md`：只在任务需要正式 Delivery Ladder、blockers/deferred 或
  established conclusions 时读取。
- `docs/DECISION_LOG.md`：只在任务需要解释既有长期决策的“为什么”时读取。
- 任务相关的 protocol / governance 文件：STRICT PATH 或当前任务真正依赖时读取。

## Live state vs persisted governance state

两类状态必须明确区分：

- **LIVE STATE**：需要时从 Git/GitHub 实时读取 current branch、current HEAD、
  `origin/master` 和 working tree；以这些查询结果为准，不以文档中的静态 SHA 为准。
- **PERSISTED GOVERNANCE STATE**：文档可以保存 formal milestone merge identity、
  strategy/protocol/frozen-artifact SHA、Delivery Ladder、Current Objective、
  blockers/deferred、decisions 和 frozen artifact identities；这些不是 live-state invariant。

live HEAD 比文档 snapshot 新、live CI run 比文档记录新、governance-only commit 使 HEAD
前进，或 formal milestone SHA 与 live HEAD 不相等，均不单独构成冲突。

只有当前任务真正依赖的 governance record 与真实仓库状态矛盾时，才输出
`PROJECT_GOVERNANCE_STATE_CONFLICT`：

1. live Git/GitHub 状态与文档的语义状态矛盾，例如 active PR、Delivery Ladder、
   artifact recoverability、Current Objective 或已正式合并的 material change 没有被反映；
2. 当前任务 required 的 frozen strategy/protocol/artifact identity 或 hash 不匹配；
3. live HEAD 不是预期历史链的合法后继，存在 branch/base/merge provenance 异常。

只解决与当前任务直接相关的冲突；不得为了证明没有冲突而重新审计全部历史状态。

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

策略、数据和已冻结 Phase 2F 研究结果不属于本治理任务的可修改范围。治理文件的职责与
更新节奏如下：

- `HANDOFF.md`：跨设备、跨 Chat、跨 Agent/Codex 会话的最小恢复入口，只保留继续开发
  真正需要的信息：当前 branch、当前 remote HEAD、当前任务、已完成状态、下一步、
  blocker、需要用户决定的问题。在设备/会话交接、暂停、当日结束或预计中断前更新。
- `docs/CURRENT_STATUS.md`：记录正式 Delivery Ladder、当前 blockers/deferred 和已成立
  结论；只在可独立交付状态、PR、merge、release、研究阶段或稳定流水线状态发生实质变化
  时更新；普通局部修改不得强制同步。
- `docs/DECISION_LOG.md`：只记录具有长期约束力、未来需要解释“为什么这样设计”的决定
  （含进入、退出或拒绝某项研究/产品决策的理由）；不记录普通 bugfix、测试补充和局部
  实现细节。
- `docs/PRODUCT_CHARTER.md`：长期使命、范围、usable definition 和交付原则。
- `AGENTS.md`：代理必须遵守的行为契约，包括 FAST/STRICT PATH 与 live state vs
  persisted governance state 的冲突语义。

### REMOTE_RECOVERY_CHECKPOINT

换设备、换 Chat、换 Agent/Codex 会话、暂停开发、当日结束或预计会话/额度可能中断前，
形成 `REMOTE_RECOVERY_CHECKPOINT`：

- 当前有价值修改已经 commit；
- commit 已 push 到远端；
- `HANDOFF.md` 指向正确 remote branch 和 remote HEAD；
- 下一步足以让另一设备在没有聊天记忆的情况下继续；
- 不存在下一环境必须依赖但只保存在本机的状态。

`REMOTE_RECOVERY_CHECKPOINT` 只是状态定义，不创建新文件、新 Phase、新 Protocol、新
registry、新 shadow、新 gate、新状态机或其他治理层。

### New-device recovery flow

```text
git fetch
读取 HANDOFF.md
切换对应 branch
git pull --ff-only
git status
git rev-parse HEAD
```

如果 branch、HEAD 和当前任务状态一致，直接继续，不执行完整项目审计。

### 声明完成前

- FAST PATH：只运行与变更直接相关的测试、`git diff --check`、检查变更文件边界，然后
  commit；普通开发不要求重新核验历史 PR/CI/artifact。
- STRICT PATH：只验证当前任务实际依赖的 PR/CI/artifact/数据血缘/研究证据；若任务允许
  合并，只有 exact-head CI 成功且 PR 为 `CLEAN` / `MERGEABLE` 才能 squash merge；合并后
  正式状态发生实质变化时再更新 `HANDOFF.md` / `CURRENT_STATUS.md`。

## Engineering Simplicity / Complexity Budget

- 默认选择“最小正确实现”，而不是“最大防御实现”。优先小改动、复用现有代码和局部修复；能改 20 行解决的问题，不得无理由重构 200 行。
- 不得为假设性的、低概率且可恢复的问题提前引入新模块、抽象层、状态机、协议、registry、shadow、gate、兼容层或恢复框架。新增复杂度必须对应当前真实需求或高代价风险。
- 新建抽象、模块或架构层之前，必须先证明现有结构无法以更简单方式正确实现；证明不了则不得新增。
- 强 fail-closed / 高强度防御仅优先用于不可逆写入、安全、资金/交易、数据污染、look-ahead、OOS 泄漏、研究结论污染等高代价场景。普通可恢复维护问题应采用简单错误处理。
- 治理强度必须与变更风险匹配。普通 bugfix、格式、映射、字段、轻量功能不得自动升级为新 Phase、Protocol、Decision、Shadow 或大规模治理流程。
- 测试只优先覆盖用户可见行为、关键不变量和真实高价值回归；禁止为了提高测试数量而测试大量内部实现细节。测试数量不是目标。
- 避免 scope creep。完成当前明确需求后停止；发现邻近问题时，除非它直接阻塞正确性，否则记录而不是顺手扩大任务。
- 当“更稳健”与“明显增加维护复杂度”冲突时，优先选择足够稳健且更简单、可理解、可维护的方案。
- 不得新增 Phase、Protocol、registry、shadow、gate、状态机、compatibility layer、
  recovery framework 或新治理文件；除非现有结构无法以更小复杂度实现目标，只对现有治理
  文件做最小必要修改。
