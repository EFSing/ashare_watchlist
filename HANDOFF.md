# HANDOFF — 跨设备最小恢复入口

> 恢复链：remote Git → branch → remote HEAD → HANDOFF.md → next action。
> 本文件只保留当前恢复所需的最小事实，不承担历史归档职责；历史 provenance 在 Git 历史中，
> 正式状态与长期决策分别见 `docs/CURRENT_STATUS.md` 与 `docs/DECISION_LOG.md`。
> 若治理文字与实时 Git / PR / CI / runtime-state 冲突，先标记
> `PROJECT_GOVERNANCE_STATE_CONFLICT`，以实时证据完成 reconciliation 后再继续。

## 2026-09-17 — REMOVE_AKSHARE_FROM_PRODUCTION_CRITICAL_PATH_V1

- classification：`correctness blocker + product blocker`（STRICT PATH）。旧 acquisition chain
  的 AkShare exchange roster JSON 解码失败会在 universe 阶段阻断整单，直接影响每日可用路径。
- live reconciliation：本文件原顶层仍是 #69 的旧 snapshot；本任务依赖的实时状态为
  `origin/master=73912d6781b4524299a5bda28f03d16f8818ed79`、
  `origin/runtime-state=be8236629684b34dab5672df774918273536a5d9`，因此标记并完成最小
  `PROJECT_GOVERNANCE_STATE_CONFLICT` reconciliation。PR #60/#66/#67/#68 均保持 untouched。
- branch/worktree：`codex/remove-akshare-production-critical-path-v1`，独立 worktree
  `D:\dev\ashare-watchlist-remove-akshare-v1`，基于 live `origin/master`；implementation
  commit=`01c14f9358e3dc988cb3d5db24031d0c1a4579dd`。
- decision：HiThink Financial-API `/api/meta/tickers/list` 是 SH/SZ a-share live universe
  的直接来源；继续复用 `ASHARE_MAIN_BOARD_ONLY_V1` / 既有 Main Board classifier。AkShare
  roster production calls=`0`，不再做 exchange-roster intersection；HiThink empty/malformed/
  duplicate/identity/asset/exchange/policy-empty 仍 fail-closed。
- sector：AkShare/Sina `新浪行业` 仅为 `OPTIONAL_FAIL_SOFT`。完整成功时保持原 exact taxonomy；
  import/API/JSON/timeout/partial-read 失败时整体 `UNAVAILABLE_DEFAULTED`，所有 symbol 使用
  frozen `("-", 50, 0.0)`，不接入 THS/申万替代。
- verification：full pytest=`620 passed, 2 skipped, 10 warnings`；compileall 与
  `git diff --check` passed；Formal B spec SHA 保持
  `f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd`。Tencent/HiThink
  market-data fallback tests passed。
- boundaries：production dispatch=`0`，runtime-state remote mutation=`0`，Cloudflare mutation=`0`；
  Final OOS=`SEALED / UNREAD`，`data/validation/continuous_speed_probe/` 未读取或触碰。
- delivery：已 push branch 并创建 target=`master` 的 Draft PR #70
  (`https://github.com/EFSing/ashare_watchlist/pull/70`)；当前 PR head 与 CI 状态以 live GitHub
  为准，不自动 merge。

## 2026-09-17 — B_VOLUME_PROSPECTIVE_REPORT_OBSERVATION_V1

- classification：`research question (non-blocking) + product report integration`；任务只冻结并展示
  #68 的 prospective observation，不改变 Formal B、候选过滤、阈值、排序或交易语义。
- live intake：`origin/master=ba081f8aba834d636c5a0222d9a6067731a8f819`，
  `origin/runtime-state=55fdd5167911ed074df9212cbca01fdda1c58a6b`；独立 branch/worktree 为
  `codex/b-volume-prospective-report-observation-v1`，基于该 live master。
- #68 source head=`916916426f3af6d5e8a451c4baea0fa69a119378`，source protocol commit=
  `d0a477db3f375ef19fdec51bb091ac3162ea6278`。本任务先冻结的 protocol commit=
  `cebda9ec8d8c085424e4b674a3353204e90bd7a0`；实现 commit=
  `533838b14a7a38cba2ca8baf60e3dce02a4cd06c`。
- 冻结窗口为 breakout `i`、signal `T`、`R=i+1:T-1`，signal day excluded，level 复用
  `max(close[i-60:i])` 与 `_first_breakout_trace`。唯一三项观察为
  `up_down_volume_ratio`、`down_volume_share`、`pullback_volume_decay_ratio`；缺失保持缺失。
- 未来日报已接入 `回踩量能` 与 `量能衰减` 两张观察卡，删除可见的低价值“市场”和
  “再启动量能 → breakout”展示；保留底层 legacy shadow 字段，观察文案明确不参与筛选/排名。
- machine persistence=`ACTIVE`：复用现有 `shadow_monitor/b_shadow_monitor.json` 的
  `pre_outcome.volume_observation` 与 current-signal context，无 runtime-state schema redesign、
  历史日报回写或生产 dispatch。Formal B、threshold/rank、provider、Final OOS（SEALED / UNREAD）
  均 untouched；runtime-state remote mutation=`0`。
- verification：focused new test=`7 passed`；relevant suite=`94 passed, 2 warnings`；full
  pytest=`613 passed, 2 skipped, 10 warnings`；compileall 与 `git diff --check` passed。2 个 skip
  为既有大型 exact-date fixture 缺失。
- delivery：独立 PR #69 已创建并保持 `DRAFT`：
  https://github.com/EFSing/ashare_watchlist/pull/69 。PR head、exact-head CI 与 base
  mergeability 均属于 live GitHub 状态。Live PR head / exact-head CI must be re-verified at
  merge decision; transient PR head is not a governance invariant。不自动 merge
  #66/#67/#68/#60 或本 PR。
- terminal：`B_VOLUME_PROSPECTIVE_REPORT_GOVERNANCE_RECONCILED`；下一步仅在 merge decision
  时重新核验 PR #69 的 live head、exact-head CI、DRAFT 与 mergeability。

## 2026-09-17 — CLOUDFLARE_SECONDARY_DISPATCHER_RECONCILIATION_V1

- Independent branch: `codex/cloudflare-secondary-dispatcher-reconciliation-v1`;
  base at intake: `origin/master=9c3f011ebc06d33347372b3792ec28f11c505f40`,
  `origin/runtime-state=55fdd5167911ed074df9212cbca01fdda1c58a6b`.
  Fetch and resolve the branch's live remote HEAD when resuming; these are provenance.
- `PROJECT_GOVERNANCE_STATE_CONFLICT`: PR #64 is merged; earlier awaiting-merge
  entries are superseded. Account reads confirm `ashare-tclose-dispatcher` deployed,
  workers.dev enabled, Cron `25 9 * * 1-5` present, required secret configured.
  Earlier Cloudflare `PREPARED / NOT_ACTIVE` descriptions are superseded by these
  account facts; successful dispatch and actual PAT permission/expiry remain UNRESOLVED.
- Minimal implementation commit: `149f5e339d1c70d8c16b9c6bb90acb04131ab3d1`;
  explicit GitHub User-Agent and `workers_dev = true`, preserving deployed exposure.
  Node tests 3 passed; focused Python tests 136 passed; syntax/diff checks and
  Wrangler 4.133.0 deploy dry-run passed. Existing concurrency, ALREADY_COMPLETED,
  XSHG and acquisition-date gates remain the authorities.
- Next: inspect this branch's PR and exact-head CI, user merge decision, then
  separately authorize redeployment of this existing Worker. No secret/Cron change
  is justified by current evidence. No automatic merge or deployment.
- Production dispatch=0; Cloudflare account mutation=0; runtime-state mutation=0.
  Formal B/research/PR #60 untouched; Final OOS SEALED / UNREAD; prohibited directory
  not read or touched. Classification remains product blocker diagnostic (STRICT PATH).

## 2026-09-16 — PER_SYMBOL_PROVIDER_FAILURE_ISOLATION_V1

- live intake reconciliation：此前 persisted docs 仍记录 `origin/master=040e077b`；实时
  fetch 已核对 `origin/master=5a024185206ca868ddf10c2e871a4a34edb1b878`，与用户本轮 intake
  预期一致。`origin/runtime-state=520d6fab222bf553caa3eeb29cc83176318626d0`，也与预期一致。
  该旧 snapshot 与当前依赖的 live master 已构成并完成最小
  `PROJECT_GOVERNANCE_STATE_CONFLICT` reconciliation；PR #63 已合并，PR #60 保持
  `OPEN / DIRTY` 且 untouched。
- user decision：采用窄化、fail-closed 的
  `PER_SYMBOL_PROVIDER_FAILURE_ISOLATION_V1`。只允许在 canonical production universe、
  正常 XSHG target session、Tencent quote 明确 `TRADED`、HiThink/Tencent historical 非空且
  结构有效、无 future/冲突/无效 OHLC/volume，且 latest historical date `< target_date` 时，
  隔离恰好一只 `TARGET_DAY_HISTORICAL_STALE`；第二只同类 stale 整单失败。
- implementation：独立 branch/worktree
  `codex/per-symbol-provider-failure-isolation-v1`；coverage record 同时写入 live package /
  generation fingerprint、canonical watchlist/run manifest、日报 HTML、checkpoint 和
  runtime-state validation。filtered evaluator input 为 canonical universe 减去唯一隔离股票；
  Formal B 与其 qualification/score/ranking/trigger/stop/target/RR/T+1/same-bar/spec SHA 不变。
- regression：fixture 已覆盖 605366.SH（quote traded、historical latest=`2026-09-14`、target
  `2026-09-15`）、single-stale continue、second-stale fail-closed、no-trade unchanged、
  future/missing-trade-proof fatal、report/checkpoint mismatch 和 degraded same-day idempotency。
- boundaries：provider live calls=`0`，production dispatch=`0`，runtime-state remote mutation=`NO`；
  Final OOS=`SEALED / UNREAD`，`data/validation/continuous_speed_probe/` 未读取或触碰，PR #60
  未触碰。
- delivery：implementation commit `b9fffa22ab11df4e68e078b522780703253842d9` 仅作为
  implementation/historical provenance 保留，不代表 PR #64 current head。实现已完成；PR #64
  当前保持 `OPEN / CLEAN / mergeable`，不自动 merge。
- live verification rule：exact-head push CI 与 PR CI 必须在 merge decision 时从 live GitHub 重新
  验证；任何 transient PR head 或 CI run ID 都不固化为长期 governance invariant。
- verification：project full pytest=`606 passed, 2 skipped, 11 warnings`（2 个 skip 是原有未提交
  的大型 exact-date fixture 缺失），compileall、git diff --check、Node dispatcher=`3 passed`。
  provider live calls=`0`，production dispatch=`0`，runtime-state remote mutation=`NO`。
- terminal：`PER_SYMBOL_PROVIDER_FAILURE_ISOLATION_V1_PR_READY_FOR_USER_MERGE_DECISION`，等待用户
  对 PR #64 作 merge decision；PR #60 untouched，Final OOS=`SEALED / UNREAD`，受禁目录未读取或触碰。

## 2026-09-15 — RUNTIME_STATE_HISTORICAL_CHECKPOINT_MUTABLE_TRACKER_VALIDATION_FIX_V1

- live reconciliation：此前本文件仍以 `origin/master=16f8e8a`、
  `runtime-state=1c8b2ec` 和 PR #61 未合并为当前入口；实时 fetch 已确认这是
  `PROJECT_GOVERNANCE_STATE_CONFLICT`。当前 live source 是
  `origin/master=040e077bbf208921798d2d5b1fa0bd2d51ba9a20`，master exact-head correctness
  run=`34938666579` 为 `success`；live `origin/runtime-state` 是
  `520d6fab222bf553caa3eeb29cc83176318626d0`。PR #61/#62 已合并，PR #60 仍为
  `OPEN / CONFLICTING`，本任务不触碰 PR #60。
- failure evidence：run `34969498897` (`workflow_dispatch`, `2026-09-15`, `manual`) 的
  canonical chain 输出 success，但在 `canonical-output-validation` 因
  `checkpoint SHA/length mismatch: perf_tracker` 失败；Email/Bark 均 success。该 run 未
  canonical-persist，runtime-state 只新增 operational failure notice，未新增
  20260915 success receipt/checkpoint。
- current task：从 live `origin/master` 创建独立 branch/worktree
  `codex/runtime-state-checkpoint-validation-fix-20260915`，只修复历史 checkpoint 对
  mutable latest-state 的错误绑定并增加跨日回归测试；当前尚未 dispatch production、调用
  provider 或修改 remote `runtime-state`。
- semantics：历史 manifest 继续严格检查 JSON/schema、date/filename、record structure、
  文件存在性和 dated immutable `watchlist`/`dated_html` identity；历史
  `perf_tracker`/`latest_html` 允许合法跨日演进。`completed_run_status(target_date)` 对目标日
  全部四类 payload 仍 strict，failure notice 继续 operational-only，不阻止未来 success。
- boundaries：Formal B、universe、provider/shadow、scheduler、PR #60、Final OOS
  (`SEALED / UNREAD`) 及 `data/validation/continuous_speed_probe/` 均保持不变。

## 2026-09-15 — CURRENT RECOVERY CHECKPOINT

- source authority：`origin/master`。恢复时必须先 `git fetch origin` 并实时读取
  `origin/master`；本次 reconciliation 的 live base 为
  `16f8e8a17a662d5288ff0c36bcebbedad342a320`，但该 SHA 不是永久真相。
- production-state authority：remote `runtime-state` branch；本地 `data/` 仅为
  cache / reproduction，不得覆盖远端生产状态。恢复时同时核对 live `runtime-state` HEAD。
- live `runtime-state` intake HEAD：`1c8b2eca3792aebf327557fe9279b88a177b0545`；恢复时继续
  以实时 remote branch 为准。
- cloud runtime：`DAILY_UNATTENDED_GITHUB_ACTIONS_CLOUD_RUNTIME_V1` 已部署；production
  schedule 为 `17:17 BJT` primary + `18:17 BJT` bounded retry，XSHG gate、
  `ALREADY_COMPLETED`、non-canceling concurrency、ephemeral provider/raw-data policy 保持不变。
- delivery：PR #54 已合并；Email + Bark delivery secrets 已由用户在 GitHub Actions
  repository secrets 配置。2026-09-14 的 `delivery-test` run `34831754237` 在
  `master@3b70ef138d5fbef18e1bf0b37782ddf9ee070b24` 完成并 `success`：
  `email_status=SUCCESS`、`bark_status=SUCCESS`、
  `status=REPORT_DELIVERY_CHANNELS_VERIFIED`、market-data provider calls=`0`、
  runtime-state mutation=`NO`、formal delivery receipt=`NOT_CREATED`（test mode 正常行为）。
 之前 `REPORT_DELIVERY_SECRETS_REQUIRED` / “delivery-test 未执行”的治理描述已被本条实时
  reconciliation supersede；后续正式成功日报只在 canonical runtime-state 已成功持久化后投递。
- genuine production：run `34850228463` 已于 `master@64bba1d` 成功；late schedule run
  `34865169737` 成功；cross-day delayed schedule run `34868158949` 失败并暴露旧日期绑定 bug。
- governance：旧的 “首笔 genuine production” future next-action 与当前 live runs 冲突，已标记并
  完成 `PROJECT_GOVERNANCE_STATE_CONFLICT` reconciliation。PR #60 仍为 open，未 merge、未改写。
- mobile report：`MOBILE_DAILY_CLOSE_REPORT_RESPONSIVE_ACTIVE`；同一份自包含 HTML 针对
  `390–430 CSS px` 手机竖屏优化，最低支持约 `360 CSS px`，不生成第二份 mobile report。
- universe：未来 production 仅 `ASHARE_MAIN_BOARD_ONLY_V1`；ChiNext/STAR 不进入未来正式名单。
- formal strategy：`B_BREAKOUT_RETEST_LEGACY_V1_1` 冻结；spec SHA
  `f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd`。不得借基础设施、
  报告或测试任务修改 qualification / score / ranking / trigger / stop / target / RR / T+1。
- shadow：`PROSPECTIVE_B_SHADOW_MONITOR_V1` 继续 observational / fail-soft，不进入正式 B identity。
- Final OOS：`SEALED / UNREAD`；不得读取或触碰 `data/validation/continuous_speed_probe/`。
- historical artifacts：不得为普通恢复、报告或测试任务重跑历史 acquisition、重写历史
  watchlist/tracker/report/evidence。
- current task：独立 branch/worktree `codex/cloud-schedule-resilience-v1` 的 repo-side
  implementation 已通过 PR #61 squash-merged；merge commit=`16f8e8a17a662d5288ff0c36bcebbedad342a320`。
  最终 PR exact-head correctness run=`34922737694`、push correctness run=`34922734570` 均为
  `success`，合并后的 master push correctness run=`34926519440` 也为 `success`。schedule
  resilience 已进入 `master`；Cloudflare 仍为 `PREPARED / NOT_ACTIVE`。
- next action：等待用户提供 Cloudflare 所需的最小 external PAT/secret/account authorization
  后再部署或启用 secondary dispatcher；本次不 dispatch genuine production，不修改 PR #60。

## Local Windows test workspace convention

在用户当前 Windows 工作站上，所有本地测试临时目录统一收敛到：

```text
D:\Temp\ashare-tests\<task-name>-<timestamp>
```

约束：

- 若 `D:\Temp\ashare-tests` 不存在，可由测试任务自动创建。
- pytest `--basetemp`、临时 `ASHARE_DATA_ROOT`、HTML smoke、临时报告与测试中间产物优先放在
  本任务自己的上述子目录中；不要再向 `D:\` 根目录生成 `pytest-ashare-*`。
- 测试完成后清理**本任务自己创建的**临时子目录；失败路径也应尽量通过 `finally` 或明确的
  bounded cleanup 收尾。
- cleanup 只能限定在 `D:\Temp\ashare-tests` 下，并且只能删除本任务拥有的子目录。
- 禁止为了清理执行 `git clean`、`git reset --hard`、`git restore`，禁止删除 repo `data/`、
  `runtime-state`、用户已有目录、其他任务目录、正式 evidence 或任何不属于本任务的文件。
- 这只是本地开发/测试工作区约定，**不得把 `D:\Temp` 硬编码进 production code、GitHub
  Actions 或跨平台路径逻辑**。在没有 D: 盘的设备/云 runner 上，使用该设备的隔离临时目录
  等价物并保持同样的 ownership + bounded-cleanup 规则。

## Recovery commands

```text
git remote -v
git fetch --all --prune
git status --short --branch
git branch --show-current
git rev-parse HEAD
git rev-parse origin/master
```

若 tracked working tree clean 且当前 branch 仅落后 upstream，可 `git pull --ff-only`；
若有无关本地修改，不得覆盖、reset、restore 或删除，改用从实时 `origin/master` 创建的独立
branch/worktree。恢复时优先核对 task-relevant live Git / PR / CI / runtime-state，不做无关的
全项目重复审计。
