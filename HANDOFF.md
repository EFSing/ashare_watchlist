# HANDOFF — 跨设备最小恢复入口

> 恢复链：remote Git → branch → remote HEAD → HANDOFF.md → next action。
> 本文件不是历史归档；历史 provenance 在 Git 历史中，正式状态与长期决策分别见
> `docs/CURRENT_STATUS.md` 与 `docs/DECISION_LOG.md`（仅当前任务需要时读取）。

- branch: `codex/review-report-project-boundary-cleanup-20260907`; this bounded cleanup branch
  is based on live `master@3308c7ab8e403d459baf1bbfe873e7320d750317`.
- recovery pointer: `origin/codex/hithink-http-transient-20260907` is the authoritative Git
  recovery branch. At recovery time, run `git rev-parse HEAD` and `git rev-parse @{u}` and
  require the two values to be equal; do not use this file's or any governance commit's SHA
  as the recovery truth.
- current task: `REVIEW_REPORT_PROJECT_BOUNDARY_CLEANUP`. The post-merge governance conflict is
  closed: PR #41 is merged at `3308c7ab8e403d459baf1bbfe873e7320d750317`, correctness run
  `34133269448` is `completed / success` with exact head, and formal Delivery Ladder is
  `frozen candidate`.
- frozen candidate identity: strategy `B_BREAKOUT_RETEST_LEGACY_V1_1`; spec SHA
  `f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd`; package SHA
  `63fa8effea45cc329035dd97dbe64dfe9d84e899fbb24623190143811e08cc3a`; fingerprint
  `fe54be9be5c5959bd3d690adab2423e7a89f19e4498fb1df927c142f8dab9e4c`; watchlist SHA
  `5a99273b6304621acbf7bba2423a6e372668348a31ac436021caf5f5855db100`.
- completed: the review cleanup checkpoint was replayed onto the new master without replaying
  the old recovery/acquisition ancestry. The bounded implementation is committed and pushed
  in PR #42; its changes remain limited to review scripts, focused tests, README and review
  governance documentation.
- boundaries: do not promote, approve production, unseal/read Final OOS, read C, rebuild old D,
  tune B, change strategy semantics, start new research, or touch
  `data/validation/continuous_speed_probe/`. Package/source/watchlist bytes and Drive
  backup/readback are unchanged and remain exact.
- active new strategy research: `NONE / PAUSED / PHASE_COMPLETE`
- blockers: none for the frozen candidate, recovery, or review cleanup. Focused review tests,
  full pytest, compileall and diff checks passed; PR #42 is open against `master` and its
  exact-head CI must remain successful. No freeze blocker remains.
- next action: user merge decision on PR #42 after live exact-head CI verification. Do not
  auto-merge.
- terminal marker: `REVIEW_REPORT_PROJECT_BOUNDARY_CLEANUP_PR_READY_FOR_USER_MERGE_DECISION`.

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

`REMOTE_RECOVERY_CHECKPOINT`: the authoritative Git recovery pointer is the pushed remote branch
`origin/codex/hithink-http-transient-20260907`, not a governance commit SHA. Recovery is valid
only when runtime verification shows `git rev-parse HEAD == git rev-parse @{u}`. The formal
capture code SHA, package SHA, generation fingerprint, watchlist SHA, and private Drive target
below provide artifact identity; the generated evidence is externally recoverable from the
recorded private Drive inventory and chunks40 manifest.
