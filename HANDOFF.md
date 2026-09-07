# HANDOFF — 跨设备最小恢复入口

> 恢复链：remote Git → branch → remote HEAD → HANDOFF.md → next action。
> 本文件不是历史归档；历史 provenance 在 Git 历史中，正式状态与长期决策分别见
> `docs/CURRENT_STATUS.md` 与 `docs/DECISION_LOG.md`（仅当前任务需要时读取）。

- branch: `codex/p1-gate-20260907`（bounded governance reconciliation；base
  `origin/master@9757a12514e2d423e95ea7de6758ab033803ce2b`）
- source intake: local `master@38322b91f691b23e7ebaa10818a8733169aafab8` was behind
  `origin/master` by 14 commits; the task is isolated so local untracked evidence is not
  overwritten.
- current task: reconcile the stale P1 first-instance status against the verified
  2026-09-03 candidate-bound V3 input package; do not start a new capture before the
  2026-09-07 XSHG close.
- completed: the first real `LIVE_OBSERVED`, candidate-bound, V3-compliant input instance
  is verified for gate A. This closes the old "no live instance" wording only; it does not
  freeze B or promote any strategy.
- formal project state: `development candidate`
- active new strategy research: `NONE / PAUSED / PHASE_COMPLETE`
- blockers: `FROZEN_RECOVERY_PROVENANCE_PARTIAL_UNVERIFIED` — 170 source sidecars retain
  `UNKNOWN_ORIGIN`, and no persistent backup/readback of the candidate-bound package and
  its source evidence is recorded. The 6,422-byte watchlist Drive readback is output
  evidence only.
- artifact snapshot: package file SHA
  `a2e6da0865ff20316e4d9074f26e2cb3ba53995d2cb3e83a49f8c82988c0b38a`, generation
  fingerprint `eeb700c98a69a98fae3fa220851190a76de88984b0f451cc1ed275b2e487351f`, corrected
  B watchlist SHA `50f0717e55daaf4435e1d25b4f1d029109c566d72d63a1fc566f263cdf0fb085`,
  candidate count 11.
- open user/external decision: provide known-origin evidence plus persistent package
  recovery/readback, or explicitly authorize a new fully attested post-close capture; no
  local documentation change can manufacture either evidence.
- next action: remain pre-close and do not call providers. The verified preflight marker is
  `PRE_CLOSE_DIAGNOSTIC_READY`; overall terminal marker is
  `BLOCKED_REQUIRES_USER_OR_EXTERNAL_DECISION:FROZEN_RECOVERY_PROVENANCE_PARTIAL_UNVERIFIED`.

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
