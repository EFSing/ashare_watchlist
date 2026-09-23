# CURRENT STATUS

## 2026-09-23 — C daily research list implementation, activation pending

- Independent C aggregation and self-contained mobile HTML now show each stock's rule matches,
  price trend/pullback/rebound, support/resistance, RV_T, pullback/reference and first/second-half
  volume, and up/down-day asymmetry. An empty match set renders an explicit report. Synthetic
  preview: `docs/examples/c_daily_research_watchlist_synthetic.html`; it is not a real daily result.
- The same-runner reader checks frozen B package/file/content SHA, qfq identity, raw sidecar SHA,
  T-day ST/name and per-request timing before calculating C. B input isolation remains a coverage
  gap. Formal volume confirmation and `entry_candidate` remain false; volume adjustment effect is
  `UNRESOLVED`. The report does not claim Formal B or `PROSPECTIVE_CAPTURED` status.
- Automatic daily delivery is **not active**. Current B workflow holds a production concurrency
  lock for the whole job. A same-job C step would hold it, and a separate job needs a transfer of
  package/raw evidence. The repository is public; no private, size-validated runner transfer or
  independent report persistence has been demonstrated. These are product activation blockers.
- #81/#83/#84 stay Draft and unmerged. This work is stacked on #83; #84's private Release path is
  unused. The narrow #84 raw request/response timestamp recording is included here directly.

更新时间：2026-09-23（Asia/Shanghai）

本文件只记录当前有效状态；历史实现过程与旧 checkpoint 以 Git history / PR / CI 为 provenance，
长期约束理由见 `docs/DECISION_LOG.md`，跨设备接手动作见 `HANDOFF.md`。
恢复时必须实时读取 `origin/master`、相关 PR/CI 与 `runtime-state`，不得把本文 SHA 当永久真相。

## 2026-09-23 — C_VOLUME_OBSERVATION_AND_STORAGE_REUSE_READY_FOR_SOL_AUDIT

- #83 保留 B 冻结逐日 volume 的 RV_T、可形成价格回踩时的 path/方向性及前后半程
  描述值；`VOLUME_FEATURE_COMPUTED` 与 `VOLUME_BASIS_UNVERIFIED` 并存，正式
  `volume_confirmation_valid=false`、`entry_candidate=false`。原下文“仅记录原值”
  已由本记录纠正。2026-09-22 的 9 只 B 隔离股票仍是缺口。
- 现有私有 Drive 根目录通过 Codex connector 实际可读，项目账号为 owner、未共享；
  可见 180,203,424-byte 的历史 daily-K 备份及既有小型 watchlist。
  Drive 中另有 2026-09-07 既有分块备份，package/outputs 约 556 MB、source evidence
  约 564 MB；它们是容量先例，不是本次完整 B→C bundle 的实测大小。
  云端 B runner 无已验证 Drive 写入接口/授权，剩余额度和单日完整 package/raw
  大小未获证实，
  因此不能启用自动 B→C Drive 交接或声称跨设备捕获。#84 的私有 GitHub 后端
  保持默认禁用；用户没有新私有仓库额度。C 自身的私有 state repo 工作流同样
  尚无已验证目标；本地 C 记录不能冒充跨设备持久化。
- Formal B 与 C 研究观察继续隔离；无 merge、正式历史收益、调度、通知或下单。

## 2026-09-23 — C_SHARED_INPUT_ACTIVATION_RELEASE_GATE_READY_FOR_SOL

- #83 reader 已将私有独立读回、T 日逐票价格/ST 证据、B 输入隔离、C 自身排除、
  主板覆盖和 volume 语义分层。真实 HiThink 响应时间只从 raw sidecar 获取；runner 起点、
  mtime、C 下载时间不能替代。逐票证据通过可形成
  `PRICE_OBSERVATION_VOLUME_UNVERIFIED`，不等于正式候选或 `PROSPECTIVE_CAPTURED`。
- #84 独立记录 HTTP 逐请求开始/接收时间，未增加请求；交接诊断区分本地导出、
  私有持久化、独立读回、receipt 读回及 C 实际消费。同日重试以 package SHA 隔离。
  正式 B 结果不受可选交接失败影响。两 PR 未合并且真实云端交接未配置。
- HiThink 历史 volume 单位为股，B 逐 bar 原值复制；`adjust=forward` 对 volume
  的影响仍 `UNRESOLVED`，量价确认禁用。下一项验收为真实同日 B package/raw 私有读回
  与 C 消费，并由 Sol 核对完整证据契约。

## 2026-09-23 — C_QFQ_SHARED_INPUT_HANDOFF_READY_FOR_SOL_FINAL_ACTIVATION_AUDIT

- 用户正式选择 A，前瞻 C 输入版本为 `C_QFQ_INPUT_V1`：B 当日冻结 qfq 股票历史 OHLC
  是唯一价格输入；原未复权方案保留历史身份，不能混算。`BALANCED_A` / `CONSERVATIVE_B`
  结构参数及 Formal B 均未改变；没有正式历史收益研究。
- HiThink 历史 `volume` 文档单位为股，B 直接复制响应数值；`adjust=forward` 对该字段的
  影响 `UNRESOLVED`。C 仅可记录原值/来源，不得将量价确认列为有效信号。
- #83 需要显式 T、package SHA 和 handoff manifest SHA，并核验私有读回 receipt、archive
  与逐文件身份。B 已评估股票、B 输入失败隔离、C ST/规则排除单独记录；缺 T-known ST
  或时间证据的股票不计算 C 规则观察。2026-09-22 的 9 只隔离仍是覆盖缺口。
- #84 独立 B 交接 PR 在 B 成功后只读导出，私有上传、独立下载和最终 SHA/字节数读回
  由单独结果记录。真实私有仓库配置与同日验收尚未发生，不能宣称真实
  `HANDOFF_VERIFIED` 或 `PROSPECTIVE_CAPTURED`。两 PR 保持 Draft、未合并、未启用。

## 2026-09-23 — C_B_TO_C_HANDOFF_AND_PRICE_BASIS_READY_FOR_SOL_DECISION

- Classification: `correctness blocker`，未改变。#83 C reader 现经 B 实际
  `LiveInputPackage.to_bytes()` 与 `persist_live_input_package()` 验证，修正 B K 线 SHA
  不带换行的编码差异，并核对 generation fingerprint、逐票 SHA、隔离覆盖和 raw sidecar。
- #83 手工工作流可从配置的私有 handoff release asset 下载并逐文件核验；独立 B 导出
  Draft PR 从最新 master 提供成功后只读导出，默认配置未启用。真实私有读回、逐请求时间、
  B 持久化时间、T-known ST 和成交量语义仍未验收，不能宣布 `PROSPECTIVE_CAPTURED`。
- B 股票历史响应请求 `adjust=forward`；同日 raw evidence 没有未复权 OHLC 或调整因子，
  当前无法确定性还原 C 原始 raw 定义。研究口径 A（新协议采用 B qfq）与 B（保留原
  未复权口径并维持输入不完整）待用户选择，不能以未来收益决定。
- 2026-09-22 `runtime-state` checkpoint SHA-256
  `826f02807bb58846788137bdaa85d47455fa679497dbd82f49f5cf2898b8ccb1`：
  5,576 原始、3,196 合格、3,187 评估、9 隔离；完整 package/raw 未持久化。

## Historical checkpoint — 2026-09-23 — C_SHARED_INPUT_REUSE_READY_FOR_SOL_AUDIT

- Classification: `correctness blocker`，本轮未改变。新版 C 的主路线改为只读消费 B
  已冻结的全量收盘输入，再由 C 独立计算规则；独立 HiThink 请求降为关闭的备用方案。
- B 现有成功路径在 runner 临时 data root 持久化完整 generation input package 与 source
  evidence，但 `runtime-state` 白名单不包含这些字节。候选名单、checkpoint、诊断摘要均不足以
  代替全量输入。`NO_VALID_INPUT` 和持久化失败没有可恢复的完整 package。
- C reader 已实现 package 文件 SHA、内部 SHA、T 日、完整逐票覆盖与 K 线 SHA 校验，写入
  C 私有 `shared_input` 观察/失败记录；B 重试后可重新读取。已识别的 qfq/raw 口径、T 日 ST
  原始来源、逐请求时刻和真实持久化时间缺口使当前结果只能是
  `CAPTURE_PARTIAL_UNVERIFIED` 或 `CAPTURE_FAILED`，不能是 `PROSPECTIVE_CAPTURED`。
- C 工作流移除了早于 B 完成的定时触发，失败后的私有状态发布使用 `always()`；由于 B
  尚无跨任务原始输入交接，工作流仍不启用。最小 B 只读导出设计在
  `docs/research/c_prospective_capture_v1.md`，需 Sol 审计；本 PR 未改 B 生产代码。
- Verification: C focused `50 passed`; B acquisition/runtime isolation `206 passed`；full suite
  `724 passed, 2 skipped, 10 warnings`；`compileall` 和 `git diff --check` 通过。
- Draft PR #83 继续 stacked on Draft #81，不合并。实时 SHA/CI 以 GitHub 当前结果为准。

## Historical checkpoint — 2026-09-23 — C_PROSPECTIVE_ACTIVATION_GATE_READY_FOR_SOL_REAUDIT

- Classification: `correctness blocker + product blocker` for actual C activation. The user
  supplied Sol's audit conclusion that PR #83's real-enable audit failed; this supersedes the
  prior persisted “ready for activation audit” state.
- Live intake: `origin/master=a54bce2c34d1c76298b02f2ddc8347fd88757ace`,
  `origin/runtime-state=2fc7f9f69949b20da0444a13a2dba860c952fc3f`.
- `PROJECT_GOVERNANCE_STATE_CONFLICT` (resolved): master gained PR #82 after the old #81 base
  `4633b37ee6eb99bee527d8907e4e51768fd3f82a`; #81 at `02c7116` was `DIRTY`, and read-only
  merge-tree found a `HANDOFF.md` conflict. Rebased #81 onto current master while retaining its
  C history and the #82 B incident record. Live #81 is now Draft/CLEAN at
  `78b723c96a351038fea379284ba52be3bd645b1a`, based on current master; both exact-head CI runs
  succeeded (`35817419573`, `35817423031`). No B source code was changed.
- PR #83 remains Draft and stacked on #81. Its C implementation and verification checkpoint is
  `26d8fe9c35e22ecdcf0fb182ab1c33dfc0bcdd56`; the pushed code checkpoint
  `dbedf9a3ff35a9a964f3491c97aa19b7067ea805` resolved to #81 head `78b723c`, and both exact-head
  checks succeeded. This final handoff-only update is on top; read the final remote SHA and exact-
  head checks from live PR state. Do not merge either PR.
- C capture repairs require verifiable T-day ST source/time and raw provider response identity;
  prevent fake runtime clock and arbitrary output roots; allow same-day partial recovery while
  retaining immutable attempts, inputs, hashes, and failures; and emit
  `PROSPECTIVE_CAPTURED` only after the full input and finalized index verify.
- A C-only HiThink adapter, independent runner, and serial workflow are prepared. Official provider
  documentation describes one unified key and dynamic limits, not an independently allocated
  B-isolated quota. The adapter has a hard live-request block until provider-issued independence
  evidence is verified. No real provider request has been made. The workflow remains only in Draft
  PR #83 and is not active on the default branch; private state repository and cloud secrets remain
  unconfigured.
- Synthetic C adapter/capture tests: `41 passed`; B isolation: `40 passed`; full suite:
  `715 passed, 2 skipped, 10 warnings`; compileall and diff check pass. Exact-head CI for the pushed
  code checkpoint succeeded in runs `35818216059` and `35818212182`; read live PR checks for this
  final handoff-only update.
  No Formal B modification, C historical-return research, Final OOS read, real schedule,
  notification, or automatic order is authorized.

## Historical checkpoint — 2026-09-22 — C_PROSPECTIVE_CAPTURE_PR_READY_FOR_SOL_ACTIVATION_AUDIT

- Classification: `correctness/provenance gate + product gate`; this is an independent C
  prospective-observation delivery, not a Formal B change, formal historical-return study,
  promotion, merge, automatic ordering, or Final OOS review.
- Live starting point: PR #81 was `OPEN / DRAFT / CLEAN` at intake, with head
  `codex/c-pre-outcome-design-ready-for-sol-audit` at
  `02c7116f5b712b187a2d70e1a46fba061981b6b8`. The implementation is on the separate worktree
  branch `codex/c-prospective-capture-v1`, based directly on that head.
- Delivery: Draft [PR #83](https://github.com/EFSing/ashare_watchlist/pull/83) is
  `OPEN / DRAFT / MERGEABLE / CLEAN`, with base
  `codex/c-pre-outcome-design-ready-for-sol-audit@02c7116f5b712b187a2d70e1a46fba061981b6b8`
  and implementation head
  `codex/c-prospective-capture-v1@a6621ec9dbc98173d785000ae7df4b48bce7c33d`. This governance
  checkpoint itself must be re-read from live Git/GitHub for the final branch tip and CI.
- C capture contract: `scripts/c_prospective_capture.py` and
  `docs/research/c_prospective_capture_v1.md` define the C-only namespace
  `data/research/c_prospective_capture_v1/` with immutable input snapshots, research
  observations, manifests, canonical capture index, logs, and failure diagnostics. A capture
  is `PROSPECTIVE_CAPTURED` only when the same-day after-close request/receive evidence and all
  required T-known fields are complete; missing ST, malformed/future bars, duplicate conflicts,
  and later backfills remain explicit non-success states.
- Protocol correction: `FULL_COMPARABLE_UNIVERSE` and per-rule `MATCHED_EVENT_SAMPLE` are
  distinct; observation-day floating P/L is distinct from T+1 reference execution P/L;
  `RV_T >= 2.0` is confirmation-day-only; continue holding, price-only defense, and
  price-plus-volume defense remain separate; a unified cost model/source must be fixed before
  formal return research without future-return tuning.
- Isolation: no B evaluator, Shadow, return tracker, formal watchlist, daily report, production
  scheduler, B `runtime-state`, automatic order, or real schedule/notification is changed or
  called. No C data was written yet; synthetic tests use temporary roots only.
- Verification: C-focused tests `27 passed` (including eight new synthetic capture tests),
  isolation/regression set `76 passed`, full suite `698 passed, 2 skipped`, compileall and
  diff check pass, and the CI-equivalent Node dispatcher test is `3 passed`. PR #83 exact-head
  CI has two `test` runs, both successful at the exact head: push run
  `35716953816` and pull-request run `35717028240`. Current decision is
  `NEEDS_MORE_EVIDENCE`; wait for Sol's activation audit before enabling any live schedule.

## 2026-09-22 — C_DATA_EVIDENCE_AND_PROTOCOL_READY_FOR_SOL_DECISION

- Classification: `research question + correctness/provenance gate`; no product promotion, Formal B
  change, parameter selection or merge.
- Live Git/GitHub: branch/worktree=`codex/c-pre-outcome-design-ready-for-sol-audit` /
  `D:\dev\ashare-watchlist-c-pre-outcome-design`; `origin/master`=`4633b37ee6eb99bee527d8907e4e51768fd3f82a`.
  The immediately preceding content checkpoint head was
  `f35a4c0877dc0c3d619516eacb1d820bb09cbfbd`; its push run `35712987048` and pull-request run
  `35712992003` were `completed / success` and exact. PR #81 remains `OPEN / DRAFT / CLEAN /
  mergeable`; after this governance-only update, final branch/PR head and exact-head CI are live
  values and must be re-read with Git/GitHub rather than inferred from this persisted snapshot.
- Artifact metadata SHA: source manifest actual SHA-256
  `008643a64e0070433f3d63dca8243f8dad294b049a7accb5d49af3597aae17b0` matches its frozen identity;
  current metadata-only dependency record actual SHA-256 is
  `89901be61dfe01872f54da2b031527c721f6d639016b20806ed918a999a3977d`.
- Daily-K evidence: the authorized read-only external path
  `D:\dev\ashare-watchlist\data\validation\core_signal_validation\raw\daily_k.parquet` is
  `180203424` bytes and SHA-256
  `61189a4850e2eb157453e28e5375e502e20d214508bbe70ea71066ca3e05e426`, exactly matching the
  frozen declaration. The C worktree canonical path remains missing; the external file was not
  copied, overwritten or used as a C replay input. Evidence record
  `data/research/c_pre_outcome_design_v1/daily_k_integrity_check.json` has SHA-256
  `2a0496e3414b4bd43969f66f7cf93c2b7a1e4a698266abdc74243f662799f939`.
- Evidence boundary: daily-K artifact identity=`VERIFIED` only; OHLCV/adjustment semantics are
  `DECLARED_ONLY`; trading-calendar metadata/helper=`VERIFIED` for deterministic session mapping;
  historical T-known ST/*ST=`UNRESOLVED`; per-bar known-at/vintage=`UNRESOLVED`; valid limit/tick,
  intraday sequence and actual T+1 fill=`MISSING`. The acquisition date is not treated as a
  historical visible-time proof.
- Protocol: independent draft
  `docs/research/c_pre_outcome_preregistration_protocol_v1.md`, SHA-256
  `c74447608490fdd7068ea4a018dc3be31358198d3570ead878e5095cc09befd3`. It proposes
  `BALANCED_A` as main and `CONSERVATIVE_B` as sensitivity without outcome selection; compares
  simple trend/momentum, price structure and price structure plus fixed `RV>=2.0` volume gate;
  `robust-z>=3.0` remains observation-only. It fixes the five-session repeated-failure definition,
  independent warning/risk/candidate/support states, MFE/MAE, false-alarm/sell-away/uncertain-fill
  metrics and PIT/evidence-limited/prospective boundaries. It is not adopted or an outcome-study
  authorization.
- Boundary: this checkpoint changed only C research docs, the C data evidence record and necessary
  governance text. No C future outcome, Final OOS, forbidden directory, Formal B, shared production
  code, runtime-state, formal artifact or scheduler was read or changed. No formal C backtest ran.
- Decision: `NEEDS_MORE_EVIDENCE`; terminal
  `C_DATA_EVIDENCE_AND_PROTOCOL_READY_FOR_SOL_DECISION`. Wait for Sol/user decision; do not merge,
  select parameters or enter outcome research.

## Historical checkpoint — 2026-09-22 — C_PRE_OUTCOME_EXIT_VOLUME_FIX_V1 ready for Sol audit

- Classification: `research question + correctness/provenance gate`; no product promotion and no
  Formal B change.
- This C-only repair splits early defense into `PRICE_ONLY_EARLY_DEFENSE` and
  `PRICE_VOLUME_EARLY_DEFENSE` on the same position and price events. Positive upper shadow alone
  is no longer a weakness or volume gate. Repeated rejection without the selected exit condition
  is reported as `REPEATED_RESISTANCE_REJECTION_RISK`; first warning, early candidate and support
  break remain separate.
- No shared production code, Formal B, runtime-state, canonical watchlist, provider acquisition,
  C future outcome, Final OOS or forbidden directory was read or changed. T-known historical ST
  status and per-bar known-at/vintage evidence remain unresolved. Existing daily-K recovery
  locations and declared SHA were listed read-only; no file was downloaded or copied.
- Verification: C `19 passed`; B isolation regression `40 passed`; full pytest `690 passed,
  2 skipped, 10 warnings`; compileall and diff check pass.
- Decision: `NEEDS_MORE_EVIDENCE`; terminal
  `C_PRE_OUTCOME_EXIT_VOLUME_FIX_READY_FOR_SOL_AUDIT`. Draft PR [#81](https://github.com/EFSing/ashare_watchlist/pull/81)
  remains open as Draft against `master`; final head and exact-head CI are live values to verify
  after any later checkpoint. Implementation head
  `52c6f1d7ce71292fd73582d6390b5d24ac68489d` has exact-head push run `35707980389` and
  pull-request run `35707984877`, both `success`. Do not merge or start C outcome research.

## Historical checkpoint — 2026-09-22 — C_PRE_OUTCOME_CORRECTNESS_FIX_V1 ready for Sol re-audit

- Classification: `research question + correctness/provenance gate`; not a product blocker for
  existing Formal B and not a promotion/freeze decision.
- User direction: start independent new C research for Main Board ordinary shares excluding ST/*ST;
  study sustained uptrend shallow pullback, two distinct lows with a higher low, small rebound and
  T-close confirmation. Old C V0 is provenance only; its 30% run-up, 5%–22% pullback, Fib/MA20
  and volume conditions are not inherited. No recent 60-session breakout gate is required.
- Live reconciliation: `origin/master=4633b37ee6eb99bee527d8907e4e51768fd3f82a`; #77/#78/#79/#80
  are merged and #80 master `test` CI is successful. The older #80 open/awaiting-merge wording in
  the retained checkpoint below is a historical snapshot only; no unrelated governance history is
  being cleaned.
- Independent branch/worktree: `codex/c-pre-outcome-design-ready-for-sol-audit` /
  `D:\dev\ashare-watchlist-c-pre-outcome-design`. C module, entry CLI, tests and
  `data/research/c_pre_outcome_design_v1/` are isolated; Formal B, B returns diagnostics, runtime
  state, canonical watchlist, formal daily report and scheduler are unchanged.
- Current delivery: design definitions, volume observables, independent exit research, data
  feasibility report and metadata-only dependency JSON are present. No C future outcome or formal
  historical return study was read or run; Final OOS and `data/validation/continuous_speed_probe/`
  remain sealed/unread and untouched.
- Data gate: frozen metadata declares 769 XSHG sessions, T-anchor price/raw volume semantics and
  deterministic hashes; local `daily_k.parquet` is absent, historical per-bar vintage proof is
  false, and historical T-known ST/*ST status is unresolved. Status is
  `DESIGN_SUPPORTED / FORMAL_OUTCOME_RESEARCH_NOT_READY`.
- Verification: C `16 passed`; B isolation regression `41 passed`; full `687 passed, 2 skipped,
  10 warnings`; compileall and diff check pass.
- Decision: `NEEDS_MORE_EVIDENCE`; terminal
  `C_PRE_OUTCOME_CORRECTNESS_FIX_READY_FOR_SOL_REAUDIT`. Draft PR
  [#81](https://github.com/EFSing/ashare_watchlist/pull/81) remains open against `master`; this
  repair starts from Sol-audited head `edd3039a1d9815eb3bdf4301699cb1fdc90dc815`, and final head/
  exact-head CI remain live GitHub state to verify after the final governance checkpoint push. The
  implementation head `ad6ec63ebc9f47ed1d5822460063cb13234b2cd2` already has exact-head push
  correctness `35706143436=success` and pull-request correctness `35706147202=success`. No automatic
  merge or C outcome access.

## Historical checkpoint — B_PROSPECTIVE_MONITOR_RECOVERY_V1 — 2026-09-22

本节保留 PR #80 合并前的交付快照；实时状态以上方 reconciliation 为准，PR #80 已合并。

本轮分类为 `product blocker + correctness/data-integrity risk`：只恢复 Formal B 旁路的真实
前瞻 Shadow capture，不改变 Formal B、Main Board universe、评分/排序/触发/止损/目标/RR/T+1、
收益跟踪口径、Final OOS 或历史正式产物。

`PROJECT_GOVERNANCE_STATE_CONFLICT` 已按实时证据完成最小 reconciliation：当前
`origin/master=30d3cab3b8c54a028ac57055e083c1ceb4610556`，`origin/runtime-state=
aaebe2d362c0cf467d06662f2792c117c889d0d7`；实时 PR #60=`OPEN / DIRTY / not mergeable`，
PR #68=`OPEN / DRAFT / CLEAN`，PR #77/#78 已进入 master。本任务在独立 branch/worktree
`codex/b-prospective-monitor-recovery-v1` 上进行，未修改这些 PR 或远端 runtime-state。

真实故障不是 HiThink 未获取指数，而是 canonical input 的 transport 类型不一致：
`GenerationInputManifest` 将 `bars` 规范化为 tuple，正常 t-close runner 直接传递
`to_dict()`；Shadow validator 只接受 list，于是将已获取的指数错误判为
`SHADOW_FEATURE_UNAVAILABLE: index.bars is unavailable`。独立量能观察仅消费股票 K 线序列，
因此能在同一输入上继续生成观察。

最小修复位于 `scripts/b_shadow_monitor.py`：既有 bar validator 接受 list/tuple，继续拒绝未来
K 线和非法结构；指数输入缺失仍 fail-closed，保留明确错误，不构造市场环境或填充 0。新增回归
覆盖正常 canonical tuple capture、指数缺失不生成完整捕获、Formal B 候选不变及量能观察与
Shadow 解耦。focused=`34 passed`；full pytest=`670 passed, 2 skipped, 10 warnings`；
compileall 与 diff check PASS。终态：
`B_PROSPECTIVE_MONITOR_RECOVERY_PR_READY_FOR_USER_MERGE_DECISION`。PR #80
(https://github.com/EFSing/ashare_watchlist/pull/80) 已为非 Draft `OPEN / CLEAN / mergeable`；
final head=`25987fb4b85881c1ddf2541d7001bb2b5867ca28`，push correctness
`35694717548=success`、pull_request correctness `35694781177=success`，均 exact-head。等待用户
决定合并，不自动 merge；合并前需重新核对最新 master 与实际代码冲突。

## Current task — DAILY_REPORT_INPUT_COVERAGE_PRESENTATION_FIX_V1 — 2026-09-21

本轮分类为 `deferred improvement`（日报可用性/展示维护），不改变 production input coverage 的
状态与计数语义，也不改变 Formal B、筛选、Score、排序、交易参数、tracker、shadow 或量能计算。

PR #77 branch `codex/friday-volume-observation-only-backfill-v1` 当前实现 commit=`676e69d`：
`DEGRADED` 正文改为“数据质量：部分覆盖”并动态显示有效评估数与异常股票数；`COMPLETE` 原有
简洁展示和 `NO_VALID_INPUT` 明确诊断保持不变。完整 exclusion records、错误枚举、日期、policy
version 与 coverage JSON 继续保存在既有 machine records/metadata。历史增强日报复用锁定候选与
原始 artifact 身份校验，只刷新独立 addendum 的 coverage 展示，不重取行情、不重跑 Formal B。

原正式报告 SHA=`acfbec2a7399c2eb83a5fe62c83ccbbfaf4852b9d9c8013b62de256789178aaa` 未变；watchlist
SHA=`5c16a0e7d57bc78249b05ea067aa798ace2c1e79bac78c1e40532a6b279573ea`、checkpoint SHA=
`64224f29ef102a283b5e83100705484ae55371a33c4e424a8bcffefc331ee376`、delivery receipt SHA=
`d37bf69a170f474faa0bd8fdf35a45820cb7c6767055e67b6d6fdd1e283c3751` 均未变。runtime-state 独立
addendum 从 `9a202c79cb628db0feb080b4a39be20240a4a0110abb65d08cb8995b967c4f24` 更新为
`be2df29f4324bc6729fbfab051d712da4820b2bd05f49e71a3bf74acbabd2c6e`，commit=`15d8da215e27aee898fb63729832233d9a7210fd`。

验证：focused=`5 passed`；短路径 full pytest=`668 passed, 2 skipped, 10 warnings`；compileall 与
`git diff --check` 通过。无 provider/production dispatch，Final OOS=`SEALED / UNREAD`，
`data/validation/continuous_speed_probe/` 未读未触碰。PR #77 已推送并完成最终 head 的 live
exact-head CI 与 mergeability 核验；停在用户合并决策，不自动 merge/production。

## Current task — VOLUME_CARD_VISUALIZATION_AND_CLOUD_DELIVERY_V1 — 2026-09-20

本轮已完成独立股票 K 线量能计算、正常 T-close 持久化、三行量能卡片和 2026-09-18 回顾增强日报。量能只用于报告观察，不改变 Formal B、候选身份、Score、排名、交易参数或生产筛选；renderer 按 `signal_id`/规范化代码读取独立 store，index/shadow 失败不会隐藏有效股票量能。

PR #77 位于 branch `codex/friday-volume-observation-only-backfill-v1`，量能功能实现 head `7d269e3e0ff4019e0310ddafe86be6ff3efde714`；其后仅追加交付记录，当前状态 `OPEN / CLEAN / MERGEABLE`。功能实现 head 的 push correctness=`35519535943` 与 pull_request correctness=`35519538698` 均 `SUCCESS`。本地 focused=`89 passed, 1 warning`，compileall/diff check 通过；本机 actionlint 未安装，本地全量运行被既有 `importlib.metadata` 的 `exchange-calendars=None` 环境异常阻断，但 CI regression 已通过。

原正式报告 SHA=`acfbec2a7399c2eb83a5fe62c83ccbbfaf4852b9d9c8013b62de256789178aaa` 保持不变。runtime-state commit=`0a6feb50aa169d9712844d5a3a16deddae596607` 只新增回顾增强报告，文件 SHA=`9a202c79cb628db0feb080b4a39be20240a4a0110abb65d08cb8995b967c4f24`：https://github.com/EFSing/ashare_watchlist/blob/runtime-state/data/reports/addenda/daily_close_20260918_volume_enriched.html。`600929` 第三项为 `样本不足`/`PULLBACK_WINDOW_LT_4`；未触发生产、通知或原正式报告回写。下一步仅是用户合并 PR #77。

## Current task — FRIDAY_VOLUME_OBSERVATION_ONLY_BACKFILL_V1 — 2026-09-20

本轮是 `RETROSPECTIVE_VOLUME_ENRICHMENT / REPORT_ONLY`：只消费已持久化的 2026-09-18 正式
十只 B 候选，补充下跌日成交量占比、上涨/下跌日均量比、回踩后半/前半均量比。候选身份、原有
顺序、Score 与 Formal B 语义冻结；不重扫、不重筛、不重排、不运行 `daily-t-close`，不读取或写入
prospective shadow/runtime-state。

实时 reconciliation 已关闭旧入口记录的 `PROJECT_GOVERNANCE_STATE_CONFLICT`：live
`origin/master=9bc58344beb5ce9bee2fdfebf4d1e1b452cad6c2`，live
`origin/runtime-state=40cbde2c30da2e2251956b52001b034b75b62ab5`，PR #73/#74/#75/#76 已合并。
本任务 branch 为 `codex/friday-volume-observation-only-backfill-v1`，PR #77，implementation commit
为 `4ba2798f620c119046046855950faabb7d0db77e`；exact-head CI 是 live delivery gate，任何
后续 push 后都必须以最终 head 重读。

独立 addendum `data/reports/daily_close_20260918_volume_addendum.html` 已生成：10/10 输入验证
通过，9 只三项全有效；`600929` 的第三项因 `PULLBACK_WINDOW_LT_4` 缺失。实际只读取十只
股票的 HiThink 历史 K 线，未调用 universe/snapshot/Formal B/shadow/production；本地 full pytest
为 `663 passed, 2 skipped, 11 warnings`。原 canonical artifact SHA 与报告中记录的身份绑定保持不变。

## Current task — PER_SYMBOL_FAIL_SOFT_PRODUCTION_V1 — 2026-09-20

本轮为 `correctness blocker + product blocker`（STRICT PATH）：正式生产对能够明确归属到单只股票
的数据异常执行无限定数量的单股票隔离；全局行情源、鉴权、批量接口或必需输入无法验证时快速失败
并进入诊断路径。`COMPLETE` 表示完整有效输入，`DEGRADED` 表示部分 exclusion 后仍有有效股票，
`NO_VALID_INPUT` 表示没有任何 Formal B 可评估输入；后者不是正常空名单，不创建正式 watchlist、
checkpoint 或 delivery receipt，但必须尽力生成带目标日/实际获取时间/运行类型/四类计数/原因统计的
日报、完整机器 exclusion record 与 Email/Bark 通知。

实时 reconciliation 已确认 live `origin/master=40091083a67fed9a5dfb279868820951f38e8f39`，
PR #73/#74/#75 已合并；`origin/runtime-state=7db58bee3aadde658a01bc9c0bbf371ff444d1dc`。
旧的“一只 stale 才可隔离” persisted 文案与 live 语义冲突，已在本任务范围内以新 policy version
`PER_SYMBOL_FAIL_SOFT_PRODUCTION_V1` 替代；旧 `PER_SYMBOL_PROVIDER_FAILURE_ISOLATION_V1`
artifact 仍可读，不被改写。Formal B、universe、tracker 缺失行情不伪造 outcome、shadow 前瞻身份、
周五授权补跑与正常工作日自动生产保持原语义。

实现位于独立 branch/worktree `codex/per-symbol-fail-soft-production-v1` /
`D:\dev\ashare-watchlist-per-symbol-fail-soft-production-v1`，commit
`d290c2ee3506fd5eba0b95fb6b0665afcfbdb857`，独立 PR #76：
https://github.com/EFSing/ashare_watchlist/pull/76；未触发生产或 remote runtime-state。当前
focused=`235 passed, 2 warnings`；此前实现 full pytest 为 `658 passed, 2 skipped, 10 warnings`，
compileall 与 diff check 通过。对最终 head `8e119dd...` 的 daily workflow run
`35497053430` 已确认是 `event=push`、`jobs=0` 的失败 check-suite；actionlint 1.7.12 定位
NO_VALID_INPUT 持久化 step 的 YAML 解析错误，当前已在 PR 分支做最小 `$'\n'` 拼接修复。修复后
全部 workflow actionlint=`0 errors`，修复已提交并 push 到 PR #76 分支。下一步是重新核验
最终 head 的 exact-head CI/mergeability，停在用户合并决策节点。

## Current task — FRIDAY_WEEKEND_BACKFILL_PREFLIGHT_STATE_FIX_V1 — 2026-09-20

本轮是 `correctness blocker`（STRICT PATH）：PR #74 合并后的真实 run `35492829019` 在
`AUTHORIZED_WEEKEND_BACKFILL_READY` preflight 状态处被 workflow 误拒，未进入真实行情调用。实时
`origin/master=bb061be8e5e81e6584878e578c097972a1ecc428` 已包含 PR #74；live
`origin/runtime-state=7db58bee3aadde658a01bc9c0bbf371ff444d1dc` 只有 9/18 operational failure
notice，没有 9/18 canonical success artifact。该旧的“PR #74 待合并”文字已完成最小
`PROJECT_GOVERNANCE_STATE_CONFLICT` reconciliation。

修复 branch/worktree 为 `codex/friday-weekend-backfill-preflight-state-fix-20260920` /
`D:\dev\ashare-watchlist-friday-weekend-backfill-preflight-fix`，PR #75：
https://github.com/EFSing/ashare_watchlist/pull/75。workflow 仍只在精确手动 production、
`as_of_date=2026-09-18`、manual source、显式授权时接受 `AUTHORIZED_WEEKEND_BACKFILL_READY`；
普通 production 仍只接受 `POST_CLOSE_DIAGNOSTIC_READY`，凭证和 runtime package gate 不变。

local relevant=`47 passed`；full pytest=`645 passed, 2 skipped, 10 warnings`；compileall 与
`git diff --check` 通过。production dispatch、provider calls、runtime-state remote mutation
均为 `0`；Final OOS=`SEALED / UNREAD`，受禁目录未读未触碰。下一步只核对 PR #75 最终 head 的
exact-head CI 与 mergeability，终点为
`FRIDAY_WEEKEND_BACKFILL_PREFLIGHT_STATE_FIX_PR_READY_FOR_USER_MERGE_DECISION`，不自动合并或
触发 production。

## Current task — FRIDAY_WEEKEND_BACKFILL_20260918_V1 — 2026-09-20

本轮为 `correctness blocker`（STRICT PATH）：只为 2026-09-18 这一个目标交易日接通显式授权的
周末补跑，不引入通用历史回填能力，不改变 Formal B、冻结策略、排名/过滤/阈值、Final OOS 或
其他研究项目。实时 intake 已核对 `origin/master=b60fac712ab96218b210f017fcea5ec871cd47c6`、
PR #73 已合并且 master correctness run=`35484210930` 为 `success`；
`origin/runtime-state=be8236629684b34dab5672df774918273536a5d9` 中没有 2026-09-18 的正式产物。

实现位于独立 branch/worktree `codex/friday-weekend-backfill-20260918-v1` /
`D:\dev\ashare-watchlist-friday-weekend-backfill-20260918-v1`，PR #74：
https://github.com/EFSing/ashare_watchlist/pull/74。workflow input 默认关闭且只允许 manual
production/manual source/`as_of_date=2026-09-18`；preflight 和正式 acquisition 都传递同一授权。
HiThink 补跑时对无日期 snapshot 执行同源目标日 OHLCV/前收一致性校验；shadow 保守跳过捕获和日更，
tracker 记录 `AUTHORIZED_WEEKEND_BACKFILL_OBSERVATION_V1`，避免伪装成 `PROSPECTIVE_CAPTURED`。

本轮 production dispatch、provider calls、runtime-state remote mutation 均为 `0`；focused=`188
passed`，full pytest=`644 passed, 2 skipped, 10 warnings`，compileall/diff check 已通过。代码/测试
head=`480e2e97c18916b2bdffb128212324c73284c379` 的 push correctness run=`35485629651` 与
pull_request correctness run=`35485631844` 均为 `success`；文档 checkpoint 后的 remote head 与 PR #74
状态须实时读取，用户合并前不执行真实 production。
用户合并前不执行真实 production；终点为
`FRIDAY_WEEKEND_BACKFILL_PR_READY_FOR_USER_MERGE_DECISION`。

## Current task — SINGLE_AUTHORITATIVE_MARKET_DATA_SOURCE_V1

本轮将生产行情决策收敛为 HiThink Financial-API 单一权威来源：universe、snapshot、个股
historical K 线与指数 historical K 线均只能使用 HiThink。Tencent quote、Tencent Kline fallback
与 AkShare exchange-roster production calls 必须为 `0`；Sina `新浪行业` 仅保留为可选、失败软化的
sector enrichment，不能成为行情或 universe 的替代来源。生产 provenance 须持久记录该 policy
identity、provider/API、fallbacks=`[]` 与调用计数。

target-day trade state 只有 `TRADED`、`NO_TRADE`、`UNKNOWN` 三态。null/partial snapshot 或缺少
T 日历史 bar 不得自动解释为 NO_TRADE；HiThink historical stale 只允许一次同源重试，仍无法证明
目标日状态时 fail-closed，并返回 symbol、target_date、latest_historical_date、provider、retry_count
等诊断。旧的单票 stale isolation 不再执行，不能扩大为 degraded coverage。

HiThink snapshot 的 `turnover` 只按成交额语义保存为 `turnover_amount`，不是换手率；当前 Formal B
不要求 turnover/vol_ratio，缺失保持缺失，禁止补 0 或伪造换手率。Formal B 规则、selection/rank/
threshold、T+1 与冻结 spec SHA 保持不变。Final OOS=`SEALED / UNREAD`，
`data/validation/continuous_speed_probe/` 保持未读未触碰。

代码在独立分支 `codex/single-authoritative-market-data-source-v1` 上实施；合并与生产动作须在
实时核对最终 PR head、exact-head CI、master correctness CI 与 canonical runtime-state 后执行。用户已
明确授权：安全条件全部满足时直接 squash merge；merge 后核验 2026-09-17 canonical completion，若未完成
则直接以 `mode=production`、`as_of_date=2026-09-17`、`trigger_source=manual` 调度，不再次请求确认。

## Current task — HITHINK_LIST_DATE_UNIVERSE_ELIGIBILITY_FIX_V1 — 2026-09-17

本轮为 `correctness blocker`（STRICT PATH）。live intake 仅使用本仓库 remote：
`origin/master=9528484887abe724bad555f9475f2cf2fb98b144`（已包含合并后的 PR #70）、
`origin/runtime-state=be8236629684b34dab5672df774918273536a5d9`。PR #71 为 docs-only open PR，
不作为 base；其他既有 open PR untouched。

2026-09-17 production failure 中，`001246.SZ`（力勤资源，`list_date=null`）在 universe 阶段到达
Tencent quote。本任务在 HiThink universe construction 阶段强制既有 SH/SZ A-share + Main Board
policy 后的 `list_date <= target_date` eligibility：null/empty 与 future date exclude，malformed
non-null date fail-closed。HiThink ticker list 仍为 universe authority；不新增 delisting/ST/
suspension/seasoning policy，AkShare roster production calls=`0`。

独立 branch/worktree 为 `codex/hithink-list-date-universe-eligibility-v1` /
`ashare_watchlist-hithink-list-date-universe-eligibility-v1`，基于 live `origin/master`。新增
`HITHINK_LIST_DATE_ELIGIBILITY_V1` 的 policy、target、source、counts 与 fingerprint，并纳入
generation identity；Tencent quote/Kline fallback、stale isolation、Formal B、provider contract
未改变。

验证：focused/relevant=`180 passed`；full pytest=`630 passed, 2 skipped, 11 warnings`，compileall
与 `git diff --check` 通过。development provider live calls=`0`，production dispatch=`0`，
runtime-state remote mutation=`0`；Final OOS=`SEALED / UNREAD`，受禁目录未读取或触碰。PR #72
(`https://github.com/EFSing/ashare_watchlist/pull/72`) 已创建为非 Draft；文档提交后以最终 head
重新核验 exact-head CI 与 mergeability，不自动 merge、不执行 production rerun。

## Historical completed task — REMOVE_AKSHARE_FROM_PRODUCTION_CRITICAL_PATH_V1 — 2026-09-17

本节记录已完成的历史任务：当时为 `correctness blocker + product blocker`（STRICT PATH）。实时 intake
已确认
`origin/master=73912d6781b4524299a5bda28f03d16f8818ed79`、
`origin/runtime-state=be8236629684b34dab5672df774918273536a5d9`；顶层旧 #69 snapshot 与 live
状态构成 `PROJECT_GOVERNANCE_STATE_CONFLICT`，已完成最小 reconciliation。PR #60/#66/#67/#68
保持 untouched。

独立 branch/worktree 为 `codex/remove-akshare-production-critical-path-v1` /
`D:\dev\ashare-watchlist-remove-akshare-v1`，implementation commit
`01c14f9358e3dc988cb3d5db24031d0c1a4579dd`。HiThink Financial-API
`/api/meta/tickers/list` 现为 SH/SZ a-share live universe 直接来源，既有
`ASHARE_MAIN_BOARD_ONLY_V1` policy 不变；AkShare exchange roster 不再是 production prerequisite，
production calls=`0`。Sina `新浪行业` 为 `OPTIONAL_FAIL_SOFT`；失败或 partial read 时全量使用
Formal B 已有 missing-sector default `sector_name="-"`、`sector_rank=50`、`sector_chg=0.0`，不使用
THS/申万替代。HiThink universe validation 与 Tencent/HiThink market-data fallback 保持
fail-closed/原语义。

验证：full pytest=`620 passed, 2 skipped, 10 warnings`，compileall 与 `git diff --check`
通过；Formal B spec SHA=`f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd`
且未修改。已创建 target=`master` 的 Draft PR #70，随后已合并；其余历史边界保持记录。production
dispatch/runtime-state remote mutation/Cloudflare mutation 均为 `0`，Final OOS 仍为
`SEALED / UNREAD`，受禁目录未读取或触碰。

## Current task — B_VOLUME_PROSPECTIVE_REPORT_OBSERVATION_V1 — 2026-09-17

本轮基于 live `origin/master=ba081f8aba834d636c5a0222d9a6067731a8f819` 创建独立
branch/worktree `codex/b-volume-prospective-report-observation-v1`，并先提交 protocol freeze
`cebda9ec8d8c085424e4b674a3353204e90bd7a0`，再提交实现
`533838b14a7a38cba2ca8baf60e3dce02a4cd06c`。研究输入来自 #68 head
`916916426f3af6d5e8a451c4baea0fa69a119378`；窗口严格为 `R=i+1:T-1`，signal day excluded，
level 与 `_first_breakout_trace` 复用。

已冻结并接入未来日报的三项观察为上涨/下跌日均量比、下跌日成交量占比、回踩后半/前半均量比；
缺失不转零，观察 fail-soft 且不参与筛选/排名。日报新增 `回踩量能`、`量能衰减` 卡片并删除
可见的“市场”和“再启动量能 → breakout”字段；底层 legacy shadow 字段保留。machine persistence
复用现有 `shadow_monitor/b_shadow_monitor.json` 的 `pre_outcome.volume_observation`，无需 schema
redesign。Formal B、strategy/filter/rank/threshold、provider、历史报告、production dispatch 与
runtime-state remote mutation 均未改变；`origin/runtime-state=55fdd5167911ed074df9212cbca01fdda1c58a6b`，
Final OOS=`SEALED / UNREAD`。

验证：focused=`7 passed`，relevant=`94 passed, 2 warnings`，full=`613 passed, 2 skipped,
10 warnings`，compileall 与 `git diff --check` 通过。独立 PR #69
(https://github.com/EFSing/ashare_watchlist/pull/69) 已创建并保持 `DRAFT`；PR head、exact-head CI
与 base mergeability 均属于 live GitHub 状态。Live PR head / exact-head CI must be re-verified at
merge decision; transient PR head is not a governance invariant。当前终点为
`B_VOLUME_PROSPECTIVE_REPORT_GOVERNANCE_RECONCILED`，等待用户 merge decision；classification=`STRICT
governance reconciliation`，不自动 merge。

## Current task — PER_SYMBOL_PROVIDER_FAILURE_ISOLATION_V1 — 2026-09-16

本轮 intake 已完成最小 live reconciliation：persisted current snapshot 仍写
`origin/master=040e077bbf208921798d2d5b1fa0bd2d51ba9a20`，实时 fetch 为
`5a024185206ca868ddf10c2e871a4a34edb1b878`；`origin/runtime-state` 实时为
`520d6fab222bf553caa3eeb29cc83176318626d0`。该与当前任务直接相关的旧 snapshot 已标记并完成
`PROJECT_GOVERNANCE_STATE_CONFLICT` reconciliation。PR #63 已合并；PR #60 仍
`OPEN / DIRTY`，不在范围内。

用户已批准 `PER_SYMBOL_PROVIDER_FAILURE_ISOLATION_V1`：只隔离 canonical production universe
中恰好一只同时满足 traded target-day quote、正常 XSHG session、非空/结构有效/无 future historical
data、latest historical `< target_date` 且错误本质为 `TARGET_DAY_HISTORICAL_STALE` 的股票；第二只
同类 stale、no-trade 不能证明交易、future/malformed/duplicate/OHLC/volume/identity/universe/index/
environment/provider-auth/broad-outage/unknown/strategy/runtime-state 错误仍 fail-closed。

实现将过滤后的 evaluator input、machine-readable exclusion record、`coverage_status`、policy version
绑定到 live package/generation identity、canonical watchlist/run manifest、HTML report、checkpoint 与
runtime-state validation；日报显式显示 `INPUT COVERAGE = COMPLETE/DEGRADED`，degraded 文案为
“本次候选名单未包含该数据异常股票。” Formal B 语义与 spec SHA 保持不变。

当前独立 branch/worktree：`codex/per-symbol-provider-failure-isolation-v1`，实现已完成；PR #64
保持 `OPEN / CLEAN / mergeable`。implementation commit
`b9fffa22ab11df4e68e078b522780703253842d9` 仅是 implementation/historical provenance，不是 PR #64
current head。exact-head push CI 与 PR CI 必须在 merge decision 时从 live GitHub 验证；transient PR
head 与 CI run ID 不构成长期 governance invariant。project full pytest=`606 passed, 2 skipped,
11 warnings`，compileall、git diff --check、Node dispatcher=`3 passed`。provider calls=`0`，production
dispatch=`0`，runtime-state mutation=`NO`；Final OOS=`SEALED / UNREAD`，受禁目录未读取或触碰。
当前终点为 `PER_SYMBOL_PROVIDER_FAILURE_ISOLATION_V1_PR_READY_FOR_USER_MERGE_DECISION`，等待用户
merge decision；PR #60 untouched。

## Current task — history-aware runtime-state checkpoint validation — 2026-09-15

本轮已完成 live reconciliation：旧的 schedule-resilience current snapshot 仍写
`origin/master=16f8e8a17a662d5288ff0c36bcebbedad342a320`、`runtime-state=1c8b2ec`、PR #61
未合并，和实时状态冲突，明确标记为 `PROJECT_GOVERNANCE_STATE_CONFLICT`。fetch 后的 live
事实是：`origin/master=040e077bbf208921798d2d5b1fa0bd2d51ba9a20`，current master
correctness run=`34938666579` 为 `success`；`origin/runtime-state=520d6fab222bf553caa3eeb29cc83176318626d0`；
PR #61/#62 已合并，PR #60 仍 `OPEN / CONFLICTING` 且不在本任务范围内。

run `34969498897` 已由 Actions log 重新核实为 `workflow_dispatch`、target date
`2026-09-15`、trigger source `manual`；canonical chain 先输出 success，随后在
`canonical-output-validation` 失败，精确错误是 `RUNTIME_STATE_ERROR` /
`checkpoint SHA/length mismatch: perf_tracker`。copy/commit gate 被跳过；失败通知 Email/Bark
均 success，`daily_failure_notice_20260915.json` 已在 remote runtime-state 持久化。该通知是
operational-only，不代表 canonical completion，也不阻止未来成功 receipt。

修复 branch/worktree 为 `codex/runtime-state-checkpoint-validation-fix-20260915`，基于 live
`origin/master`。manifest payload 分类固定为：dated immutable=`watchlist`,`dated_html`；
mutable latest-state=`perf_tracker`,`latest_html`。`validate_runtime_data()` 与 bootstrap 对
历史 checkpoint 保留 schema/date/filename/record/path/immutable identity 验证，只跳过 mutable
历史 SHA/长度等同性；`completed_run_status(target_date)` 仍对目标日全部 payload 严格 fail-closed，
并继续验证 current tracker/prospective identity。未修改 B、策略/Universe/provider/shadow、
scheduler、Cloudflare、PR #60、历史 artifact、Final OOS 或受禁目录。

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
