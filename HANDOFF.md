# HANDOFF — 跨设备最小恢复入口

## 2026-09-23 — C_DAILY_RESEARCH_WATCHLIST_SHARED_B_INPUT_V1 review checkpoint

- Classification: product blocker with correctness boundaries, unchanged; STRICT PATH. Work branch
  `codex/c-daily-research-watchlist-shared-b-input-v1` is stacked on Draft #83 (which is stacked
  on Draft #81). Fetch live remote HEAD/CI before continuing. Draft #84 remains separate and disabled.
- Added same-runner read-only C input mode, independent two-rule daily research list and mobile HTML;
  synthetic preview is `docs/examples/c_daily_research_watchlist_synthetic.html`. C keeps price-rule
  match and volume research values separate from formal volume confirmation/entry candidate.
- Reused the narrow #84 per-request HiThink start/receive sidecar timestamps, without importing its
  private Release export or modifying its PR. No provider call, production run, merge, or Final OOS read.
- **Activation remains closed:** workflow-level production concurrency covers the entire B job; a C
  tail step would hold B's lock. A separate job loses runner-local package/raw bytes, while the repo
  is public and has no verified private transfer for that large input. Do not add a public raw artifact
  or claim daily automatic reports until isolation, privacy, size, and persistence are demonstrated.
- Next: review this bounded Draft PR and its exact-head CI; design a verified isolated C execution
  path that consumes the same package without holding B's lock or publishing raw evidence. Then test
  a real same-day daily report and decide merge/enable. `PROSPECTIVE_CAPTURED` remains unproven.

## 2026-09-23 — C_VOLUME_OBSERVATION_AND_EXISTING_STORAGE_REUSE_V1

- Classification: correctness blocker + product blocker, unchanged. `#81/#83/#84` remain Draft;
  current master `a54bce2c34d1c76298b02f2ddc8347fd88757ace`, runtime-state
  `2fc7f9f69949b20da0444a13a2dba860c952fc3f` are live intake snapshots.
- Recovery branch: `codex/c-prospective-capture-v1` (Draft #83, stacked on #81); fetch
  its live remote HEAD and exact-head CI. #84 is `codex/b-c-readonly-handoff-v1` and remains
  unchanged; no handoff backend was enabled.
- C now preserves B frozen volume research values, with `VOLUME_FEATURE_COMPUTED` and
  `VOLUME_BASIS_UNVERIFIED` separate; formal volume confirmation remains false. The 2026-09-22
  nine B isolated symbols stay gaps. No provider call or Formal B mutation.
- Existing private Drive project root is readable through the Codex connector, owned and unshared;
  the historical 180,203,424-byte daily-K backup is visible. The B cloud runner has no verified
  Drive writer or quota evidence. #84's optional private GitHub Release backend remains disabled
  because no additional private repository is available. Neither backend is a proven live handoff.
- Next user decision: authorize a runner-accessible use of the existing private Drive account
  through a secure deployment configuration, or accept a manual local handoff with computer-on
  and cross-device recovery limits. Do not request a token in chat, activate C, merge, or claim
  `PROSPECTIVE_CAPTURED` before independent SHA readback.

> 恢复链：remote Git → branch → remote HEAD → HANDOFF.md → next action。
> 本文件只保留当前恢复所需的最小事实，不承担历史归档职责；历史 provenance 在 Git 历史中，
> 正式状态与长期决策分别见 `docs/CURRENT_STATUS.md` 与 `docs/DECISION_LOG.md`。
> 若治理文字与实时 Git / PR / CI / runtime-state 冲突，先标记
> `PROJECT_GOVERNANCE_STATE_CONFLICT`，以实时证据完成 reconciliation 后再继续。

## 2026-09-23 — C_SHARED_INPUT_ACTIVATION_RELEASE_GATE_READY_FOR_SOL

- Classification: correctness blocker + product blocker, unchanged. #83 remains Draft and stacked
  on #81; live PR heads and exact-head CI must be rechecked before review. No merge or activation.
- The C reader verifies private handoff identity, actual HiThink response request/receive times,
  raw ticker name at T, per-symbol qfq history, B isolated symbols and C exclusions separately.
  Verified price observations use `PRICE_OBSERVATION_VOLUME_UNVERIFIED`; they are not formal
  candidates or `PROSPECTIVE_CAPTURED`. Volume forward-adjustment semantics remain `UNRESOLVED`;
  volume confirmation is disabled. The 2026-09-22 nine isolated symbols remain a market gap.
- Next: Sol reviews #83/#84. A real same-day private handoff and C consumption acceptance still
  requires a user-provided private repository and scoped permission; no cloud secret was configured.

## 2026-09-23 — C_QFQ_SHARED_INPUT_HANDOFF_READY_FOR_SOL_FINAL_ACTIVATION_AUDIT

- Classification: correctness blocker + product blocker, unchanged. User chose A for prospective
  C input: `C_QFQ_INPUT_V1` uses only B's same-day frozen qfq stock prices. Original unadjusted
  design stays historical; no Formal B strategy, historical returns, Final OOS, schedule or order change.
- #83 branch `codex/c-prospective-capture-v1` remains stacked on #81. C now requires T, package
  SHA, handoff manifest SHA and a `HANDOFF_VERIFIED` private readback receipt before consumption;
  missing T-known ST prevents C rule observation. B evaluated, B isolated and C exclusions remain
  separate. Volume is documented in shares but forward-adjustment behavior is `UNRESOLVED`;
  volume confirmation remains invalid.
- #84 independent branch `codex/b-c-readonly-handoff-v1` adds private upload, separate download,
  SHA/byte readback and an independent receipt. Real private configuration and same-day acceptance
  remain outstanding. On resumption fetch both live PR heads and exact-head CI; no automatic merge
  or activation. The 9 isolated symbols in 2026-09-22 B coverage are still unavailable to C.

## 2026-09-23 — C_B_TO_C_HANDOFF_AND_PRICE_BASIS_READY_FOR_SOL_DECISION

- Classification: `correctness blocker`，未改变。Branch `codex/c-prospective-capture-v1`
  continues Draft PR #83 stacked on Draft #81; fetch live remote HEAD and exact-head CI.
  At intake master=`a54bce2c34d1c76298b02f2ddc8347fd88757ace`, runtime-state=
  `2fc7f9f69949b20da0444a13a2dba860c952fc3f`; these are snapshots only.
- C reader now consumes B's actual serialized package, verifies generation and per-symbol SHA,
  preserves excluded-symbol coverage, and checks raw/sidecar bytes. Private handoff download is
  wired only in the disabled manual workflow. Independent B exporter Draft PR is on
  `codex/b-c-readonly-handoff-v1` from current master; no merge or production activation.
- Current B stock request is qfq (`adjust=forward`), with no frozen unadjusted OHLC/factors and
  unproved volume unit. User must choose A: new qfq protocol identity, or B: original raw C
  definition remains input-incomplete. No future returns or Final OOS read.
- Next: Sol decides price basis and reviews both Draft PRs. Before any real C capture, verify a
  same-day private handoff readback, ST/time/volume evidence and excluded coverage. Do not enable
  C schedule, notification or orders; do not merge #81/#83 or the B exporter automatically.

## 2026-09-23 — C_SHARED_INPUT_REUSE_READY_FOR_SOL_AUDIT

- Classification: `correctness blocker`，未改变。用户纠正 C 应优先复用 B 已冻结的收盘
  原始输入；先前独立 provider 配额门槛只约束 C 新发 HiThink 请求。这一语义冲突已在
  protocol/status/decision 记录中调和；没有改变 #81/#83 stacked 关系。
- Live intake: `origin/master=a54bce2c34d1c76298b02f2ddc8347fd88757ace`，
  `origin/runtime-state=2fc7f9f69949b20da0444a13a2dba860c952fc3f`，#81 Draft/CLEAN
  head `78b723c96a351038fea379284ba52be3bd645b1a`；#83 Draft/CLEAN，base 指向 #81。
  本轮最终 #83 head/CI 请从 GitHub 实时读取。
- B 成功时完整 package 与 raw evidence 仅在 runner 临时目录；`runtime-state` 只保存
  allowlisted 正式产物/诊断，没有完整输入。C 只读 adapter 在本 PR 内验证 SHA、T 日、
  逐票覆盖及 K 线，独立执行 C 规则并写 C 私有观察/失败记录。qfq 与 C raw 口径、T 日
  ST 原始来源、逐请求时间及 B 持久化时间仍缺；只能 `CAPTURE_PARTIAL_UNVERIFIED` 或
  `CAPTURE_FAILED`，无真实 `PROSPECTIVE_CAPTURED`。
- 下一步：Sol 审计 `docs/research/c_prospective_capture_v1.md` 的最小 B 只读交接设计，
  明确复权/量口径与 ST/时间证据是否可补齐；之后才可另行决定 B 生产导出改动与启用。
  不合并 #81/#83，不开启真实调度/通知或 provider 请求。
- Verification: C focused `50 passed`; B isolation `206 passed`; full suite `724 passed,
  2 skipped, 10 warnings`; compileall/diff check PASS。最终 pushed branch head 和 exact-head
  CI 以实时 GitHub 查询为准；无仅保留在本机的有价值代码状态。

## Historical checkpoint — 2026-09-22 — NO_VALID_INPUT root-cause investigation — `UNRESOLVED`

- Classification: `correctness blocker + product blocker`，未改变。2026-09-22 正式 B 因 HiThink
  universe 资格结果为空而 fail-closed，未生成 watchlist、checkpoint 或 delivery receipt。
- Incident root cause: `NOT_REPRODUCIBLE_WITH_CURRENT_DATA / INSUFFICIENT_DATA`。首次生产 run
  `35710352302` 使用 `master@4633b37ee6eb99bee527d8907e4e51768fd3f82a`，持久化结果只有
  `raw=5576`、`qualified=0`；当次原始 HiThink payload 位于 runner 临时 evidence 目录，未上传
  artifact、未写入 runtime-state，现存证据没有 exchange、board 或 `list_date` 的逐层分布，
  因而不能把故障归因于程序或行情源。
- Verified divergence: 使用首次生产 exact source SHA、同一 `HiThinkClient.universe()`、同一
  `/api/meta/tickers/list?exchange=SH%2CSZ&asset_type=a-share&limit=10000&offset=0` 请求以及同一
  `_build_universe(..., as_of_date="2026-09-22", include_exclusions=True)` 路径，对当前可信输入得到
  `5576 raw -> 5226 SH/SZ -> 3197 Main Board -> 3196 eligible`；manifest 实际含 `3196` 个 symbol。
  输入为 `5576` 个 dict；ticker/thscode/exchange/asset_type 均为 string，`list_date` 为 `5568`
  个 string 与 `8` 个 null；唯一主板缺失上市日为 `001246.SZ`，future list_date 为 `0`。
- Code decision: 未发现会把当前可信输入从 3196 变为 0 的生产筛选错误，不修改资格、主板范围、
  Formal B 或生产调用。PR #82 https://github.com/EFSing/ashare_watchlist/pull/82 仍只补充下一次
  NO_VALID_INPUT 的逐层资格诊断；它不是本次故障修复，也不能证明首次故障根因。
- Recovery readiness at `2026-09-22T18:10:48+08:00`: local production preflight 为
  `POST_CLOSE_DIAGNOSTIC_READY`，credential/runtime packages READY，XSHG session 与收盘 gate 通过；
  live `origin/runtime-state=65429e0c45c8dce572d7e9fd6eb9bff00ee7f734` 仍只有 diagnostic report、
  failure notice 和 NO_VALID_INPUT HTML，没有 2026-09-22 canonical watchlist/checkpoint/delivery。
- Next: 在用户明确授权前不 merge、不 dispatch。若仍在 2026-09-22 BJT 且最终 recheck 保持上述
  条件，精确恢复操作为手动 dispatch `daily_t_close.yml`：`mode=production`,
  `as_of_date=2026-09-22`, `trigger_source=manual`, `allow_weekend_backfill=false`。#82 可先单独作为
  诊断增强合并，但不得表述为修复根因；本调查未写 runtime-state、未触发生产，Formal B、Final OOS
  与历史证据均未改写。

## 2026-09-23 — C_PROSPECTIVE_ACTIVATION_GATE_READY_FOR_SOL_REAUDIT

- Classification: correctness blocker + product blocker for actual C activation. The prior
  checkpoint said to wait for Sol's audit; the user has now supplied Sol's finding that the
  real-enable audit failed. That finding supersedes the earlier “wait for activation audit” status.
- `PROJECT_GOVERNANCE_STATE_CONFLICT` (resolved): live master had advanced from #81's original
  base `4633b37ee6eb99bee527d8907e4e51768fd3f82a` to
  `a54bce2c34d1c76298b02f2ddc8347fd88757ace` via PR #82; #81 remained at `02c7116` and GitHub
  reported it `dirty`. A read-only merge-tree confirmed the only conflict was `HANDOFF.md`.
  Rebased #81 onto current master, retaining the #82 B incident record and C checkpoint history;
  new #81 head is `78b723c96a351038fea379284ba52be3bd645b1a`. Rebased #83's two original commits
  plus the C activation repair onto that #81 head. The C implementation and local verification
  checkpoint is `26d8fe9c35e22ecdcf0fb182ab1c33dfc0bcdd56`. The reconciled branch was pushed at
  `dbedf9a3ff35a9a964f3491c97aa19b7067ea805`; both exact-head checks passed there. This final
  handoff-only update is on top; read its final branch SHA and exact-head checks from live PR state.
- Live intake: `origin/master=a54bce2c34d1c76298b02f2ddc8347fd88757ace`,
  `origin/runtime-state=2fc7f9f69949b20da0444a13a2dba860c952fc3f`. PR #81 remains Draft/CLEAN on
  current master at `78b723c96a351038fea379284ba52be3bd645b1a`; exact-head push run
  `35817419573` and pull-request run `35817423031` both succeeded. PR #83 remains Draft and is
  stacked on the #81 branch. Its pushed code checkpoint `dbedf9a3ff35a9a964f3491c97aa19b7067ea805`
  resolved to #81 head `78b723c96a351038fea379284ba52be3bd645b1a`; both checks succeeded (runs
  `35818216059`, `35818212182`). Read live state for this final handoff-only update. Continue on
  `codex/c-prospective-capture-v1`; do not merge either PR.
- C repairs: provider-backed T-day ST evidence now requires the verified ticker-list row, T-date
  upstream timestamp, and actual receive time; raw provider body hash and envelope request ID are
  checked. Public capture uses the actual runtime clock and fixed C-only root. Partial attempts can
  resume the same day; immutable response, snapshot, observation, manifest, and index artifacts
  preserve prior input identities and failure reasons. `PROSPECTIVE_CAPTURED` requires complete
  verified inputs and a finalized, reverified immutable index.
- Independent chain: `scripts/c_provider_adapter.py` and
  `scripts/run_c_prospective_capture.py` use only C credentials, the documented HiThink ticker
  list and per-symbol daily-history endpoints, serial request pacing, immutable response caching,
  and same-day resume. HiThink publishes a unified API key and dynamic rate limits, but no provider-
  issued allocation proving a quota independent of B was available at this checkpoint. The adapter
  therefore hard-blocks all live requests until such evidence is separately verified; no live
  provider request has been made.
- Recovery/schedule: `.github/workflows/c_prospective_capture.yml` prepares a weekday C-only job
  gated by an explicit repository variable. As #83 remains Draft, this workflow is not on the
  default branch and is not active. It stores only `data/research/c_prospective_capture_v1/` in a
  separate private state repository and refuses runtime/report/production destinations. No C
  credentials, private state repository, or cloud secrets were configured in this worktree. No
  real schedule, notification, or order is enabled.
- Verification at the rebased stack: C-focused `41 passed`; B isolation `40 passed`; full suite
  `715 passed, 2 skipped, 10 warnings`; `compileall` and `git diff --check` pass. These runs cover
  source checkpoint `26d8fe9c35e22ecdcf0fb182ab1c33dfc0bcdd56`. The code checkpoint's exact-head
  CI passed in runs `35818216059` and `35818212182`; read live PR checks for this handoff-only
  update, then stop at
  `C_PROSPECTIVE_ACTIVATION_GATE_READY_FOR_SOL_REAUDIT`. Actual activation still requires provider-
  issued independent quota evidence, C-only credentials/private repository configuration, and Sol's
  re-audit. No formal C historical return research, Final OOS read, or Formal B change is authorized.
## 2026-09-22 — C_PROSPECTIVE_CAPTURE_PR_READY_FOR_SOL_ACTIVATION_AUDIT

- Classification: `correctness/provenance gate + product gate`; the task changes the
  look-ahead-sensitive C observation boundary, but does not select parameters, run formal
  historical returns, change Formal B, merge, or enable production scheduling.
- Live intake identity: PR #81 was re-read before branching as `OPEN / DRAFT / CLEAN`, with
  base `master`, head branch `codex/c-pre-outcome-design-ready-for-sol-audit`, and head
  `02c7116f5b712b187a2d70e1a46fba061981b6b8`. This work is isolated in branch
  `codex/c-prospective-capture-v1`, worktree
  `D:\dev\ashare-watchlist-c-prospective-capture-v1`, based directly on that live head.
- Delivery identity at implementation push: Draft PR [#83](https://github.com/EFSing/ashare_watchlist/pull/83)
  is `OPEN / DRAFT / MERGEABLE / CLEAN`, base
  `codex/c-pre-outcome-design-ready-for-sol-audit@02c7116f5b712b187a2d70e1a46fba061981b6b8`,
  implementation head `codex/c-prospective-capture-v1@a6621ec9dbc98173d785000ae7df4b48bce7c33d`.
  This checkpoint adds only persisted governance metadata; re-read the live branch tip and
  exact-head CI before resuming.
- Implementation checkpoint: `scripts/c_prospective_capture.py` provides a C-only normalized
  provider-snapshot entry point and immutable input/observation/manifest/log/failure paths under
  `data/research/c_prospective_capture_v1/`. It accepts only same-day after-close evidence,
  preserves input SHA and request/receive provenance, records both C rules separately, and
  fail-closes missing or conflicting evidence. It does not import or call B evaluators, Shadow,
  return tracking, formal lists, daily reports, schedulers, or `runtime-state`.
- Protocol checkpoint: the C protocol now separates `FULL_COMPARABLE_UNIVERSE` from each
  rule's `MATCHED_EVENT_SAMPLE`, separates observation-day floating P/L from T+1 reference
  execution P/L, limits `RV_T >= 2.0` to confirmation-day volume, retains the three exit
  observations, and requires a pre-existing unified cost model before formal return research.
- Verification: the new synthetic capture tests pass (`8`); together with the existing C design
  tests the C-focused set is `27 passed`; the isolation/regression set is `76 passed`; full suite
  is `698 passed, 2 skipped`; `compileall`, `git diff --check`, and the CI-equivalent Node
  dispatcher test (`3 passed`) pass. Exact-head CI for PR #83 has two `test` runs, both
  `success` at the recorded head: push run `35716953816` and pull-request run `35717028240`.
- Decision: `NEEDS_MORE_EVIDENCE`. The implementation is prepared but not activated; Sol must
  audit the capture boundary and an independent provider/credential/quota and persistence setup
  before any real schedule or notification is enabled. No historical backfill may be labeled
  `PROSPECTIVE_CAPTURED`; Final OOS and prohibited validation data remain untouched.
- Next action: stop and wait for Sol's activation audit. Do not merge PR #83, enable a real
  schedule/notification, run formal historical returns, read Final OOS, or alter Formal B.

## 2026-09-22 — C_DATA_EVIDENCE_AND_PROTOCOL_READY_FOR_SOL_DECISION

- Classification: `research question + correctness/provenance gate`; no parameter selection,
  promotion, Formal B change or merge.
- Live recovery identity: branch/worktree=`codex/c-pre-outcome-design-ready-for-sol-audit` /
  `D:\dev\ashare-watchlist-c-pre-outcome-design`; `origin/master`=`4633b37ee6eb99bee527d8907e4e51768fd3f82a`.
  The immediately preceding content checkpoint head was
  `f35a4c0877dc0c3d619516eacb1d820bb09cbfbd`; exact-head push run `35712987048` and
  pull-request run `35712992003` were both `success`. PR #81 remains `OPEN / DRAFT / CLEAN /
  mergeable`; after this governance-only update, re-read the final branch/PR head and exact-head
  CI live before resuming, rather than treating the persisted checkpoint SHA as invariant.
- Authorized read-only daily-K verification: external existing path
  `D:\dev\ashare-watchlist\data\validation\core_signal_validation\raw\daily_k.parquet` has
  size `180203424` bytes and SHA-256
  `61189a4850e2eb157453e28e5375e502e20d214508bbe70ea71066ca3e05e426`, matching the frozen
  declaration. C worktree canonical daily-K remains absent; no download, copy or overwrite was
  performed and the external bytes were not used as C input. Evidence record:
  `data/research/c_pre_outcome_design_v1/daily_k_integrity_check.json`, SHA-256
  `2a0496e3414b4bd43969f66f7cf93c2b7a1e4a698266abdc74243f662799f939`.
- Evidence status: daily-K identity=`VERIFIED`; manifest field/adjustment semantics=`DECLARED_ONLY`;
  calendar mapping=`VERIFIED` for deterministic metadata/helper; historical T-known ST/*ST and
  per-bar known-at/vintage=`UNRESOLVED`; limit/tick/intraday/actual fill=`MISSING`.
- Independent protocol draft:
  `docs/research/c_pre_outcome_preregistration_protocol_v1.md`, SHA-256
  `c74447608490fdd7068ea4a018dc3be31358198d3570ead878e5095cc09befd3`. It keeps
  `BALANCED_A`/`CONSERVATIVE_B`, proposes the former as main and latter as sensitivity without
  outcome selection, fixes `RV>=2.0` as the price-plus-volume hypothesis and keeps robust-z only
  observational, with explicit five-session repeated-failure, T-close/T+1, MFE/MAE and execution
  boundaries. Draft only; Sol/user decision remains required.
- Boundary: only C research docs, C data evidence and necessary governance text changed. No C future
  outcome, Final OOS, forbidden directory, Formal B, shared production code, runtime-state, formal
  artifact or scheduler was read or changed; no formal C backtest ran.
- Decision/terminal: `NEEDS_MORE_EVIDENCE` /
  `C_DATA_EVIDENCE_AND_PROTOCOL_READY_FOR_SOL_DECISION`. Next action is Sol/user audit; do not
  merge, select parameters or start outcome research.

## Historical snapshot — 2026-09-22 — C_PRE_OUTCOME_EXIT_VOLUME_FIX_V1 ready for Sol audit

- Classification: `research question + correctness/provenance gate`; no product promotion and no
  Formal B change. This repair is limited to the early-defense price/volume observation semantics
  requested after Sol's second audit.
- Scope: `classify_exit_observation()` now exposes the explicit
  `PRICE_ONLY_EARLY_DEFENSE` price baseline and `PRICE_VOLUME_EARLY_DEFENSE` same-position,
  same-price-event version. `upper_shadow_fraction > 0` is descriptive only; it is not a weakness
  gate or volume confirmation. Repeated rejection without the selected exit condition returns
  `REPEATED_RESISTANCE_REJECTION_RISK`, while first warning, early candidate, and support break
  remain independent.
- Boundary: C-only script/tests/docs changed. Formal B, shared production code, runtime-state,
  canonical watchlist, daily report, provider acquisition, C future returns, Final OOS and
  `data/validation/continuous_speed_probe/` were not read or changed.
- Data recovery intake was read-only: the C worktree lacks daily-K; an existing copy is present
  only in another worktree at the canonical path with declared SHA
  `61189a4850e2eb157453e28e5375e502e20d214508bbe70ea71066ca3e05e426`, and governance metadata
  points to the existing private Drive recovery location. No download, copy, overwrite or hash
  replacement was performed. Historical T-known ST and per-bar known-at evidence remain unresolved.
- Verification before delivery: C `19 passed`; B isolation regression `40 passed`; full pytest
  `690 passed, 2 skipped, 10 warnings`; compileall and diff check pass.
- Draft PR: [#81](https://github.com/EFSing/ashare_watchlist/pull/81) remains open as Draft against
  `master`. Implementation commit `52c6f1d7ce71292fd73582d6390b5d24ac68489d` is pushed from
  Sol-audited head `11a47fdb80d7887c97a0cc4c378b8c935bc44121`; exact-head push run
  `35707980389` and pull-request run `35707984877` both completed `success` with that SHA.
  Any later governance-only head still requires live verification.
- Decision: `NEEDS_MORE_EVIDENCE`; terminal marker
  `C_PRE_OUTCOME_EXIT_VOLUME_FIX_READY_FOR_SOL_AUDIT`. Do not merge, read future returns, or
  start C outcome research.

## Historical snapshot — 2026-09-22 — C_PRE_OUTCOME_CORRECTNESS_FIX_V1 ready for Sol re-audit

- Classification: research question + correctness/provenance gate; no product promotion and no
  Formal B change. User selected the new C direction; old C V0 is provenance only, old A stopped,
  old D excluded, RS/VCB conclusions retained.
- Live intake: `origin/master=4633b37ee6eb99bee527d8907e4e51768fd3f82a`; PR #77/#78/#79/#80 are
  merged, and master `test` CI for #80 merge head is `success`. The older #80 open/awaiting-merge
  wording below is retained as a historical snapshot only; no unrelated governance history is
  being cleaned.
- Independent branch/worktree: `codex/c-pre-outcome-design-ready-for-sol-audit` /
  `D:\dev\ashare-watchlist-c-pre-outcome-design`; C-only module, CLI, tests and output namespace.
- Delivered design: `docs/research/c_pre_outcome_design_v1.md` and
  `docs/research/c_data_feasibility_v1.md`; pure functions in `scripts/c_pre_outcome_design.py`;
  metadata-only check at `data/research/c_pre_outcome_design_v1/data_dependency_check.json`.
  No C outcome, formal historical return study, Final OOS or forbidden directory was read.
- Data status: OHLCV/calendar/T-anchor metadata supports design; local `daily_k.parquet` is absent,
  historical per-bar vintage proof is false, and T-known historical ST/*ST status is unresolved.
  Formal C outcome research is not ready.
- Verification: C tests `16 passed`; B isolation regression `41 passed`; full pytest
  `687 passed, 2 skipped, 10 warnings`; compileall and diff check pass. The two skips are the
  pre-existing large exact-date fixture absence.
- Draft PR: [#81](https://github.com/EFSing/ashare_watchlist/pull/81) remains open as Draft against
  `master`; this repair starts from Sol-audited head `edd3039a1d9815eb3bdf4301699cb1fdc90dc815`.
  Implementation head `ad6ec63ebc9f47ed1d5822460063cb13234b2cd2` is pushed and its exact-head
  push correctness run `35706143436` and pull-request correctness run `35706147202` are both
  `success`; this governance checkpoint is the final branch update and must be checked live again.
- Decision: `NEEDS_MORE_EVIDENCE`; terminal marker
  `C_PRE_OUTCOME_CORRECTNESS_FIX_READY_FOR_SOL_REAUDIT`. Next: push the repair, verify exact-head CI
  on the final remote head, then stop for Sol re-audit. Do not merge, run provider acquisition, or
  start C formal returns research.

## 2026-09-22 — B_PROSPECTIVE_MONITOR_RECOVERY_V1 ready for user merge decision

- Classification: `product blocker + correctness/data-integrity risk`; Formal B、正式收益口径、
  `runtime-state`、Final OOS 与历史正式产物均未改变。
- `PROJECT_GOVERNANCE_STATE_CONFLICT` reconciliation：实时 source 为
  `origin/master=30d3cab3b8c54a028ac57055e083c1ceb4610556`，实时
  `origin/runtime-state=aaebe2d362c0cf467d06662f2792c117c889d0d7`。实时 PR #60 为
  `OPEN / DIRTY / not mergeable`，PR #68 为 `OPEN / DRAFT / CLEAN`；PR #77/#78 已关闭并已
  进入当前 master。它们均未被本任务修改。
- Root cause：HiThink 指数 K 线已在 `GenerationInputManifest` 中正常获取、校验并保存；其
  `to_dict()` 在正常 runner 的内存传递中保留 tuple-backed `bars`，而
  `b_shadow_monitor._validated_bars()` 只接受 `list`，因此把可用指数错误记录为
  `SHADOW_FEATURE_UNAVAILABLE: index.bars is unavailable`。独立量能观察消费股票 K 线序列，
  所以不受该类型映射错误影响。
- Minimal fix：`scripts/b_shadow_monitor.py` 让既有 validator 接受 canonical `list/tuple`
  transport；不新增 provider、调度器、状态机或第二套存储。缺失指数仍 fail-closed，不构造市场
  环境、不填 0，且不落盘虚假完整捕获。新增回归覆盖 canonical tuple capture、missing-index
  failure、candidate immutability 与 independent volume path。
- Verification：focused `34 passed`；full pytest `670 passed, 2 skipped, 10 warnings`；
  compileall、`git diff --check` PASS；provider calls、production dispatch、runtime-state
  mutation 均为 `0`。`Final OOS=SEALED / UNREAD`，`data/validation/continuous_speed_probe/`
  未读取或触碰。
- Branch/worktree：`codex/b-prospective-monitor-recovery-v1` /
  `D:\dev\ashare-watchlist-b-prospective-monitor-recovery-v1`，基于实时 `origin/master`。
- Historical snapshot (superseded by the live merge above)：Delivery：PR #80
  https://github.com/EFSing/ashare_watchlist/pull/80 已创建为非 Draft，
  final head=`25987fb4b85881c1ddf2541d7001bb2b5867ca28`；push correctness run=`35694717548`
  与 pull_request correctness run=`35694781177` 均为 `success` 且 head exact，PR live 状态为
  `OPEN / CLEAN / mergeable`。不自动合并、不触发生产或正式通知。
- Terminal：`B_PROSPECTIVE_MONITOR_RECOVERY_PR_READY_FOR_USER_MERGE_DECISION`，等待用户 merge
  decision；合并前需重新核对最新 master 与实际代码冲突。

## 2026-09-22 — MOBILE_VOLUME_OBSERVATION_CARD_LAYOUT_FIX_V1

- Classification: display-layer bugfix; no correctness, strategy, signal, score, watchlist,
  checkpoint, delivery receipt, production artifact, or research-conclusion change.
- Implementation branch: `codex/mobile-volume-card-layout-fix`; PR #78
  https://github.com/EFSing/ashare_watchlist/pull/78; current head and exact-head CI must be
  re-read live before any merge decision. No automatic merge.
- Change: `scripts/render_daily_close_html.py` uses a bounded two-row mobile grid for the
  `回踩量能 · 量能衰减` card while preserving the desktop three-column layout and all metric
  values, calculations, explanations, colors, and observation-only semantics. The focused
  layout regression is in `tests/test_b_volume_prospective_report_observation.py`.
- Verification: focused tests `10 passed`; full pytest `668 passed, 2 skipped, 10 warnings`;
  compileall and `git diff --check` passed; browser preview covered desktop plus 320, 375, 390,
  and 430 CSS px nested mobile viewports. The 2026-09-21 report/latest artifact remains
  unchanged at SHA-256 `d383fbd485b72c810d8e5fbf7149304098678d01988df99ac1228b3c31fdac90`.
- Intake reconciliation: the older 2026-09-21 PR #77 awaiting-merge note was stale relative to
  live GitHub; it is recorded as `PROJECT_GOVERNANCE_STATE_CONFLICT` and superseded by merged
  PR #77 / live `origin/master=fd33b8b…`. No task-dependent strategy, artifact, or research-state
  conflict remained before this UI fix.
- Next: wait for the final PR head's exact-head CI and the user's merge decision; do not merge
  automatically. `Final OOS=SEALED / UNREAD` and the forbidden validation directory remain
  untouched.

## 2026-09-21 — DAILY_REPORT_INPUT_COVERAGE_PRESENTATION_FIX_V1

- classification：`deferred improvement`（日报可用性/展示维护）；不改变输入 coverage 状态与计数、
  Formal B、筛选、Score、排序、交易参数、tracker、shadow 或量能计算。
- implementation：在 PR #77 branch `codex/friday-volume-observation-only-backfill-v1` 的 commit
  `676e69d` 中，`DEGRADED` 正文改为“数据质量：部分覆盖”及动态有效评估/异常股票计数；
  `COMPLETE` 原展示与 `NO_VALID_INPUT` 诊断语义保持不变。完整 exclusion records、错误、日期、
  policy 与 coverage JSON 仍保存在既有机器记录/metadata。
- runtime-state：独立增强日报原 SHA=`9a202c79cb628db0feb080b4a39be20240a4a0110abb65d08cb8995b967c4f24`，
  仅更新 `data/reports/addenda/daily_close_20260918_volume_enriched.html`，新 SHA=
  `be2df29f4324bc6729fbfab051d712da4820b2bd05f49e71a3bf74acbabd2c6e`；commit=`15d8da215e27aee898fb63729832233d9a7210fd`。
  原正式报告=`acfbec2a7399c2eb83a5fe62c83ccbbfaf4852b9d9c8013b62de256789178aaa`、watchlist、checkpoint、
  delivery receipt 均未改写；runtime-state 只更新该独立增强展示产物。
- verification：focused=`5 passed`；full pytest=`668 passed, 2 skipped, 10 warnings`（短路径
  basetemp；长路径初次失败为既有测试的 Windows 临时路径长度错误，短路径复跑通过）；compileall 与
  `git diff --check` 通过。无 provider/production dispatch；Final OOS=`SEALED / UNREAD`，禁读目录未触碰。
- terminal：PR #77 已推送并完成最终 head 的 live exact-head CI 与 mergeability 核验；等待用户决定并合并，
  不自动 merge、不触发正式生产。

## 2026-09-20 — VOLUME_CARD_VISUALIZATION_AND_CLOUD_DELIVERY_V1

- terminal：`VOLUME_CARD_CLOUD_DELIVERED_AND_PRODUCTION_FIX_PR_READY`。本轮完成独立股票 K 线量能计算与正常 T-close 接线、三行紧凑量能卡片、2026-09-18 独立回顾增强日报；量能仍是 report-only，不进入 Formal B、筛选、Score、排序或交易参数。
- implementation：branch/worktree=`codex/friday-volume-observation-only-backfill-v1` / `C:\awv`，量能功能实现 head=`7d269e3e0ff4019e0310ddafe86be6ff3efde714`；PR #77 后续仅追加交付记录，当前保持 OPEN/CLEAN/MERGEABLE。正常路径写入 `data/volume_observations/volume_observations_YYYYMMDD.json`；renderer 优先按 signal_id/代码读取，index/shadow 缺失不会遮蔽有效股票量能。
- retrospective report：只由既有 addendum 计算结果与原正式 HTML 重渲染，不重新取数；原正式报告 SHA=`acfbec2a7399c2eb83a5fe62c83ccbbfaf4852b9d9c8013b62de256789178aaa` 未变。`600929` 第三项仍为 `PULLBACK_WINDOW_LT_4` / `样本不足`；候选排名按原正式报告保留。
- cloud delivery：runtime-state commit=`0a6feb50aa169d9712844d5a3a16deddae596607`，只新增 `data/reports/addenda/daily_close_20260918_volume_enriched.html`，SHA=`9a202c79cb628db0feb080b4a39be20240a4a0110abb65d08cb8995b967c4f24`。URL：https://github.com/EFSing/ashare_watchlist/blob/runtime-state/data/reports/addenda/daily_close_20260918_volume_enriched.html
- verification：focused/local=`89 passed, 1 warning`；compileall、diff check 通过；最终 head 的 push correctness run=`35519184571`、pull_request correctness run=`35519187151` 均 SUCCESS。本机 actionlint 未安装；本地全量 pytest 受既有 `importlib.metadata` 将 `exchange-calendars` 解析为 `None` 的环境问题阻断，但 CI 全量 regression 已通过。未运行生产、未触碰 Final OOS 或 `data/validation/continuous_speed_probe/`。浏览器 `file://` 视觉检查被安全策略拦截，未绕过；静态桌面/窄屏 CSS 检查已完成。
- next：用户决定并合并 PR #77；合并前不启动 `daily-t-close`，不发送邮件/Bark，不再改写原正式报告。

## 2026-09-20 — FRIDAY_VOLUME_OBSERVATION_ONLY_BACKFILL_V1

- classification：`RETROSPECTIVE_VOLUME_ENRICHMENT / REPORT_ONLY`。本轮只为已持久化的
  2026-09-18 Formal B 十只候选生成独立量能补充，不重扫 universe、不重跑 Formal B、不改写
  canonical watchlist/checkpoint/report/delivery/tracker/shadow/runtime-state，也不启动
  `daily-t-close`。
- `PROJECT_GOVERNANCE_STATE_CONFLICT`：旧入口仍停留在 PR #76 合并前的
  `origin/master=4009108...` / `origin/runtime-state=7db58b...`；实时 fetch 已核对
  `origin/master=9bc58344beb5ce9bee2fdfebf4d1e1b452cad6c2`、PR #73/#74/#75/#76 已合并，
  `origin/runtime-state=40cbde2c30da2e2251956b52001b034b75b62ab5`。本条只做最小入口修正。
- locked identity：原 watchlist SHA-256=`5c16a0e7d57bc78249b05ea067aa798ace2c1e79bac78c1e40532a6b279573ea`；
  checkpoint=`64224f29ef102a283b5e83100705484ae55371a33c4e424a8bcffefc331ee376`；formal
  report=`acfbec2a7399c2eb83a5fe62c83ccbbfaf4852b9d9c8013b62de256789178aaa`；delivery
  receipt=`d37bf69a170f474faa0bd8fdf35a45820cb7c6767055e67b6d6fdd1e283c3751`。顺序固定为
  `000701,000807,001217,001222,600689,600929,601599,603096,603628,605003`。
- implementation：独立 branch/worktree 为 `codex/friday-volume-observation-only-backfill-v1` /
  `C:\awv`，PR #77，head=`4ba2798f620c119046046855950faabb7d0db77e`。工具只读取可信缓存或
  对上述十只调用 HiThink historical K-line，复用既有三项纯计算；未来日期、身份/OHLCV
  不兼容逐票 fail-soft，绝不写 prospective shadow。
- result：独立 addendum 为 `data/reports/daily_close_20260918_volume_addendum.html`，实际
  10/10 输入验证通过，9 只三项全有效；`600929` 的后半/前半均量比为
  `PULLBACK_WINDOW_LT_4`。报告 output SHA-256=`e1c110f64741690ccea2d85dd6762df2eafab2f28abf2753c503fc06e7da5d4e`。
- verification：local full pytest=`663 passed, 2 skipped, 11 warnings`；实际 provider
  access=`10` 个定向历史 K 线 symbol，universe/snapshot/Formal B/shadow calls=`0`，production
  dispatch=`0`，remote runtime-state mutation=`0`。PR #77 的 exact-head CI 是交付门槛，任何
  后续 push 后都必须实时重读；不自动 merge，终点仍为用户 merge decision。

## 2026-09-20 — PER_SYMBOL_FAIL_SOFT_PRODUCTION_V1

- classification：`correctness blocker + product blocker`（STRICT PATH）。目标是让正式生产
  对可归属到单只股票的数据异常 fail-soft；不改变 Formal B、Main Board 范围、Final OOS 或历史
  immutable artifact，也未读取或触碰 `data/validation/continuous_speed_probe/`。
- `PROJECT_GOVERNANCE_STATE_CONFLICT`：旧 handoff 仍停留在 PR #75 前后的 persisted snapshot；
  live fetch 已核对 `origin/master=40091083a67fed9a5dfb279868820951f38e8f39`，PR #73/#74/#75
  均已真实合并；live `origin/runtime-state=7db58bee3aadde658a01bc9c0bbf371ff444d1dc`。最近
  production failure 为 Actions run `35493683084`，canonical T-close step 失败但 failure
  notification/operational notice 成功；run `35492829019` 在 preflight 失败，均未据此触发生产。
- implementation：独立 worktree `D:\dev\ashare-watchlist-per-symbol-fail-soft-production-v1`、
  branch `codex/per-symbol-fail-soft-production-v1`，commit
  `d290c2ee3506fd5eba0b95fb6b0665afcfbdb857`，PR #76：
  https://github.com/EFSing/ashare_watchlist/pull/76。新写入使用
  `PER_SYMBOL_FAIL_SOFT_PRODUCTION_V1`；旧 coverage policy 仍可验证历史 artifact。单股票异常
  写入完整 machine exclusion record，正式输入状态为 `COMPLETE`/`DEGRADED`；没有有效输入时为
  `NO_VALID_INPUT`，只生成 bounded diagnostic report/完整 JSON，绝不生成正式空名单、正常成功
  checkpoint 或 delivery receipt。
- workflow verification：head `8e119dd637d8b0097a977acf0a6b015111c297e7` 的 run
  `35497053430` 为 `event=push`、check-suite `failure`、`jobs=0`；官方 actionlint 1.7.12
  定位 `.github/workflows/daily_t_close.yml:678` 的 NO_VALID_INPUT 路径 YAML 解析错误。该错误
  已以 Bash `$'\n'` 拼接方式最小修复，并已推送到 PR #76 分支；未执行 production job、
  provider live call 或 runtime-state 写入。
- verification：focused=`235 passed, 2 warnings`；此前代码实现 full pytest=`658 passed,
  2 skipped, 10 warnings`；修复后 actionlint（`ci.yml` + `daily_t_close.yml`）=`0 errors`，
  compileall 与 `git diff --check` 已通过。provider live calls、production dispatch、remote
  runtime-state mutation 均为 `0`。
- next：核验 PR #76 当前 live head 的 exact-head CI 与 mergeability；不自动 merge、不触发
  真实 production，终点为用户 merge decision。

## 2026-09-20 — FRIDAY_WEEKEND_BACKFILL_PREFLIGHT_STATE_FIX_V1

- classification：`correctness blocker`（STRICT PATH）。本轮只修复 PR #74 合并后暴露的
  workflow preflight 状态分支遗漏，不改变补跑日期、授权、凭证、HiThink 证据或任何生产语义。
- `PROJECT_GOVERNANCE_STATE_CONFLICT`：旧的当前入口仍将 PR #74 记为待合并；实时状态已确认
  PR #74 合并为 `bb061be8e5e81e6584878e578c097972a1ecc428`，workflow run `35492829019`
  在 preflight 返回 `AUTHORIZED_WEEKEND_BACKFILL_READY` 后因 workflow 只接受
  `POST_CLOSE_DIAGNOSTIC_READY` 而失败。
- runtime-state：live HEAD=`7db58bee3aadde658a01bc9c0bbf371ff444d1dc`，只有
  `daily_failure_notice_20260918.json`；没有 2026-09-18 的 watchlist、日报、checkpoint 或
  delivery success。该 failure notice 是 operational-only，不代表 canonical completion。
- implementation：独立 branch/worktree 为
  `codex/friday-weekend-backfill-preflight-state-fix-20260920` /
  `D:\dev\ashare-watchlist-friday-weekend-backfill-preflight-fix`，PR #75：
  https://github.com/EFSing/ashare_watchlist/pull/75 。仅在既有精确手动 production 授权条件下
  额外接受 `AUTHORIZED_WEEKEND_BACKFILL_READY`；普通生产仍只接受
  `POST_CLOSE_DIAGNOSTIC_READY`，并继续要求凭证与运行包 READY。
- verification：local relevant=`47 passed`；full pytest=`645 passed, 2 skipped, 10 warnings`；
  compileall 与 `git diff --check` 通过。未触发 production、未调用 provider、未修改 remote
  `runtime-state`；Final OOS=`SEALED / UNREAD`，`data/validation/continuous_speed_probe/`
  未读未触碰。
- next：重新核对 PR #75 最终 head 的 exact-head CI 与 mergeability；不自动合并、不触发
  production。终点为 `FRIDAY_WEEKEND_BACKFILL_PREFLIGHT_STATE_FIX_PR_READY_FOR_USER_MERGE_DECISION`。

## 2026-09-20 — FRIDAY_WEEKEND_BACKFILL_20260918_V1

- classification：`correctness blocker`（时间点、HiThink 日期证据、tracker/shadow 前瞻身份与
  runtime-state 幂等边界）；不改变 Formal B、冻结策略或研究结论。
- live reconciliation：`origin/master=b60fac712ab96218b210f017fcea5ec871cd47c6` 已包含 PR #73
  的单一 HiThink 生产行情源；其 master correctness run=`35484210930` 为 `success`。当前
  `origin/runtime-state=be8236629684b34dab5672df774918273536a5d9`，没有 2026-09-18 的 dated
  watchlist、日报、checkpoint 或 delivery receipt；仅有 2026-09-17 failure notice。
- implementation：独立 branch/worktree 为
  `codex/friday-weekend-backfill-20260918-v1` /
  `D:\dev\ashare-watchlist-friday-weekend-backfill-20260918-v1`，PR #74：
  https://github.com/EFSing/ashare_watchlist/pull/74 。授权只绑定手动 production、manual source、
  `as_of_date=2026-09-18`、默认关闭的 `allow_weekend_backfill`；preflight 与 acquisition 同时接线。
- safety：HiThink undated snapshot 必须与同源目标日 OHLCV/前收一致；补跑不写
  `PROSPECTIVE_CAPTURED` shadow，tracker observations 写入明确的非前瞻 source mode；失败不持久化
  正式成功。当前 production dispatch=`0`，provider calls=`0`，runtime-state remote mutation=`0`。
- verification：代码/测试 head `480e2e97c18916b2bdffb128212324c73284c379` 的 push correctness run
  `35485629651` 与 pull_request correctness run `35485631844` 均为 `success`；本条 checkpoint 后的
  文档提交使 branch remote head 前进，恢复时须实时读取其 exact head 与 PR #74 状态。focused=`188 passed`；
  full pytest=`644 passed, 2 skipped, 10 warnings`；compileall、`git diff --check` 通过；Final OOS=
  `SEALED / UNREAD`，`data/validation/continuous_speed_probe/` 未读未触碰。
- next：不自动 merge、不触发 production。用户
  合并后才可在仍处于合法窗口时以 `mode=production`、`as_of_date=2026-09-18`、
  `trigger_source=manual`、`allow_weekend_backfill=true` 手动 dispatch。
- terminal：`FRIDAY_WEEKEND_BACKFILL_PR_READY_FOR_USER_MERGE_DECISION`；若窗口进入 2026-09-21 或以后，
  必须停止补跑方案。

## 2026-09-18 — SINGLE_AUTHORITATIVE_MARKET_DATA_SOURCE_V1

- decision：生产 universe、snapshot、个股/指数 historical K 线只允许 HiThink Financial-API；
  Tencent quote/Kline 与 AkShare exchange roster production calls=`0`。Sina `新浪行业` 仅为
  optional fail-soft sector enrichment。
- safety：target-day trade state 使用 `TRADED` / `NO_TRADE` / `UNKNOWN`；null/partial 或缺少 T 日
  historical bar 不得推断为 NO_TRADE。HiThink stale 只做一次同源重试，仍不确定就 fail-closed，
  diagnostics 必须包含 symbol、target_date、latest_historical_date、provider、retry_count；不做
  per-symbol stale isolation。
- turnover：HiThink `turnover` 按成交额记录为 `turnover_amount`，不是换手率；Formal B 当前不
  要求 turnover/vol_ratio，缺失保持缺失，禁止补 0 或伪造。
- delivery：分支为 `codex/single-authoritative-market-data-source-v1`。用户已授权在最终 PR
  head、exact-head CI、master correctness CI、Formal B SHA、工作树范围与 runtime-state canonical
  completion 全部安全后直接 squash merge；merge 后若 2026-09-17 尚未 canonical completed，则直接
  以 `mode=production`、`as_of_date=2026-09-17`、`trigger_source=manual` 调度并监控到终态。
- boundaries：PR #60/#66/#67/#68/#71 untouched；Final OOS=`SEALED / UNREAD`；
  `data/validation/continuous_speed_probe/` 未读未触碰。实时状态以 remote/CI/runtime-state 为准，
  不把 transient SHA 或 run ID 写成永久治理不变量。

## 2026-09-17 — HITHINK_LIST_DATE_UNIVERSE_ELIGIBILITY_FIX_V1

- classification：`correctness blocker`（STRICT PATH）。2026-09-17 production failure 中，
  `001246.SZ`（力勤资源，`list_date=null`）在 universe 阶段未被排除而到达 Tencent quote；本任务
  只修复 HiThink list-date eligibility，不改变 provider、Kline、Formal B 或交易语义。
- live intake：仅使用本仓库的 live remote。`origin/master=9528484887abe724bad555f9475f2cf2fb98b144`
  已包含合并后的 PR #70，`origin/runtime-state=be8236629684b34dab5672df774918273536a5d9`；PR #71
  为 docs-only open PR，不作为 base。其余既有 open PR untouched。
- decision：HiThink `/api/meta/tickers/list` 仍是 universe authority；SH/SZ A-share 先通过既有
  Main Board policy，再要求可解析 `list_date <= target_date`。null/empty 与 future date exclude，
  malformed non-null date fail-closed；不新增 delisting/ST/suspension/seasoning policy。AkShare roster
  production calls=`0`。
- branch/worktree：`codex/hithink-list-date-universe-eligibility-v1`，独立 worktree
  `ashare_watchlist-hithink-list-date-universe-eligibility-v1`，基于 live `origin/master`。
- implementation：`HITHINK_LIST_DATE_ELIGIBILITY_V1` 的 counts、policy、target、source 与 fingerprint
  写入现有 universe quality，并绑定 generation identity；001246 在 quote 前回归覆盖。
- boundaries：Tencent quote/Kline fallback、stale isolation、Formal B 与 provider contract 未改变；
  development provider live calls=`0`，production dispatch=`0`，runtime-state remote mutation=`0`。
  Final OOS=`SEALED / UNREAD`，`data/validation/continuous_speed_probe/` 未读取或触碰。
- verification：focused/relevant=`180 passed`；full pytest=`630 passed, 2 skipped, 11 warnings`；
  compileall 与 `git diff --check` passed。
- delivery：PR #72 (`https://github.com/EFSing/ashare_watchlist/pull/72`) 已创建为非 Draft；文档提交
  后须以最终 head 重新核验 exact-head CI 与 mergeability，不自动 merge、不执行 production rerun。

## Historical completed task — REMOVE_AKSHARE_FROM_PRODUCTION_CRITICAL_PATH_V1

- classification：`correctness blocker + product blocker`（STRICT PATH）。旧 acquisition chain
  的 AkShare exchange roster JSON 解码失败会在 universe 阶段阻断整单，直接影响每日可用路径。
- live reconciliation：本历史记录当时处理了本文件原顶层的 #69 旧 snapshot；当时实时状态为
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
- delivery：已 push branch 并创建 target=`master` 的 Draft PR #70；PR #70 后续已合并，当前
  PR/head/CI 状态以 live GitHub 为准，不自动 merge。

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
