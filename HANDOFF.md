# HANDOFF — 跨设备最小恢复入口

> 恢复链：remote Git → branch → remote HEAD → HANDOFF.md → next action。
> 本文件不是历史归档；历史 provenance 在 Git 历史中，正式状态与长期决策分别见
> `docs/CURRENT_STATUS.md` 与 `docs/DECISION_LOG.md`（仅当前任务需要时读取）。

- branch: `master`（tracking `origin/master`）
- remote HEAD: `origin/master`；以下方恢复流程实时解析确认。
- current task: 无进行中的治理任务；恢复状态已回到项目主线。
- completed: governance optimization completed —— FAST/STRICT PATH、最小 HANDOFF 与
  sync-first 恢复流程均已生效；不再把治理优化当作项目恢复终点。
- formal project state: `development candidate`
- active new strategy research: `NONE / PAUSED / PHASE_COMPLETE`
- blockers: `P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE`
- open user decisions: none
- next action: 从上述正式项目状态继续，或执行用户下一项明确开发任务；不要再次以治理
  优化作为项目任务。

## New-device / new-session recovery

```text
git remote -v
git fetch --all --prune
git status --short --branch
git branch --show-current
git rev-parse HEAD
git rev-parse @{u}
```

若 tracked working tree clean 且当前 branch 仅落后 upstream，执行 `git pull --ff-only`；
随后读取本文件，确认 branch、HEAD 与 current task 状态一致后直接继续。不一致时只核对
该任务实际依赖的 live Git/GitHub 状态，不执行完整项目审计。

`REMOTE_RECOVERY_CHECKPOINT`：本 commit 已 push 到 `origin/master`；HANDOFF 指向
`master` / `origin/master`；继续当前项目主线不依赖仅存在于本机的未推送状态。
