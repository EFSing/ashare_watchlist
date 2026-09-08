# HANDOFF — 跨设备最小恢复入口

> 恢复链：remote Git → branch → remote HEAD → HANDOFF.md → next action。
> 本文件不是历史归档；历史 provenance 在 Git 历史中，正式状态与长期决策分别见
> `docs/CURRENT_STATUS.md` 与 `docs/DECISION_LOG.md`（仅当前任务需要时读取）。

- branch: `codex/daily-close-bundle-html-report`; based on live `master@52484a82e4a2700372c85c47991f62717d4b1196`.
- recovery pointer: this task's pushed `origin/codex/daily-close-bundle-html-report` is the
  authoritative recovery branch after the source commit is pushed. At recovery time, run
  `git rev-parse HEAD` and `git rev-parse @{u}` and require the two values to be equal; do not
  use this file's or any governance commit's SHA as the recovery truth.
- current task: `REPAIR_PRE_T_PLUS_1_TRACKER_STATE`. Live governance reconciliation is closed:
  PR #41 is merged, review cleanup PR #42 is merged into master, post-merge correctness run
  `34140697889` is `completed / success` with exact head, and formal Delivery Ladder is
  `frozen candidate`.
- frozen candidate identity: strategy `B_BREAKOUT_RETEST_LEGACY_V1_1`; spec SHA
  `f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd`; package SHA
  `d3bbdc7275fe32fd8763eba03fb987fad2308eb43d6149919829b0d5ec462ba4`; fingerprint
  `93882eecb2f37d4c0653864bd54dbbe80c19334b7913439ef3f6939a69ef5db8`; watchlist SHA
  `f58059cd5269f8ac5cd10da357a2bd008a76ef84feaa399846d74ad7daa4b5fc`.
- T+1 correction: 34 eligible 20260908 signals contained invalid same-list-day execution
  observations/state (58 violating fields/observation categories). Reset all 34 to pending,
  null execution fields, zero days and empty observations. Earlier 11/25 signals and all
  review point identities/schedules remain unchanged. Validation rejects execution dates
  <= signal date. Same-day update is a complete no-op and fetches no new-signal quotes.
- completed: current prospective review is bounded at `2026-09-03`, exact strategy
  `B_BREAKOUT_RETEST_LEGACY_V1_1`, and schema-valid canonical membership. Ingest skips
  legacy/out-of-scope files. CLI cleanup validates KEEP before removal; conflicting
  stable identities fail closed. Renderer applies the same boundary as defense in depth.
- contamination correction: the prior HTML smoke's 12 expired rows came from an out-of-scope
  20260820 list. Fourteen old tracker records were two versions of seven old candidates
  (`legacy-v1` from v1 migration and `watchlist-v1` from unbounded ingest). They are removed
  from the current tracker; the original 20260820 watchlist bytes remain unchanged.
- continuity: exact Drive bytes restored 20260903 (11 candidates, SHA
  `50f0717e55daaf4435e1d25b4f1d029109c566d72d63a1fc566f263cdf0fb085`) and 20260907
  (25 candidates, SHA `5a99273b6304621acbf7bba2423a6e372668348a31ac436021caf5f5855db100`).
  20260908 remains exact 34 candidates with the SHA above. Current tracker counts are
  11 / 25 / 34; its 34 new-signal records are now repaired to pre-execution state, without replay.
- recovery sources: 9/3 Drive file `1N-G0LVvMtotffm5Tdq-2-f4I-fZkuTUq`; 9/7 formal
  chunks40 manifest `1qU6VC-_hCs59ZHHHxhQ9hv9z4y-2PHBs`, package-output chunk 014
  `1PPHCZfD-B7f5vRHhJ75NwFvF2NCgHPZK`. The chunk SHA was verified, then only its
  `watchlist/watchlist_20260907.json` ZIP member was extracted and exact-SHA checked.
- smoke: `data/reports/daily_close_20260908.html` and `data/reports/latest.html` show
  34 new candidates, 25 exact previous-session signals, 11 older active signals and
  11 due T+3 snapshots. The 36 historical signals lack 9/8 observations: OHLC remains
  missing, no historical quotes or observations were fabricated. No 8/20 or duplicate
  signal IDs appear. The migration plan/removed-record audit is local operational output
  at `data/reports/prospective_cleanup_20260908.json`.
- observation compatibility: future observations preserve quote open; old observations
  without open remain missing. Update does not execute a signal on its list day (T+1).
- validation: 51 focused tests and 398 full pytest tests passed; compileall, diff check,
  exact-byte continuity and structured HTML smoke passed. Exact-head CI must be read live
  for the pushed head. Classification remained correctness blocker / STRICT PATH.
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
- terminal marker: `T_PLUS_1_TRACKER_STATE_REPAIRED_PR_READY_FOR_USER_MERGE_DECISION`.

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
