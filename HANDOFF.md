# HANDOFF — 跨设备最小恢复入口

> 恢复链：remote Git → branch → remote HEAD → HANDOFF.md → next action。
> 本文件不是历史归档；历史 provenance 在 Git 历史中，正式状态与长期决策分别见
> `docs/CURRENT_STATUS.md` 与 `docs/DECISION_LOG.md`（仅当前任务需要时读取）。

## 2026-09-14 — DAILY_REPORT_EMAIL_AND_BARK_DELIVERY_V1 — implementation in progress

- classification: `PRODUCT INFRASTRUCTURE / REPORT DELIVERY / OPERATIONAL NOTIFICATION`；不是
  strategy research。Intake 从实时 `origin/master`
  `c1bf5d6d36b1bfd84b62447afeb98e1a42940cdd` 创建独立 branch
  `codex/daily-report-email-bark-delivery`；本地仅有设备生成的未跟踪
  `ashare_watchlist.egg-info/`，未纳入修改。
- scope: 新增 `scripts/daily_report_delivery.py`，复用现有 canonical HTML；workflow 增加
  Email/Bark、BJT 用户可见命名、production failure 无附件、`delivery-test` 与 bounded
  per-channel retry。正式成功投递只在 canonical runtime-state 首次 push 成功后发生。
- receipt: `data/delivery/daily_delivery_YYYYMMDD.json` 是 operational-only durable receipt；
  runtime-state allowlist 只接受这一种 dated filename，不扩大为通配目录。receipt 绑定当天
  report SHA；同 SHA 双成功返回 `ALREADY_DELIVERED`，只重试失败 channel，SHA 冲突 fail closed。
- invariants: `B_BREAKOUT_RETEST_LEGACY_V1_1`、strategy/spec、candidate qualification、
  score/ranking/trigger/stop/target/RR/T+1、Main Board policy、shadow、tracker、provider
  acquisition、historical artifacts、existing 17:17/18:17 BJT schedule 与 canonical report
  filenames unchanged。Final OOS remains `SEALED / UNREAD`；forbidden probe directory untouched。
- validation so far: delivery targeted `23 passed`；cloud runtime/runner targeted `42 passed`；
  final full-suite run `571 passed, 2 skipped, 10 warnings`. `compileall` and `git diff --check`
  passed. Next: commit/push, open PR, and verify exact-head CI. No provider call or delivery-test
  dispatch has been made.
- terminal marker for this checkpoint: `REPORT_DELIVERY_IMPLEMENTATION_READY_FOR_FINAL_VALIDATION`。

## 2026-09-14 — MOBILE_DAILY_CLOSE_REPORT_6_3_INCH_OPTIMIZATION_V1 — merged

- classification: P3 product usability；presentation-only responsive optimization，服务
  actionable watchlist usable gate，不是 research、strategy 或 data semantic change。
- PR #53 (`feat: optimize daily close report for mobile`) from
  `codex/mobile-daily-report-63` was squash-merged；implementation head
  `42de5ccde62fe9ea256398d2dfbc06ef911f5151`，merge SHA
  `0c6f7e0fb579a411653eaebd6c385d4c9cb45099`。
- same self-contained daily close HTML now targets `390–430 CSS px` portrait，supports
  `360 CSS px`，uses one-column/2-column mobile grids，watchlist cards retain rank/code/name/
  score/state plus trigger/stop/target/RR，and wide trade/audit tables retain contained touch
  horizontal scrolling。Desktop/tablet layout remains on the existing shared renderer path。
- exact-head PR correctness run `34815050549` and post-merge master correctness run
  `34815229243` are `success`；Final OOS was not read，historical HTML was not rewritten，and
  `data/validation/continuous_speed_probe/` was not touched。
- browser visual smoke was not completed because the available browser security policy blocks
  local `file://` HTML；no browser dependency was added。
- terminal marker: `MOBILE_DAILY_CLOSE_REPORT_RESPONSIVE_ACTIVE`。

## 2026-09-14 — source merged; cloud runtime waiting for the required secret

- PR #50 (`feat: add unattended daily cloud runtime`) was squash-merged into `master`: final
  implementation head `468411f661211eb74140d89a7f489587bf8821a8`, merge SHA
  `cf1bbf53e4727bffdc6b1096f3d61b9bc5e03df4`; `origin/master` was fetched and matches the merge
  SHA. Post-merge correctness run `34771128198` is exact-head `success`.
- the remote `runtime-state` branch exists at `140d8dce20d2aa4a16802787ca9f8342390f48a7` and is
  operational-state-only. It contains the validated formal B watchlists, tracker, and final
  reports; stale checkpoint manifests and the legacy non-B 2026-08-20 list were omitted. The
  2026-09-11 watchlist SHA remains
  `80e6198e8e8af869d6718f14874be8e6eaa36cf3f63e7af1f381fb83c78db12b`.
- the master workflow schedule is active at 17:17 BJT primary / 18:17 BJT bounded retry with
  XSHG gating, isolated temporary data, and no raw/intermediate persistence. No production
  T-close run, weekend backfill, or
  manual cloud preflight was dispatched during this deployment session.
- repository Actions secret metadata currently reports zero configured secrets. The required
  `HITHINK_FINANCE_API_KEY` therefore cannot be verified from Codex; do not dispatch production
  until the user adds it in GitHub: `Settings → Secrets and variables → Actions → New repository
  secret`, name `HITHINK_FINANCE_API_KEY`, paste the provider key, and save. Never place the value
  in Git, workflow text, logs, or runtime-state.
- terminal marker: `GITHUB_ACTIONS_HITHINK_SECRET_REQUIRED`; after the one-time user action,
  dispatch `daily-t-close` with `mode=preflight-only` and verify the cloud preflight before the
  first genuine scheduled XSHG T-close.

## 2026-09-14 — GitHub Actions unattended cloud runtime implementation in progress

- live source base is `origin/master` at `306db219a8a9afdbb755450a184d43cdd9d95998`;
  implementation branch is `codex/daily-unattended-github-actions`.
- scope is deployment infrastructure only: `.github/workflows/daily_t_close.yml`, an explicit
  runtime-state allowlist/restore helper, a cloud-only ephemeral rule-performance history read,
  the 61-bar shadow input sufficiency fix, tests, and governance docs. The production chain still
  enters through `scripts/t_close_runner.py`.
- cloud compute is an ephemeral GitHub-hosted `ubuntu-latest` runner; `ASHARE_DATA_ROOT` is the
  runner temporary directory. Only canonical B watchlists, `perf_tracker`, optional shadow store,
  final reports, and verified daily checkpoint manifests may cross into the remote `runtime-state`
  branch. Raw evidence, provider responses, K-lines, quotes, sectors, generation inputs, and
  prospective inputs are not persisted or uploaded.
- remote `runtime-state` exists and was bootstrapped from the trusted local operational state at
  `a99cc7900f6b540132f99993e61acdcfbbe47430`; the legacy non-B 2026-08-20 list and stale local
  checkpoint manifests were omitted. The 2026-09-11 canonical watchlist SHA remains
  `80e6198e8e8af869d6718f14874be8e6eaa36cf3f63e7af1f381fb83c78db12b`.
- schedule is XSHG-gated at 18:17 and 19:17 BJT. The cloud workflow explicitly disables the
  unconfigured Drive connector while retaining the local manifest, and enables only the
  read-only in-memory historical reconstruction needed to preserve formal rule-price semantics.
- formal `B_BREAKOUT_RETEST_LEGACY_V1_1`, spec SHA
  `f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd`, Main Board-only policy,
  shadow definitions, Final OOS boundary, and historical artifacts are unchanged. Local full
  regression is `547 passed, 2 skipped, 11 warnings` with a short Windows basetemp.
- next action: run clean-room cross-device validation, commit/push source, open the PR, then use
  exact-head CI. Merge and cloud preflight remain gated by the requested correctness checks and
  the configured `HITHINK_FINANCE_API_KEY` secret.

## 2026-09-13 — PR #49 squash-merged; Main Board-only future production universe active

- live base at intake：`origin/master` 为 `88acfaed0372f3bc17bbbe969287b0731548c322`；
  implementation branch 为 `codex/main-board-only-universe`，PR #49 base 为 `master`，
  implementation commit 为 `5fb21198064f1641cc14de2d6475e0865a3c3774`。
- decision class：`USER_UNIVERSE_POLICY_DECISION`。未来 live universe 固定为既有 eligible universe ∩ Main Board，policy literal
  为 `ASHARE_MAIN_BOARD_ONLY_V1`；canonical `ASHARE_BOARD_TAXONOMY_V1` 将 00/60 系列归为
  `Main`，30 系列归为 `ChiNext`，68 系列归为 `STAR`，其余为 `Unknown`。该决定是生产范围
  约束，不是研究假设，不重做阈值或历史结论。
- implementation：live acquisition 在 quote/kline 前执行主板筛选；B-bound generation input
  在 evaluator 前再以同一 helper fail-closed 过滤，并把 policy 写入 future provenance、run
  manifest、generation identity 和 canonical watchlist。B evaluator、score、ranking、
  trigger、stop、target、RR 及 spec SHA 未改。
- effective boundary：`FIRST_GENUINE_T_CLOSE_RUN_AFTER_DEPLOYMENT`；不重跑 acquisition、不
  改写历史 watchlist/tracker/report/evidence。2026-09-11 watchlist SHA
  `80e6198e8e8af869d6718f14874be8e6eaa36cf3f63e7af1f381fb83c78db12b` 与 input package SHA
  `d729c3f4c3261f45036cd748cd75db2e191c7af3939c66f8707f802f6ca659cd` 已核对未变。
- shadow monitor 继续只消费 canonical watchlist，不增加第二个 board filter；旧 watchlist
  缺少 policy 字段仍可读取，历史 artifact 报告显示未记录而不伪造主板标签。
- merge outcome：PR #49 final head `76c4635c768db07c2d721aa5e0bdb1373f473aa5` 于
  `2026-09-13T15:04:08Z` squash-merged，merge SHA 为
  `14b43e81686f537debb713fc710f20c40a50ae63`；merge-time live `origin/master` 已核对为同一 SHA。
- post-merge governance：本条目所在 commit 是唯一的 docs-only governance sync；不改变生效边界、策略或历史 artifact。
- validation：project `.venv` full suite `529 passed, 10 warnings`；implementation head
  的 exact-head correctness push run `34763466511` 与 pull-request run `34763477122` 均
  `success`；merge 后已重新读取 PR #49、fetch origin，并核对 `origin/master`。
- terminal marker：`PR49_MERGED_MAIN_BOARD_ONLY_UNIVERSE_ACTIVE`。

## 2026-09-13 — PR #47/#48 merged; prospective shadow monitor active

- merge sequence：PR #47 从 head `1cf1ab419ab6e6bc6f6d1cfeadbef94b886d7ecf` squash-merged
  为 `9bb23d63bff058d13b64de8f7864ea1da6222ba2`；PR #48 retarget 到 `master` 后因正常
  squash graph divergence 重建 shadow-only head `1d31a6d2e4c0bd17370a4f99e328189ea2f9083a`，
  最终 squash-merged 为 `105289cb1e0da318a0f7d07bb1dfd7a2af8d5054`。该 graph divergence
  不是 `PROJECT_GOVERNANCE_STATE_CONFLICT`。
- current branch：`master`；PR #47/#48 已 merged，正式 master 现在包含 rule-price
  performance 与 `PROSPECTIVE_B_SHADOW_MONITOR_V1`。
- implementation：新增 `PROSPECTIVE_B_SHADOW_MONITOR_V1`，只在 canonical B
  watchlist 产生后旁路捕获 T-close market regime、reactivation volume path 与 structural
  context；只更新独立的 theoretical rule-price outcomes、`FAST_STOP` 和 +3/+5/+10
  XSHG-session STOP recovery。pre-outcome immutable，prospective 与 retrospective label
  分离，shadow failure fail-soft；不进入 qualification、score、ranking、trigger、stop、
  target、RR、generation、live acquisition qualification 或 canonical identity。
- prospective epoch：从实际首次 shadow capture 开始，不对部署前 signal 做 prospective
  backfill。固定 regime definition/version；reactivation 仅 continuous median descriptive
  aggregation，无 frozen/outcome-derived threshold。历史 stop-timing 只保留
  `REFERENCE_ONLY` metadata，不驱动策略修改。
- verified identity：正式 `B_BREAKOUT_RETEST_LEGACY_V1_1` spec SHA
  `f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd` unchanged；2026-09-11
  watchlist SHA `80e6198e8e8af869d6718f14874be8e6eaa36cf3f63e7af1f381fb83c78db12b` 与 input
  package SHA `d729c3f4c3261f45036cd748cd75db2e191c7af3939c66f8707f802f6ca659cd` unchanged；
  no 9/11 acquisition rerun。
- validation：shadow targeted tests `22 passed`; project `.venv` full suite `508 passed,
  10 warnings` using a short external Windows basetemp。未读取 Final OOS，未读取或触碰
  `data/validation/continuous_speed_probe/`，未 stage runtime data/report/watchlist/tracker/evidence。
- prospective epoch：尚未开始；首次真实 post-deployment T-close capture 时建立，不人为
  生成 snapshot，不把 retrospective data 标成 `PROSPECTIVE_CAPTURED`。
- terminal marker：`PR47_PR48_MERGED_PROSPECTIVE_SHADOW_MONITOR_ACTIVE`。

## Historical pre-merge — PR #47 rule-price strategy performance review ready

- current branch: `codex/weekend-tclose-backfill-20260911`; PR #47 remains `OPEN`, base
  `master`, and must not be merged automatically. Current pushed head is
  `ec578a65363e691bf9350b3d90765936161cd491`.
- implementation: added the derived
  `STRATEGY_RULE_PERFORMANCE_TRIGGER_STOP_TARGET_T1_V1` evaluator and made it the HTML/
  markdown primary performance model. Canonical `B_BREAKOUT_RETEST_LEGACY_V1_1` signals,
  watchlists, trigger/stop/target/RR, identities, generation logic and the existing
  `EXECUTION_MODEL_DAILY_OHLC_T1_V1` prospective audit remain intact. Rule-price replay is
  read-only: it never backfills tracker observations; T+3/T+5/T+10 remain fixed-horizon
  research snapshots; OPEN rule trades are theoretical and do not represent account holdings.
- 2026-09-11 as-of result: total 75; T+1 eligible 70; triggered 62; trigger rate 88.571429%;
  resolved TARGET 4; STOP 39; ambiguous 0; OPEN 19; UNTRIGGERED 8; win rate 9.302326%;
  average return -0.929683%; median return -2.014011%; payoff 5.992377; Profit Factor
  0.614603; expectancy -0.929683%; average R -0.276401; average holding 2.790698 sessions;
  average MFE 4.663325%; average MAE -4.137739%; performance data incomplete 0;
  prospective observation missing 70.
- validation: local full suite `486 passed, 10 warnings`; exact-head correctness runs
  `34706865006` and `34706862978` both `success` for the current head. Dated/latest HTML
  SHA is `f5b5a2b8c0353a03dc0d892a661dabe06dff67ba95d99e57c3ae131c6a3cd08f` for both.
  2026-09-11 watchlist SHA is
  `80e6198e8e8af869d6718f14874be8e6eaa36cf3f63e7af1f381fb83c78db12b`; input package SHA is
  `d729c3f4c3261f45036cd748cd75db2e191c7af3939c66f8707f802f6ca659cd`; no generation
  provider call was made, and rule-performance historical cache reads reported provider calls `0`.
- recovery: at continuation, re-read live `HEAD`, `@{u}`, PR #47 and exact-head CI; preserve
  the existing dirty `data/perf_tracker.json`, local evidence, untracked operational outputs,
  and temporary validation directories. Do not run `t_close_runner`, regenerate the watchlist,
  alter generation inputs, backfill prospective observations, or merge PR #47.
- terminal marker: `PR47_RULE_PERFORMANCE_AND_VISUAL_REVIEW_READY`.

## 2026-09-10 — PR #46 squash-merged; C→D migration and retention audit completed

- user-authorized squash merge completed. PR #46 was merged into `master` at merge commit
  `246700a72261bddde7da9148ecc18db0080da9be`; the source head at merge was
  `7ae76985f39c53e5d3a9bbb046cecc4cd7ddc167`, with exact-head push run `34466803595` and
  pull-request run `34466807793` both `success`. The source branch remains intact and was
  not deleted.
- after merge, re-read `origin/master`, the branch/ref, `HEAD`, `@{u}` and CI live at recovery;
  the merge commit and CI numbers above are persisted provenance, not permanent live-state
  invariants.
- D recovery workspace: `D:\ChatGPT\A股项目开发`, branch
  `codex/daily-report-review-usability-20260909` retains the migrated operational state;
  use live `master` as the code recovery base and require live `HEAD==@{u}` when continuing.
- migration: 85,372 selected local operational/evidence files, 9,332,547,439 bytes
  (8.692 GiB), copied without deleting C. T-close counts/bytes match C exactly;
  raw/sidecar pair sets are complete for each retained date; formal backup archive/chunk
  map is 50/50 exact; canonical package/watchlist/tracker/report/checkpoint hashes match;
  the local-only B diagnostic event file matches SHA
  `4bc5261c6d5329f48eded16caead33ebf0a49c462739f2f43d2dc33f0a88c3fe`.
- D validation: fresh venv/preflight, D-path smoke, report/runner targeted tests
  (`35 passed`), clean-checkout full suite (`444 passed, 2 skipped`), compileall and
  PR diff check passed. No acquisition/refetch, provider probe, remote delete or C-source
  deletion was performed.
- retention: as of `2026-09-10`, the rolling 20 XSHG sessions are
  `2026-08-14` through `2026-09-10`; all present T-close dates are inside the window,
  so prune candidates are 0 files / 0 pairs / 0 bytes. Formal/recovery evidence and
  unknown/forbidden validation remain excluded. `DELETE=NO`.
- terminal marker: `PR46_SQUASH_MERGED`.

- branch: `codex/daily-report-review-usability-20260909`; this remains the recovery pointer for
  PR #46 and the local workspace migration audit.
- current task: `LOCAL_WORKSPACE_C_TO_D_MIGRATION_AND_EVIDENCE_RETENTION_AUDIT`; this is a
  bounded storage/recovery task and does not change strategy, watchlist, review, provider,
  T+1, research conclusions, or formal artifact semantics.
- recovery pointer: use `origin/codex/daily-report-review-usability-20260909` as the current
  handoff branch. At recovery time, run `git rev-parse HEAD` and `git rev-parse @{u}` and require
  the two values to be equal; do not use this file's or any governance commit's SHA as live truth.
- governance: at intake, PR #46 was open/unmerged and its live remote head was
  `6191489edae55f7389d24526292d502b1c5932bd`; exact-head correctness run `34347550977` was
  `completed / success`. The preceding current-state snapshot recorded `b64a5fa...` and
  `34347321149`; this is a bounded `PROJECT_GOVERNANCE_STATE_CONFLICT`, not a strategy or
  artifact-identity conflict. The old values remain historical provenance below.
- implementation: the review-oriented daily report and successful-run bundle wiring remain
  unchanged. This docs-only reconciliation creates a new branch head; re-read the live branch,
  PR and exact-head CI after push instead of treating this file as a permanent head/CI record.
- terminal marker: `PR46_SQUASH_MERGED`.
- completed: the daily HTML is now review-oriented (yesterday review → today's new list/T+1
  observation → rolling review → data quality → collapsed audit); current-date signals are
  explicitly `T_PLUS_1_OBSERVATION_PENDING`; historical missing, UNVERIFIED return, same-bar,
  acquisition and cloud checkpoint states remain separate. The successful T-close runner now
  attaches/persists `daily_close_bundle` using its exact success status. Canonical watchlist,
  tracker, strategy and review semantics are unchanged.
- validation: project `.venv` full suite is `444 passed, 2 skipped, 8 warnings`; targeted report/
  runner regression set is `35 passed`; `git diff --check` passed. Existing 20260909 evidence was
  read only: 10,601 raw/sidecar pairs span `18:05:30–18:21:30 BJT`; no acquisition rerun or
  operational artifact overwrite was performed. The local dated checkpoint remains
  `LOCAL_INPUTS_VERIFIED`, not remote cloud `VERIFIED`.
- next action: future work starts from live `master`. Do not delete routine K-line evidence,
  C-source data, or any remote object without a separate explicit authorization. Classification
  remains STRICT PATH with no correctness semantic change.
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

## Historical pre-merge checkpoint — daily lightweight cloud checkpoint — 2026-09-09

The section below is retained as pre-merge provenance. The live merged state is recorded above.

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
