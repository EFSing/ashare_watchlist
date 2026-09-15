# CURRENT STATUS

更新时间：2026-09-15（Asia/Shanghai）

本文件只记录当前有效状态；历史实现过程与旧 checkpoint 以 Git history / PR / CI 为 provenance，
长期约束理由见 `docs/DECISION_LOG.md`，跨设备接手动作见 `HANDOFF.md`。
恢复时必须实时读取 `origin/master`、相关 PR/CI 与 `runtime-state`，不得把本文 SHA 当永久真相。

## Governance reconciliation — 2026-09-15

此前治理文字仍记录 `REPORT_DELIVERY_SECRETS_REQUIRED`、delivery-test 未执行，以及
`HITHINK_FINANCE_API_KEY` 未配置；这些状态已被实时 GitHub evidence supersede，构成过
`PROJECT_GOVERNANCE_STATE_CONFLICT`。本次 docs-only reconciliation 以实时证据修正，
不改变任何策略、provider、runtime-state、watchlist、tracker、shadow 或 report 语义。

本次恢复又发现旧的 “首笔 genuine production 仍在未来” next-action 文字，且
`CURRENT_STATUS` 的 persisted live snapshot 早于当前远端；按契约标记并完成
`PROJECT_GOVERNANCE_STATE_CONFLICT` reconciliation。实时 Git/GitHub 状态优先，旧 SHA 仅保留
为历史 provenance，不构成当前 invariant。

Live source base at this reconciliation：
`origin/master=16f8e8a17a662d5288ff0c36bcebbedad342a320`。
Live `runtime-state` HEAD：
`1c8b2eca3792aebf327557fe9279b88a177b0545`。
恢复时仍必须重新 fetch，以实时 `origin/master` 为准。

## DAILY_UNATTENDED_GITHUB_ACTIONS_CLOUD_RUNTIME_V1 — active

GitHub Actions `daily-t-close` 已部署：

- primary：17:17 BJT
- bounded retry：18:17 BJT
- XSHG trading-day / close-window gate：active
- same-day `ALREADY_COMPLETED` idempotency：active
- concurrency：non-canceling
- cloud data root：ephemeral
- raw/provider/K-line/quote/sector/generation-input persistence：disabled
- production state authority：remote `runtime-state` branch
- Drive checkpoint in cloud：disabled

`HITHINK_FINANCE_API_KEY` 已在 Actions runtime 中可见为 configured secret（值不可读取、不可记录）。
此前“waiting for HITHINK secret”状态已失效。

实时 production evidence：run `34850228463`（`workflow_dispatch`，`success`，
`master@64bba1d`）为 genuine production；run `34865169737`（`schedule`，`success`）为
late schedule success；run `34868158949`（`schedule`，`failure`）暴露了旧 schedule
跨 BJT 午夜后把 runner 日期当成新 production target 的 bug。后续验证应针对本次修复后的
首次 production，而不是把 genuine production 当成尚未发生的节点。

PR #60 仍是 `OPEN`、base=`master`、head=`0a829193af5a761d3190d02543e9edd5b9312550`，
研究内容未进入 master，也不属于本次生产调度修复。

本次 `CLOUD_SCHEDULE_RESILIENCE_V1` repo-side implementation 已通过 PR #61 squash-merged
进入 `master`，merge commit=`16f8e8a17a662d5288ff0c36bcebbedad342a320`。最终 PR
exact-head correctness run=`34922737694` 与 push correctness run=`34922734570` 均为
`success`；合并后的 master push correctness run=`34926519440` 也为 `success`。本次任务未
dispatch genuine production；Cloudflare dispatcher 仍需外部授权后才可部署或启用。

## DAILY_REPORT_EMAIL_AND_BARK_DELIVERY_V1 — channels verified

PR #54 已 squash-merged；delivery-only infrastructure 保持在 canonical production engine 之外。
正式成功投递顺序固定为：canonical production success → canonical runtime-state persisted →
Email/Bark delivery → operational delivery receipt persisted。

必需的 Actions delivery secrets 已由用户配置；不记录任何 secret 值。
2026-09-14 手工 `delivery-test` 最终成功 run：

- run：`34831754237`
- source：`master@3b70ef138d5fbef18e1bf0b37782ddf9ee070b24`
- Email：`SUCCESS`
- Bark：`SUCCESS`
- status：`REPORT_DELIVERY_CHANNELS_VERIFIED`
- market-data provider calls：`0`
- runtime-state mutation：`NO`
- formal receipt：`NOT_CREATED`（delivery-test 的正确行为）

正式 Email subject：`YYYY-MM-DD HH:MM - A股每日收盘复盘报告`；附件显示名：
`YYYY-MM-DD_A股每日收盘复盘报告.html`。Bark 成功标题：`HH:MM - A股每日收盘复盘完成`。
时间均为实际完成/发送的 BJT，不使用 cron 固定时间冒充完成时间。

正式 delivery receipt schema：`DAILY_REPORT_DELIVERY_RECEIPT_V1`，路径仅允许
`data/delivery/daily_delivery_YYYYMMDD.json`；receipt 与当天 report SHA 绑定。同 SHA 且双通道
成功时为 `ALREADY_DELIVERED`；bounded retry 只补失败/缺失 channel；SHA 冲突 fail closed。

Terminal marker：`REPORT_DELIVERY_CHANNELS_VERIFIED`。

## MOBILE_DAILY_CLOSE_REPORT_RESPONSIVE_V1 — active

同一份 self-contained daily close HTML 同时服务 desktop/tablet/mobile：

- primary mobile target：390–430 CSS px portrait
- minimum：约 360 CSS px
- core KPI：mobile 2-column
- watchlist：mobile card layout，保留 trigger / stop / target / RR
- action facts：mobile 2-column
- research panels：mobile 1-column
- wide audit/trade tables：contained touch horizontal-scroll
- canonical report / data semantics：unchanged

历史 HTML 不因该 feature 被重写；后续正常 report generation 自动使用 responsive renderer。

Terminal marker：`MOBILE_DAILY_CLOSE_REPORT_RESPONSIVE_ACTIVE`。

## Formal strategy / universe / performance — unchanged

Formal B：`B_BREAKOUT_RETEST_LEGACY_V1_1`。

Frozen spec SHA：
`f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd`。

Production universe：`ASHARE_MAIN_BOARD_ONLY_V1`，canonical taxonomy
`ASHARE_BOARD_TAXONOMY_V1`；00/60 series Main，30 ChiNext，68 STAR，Unknown rejected。
Future production pipeline remains existing eligible A-share universe → Main Board-only → frozen B。

Formal performance model：`STRATEGY_RULE_PERFORMANCE_TRIGGER_STOP_TARGET_T1_V1`；rule-price
trigger/stop/target/T+1/same-bar semantics unchanged。Formal performance is theoretical strategy
performance, not the user's actual trades。

Current interpretation remains：B 在当前已观察市场环境中为负期望，主要问题是大量快速假突破；
这不是对所有市场环境的全局否定，B 继续冻结，不因报告/云端/投递任务自动调参。

## Prospective shadow monitor — active observational layer

`PROSPECTIVE_B_SHADOW_MONITOR_V1` remains observational / fail-soft。它记录 pre-outcome
market regime、reactivation structure、formal outcomes、FAST_STOP 与 post-stop recovery；
不进入 qualification、score、ranking、trigger、stop、target、RR 或 canonical B identity。

Prospective 与 retrospective labels 保持分离；不对部署前数据伪造 prospective capture。

## Canonical historical baseline retained

2026-09-11 authorized weekend backfill 已完成且不得重跑：

- watchlist SHA：`80e6198e8e8af869d6718f14874be8e6eaa36cf3f63e7af1f381fb83c78db12b`
- generation input package SHA：`d729c3f4c3261f45036cd748cd75db2e191c7af3939c66f8707f802f6ca659cd`
- candidate count：5
- provenance：`AUTHORIZED_WEEKEND_BACKFILL`

历史 watchlists / tracker / reports / evidence 不因后续 cloud、mobile 或 delivery feature 改写。

## Cloud schedule resilience — merged, dispatcher not active

- schedule date binding：已进入 `master`，由 UTC cron calendar date 解析 target；跨 BJT 午夜或
  cron 之前启动返回 `SKIPPED_STALE_SCHEDULE`，provider calls、正式 production、failure
  notification 均为 0。
- secondary dispatcher：Cloudflare Worker 仅 dispatch GitHub `workflow_dispatch`，状态为
  `PREPARED / NOT_ACTIVE`；不会调用 provider 或写 `runtime-state`。
- failure notification：`DAILY_FAILURE_NOTICE_V1` 是 operational-only、按 target date 去重的
  精确 allowlist 文件；canonical B/tracker/shadow/completion 不消费它。

## Local test workspace convention

当前 Windows 工作站本地测试临时根统一使用：

`D:\Temp\ashare-tests\<task-name>-<timestamp>`

如目录不存在可创建。pytest basetemp、临时 `ASHARE_DATA_ROOT`、HTML smoke 与测试中间产物应放入
本任务独立子目录；测试结束后只清理本任务自己创建的子目录。禁止 `git clean`、
`git reset --hard`、`git restore` 作为 cleanup；禁止删除 repo `data/`、`runtime-state`、正式
evidence、用户目录或其他任务目录。不得把 `D:\Temp` 硬编码进 production / GitHub Actions；
其他设备与云 runner 使用各自隔离临时目录等价物。

## Safety / next action

Final OOS：`SEALED / UNREAD`。
`data/validation/continuous_speed_probe/`：不得读取或触碰。

下一真实节点：本次 PR 合并后，核对新 workflow 的首个 production target、watchlist SHA/count、
tracker、shadow、responsive HTML、runtime-state new HEAD、delivery receipt、Email/Bark，并确认
raw/provider inputs persisted=`0`。若 18:17 retry、Cloudflare dispatch 或手工 production 命中同日
已完成状态，应保持 `ALREADY_COMPLETED` / `ALREADY_DELIVERED` 幂等，不重复 acquisition 或重复
成功 channel。Cloudflare 实际 activation 仍需用户完成 PAT/secret/account authorization。
