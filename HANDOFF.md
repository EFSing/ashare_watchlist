# CURRENT OPERATIONAL HANDOFF SNAPSHOT

> 本文件是下一台电脑、一次新 clone 或一个新 Codex 会话的接手入口；它不是完整 Git 历史。

## 1. Current Objective

- 唯一主任务：建立并验证项目级多设备 / 多会话开发交接治理机制。
- 原因：项目已有跨阶段 research replay、returns、checkpoint 和大型 raw artifact；仅靠会话记忆或单机路径不能安全恢复。
- Scope：治理文档、冻结 artifact registry、交接冲突 gate、当前真实状态和恢复边界；不改变生产策略或既有 frozen artifact。
- 禁止事项：不 merge；不读取 Final OOS；不 promotion；不调参；不把当前数据回填历史；不替换新浪历史行业 membership；不重跑已完成 CORE replay；不以“差不多”的新文件替代 frozen bytes。
- 完成条件：治理文件通过测试和 CI，治理 PR 的最终 head 有 exact-head CI，registry 中每个 artifact 都有可核验的身份和 recoverability 状态，且本文件与真实 Git / PR / CI 一致。
- 停止条件：出现 `PROJECT_GOVERNANCE_STATE_CONFLICT`、任一 required hash 不匹配、外部 raw artifact 无法证明为同一 bytes、或任务要求越过 research / OOS / promotion 边界。

## 2. Current Repository State

- repo：`EFSing/ashare_watchlist`；origin：`https://github.com/EFSing/ashare_watchlist.git`。
- formal master SHA：`74ccf86dfdea3b9d4b0124fb54346aa429735508`；这是已合并 PR #6 的 merge commit。
- working branch：`chore/project-handoff-governance`，从上述 master 派生。
- HEAD at last verified snapshot：`f5e8851c09c4974706e43a940fc99d94b5095a23`；治理 commit 已创建，当前尚未 push。
- PR / state：`NOT_CREATED`；没有 active open PR。PR #1–#6 均已 merged；PR #6 head 为 `edb57a3489733e0f7657ae9e2b8a1b473c52cfc2`，merge 为 master@74ccf86…。
- exact-head CI：master correctness run `33246744991`，headSha=`74ccf86dfdea3b9d4b0124fb54346aa429735508`，success；治理 branch 尚未 push，暂无独立 exact-head CI。
- expected working tree state：tracked working tree clean；`.pytest_cache/`、`__pycache__/` 和本机 `daily_k.parquet` 可被 `.gitignore` 忽略，但不得被当作 frozen backup。Windows text checkout 的 CRLF SHA 若存在，以 registry 的 Git-blob `file_sha256` 为恢复身份。
- formal phase / research status：Phase 2E 已完成；CORE continuous replay 和 DEVELOPMENT returns V2 已冻结；FULL legacy 85-score validation 仍 blocked。当前本机另有未推送 Phase 2F 分支，见下方，不是 formal master 状态。

## 3. Completed Work

- Phase 2A legacy strategy audit：PR #2，merged；历史 provenance 不足时使用 `UNKNOWN_ORIGIN` / `NOT_REPRODUCIBLE_WITH_CURRENT_DATA`。
- Phase 2B generation input/timing contract：PR #3，merged；close-only、`Asia/Shanghai`、XSHG T+1、`exchange-calendars==4.13.2`。
- Phase 2C `A_PLATFORM_BREAKOUT_LEGACY_V1`：PR #4，merged；仅 research evaluator，不是 production promotion。
- Phase 2D validation protocol：PR #5，merged；PIT、known-at、sector provenance 和 fail-closed contract 已冻结。
- Phase 2E：PR #6，merged 到 master@74ccf86…；CORE continuous replay 769 个 XSHG sessions、4,041,140 个 candidate evaluations；V2 returns 8,463 个 qualified outcomes。
- V2 outcome 明确为 `DEVELOPMENT` / `RECONSTRUCTED_RETROSPECTIVE`；V1 raw outcome 保留为 diagnostic，不覆盖；Final OOS 未读取。
- 形式化的 artifact inventory 已写入 [`data/governance/frozen_artifacts.json`](data/governance/frozen_artifacts.json)；`daily_k.parquet` 的外部副本尚未被证明有 persistent backup。

## 4. Pending Work

### Required Next

1. 将已提交的治理 branch push 到 origin，创建治理 PR，并等待治理 PR 最终 head 的 exact-head CI；当前 push 被托管安全策略拒绝，需用户明确授权后重试。
2. 新会话接手时先核对本文件、[`docs/CURRENT_STATUS.md`](docs/CURRENT_STATUS.md)、[`docs/DECISION_LOG.md`](docs/DECISION_LOG.md)、[`docs/FROZEN_ARTIFACT_POLICY.md`](docs/FROZEN_ARTIFACT_POLICY.md)、Git/PR/CI 和 registry hashes。
3. 将 `daily_k.parquet` 的同一 bytes 放入受控 persistent backup，并以 `61189a4850e2eb157453e28e5375e502e20d214508bbe70ea71066ca3e05e426` 验证；未完成前不得声明完整 replay 跨设备可恢复。
4. 对本机 `codex/phase2f-a-breakout-failure-diagnostic@3eeb5df9f7cf4ef5c30b3380b323f26f2491f873` 的 Phase 2F A-platform failure diagnostic 做独立 handoff / provenance review；它没有远端分支、PR 或 CI，不得当作 master 已完成。
5. 在历史新浪行业 membership / effective-date source 与 provenance 边界明确后，再决定 Research V2 / FULL legacy validation 的范围。

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
- Decision：`daily_k.parquet` 标为 `NOT_FULLY_RECOVERABLE`。
  - Why：本机 bytes 与 manifest hash 一致，但 `.gitignore` 和 Git object 检查均证明它不在 master / origin backup 中。
  - Rejected Alternatives：把“本机存在”写成 fully recoverable；虚构云盘或外部 backup。
  - Revisit Condition：同一 SHA 的 persistent backup 存在并完成独立恢复验证。
- Decision：`A_PLATFORM_BREAKOUT_LEGACY_V1` 保持 research-only。
  - Why：当前完整 legacy output 仍缺历史新浪行业 membership，development outcome 也不是 Final OOS。
  - Rejected Alternatives：按 85 分、V2 returns 或 Phase 2F diagnostic 直接 promotion。
  - Revisit Condition：满足明确批准的验证层、provenance、OOS 和 decision gate。

## 6. Important Files Changed

本治理 commit 预期新增：

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

- correctness：`daily_k.parquet` 的本机 bytes 已 hash-verified，但缺 Git/持久备份，完整 replay 不能声明跨设备恢复。
- research/design：历史新浪行业 membership / effective-date evidence 缺失，FULL 85-score parity blocked；retrospective raw dump 没有 per-bar historical vintage timestamp。
- provider/external：需要可按 T 提供新浪行业 membership 的 source 或带 effective-date 的权限/导出；不能用其他 taxonomy 替代。
- environment：新设备必须有 Python 3.11/3.12、锁定依赖和可读的 external raw artifact；环境差异不是数据恢复证明。
- artifact availability：Phase 2F 诊断文件只在本机 local branch，未进入 origin。
- environment：本轮 `git push -u origin chore/project-handoff-governance` 被托管安全策略拒绝；在获得明确授权前不得用其他方式绕过。
- ambiguity：治理 PR 的 branch head / CI 必须在创建后回填并再次验证；任何文档与真实状态不一致都先标记 `PROJECT_GOVERNANCE_STATE_CONFLICT`。
- non-blocking debt：忽略目录中的测试缓存不属于版本化 artifact，但声明 handoff 前应保持 tracked working tree clean。

## 9. Lessons / Pitfalls — DO NOT REPEAT

- 历史 V0 规则缺少可复现的 as-of / raw response / adjustment provenance；没有证据就标 `UNKNOWN_ORIGIN` 或 `NOT_REPRODUCIBLE_WITH_CURRENT_DATA`，不补猜测。
- 旧 sector 缺失时的 `rank=50/chg=0` 式静默 fallback 已被识别为不合格；缺 evidence 必须显式 `INSUFFICIENT_DATA`，不能把其他 taxonomy 伪装成新浪行业。
- 旧的 source hash 曾把 filesystem path 混入 identity；portable hash 必须使用稳定 `logical_identity`、bytes 和 file SHA，路径只能作 provenance。
- V1 raw unadjusted historical outcome 不能直接承担 corporate-action-aware outcome；V1 保留为 diagnostic，V2 采用冻结事件和统一 adjusted path。
- checkpoint 虽可在 Git 中恢复，但若 required `daily_k.parquet` 仅在单机，resume 仍不能跨设备完成；checkpoint 与 raw input hash 必须成对验证。
- development 数据和已暴露的 retrospective artifact 不得重新包装为 Final OOS；当前所有文档和 registry 必须保留 `DEVELOPMENT` / `RECONSTRUCTED_RETROSPECTIVE` 标签。

## 10. Next Action

1. push 已提交的 `chore: establish project handoff governance` branch 并创建独立治理 PR；把最终 PR head、exact-head CI、tests 和当前 HEAD 回填到本文件。
2. 若 remote push 仍不可用，停止在 `PR_NOT_CREATED`，不得声明 `PR_FULLY_READY`。
3. 新设备接手时先执行：`git fetch origin`，核对 master/branch/PR/CI；读取四份治理文件；逐项验证 `frozen_artifacts.json`。
4. 取得并验证 `daily_k.parquet` 的 persistent backup；没有 `61189a…` exact match 就停止 replay/resume。
5. 对 local-only Phase 2F A-platform failure diagnostic 做 separate review；若继续则以 `A_PLATFORM_BREAKOUT failure diagnostic / Research V2 preparation` 为 research next action，仍不 promotion、不读 Final OOS。
6. 在 defined decision node 停止：`PR_FULLY_READY`，不 merge。

## 11. Handoff Checklist

在声明 `TASK_COMPLETE`、`PHASE_COMPLETE`、`PR_FULLY_READY`、`READY_FOR_REVIEW` 或 `READY_FOR_DECISION` 之前，必须确认：

`HANDOFF_CURRENT_AND_CONSISTENT`

确认项：

- [ ] Git branch / HEAD / master 与远端一致或差异已写明。
- [ ] PR state、最终 `headSha` 和 exact-head CI 已核对。
- [ ] required artifact 的 content SHA、Git-blob/file SHA、backup 和 recovery status 已核对；若适用也核对 working-tree SHA。
- [ ] research / development / OOS / production 边界未被改变。
- [ ] 本文件、CURRENT_STATUS、DECISION_LOG、FROZEN_ARTIFACT_POLICY 没有互相冲突。
- [ ] tracked working tree clean；没有未登记的 raw、checkpoint 或 output。

## 12. Last Verified

- last_updated_at：`2026-08-29T19:16:00+08:00`（Asia/Shanghai）
- verified_master_sha：`74ccf86dfdea3b9d4b0124fb54346aa429735508`
- verified_branch_head：`f5e8851c09c4974706e43a940fc99d94b5095a23`（治理 commit；本次 metadata update 之后的 commit 需在 push 前再次核对）
- latest_test_result：`pytest 135 passed`; `compileall` pass; registry JSON/hash checks pass; master exact-head correctness run `33246744991` success
- latest_ci_run：run `33246744991` / headSha `74ccf86dfdea3b9d4b0124fb54346aa429735508` / success
- updated_by_task：`project handoff governance initialization`
