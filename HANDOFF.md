# CURRENT OPERATIONAL HANDOFF SNAPSHOT

> 本文件是下一台电脑、一次新 clone 或一个新 Codex 会话的接手入口；它不是完整 Git 历史。

## 1. Current Objective

- 唯一主任务：设计并实现 usable path 的 `development candidate`。
- 原因：当前 P1 product blocker 是 `deterministic daily generation → canonical watchlist → explicit fail-closed → monitoring / rollback / versioning` 尚未形成已证明的端到端路径。
- Scope：先核验 usable-path prerequisites，再定义 development candidate contract，并在 development fixtures 或受控数据上实现端到端路径；不改变生产策略、数据、冻结 artifact 或 Phase 2F 研究结果。
- 本次修复边界：仅消除本文件遗留的治理状态冲突；不启动实际 usable-path 开发。
- 禁止事项：不启动 Phase 2F；不读取 Final OOS；不 promotion；不调参；不把当前数据回填历史；不替换新浪历史行业 membership；不重跑已完成 CORE replay；不以“差不多”的新文件替代 frozen bytes。
- 完成条件：development candidate 在受控输入上可重复演示，canonical watchlist 与显式失败处理、监控/回滚/版本边界均有回归证据，并停在 `development-candidate` gate；不据此 promotion 或进入 Final OOS。
- 停止条件：出现 `PROJECT_GOVERNANCE_STATE_CONFLICT`、任一 required hash 不匹配、外部 raw artifact 无法证明为同一 bytes、或任务要求越过 research / OOS / promotion 边界。
- CI provenance 规则：本文件只保存 `last verified CI provenance`，不要求也不允许把当前 commit 自己产生的 CI run 回写到同一 commit；每个新会话必须实时查询当前 Git HEAD、PR state 和 exact-head CI。

## 2. Current Repository State

- repo：`EFSing/ashare_watchlist`；origin：`https://github.com/EFSing/ashare_watchlist.git`。
- formal governance merge identity：`7a27484293cbcb791c6b8407949e9e71257e016b`；这是产品章程与代理开发契约 PR #9 的真实 squash merge commit，Phase 2E research baseline 仍为 `74ccf86…`。
- current live master HEAD：`dbc22b51069703bb916281d039b872815c136357`；这是 PR #9 合并后的治理 handoff refresh commit，当前 `master` 与 `origin/master` 一致。
- working branch at last verified snapshot：`master`；本次治理修复分支从上述 current live master HEAD 派生。
- HEAD at last verified snapshot：`dbc22b51069703bb916281d039b872815c136357`（current live master）。
- PR / state：intake 时 `PR: NONE`；PR #1–#9 均已 merged，没有 active open PR。PR #9 head 为 `859935fb80a0de585149da16ead8870db11a63a7`，formal governance merge 为 master@7a27484…。
- last verified CI provenance：master correctness run `33261156054`，headSha=`dbc22b51069703bb916281d039b872815c136357`，success。
- live state gate：新会话必须实时执行 Git / GitHub 核验；本节和 `Last Verified` 的 CI 字段是最近一次证据快照，不是对当前 HEAD 的隐含声明。
- expected working tree state：tracked working tree clean；`.pytest_cache/`、`__pycache__/` 和本机 `daily_k.parquet` 可被 `.gitignore` 忽略，但 `daily_k.parquet` 的 recovery identity 现在由 registry 记录的 Google Drive private archive member evidence 独立确认。Windows text checkout 的 CRLF SHA 若存在，以 registry 的 Git-blob `file_sha256` 为恢复身份。
- formal phase / research status：Phase 2E 已完成；CORE continuous replay 和 DEVELOPMENT returns V2 已冻结；FULL legacy 85-score validation 仍 blocked。治理 PR 已合并；本机另有未推送 Phase 2F 分支，见下方，不是 formal master 状态。

## 3. Completed Work

- Phase 2A legacy strategy audit：PR #2，merged；历史 provenance 不足时使用 `UNKNOWN_ORIGIN` / `NOT_REPRODUCIBLE_WITH_CURRENT_DATA`。
- Phase 2B generation input/timing contract：PR #3，merged；close-only、`Asia/Shanghai`、XSHG T+1、`exchange-calendars==4.13.2`。
- Phase 2C `A_PLATFORM_BREAKOUT_LEGACY_V1`：PR #4，merged；仅 research evaluator，不是 production promotion。
- Phase 2D validation protocol：PR #5，merged；PIT、known-at、sector provenance 和 fail-closed contract 已冻结。
- Phase 2E：PR #6，merged 到 master@74ccf86…；CORE continuous replay 769 个 XSHG sessions、4,041,140 个 candidate evaluations；V2 returns 8,463 个 qualified outcomes。
- V2 outcome 明确为 `DEVELOPMENT` / `RECONSTRUCTED_RETROSPECTIVE`；V1 raw outcome 保留为 diagnostic，不覆盖；Final OOS 未读取。
- 形式化的 artifact inventory 已写入 [`data/governance/frozen_artifacts.json`](data/governance/frozen_artifacts.json)；`daily_k.parquet` 已由 Google Drive private-download archive 的唯一 parquet member 完成 persistent backup 与 recovery verification。
- recovery governance PR #8 已 squash merge 到 `7fe15d8…`；PR exact-head CI runs `33259704118`、`33259700451` 和 merge 后 master CI run `33259819493` 均 success，headSha 精确匹配各自目标。
- 产品章程与代理开发契约 PR #9 已 squash merge 到 `7a27484…`；PR exact-head CI runs `33260677946`、`33260690327` 和 merge 后 master CI run `33260777592` 均 success，headSha 精确匹配各自目标。

## 4. Pending Work

### Required Next

1. **verify usable-path prerequisites**：核对 strategy/protocol/dependency/data/output identities、输入 manifest、T close/T+1 contract、development fixture、recovery 与 fail-closed prerequisites；不改 frozen artifact。
2. **设计 development candidate contract**：明确 deterministic daily generation、canonical `watchlist_YYYYMMDD.json` 输出、显式不可用/失败状态、monitoring、rollback 和 versioning 的输入、输出、版本及停止条件。
3. **实现端到端 development path**：仅在 development fixtures 或受控数据上接通 generation、策略评估、canonical watchlist 输出和失败处理，不做 promotion、不写 Final OOS。
4. **tests / CI**：完成 pytest、compileall、JSON/hash/provenance validation、diff 检查及固定 development validation；exact-head CI 成功后再判断 development-candidate gate。
5. **停在 development-candidate gate**：不启动 Phase 2F、不调参、不读 Final OOS；Phase 2F `NEEDS_MORE_EVIDENCE`、历史新浪 membership 和其他 deferred 项保持原边界。

### Deferred

- Phase 2F 是否另开独立 PR；其本机诊断产物目前只作 `LOCAL_UNPUBLISHED` 记录。
- 历史新浪行业 membership acquisition contract、完整 85-score parity 和正式 validation dataset freeze。
- 任何 production rule、watchlist promotion、参数选择或 performance-based rule change。

### Prohibited For Now

- `final_oos`、`production_promotion`、`parameter_tuning`、`current_universe_backfill`、`current_sector_backfill`。
- 用当前 qfq / current sector / current constituents 冒充 T 日历史证据。
- 将 `A_PLATFORM_BREAKOUT_LEGACY_V1` 的 development historical outcome 写成 production promotion。
- 重新生成或重新下载一个近似 artifact 以替代 registry 中的 frozen identity。

## 5. Key Decisions And Rationale

- Decision：本治理 branch 从 formal master 派生，不承载本机 Phase 2F 代码。
  - Why：当前没有 active PR；Phase 2F 只有 local commit，混入会污染治理 PR 的审阅和 provenance。
  - Rejected Alternatives：从 Phase 2F local HEAD 建 branch；将未发布 research 与 governance 一起 push。
  - Revisit Condition：Phase 2F 经过独立审阅、artifact 可恢复性确认并需要正式发布时，另建 PR。
- Decision：artifact identity 分成 semantic/content SHA 与 file SHA，绝不包含绝对 filesystem path。
  - Why：换设备时路径会变，同一 bytes 和稳定 logical identity 必须保持相同 hash。
  - Rejected Alternatives：把本机路径写入 canonical hash；只记录文件名或重新下载结果。
  - Revisit Condition：只有 protocol 明确改变 canonical identity 时，才新增版本并保留旧 registry 记录。
- Decision：`daily_k.parquet` 更新为 `FULLY_RECOVERABLE`，storage type 为 `GOOGLE_DRIVE_PRIVATE`。
  - Why：从 Downloads 中实际下载的 Google Drive private archive 读取到唯一 parquet member；member size 为 `180203424` bytes，member SHA-256 与 frozen SHA `61189a…` 严格一致，matching member count 为 1。
  - Rejected Alternatives：把 ZIP 自身 hash 当作 parquet identity；按文件名猜测；继续使用本机原始文件作为唯一 recovery evidence；记录 URL、token 或绝对路径。
  - Revisit Condition：registry frozen bytes、Google Drive recovery member 或 recovery evidence 发生变化时，重新执行唯一性与 byte-level SHA verification。
- Decision：`A_PLATFORM_BREAKOUT_LEGACY_V1` 保持 research-only；当前正式 Delivery Ladder 为 `research`，不因 Phase 2E 或 Phase 2F local artifact 直接 promotion。
  - Why：当前完整 legacy output 仍缺历史新浪行业 membership，development outcome 也不是 Final OOS。
  - Rejected Alternatives：按 85 分、V2 returns 或 Phase 2F diagnostic 直接 promotion。
  - Revisit Condition：满足明确批准的验证层、provenance、OOS 和 decision gate。

## 6. Important Files Changed

本治理 commit 已新增：

- `HANDOFF.md` — governance；会话接手快照。
- `docs/CURRENT_STATUS.md` — governance；formal project status。
- `docs/DECISION_LOG.md` — governance；长期决策及理由。
- `docs/FROZEN_ARTIFACT_POLICY.md` — governance；冻结物 identity、backup 和 recovery policy。
- `data/governance/frozen_artifacts.json` — governance / artifact；机器可读 inventory。

当前理解所依赖的既有文件：

- `scripts/validation_contract.py` — production-sensitive / protocol；Phase 2D semantic SHA。
- `scripts/a_platform_breakout.py` — production-sensitive / research evaluator；strategy spec 不得静默改变。
- `docs/phase2e_pit_source_audit.md`、`docs/core_signal_validation_continuous.md`、`docs/development_historical_returns_v2.md` — research-only / artifact provenance。
- `data/validation/core_signal_validation*`、`data/validation/phase2e_*.json` — artifact；详见 registry。

## 7. Frozen Identities And Invariants

- strategy：`A_PLATFORM_BREAKOUT_LEGACY_V1`；strategy spec SHA `7ce0bf660e3ae685405e01fb9d1ef8e27e7dec44a201ab290da5d8fa8079068d`。
- validation protocol：`PHASE2D_VALIDATION_PROTOCOL_V1`；semantic SHA `a7db6dc2d6f2dba2555855236fce5580f5e13e192e66991f0f9f63cb0eb9e7ee`。
- continuous dataset：`core-signal-hithink-continuous-2023-06-30-to-2026-08-28-v1`；raw content SHA `68d10afc4a0e3341c124f8a5e896292faf8ca271ab15cfbb7ac55fe485db8ccb`。
- continuous CORE projection SHA `882b8925e787d67d7035de07f91cd3c941b7394661bd32d5d534cc62e3996c1b`；continuous result file SHA `0d23cf54843920f5fdcc05847e4b78c5d605b05c8793f878b6021c85b3ab0c2f`。
- returns V2 manifest semantic SHA `213a76b3da552c4dd68ca949f5a7b80eaee3e14241db825b497c78d875898bab`；event file SHA `eac51184bd2b51e80d7c2824de1e4b51ff904a1509ae320e85d9b816f6ecd8d1`。
- provider：HiThink Financial-API；historical Sina industry membership remains unavailable; current constituents/taxonomy cannot substitute。
- timing：signal at T close；earliest execution at next XSHG session T+1；timezone `Asia/Shanghai`。
- adjustment：raw OHLCV plus events with `ex_date <= T` for signal inputs；V2 outcome uses target-date basis and the frozen affine convention；`ex_date == entry_date` is not adjusted twice。
- status：CORE complete; V2 is `DEVELOPMENT` / `RECONSTRUCTED_RETROSPECTIVE`; sector score/report `UNVERIFIED`; FULL legacy `BLOCKED_HISTORICAL_SINA_MEMBERSHIP`; Final OOS `false`。
- public interface：production ingest remains canonical `watchlist_YYYYMMDD.json` with `candidates` / `trigger`; research harness does not write canonical watchlists。

## 8. Known Issues / Blockers

- resolved：`daily_k.parquet` 的本机 bytes 与 Google Drive private-download archive 的唯一 parquet member 均 hash-verified；registry 状态为 `FULLY_RECOVERABLE`。
- research/design：历史新浪行业 membership / effective-date evidence 缺失，FULL 85-score parity blocked；retrospective raw dump 没有 per-bar historical vintage timestamp。
- provider/external：需要可按 T 提供新浪行业 membership 的 source 或带 effective-date 的权限/导出；不能用其他 taxonomy 替代。
- environment：新设备必须有 Python 3.11/3.12、锁定依赖和可读的 external raw artifact；环境差异不是数据恢复证明。
- artifact availability：Phase 2F 诊断文件只在本机 local branch，未进入 origin；不纳入本次治理 PR。
- product readiness：端到端 deterministic daily generation、canonical watchlist output、显式 data failure、monitoring/rollback/versioning 尚未组成已证明的 usable path，这是 P1 product blocker。
- scope-local blocker：历史新浪行业 membership 缺失阻止 FULL legacy / 85-score validation，但不阻止 CORE research 或 prospective product progression。
- ambiguity：治理 PR #8 的 branch head、merge commit 和 exact-head/master CI 已回填并核验；后续任何文档与真实状态不一致都先标记 `PROJECT_GOVERNANCE_STATE_CONFLICT`。
- non-blocking debt：忽略目录中的测试缓存不属于版本化 artifact，但声明 handoff 前应保持 tracked working tree clean。

## 9. Lessons / Pitfalls — DO NOT REPEAT

- 历史 V0 规则缺少可复现的 as-of / raw response / adjustment provenance；没有证据就标 `UNKNOWN_ORIGIN` 或 `NOT_REPRODUCIBLE_WITH_CURRENT_DATA`，不补猜测。
- 旧 sector 缺失时的 `rank=50/chg=0` 式静默 fallback 已被识别为不合格；缺 evidence 必须显式 `INSUFFICIENT_DATA`，不能把其他 taxonomy 伪装成新浪行业。
- 旧的 source hash 曾把 filesystem path 混入 identity；portable hash 必须使用稳定 `logical_identity`、bytes 和 file SHA，路径只能作 provenance。
- V1 raw unadjusted historical outcome 不能直接承担 corporate-action-aware outcome；V1 保留为 diagnostic，V2 采用冻结事件和统一 adjusted path。
- checkpoint 虽可在 Git 中恢复，resume 仍必须同时验证 checkpoint identity 与 `daily_k.parquet` raw input hash；本次已完成 raw persistent backup / recovery gate。
- development 数据和已暴露的 retrospective artifact 不得重新包装为 Final OOS；当前所有文档和 registry 必须保留 `DEVELOPMENT` / `RECONSTRUCTED_RETROSPECTIVE` 标签。

## 10. Next Action

1. verify usable-path prerequisites，包括 registry hashes、输入/输出 identity、T close/T+1、development fixture、recovery 和 fail-closed 条件。
2. 设计 development candidate contract，覆盖 deterministic daily generation、canonical watchlist、显式失败、monitoring、rollback 和 versioning。
3. 实现端到端 development path，并在受控 development 输入上形成可重复的 canonical 输出。
4. 完成 tests / CI 与 development validation，核对所有 P0/P1；不把未验证项写成通过。
5. 停在 `development-candidate` gate；不启动 Phase 2F、不调参、不读 Final OOS。

## 11. Handoff Checklist

在声明 `TASK_COMPLETE`、`PHASE_COMPLETE`、`PR_FULLY_READY`、`READY_FOR_REVIEW` 或 `READY_FOR_DECISION` 之前，必须确认：

`HANDOFF_CURRENT_AND_CONSISTENT`

确认项：

- [x] Git branch / HEAD / master 与远端一致或差异已写明。
- [x] PR state、最终 `headSha` 和 exact-head CI 已核对。
- [x] required artifact 的 content SHA、Git-blob/file SHA、backup 和 recovery status 已核对；若适用也核对 working-tree SHA。
- [x] research / development / OOS / production 边界未被改变。
- [x] 本文件、CURRENT_STATUS、DECISION_LOG、FROZEN_ARTIFACT_POLICY 没有互相冲突。
- [x] tracked working tree clean；没有未登记的 raw、checkpoint 或 output。

## 12. Last Verified

- last_updated_at：`2026-08-29T23:55:10+08:00`（Asia/Shanghai；intake 核验 current live master 后的治理修复）
- verified_master_sha：`dbc22b51069703bb916281d039b872815c136357`（current live master at last verification；formal governance merge identity 仍为 `7a27484293cbcb791c6b8407949e9e71257e016b`）
- verified_branch_head：`dbc22b51069703bb916281d039b872815c136357`（本次治理修复分支起始的 verified master snapshot；最终 PR head 以实时状态核验）
- latest_test_result：`pytest 135 passed`; `compileall` pass; registry JSON/hash/recovery checks pass; secret scan and path/URL guard pass; master correctness run `33261156054` success
- latest_ci_run_provenance：run `33261156054` / headSha `dbc22b51069703bb916281d039b872815c136357` / success（last verified master provenance；不制造 CI 自引用更新循环）
- updated_by_task：`repair stale usable-path governance handoff`
