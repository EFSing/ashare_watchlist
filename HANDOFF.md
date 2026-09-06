# HANDOFF — 跨设备最小恢复入口

> 恢复链：remote Git → branch → remote HEAD → HANDOFF.md → next action。
> 本文件不是历史归档；历史 provenance 在 Git 历史中，正式状态与长期决策分别见
> `docs/CURRENT_STATUS.md` 与 `docs/DECISION_LOG.md`（仅当前任务需要时读取）。

- branch: `master`（tracking `origin/master`）
- remote HEAD: `origin/master`；以 `git fetch` + `git rev-parse origin/master` 的实时
  结果为准，本文件不保存历史 PR/CI/artifact 快照。
- current task: 治理规则优化 —— FAST/STRICT PATH、最小 HANDOFF、CURRENT_STATUS /
  DECISION_LOG 更新节奏与 REMOTE_RECOVERY_CHECKPOINT（本 commit 已 push 到 master）。
- completed:
  - `AGENTS.md` 改为 FAST PATH / STRICT PATH 分级验证；普通开发只需检查 working tree、
    branch、HEAD、remote+fetch 并读取本文件。
  - `HANDOFF.md` 精简为最小恢复入口，不再堆叠历史快照。
  - `CURRENT_STATUS.md` 只在正式状态实质变化时更新；`DECISION_LOG.md` 只记录长期约束
    决定（本轮已记录对应 decision）。
  - 与旧表述直接冲突的 `docs/DEVELOPMENT_BOOTSTRAP.md`、`docs/FROZEN_ARTIFACT_POLICY.md`
    及治理测试已同步。
  - 未改动交易逻辑、研究逻辑、策略参数、数据口径、选股规则或 artifact。
- next action: 无强制业务下一步。恢复时按下方流程从 `master` 继续；正式状态发生实质
  变化才更新 `CURRENT_STATUS.md`，新的长期约束决定才写入 `DECISION_LOG.md`。
- blockers: 无当前任务 blocker。
- open user decisions: 无。

## New-device / new-session recovery

```text
git fetch
读取 HANDOFF.md
切换对应 branch
git pull --ff-only
git status
git rev-parse HEAD
```

若 branch、HEAD 与本文件中的 current task 状态一致，直接继续；不一致时只核对该任务
实际依赖的 live Git/GitHub 状态，不执行完整项目审计。

`REMOTE_RECOVERY_CHECKPOINT`：本 commit 已 push 到 `origin/master`；HANDOFF 指向
`master` / `origin/master`；继续当前任务不依赖仅存在于本机的未推送状态。
