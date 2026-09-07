# HANDOFF — 跨设备最小恢复入口

> 恢复链：remote Git → branch → remote HEAD → HANDOFF.md → next action。
> 本文件不是历史归档；历史 provenance 在 Git 历史中，正式状态与长期决策分别见
> `docs/CURRENT_STATUS.md` 与 `docs/DECISION_LOG.md`（仅当前任务需要时读取）。

- branch: `codex/hithink-http-transient-20260907`; formal capture code SHA
  `39cbd7cf2335ebee1cc7a81faee47c744c737fc3` (`fix: retry transient HiThink HTTP failures`).
- source intake: the bounded acquisition fix was committed from the verified baseline
  `9e2a32911433242df6cb4a963f78fe8868071a64`; tracked source files remain clean apart from
  the committed fix and this governance checkpoint. Generated T-close evidence is kept
  untracked and is not used to alter source files.
- current task: complete the 2026-09-07 post-close candidate-bound V3 capture, exact external
  recovery/readback, and frozen-prerequisite audit; do not auto-freeze.
- completed: HiThink `000002.SZ` diagnostic evidence was sufficient to classify the failure as
  HTTP 429 (`request limit exceeded`) with response bytes received. The shared transient
  classifier now covers 408/429/5xx while preserving the existing three-attempt and Tencent
  fallback contracts. A new clean evidence root was captured at the new code SHA.
- completed: package `data/prospective_inputs/20260907/2026-09-07_fe54be9be5c5959bd3d690adab2423e7a89f19e4498fb1df927c142f8dab9e4c.json` is
  `READY_FOR_STRATEGY_EVALUATION`; source evidence is 10,677 raw/sidecar pairs, all complete,
  all code SHA `39cbd7cf2335ebee1cc7a81faee47c744c737fc3`, and zero new `UNKNOWN_ORIGIN`.
- completed: B `B_BREAKOUT_RETEST_LEGACY_V1_1` succeeded with raw qualified=26, ST excluded=1,
  final non-ST=25; canonical watchlist is `data/watchlist_20260907.json`.
- completed: formal Drive recovery inventory (14 package chunks + 15 source chunks + one
  chunks40 manifest) was independently raw-fetched; every file matched its manifest byte length
  and SHA-256. Target folder is
  `ashare_watchlist/t_close_20260907_v3_39cbd7cf`.
- formal project state: `development candidate`
- active new strategy research: `NONE / PAUSED / PHASE_COMPLETE`
- blockers: none for the current package, evidence, B output, or persistent recovery. The
  remaining user decision is whether to freeze the candidate; this task does not perform that
  action.
- artifact snapshot: package file SHA
  `63fa8effea45cc329035dd97dbe64dfe9d84e899fbb24623190143811e08cc3`, generation fingerprint
  `fe54be9be5c5959bd3d690adab2423e7a89f19e4498fb1df927c142f8dab9e4c`, content SHA
  `792442ff35b5f1e5858180d3e6fc8965c661e4fd6e0c3abd5f9247d90dd6e31e`, watchlist SHA
  `5a99273b6304621acbf7bba2423a6e372668348a31ac436021caf5f5855db100`, candidate count 25.
- next action: user freeze decision. Keep Final OOS sealed/unread, C unread, old D not
  reconstructed, and the forbidden continuous-speed-probe directory untouched.
- terminal marker: `FROZEN_CANDIDATE_READY_FOR_USER_DECISION`.

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

`REMOTE_RECOVERY_CHECKPOINT`：bounded branch `codex/hithink-http-transient-20260907` is pushed
to `origin/codex/hithink-http-transient-20260907` at governance HEAD `e1b9775`. The generated
evidence remains locally recoverable from the recorded paths and externally recoverable from the
private Drive target; the formal recovery inventory is recorded in the audit and chunks40
manifest.
