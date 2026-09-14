# HANDOFF — 跨设备最小恢复入口

> 恢复链：remote Git → branch → remote HEAD → HANDOFF.md → next action。
> 本文件只保留当前恢复所需的最小事实，不承担历史归档职责；历史 provenance 在 Git 历史中，
> 正式状态与长期决策分别见 `docs/CURRENT_STATUS.md` 与 `docs/DECISION_LOG.md`。
> 若治理文字与实时 Git / PR / CI / runtime-state 冲突，先标记
> `PROJECT_GOVERNANCE_STATE_CONFLICT`，以实时证据完成 reconciliation 后再继续。

## 2026-09-14 — CURRENT RECOVERY CHECKPOINT

- source authority：`origin/master`。恢复时必须先 `git fetch origin` 并实时读取
  `origin/master`；本次 reconciliation 的 live base 为
  `3b70ef138d5fbef18e1bf0b37782ddf9ee070b24`，但该 SHA 不是永久真相。
- production-state authority：remote `runtime-state` branch；本地 `data/` 仅为
  cache / reproduction，不得覆盖远端生产状态。恢复时同时核对 live `runtime-state` HEAD。
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
- next action：继续以实时 GitHub 状态为准；首笔真实云端 production 后核对 source SHA、
  watchlist/count、tracker、shadow、HTML、delivery receipt、Email/Bark 与 runtime-state 新 HEAD。

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
