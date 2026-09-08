# HANDOFF — 跨设备最小恢复入口

> 恢复链：remote Git → branch → remote HEAD → HANDOFF.md → next action。
> 本文件不是历史归档；历史 provenance 在 Git 历史中，正式状态与长期决策分别见
> `docs/CURRENT_STATUS.md` 与 `docs/DECISION_LOG.md`（仅当前任务需要时读取）。

- branch: `codex/daily-close-bundle-html-report`; based on live `master@52484a82e4a2700372c85c47991f62717d4b1196`.
- recovery pointer: this task's pushed `origin/codex/daily-close-bundle-html-report` is the
  authoritative recovery branch after the source commit is pushed. At recovery time, run
  `git rev-parse HEAD` and `git rev-parse @{u}` and require the two values to be equal; do not
  use this file's or any governance commit's SHA as the recovery truth.
- current task: `DAILY_CLOSE_BUNDLE_HTML_REPORT`. Live governance reconciliation is closed:
  PR #41 is merged, review cleanup PR #42 is merged into master, post-merge correctness run
  `34140697889` is `completed / success` with exact head, and formal Delivery Ladder is
  `frozen candidate`.
- frozen candidate identity: strategy `B_BREAKOUT_RETEST_LEGACY_V1_1`; spec SHA
  `f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd`; package SHA
  `d3bbdc7275fe32fd8763eba03fb987fad2308eb43d6149919829b0d5ec462ba4`; fingerprint
  `93882eecb2f37d4c0653864bd54dbbe80c19334b7913439ef3f6939a69ef5db8`; watchlist SHA
  `f58059cd5269f8ac5cd10da357a2bd008a76ef84feaa399846d74ad7daa4b5fc`.
- completed: the stale PR #42/open review-cleanup snapshot is superseded by live master truth;
  this bounded task adds only the daily-close renderer, fail-soft reporting integration,
  focused tests, README usage and the minimum governance reconciliation. Source commit
  `9162c0ef73ad07adc7533b85e0b78248c539b6ff` is pushed in PR #43.
- boundaries: do not promote, approve production, unseal/read Final OOS, read C, rebuild old D,
  tune B, change strategy semantics, start new research, or touch
  `data/validation/continuous_speed_probe/`. Package/source/watchlist bytes and Drive
  backup/readback are unchanged and remain exact.
- active new strategy research: `NONE / PAUSED / PHASE_COMPLETE`
- blockers: none for the frozen candidate or daily-close bundle. Final OOS remains
  `SEALED / UNREAD`; C remains unread; old D is not reconstructed; forbidden validation data
  remains untouched.
- next action: user merge decision on PR #43 after exact-head CI verification. Do not auto-merge.
- exact-head CI must always be re-read live for the current remote head; the previously
  verified implementation head passed both push and pull-request correctness checks before
  this governance-only handoff update.
- terminal marker: `DAILY_CLOSE_BUNDLE_HTML_REPORT_PR_READY_FOR_USER_MERGE_DECISION`.

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
`origin/codex/daily-close-bundle-html-report`, not a governance commit SHA. Recovery is valid
only when runtime verification shows `git rev-parse HEAD == git rev-parse @{u}`. The formal
package SHA, generation fingerprint and watchlist SHA above provide artifact identity; the
daily HTML is reproducible from canonical data and is intentionally not a source commit.
