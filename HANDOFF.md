# HANDOFF — 跨设备最小恢复入口

> 恢复链：remote Git → branch → remote HEAD → HANDOFF.md → next action。
> 本文件只保留当前恢复所需的最小事实，不承担历史归档职责；历史 provenance 在 Git 历史中，
> 正式状态与长期决策分别见 `docs/CURRENT_STATUS.md` 与 `docs/DECISION_LOG.md`。
> 若治理文字与实时 Git / PR / CI / runtime-state 冲突，先标记
> `PROJECT_GOVERNANCE_STATE_CONFLICT`，以实时证据完成 reconciliation 后再继续。

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
- delivery：commit `b9fffa22ab11df4e68e078b522780703253842d9` 已 push，独立 PR #64 已创建，base
  `master`=`5a024185206ca868ddf10c2e871a4a34edb1b878`。push correctness run=`35108470922` 与
  pull-request correctness run=`35108504369` 均 `success`，且 workflow head exact 匹配该 commit；
  PR 状态保持 `OPEN`，不自动 merge。
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
