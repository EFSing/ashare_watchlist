# HANDOFF — 跨设备最小恢复入口

> 恢复链：remote Git → branch → remote HEAD → HANDOFF.md → next action。
> 本文件不是历史归档；历史 provenance 在 Git 历史中，正式状态与长期决策分别见
> `docs/CURRENT_STATUS.md` 与 `docs/DECISION_LOG.md`（仅当前任务需要时读取）。

- branch: `codex/daily-lightweight-cloud-checkpoint`; directly based on
  `master@37551f88f34568f3d55a6ce602372e6135e20a61` after PR #43 was squash-merged.
  PR #43 is `MERGED`; post-merge master correctness run `34306373948` is
  `completed / success` at that exact SHA.
- current task: `DAILY_LIGHTWEIGHT_CLOUD_CHECKPOINT`; cloud branch exact head is
  `6ec9513186902b49e1fcc8451f81c0f6c5847f91`. PR #44 is OPEN / CLEAN / non-draft against
  `master@37551f88f34568f3d55a6ce602372e6135e20a61`; push correctness `34307324454` and
  PR correctness `34307530082` are both `completed / success`. Awaiting the user's merge decision.
- recovery pointer: this task's pushed `origin/codex/daily-lightweight-cloud-checkpoint` is the
  authoritative recovery branch after the source commit is pushed. At recovery time, run
  `git rev-parse HEAD` and `git rev-parse @{u}` and require the two values to be equal; do not
  use this file's or any governance commit's SHA as the recovery truth.
- prior task: `EXACT_DATE_IMMUTABLE_REVIEW_RECOVERY_AND_COMPLETENESS_GUARD`. PR #43 was
  squash-merged at `37551f88f34568f3d55a6ce602372e6135e20a61`; that task started from exact head
  `945b0fc16c0dde80aa4d795f049781834a7689a8` and kept the no-merge boundary.
  Live governance reconciliation is closed:
  PR #41 is merged, review cleanup PR #42 is merged into master, post-merge correctness run
  `34140697889` is `completed / success` with exact head, and formal Delivery Ladder is
  `frozen candidate`.
- frozen candidate identity: strategy `B_BREAKOUT_RETEST_LEGACY_V1_1`; spec SHA
  `f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd`; package SHA
  `d3bbdc7275fe32fd8763eba03fb987fad2308eb43d6149919829b0d5ec462ba4`; fingerprint
  `93882eecb2f37d4c0653864bd54dbbe80c19334b7913439ef3f6939a69ef5db8`; watchlist SHA
  `f58059cd5269f8ac5cd10da357a2bd008a76ef84feaa399846d74ad7daa4b5fc`.
- exact-date recovery policy: `EXACT_DATE_IMMUTABLE_EVIDENCE_RECOVERY_V1`; evidence root
  `data/t_close_evidence/20260908/20260908`; integrity `PASS`, raw/sidecar pairs `10598/10598`,
  `UNKNOWN_ORIGIN=0`, provider calls `0`. 9/7 execution `25/25`; 9/3 T+3 snapshot `11/11`;
  9/3 prior execution remains unavailable and is not reconstructed. Review guard is
  `REVIEW_OBSERVATION_INCOMPLETE` with execution `36 expected / 25 captured / 11 missing` and
  horizon `11 expected / 11 captured / 0 missing`.
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
  34 new candidates, 25 exact previous-session signals with 9/8 OHLC, 11 exact T+3 snapshots
  with `UNVERIFIED` return/path, and the top completeness warning. The 9/3 execution path is
  intentionally still missing; no historical quotes or observations were fabricated. No 8/20
  or duplicate signal IDs appear.
- observation compatibility: future observations preserve quote open and normal observations
  carry `LIVE_DAILY_TRACKER_QUOTE`; recovered observations carry the exact immutable recovery
  provenance. Old observations without provenance remain readable. Update does not execute a
  signal on its list day (T+1).
- validation: latest recovery/renderer/runner-focused set is 77 passed; the full repository
  suite is 423 passed when run with the repository `.venv` and a short Windows basetemp;
  compileall, diff check, exact-byte continuity and structured HTML smoke passed. Exact-head
  CI must be read live for the pushed head. Classification remained correctness blocker /
  STRICT PATH.
- boundaries: do not promote, approve production, unseal/read Final OOS, read C, rebuild old D,
  tune B, change strategy semantics, start new research, or touch
  `data/validation/continuous_speed_probe/`. Package/source/watchlist bytes and Drive
  backup/readback are unchanged and remain exact.
- active new strategy research: `NONE / PAUSED / PHASE_COMPLETE`
- blockers: none for the frozen candidate or daily-close bundle. Final OOS remains
  `SEALED / UNREAD`; C remains unread; old D is not reconstructed; forbidden validation data
  remains untouched.
- prior task outcome: PR #43 exact head and exact-head CI were re-read before its squash merge;
  master now contains the daily close bundle, exact-date recovery, current prospective boundary,
  T+1 invariant, and review completeness guard. The post-merge master correctness run passed.
- exact-head CI must always be re-read live for the current remote head; the current cloud head
  passed both push and pull-request correctness checks listed above.
- prior-task terminal marker: `PR43_SQUASH_MERGED_AND_POST_MERGE_CORRECTNESS_SUCCESS`.

## Current checkpoint — daily lightweight cloud checkpoint — 2026-09-09

The bounded follow-up is implemented on `codex/daily-lightweight-cloud-checkpoint`, now
replayed directly onto `master@37551f88f34568f3d55a6ce602372e6135e20a61` after PR #43's squash
merge. PR #43 is merged and the daily close bundle / exact-date recovery are formally in master.
The rebased implementation commit is
`b33b2ecbbb0b43b9a5c232acee6cccf8a2527f49`; the manifest records that code SHA because
subsequent governance/test-only commits may advance the branch head without changing checkpoint
implementation code.

The private Drive target is `ashare_watchlist/daily_checkpoints`:

- dated `20260908`: `watchlist_20260908.json`, `perf_tracker.json`,
  `daily_close_20260908.html`, and `daily_checkpoint_20260908.json`;
- fixed `latest`: `latest.html` and `latest_checkpoint.json`.

All six files were uploaded in the required order and read back from Drive with exact metadata,
length, and SHA-256 verification. Total payload is 389,472 bytes; the watchlist SHA remains
`f58059cd5269f8ac5cd10da357a2bd008a76ef84feaa399846d74ad7daa4b5fc`. Dated files are not
overwritten by latest failures, same-name SHA conflicts fail closed, and no remote object was
deleted. K-line/raw/sidecar/source evidence, prospective packages, formal chunks, and historical
archives were not uploaded by the daily checkpoint.

The real recovery smoke fetched the dated manifest, watchlist, tracker, and HTML from Drive,
verified identity/length/SHA, restored the lightweight canonical-shaped state in isolation, and
matched the local canonical bytes. Result: `LIGHTWEIGHT_CLOUD_RECOVERY_SMOKE_PASS`. The
read-only inventory is `data/reports/cloud_storage_inventory_20260908.json` with
`FORMAL_KEEP=62`, `DAILY_KEEP=6`, `REDUNDANT_INTERMEDIATE_CANDIDATE=29`,
`UNKNOWN_DO_NOT_DELETE=0`; remote deletes remain `0`.

The runner remains fail-soft: it emits `[CLOUD] VERIFIED` when an injected authenticated Drive
adapter completes, or `[CLOUD] FAILED <exact reason>` without changing canonical local state.
There is no automatic scheduler. The terminal marker for this bounded follow-up is
`DAILY_LIGHTWEIGHT_CLOUD_CHECKPOINT_PR_READY_FOR_USER_MERGE_DECISION`.

Validation is complete: focused cloud/runner tests `18 passed`; full repository suite
`438 passed, 2 skipped, 8 warnings` (the two skips are for the intentionally unavailable local
immutable evidence fixture); compileall and `git diff --check` pass. Push correctness is
`34307324454`, PR correctness is `34307530082`, both exact-head `completed / success`.
Formal Delivery Ladder remains `frozen candidate`; Final OOS remains `SEALED / UNREAD`; C remains
unread; old D is not reconstructed.

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
`origin/codex/daily-lightweight-cloud-checkpoint`, not a governance commit SHA. Recovery is valid
only when runtime verification shows `git rev-parse HEAD == git rev-parse @{u}`. The formal
package SHA, generation fingerprint and watchlist SHA above provide artifact identity; the
daily HTML is reproducible from canonical data and is intentionally not a source commit.
