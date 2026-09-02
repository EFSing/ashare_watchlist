# CURRENT OPERATIONAL HANDOFF SNAPSHOT

> 本文件是下一台电脑、一次新 clone 或一个新 Codex 会话的接手入口；它不是完整 Git 历史。

## 1. Current Objective

- 当前工作对象：PR #20 merge 后的 governance state reconciliation，以及
  `T=2026-09-02` 合法 T-close prospective capture 前置状态确认；当前 master 为
  `106bfbd00502db56a2e544f1c804a52372c1fa3e`。
- PR #12 已 merge；正式 Delivery Ladder 为 `development candidate`。
- 该晋级只承认 deterministic daily generation → canonical watchlist → explicit
  fail-closed → provenance / versioning → monitoring / rollback 的受控产品路径，
  不承认 strategy promotion。
- Scope：本次 follow-up 仅更新 `HANDOFF.md`、`docs/CURRENT_STATUS.md` 和
  `docs/DECISION_LOG.md` 的 live governance snapshot；不改变 B evaluator、B spec、
  live contract、threshold、生产策略、数据、冻结 artifact 或 Phase 2F 研究结果。
- PR #20 已 squash merge，merge SHA 为
  `106bfbd00502db56a2e544f1c804a52372c1fa3e`；corrected candidate 为
  `B_BREAKOUT_RETEST_LEGACY_V1_1`，eligibility decision 为
  `CORRECTED_B_CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES`。
- 当前下一 gate：等待 `2026-09-02` XSHG 合法收盘窗口；北京时间 15:00 前不运行
  formal `LIVE_OBSERVED` capture，不把 current diagnostic 当作 prospective evidence。
- 禁止事项：不启动 Phase 2F；不读取 Final OOS；不 promotion；不调参；不把当前数据回填历史；不替换新浪历史行业 membership；不重跑已完成 CORE replay；不以“差不多”的新文件替代 frozen bytes。
- 本轮历史结果：正式 master-baseline acquisition 在 exact Sina sector/member 阶段
  因 `INPUT_CONFLICT` fail closed；该 blocker 是 input/provider-data consistency
  conflict，不是 provider connectivity failure。没有形成 `LIVE_OBSERVED` package，
  正式状态仍停在 `development candidate`，不据此 promotion 或进入 Final OOS。
- 上述 source audit、旧 reconstruction 和 pre-merge review 状态均保留为历史证据；
  当前 authoritative source identity、corrected B semantics 和 eligibility impact
  以 2026-09-01 corrected reconstruction decision 及本文件末尾的 post-merge snapshot
  为准。
- 停止条件：出现 `PROJECT_GOVERNANCE_STATE_CONFLICT`、任一 required hash 不匹配、外部 raw artifact 无法证明为同一 bytes、或任务要求越过 research / OOS / promotion 边界。
- CI provenance 规则：本文件只保存 `last verified CI provenance`，不要求也不允许把当前 commit 自己产生的 CI run 回写到同一 commit；每个新会话必须实时查询当前 branch、HEAD、`origin/master`、PR state、exact-head CI 和 working tree。

## 2. Current Repository State

- repo：`EFSing/ashare_watchlist`；origin：`https://github.com/EFSing/ashare_watchlist.git`。
- active product PR：无；PR #20 已合并到正式 master
  `106bfbd00502db56a2e544f1c804a52372c1fa3e`。PR #20 merge 后 master exact-head
  correctness run `100101351273` success，当前 open PR 为 0。
- HISTORICAL_MILESTONE_IDENTITY：PR #9 产品章程与代理开发契约 squash merge `7a27484293cbcb791c6b8407949e9e71257e016b`；Phase 2E research baseline 仍为 `74ccf86…`。
- HISTORICAL_MILESTONE_IDENTITY：PR #10 handoff consistency repair squash merge `11db387cc51a645c4491b39cbfa3e03e1228b6c4`。
- HISTORICAL_MILESTONE_IDENTITY：PR #12 development-candidate gate squash merge
  `7dfb59b9f379c7d74f95c3e522fde55bcdf49ba1`；merge 后 master correctness run
  `33268086906` success，headSha 精确匹配该 merge commit。
- last_verified_master_snapshot：`106bfbd00502db56a2e544f1c804a52372c1fa3e`；这是
  PR #20 合并后的静态 provenance snapshot，不要求等于后续新会话 intake 时的 live HEAD。
- last_verified_branch：`master`；仅表示上述 snapshot 的来源，不是 current branch invariant。
- last_verified_ci_provenance：master correctness run `100101351273`，
  headSha=`106bfbd00502db56a2e544f1c804a52372c1fa3e`，success；仅是最近一次 CI
  证据，不是未来 live CI invariant。
- live state gate：新会话必须实时执行 Git / GitHub 核验；current branch、HEAD、`origin/master`、active PR、exact-head CI 和 working tree 以实时结果为准。
- expected working tree state：tracked working tree clean；`.pytest_cache/`、`__pycache__/` 和本机 `daily_k.parquet` 可被 `.gitignore` 忽略，但 `daily_k.parquet` 的 recovery identity 现在由 registry 记录的 Google Drive private archive member evidence 独立确认。Windows text checkout 的 CRLF SHA 若存在，以 registry 的 Git-blob `file_sha256` 为恢复身份。
- formal phase / research status：Phase 2E 已完成；CORE continuous replay 和 DEVELOPMENT
  returns V2 已冻结；FULL legacy 85-score validation 仍 blocked。PR #15 已合并，formal
  Delivery Ladder 仍为 `development candidate`；本机另有未推送 Phase 2F 分支，见下方，
  不是 formal master 状态。

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
- stale usable-path handoff repair PR #10 已 squash merge 到 `11db387…`；PR exact-head CI runs `33261804181`、`33261822861` 和 merge 后 master CI run `33261928349` 均 success，headSha 精确匹配各自目标。
- PR #12 已建立 development-candidate contract 和受控实现：zero-candidate success、
  complete `generation_fingerprint`、fail-closed conflict/write failure、immutable
  versioning、monitoring/rollback 以及 downstream ingest 回归均已纳入 gate evidence；
  PR #12 已 merge，formal Delivery Ladder 现为 `development candidate`。
- B `BREAKOUT_RETEST_LEGACY_V1` 已完成一次且仅一次的冻结 eligibility replay，
  decision 为 `CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES`；candidate-bound
  prospective input/provenance contract 已定义，但未创建 live instance 或
  `FROZEN_CANDIDATE_CONTRACT_V1`。

## 4. Pending Work

### Frozen-candidate prerequisites decision

1. `FROZEN_CANDIDATE_BLOCKED`：B 已通过冻结 eligibility，但首个真实
   candidate-bound `LIVE_OBSERVED` T-close input instance 尚未形成；2026-08-31 的
   formal attempt 仍保留原始 `INPUT_CONFLICT` 事实。
2. 当前 P1 为 `P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE`，现阶段的精确
   provider gate 是 `FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_SECTOR_MEMBERSHIP_AMBIGUITY`
   并伴随 exact-Sina coverage failure；不得缩 universe、丢弃 symbol、猜 sector、
   用 EM/THS/SW 替代或 current-data backfill。
3. 当前 active contract 为 `CANDIDATE_BOUND_PROSPECTIVE_INPUT_PROVENANCE_CONTRACT_V3`；
   V1/V2 保持历史 evidence。V3 绑定 corrected
   `B_BREAKOUT_RETEST_LEGACY_V1_1`，不把 contract 写成 live evidence，也不创建
   `FROZEN_CANDIDATE_CONTRACT_V1`。
4. fresh environment、current read-only provider audit 和 Google Drive probe 已完成；
   当前等待 `T=2026-09-02` 合法 T-close。北京时间 15:00 前不运行 acquisition；不启动
   Phase 2F、不调参、不读 Final OOS、不 promotion、不测试 C。

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
  - Why：该治理决策形成时没有 active PR；Phase 2F 只有 local commit，混入会污染治理 PR 的审阅和 provenance。
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
- Decision：`A_PLATFORM_BREAKOUT_LEGACY_V1` 保持 research-only；它不是 frozen
  strategy candidate、production strategy 或 parameter validation。`development
  candidate` 是产品管线的 formal ladder，不是该 strategy 的 promotion。
  - Why：当前完整 legacy output 仍缺历史新浪行业 membership，development outcome 也不是 Final OOS。
  - Rejected Alternatives：按 85 分、V2 returns 或 Phase 2F diagnostic 直接 promotion。
  - Revisit Condition：满足明确批准的验证层、provenance、OOS 和 decision gate。
- Decision：`Development Candidate Gate V1` ADOPT 的是 development candidate product
  path；PR #12 已 merge，formal Delivery Ladder 为 `development candidate`。
  - Why：deterministic generation、canonical output、fail-closed、完整
    provenance/versioning、monitoring/rollback 和 zero-candidate success semantics
    已有受控回归证据。
  - Rejected Alternatives：把该 gate 写成 legacy strategy promotion、参数有效性
    证明、frozen candidate 或 Final OOS 结论。
- Revisit Condition：完成 frozen-candidate prerequisites 的明确 decision；若通过，
  再定义新的 frozen candidate contract/gate。
- Decision：`FROZEN_CANDIDATE_BLOCKED`，原因为
  `FROZEN_CANDIDATE_BLOCKED_NO_APPROVED_STRATEGY_CANDIDATE`。
  - Why：没有正式 nominated/approved strategy candidate；现有 A baseline 只有
    research-only wiring、DEVELOPMENT retrospective evidence，且 sector/full
    legacy evidence 未完成，不能把 harness 可运行写成 freeze eligibility。
  - Consequences：不创建 `FROZEN_CANDIDATE_CONTRACT_V1`；P1 仅限候选 nomination/
    eligibility 与 candidate-bound prospective input/provenance evidence。
  - Revisit Condition：最小证据链到位后，在同一 prerequisites decision point 重新判断。

## 6. Important Files Changed

本治理 commit 已新增：

- `HANDOFF.md` — governance；会话接手快照。
- `docs/CURRENT_STATUS.md` — governance；formal project status。
- `docs/DECISION_LOG.md` — governance；长期决策及理由。
- `docs/frozen_candidate_prerequisites_audit.md` — governance；冻结候选前置条件审计与 decision。
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
- public interface：production ingest remains canonical `watchlist_YYYYMMDD.json` with
  `candidates` / `trigger`；PR #12 的 development-candidate harness 可在受控 data
  root 写入 schema-valid canonical watchlist，但这不代表 production promotion。

## 8. Known Issues / Blockers

- resolved：`daily_k.parquet` 的本机 bytes 与 Google Drive private-download archive 的唯一 parquet member 均 hash-verified；registry 状态为 `FULLY_RECOVERABLE`。
- research/design：历史新浪行业 membership / effective-date evidence 缺失，FULL 85-score parity blocked；retrospective raw dump 没有 per-bar historical vintage timestamp。
- provider/external：需要可按 T 提供新浪行业 membership 的 source 或带 effective-date 的权限/导出；不能用其他 taxonomy 替代。首个正式 T-close acquisition 另因 AkShare sector membership `ConnectionError` 失败；未进入 quote/Kline 或 persistence 阶段。
- environment：新设备必须有 Python 3.11/3.12、锁定依赖和可读的 external raw artifact；环境差异不是数据恢复证明。
- artifact availability：Phase 2F 诊断文件只在本机 local branch，未进入 origin；不纳入本次治理 PR。
- product readiness：PR #12 已证明端到端 development-candidate path；PR #15 已将
  live adapter 合并到 master，但首个正式 acquisition 因 provider failure 未形成
  package；当前正式 Ladder 为 `development candidate`，尚未达到 frozen candidate 或
  production strategy。
- next-ladder blocker：prerequisites decision 为 `FROZEN_CANDIDATE_BLOCKED`；B 已获
  eligibility，但首个 candidate-bound prospective T-close input 在 provider failure
  下仍缺失。
- contract boundary：candidate-bound prospective input/provenance contract 已定义；
  未定义且不得以现有 development contract 代替 `FROZEN_CANDIDATE_CONTRACT_V1`。
- scope-local blocker：历史新浪行业 membership 缺失只阻止 FULL legacy / 85-score
  validation；它不阻止 development-candidate product path，不能升级为全局 blocker。
- governance semantics：snapshot SHA、historical milestone SHA 和 last-verified CI 只保存 provenance；只有 material semantic divergence、required frozen identity mismatch 或非法历史后继才是 `PROJECT_GOVERNANCE_STATE_CONFLICT`。
- hash audit note：现有非 replay-required 的 `phase2e.hithink_probe` registry record
  预存 `working_tree_sha256=af694b...`，但当前 exact bytes 为其 registered
  `file_sha256=395601b...`；该 pre-existing discrepancy 未由本轮修改，不能把它当作
  新 live package 或 recovery evidence。策略/输入冻结 identity 未改变。
- non-blocking debt：忽略目录中的测试缓存不属于版本化 artifact，但声明 handoff 前应保持 tracked working tree clean。

## 9. Lessons / Pitfalls — DO NOT REPEAT

- 历史 V0 规则缺少可复现的 as-of / raw response / adjustment provenance；没有证据就标 `UNKNOWN_ORIGIN` 或 `NOT_REPRODUCIBLE_WITH_CURRENT_DATA`，不补猜测。
- 旧 sector 缺失时的 `rank=50/chg=0` 式静默 fallback 已被识别为不合格；缺 evidence 必须显式 `INSUFFICIENT_DATA`，不能把其他 taxonomy 伪装成新浪行业。
- 旧的 source hash 曾把 filesystem path 混入 identity；portable hash 必须使用稳定 `logical_identity`、bytes 和 file SHA，路径只能作 provenance。
- V1 raw unadjusted historical outcome 不能直接承担 corporate-action-aware outcome；V1 保留为 diagnostic，V2 采用冻结事件和统一 adjusted path。
- checkpoint 虽可在 Git 中恢复，resume 仍必须同时验证 checkpoint identity 与 `daily_k.parquet` raw input hash；本次已完成 raw persistent backup / recovery gate。
- development 数据和已暴露的 retrospective artifact 不得重新包装为 Final OOS；当前所有文档和 registry 必须保留 `DEVELOPMENT` / `RECONSTRUCTED_RETROSPECTIVE` 标签。

## 10. Next Action

1. formal Delivery Ladder 已为 `development candidate`；不把 product-ladder 晋级写成
   legacy strategy promotion。
2. PR #18 在单一治理 PR 内记录 2026-08-31 failed attempt 的准确分类，并完成
   display-name normalization / structured fail-closed diagnostic fix；B eligibility
   仍为 `CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES`，不自动扩大研究。
3. candidate-bound prospective input/provenance contract 已定义，但只有 PR #18
   完成 review/merge 后、2026-09-01 XSHG 正式收盘后的新真实 package 通过审计，才
   重新判断 frozen candidate gate；当前不伪造 live instance。
4. 历史新浪 membership 限制继续留在 FULL legacy validation scope；不升级为全局 blocker。
5. 不自动启动 Phase 2F、不调参、不读 Final OOS、不 promotion。

## 11. Handoff Checklist

在声明 `TASK_COMPLETE`、`PHASE_COMPLETE`、`PR_FULLY_READY`、`READY_FOR_REVIEW` 或 `READY_FOR_DECISION` 之前，必须确认：

`HANDOFF_CURRENT_AND_CONSISTENT`

确认项：

- [ ] 新会话已实时核对 current branch / HEAD / `origin/master` / working tree；该项不由本文件的静态 snapshot 自动满足。
- [ ] 新会话已实时核对 active PR、最终 `headSha` 和 exact-head CI；该项不由本文件的静态 CI provenance 自动满足。
- [x] required artifact 的 content SHA、Git-blob/file SHA、backup 和 recovery status 已核对；若适用也核对 working-tree SHA。
- [x] research / development / OOS / production 边界未被改变。
- [x] PR #12 development-candidate gate 已 merge；formal Ladder 已刷新为
  `development candidate`。
- [x] B eligibility decision、唯一剩余 P1、candidate-bound contract、下一 decision
  和“不创建 frozen candidate contract / 不伪造 live instance”的边界已记录。
- [x] 本文件、CURRENT_STATUS、DECISION_LOG、FROZEN_ARTIFACT_POLICY 没有互相冲突。
- [x] tracked working tree clean；没有未登记的 raw、checkpoint 或 output。

## 12. Last Verified

- last_updated_at：`2026-08-31`（Asia/Shanghai；PR #16 merge and same-day retry decision）
- last_verified_master_snapshot：`c5988d18fdec72d3148a5f6e22df1a1153731986`
- latest_test_result：PR #16 exact-head CI 与 merge 后 master correctness 均 success；
  当前 master snapshot 的 correctness run 为 `33373176281`。
- latest_ci_run_provenance：run `33373176281` / headSha
  `c5988d18fdec72d3148a5f6e22df1a1153731986` / success；不制造 CI 自引用更新循环。
- updated_by_task：`PR #16 bounded AkShare retry and same-day acquisition decision`

## 13. Strategy Candidate Nomination V1 — final eligibility update

本轮唯一 nomination 仍为
`NOMINATE_B_BREAKOUT_RETEST_LEGACY_V1_FOR_DEVELOPMENT_ELIGIBILITY`；A 仍为
`REJECT_A_PLATFORM_BREAKOUT_LEGACY_V1_AS_FROZEN_CANDIDATE`，C 未被评估。

B exact reconstruction 已完成，spec SHA 为
`5bbeb345ebd8883149138d2f29f8606f919949ae285aa2839fa337921dfc7112`。固定
`STRATEGY_DEVELOPMENT_ELIGIBILITY_V1` 只运行一次，且
`ELIGIBILITY_RULE_FROZEN_BEFORE_B_RETURNS_READ = true`。环境为 Python 3.12.13、
pandas 2.2.3、pyarrow 17.0.0；registry required artifacts 13/13 通过校验，
daily_k SHA 为 `61189a4850e2eb157453e28e5375e502e20d214508bbe70ea71066ca3e05e426`。

Event N `17,714`；1D/3D/5D/10D available N 为 `17,689` / `17,635` / `17,602` /
`17,558`；10D positive rate / mean / median 为 `51.6403%` / `+1.4603%` /
`+0.3226%`；4 个 robust years 中 2 个 mean 为正。最终 B decision 为
`CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES`。完整指标、MFE/MAE、concentration、
year robustness、fixed gate audit 和 artifact SHA 见
[`docs/strategy_candidate_eligibility_report.md`](docs/strategy_candidate_eligibility_report.md)。

已定义 [`docs/candidate_bound_prospective_input_contract_v1.md`](docs/candidate_bound_prospective_input_contract_v1.md)，
但没有伪造 prospective live instance。重新判断后的
`FROZEN_CANDIDATE_PREREQUISITES` 为 `FROZEN_CANDIDATE_BLOCKED`，唯一 P1 为
`P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE`；等待首个真实
`LIVE_OBSERVED` T-close package 前，不创建 `FROZEN_CANDIDATE_CONTRACT_V1`，不测试
C、不启动 Phase 2F、不调参、不读 Final OOS。

本节是治理 snapshot；live branch / PR / exact-head CI 仍须按 checklist 实时核对。

## 14. Governance conflict and provenance correctness closure — 2026-08-31

Sol audit 指出的 `PROJECT_GOVERNANCE_STATE_CONFLICT` 已限定并修复：active PR
metadata 现在必须描述 B `CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES`；Formal
Delivery Ladder 仍为 `development candidate`；尚未创建
`FROZEN_CANDIDATE_CONTRACT_V1`；唯一当前 P1 为
`P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE`；不 promotion。

`strategy_development_eligibility.py` 的 serialized provenance 现在只保存稳定
repo-relative logical paths；不同 repo/temp roots 以及 relative/absolute invocation
不会改变 canonical identity，绝对 path 和 `Path.resolve()` machine-specific result
不参与 semantic/content/manifest hash。

本轮正式 decision artifacts 已登记并做 byte/hash verification：

- event：17,714 rows；file SHA `8940a4a346ac6911ba669f84a9ceba7ef878b0ed0ce51edf673439b52aa056b9`；semantic/content SHA `a16e48dfbe8a93f64d8bf1bad6e00d3eaf32c10fd60eed09dc5574247b8119bc`。
- manifest：367,674 bytes；file SHA `5e0a557c1930de7b4f182f09f43b45c0c11b19b2d7c992bf9e7fa7e6cc6de048`；manifest semantic SHA `f79ec9baa494f2f0256843c2540988bd25c94269ed9a1fd4ada228759bd8e0a2`；payload content SHA `e754787836b28316430278372ab2d84817091d4608da394f9207f695a4c27aee`。

同一冻结 inputs/fixed B protocol 的 deterministic reproducibility verification 证明
event count、event identities、全部 metrics、fixed thresholds、gate audit、decision
与修复前完全一致；manifest 仅做 provenance rematerialization，不是第二次
candidate-selection experiment。Phase 2B T-close/T+1、anti-lookahead、Final OOS sealed
invariants 未改变。当前停在 Sol review；不测试 C、不启动 Phase 2F、不调参、不读
Final OOS、不 merge。

## 15. Live acquisition adapter readiness — 2026-08-31 (pre-merge implementation snapshot)

- task branch：`codex/live-acquisition-adapter-v1`，从用户指定的
  `origin/master=4e685ba28668ada29f78e6fa4a56be1cacc259ea` 派生；本分支不承载
  nomination branch 的额外提交。
- implementation：确认原 master 缺少 AkShare/Tencent live acquisition adapter，
  新增 `scripts/live_acquisition.py`、mock/fixture regression tests、明确 pin
  `akshare==1.18.94` 和对应 adapter contract 文档。
- runtime snapshot：Python `3.12.13`、AkShare 实际版本 `1.18.94`、pandas
  `2.2.3`、requests `2.32.3`、exchange-calendars `4.13.2`、pyarrow `25.0.1`。
  AkShare API callable probe 只做 import/capability check，没有调用 live endpoint。
- path boundary：adapter 能在正式 T close 后构造 universe、quotes、stock/index
  qfq Kline、sector、market_env 和 READY `GenerationInputManifest`；pre-close、
  wrong date、provider/schema/coverage/conflict/freshness/future-bar 失败均 fail
  closed。display names/market_env 进入 candidate-bound generation identity；不写
  canonical watchlist。
- evidence boundary：本轮没有真实 `LIVE_OBSERVED` package，没有 formal output，
  没有 current-data backfill、Phase 2F、promotion、调参或 Final OOS。formal
  Delivery Ladder 仍为 `development candidate`，后续仍等待首个真实 T-close
  package，并在 `FROZEN_CANDIDATE_PREREQUISITES` 重新审计。
- GitHub live state at the time：PR #15 的 exact-head correctness run `33366136847`
  / run #92 已 `success`，head 精确匹配当时的
  `0d092788f4296bd9501a6f1f82cdb74f3de230e3`；该 PR 后续已按 expected head
  `f0528744d9fe0add78436a543b15afa12c2e229e` squash merge。既有
  `data/validation/continuous_speed_probe/` 未跟踪目录属于用户现有内容，未触碰。

## 16. First prospective T-close acquisition — 2026-08-31

- formal baseline：PR #15 merge master
  `f1fed4608210aa175ac268189a8d7f032b0b88e0`；post-merge correctness run
  `33367655723` success；当前 product PR 为 `NONE`。
- timing：T=`2026-08-31` 是 XSHG session，session close
  `2026-08-31T15:00:00+08:00`，T+1=`2026-09-01`；正式调用的实际
  `observed_at_bjt` 为 `2026-08-31T15:21:18.969554+08:00`。
- result：`acquire_live_generation_inputs()` 在 AkShare sector membership 阶段
  以 `ConnectionError` 映射为 `PROVIDER_FAILURE`；有限 retries 已耗尽，未形成 READY
  manifest 或 `LIVE_OBSERVED` package。
- no artifact：没有 input/generation fingerprint、package content/file SHA 或
  logical path；`data/prospective_inputs/` 未创建，没有 recovery copy 可登记，也
  没有 canonical watchlist。Tencent quote/Kline、market_env、persistence 和后续
  frozen-candidate checks 均为 `NOT_REACHED`。
- next gate：`FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_PROVIDER_FAILURE`；若仍在同一
  BJT 日期且已正式收盘，可用新的 `observed_at` 独立重新执行完整 contract，不复用
  本次失败的 partial response；跨日后不得回填本次 T。

## 17. PR #16 — same-day retry semantics and bounded AkShare reads

- task classification：本轮仍属于 product blocker 审计，并包含 provider-induced
  correctness fail-closed 风险；不是新的 strategy research、参数选择、Phase 2F 或
  Final OOS 任务。
- governance conflict closure：Sol review 将 `PROJECT_GOVERNANCE_STATE_CONFLICT`
  限定为 retry 表述错误。Phase 2B 允许在同一 BJT 日期 T、正式 session close 后发起
  新的独立 acquisition attempt；每次使用新的真实 `observed_at`，不复用 failed
  attempt 的 partial response，不改写第一次失败。跨至 `2026-09-01` 后，当前 live
  provider 数据不得构造 `T=2026-08-31` package。
- implementation：`scripts/live_acquisition.py` 对
  `stock_info_a_code_name`、`stock_board_industry_name_em` 和每个
  `stock_board_industry_cons_em` provider read 增加固定最多 3 次 transient
  network/connection retry，backoff 为 bounded `0.25s` / `0.50s`。返回后的 schema、
  empty、duplicate、name/sector conflict 和 coverage validation 不重试；exhaustion
  映射 `PROVIDER_FAILURE`，不形成 formal output。
- identity boundary：retry attempts/backoff 只保留进程内诊断，不进入 canonical input
  fingerprint、candidate-bound generation fingerprint、package content identity 或
  成功 provenance；provider source、最终捕获数据和 runtime identity 语义不变。
- scale audit：完整 universe 的模型为 1 次 universe read、1 次 definitions read、
  每个 sector definition 1 次逻辑 member read、`ceil(N / 50)` 个 Tencent quote
  batches、N 个 planned stock Kline requests 加 1 个 index Kline request；这些是
  execution diagnostics，不是筛选规则。首次正式失败在 sector membership，后续
  quote/Kline 计数为 `NOT_REACHED`，不允许缩 universe 或跳过股票。
- evidence boundary：本次实现与回归测试不改变 B strategy/spec/threshold、Phase 2B
  protocol、provider source semantics、冻结 artifact identity 或 Final OOS 状态；
  同日新的真实 acquisition 必须在 clean merged master 上重新获取全部 required
  input，并在 `FROZEN_CANDIDATE_PREREQUISITES` 决策点审计。

## 18. PR #16 merge and same-day retry decision — 2026-08-31

- PR #16：exact head `f604dc39c681ee63c075cc0fea5cef367d6296f5`，squash merge
  `c9d5e50be833bf5bb1c3c83c0a2fa1b3e83979c1`；merge master correctness run
  `33372781495` success，head 精确匹配 merge SHA。
- second attempt：clean merged master `c9d5e50…` 上重新运行完整
  `acquire_live_generation_inputs(T=2026-08-31)`，新的真实
  `observed_at_bjt=2026-08-31T16:27:36.974203+08:00`。第一次
  `15:21:18.969554+08:00` 的失败和 partial-response 不被复用。
- result：AkShare `stock_info_a_code_name` 在 attempts `3/3` 后为
  `PROVIDER_FAILURE / ConnectionError`；adapter acquisition elapsed
  `0.782s`。sector code/name 不适用；completed sector calls `0`；sector definition
  count `NOT_REACHED`；universe symbol count `0`；Tencent quote batches、stock/index
  Kline、market_env、manifest 和 persistence 均 `NOT_REACHED`。
- artifact/recovery：没有 READY manifest、`LIVE_OBSERVED` package、input/generation
  fingerprint、content/file SHA、logical path 或 `data/prospective_inputs/`；没有
  partial formal evidence，也没有 recovery copy。最终 decision 为
  `FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_PROVIDER_FAILURE`。
- current formal state：Formal Delivery Ladder 仍为 `development candidate`；B
  eligibility、strategy/spec/threshold、冻结 artifact、Final OOS sealed status 和
  non-blocking `phase2e.hithink_probe` metadata debt 均未改变。停止在本 decision node，
  不创建 `FROZEN_CANDIDATE_CONTRACT_V1`。

## 19. P0 live sector taxonomy correction — 2026-08-31 (review branch)

- task classification：本轮是 `correctness blocker`，同时修正阻止 candidate-bound
  live path 可用的 provider architecture；不是 strategy research、参数选择、Phase
  2F、Final OOS 或 promotion。
- intake live state：用户指定 master/`origin/master` 为
  `3b5b2f9abb6413bd4a2bbd531e11a8162e1bb2c9`，intake 时无 open PR；本修正分支为
  `codex/live-provider-taxonomy-correction`。已有未跟踪
  `data/validation/continuous_speed_probe/` 属于用户内容，未触碰。
- blocker：merged adapter 使用 Eastmoney
  `stock_board_industry_name_em` / `stock_board_industry_cons_em`，但 B 冻结的 exact
  legacy provenance 是 AkShare Sina `stock_sector_spot` / `stock_sector_detail`，
  taxonomy=`新浪行业`；EM/THS/SW 不能替代。两次 `2026-08-31` live attempt 均在
  package 构造前 fail closed，没有 contaminated prospective artifact。
- capability audit：HiThink Financial-API 的 authenticated metadata/ticker、snapshot、
  stock/index historical K 和 adjustment-events endpoint 当前均返回 HTTP 200 /
  `code=0` 结构化响应；AkShare `1.18.94` 的 exact Sina spot/detail 当前可调用，probe
  返回 49 个行业及首个 detail 的 19 个成员。probe 只验证能力，不保存 payload、不构造
  manifest/package、不改变 T=`2026-08-31` 的失败事实。
- decision：`ADOPT` 最小 provider correction。HiThink metadata 为 universe/name
  primary；HiThink forward stock K、raw index K 为 market-data primary；exact Sina
  sector 为唯一 sector source；Tencent quote 保留既有语义；Tencent Kline fallback
  仅在 `LIVE_MARKET_DATA_FAILOVER_POLICY_V1` / `TENCENT_QFQ_FALLBACK_V1` 下显式记录；
  provider/schema/date/coverage/taxonomy failure 全部 fail closed。
- invariant：B strategy/spec/threshold、B spec SHA
  `5bbeb345ebd8883149138d2f29f8606f919949ae285aa2839fa337921dfc7112`、T-close/T+1、
  no current-data backfill 和 no-future semantics 均不变；新增 raw-index mode 只诚实
  表示 HiThink index endpoint 无 adjustment，不修改 B strategy。
- verdict：`HITHINK_LIVE_PRIMARY = SUPPORTED`；
  `EXACT_SINA_SECTOR_SOURCE = AVAILABLE`。
- PR/live state：单一 PR #17 已创建并保持 `OPEN`，base=`master`/
  `3b5b2f9abb6413bd4a2bbd531e11a8162e1bb2c9`，head=
  `869eade1eaf48e2d470175e234e83c99fd2168ac`；pull-request correctness run
  `33379014737` 与 push correctness run `33378978157` 均在该 exact head 成功，PR
  当前 `CLEAN`/`MERGEABLE`。这是 live GitHub snapshot；不得把它视为已合并。
- stop condition：停在 Sol review；review/merge 后还需用户明确授权，才能在新的合法
  T-close session 重新执行完整 acquisition。当前不运行 prospective package，不创建
  canonical watchlist，不测试 C，不启动 Phase 2F，不调参，不读 Final OOS，不 merge。

## 20. PR #17 final contract hardening — 2026-08-31 (review branch)

- classification：`correctness blocker` + `product blocker` hardening；不启动新的
  strategy、Phase 2F、参数选择、Final OOS 或 promotion。
- validator：stock `KlineManifest` 只接受 `PROVIDER_QFQ_SNAPSHOT`；HiThink index
  primary 只接受 `PROVIDER_RAW_SNAPSHOT`；Tencent index fallback 只接受
  `PROVIDER_QFQ_SNAPSHOT`；其他 provider/adjustment 配对 fail closed。
- universe scope：`TRADABLE_UNIVERSE_SCOPE_V1 = SH_SZ_A_SHARE_ONLY`，SH/SZ A 股
  included，BJ explicitly excluded；scope/version 已进入 UniverseManifest content
  identity、GenerationInput input fingerprint、live generation identity、provider
  metadata 和 provenance。BJ absence 不属于 incomplete coverage；未来加入 BJ 必须新
  scope/version。既有 B development eligibility 不重跑；若历史输入含 BJ，只记录
  `KNOWN_DEVELOPMENT_VS_PROSPECTIVE_UNIVERSE_SCOPE_DIFFERENCE`。
- invariants：B strategy/spec/threshold、冻结 historical artifact、Final OOS sealed
  status 和 T-close/T+1 semantics unchanged；当前没有 live package/watchlist 或新的
  prospective evidence。

## 21. Post-merge first LIVE_OBSERVED acquisition attempt — 2026-08-31

- PR #17 was squash-merged after final exact-head review: final PR head
  `ef48d192c7709a7194348369c689070c665da2b4`; merge SHA
  `91e9ec76e3f4ea8ffaa1badeb759c1d2a7f5f73b`.
- Merge master correctness run `33399324692` completed `success` with exact
  `headSha=91e9ec76e3f4ea8ffaa1badeb759c1d2a7f5f73b`.
- A new independent formal acquisition used `T=2026-08-31`, `T+1=2026-09-01`,
  `LIVE_OBSERVED`, and fresh `observed_at_bjt=2026-08-31T22:01:28.307161+08:00`.
  It did not reuse the 15:21/16:27 attempts, capability probe, or partial responses.
- The post-merge provider path reached exact Sina sector/member validation and failed
  closed with `INPUT_CONFLICT: display-name conflict for 000012: universe/member`.
  Quotes, stock/index Kline, market_env, READY manifest, package serialization,
  persistence, Drive upload, and recovery read-back were not reached.
- Final current decision is
  `FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_INPUT_CONFLICT`; the blocker is an
  input/provider-data consistency conflict, not provider connectivity; no package hash, file
  hash, byte length, local logical path, Drive reference, or recovery state exists.
  No new frozen-artifact registry record was fabricated; the compact attempt evidence
  is `data/governance/prospective_input_attempt_evidence_20260831.json` and is marked
  `not_a_frozen_artifact=true`.
- B strategy/spec/thresholds, scope/version, T-close/T+1, fail-closed, provenance,
  monitoring/rollback, Final OOS sealed/unread, C exclusion, Phase 2F exclusion,
  and no-tuning/no-promotion boundaries remain unchanged.

## 22. PR #18 — display-name consistency blocker diagnosis and minimal fix

- task classification：`correctness blocker`；不是新的 strategy research、Phase、参数选择、
  Final OOS 或 promotion。
- historical correction：2026-08-31T22:01:28 的 attempt 保留原始失败事实
  `INPUT_CONFLICT` / `display-name conflict for 000012: universe/member`，但最终分类
  修正为 `FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_INPUT_CONFLICT`，类别为
  `INPUT_PROVIDER_DATA_CONSISTENCY_CONFLICT`；provider connectivity 明确为 false。
  原始 attempt 未记录 raw names/counts，不用 current diagnostic 回填。
- current diagnostic：完整当前 `SH_SZ_A_SHARE_ONLY` universe 为 5,220 symbols；exact
  Sina definitions 49，completed member calls 49；common symbols 2,539，其中 exact
  raw-name matches 2,492，raw-name mismatches 47。固定
  `DISPLAY_NAME_NORMALIZATION_NFKC_TRIM_EXPLICIT_ZERO_WIDTH_V1` 消除 0 个冲突；
  所有 47 个在 normalization 后仍不一致，故当前真实 blocker 为
  `FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_SUBSTANTIVE_NAME_CONFLICT`。完整 raw/code-point
  清单见 `docs/current_capability_name_diagnostic_20260831.md`；该文件不是 prospective
  evidence。
- implementation：live adapter 保留 universe/sector raw display names，只比较固定
  normalized values；symbol 仍是 security identity；normalization version 进入
  generation identity/provenance；name conflict 暴露 symbol、两边 raw/normalized name、
  universe count、sector definition count 和 completed member calls 等非 secret diagnostics。
  无 partial formal package persistence。
- invariants/next gate：B strategy/spec/threshold、`SH_SZ_A_SHARE_ONLY`、exact Sina
  taxonomy、T-close/T+1、Final OOS sealed/unread、C/Phase 2F exclusion 和 no tuning 均不变。
  2026-09-01 白天只完成修复/review；PR #18 Sol review/merge 后，且 XSHG 正式收盘，才
  允许新的 `T=2026-09-01`, `LIVE_OBSERVED` acquisition；绝不构造 T=`2026-08-31` package。

## 23. 2026-09-01 continuation — B dependency audit and fresh-machine handoff

- task classification：`correctness blocker` + `product blocker`；不启动 strategy、
  Phase 2F、C、Final OOS、tuning、promotion 或 T-close acquisition。
- source decision：B 不消费 display name for join/selection/gates/trigger/stop/target/
  RR/score/status/canonical identity；exact symbol 是 security identity。B 确实消费
  sector membership/evidence、`sector_rank` 和 `sector_chg`，后两者进入 B 85-score，
  missing evidence 返回 `INSUFFICIENT_DATA`。详细 matrix 见
  [`docs/b_dependency_audit_20260901.md`](docs/b_dependency_audit_20260901.md)。
- policy decision：`ADOPT`
  `DISPLAY_NAME_CONSISTENCY_POLICY_V2_SYMBOL_AUTHORITATIVE`；raw names 独立保留，
  registered normalization 只做 diagnostics，不 fuzzy reconcile、不生成 alias、不用
  name join/filter。active contract 为
  `CANDIDATE_BOUND_PROSPECTIVE_INPUT_PROVENANCE_CONTRACT_V2`，V1 保持历史 evidence。
- current provider diagnostic：fresh preflight exact dependency versions PASS；HiThink
  5,221 scoped symbols，exact Sina 49 definitions/49 member calls；sector audit 当前
  2,682 universe symbols 缺 membership、439 sector symbols outside universe、47 name
  mismatches（normalization resolve 0）、5 distinct multi-sector symbols
  (`000587`,`000602`,`002217`,`002617`,`600714`)，exact duplicate symbol 为 0。结果
  明确标记为 `LOCAL_CURRENT_SNAPSHOT_DIAGNOSTIC_NOT_PROSPECTIVE_EVIDENCE`，不回填
  2026-08-31。
- current gate：`FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_SECTOR_MEMBERSHIP_AMBIGUITY`
  并伴随 exact-Sina coverage failure；`NEEDS_MORE_EVIDENCE` 只针对 future legitimate
  T-close 的 complete/unambiguous sector response。不得丢 symbol、缩 universe、猜
  sector、换 taxonomy 或写入 partial package。
- fresh-machine status：workspace-local `.venv` rebuilt from `pyproject.toml` with
  `.[test,research]`; runtime and preflight PASS. Codex app Drive profile、formal backup
  metadata/raw streamed read reference 和 temporary upload/readback/delete probe PASS；
  formal `daily_k.parquet` byte-level recovery hash 未在本轮重新物化，因此不升级其
  existing recovery claim。
- live snapshot before this governance change：branch
  `codex/prospective-input-blocker-evidence-20260831`，HEAD/PR #18 head
  `dc358ca3456d1aba7704513c309e165b24309f11`，base/`origin/master`
  `91e9ec76e3f4ea8ffaa1badeb759c1d2a7f5f73b`，PR `OPEN/CLEAN/MERGEABLE`；exact-head
  correctness runs `33407668273` and `33407662674` were `success` at that snapshot.
  This is persisted pre-change provenance; final live head/CI must be re-queried after
  the governance commit/push.

## 24. 2026-09-01 sector-provenance closure

- classification：`correctness blocker` + `product blocker`；不启动新的 strategy、
  Phase 2F、C、Final OOS、tuning、promotion 或 formal T-close acquisition。
- live Git/GitHub：PR #18 已针对 actual head
  `0bfe7d1e012ad5213b82b5bbfe42776e5f3a0652` 完成 exact-head review，并 squash merge
  到 `master`，merge SHA=`17371fde39a6b24241532b131caf5927cb9b8933`。merge 后 push
  correctness run `33476256589` 在 exact merge SHA 成功。当前 closure branch 是从该
  merged `origin/master` 创建的 `codex/sector-provenance-closure-20260901`；当前
  HEAD 为该 local unpublished governance commit，`origin/master`=
  `17371fde39a6b24241532b131caf5927cb9b8933`。该治理 commit 尚未 push，没有新 PR，
  因为本轮没有发现可安全合并的 code correction；最终 live SHA 以交接时 Git
  snapshot 为准。
- source semantics：精确读取 V0
  `EFSing/ashare_watchlist-V0@c8406c393c0b135eafb0aec763576ae869fddcff` 后确认，
  missing sector 在 V0 是 `("-", 50, 0.0)` 默认并继续 B；multi-sector 是 provider
  sector iteration 下 last-write-wins。当前 B evaluator 对 missing evidence 返回
  `INSUFFICIENT_DATA`，因此不是仅有 package-level hardening，而是 evaluator-level
  exact reconstruction difference。
- exact-source parity：AkShare `1.18.94` 与 Sina raw endpoint 对 49/49 definitions
  完成逐 sector 审计；raw/wrapper rows 都为 2,983，unique symbols 为 2,978，49 个
  row-count/边界均一致，parse/call/duplicate error 为 0。count endpoint 的低报只
  形成 provider consistency diagnostic，当前没有可安全合并的 wrapper 修复。
- coverage diagnostic：current `SH_SZ_A_SHARE_ONLY` 为 5,221；sector common 2,539；
  missing 2,682；outside-scope 439；distinct multi-sector 五个为
  `000587`,`000602`,`002217`,`002617`,`600714`。listing date/status 不在当前
  HiThink response，未推断 cohort、delisting 或 code reuse。
- final decision：`B_RECONSTRUCTION_SEMANTIC_MISMATCH`。Model S/V3 不采用；不修改
  B/spec/threshold、sector taxonomy、universe scope、name policy 或 provider wrapper。
  formal `T=2026-09-01` capture=`NOT_RUN`；没有 READY manifest、package、watchlist 或
  prospective result。详见 [`docs/sector_provenance_closure_20260901.md`](docs/sector_provenance_closure_20260901.md)。
- worktree boundary：既有未跟踪 user directory
  `data/validation/continuous_speed_probe/` 未读取、未修改、未删除。该 closure 只
  新增 governance evidence，后续交接前需重新核对 branch/HEAD/origin/master/PR/CI
  和 final checks。

## 25. 2026-09-01 continuation — frozen B spec text conflict

- classification：`correctness blocker` + `product blocker`；任务分类未改变。
- live intake：本地 branch 为 `codex/sector-provenance-closure-20260901`，rebase 后
  HEAD=`3d5f3b185f95a8215eed3eb0a88a54e568333acc`，`origin/master`=
  `fc0698c20fb3e7909090cf5073c59d1a2dd710f3`；tracked working tree clean，既有未跟踪
  `data/validation/continuous_speed_probe/` 未触碰。GitHub open PR 为 0；PR #18 已以
  `17371fde39a6b24241532b131caf5927cb9b8933` 合并，merge exact-head correctness run
  `33476256589` success。
- closure branch protection：本地 closure evidence 已保留并 rebase；推送到 origin
  被安全审查拒绝，故 remote branch 未创建，状态为 `REMOTE_PROTECTION_NOT_ESTABLISHED`。
  不通过其他路径外发内部治理/诊断证据。
- exact V0 finding：指定 commit 的 `get_sectors()` 按 spot `label` 顺序逐一读取
  `stock_sector_detail()`，按返回 member 行顺序执行 `mapping[symbol] = name`；主流程
  对缺失映射使用 `sec_name="-"`、`sec_rank=50`、`sec_chg=0.0`，继续调用
  `analyze()`。因此 multi-sector 是 provider traversal order 下
  `LEGACY_PROVIDER_ORDER_LAST_WRITE_WINS_V1`。
- blocking conflict：当前 `scripts/b_breakout_retest.py` 继承的 executable
  `LEGACY_SPEC["input_contract"]["sector_evidence"]` 明确写有
  `silent_fallback=False`、`missing_status=INSUFFICIENT_DATA`。该 frozen spec text
  与 exact V0 不一致，当前 stop state 为 `B_FROZEN_SPEC_TEXT_CONFLICT`；没有修改
  evaluator、contract、strategy/spec SHA 或旧 eligibility bytes，也没有继续 T-close。
- independent identity note：从指定 V0 commit 读取的 Git blob
  `ashare_watchlist/scripts/screen_system.py` SHA-256 为
  `843935d9b86ec05af848ee8cc54812334475e3d17807cb93349a02c84896417a`，而现有 frozen
  declaration 为 `6cac746123e315199cbeeb1a612868ef77b50af6c7c64b0d80eb387ae1d19f9`；
  原 declaration 未覆盖，状态为 `PROJECT_GOVERNANCE_STATE_CONFLICT` / identity
  unresolved，需 Sol review。
- eligibility audit：按 mandated stop condition 尚未审计 17,714-event artifact，故
  `EXISTING_B_ELIGIBILITY_ARTIFACT_AFFECTED=UNRESOLVED`；未标记旧 artifact superseded，
  未生成 corrected artifact，未运行 `T=2026-09-01` capture。

## 26. 2026-09-01 B candidate identity/provenance closure

- classification：`correctness blocker` + `product blocker`；本轮没有启动新的
  strategy、Phase 2F、C、Final OOS、tuning、promotion、T-close acquisition 或
  eligibility replay。
- V0 identity：remote repository `EFSing/ashare_watchlist-V0` 的 `main` ref 实时指向
  `c8406c393c0b135eafb0aec763576ae869fddcff`；exact path 为
  `ashare_watchlist/scripts/screen_system.py`。Git object format=`sha1`，blob OID=
  `ede1ee62451fa9b817bf390ab75e963115a678dc`，raw blob bytes=21,770，raw/LF SHA-256=
  `843935d9b86ec05af848ee8cc54812334475e3d17807cb93349a02c84896417a`。CRLF 转换后的
  64-char SHA 为 `6cac746123e3151999cbeeb1a612868ef77b50af6c7c64b0d80eb387ae1d19f9`，
  但声明的 candidate value 只有 63 chars：
  `6cac746123e315199cbeeb1a612868ef77b50af6c7c64b0d80eb387ae1d19f9`，二者不相等。
  这是 unresolved declared SHA mismatch，不是 Git blob SHA 混淆。声明值未修改，canonical raw tuple 见
  [`b_candidate_identity_provenance_20260901.md`](docs/b_candidate_identity_provenance_20260901.md)。
- V0 source identity remains `V0_SOURCE_FILE_IDENTITY_UNVERIFIED_DECLARED_SHA_MISMATCH`;
  repository/commit/path are established, but the required source-file declaration is not
  verified. The semantic B Case A/B decision and eligibility impact audit remain blocked.
- B spec lineage：machine-readable object 是
  `scripts/b_breakout_retest.py:LEGACY_SPEC`，由 PR #14 squash commit
  `4e685ba28668ada29f78e6fa4a56be1cacc259ea` 创建；其
  `copy.deepcopy(A_LEGACY_SPEC)` 机械继承 A 的 `silent_fallback=False` /
  `missing_status=INSUFFICIENT_DATA`，B-specific overrides 没有重写 sector block。
- semantic evidence：V0 实际路径为缺失 sector 使用 `("-",50,0.0)` 继续评估、multi-sector
  provider-order last-write-wins；PR #14 B spec 机械继承 generic hardening，且未找到
  pre-returns 的 B-specific stricter adoption evidence。由于 V0 declared source SHA 仍未
  验证，最终 classification 必须 fail closed 为 `B_CANDIDATE_IDENTITY_UNRESOLVED`；
  不能提前宣布 Case A/B。
- eligibility impact：按 mandated stop condition 未作影响结论；既有 artifact 未
  supersede/overwrite，`EXISTING_B_ELIGIBILITY_ARTIFACT_AFFECTED=UNRESOLVED`。B
  eligibility 使用不接收 sector 的 `evaluate_numeric_projection`、parity fixture 只用
  neutral sentinel、score 不进入 projection/event，但这些结构性事实要在 source/candidate
  identity 解决后才可形成正式 impact decision；真实 missing/multi-sector 数量不填猜测。
- current live snapshot before final governance commit：origin/master=
  `fc0698c20fb3e7909090cf5073c59d1a2dd710f3`；closure branch 已推送到 origin，remote
  head=`3ef6c4643f11256e4f8518adf353322eef6a2c51`；该 head 的 exact push correctness
  run=`33486257291` success。GitHub API 对 branch protection 返回 HTTP 403，故 remote
  branch protection 未独立验证；不能把 403 推断为已配置或未配置。该分支尚无 open PR，
  final head/CI/PR state 需在交接时重新核对。
- next decision：停在 Sol/user review；先解决 declared SHA 的正确 64-char identity 或
  historical source/canonicalization 证据，之后才能重开 Case A/B 与 eligibility audit，
  再另行授权 versioned semantic repair。当前 B spec、evaluator、contract、threshold、旧
  artifact 和 Final OOS 均保持不变。

## 27. 2026-09-01 continuation — corrected B reconstruction and impact closure

- classification：`correctness blocker` + `product blocker`；任务仍不启动 C、Phase 2F、
  调参、promotion、Final OOS、自动 freeze 或历史 T-close backfill。
- PR #19 immutable audit history：已在授权条件下以 squash merge 合并。final head=
  `f99c33993fed00e38e87785a88155034ceaf57c3`，merge SHA=
  `28e871552da0813fd51b510a9ef0980976556d29`；post-merge master exact-head
  correctness run `33491720346` 对该 merge SHA 为 `success`。PR #19 早先的
  `B_CANDIDATE_IDENTITY_UNRESOLVED` 保留为历史时点事实。
- source decision：`V0_SOURCE_IDENTITY_RESOLVED_AUTHORITATIVE_RAW_GIT_BYTES`。canonical
  tuple 是 `EFSing/ashare_watchlist-V0@c8406c393c0b135eafb0aec763576ae869fddcff`、
  `ashare_watchlist/scripts/screen_system.py`、raw/LF SHA
  `843935d9b86ec05af848ee8cc54812334475e3d17807cb93349a02c84896417a`。合法的历史
  CRLF witness 是 `6cac746123e3151999cbeeb1a612868ef77b50af6c7c64b0d80eb387ae1d19f9`；
  旧 63-character declaration 分类为 `HISTORICAL_SOURCE_SHA_TRANSCRIPTION_ERROR`。
- old B disposition：`B_BREAKOUT_RETEST_LEGACY_V1` / old spec SHA
  `5bbeb345ebd8883149138d2f29f8606f919949ae285aa2839fa337921dfc7112` 保留 bytes、
  artifact 和 history，分类为 `SUPERSEDED_RECONSTRUCTION_WITH_PROVENANCE_AND_SECTOR_SEMANTIC_DEFECT`。
- corrected identity：`B_BREAKOUT_RETEST_LEGACY_V1_1`，role
  `CORRECTED_EXACT_V0_RECONSTRUCTION`，spec SHA
  `f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd`。明确恢复
  missing-sector `(-,50,0.0)` continue、provider-order last-write-wins、raw
  membership retention、无 score cutoff/TOP-N；shared numeric path 保持已审计实现。
- impact decision：`EXISTING_B_ELIGIBILITY_ARTIFACT_AFFECTED=FALSE`，
  `ELIGIBILITY_ARTIFACT_EVENT_SET_INVARIANT`。769 sessions / 4,041,140 evaluated
  symbol-dates，旧/校正 event count 均 17,714，projection/status/event membership
  differences 均为 0；historical sector missing/multi counts 仍是
  `NOT_AVAILABLE_IN_FROZEN_DEVELOPMENT_INPUT`。不重算 returns，不覆盖旧 artifact。
- corrected candidate：`CORRECTED_B_CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES`。
  future live binding 已切换至 V3 contract；尚无 live instance。V3 见
  [`docs/candidate_bound_prospective_input_contract_v3.md`](docs/candidate_bound_prospective_input_contract_v3.md)，
  evidence 见 [`docs/b_corrected_reconstruction_20260901.md`](docs/b_corrected_reconstruction_20260901.md)。
- live snapshot before correctness PR creation：branch=`codex/b-corrected-reconstruction-20260901`，
  HEAD=`28e871552da0813fd51b510a9ef0980976556d29`，`origin/master` 同 SHA，尚无新
  open PR；working tree 的 corrected implementation/audit/docs 为本任务改动，既有
  未跟踪 user directory `data/validation/continuous_speed_probe/` 未读取、未修改、未删除。
- pre-merge persisted snapshot after correctness PR creation：PR #20 当时为 open，head=
  `078bc3c083c1b3d309505a10715745b8acd6ef4e`，base/
  `origin/master`=`28e871552da0813fd51b510a9ef0980976556d29`；该段仅保留当时的
  review/CI provenance，不代表当前 live state。
- current post-merge snapshot：PR #20 已 squash merge，merge SHA、当前
  `master`/`origin/master` 均为 `106bfbd00502db56a2e544f1c804a52372c1fa3e`；
  master exact-head run `100101351273` 为 `success`，GitHub open PR 为 0。当前
  corrected candidate 已进入等待 `T=2026-09-02` 合法 T-close prospective capture
  的状态。
