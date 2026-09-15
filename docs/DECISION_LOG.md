# DECISION LOG

职责：只记录具有长期约束力、未来需要解释“为什么这样设计”的决定（含进入、退出或拒绝
某项研究/产品决策的理由，以及冻结的契约）；不记录普通 bugfix、测试补充和局部实现细节。
当前操作接手规则见 [`HANDOFF.md`](../HANDOFF.md)；正式状态见
[`CURRENT_STATUS.md`](CURRENT_STATUS.md)。

## 2026-09-15 — CLOUD_SCHEDULE_RESILIENCE_V1 — adopt bounded date binding and operational failure dedupe

- classification：`product infrastructure + correctness`；不是策略研究、参数选择、promotion 或
  Final OOS 工作。
- decision：`ADOPT` a small run-context resolver. GitHub `schedule` runs use the supported cron's
  UTC calendar date as the immutable target and return `SKIPPED_STALE_SCHEDULE` after BJT midnight or
  before the valid post-close wake-up. `workflow_dispatch` accepts optional `as_of_date` and
  `trigger_source`; external production dispatch must provide a strict ISO `YYYY-MM-DD` date.
- decision：`ADOPT` a separate, dependency-free Cloudflare Worker Cron dispatcher at `25 9 * * 1-5`
  UTC. It only calls GitHub `workflow_dispatch` with `ref=master`, `mode=production`, explicit
  `as_of_date`, and `trigger_source=cloudflare-cron`. Repository state is `PREPARED / NOT_ACTIVE`
  until the user creates the fine-grained PAT, stores the secret in Cloudflare, and deploys it.
- decision：`ADOPT` operational failure notification receipt
  `data/delivery/daily_failure_notice_YYYYMMDD.json` with schema `DAILY_FAILURE_NOTICE_V1`. It is
  allowlisted only for that exact dated filename pattern, dedupes Email/Bark by target date, retries
  only failed channels, and is persisted from a clean runtime-state checkout so failed canonical
  staging cannot be bundled with it. It never participates in formal completion, B/tracker/shadow,
  or successful report-delivery receipt semantics.
- live evidence used for intake：`origin/master=64bba1df7b0dfd362938399ef5393f0912ce1e5f`,
  `runtime-state=1c8b2eca3792aebf327557fe9279b88a177b0545`; genuine production
  `34850228463=success`, late schedule `34865169737=success`, cross-day schedule
  `34868158949=failure`. PR #60 remains open and its `B_VOLUME_CONFIRM_FOCUS_V1` content is not
  included in this change.
- invariants：`B_BREAKOUT_RETEST_LEGACY_V1_1`, frozen spec SHA, Main Board-only universe, provider
  semantics, shadow semantics, historical artifacts, runtime-state canonical files, Final OOS
  `SEALED / UNREAD`, and `data/validation/continuous_speed_probe/` boundary remain unchanged.
- delivery：独立 PR #61 已创建，implementation head=`17e68b7139ed24441400b3a09c321466805d4032`；
  push correctness=`34922511075 success`，pull-request correctness=`34922534106 success`，不自动
  merge，Cloudflare 不在 PR 合并前启用。

## 2026-09-14 — DAILY_REPORT_EMAIL_AND_BARK_DELIVERY_V1 — adopt delivery-only infrastructure

- decision：`ADOPT` a small stdlib-only delivery helper and keep Email/Bark outside the canonical
  production engine. Email uses generic SMTP (`465` implicit SSL; other configured ports
  STARTTLS) and attaches the exact dated self-contained HTML; Bark uses the current official JSON
  `POST /push` contract with the device key in the request body and no critical/time-sensitive
  level.
- delivery contract：a formal success notification is sent only after the canonical production
  outputs and runtime-state commit are authoritative. Production hard failures send an explicit
  Email/Bark failure notification with the Actions run URL and no HTML attachment. Delivery
  channel failure never rolls back canonical state; the workflow reports `DELIVERY_SUCCESS`,
  `DELIVERY_DEGRADED`, or `DELIVERY_FAILED` separately.
- idempotency：`data/delivery/daily_delivery_YYYYMMDD.json` is operational-only state, not strategy,
  watchlist, tracker, shadow, performance, checkpoint identity, or research evidence. Its exact
  dated filename is the only new runtime-state allowlist entry and its `report_sha256` binding
  fails closed on identity conflict. Same-report dual success is `ALREADY_DELIVERED`; only failed
  channels receive the bounded retry.
- manual test boundary：`delivery-test` restores the existing runtime-state and sends explicitly
  marked test Email/Bark using `latest.html`; it does not call acquisition, generate a watchlist,
  update tracker/shadow, mutate runtime-state, or create a formal receipt. Missing delivery
  secrets are reported by name only as `REPORT_DELIVERY_SECRETS_REQUIRED`.
- invariants：formal B, spec SHA, Main Board-only universe, candidate qualification and ranking,
  trigger/stop/target/RR/T+1 semantics, shadow/provider semantics, historical artifacts,
  existing schedule/XSHG gate/`ALREADY_COMPLETED`, canonical report filenames, Final OOS boundary,
  and forbidden validation directory are unchanged.

## 2026-09-14 — MOBILE_DAILY_CLOSE_REPORT_RESPONSIVE_V1 — adopt shared responsive presentation

- decision：`ADOPT` one shared daily close HTML with CSS-only responsive behavior for the
  portrait mobile target `390–430 CSS px`，minimum `360 CSS px`。The mobile layout keeps the
  actionable watchlist fields visible without page-level horizontal scrolling；only wide
  trade/audit tables use contained touch horizontal scrolling。
- rationale：the existing report already has the canonical actionable fields and self-contained
  renderer；a single responsive presentation improves the mobile usable gate without duplicating
  report generation logic or creating a second artifact。
- invariants：header/date/market/strategy status，KPI/metric/funnel values，watchlist identity，
  score/ranking/trigger/stop/target/RR，review/shadow/audit content and deterministic output are
  unchanged。No strategy、universe、provider、acquisition、runtime-state、cloud workflow、T+1
  or historical artifact semantics changed；Final OOS remains unread。
- delivery：PR #53 implementation head
  `42de5ccde62fe9ea256398d2dfbc06ef911f5151` was squash-merged as
  `0c6f7e0fb579a411653eaebd6c385d4c9cb45099` after exact-head correctness success
  `34815050549`；post-merge master correctness `34815229243` also succeeded。

## 2026-09-14 — DAILY_UNATTENDED_GITHUB_ACTIONS_CLOUD_RUNTIME_V1 — bounded schedule adjustment

- decision：production wake-ups are adjusted to primary `17:17 BJT` (`17 9 * * 1-5` UTC) and
  bounded retry `18:17 BJT` (`17 10 * * 1-5` UTC). The adjustment is limited to when the
  existing unattended cloud workflow starts.
- invariants：XSHG trading-day gating, same-day `ALREADY_COMPLETED` idempotency, non-canceling
  concurrency, `workflow_dispatch`, preflight semantics, provider semantics, runtime-state
  authority/allowlist, ephemeral raw-data policy, and cloud Drive-disable behavior are unchanged.
  Formal B `B_BREAKOUT_RETEST_LEGACY_V1_1`, its spec SHA, Main Board-only universe, shadow
  semantics, historical artifacts, and Final OOS boundary are unchanged.
- boundary：this is a production scheduling change only; it does not change strategy, data,
  provider, runtime-state contents, universe, shadow, or research semantics. Final OOS remains
  `SEALED / UNREAD` and is not read.

## 2026-09-14 — GITHUB_ACTIONS_DAILY_RUNTIME_V1 — post-merge deployment gate

- outcome：PR #50 final head `468411f661211eb74140d89a7f489587bf8821a8` squash-merged into
  `master` as `cf1bbf53e4727bffdc6b1096f3d61b9bc5e03df4`; exact post-merge correctness run
  `34771128198` passed. Remote `runtime-state` is established at
  `140d8dc` and remains separate from source history.
- gate：the repository has zero configured Actions secrets in metadata. The workflow must stop at
  `GITHUB_ACTIONS_HITHINK_SECRET_REQUIRED` until the user adds `HITHINK_FINANCE_API_KEY`; no
  credential value is read, printed, committed, or fabricated. No cloud preflight, production
  T-close, weekend backfill, or provider call was performed during deployment.
- next boundary：after the secret is added, run only `workflow_dispatch` `preflight-only` first;
  the first production run remains the next genuine XSHG T-close. Formal B, Main Board-only
  universe, shadow and rule-performance semantics, and all historical/OOS boundaries are frozen.

## 2026-09-14 — GITHUB_ACTIONS_DAILY_RUNTIME_V1 — unattended cloud runtime boundary

- decision：每日生产计算使用临时 GitHub-hosted `ubuntu-latest` runner；GitHub Actions 是
  正常的唯一 production-state writer，远端 `runtime-state` branch 是跨设备生产状态权威，
  home/work PC 只读或本地复现。workflow 以 `ASHARE_DATA_ROOT` 统一定位临时数据目录，不依赖
  任一设备路径、浏览器、Excel、SQLite 或桌面 connector。
- schedule：使用 18:17 与 19:17 BJT 两个 bounded wake-up，实际是否运行完全复用
  `default_calendar()` 的 XSHG session 判断；非交易日只输出 `SKIPPED_NON_TRADING_DAY`，
  不生成名单、日报、tracker update 或 shadow capture。workflow 提供 `workflow_dispatch`
  的 `preflight-only` 模式，且不授权 weekend backfill。
- durable boundary：只允许 formal B canonical watchlists、`perf_tracker`、现有 shadow store、
  final daily reports 与已验证的 daily checkpoint manifest 进入 `runtime-state`。raw provider
  responses、K-lines、quotes、sectors、generation input package、`t_close_evidence` 与
  `prospective_inputs` 仅在 runner 临时目录存在，workflow 结束后随 runner 销毁。
- performance parity：若没有本地 immutable K-line evidence，cloud mode 只为报告实际需要的
  canonical signal codes 临时读取历史 OHLC，并标记
  `EPHEMERAL_PROVIDER_RULE_PERFORMANCE_RECONSTRUCTION`。该读取是理论 rule-price、只读、
  不回填 prospective observation，不写 tracker/canonical/shadow/runtime-state，不改变正式
  B 的 entry/exit/T+1/same-bar/sample semantics；provider failure 不静默降级为 N/A。
- correctness：shadow regime 的既有定义需要至少 61 根指数 bar，因此把默认 input count
  从 60 修正为 61；这是数据充足性修复，不是 threshold、regime 或策略修改。Drive checkpoint
  在 cloud mode 仅显式禁用 connector，仍保留本地 manifest 与默认本地行为。
- invariant：正式 `B_BREAKOUT_RETEST_LEGACY_V1_1` 与 spec SHA
  `f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd`、
  `ASHARE_MAIN_BOARD_ONLY_V1`、shadow semantics、Final OOS boundary 与历史 artifact 均不变。

## 2026-09-13 — USER_UNIVERSE_POLICY_DECISION — Main Board-only future production universe adopted and merged

- decision：未来 live universe 固定为既有 eligible universe ∩ Main Board，policy literal 为
  `ASHARE_MAIN_BOARD_ONLY_V1`。canonical `ASHARE_BOARD_TAXONOMY_V1` 是唯一板块分类来源：
  00/60 系列为 `Main`，30 系列为 `ChiNext`，68 系列为 `STAR`，其他代码为 `Unknown`；
  ChiNext 与 STAR 不进入未来 canonical live signals。
- scope：这是用户已经明确作出的生产交易范围决定，不是研究假设；不进行阈值搜索、性能重证、
  历史重写或 B evaluator 改动。政策在 live acquisition 的 quote/kline 之前生效，并在 B
  evaluator 前的 input boundary 保留同一 canonical filter，防止绕过 acquisition 的调用进入。
- provenance：future package/run manifest/generation identity/watchlist 记录 policy；日报 header
  显示 `沪深主板 / Main Board Only`，技术 literal 只在 audit 中出现。effective boundary 为
  `FIRST_GENUINE_T_CLOSE_RUN_AFTER_DEPLOYMENT`。
- invariants：`B_BREAKOUT_RETEST_LEGACY_V1_1` 的 evaluator、score、ranking、trigger、stop、
  target、RR 以及 spec SHA `f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd`
  保持不变；shadow monitor 继续旁路消费 canonical watchlist，不新增第二个 board filter。
  旧 artifact 缺少 policy 字段时仍可读取，且不被补写或伪造新范围。
- boundary/verification：不重跑 acquisition，不改写 2026-09-11 watchlist/tracker/report/evidence，
  不读取 Final OOS 或 `data/validation/continuous_speed_probe/`。PR #49 base `master`、branch
  `codex/main-board-only-universe`，final head `76c4635c768db07c2d721aa5e0bdb1373f473aa5` 于
  `2026-09-13T15:04:08Z` squash-merged 为 `14b43e81686f537debb713fc710f20c40a50ae63`；
  merge-time live `origin/master` 已核对为该 merge SHA；本条目仅记录唯一的 post-merge
  docs-only governance sync。implementation head 的 local full suite 为
  `529 passed, 10 warnings`，两个 implementation exact-head correctness runs 均 `success`。

## 2026-09-13 — Merge PR #47/#48 and activate prospective B shadow monitor

- live outcome：PR #47 exact head `1cf1ab419ab6e6bc6f6d1cfeadbef94b886d7ecf` squash-merged为
  `9bb23d63bff058d13b64de8f7864ea1da6222ba2`；PR #48 retarget 后只保留 shadow/source/test/docs
  增量，final head `1d31a6d2e4c0bd17370a4f99e328189ea2f9083a` squash-merged 为
  `105289cb1e0da318a0f7d07bb1dfd7a2af8d5054`。
- decision：`PR47_PR48_MERGED_PROSPECTIVE_SHADOW_MONITOR_ACTIVE`。正式 B 仍冻结；rule-price
  theoretical performance 与 observational shadow monitor 已进入 master，但 shadow 不参与任何
  candidate qualification、score、ranking、trigger、stop、target、RR、generation、live
  acquisition qualification 或 canonical identity。
- deployment boundary：prospective epoch 只有在首次真实 post-deployment T-close capture 时建立；
  不人为生成部署前 snapshot，不把 retrospective reconstruction 标成
  `PROSPECTIVE_CAPTURED`。FAST_STOP 固定为首个/第二个可卖 XSHG session 的 STOP；STOP recovery
  固定观察 +3/+5/+10 XSHG sessions，且不改变原 STOP outcome。
- verification：retarget 后 shadow targeted `22 passed`、full suite `508 passed, 10 warnings`、
  exact-head CI `2/2 pass`、diff check PASS；正式 B spec SHA 与 2026-09-11 canonical
  watchlist/input SHA unchanged。Final OOS 与 forbidden continuous-speed-probe 未读取。

## Pre-merge decision — Add prospective B shadow monitor without changing frozen B

- decision：在正式 `B_BREAKOUT_RETEST_LEGACY_V1_1` canonical output 之后增加独立的
  `PROSPECTIVE_B_SHADOW_MONITOR_V1`。它只观察 T-close market regime、既有 volume-path
  reactivation ratios、structural context，以及按正式规则价语义计算的 outcome、固定
  `FAST_STOP` 与 STOP recovery；不回答 signal 是否应进入名单。
- invariants：shadow 字段不得进入 qualification、score、candidate ranking、trigger、stop、
  target、RR、generation、live acquisition qualification 或 canonical identity。正式 B spec
  SHA `f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd` 保持不变。
- capture：从首次真实部署后 capture 建立 prospective epoch；T-close snapshot 使用当时已有
  package/index/stock bars，future bars fail closed；pre-outcome immutable，同值重复 ingest
  idempotent，冲突返回 `SHADOW_PRE_OUTCOME_IDENTITY_CONFLICT`。部署前数据只能标识为
  `RETROSPECTIVE_RECONSTRUCTED`，不能伪装成 prospective snapshot。
- outcome：entry 使用 canonical trigger，entry day 不可卖，卖出遵守 T+1；sellable bar 以
  canonical stop/target rule price 退出，同 bar 双触达为 `AMBIGUOUS`，无 T+10 forced exit。
  `FAST_STOP` 永久定义为 first/second sellable XSHG session；STOP 后 +3/+5/+10 XSHG
  sessions 的 recovery 不改变原 STOP 结果。
- governance：PR #47 live 仍 `OPEN / CLEAN / UNMERGED`，新实现以 exact PR #47 head 为
  stacked base；接手时 HANDOFF 的旧 head 因此构成并已纠正
  `PROJECT_GOVERNANCE_STATE_CONFLICT`。历史 stop-timing 只保存为 `REFERENCE_ONLY`，不作为
  threshold、candidate selection 或 strategy-change signal。
- reporting：每日报告新增轻量 shadow section 与当日候选 context；capture 不完整只产生
  `Shadow monitor data incomplete: X/Y` data-quality signal，不能污染正式 watchlist、runner
  success、strategy performance 或 review coverage。
- validation boundary：不读取 Final OOS，不读取或触碰
  `data/validation/continuous_speed_probe/`，不重跑 2026-09-11 acquisition；runtime shadow
  data/reports/watchlists/tracker/evidence 不纳入 source commit。

## 2026-09-10 — Complete bounded C→D migration and retention dry-run

- classification：`product infrastructure + correctness/provenance + recovery`，属于
  STRICT PATH；不改变 B strategy、review、provider、T+1、研究结论或正式 artifact 语义。
- decision：采用 D 盘 fresh remote-recoverable workspace 作为后续恢复入口；C-local
  operational/evidence state required for current review was copied and verified by exact
  counts/bytes, SHA identities, raw/sidecar pair integrity and formal archive/chunk checks。
- retention：复用 `ROUTINE_DAILY_EVIDENCE_ROLLING_20_SESSIONS` 规则，只做 inventory；截至
  2026-09-10 所有 present T-close dates 均在最近 20 个 XSHG sessions 内，candidate 为
  0 files / 0 pairs / 0 bytes。formal/frozen/recovery evidence、checkpoint/canonical
  artifacts、unknown validation 和 forbidden validation 不进入 routine deletion。
- boundary：C source remains intact；`DELETE=NO`；remote delete=0；acquisition/refetch=0；
  `data/validation/continuous_speed_probe/` 未读取、未 hash、未复制、未修改、未删除。
  下一步只剩 PR #46 的用户 squash-merge decision。

## 2026-09-09 — Reconcile PR #46 live head before C→D migration audit

- classification：`product infrastructure + correctness/provenance + recovery`，属于 STRICT
  PATH；不改变交易、review、provider、T+1、研究结论或正式 artifact 语义。
- live truth：PR #46 为 `OPEN / UNMERGED`；remote branch 与 pull head 均为
  `6191489edae55f7389d24526292d502b1c5932bd`，exact-head correctness run
  `34347550977` 为 `completed / success`。旧当前快照中的
  `b64a5fa088fff177dd93aa6cfbb39aaffa487517` / `34347321149` 已过时。
- decision：将该差异标记并以 bounded docs-only reconciliation 关闭
  `PROJECT_GOVERNANCE_STATE_CONFLICT`；只修当前入口，不改写旧历史 provenance，不把
  HANDOFF 设计成永久记录当前 branch exact HEAD 或 CI run 的不变量。
- boundary：reconciliation push 后必须重新读取 `HEAD`、`@{u}`、PR 和 exact-head CI；随后
  执行 C→D fresh clone、local evidence retention inventory 与 dry-run。routine daily
  raw/sidecar 本轮只提案、不删除；Final OOS、C、forbidden validation、Drive remote
  delete、acquisition rerun 和 PR merge 均不在授权范围内。

## 2026-09-09 — Adopt review-oriented daily close information architecture

- decision：daily close HTML is organized as overview → actual previous-session review → today's
  new list / next-trading-day observation → existing rolling review coverage → separate data
  quality → collapsed audit detail. A current-date signal is displayed as
  `T_PLUS_1_OBSERVATION_PENDING` / “今日新信号，等待下一交易日观察”, not as a historical missing
  observation.
- rationale：the prior report mixed current T-day candidates, yesterday's review, historical
  gaps and same-bar ambiguity into a long page with generic labels. Separating these states makes
  the operational decision surface readable without inventing observations, returns, win rates,
  or day-internal order.
- invariant：historical missing nodes remain `MISSING_HISTORICAL_OBSERVATION / UNVERIFIED`,
  missing confirmed entry keeps return unverified, and `AMBIGUOUS_SAME_BAR` remains fail-safe and
  visible. Score, Trigger, Stop, Target, RR, watchlist membership, T+1 rules, strategy identity,
  and formal review semantics are unchanged.
- operational wiring：only the exact successful canonical T-close runner status attaches the
  daily bundle, preventing the previous success-path omission while leaving preflight/failure
  behavior unchanged. The report exposes cloud `VERIFIED` only when the dated manifest itself
  carries remote verification; `LOCAL_INPUTS_VERIFIED` is not promoted by inference.
- evidence/stop：existing 20260909 timestamps show a 16-minute evidence-capture span and later
  post-processing, but do not isolate a code bottleneck. No benchmark, acquisition rerun, strategy
  change, Final OOS/C access, or forbidden validation-data access is authorized by this decision.

## 2026-09-09 — Reconcile live master before daily report usability work

- live truth：`origin/master` is
  `f5c4c6bbf9d3213fc15af75ceb57b4de23bb1559`; PR #43, PR #44 and PR #45 are merged, and
  master correctness run `34317755077` is `completed / success` for that exact head.
- decision：close `PROJECT_GOVERNANCE_STATE_CONFLICT` caused by the stale c139a04/PR #44
  current-state snapshot before continuing. The current bounded task is
  `DAILY_REPORT_REVIEW_USABILITY_AND_BUNDLE_WIRING`.
- boundary：the task may change presentation aggregation and the confirmed runner wiring only;
  it does not change canonical watchlist/tracker semantics, strategy, T+1 rules, provider
  acquisition, research conclusions, Final OOS, C, or the continuous-speed-probe boundary.

## 2026-09-09 — Merge and verify daily lightweight cloud checkpoint

- live truth：PR #44 was squash-merged into `master` at
  `c139a04c989913b14ae6c1c63aa14e63f66bc246`; `origin/master` matches exactly. Post-merge
  correctness run `34316393267` is `completed / success` for `push`, `master`, and that exact
  merge SHA.
- decision：`DAILY_LIGHTWEIGHT_CLOUD_CHECKPOINT_MERGED_MASTER_VERIFIED`. The bounded source is
  now formal master functionality; its six-file scope, manifest/length/SHA readback, same-path
  idempotence, same-path conflict fail-closed behavior, and fail-soft local-output boundary are
  effective. Remote deletion remains forbidden and `remote_deletes=0`.
- reconciliation：the stale PR #44 open/awaiting-merge state in the preceding handoff/status
  snapshot is retained as historical provenance and superseded by the current post-merge state.
  No historical record is rewritten, and no code, strategy, provider, scheduler, research,
  promotion, production approval, Final OOS, C, or old-D boundary is changed.
- stop：`Formal Delivery Ladder=frozen candidate`; Final OOS=`SEALED / UNREAD`; C unread; old D
  not reconstructed. Stop at `DAILY_LIGHTWEIGHT_CLOUD_CHECKPOINT_MERGED_MASTER_VERIFIED`.

## 2026-09-08 — Adopt daily lightweight cloud checkpoint with immutable dated state

- scope：在 PR #43 仍未 merge 的条件下，新增独立 stacked branch
  `codex/daily-lightweight-cloud-checkpoint`，只负责小型日终 checkpoint，不改变交易、
  review、tracker 语义或正式 evidence。
- decision：每个日期只保存 `watchlist_YYYYMMDD.json`、`perf_tracker.json`、dated HTML
  和小型 manifest；固定 latest 只保存 `latest.html` 与 `latest_checkpoint.json`。上传顺序
  是 dated watchlist → tracker → dated HTML/readback → dated manifest → latest 两个文件。
  同 logical filename 的相同 SHA 只能 `NO_OP_ALREADY_VERIFIED`，不同 SHA 必须
  `CLOUD_CHECKPOINT_CONFLICT` 并 fail closed，禁止覆盖、改名或复制。
- rationale：dated checkpoint 是可恢复的 immutable daily state，latest 只是已验证 dated
  state 的便捷指针；将 latest 更新置于 dated manifest 成功之后，可避免 latest 失败损伤
  dated recovery。
- governance：Kline/raw/sidecar/source evidence、prospective package、formal chunks 和
  historical archives 永不进入 daily scope。Drive inventory 只读分类为
  `FORMAL_KEEP`、`DAILY_KEEP`、`REDUNDANT_INTERMEDIATE_CANDIDATE`、
  `UNKNOWN_DO_NOT_DELETE`；本决定不授权任何 remote delete。无自动 scheduler，云端失败
  只产生精确原因并保持 canonical local files 不变。
- recovery：20260908 六个 checkpoint 文件实际上传、readback 与 SHA 验证通过，真实恢复
  smoke 通过；本地 inventory 报告保留为未跟踪 operational report。该 bounded follow-up
  的 terminal marker 是
  `DAILY_LIGHTWEIGHT_CLOUD_CHECKPOINT_STACKED_BRANCH_READY_AFTER_PR43_MERGE`。

## 2026-09-08 — Adopt exact-date immutable review recovery and completeness guard

- context：PR #43 的 2026-09-03 / 2026-09-07 review observation 在 2026-09-08 才发现缺口；
  本机已有同一收盘日的完整 raw/sidecar capture，但不存在可安全重放的 9/4、9/7 historical
  execution path。
- decision：冻结 `EXACT_DATE_IMMUTABLE_EVIDENCE_RECOVERY_V1`。只接受通过配对 SHA、capture
  schema、provider/source、retrieved-at、代码 SHA、Tencent canonical parser 和 QFQ OHLC
  compatibility cross-check 的本地 exact-date evidence。可写入 exact-date execution node 或
  fixed-horizon snapshot；不得由该 evidence 推断缺失的先前路径。无确认入场时 return 必须是
  `UNVERIFIED`，reason=`CONFIRMED_ENTRY_UNAVAILABLE`，path=
  `UNVERIFIED_MISSING_PRIOR_EXECUTION_PATH`。
- guard：每日 report date `R` 更新前冻结 expected execution（current signal、list_date < R、
  start status pending/triggered）和 expected horizon（scheduled_date == R）；更新后 execution
  必须有 observation.date==R，horizon 必须是 exact-date `CAPTURED` 或带明确 reason 的
  `NOT_CAPTURED`。缺失时输出 `REVIEW_OBSERVATION_INCOMPLETE`，保留 canonical watchlist，HTML
  顶部告警，禁止静默降级为完整报告。
- rationale：同时保留可验证的 contemporaneous market node 与不可验证的 historical path 边界，
  避免 current quote、provider refetch 或 fabricated replay 造成 look-ahead / outcome overclaim。
- consequences：9/7 的 25 个 execution observations 与 9/3 的 11 个 T+3 snapshots 可审计；
  9/3 的 11 个 execution obligations 仍显式 missing，当前 coverage 为 36/25/11 和 11/11/0。
  正常 future daily runner 使用 `LIVE_DAILY_TRACKER_QUOTE` provenance；recovery 使用本策略
  provenance；既有无 provenance observation 仍可读。
- boundaries：不改变 B strategy/threshold/scoring/target、acquisition priority、T+5 primary、
  Final OOS/C/old D/historical B semantics，也不触碰 `data/validation/continuous_speed_probe/`。

## 2026-09-06 — Adopt FAST/STRICT path and minimal cross-device governance

- context：既有治理要求每个任务默认读取全部治理/protocol 文件并实时核验历史
  PR/CI/artifact，跨设备恢复成本高；HANDOFF 堆叠大量历史快照造成同步压力。
- decision：远端 Git 为代码、测试、配置及跨设备可恢复开发状态的事实源。普通开发默认
  FAST PATH，开始只检查 working tree、branch、HEAD、remote/fetch 并读取 `HANDOFF.md`；
  仅 STRICT PATH（交易语义、数据口径、universe/样本、look-ahead/OOS、数据污染、正式
  artifact、不可逆写入、merge/release、资金/生产风险等）验证当前任务真正依赖的
  PR/CI/artifact/数据血缘/研究证据。HANDOFF 最小化为 7 项恢复字段；CURRENT_STATUS 只在
  可独立交付/PR/merge/release/研究阶段/稳定流水线状态实质变化时更新；DECISION_LOG 只
  记录长期约束决定。`REMOTE_RECOVERY_CHECKPOINT` 是状态定义（commit+push+HANDOFF 指向
  remote branch/HEAD+可无聊天记忆继续），不新增文件/Phase/registry/gate。
- rationale：降低普通开发的治理验证成本，同时保持跨设备恢复链 remote Git → branch →
  remote HEAD → HANDOFF → next action 不降级。
- consequences：历史 PR/CI 快照不再写入 HANDOFF（provenance 保留在 Git 历史与既有
  status/decision 文档）；governance-only commit 使 HEAD 前进不再构成冲突；
  `PROJECT_GOVERNANCE_STATE_CONFLICT` 只针对当前任务真正依赖且与 live 状态矛盾的记录，
  不做无边界历史审计。
- revisit condition：跨设备恢复能力或普通开发治理验证成本出现实质退化时。

## 2026-09-06 — PR #37 merge reconciliation and VCB research handoff

- live state：PR #37（`research: cross-sectional RS leadership V1`）已在 exact merge SHA
  `547feebb88e7b755785c2ae590ea7e4cca0c7a0d` 合并；merge-head correctness runs
  `33987664237` / `33987644452` 均为 `success`。旧治理文档仍描述 PR #37 open/awaiting
  merge，构成仅限治理快照的 bounded `PROJECT_GOVERNANCE_STATE_CONFLICT`。
- decision：执行一次 docs-only reconciliation，只更新 `HANDOFF.md`、
  `docs/CURRENT_STATUS.md`、`docs/DECISION_LOG.md`；不修改 B、RS、Volume-Path、turnover/RV、
  protocol semantics、research artifacts、production path、frozen state 或 Final OOS。
- next research：用户正式选择 `NEW_VOLATILITY_CONTRACTION_BREAKOUT_V1`。当前只进入
  no-outcome input audit；必须在任何该候选 forward outcome access 前完成并 commit 固定 protocol。
- boundaries：Final OOS=`SEALED / UNREAD`；B prospective outcomes、C、controlled reversal、
  provider replacement、current-data backfill、parameter tuning、promotion 和 freeze 均未运行；
  `data/validation/continuous_speed_probe/` 未读取、未修改、未删除、未 hash、未上传。

## 2026-09-02 — Workstation-to-home seamless handoff checkpoint

- classification：`correctness blocker` follow-up / operational handoff；不新增研究问题，
  不改变既有 `ADOPT — EXCHANGE_OFFICIAL_CURRENT_LISTED_ROSTER_V1` decision。
- current task：`TRADABLE_UNIVERSE_LISTING_ELIGIBILITY`。当前停止点是官方 SSE/SZSE
  roster correction 已实现、验证、推送至 PR #25，等待 user merge decision；formal
  capture=`NOT_RERUN`，candidate list=`NOT_EVALUATED`，正式 Delivery Ladder 仍为
  `development candidate`。
- preserved boundary：`301686` 的 T 日上市资格只能由 official roster deterministic
  evidence 决定；`002731` 已上市停牌仍保留；ST/*ST 仍仅在 B 后处理；Tencent
  `p[38]=""`、B evaluator/spec/threshold/score 和 frozen artifacts 不变。
- handoff result：工作站必须把 branch、PR、治理文档及合法代码变更推送到 GitHub；家用
  电脑接手时重新核对 live branch/HEAD/base/PR/exact-head CI/worktree。未上传 secrets；
  `data/validation/continuous_speed_probe/` 保持本机未跟踪，交接过程中不读取、不修改、
  不删除、不上传。
- final objective：`WORKSTATION_STATE_DURABLY_PUSHED_AND_HOME_RESUME_READY`；不 merge，
  不启动 Phase 2F/C、Final OOS、promotion、调参或 formal capture。

## 2026-08-27 — Phase 2A provenance labels

- context：V0 `screen_system.py` 的历史输入、as-of snapshots、raw responses 和 adjustment factors 不完整。
- decision：无法证明的规则与结果使用 `UNKNOWN_ORIGIN` / `NOT_REPRODUCIBLE_WITH_CURRENT_DATA`，不从当前数据补造历史。
- rationale：历史可复现性优先于表面上完整的规则恢复。
- alternatives：按现有代码推测历史数据；把当前结果视作历史重演。
- consequences：部分 legacy 输出保持不可验证，但研究结论不会被伪造为已证实。
- revisit condition：取得可验证的原始 payload、as-of provenance 和调整因子后，另开审计。
- PR / commit：PR #2；`b1c4615`（merged）。

## 2026-08-27 — Phase 2B close-only timing contract

- context：需要定义 generation input 的可知时间和执行时间，避免盘中、same-bar 或当前数据回填。
- decision：只接受 T 日正式收盘后的 close generation；最早执行是 XSHG 下一个交易日 T+1；时区为 `Asia/Shanghai`；日历 pin 为 `exchange-calendars==4.13.2`。
- rationale：T close → T+1 是项目明确的时序边界，真实 provider session close 不能用人工缓冲代替。
- alternatives：premarket generation；same-bar execution；固定 15:05/15:10 代替交易所 session close。
- consequences：盘中输入返回 `SESSION_NOT_CLOSED`；历史 replay 不属于本阶段 generation contract。
- revisit condition：明确批准新的 timing contract 并新增协议版本。
- PR / commit：PR #3；`e587753`（merged）。

## 2026-08-27 — Phase 2C baseline remains research-only

- context：需要恢复 V0 A 平台突破规则并提供可审计的逐标的 evaluation。
- decision：建立 `A_PLATFORM_BREAKOUT_LEGACY_V1` evaluator，保留完整 85 分 breakdown 字段，但不做 TOP N、score cutoff、portfolio selection、scheduler 或 production write。
- rationale：规则恢复不等于预测有效性验证；sector evidence 缺失时必须显式不足，不能静默用中性值。
- alternatives：直接发布 canonical watchlist；把 85 分当成已验证信号；使用 `rank=50/chg=0` 作为缺失 fallback。
- consequences：只产生 research `CandidateEvaluation`；完整 legacy output parity 仍待历史新浪行业 membership。
- revisit condition：完成指定 validation layer、历史 provenance 和显式 promotion decision。
- PR / commit：PR #4；`fc2762e`（merged）。

## 2026-08-28 — Phase 2D point-in-time validation protocol

- context：CORE / historical validation 需要防止 current universe、current sector、future events 和 known-at 违规。
- decision：冻结 `PHASE2D_VALIDATION_PROTOCOL_V1`；semantic SHA 为 `a7db6dc2d6f2dba2555855236fce5580f5e13e192e66991f0f9f63cb0eb9e7ee`；输入必须有 T 日证据、source/version/hash 和 `known_at <= T`。
- rationale：缺证据时 fail-closed，比用近似数据产生不可审计结果更安全。
- alternatives：current constituents backfill；current sector taxonomy 替代历史新浪行业；把 provider forward 结果改名为历史 T-anchor。
- consequences：历史新浪行业 membership 成为 FULL legacy validation 的明确 blocker；核心 signal layer 可以与 sector score layer 分离。
- revisit condition：取得满足 effective-date / T-day semantics 的历史新浪 membership source。
- PR / commit：PR #5；`4ea7b5c`（merged）。

## 2026-08-29 — Phase 2E CORE replay and DEVELOPMENT V2 outcome

- context：在 Phase 2D contract 下验证 CORE signal/level，并在明确授权后测量 DEVELOPMENT outcome。
- decision：完成 769-session continuous CORE replay；以冻结 raw input、T-anchor affine adjustment 和 T+1 open 完成 V2 DEVELOPMENT returns；V2 为 `RECONSTRUCTED_RETROSPECTIVE`，Final OOS 保持 false。
- rationale：先冻结信号 identity，再把 outcome measurement 与 full 85-score parity、production promotion 分离；raw V1 不覆盖，只保留 diagnostic。
- alternatives：读取 Final OOS；把 retrospective data 写成 OOS；用 unadjusted raw outcome 作为 primary；重跑已完成 769 日 replay。
- consequences：CORE 工程结果和 V2 development metrics 可审计，但 FULL legacy 仍因新浪行业 membership blocked，不能 promotion。
- revisit condition：获得历史 sector membership、接受 vintage provenance 边界，并得到新的明确 validation / OOS 授权。
- PR / commit：PR #6；head `edb57a3`，merge `74ccf86dfdea3b9d4b0124fb54346aa429735508`。

## 2026-08-29 — Project handoff governance

- context：跨设备接手需要同时知道 formal master、local unpublished work、artifact identity、backup 和 CI 状态。
- decision：新增 `HANDOFF.md`、`CURRENT_STATUS.md`、本文件、`FROZEN_ARTIFACT_POLICY.md` 和 `data/governance/frozen_artifacts.json`；治理 branch 从 master 独立派生，不吸收 local-only Phase 2F。
- rationale：职责分离可避免把会话摘要、正式状态、决策理由和 artifact inventory 混为一份易漂移文本；local-only artifact 必须显式标注为不可完全恢复。
- alternatives：继续依赖会话记忆；从 Phase 2F local HEAD 建治理 PR；把未验证的外部 backup 写成已存在。
- consequences：新会话有固定冲突 gate；`daily_k.parquet` 在唯一 Google Drive private-download parquet member 完成 exact SHA recovery verification 后更新为 `FULLY_RECOVERABLE`。
- revisit condition：治理 PR 合并后，或发生 phase/PR/CI/artifact/provenance/production-status 变化时更新治理文件。
- PR / commit：PR #7；head `c72ad0498a1ac89966ea39e1e600647f14926ada`，squash merge `16ad543bb39a7d01ed4c484406f1053ca5da0ec2`；merge CI run `33250117945` success。

## 2026-08-29 — daily_k Google Drive recovery verification

- context：`daily_k.parquet` 的本机 bytes 已有 frozen SHA，但此前缺少独立 persistent backup 与 recovery read；Google Drive 下载条目为一个 ZIP archive。
- decision：只读取 Downloads 根目录中实际下载的 `daily_k.parquet-20260829T145838Z-1-001.zip`，对其唯一 member `daily_k.parquet/daily_k.parquet` 的解压字节流做 SHA-256；member size `180203424` bytes，SHA 严格匹配 `61189a4850e2eb157453e28e5375e502e20d214508bbe70ea71066ca3e05e426`，matching member count 为 1。更新 registry 为 `LOCAL_PRESENT`、`HASH_VERIFIED`、`PERSISTENT_BACKUP_PRESENT`、`RECOVERY_VERIFIED`、`FULLY_RECOVERABLE`，storage type 为 `GOOGLE_DRIVE_PRIVATE`。
- rationale：恢复身份由 frozen parquet bytes 决定；ZIP 自身 hash、文件名、绝对路径、URL、token 和 credentials 都不替代 byte-level identity，也不进入治理 identity。
- alternatives：按名称猜测；把项目目录原始 frozen 文件当作 recovery copy；把 ZIP hash 当作 parquet hash；记录 share URL 或临时 URL。
- consequences：`daily_k.parquet` 的跨设备 persistent-backup / recovery blocker 已解除；不改变 Phase 2E replay、strategy、protocol、Final OOS 或 Phase 2F 边界。
- revisit condition：recovery archive/member 不可读、member 数量变化、member SHA 不再匹配 frozen SHA，或 backup storage semantics 发生变化时，立即降级为 `NOT_FULLY_RECOVERABLE` 并停止 replay/resume。
- PR / commit：PR #8；head `2a1fa22ad474ee91c5946d5d0c1d49db34d691a4`；squash merge `7fe15d8fd2eaf07892a0051321fa6d1dc4352ef9`；PR exact-head correctness runs `33259704118`、`33259700451` success，merge master correctness run `33259819493` success。

## 2026-08-29 — Product charter and agent development contract

- context：Phase 2E research/development evidence 和现有 manual review utility 已存在，但项目需要明确何时能进入每日 observation / paper-use，避免把 deferred research 误当成 release blocker。
- decision：新增 `docs/PRODUCT_CHARTER.md` 定义产品使命、范围、十项 usable gate、P0–P3 blocking severity、Delivery Ladder 和 anti-research-loop rule；新增根目录 `AGENTS.md` 作为所有新 Codex / agent 的强制 intake、分类、边界和 research exit 契约。当前 formal Delivery Ladder 保持为 `research`，不作 production promotion。
- rationale：研究、PIT、provenance、hash 和 validation 服务于可靠的每日系统；没有端到端 deterministic generation、canonical output、explicit failure、monitoring/rollback/versioning 的证据，不能把研究完成写成 usable。
- alternatives：继续以 research 完整度作为唯一 release 条件；把所有未解决研究都列成系统 blocker；从 local-only Phase 2F 分支直接晋级 product candidate。
- consequences：P1 只用于阻止当前 usable milestone；历史新浪 membership 缺失明确限制在 FULL legacy / 85-score validation，不能阻止 CORE research 或 prospective product progression；新的研究必须以 `ADOPT`、`REJECT`、`DEFER` 或 `NEEDS_MORE_EVIDENCE` 结束。
- revisit condition：具体 usable gate、当前 frozen candidate 或真实产品范围发生变化时，更新章程并记录新 decision；不得用新指标本身触发新 Phase。
- PR / commit：PR #9；head `859935fb80a0de585149da16ead8870db11a63a7`；squash merge `7a27484293cbcb791c6b8407949e9e71257e016b`；PR exact-head correctness runs `33260677946`、`33260690327` success，merge master correctness run `33260777592` success。

## 2026-08-29 — Phase 2F local diagnostic exit decision

- context：local-only commit `3eeb5df9f7cf4ef5c30b3380b323f26f2491f873` 的 Phase 2F DEVELOPMENT diagnostic 在不修改冻结策略/阈值、不读取 Final OOS 的边界内分析 A_MATCH/QUALIFIED 的失败结构与执行归因。
- decision：`NEEDS_MORE_EVIDENCE`。诊断结果不足以 adopt production threshold、promotion 或自动启动 Research V2；如未来继续，必须先有 materiality justification、预注册比较和明确 exit gate。
- rationale：Phase 2E V2 结果是描述性 `RECONSTRUCTED_RETROSPECTIVE`，Phase 2F 能帮助判断当前候选是否应被拒绝或是否值得一个范围受限的新 protocol，但当前证据没有证明稳定可迁移 edge。
- alternatives：把诊断画像直接改成规则；因为发现分组差异就自动调参；把历史 sector/membership 缺失扩大成整个产品 blocker。
- consequences：Phase 2F 的研究结果保持 local-only / research-only，不改变 formal master、strategy、data、Phase 2E artifacts 或 product delivery；FULL legacy blocker 仍只作用于对应验证层。
- revisit condition：取得足以改变下一 product decision 的 evidence，或明确批准一个新的 preregistered research protocol 后，另记新 decision。
- PR / commit：Phase 2F 没有在本次治理 PR 中发布；本条只记录其退出 decision。

## 2026-08-30 — Live Git State vs Persisted Governance Snapshot

- context：tracked governance 文档曾把静态的 current HEAD / CI 记录写成实时 invariant；治理文档自身的后续 commit 会使该 invariant 永久自引用并制造假冲突。
- decision：live Git/GitHub state 永远在 intake 时实时查询；tracked docs 只保存 `last_verified_master_snapshot`、last-verified CI provenance、历史 milestone identities、正式 Delivery Ladder、Current Objective、blockers/deferred、decisions 和 frozen identities。
- rationale：SHA 前进本身不是治理语义变化；只有 material semantic divergence、required frozen identity/hash mismatch 或非法历史后继才构成 `PROJECT_GOVERNANCE_STATE_CONFLICT`。
- alternatives：每次治理文档变更后把新 HEAD/CI 再写回同一文档；把 snapshot 与 live HEAD 强制相等；把 GitHub API 依赖放入普通 unit tests。
- consequences：snapshot 可以落后 live HEAD，governance-only commit 不会形成无限更新循环；冻结 strategy/protocol/artifact identity 仍保持 exact-match gate，语义产品状态不一致仍 fail closed。
- revisit condition：live intake、正式 Delivery Ladder、Current Objective、frozen identity 或历史 branch/base/merge provenance 的语义发生变化时，更新对应治理职责文件并记录新的 decision。

## 2026-08-30 — Development Candidate Gate V1

- context：PR #12 在既有 Phase 2B close-only input contract 和既有 legacy evaluator
  wiring 上建立了受控 development-candidate path；代码审计和 development gate
  evidence 已完成，随后 PR #12 已 squash merge。
- decision：`ADOPT` development candidate product path V1。PR #12 已 squash merge，正式
  Delivery Ladder 已从 `research` 晋级为 `development candidate`；对象是产品路径，
  不是 `A_PLATFORM_BREAKOUT_LEGACY_V1` strategy 本身。
- rationale：该路径已经证明 deterministic generation → schema-valid canonical
  watchlist → explicit fail-closed handling → immutable provenance/versioning →
  monitoring/rollback 的受控闭环，具备继续核验 frozen-candidate prerequisites 的
  产品基础。
- gate evidence：正常 evaluator 运行即使 `candidate_count=0` 也成功生成
  `candidates=[]` canonical watchlist，重复运行保持 output SHA 幂等，downstream
  ingest 可读取且 monitor 为 `HEALTHY`；evaluator failure 与 zero-candidate 明确
  区分；`generation_fingerprint` 覆盖 Phase 2B `input_fingerprint`、contract/schema
  version、strategy identity、实际参与输出的规范化 names、canonical `market_env`
  和其他输出相关辅助输入；同一 T 的不同 generation identity fail closed；write
  failure、rollback、完整 provenance monitor 均有回归证据；focused/full tests、
  compileall、JSON/hash/provenance、diff 和 secret checks 通过，并以 exact-head CI
  复核。
- known limitations：输入仍限于 READY frozen generation manifest 和受控
  development fixtures；历史新浪 industry membership / effective-date evidence
  缺失仍只限制 FULL legacy validation；retrospective data 的 vintage provenance
  限制仍存在。该 gate 不证明参数有效性、收益 edge、跨数据源迁移性或运营上线安全。
- non-equivalence：本 decision 不构成 frozen candidate，不构成 production strategy，
  不构成参数选择或调参，不构成 Final OOS 结论，也不授权自动交易、promotion 或
  自动启动 Phase 2F。
- consequences：正式 Delivery Ladder 已为 `development candidate`；后续必须先核验
  frozen-candidate prerequisites，明确必须解决的 P0/P1，并在 prerequisites PASS
  时定义 frozen candidate contract/gate。不得把 product-ladder 晋级改写为 legacy
  strategy promotion。
- revisit condition：frozen-candidate prerequisites、产品范围、required
  provenance 或正式 promotion decision 发生变化时，另记 decision；任何新的
  research question 必须有独立 exit decision，不能由本 gate 自动触发新 Phase。
- PR / commit：PR #12；最终 merge 状态和 exact-head CI 属于 live Git/GitHub
  provenance，不在本条写入会自引用的 current HEAD。

## 2026-08-30 — Frozen-candidate prerequisites audit V1

- context：PR #12 已将产品管线正式带入 `development candidate`；下一 decision
  不是默认把既有 legacy baseline freeze，而是审计当前是否存在真实、获批准且有
  足够 development evidence 的 strategy candidate。
- research question：当前项目是否已经具备一个可以进入 frozen candidate gate 的
  真实 strategy candidate？停止条件是完成 product infrastructure、strategy
  eligibility、data/provenance 和最小 operational prerequisite 核验后形成唯一
  decision；不以新增指标或优化方向扩大研究。
- decision：`FROZEN_CANDIDATE_BLOCKED`，具体原因为
  `FROZEN_CANDIDATE_BLOCKED_NO_APPROVED_STRATEGY_CANDIDATE`。
- rationale：当前没有正式 nominated/approved strategy candidate；
  `A_PLATFORM_BREAKOUT_LEGACY_V1` 仍是 research-only wiring witness。虽有可复核
  spec identity、T close/T+1、deterministic generation、canonical output、
  fail-closed、monitoring/rollback 和 artifact recovery 的 development/path
  evidence，但现有 CORE 与 `DEVELOPMENT` / `RECONSTRUCTED_RETROSPECTIVE` evidence
  不足以支持“值得进入 prospective/frozen candidate”的资格判断；sector score
  仍 `UNVERIFIED`，FULL legacy 仍受历史新浪 membership 限制，Phase 2F 仍是
  `NEEDS_MORE_EVIDENCE`。
- P0/P1：本轮没有新的全局 P0 correctness/safety defect。frozen gate 的 P1 是
  (1) strategy nomination/eligibility decision 缺失，(2) 固定 development evidence
  的候选资格 decision 缺失，(3) candidate-bound prospective input/provenance
  package 缺失。历史新浪 membership 只作为 FULL legacy retrospective scope 的
  blocker，不升级为全局 blocker。
- consequences：不把 A baseline 晋级为 frozen candidate，不创建或伪造
  `FROZEN_CANDIDATE_CONTRACT_V1`，不启动 Phase 2F、不调参、不读 Final OOS、不
  promotion。scheduler、broker、自动交易和复杂告警不属于当前 frozen gate 的最小
  前置条件。
- next decision：取得上述最小 nomination/eligibility 与 candidate-bound
  prospective evidence 后，回到 `FROZEN_CANDIDATE_PREREQUISITES` decision point；
  缺少这些证据时仍保持 BLOCKED。完整审计见
  [`frozen_candidate_prerequisites_audit.md`](frozen_candidate_prerequisites_audit.md)。

## 2026-08-30 — Strategy Candidate Nomination V1

- context：PR #13 已以 expected head `0f5629765ef0eebbae0c6981f2d7ccafab7f7e35`
  squash merge；其 master merge CI 已成功。当前任务只允许确定下一只值得进入
  development eligibility 验证的 candidate，不允许调参、Phase 2F 或 Final OOS。
- A decision：`REJECT_A_PLATFORM_BREAKOUT_LEGACY_V1_AS_FROZEN_CANDIDATE`。冻结的
  Phase 2E V2 primary evidence 为 1D 42.4594% / -0.1270%，3D 42.6095% / -0.2281%，
  5D 40.6703% / -0.5085%，10D 41.3134% / -0.4631%；scope 是 DEVELOPMENT /
  RECONSTRUCTED_RETROSPECTIVE，不是 Final OOS。A 仍是 research baseline / regression
  witness；该 decision 不外推到平台突破思想、未来 A 版本或 Research V2。
- inventory：只审计已有固定 V0 provenance 的 A、B breakout-retest、C
  main-trend-retest；D / generic old history types 因 exact mapping/provenance 不完整
  排除。未引入其他项目规则。
- nomination：在读取 B/C development returns 之前，按 exact provenance、未知来源、
  frozen/recoverable data、无 backfill、Phase 2B contract、implementation/inference
  complexity 的 lexicographic rule，唯一提名
  `NOMINATE_B_BREAKOUT_RETEST_LEGACY_V1_FOR_DEVELOPMENT_ELIGIBILITY`。B lower
  complexity；若仍相同，B→C 是固定 research tie-break，不是预测排名。C 不做 returns
  evaluation。
- reconstruction：B exact V0 reconstruction PASS；V0 source commit
  `c8406c393c0b135eafb0aec763576ae869fddcff`，source SHA
  `6cac746123e315199cbeeb1a612868ef77b50af6c7c64b0d80eb387ae1d19f9`，canonical
  semantic spec SHA `5bbeb345ebd8883149138d2f29f8606f919949ae285aa2839fa337921dfc7112`；
  focused parity/hash/edge/decision tests `7 passed`。
- eligibility environment stop：此前的环境阻塞状态统一为
  `CANDIDATE_ELIGIBILITY_BLOCKED_ENVIRONMENT`，原因是
  `B_ELIGIBILITY_NOT_EXECUTED_MISSING_PARQUET_READER`。这不是 B performance
  rejection、no-rule conclusion 或 C rejection。
- fixed replay：安装 exact-pinned `pyarrow==17.0.0` 后，以 Python 3.12.13、
  pandas 2.2.3 只运行一次相同的 `STRATEGY_DEVELOPMENT_ELIGIBILITY_V1`；首次
  parquet read 前 registry required artifacts 13/13、daily_k exact SHA
  `61189a4850e2eb157453e28e5375e502e20d214508bbe70ea71066ca3e05e426`、raw source、
  checkpoint、CORE projection/manifest identity 均通过，frozen bytes 未修改。
- frozen protocol：`ELIGIBILITY_RULE_FROZEN_BEFORE_B_RETURNS_READ = true`；
  minimum N=30、primary=10D、10D positive rate >=50%、mean >0、median >0、
  robust years >=3（每年 >=10 events）、positive robust-year means >=2。结果未改动
  threshold。
- B result：Event N `17,714`；available N 1D/3D/5D/10D 为 `17,689` / `17,635` /
  `17,602` / `17,558`；10D positive rate / mean / median 为 `51.6403%` /
  `+1.4603%` / `+0.3226%`；4 个 robust years 中 2 个 mean 为正，fixed gates 全部
  PASS。
- decision：`CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES`。这是 B candidate
  eligibility 的 `ADOPT`，不是 production strategy promotion、parameter validation
  或 Final OOS 结论。event artifact SHA 为
  `8940a4a346ac6911ba669f84a9ceba7ef878b0ed0ce51edf673439b52aa056b9`；eligibility
  original manifest file SHA 为 `a0c5a195ea991a471fd56eb80534d03091d6bd308f6c6f263476737380a28c9a`；
  该文件后续仅因 provenance correctness 修复而 deterministic rematerialized，当前
  file SHA 由 2026-08-31 closure entry 记录。
- prospective contract：定义
  `CANDIDATE_BOUND_PROSPECTIVE_INPUT_PROVENANCE_CONTRACT_V1`，绑定 B strategy/spec
  SHA、T close/T+1、universe、sector semantics、names、market_env、provider/version、
  calendar、availability/fail-closed、recovery 和 generation/output identity；不伪造
  尚未发生的 live instance。
- rejudged prerequisites：`FROZEN_CANDIDATE_BLOCKED`；唯一 P1 为
  `P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE`，等待首个真实 candidate-bound
  `LIVE_OBSERVED` T-close package 并验证 `known_at <= T`。不测试 C、不启动 Phase 2F、
  不调参、不读 Final OOS、不创建 `FROZEN_CANDIDATE_CONTRACT_V1`。

## 2026-08-31 — PR #14 governance conflict and provenance correctness closure

- context：Sol 独立审计发现 active PR body 仍保留旧的 parquet-reader stop /
  `NO_REPRODUCIBLE_STRATEGY_CANDIDATE` 叙述，与 HEAD 上已完成的 B eligibility
  及 HANDOFF/CURRENT_STATUS/本日志冲突；同时 eligibility manifest provenance
  serialization 允许 CLI absolute path 影响 manifest identity。
- decision：只修 active PR metadata、eligibility provenance canonicalization 和
  formal decision-artifact registry；B fixed rule/spec/thresholds、observed metrics、
  event set 与 decision 全部保持不变。
- provenance：不同 filesystem root 及 relative/absolute invocation 的 regression
  证明 canonical identity 相同；path 只保存稳定 repo-relative logical provenance，
  `Path.resolve()` 的 machine-specific result 不进入 semantic/content/manifest hash。
- deterministic verification：同一冻结 raw/CORE inputs 与既有固定 protocol 完成一次
  reproducibility verification；event count `17,714`、event file SHA
  `8940a4a346ac6911ba669f84a9ceba7ef878b0ed0ce51edf673439b52aa056b9`、event semantic
  SHA `a16e48dfbe8a93f64d8bf1bad6e00d3eaf32c10fd60eed09dc5574247b8119bc`、metrics
  identity、all gates 和 `CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES` 与修复前完全
  一致。manifest 只做 deterministic provenance rematerialization；new manifest
  semantic SHA 为 `f79ec9baa494f2f0256843c2540988bd25c94269ed9a1fd4ada228759bd8e0a2`，
  payload content SHA 为 `e754787836b28316430278372ab2d84817091d4608da394f9207f695a4c27aee`，
  file SHA 为 `5e0a557c1930de7b4f182f09f43b45c0c11b19b2d7c992bf9e7fa7e6cc6de048`。
- registry：两个 B artifacts 均登记为 `required_for_decision=true`、
  `required_for_replay=false`，并验证 registry 的实际 file/content SHA 与提交文件
  完全匹配；不记录 absolute path、URL、token 或 secret。
- governance outcome：Formal Delivery Ladder 仍为 `development candidate`，不创建
  `FROZEN_CANDIDATE_CONTRACT_V1`；唯一当前 P1 仍为
  `P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE`；不 promotion、不测试 C、不启动
  Phase 2F、不调参、不读 Final OOS。
- revisit condition：只有首个真实 candidate-bound `LIVE_OBSERVED` T-close input
  instance 到来，或正式 strategy/protocol/data/provenance identity 改变时，才重新
  进入对应 decision gate。

## 2026-08-31 — Live acquisition adapter readiness

- task classification：本轮属于 product blocker 审计，并包含 correctness fail-closed
  风险；不是新的 strategy research、参数选择、Phase 2F 或 Final OOS 任务。
- audit finding：当前 master 原有 Phase 2B `GenerationInputManifest` 只验证已构造
  的输入，没有 AkShare universe/sector adapter，也没有 Tencent qfq stock/index K
  acquisition path，因此确认存在 `P1-FC-LIVE-ACQUISITION-ADAPTER_MISSING`。
- implementation decision：在从当前 master 派生的单一分支中补齐最小
  `scripts/live_acquisition.py`，绑定 B strategy/spec identity，严格执行 T close /
  T+1、`LIVE_OBSERVED`、provider/version、names、market_env、coverage/conflict/
  freshness、fingerprint、immutable persistence 和 fail-closed contract；新增
  AkShare `1.18.94` 明确 pin。B strategy/spec/threshold、冻结数据和既有 research
  artifacts 均未修改。
- readiness evidence：mock/fixture tests 覆盖 pre-close、wrong date、provider
  unavailable、空/不完整 universe、sector member/rank/name failures、stale/missing
  quote/Kline、future bar、T+1、deterministic fingerprint/bytes、no backfill 和
  incomplete manifest 不产生 output。实际 runtime probe 读取 AkShare `1.18.94`；
  pyarrow 保持 `25.0.1`，没有执行 research optional pin 的降级。
- boundary：这是 implementation/runtime readiness，不是 prospective evidence；本轮
  不调用 live provider，不生成或冻结正式 `LIVE_OBSERVED` T-close package，不生成
  canonical watchlist。Formal Delivery Ladder 仍为 `development candidate`，唯一
  formal prerequisite blocker 仍为 `P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE`。
- revisit condition：Sol review/CI 后合并才可将 adapter 视为 master path；正式收盘后
  才能运行真实 T 日采集，并按 `CANDIDATE_BOUND_PROSPECTIVE_INPUT_PROVENANCE_CONTRACT_V1`
  审计首个 package。

## 2026-08-31 — First prospective T-close acquisition attempt

- task classification：本轮属于 product blocker 审计，并包含 provider-induced
  correctness fail-closed 风险；不是新的 strategy research、参数选择、Phase 2F 或
  Final OOS 任务。
- baseline：PR #15 已按 expected head
  `f0528744d9fe0add78436a543b15afa12c2e229e` squash merge，merge SHA 为
  `f1fed4608210aa175ac268189a8d7f032b0b88e0`；master correctness run
  `33367655723` success，head 精确匹配 merge SHA。
- timing：T=`2026-08-31` 被 exchange-calendars/XSHG 判定为真实 session，官方
  session close 为 `2026-08-31T15:00:00+08:00`，T+1 为 `2026-09-01`。正式调用使用
  实际运行时 `observed_at_bjt=2026-08-31T15:21:18.969554+08:00`，满足 close 后
  precondition。
- provider result：正式调用 `acquire_live_generation_inputs()` 在 AkShare sector
  membership acquisition 阶段发生 `ConnectionError`，adapter 映射为
  `PROVIDER_FAILURE` 并停止。已做首次调用加两次有限重试；另外在切换到 merge
  master 后做了一次 formal master-baseline attempt，结果相同。
- decision：`FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_PROVIDER_FAILURE`。本次没有
  READY `GenerationInputManifest`，没有 `LIVE_OBSERVED` package，没有 universe/
  sector/quote/Kline completeness evidence，没有 input/generation fingerprint，
  没有 package content/file SHA 或 logical path。
- fail-closed evidence：T/session-close/date gate PASS；AkShare runtime capability
  已可读取且版本为 `1.18.94`；sector membership provider failure STOP；Tencent
  quote、stock/index Kline、market_env、manifest READY、persistence、exact-byte
  read-back、recovery 和 frozen-candidate audit downstream checks 均
  `NOT_REACHED`，不得写成 PASS。
- persistence/recovery：`ASHARE_DATA_ROOT` 本次显式指向仓库 `data` 根；由于没有
  完整 package，`data/prospective_inputs/` 未创建，没有 local package、persistent
  backup 或 recovery identity 可登记。没有修改 `data/governance/frozen_artifacts.json`。
- hash audit note：对既有、非 replay-required 的 `phase2e.hithink_probe` record
  进行 JSON/hash audit 时发现，当前 exact bytes SHA 为 registered `file_sha256`
  `395601b...`，但预存 `working_tree_sha256` 为 `af694b...`。这是本轮之前的
  provenance discrepancy；未自动修复、未重新下载、未改变 frozen identity，也没有把
  该 probe 用作本次 live evidence。后续若要修复，需单独记录明确治理 decision。
- consequences：Formal Delivery Ladder 保持 `development candidate`；B 的
  `CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES`、strategy/spec/threshold、冻结数据、
  existing artifacts 和 Final OOS sealed 状态不变；不创建
  `FROZEN_CANDIDATE_CONTRACT_V1`，不 promotion、不测试 C、不启动 Phase 2F、不调参、
  不读 Final OOS。
- revisit condition：仅在 provider 可用后的新真实 XSHG T-close session 重新 acquisition；
  不把 2026-08-31 的失败回填为成功，不跳过 sector coverage，不猜 membership，且
  必须重新满足完整 `CANDIDATE_BOUND_PROSPECTIVE_INPUT_PROVENANCE_CONTRACT_V1`。

## 2026-08-31 — PR #16 same-day retry semantics and AkShare bounded retry

- context：Sol review 发现 active PR #16 草稿把同日 retry 错写成只能等待下一个
  T-close session；真实 AkShare acquisition 还显示三个 provider-read API 没有
  adapter-level transient retry，sector membership 的单次 `ConnectionError` 会终止整次采集。
- task classification：product blocker hardening，并包含 provider-induced correctness
  fail-closed 风险；不启动新的 strategy、Phase、promotion、参数选择或 Final OOS。
- decision：`ADOPT` 最小 retry hardening；同一 BJT 日期 T 在正式收盘后允许新的独立
  live acquisition attempt。每次 attempt 使用新的真实 `observed_at`、重新获取全部
  required input、不复用 failed attempt 的 partial response；第一次失败保留，跨到
  下一 BJT 日期后禁止用当前 live provider 数据构造此前 T 的 package。
- implementation：AkShare `stock_info_a_code_name`、`stock_board_industry_name_em`
  和每个 `stock_board_industry_cons_em` read 只对 transient network/connection
  exception 做固定最多 3 次 retry，backoff bounded 为 `0.25s`、`0.50s`。schema、
  empty、duplicate、name/sector conflict、coverage 等 response semantics 在 retry
  边界外一次性校验；exhaustion 映射 `PROVIDER_FAILURE` 且不产生 formal output。
- identity：attempt/backoff 仅为 process diagnostics，不进入 canonical input /
  generation/package content identity 或成功 provenance；不改变 provider source、
  B strategy/spec/threshold、Phase 2B contract、冻结 artifact 或 Final OOS。
- scale audit：完整 universe 的固定执行模型是 1 次 universe read、1 次 definitions
  read、每个 definition 1 次逻辑 member read、`ceil(N / 50)` 个 Tencent quote batch、
  N 个 stock Kline request 加 1 个 index request。它是 execution diagnostics，不是筛选
  规则；不得缩 universe 或跳过股票。首次正式失败在 sector membership，后续实际计数
  保持 `NOT_REACHED`。
- evidence：新增回归覆盖 universe/definitions transient recovery、persistent
  3-attempt failure、sector-member recovery、semantic/schema no-retry、no-output 和
  retry-independent identity；full pytest、compile、JSON/hash、diff 和 secret checks
  必须在 PR #16 exact head 上通过。
- consequences：Formal Delivery Ladder 仍为 `development candidate`；唯一 frozen
  prerequisite P1 仍为 `P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE`，同日窗口内
  可在 clean merged master 重新 acquisition；不创建 `FROZEN_CANDIDATE_CONTRACT_V1`。

## 2026-08-31 — PR #16 merged and same-day retry remained blocked

- context：PR #16 的 bounded AkShare retry hardening 已在 exact-head CI 全绿后合并；
  按 Phase 2B 同日 close contract，在北京时间仍为 `2026-08-31` 时于 clean merged
  master 上重新发起独立 acquisition。
- provenance：PR #16 final head 为
  `f604dc39c681ee63c075cc0fea5cef367d6296f5`，squash merge SHA 为
  `c9d5e50be833bf5bb1c3c83c0a2fa1b3e83979c1`；merge master correctness run
  `33372781495` success，head 精确匹配 merge SHA。新的 attempt 使用真实
  `observed_at_bjt=2026-08-31T16:27:36.974203+08:00`，没有复用第一次 attempt。
- result：AkShare `stock_info_a_code_name` 在固定 `3/3` attempts 后以
  `ConnectionError` fail closed，provider/API 为 AkShare/universe，acquisition elapsed
  `0.782s`；sector code/name 不适用，completed sector calls `0`，sector definition
  count `NOT_REACHED`，universe symbol count `0`，Tencent quote batch、stock/index
  Kline、market_env、manifest 和 persistence 均 `NOT_REACHED`。
- decision：`FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_PROVIDER_FAILURE`。两次失败均保留；
  没有 READY manifest、`LIVE_OBSERVED` package、fingerprint、content/file SHA、
  logical path、partial formal evidence 或 recovery copy。没有把失败改写为成功，也
  没有 current-data backfill；本任务不自动无限重试。
- consequences：Formal Delivery Ladder 仍为 `development candidate`；B eligibility、
  B strategy/spec/threshold、Phase 2B semantics、frozen artifact identities、Final OOS
  sealed state 和既有 `phase2e.hithink_probe` non-blocking metadata debt 均未改变。
  不创建 `FROZEN_CANDIDATE_CONTRACT_V1`，不 promotion、不测试 C、不启动 Phase 2F、不调参。

## 2026-08-31 — P0 live sector taxonomy mismatch correction

- task classification：`correctness blocker` P0，并包含阻止当前 candidate-bound live
  path 使用的 product/provider architecture blocker；不启动新的 strategy research。
- research question and materiality：当前 authenticated HiThink Financial-API 是否能
  支持 universe/names 与 stock/index K primary，以及 AkShare 当前是否仍能提供 B 冻结的
  exact Sina industry membership；答案决定能否修正 live adapter，而不修改 B spec。停止
  条件是 endpoint capability、返回 schema/taxonomy 和 fail-closed boundary 均被核实。
- finding：merged master 的 `stock_board_industry_name_em` /
  `stock_board_industry_cons_em` 是东方财富 industry taxonomy，违反 B exact legacy
  provenance（AkShare `stock_sector_spot` / `stock_sector_detail`，`新浪行业`）。两次
  `2026-08-31` attempt 都在 package 构造前失败，故没有 contaminated prospective
  artifact，也不改写既有失败事实。
- capability evidence（非 prospective evidence）：HiThink authenticated metadata/
  ticker、snapshot、stock historical K、index historical K、adjustment-events 当前均
  返回 HTTP 200 / `code=0` 与结构化字段；AkShare `1.18.94` 的 exact Sina spot/detail
  当前可调用，live probe 返回 49 个行业及首个 detail 的 19 个成员。没有保存 raw
  payload、没有构造 manifest/package、没有进行收益研究或 Final OOS 读取。
- decision：`ADOPT` 最小 provider correction。HiThink metadata primary universe/name；
  HiThink `adjust=forward` stock K 和 unadjusted index K primary；exact Sina API 是唯
  一 sector source；Tencent quotes 保留既有字段语义；Tencent Kline 仅作为明确版本化
  `LIVE_MARKET_DATA_FAILOVER_POLICY_V1` / `TENCENT_QFQ_FALLBACK_V1` transport fallback。
  EM/THS/SW 代替、taxonomy/schema/date/coverage failure 和非 transient provider failure
  均 fail closed。HiThink index 使用 `PROVIDER_RAW_SNAPSHOT`，不伪装成 qfq。
- invariants：B strategy/spec/threshold、spec SHA
  `5bbeb345ebd8883149138d2f29f8606f919949ae285aa2839fa337921dfc7112`、T-close/T+1、
  no-current-data-backfill、no-future-bar 和 existing frozen artifacts 均不变。
- verdict：`HITHINK_LIVE_PRIMARY = SUPPORTED`；
  `EXACT_SINA_SECTOR_SOURCE = AVAILABLE`。
- next decision：单一 correction PR #17 已创建并保持 `OPEN`，head=
  `869eade1eaf48e2d470175e234e83c99fd2168ac`；pull-request correctness run
  `33379014737` 与 push correctness run `33378978157` 均在该 exact head 成功，当前
  `CLEAN`/`MERGEABLE`。停在 Sol review；review/merge 后是否运行新的 prospective
  T-close acquisition，必须由用户在新的合法 close session 明确授权；本任务不自动
  选择新的 T、不生成 package、不启动 C/Phase 2F、不调参、不读 Final OOS、不 merge。

## 2026-08-31 — PR #17 adjustment boundary and tradable-universe scope closure

- task classification：`correctness blocker`（stock raw Kline 可被通用 validator 接受）
  加 `product blocker` hardening（live universe scope 未进入稳定 identity）；不是新的
  strategy research、参数选择、Phase 2F 或 Final OOS 任务。
- research question / materiality：不新增研究问题；修正直接决定 live input 是否能
  fail closed，以及未来 BJ 纳入是否会被识别为不同产品范围。停止条件是 stock/index
  provider-adjustment 配对、scope identity、provenance 和回归测试全部明确。
- decision：`ADOPT`。`KlineManifest` 只接受 `PROVIDER_QFQ_SNAPSHOT`；`IndexManifest`
  只接受 HiThink Financial-API + `PROVIDER_RAW_SNAPSHOT`，或 Tencent +
  `PROVIDER_QFQ_SNAPSHOT` 的 explicit fallback；其他 adjustment/provider 配对 reject。
- decision：`ADOPT` `TRADABLE_UNIVERSE_SCOPE_V1 = SH_SZ_A_SHARE_ONLY`。SH/SZ A 股
  included，BJ explicitly excluded，BJ absence 不属于 incomplete coverage；scope/version
  进入 UniverseManifest content hash、GenerationInput input fingerprint、live
  generation identity、provider metadata 和 prospective provenance。
- invariants：B strategy、B spec SHA、B threshold、既有 frozen historical artifacts、
  Final OOS sealed 状态和 T-close/T+1 semantics 均不变。既有 B development eligibility
  不重跑、不改写；若历史输入包含 BJ，只记录
  `KNOWN_DEVELOPMENT_VS_PROSPECTIVE_UNIVERSE_SCOPE_DIFFERENCE`，不自动推翻既有 decision。
- consequence：PR #17 仍是现有 correction PR 的最后 hardening；合并前不获取真实
  prospective input，不生成 package/watchlist，不启动 C/Phase 2F，不调参，不读 Final OOS。

## 2026-08-31 — First post-merge LIVE_OBSERVED acquisition attempt

- context：PR #17 已按 actual expected head `ef48d192c7709a7194348369c689070c665da2b4`
  squash merge，merge SHA 为 `91e9ec76e3f4ea8ffaa1badeb759c1d2a7f5f73b`；merge master
  exact-head correctness run `33399324692` 成功。随后在同一合法 XSHG T-close window
  用 fresh `observed_at_bjt=2026-08-31T22:01:28.307161+08:00` 执行正式 acquisition。
- contract：T=`2026-08-31`，T+1=`2026-09-01`，`LIVE_OBSERVED`，scope/version 为
  `SH_SZ_A_SHARE_ONLY` / `TRADABLE_UNIVERSE_SCOPE_V1`；universe/names 使用 HiThink
  primary，sector 使用 AkShare 1.18.94 exact `新浪行业` spot/detail；没有复用此前失败
  attempt、capability probe 或 partial response。
- finding：在 exact Sina sector/member display-name consistency 阶段发现
  `INPUT_CONFLICT: display-name conflict for 000012: universe/member`；quotes、Kline、
  market_env、manifest、package、persistence 和 Drive recovery 均未执行。
- decision：`FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_INPUT_CONFLICT`；这是 required
  name/provenance consistency conflict 的 fail-closed blocker，不是 provider
  connectivity failure；不得用猜测映射、current data 或 taxonomy substitution 继续。
- consequences：没有 `READY_FOR_STRATEGY_EVALUATION`、package/content/file SHA、byte
  length、local logical path 或 Drive persistent recovery reference；没有 canonical
  watchlist、prospective returns、C、Phase 2F、调参、paper/live trading 或 promotion。
  不向 frozen artifact registry 添加伪 artifact；attempt evidence 另存为
  `data/governance/prospective_input_attempt_evidence_20260831.json`，并明确
  `not_a_frozen_artifact=true`。
- invariants：B strategy/spec/threshold、`5bbeb345ebd8883149138d2f29f8606f919949ae285aa2839fa337921dfc7112`、
  exact Sina taxonomy、SH/SZ scope/version、T-close/T+1、provider/fallback provenance、
  monitoring/rollback、Final OOS sealed/unread 均不变。
- next decision：在 provider/name consistency conflict 解决且新的合法 T-close window
  到来后，重新获取全部 required inputs；在此之前保持该 input blocker，不构造 package，不创建
  `FROZEN_CANDIDATE_CONTRACT_V1`。

## 2026-08-31 — PR #18 display-name consistency conflict and minimal correctness fix

- task classification：`correctness blocker`；这是输入/provider-data consistency
  conflict，不是 provider connectivity failure，也不是新的 strategy research、Phase、
  参数选择、Final OOS 或 promotion 任务。
- historical correction：2026-08-31T22:01:28 的正式 attempt 保留
  `INPUT_CONFLICT`、stage=`exact_sina_sector/display_name_consistency`、symbol=`000012`
  和原始 detail；其 final decision 改为
  `FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_INPUT_CONFLICT`，分类为
  `INPUT_PROVIDER_DATA_CONSISTENCY_CONFLICT`。原始 attempt 未保存 raw names 或执行
  计数，故不以 current diagnostic 回填这些字段，也不把失败改写为成功。
- current capability diagnostic：在不读取 returns、Final OOS 或策略结果的前提下，
  重新读取完整当前 `SH_SZ_A_SHARE_ONLY` universe 与 exact Sina sector/member source。
  HiThink universe 为 5,220 symbols，Sina definitions 为 49，完成 49 次 member call，
  common symbols 为 2,539；2,492 个 raw names 一致，47 个 raw names 不一致。`000012`
  的 raw universe name 为 `南玻Ａ`（`U+5357 U+73BB U+FF21`），raw sector name 为
  `南 玻Ａ`（`U+5357 U+0020 U+73BB U+FF21`）。完整清单见
  [`current_capability_name_diagnostic_20260831.md`](current_capability_name_diagnostic_20260831.md)。
- decision：`ADOPT` 统一、预注册、语义安全的名称比较规则
  `DISPLAY_NAME_NORMALIZATION_NFKC_TRIM_EXPLICIT_ZERO_WIDTH_V1`：只移除显式零宽
  格式字符、执行 Unicode NFKC、trim 首尾 whitespace；raw universe/sector values
  继续保留，symbol 仍是 security identity，normalization version 进入 generation
  identity/provenance。`REJECT` 删除 ST/*ST、A/B 标记、内部 whitespace、listing suffix、
  fuzzy/edit-distance、拼音或按 symbol 忽略实质分歧。
- result：该规则消除 0 个当前 raw-name mismatch；47 个冲突 normalization 后仍不一致，
  因而当前真实 blocker 为
  `FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_SUBSTANTIVE_NAME_CONFLICT`。adapter 继续
  fail closed，并将 symbol、两边 raw/normalized names、universe count、sector
  definition count 和 completed member calls 暴露为非 secret structured diagnostics。
  该修复不产生 partial formal package。
- invariants/next decision：B strategy/spec/threshold、`SH_SZ_A_SHARE_ONLY`、exact Sina
  taxonomy、T-close/T+1、Final OOS sealed/unread、C exclusion、Phase 2F exclusion 和
  no tuning 均不变。2026-09-01 白天只完成修复与 review；PR #18 完成 Sol review 并合并
  到 clean master，且 XSHG 正式收盘后，才可运行新的 `T=2026-09-01` `LIVE_OBSERVED`
  acquisition；不构造 T=`2026-08-31` package。

## 2026-09-01 — B dependency audit, symbol-authoritative names, and sector gate

- classification：`correctness blocker` + `product blocker`；任务只处理首个
  candidate-bound prospective input 的可执行依赖与 cross-machine development path，
  不启动新的 strategy research、参数选择、Phase 2F、C、Final OOS 或 promotion。
- research question：B 的 display name、sector membership、`sector_name`、
  `sector_rank`、`sector_chg` 是否真的进入 executable/output semantics；当前 exact
  Sina provider 能否在不缩 universe、不替换 taxonomy、不回填历史的情况下满足它们。
- materiality：该结论决定 PR #18 的 name correction 是否安全，以及 B 是否仍需完整
  sector evidence 才能进入 frozen-candidate gate。停止条件是 source call graph、
  field/gate matrix、provider coverage、duplicate 和 ambiguity 已明确；不因当前快照
  发现新的分组或指标而扩大研究。
- inputs：`scripts/b_breakout_retest.py`、`scripts/a_platform_breakout.py`、B
  nomination/eligibility/prospective contract、PR #18 changes，以及 fresh `.venv`
  的 read-only HiThink/AkShare probe。当前 payload 只在内存中读取，结果记录在
  `docs/b_dependency_audit_20260901.md`，明确标记为
  `LOCAL_CURRENT_SNAPSHOT_DIAGNOSTIC_NOT_PROSPECTIVE_EVIDENCE`。
- source finding：exact six-digit symbol 是 security/trading identity；display name
  不参与 symbol join、candidate selection、hard gates、trigger、stop、target、RR、
  score、final status 或 B canonical identity。`sector_rank`/`sector_chg` 分别进入
  B 85-score 的 `strong_sector`/`sector_linkage`，缺 sector evidence 返回
  `INSUFFICIENT_DATA`，故 sector 仍是 `EXECUTABLE_REQUIRED`，不是 generic baggage。
- decision：`ADOPT`
  `DISPLAY_NAME_CONSISTENCY_POLICY_V2_SYMBOL_AUTHORITATIVE`。raw HiThink/Sina names
  独立保留，registered normalization 只做 diagnostic；不 fuzzy reconcile、不生成
  alias、不用名字 join/filter；policy/diagnostics 进入 active V2 contract、provenance
  和 generation identity。V1 historical evidence 不改写。
- current provider evidence：fresh preflight exact versions 全部 PASS；HiThink current
  scope 为 5,221 symbols，exact Sina 为 49 definitions/49 member calls；sector audit
  报告 2,682 个 universe symbols 缺 membership、439 个 sector symbols 在 universe 外、
  47 个 raw-name mismatch（normalization resolve 0），以及 `000587`、`000602`、
  `002217`、`002617`、`600714` 五个 distinct multi-sector memberships；当前无 exact
  duplicate symbol。该事实随 provider snapshot 变化，不回填 2026-08-31。
- decision：`NEEDS_MORE_EVIDENCE` for a future legitimate T-close exact-Sina response
  that is complete and unambiguous for the full scope. Exact duplicate same-sector rows
  may be deterministically deduplicated only with raw row/count provenance; distinct
  sector memberships remain fail closed, with no silent drop/substitution/backfill。
- current gate at that historical snapshot：
  `FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_SECTOR_MEMBERSHIP_AMBIGUITY`, with an
  independent exact-Sina coverage failure. PR #18 remains unmerged; no T=`2026-08-31`
  backfill and no T=`2026-09-01` acquisition/package is created in this task. Formal
  Delivery Ladder remains `development candidate`; B eligibility remains
  `CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES`; Final OOS remains `SEALED / UNREAD`。

## 2026-09-01 — Sector provenance closure and exact B semantic stop

- classification：`correctness blocker` + `product blocker`。这是对现有 candidate-bound
  input gate 的 closure，不是新的 strategy research、Phase、参数选择、C、Final OOS
  或 promotion。
- research question / materiality：V0 的 missing-sector 与 multi-sector 行为是否被
  当前 B evaluator 和 V2 live contract 精确保留；AkShare `1.18.94` 是否相对 exact
  Sina raw endpoint 造成当前 2,682 missing symbols；以及当前 package-level fail-close
  能否直接解释为 per-symbol Model S。结果会决定是否允许进入合法 T-close capture，
  因而属于 correctness/product gate，而非可忽略的分组研究。
- inputs：V0 exact source
  `EFSing/ashare_watchlist-V0@c8406c393c0b135eafb0aec763576ae869fddcff`，当前
  `scripts/b_breakout_retest.py`、`scripts/a_platform_breakout.py`、generation/live
  contract，AkShare `1.18.94` installed source，以及 2026-09-01 current HiThink/Sina
  in-memory responses。未读取 Final OOS，未使用 2026-08-31 partial attempt 回填。
- stop condition：只在 source semantics、provider parity、coverage decomposition、
  five multi-sector identities、package/per-symbol distinction 都明确后停止；若
  evaluator 偏离 exact frozen B，则不得修 B 或继续 T-close capture。
- finding：V0 missing sector 使用 `("-",50,0.0)` 继续 B，multi-sector 为 provider
  order 下 last-write-wins；current B missing evidence 返回 `INSUFFICIENT_DATA`，
  且绕过 adapter 的 ambiguous manifest 会取第一条有效记录。V2 adapter 的完整覆盖
  与 distinct multi-sector package fail-close 是额外的 input-integrity hardening。
- provider decision：`EXACT_SINA_CURRENT_SOURCE_INTRINSICALLY_INCOMPLETE`；同时
  `REJECT` `EXACT_SINA_AKSHARE_WRAPPER_INCOMPLETE`。49/49 exact definitions 的
  raw/wrapper member rows、per-sector counts/boundaries 均一致；当前 source coverage
  shortfall 不是已证实的 wrapper parsing/pagination 漏抓。count endpoint
  under-reporting 保留为 future provider-consistency diagnostic，当前不改 wrapper。
- final decision：`B_RECONSTRUCTION_SEMANTIC_MISMATCH`。不采用 Model S/V3，不改变
  B/spec/threshold/taxonomy/scope/name policy，不生成 partial package。formal
  `LIVE_OBSERVED` capture=`NOT_RUN`；Delivery Ladder 仍为 `development candidate`。
  详细 evidence、5-symbol table、2,682 decomposition 和 machine-readable record 见
  [`sector_provenance_closure_20260901.md`](sector_provenance_closure_20260901.md)。
- invariants：PR #18 merge SHA 为
  `17371fde39a6b24241532b131caf5927cb9b8933`，exact merge correctness run
  `33476256589` success；B spec SHA
  `5bbeb345ebd8883149138d2f29f8606f919949ae285aa2839fa337921dfc7112`、Final OOS
  `SEALED / UNREAD`、no-backfill/no-future、C/Phase 2F/promotion exclusions remain
  unchanged。

## 2026-09-01 — B frozen spec text conflict blocks semantic repair

- context：本轮按既定 closure 指令重新读取 exact V0 source，并在修复 evaluator 前核对
  current B semantic spec。任务分类仍为 `correctness blocker` + `product blocker`，
  不是 strategy research、参数选择、Phase 2F、C、Final OOS 或 promotion。
- exact V0 evidence：指定
  `EFSing/ashare_watchlist-V0@c8406c393c0b135eafb0aec763576ae869fddcff` 的
  `get_sectors()` 以 spot `label` iteration、detail member row iteration 和
  `mapping[symbol] = name` 构成 provider-order last-write-wins；主流程
  `sec_map.get(code, "-")`、`sec_rank_map.get(sec_name, 50)`、
  `sec_chg_map.get(sec_name, 0.0)` 对缺失 sector 采用 exact legacy tuple，并继续
  `analyze()`。该事实支持 `LEGACY_PROVIDER_ORDER_LAST_WRITE_WINS_V1` 与
  `("-", 50, 0.0)`，不支持当前 `INSUFFICIENT_DATA` 分支。
- spec finding：当前 B `LEGACY_SPEC` 继承的 sector evidence contract 明确包含
  `silent_fallback=False` 和 `missing_status=INSUFFICIENT_DATA`。这不是只存在于
  package-level contract 的解释差异，而是 frozen executable spec text conflict。
- decision：`B_FROZEN_SPEC_TEXT_CONFLICT`。不在本轮修改 B evaluator、live contract、
  strategy version、B spec SHA 或旧 eligibility artifact；停止在 Sol review，不继续
  T-close acquisition。只有先解决 spec text / frozen identity 决策后，才可重新审计
  eligibility call path。
- independent provenance finding：指定 commit 的 Git blob
  `ashare_watchlist/scripts/screen_system.py` SHA-256 为
  `843935d9b86ec05af848ee8cc54812334475e3d17807cb93349a02c84896417a`，与现有声明
  `6cac746123e315199cbeeb1a612868ef77b50af6c7c64b0d80eb387ae1d19f9` 不一致。根据
  governance contract，不覆盖旧身份，另标记 `PROJECT_GOVERNANCE_STATE_CONFLICT` /
  `UNKNOWN_ORIGIN`，交由 Sol review。
- eligibility：按上述 mandated stop condition，既有 17,714-event artifact 尚未完成
  affected/unaffected call-path audit；状态为
  `EXISTING_B_ELIGIBILITY_ARTIFACT_AFFECTED=UNRESOLVED`。没有把旧 bytes 标记为
  superseded，没有重跑 eligibility，没有生成 corrected artifact。
- live provenance：本地 closure branch rebase 后 HEAD=
  `3d5f3b185f95a8215eed3eb0a88a54e568333acc`，`origin/master`=
  `fc0698c20fb3e7909090cf5073c59d1a2dd710f3`；GitHub open PR=0，PR #18 merge SHA=
  `17371fde39a6b24241532b131caf5927cb9b8933`，merge exact-head run `33476256589`
  success。closure branch push 被安全审查拒绝，故 remote branch protection remains
  `REMOTE_PROTECTION_NOT_ESTABLISHED`；没有使用替代路径外发内部治理/诊断证据。

## 2026-09-01 — B candidate identity/provenance closure

- classification：`correctness blocker` + `product blocker`；本条 closure 不启动新的
  strategy、Phase、参数选择、C、Final OOS、T-close acquisition 或 eligibility replay。
- research question：指定 V0 source identity 是否可在不混淆 Git object、raw file 和
  Windows line-ending hash 的前提下验证；以及 PR #14 的 B spec sector semantics 是否是
  exact V0 reconstruction，还是未授权的 generic hardening inheritance。
- materiality：这两个结论直接决定是否可以使用当前 `B_BREAKOUT_RETEST_LEGACY_V1`
  identity 进入后续 frozen-candidate decision；hash/provenance 或 missing-sector 语义
  错误会污染候选身份，因此是 P0/P1 correctness gate，不是普通 research improvement。
- inputs / stop：只用 V0 commit/path/raw bytes、current repository history、PR #14 tree,
  source tests、nomination/spec/eligibility docs 和已冻结 development manifest/event
  evidence；不读取 Final OOS、不获取新数据、不运行 replay。完成 raw-vs-CRLF identity、
  spec creation lineage、V0-vs-spec matrix、Case A/B/C 判定和 artifact call-path audit
  后停止。
- identity finding / decision：remote `EFSing/ashare_watchlist-V0@c8406c…` 的 exact raw
  file SHA-256 为 `843935d9…`。测试过的 LF-to-CRLF 变体为合法 64 字符值
  `6cac7461…d19f9`，但历史声明值为 63 字符 `6cac7461…d19f9`，二者不相等；
  Git blob OID=`ede1ee…`、object format=`sha1` 是独立 identity。决定：
  `NEEDS_MORE_EVIDENCE`；不改 declared SHA，不修改 B spec hash。
- lineage finding：PR #14 squash commit `4e685ba28668ada29f78e6fa4a56be1cacc259ea` 创建
  `scripts/b_breakout_retest.py:LEGACY_SPEC`，先 `copy.deepcopy(A_LEGACY_SPEC)`，只覆盖
  identity/legacy-source/B-match/B-score/status fields；sector evidence block 来自 A
  generic hardened spec。exact V0 path 明确使用 `("-",50,0.0)` 缺失 fallback 继续评估，
  multi-sector 为 provider-order last-write-wins。没有找到 pre-returns 的 B-specific
  stricter adoption evidence。语义证据指向 Case A，但因 source identity 未解决，最终
  classification 必须保持 `B_CANDIDATE_IDENTITY_UNRESOLVED`，不能宣布 Case A。
- eligibility impact：既有 generator 走不接收 sector 的
  `evaluate_numeric_projection`；parity fixture 只使用 neutral sentinel，score 未输出。
  这些只是待身份解决后的结构性审计输入；按 mandated stop condition，本轮不形成
  impact 结论。因此 `EXISTING_B_ELIGIBILITY_ARTIFACT_AFFECTED=UNRESOLVED`，
  `ELIGIBILITY_ARTIFACT_SEMANTICALLY_INVARIANT=UNRESOLVED`，
  `ELIGIBILITY_ARTIFACT_REGENERATION_REQUIRED=UNRESOLVED`。未把旧 artifact 标记为
  superseded/overwrite，真实 historical sector missing/multi counters 也未填猜测。
- consequence：current B spec SHA、evaluator、live contract、threshold、old artifact、
  Final OOS 和 formal T-close 状态全部保持不变。下一节点是 Sol/user review 决定是否
  授权另一个 versioned semantic repair；在该决策前不得恢复 exact candidate gate。

## 2026-09-01 — authoritative V0 source and corrected B reconstruction

- classification：`correctness blocker` + `product blocker`；本次是既定 correctness
  repair，不是策略优化或重新 nomination。C、Phase 2F、调参、promotion、Final OOS、
  自动 freeze 和 T-close backfill 均不在范围内。
- merge provenance：PR #19 final head=`f99c33993fed00e38e87785a88155034ceaf57c3`，
  squash merge SHA=`28e871552da0813fd51b510a9ef0980976556d29`；post-merge master
  exact-head correctness run=`33491720346` success。PR #19 的历史
  `B_CANDIDATE_IDENTITY_UNRESOLVED` 不改写。
- source decision：`V0_SOURCE_IDENTITY_RESOLVED_AUTHORITATIVE_RAW_GIT_BYTES`。
  authoritative tuple 为 repository `EFSing/ashare_watchlist-V0`、commit
  `c8406c393c0b135eafb0aec763576ae869fddcff`、path
  `ashare_watchlist/scripts/screen_system.py`、raw/LF SHA
  `843935d9b86ec05af848ee8cc54812334475e3d17807cb93349a02c84896417a`。历史合法
  CRLF witness 为 `6cac746123e3151999cbeeb1a612868ef77b50af6c7c64b0d80eb387ae1d19f9`；
  旧 63-character declaration 分类为 `HISTORICAL_SOURCE_SHA_TRANSCRIPTION_ERROR`。
- old identity decision：`B_BREAKOUT_RETEST_LEGACY_V1` / old spec SHA
  `5bbeb345ebd8883149138d2f29f8606f919949ae285aa2839fa337921dfc7112` 保留为历史
  reconstruction 和旧 eligibility bytes，分类为
  `SUPERSEDED_RECONSTRUCTION_WITH_PROVENANCE_AND_SECTOR_SEMANTIC_DEFECT`，不原地
  重写、不冒充 corrected artifact。
- corrected decision：创建 `B_BREAKOUT_RETEST_LEGACY_V1_1`，role 为
  `CORRECTED_EXACT_V0_RECONSTRUCTION`，spec SHA 为
  `f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd`；显式恢复
  exact V0 missing tuple `(-,50,0.0)` continue 与
  `LEGACY_PROVIDER_ORDER_LAST_WRITE_WINS_V1`，保留 raw memberships/provider order，
  不设 score cutoff/TOP-N。semantic decision=`B_CORRECTED_RECONSTRUCTION_SEMANTICS_ADOPTED`。
- eligibility impact decision：`EXISTING_B_ELIGIBILITY_ARTIFACT_AFFECTED=FALSE`，
  `ELIGIBILITY_ARTIFACT_EVENT_SET_INVARIANT`。冻结 development input 为 769 sessions、
  4,041,140 evaluated symbol-dates；old/corrected event count=17,714；projection、
  status、event membership differences=0；sector missing/multi counts 因历史 CORE
  input 不携带 membership 而保持 `NOT_AVAILABLE_IN_FROZEN_DEVELOPMENT_INPUT`。不需要
  correctness returns regeneration，旧 artifact 不覆盖。
- candidate decision：`CORRECTED_B_CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES`。
  future contract 采用 V3；V3 仍是 `CONTRACT_DEFINED_NO_LIVE_INSTANCE`。下一 gate 是
  correctness PR 的 review/merge/CI，然后才可在合法收盘窗口 fresh acquire；不把当前
  diagnostic 作为 prospective evidence。

## 2026-09-02 — PR #20 post-merge governance reconciliation

- classification：`correctness blocker` + `product blocker` follow-up；本次只修复
  merge 后治理 snapshot，不改变策略、spec、阈值、代码、数据、artifact 或历史决策。
- live Git/GitHub state：PR #20 已按 expected head
  `078bc3c083c1b3d309505a10715745b8acd6ef4e` squash merge；merge SHA 与当前
  `master` 均为 `106bfbd00502db56a2e544f1c804a52372c1fa3e`，master exact-head
  correctness run `100101351273` 为 `success`，当前 open PR 为 0。
- governance decision：将此前 section 27 的 pre-merge
  `PR #20 open / waiting user direction` 明确限定为历史时点 snapshot；当前
  authoritative state 为 PR #20 merged，corrected candidate 为
  `B_BREAKOUT_RETEST_LEGACY_V1_1`，decision 为
  `CORRECTED_B_CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES`。
- current product state：Formal Delivery Ladder 仍为 `development candidate`，
  V3 为 `CONTRACT_DEFINED_NO_LIVE_INSTANCE`；当前等待
  `T=2026-09-02` 的合法 XSHG T-close prospective capture。北京时间 15:00 前不运行
  formal `LIVE_OBSERVED` capture，不创建 frozen candidate，不读取 Final OOS，不做
  current-data backfill、promotion、调参或 Phase 2F。
- decision：`PROJECT_GOVERNANCE_STATE_RECONCILED`。本次 follow-up 的变更文件严格
  限定为 `HANDOFF.md`、`docs/CURRENT_STATUS.md` 和 `docs/DECISION_LOG.md`。

## 2026-09-02 — Corrected B/V3 current-state governance reconciliation

- context：`master@614934e7ea98bbe94099e9bf57971cf8454c9713` 后，HANDOFF、CURRENT_STATUS
  和 prerequisite audit 仍有 stale current/active/next-gate wording。
- decision：`PROJECT_GOVERNANCE_STATE_CONFLICT_RESOLVED`；当前统一为 corrected
  `B_BREAKOUT_RETEST_LEGACY_V1_1`、spec SHA
  `f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd`、
  `CANDIDATE_BOUND_PROSPECTIVE_INPUT_PROVENANCE_CONTRACT_V3`、missing-sector fallback
  continue、provider-order last-write-wins，以及唯一当前 blocker
  `P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE`。current next gate 是
  `2026-09-02` legitimate T-close capture。
- boundary：V1/V2、old spec、历史 coverage/ambiguity diagnostic、失败 attempt 和旧
  decision 未改写；last-verified master snapshot 使用上述 master 与 correctness run
  `33584844019` success，不构造 self-referential CI invariant；北京时间 15:00 前不运行
  formal `2026-09-02` acquisition。

## 2026-09-02 — corrected-B/V3 prospective capture provider validation failure

- classification：`correctness blocker` + `product blocker`；任务分类未改变。本次只执行
  首个合法 corrected-B/V3 prospective capture，不进入 C、Phase 2F、Final OOS、调参、
  promotion 或自动 freeze。
- research/product question：在合法 T-close 后，能否形成一个 candidate-bound
  `LIVE_OBSERVED`、`known_at <= T`、可恢复的 corrected-B/V3 input instance。
- materiality：这是从 `development candidate` 进入 frozen-candidate prerequisites 的
  唯一 P1；quote 字段错误若被静默接受会污染 input manifest、B signal 和后续 artifact
  identity，因此必须 fail closed。
- inputs：clean master `a0a0fedeeb38735d661fcaf5d33b114c071b8568`、corrected B/V3
  identity、XSHG calendar、HiThink universe、exact Sina `新浪行业` APIs、Tencent
  quote source；runtime versions 为 Python `3.12.13`、AkShare `1.18.94`、
  exchange-calendars `4.13.2`、pandas `2.2.3`、requests `2.32.3`。
- timing evidence：capture start `2026-09-02T16:10:17.291775+08:00` BJT，session close
  `15:00:00+08:00`，T+1=`2026-09-03`；未使用 `2026-09-01` backfill、future bars 或
  same-bar execution。
- finding：HiThink universe 与 exact Sina sector acquisition 完成；Tencent quote
  snapshot 抛出 `QuoteFieldError`，adapter 以 `PROVIDER_FAILURE` 停止。该错误分类为
  `PROVIDER_DATA_VALIDATION_FAILURE`，`provider_connectivity_failure=false`。异常路径
  未暴露 counts/sector diagnostics，全部保留为 `NOT_RECORDED`/`NOT_AVAILABLE`，不由旧
  snapshot 推断。
- decision：`FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_PROVIDER_FAILURE`。证据见
  [`data/governance/prospective_input_attempt_evidence_20260902.json`](../data/governance/prospective_input_attempt_evidence_20260902.json)，
  `not_a_frozen_artifact=true`。不创建 partial package，不生成 canonical watchlist，
  不执行 Drive upload/recovery，不返回候选表；这是 `NOT_EVALUATED`，不是 zero-candidate。
- consequence：candidate eligibility、strategy/spec、threshold、sector taxonomy、V3
  semantics、Final OOS sealed/unread 状态均不变；未创建任何新 frozen registry record。
  不自动重试；下一次必须重新满足 fresh legitimate T-close capture contract。

## 2026-09-02 — TENCENT_QUOTE_FIELD_ERROR_ROOT_CAUSE_AUDIT

- classification：`correctness blocker` + `product blocker`；这是既定 first prospective
  input gate 的最小 root-cause audit，不是新的 Phase、策略研究、B evaluation、C、
  Final OOS、prospective returns、tuning、promotion 或 package generation。
- research question：第一次 formal Tencent `QuoteFieldError` 是否属于合法无成交/停牌
  representation（A）、malformed/inconsistent provider data（B），或 implementation
  field mapping bug（C）。materiality 是避免把真实 provider failure 当成可交易 quote，
  或为了通过 capture 而错误放宽字段规则。
- inputs / stop：审计了 immutable attempt evidence、task output、当前 Tencent parser、
  `GenerationInputManifest` quote gate 和 corrected B quote consumer；未读取或修改
  `data/validation/continuous_speed_probe/`。停止条件是缺失 exact symbol/batch/raw
  line，不能以猜测补齐。
- finding：formal detail 只有
  `Tencent quote acquisition failed: QuoteFieldError`，历史 diagnostics=`{}`；exact
  symbol、Tencent symbol、field/index、underlying validation message、raw Tencent line
  和 failure batch 都未记录。当前 parser index mapping 仅有 synthetic fixture regression
  证据，不能用来宣布 C；B executable path 实际消费 quote 的数值字段只有 `turnover`，
  但这不构成对缺失/无成交 raw 状态的安全解释。
- probe decision：`CURRENT_ONLY_DIAGNOSTIC_NOT_PROSPECTIVE_EVIDENCE`=`NOT_RUN`。没有
  可合法限定的失败 symbol/batch；不请求猜测股票，不注册 current response，不复用
  payload，不运行 B、不生成 package。
- decision：`NEEDS_MORE_EVIDENCE`。需要 exact six-digit/Tencent symbol、原失败 batch、
  raw line、field/index 和完整 validator message，才可在 A/B/C 中分类；在证据到位前
  保持 parser fail closed，不缩 universe、不跳过股票、不增加 provider/fallback。
- local fix：仅追加 diagnostics improvement：`QuoteFieldError` 保留原 detail，并带上
  six-digit/Tencent batch；`live_acquisition.py` 将 detail 写入 formal message/diagnostics。
  第一次失败 commit/evidence 未改写，`FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_PROVIDER_FAILURE`
  未被宣布最终关闭；未 push、未建 PR、未执行第二次 formal capture。
- full audit record：[`docs/tencent_quote_field_error_root_cause_audit_20260902.md`](../docs/tencent_quote_field_error_root_cause_audit_20260902.md)。

## 2026-09-02 — PR #24 merge and fresh post-merge capture blocker

- classification：`correctness blocker` + `product blocker`；不是策略研究、参数选择、
  Phase 2F、C、Final OOS、prospective returns、promotion 或 automatic freeze。
- merge provenance：在重新断言 PR #24 exact head
  `e97a6a3c525b497f57aac9cfd751b11f86ca9d5c`、base `master@6705624660c8b0432ad038c76c2fc0f3fd2a7948`、
  clean mergeability 和 exact-head correctness success `33615315409` 后完成 squash
  merge；真实 merge SHA 为 `05232677055c67b8b87c8d8c3c3b4139df8c477d`。local
  `master==origin/master==merge SHA`，merge 后 exact-head correctness run
  `33616552822` success。
- input/stop：重新启动唯一的新 `T=2026-09-02` / `T+1=2026-09-03` formal
  `LIVE_OBSERVED` capture。close-window validation 通过；HiThink universe 与 exact
  Sina `新浪行业` 已完成。Tencent quote stage 是 stop condition；不读取、猜测或重试
  后续 inputs，不复用前两次失败 attempt、current-only probe 或 PR regression payload。
- finding：`301686` / `sz301686` 的 Tencent response 在 `p[38]` (`turnover`) 为空，
  触发 `QuoteFieldError`；adapter 返回 `PROVIDER_FAILURE`，分类为
  `PROVIDER_DATA_VALIDATION_FAILURE`，`provider_connectivity_failure=false`。failure
  batch 与完整可得 detail 登记在
  [`data/governance/prospective_input_attempt_evidence_20260902_post_merge.json`](../data/governance/prospective_input_attempt_evidence_20260902_post_merge.json)。
  raw provider line 未被 parser 保留，故不能判断它是否与 `002731` 的已核验合法
  no-trade representation 相同，状态保持 `UNRESOLVED_FOR_301686`。
- decision：`FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_PROVIDER_FAILURE`。不放宽 quote
  validation、不删除/跳过 symbol、不缩 universe、不将此 error 当作合法 no-trade，
  不进入 stock Kline/manifest suspension 语义审计。未创建 READY manifest、package、
  Drive backup/recovery 或 candidate output；Final OOS 保持 sealed/unread。
- consequence：现有两份 2026-09-02 历史失败 evidence 保持 immutable；新增证据不是
  frozen artifact，且未新增 registry record。当前 Delivery Ladder 仍为
  `development candidate`，下一步需等待明确的 correctness/root-cause decision 或
  未来合法 T-close fresh acquisition；本次不自动重试。

## 2026-09-02 — Adopt user non-ST final eligibility

- classification：`product correctness constraint`；不启动新 strategy、strategy version、
  research phase、development returns、调参或 universe acquisition。
- requirement：用户要求最终展示结果不得包含 ST / `*ST` 股票，同时保留完整 live
  universe 与 provider provenance，且不因 ST 跳过 quote/Kline/manifest completeness。
- decision：`ADOPT` — `USER_TRADABILITY_ELIGIBILITY_NON_ST_V1`。在既有 evaluator
  完成后，使用当前 T-close HiThink universe 的 `name` 做 trim + case-insensitive
  prefix detection；`*ST` 或 `ST` 开头为 `INELIGIBLE_ST`，其他名称保留。symbol 仍是
  security identity，不做 fuzzy matching。
- output contract：run manifest 与 `DevelopmentRunResult` 记录
  `b_raw_qualified_count`、`st_excluded_count`、`final_non_st_qualified_count` 和
  symbol/name exclusion list；canonical watchlist 只写 final non-ST candidates，
  不扩充现有 schema。
- boundary：该资格层不是 B alpha filter，不改
  `B_BREAKOUT_RETEST_LEGACY_V1_1` evaluator/spec/threshold/score、历史 development
  evidence 或 performance claim；不影响当前独立 Tencent quote blocker。

## 2026-09-02 — Tradable-universe listing eligibility source decision required

- classification：`correctness blocker`；不是策略研究、参数选择、Phase 2F、C、Final
  OOS、prospective returns、调参、promotion 或正式 capture。
- research question：HiThink `/api/meta/tickers/list` 是否已有 listing date/status
  或等价字段，能够 deterministic 判断 `301686` 在 `as_of_date=2026-09-02` 是否已上市。
  materiality 是避免 pre-listing security 污染 `TRADABLE_UNIVERSE_SCOPE_V1`，同时不
  引入 hard-code、look-ahead、current-data backfill 或第二套 listing engine。
- input / boundary：只对 exact `301686` 做一次 current-only read-only diagnostic，
  标记 `CURRENT_ONLY_DIAGNOSTIC_NOT_PROSPECTIVE_EVIDENCE`；没有写入 formal input、
  package、registry 或 output，也没有读取/修改
  `data/validation/continuous_speed_probe/`。完整 evidence 见
  `docs/tradable_universe_listing_eligibility_audit_20260902.md`。
- finding：HiThink response `code=0`，provider timestamp 为
  `2026-09-02T16:00:18.945+08:00`；exact row 为
  `301686.SZ / 301686 / 中塑股份 / SZ / a-share / CNY`。raw schema 只有
  `thscode`、`ticker`、`name`、`exchange`、`asset_type`、`currency`，没有
  `listing_date/list_date`、listing/security status、`delisting_date`、
  `trading_status`、`market_status` 或等价 as-of eligibility field。
- decision：`NEEDS_MORE_EVIDENCE`，最终 stop 为
  `TRADABLE_UNIVERSE_LISTING_ELIGIBILITY_SOURCE_DECISION_REQUIRED`。任务输入中已确认
  的外部事实支持 root-cause direction
  `PRE_LISTING_SECURITY_INCORRECTLY_INCLUDED_IN_TRADABLE_UNIVERSE`，但 HiThink row
  自身不能 deterministic 证明 `NOT_YET_LISTED`，因此不修改 `_build_universe()`，不
  hard-code `301686`，不按代码新旧/历史 Kline 猜上市状态，不缩 universe、不跳过
  symbol、不放宽 Tencent turnover parser。
- semantic boundary：若后续获得可靠且获批准的 source，已上市停牌 `002731` 必须保留
  在 acquisition universe，而被 deterministic 证明为 T 日未上市的 `301686` 才排除；
  ST 仍只由 B 后的 `USER_TRADABILITY_ELIGIBILITY_NON_ST_V1` final layer 排除。该
  filter 本轮未批准、未实现；正式 capture 未重跑。

## 2026-09-02 — Adopt official exchange listed-roster universe source

- classification：`correctness blocker`；任务分类未改变。本轮仅处理既定
  `TRADABLE_UNIVERSE_LISTING_ELIGIBILITY_SOURCE_DECISION`，不启动策略研究、Phase 2F、
  C、Final OOS、prospective returns、调参、promotion 或 formal capture。
- research question：能否使用一个已批准、可复核且不依赖 hard-code/current-data
  backfill 的 listing source，修复 HiThink broad metadata 把 T 日未上市证券带入
  `TRADABLE_UNIVERSE_SCOPE_V1` 的 correctness 风险？materiality 是在请求 Tencent
  quote/Kline 前确定 acquisition universe 的边界，避免把 pre-listing security 的
  provider failure 当作停牌/无成交语义。
- inputs：Sol source decision
  `USE_EXCHANGE_OFFICIAL_LISTED_ROSTER_VIA_EXISTING_AKSHARE`；当前 AkShare `1.18.94`
  APIs `stock_info_sh_name_code`（`主板A股`、`科创板`）与
  `stock_info_sz_name_code`（`A股列表`）；SSE underlying URL
  `https://www.sse.com.cn/assortment/stock/list/share/`；SZSE underlying URL
  `https://www.szse.cn/market/product/stock/list/index.html`。
- decision：`ADOPT` — `EXCHANGE_OFFICIAL_CURRENT_LISTED_ROSTER_V1`。HiThink
  `/api/meta/tickers/list` remains the broad SH/SZ A-share metadata source; the formal
  prospective universe is its exact six-digit-symbol intersection with the fresh official
  roster. Roster listing dates are canonicalized and must satisfy
  `listing_date <= as_of_date`。
- fail-closed rules：required code/listing-date fields missing or invalid, official roster
  unavailable, or duplicate/conflicting official symbol causes acquisition to stop before
  sector/quote/Kline. There is no HiThink-only fallback, fuzzy name join, hard-coded
  `301686` exception, or second listing engine。
- provenance/output：AkShare version, exact API arguments/URLs, three source row counts,
  canonical combined and eligible counts, deterministic content/semantic SHA-256 values,
  and HiThink-only/roster-only mismatch counts/lists are included in existing provider
  metadata and package provenance；roster identity is included in input and candidate-bound
  generation identity。
- semantic boundary：`301686` is excluded before formal Tencent quote/Kline only when the
  official roster evidence shows it is not eligible by T；already-listed suspended
  `002731` remains in acquisition universe。ST/*ST remains exclusively the post-B
  `USER_TRADABILITY_ELIGIBILITY_NON_ST_V1` final user-facing filter。
- stop condition/result：implementation and focused tests are in the current local branch；
  formal capture was not rerun；Tencent parser and B/spec/threshold/score were not modified。
  After full validation, push one PR, wait for exact-head CI, verify `CLEAN`/`MERGEABLE`, and
  stop at `TRADABLE_UNIVERSE_EXCHANGE_ROSTER_FIX_PR_READY_FOR_USER_MERGE_DECISION` without
  merge。Deferred items remain unchanged。

## 2026-09-02 — Official-roster correction PR ready; stop before merge

- classification：`correctness blocker` follow-up；本次仅同步 post-PR governance state，
  不改变前一条 `ADOPT` decision，也不启动 Phase 2F、C、Final OOS、prospective returns、
  调参、promotion 或 formal capture。
- live result：PR #25 已创建，pre-reconciliation head 为
  `105acc9d9772539a3f799faf90bef14a83f83152`，base 为
  `05232677055c67b8b87c8d8c3c3b4139df8c477d`，pull_request exact-head correctness run
  `33624209979` 为 `success`；PR 为 `open`、`mergeable=true`、`mergeable_state=clean`。
- governance action：追加本 post-PR reconciliation 后，PR head 会变为新的 governance-only
  commit；遵守不把当前 commit 自己产生的 CI 回写到同一 commit 的规则。新 head push 后
  重新实时核验 exact-head CI 和 `CLEAN`/`MERGEABLE`。
- final decision：`TRADABLE_UNIVERSE_EXCHANGE_ROSTER_FIX_PR_READY_FOR_USER_MERGE_DECISION`。
  保持 PR open，merge 由 user 决定；formal Delivery Ladder、当前 Tencent quote/P1
  blocker、Final OOS `SEALED / UNREAD` 和 frozen artifacts 均不变。

## 2026-09-02 — PR #26 merged; stock-Kline suspension semantics correctness fix

- classification：`correctness blocker` follow-up；本轮不新增策略研究，不读取 Final OOS，
  不启动 C、Phase 2F、prospective returns、tuning、promotion 或 auto-freeze。
- governance reconciliation：旧 tracked snapshot 将 PR #25 保留为 open，但实时 PR #25
  已以 squash merge SHA `f0c1fe56972fe1d1d3db99dd51f75ae9b75e1b74` 合并；这是
  `PROJECT_GOVERNANCE_STATE_CONFLICT_RESOLVED`，不改变 formal candidate 或 frozen
  identities。
- merge result：PR #26 的批准 exact head
  `1e736979f394401f5fab2e38caa39408cdc1377b` 未移动，base 为
  `f0c1fe56972fe1d1d3db99dd51f75ae9b75e1b74`，reviews/unresolved threads 为 0，
  exact-head correctness `33645366992` success；真实 squash merge SHA 为
  `7bd620e72daac1c8239daa982e958edab94fd236`，merge-after master correctness
  `33646931153` success。
- formal attempt：在实时 BJT `2026-09-02T23:13:30.5358588+08:00` 后启动 fresh
  `LIVE_OBSERVED` capture，目标 `T=2026-09-02`、`T+1=2026-09-03`；没有复用旧
  attempt/probe/payload/object。失败路径未生成 package、watchlist 或 partial evidence。
- first exact blocker：`INPUT_DATE_MISMATCH`；HiThink 对已上市停牌 `002731.SZ` 返回
  合法非空 330 根历史，最新为 `2026-08-31`；bounded Tencent diagnostic 返回 T 日
  合法 no-trade quote（price/prev_close=`0.77`，open/volume/turnover=`0`）。因此
  root cause 是 stock Kline history/as-of semantics，不是 malformed provider data、
  quote mapping、listing/universe、manifest contract identity 或 B input semantics。
- decision：`ADOPT_MINIMAL_STOCK_KLINE_SUSPENSION_AS_OF_FIX`。stock Kline 允许非空真实
  history 的 `last_bar_date <= T`，仍 fail closed 于空数据、future bar、OHLCV/schema/
  duplicate/coverage failure；index 保持 `last_bar_date == T` 与 market-env minimum
  `21`；B 保持 strategy `B_BREAKOUT_RETEST_LEGACY_V1_1`、role
  `CORRECTED_EXACT_V0_RECONSTRUCTION`、spec SHA
  `f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd`、
  `score_cutoff=None`、`top_n=None`，并自己处理 `<120 -> INSUFFICIENT_DATA`。
- verification：focused tests `94 passed`，full pytest `249 passed`，compileall PASS；
  correctness fix 当前分支为 `codex/stock-kline-suspension-asof-20260902`，后续 stop
  condition 为 `NEW_CORRECTNESS_FIX_PR_READY_FOR_USER_MERGE_DECISION`。未读取、修改或
  上传 `data/validation/continuous_speed_probe/`。

## 2026-09-02 — PR #27 exact-head correctness fix ready

- PR #27 (`https://github.com/EFSing/ashare_watchlist/pull/27`) targets
  `master@7bd620e72daac1c8239daa982e958edab94fd236` with pre-governance head
  `028d6e33b1411b6d0d52188427aaccf988882e07`; it is open/mergeable, reviews are empty,
  and no self-approval was performed.
- pull_request correctness run `33649816076` and push correctness run `33649783681` both
  succeeded at that exact head. This governance-only update advances the PR head, so the
  resulting exact-head CI must be re-verified live and is not claimed by this commit.
- Decision remains `ADOPT_MINIMAL_STOCK_KLINE_SUSPENSION_AS_OF_FIX`: legal non-empty stock
  history may end at `T` or earlier on both primary and explicit Tencent fallback paths;
  future bars and malformed/duplicate/insufficient data still fail closed; index remains
  T-date strict with market-env minimum `21`. No B/spec/threshold/universe/ST rule changed.
- Evidence boundary: full pytest `250 passed`, focused `95 passed`, compileall,
  `git diff --check`, JSON/hash/governance validation PASS. The fresh capture stopped before
  B evaluation/package persistence at the `002731.SZ` blocker; no formal candidate, Drive
  backup/readback, Final OOS, C, Phase 2F, returns, tuning, auto-freeze, or promotion ran.
- Stop after live verification of the new head at
  `NEW_CORRECTNESS_FIX_PR_READY_FOR_USER_MERGE_DECISION`; user decides whether to merge.

## 2026-09-03 — PR #27 narrow no-trade gate and downstream provider audit

- Execution override adopted for the remaining grace window through
  `2026-09-03T08:00:00+08:00`; T remains `2026-09-02`, T+1=`2026-09-03`, and post-midnight
  retrieval timestamps must be recorded honestly. The diagnostic-only chain began with
  `observed_at_bjt=2026-09-02T23:59:52.143765+08:00`; it is not formal evidence.
- PR #27 technical head before this governance-only update was
  `474f1e78f9db856f5cd6813f78479bbe5bb5e317`, based on merged master
  `7bd620e72daac1c8239daa982e958edab94fd236`; push/pull_request correctness runs
  `33651616418`/`33651627289` both succeeded. The governance update advances the head and
  requires new live exact-head verification.
- Decision refinement: ordinary traded securities remain T-date strict. A listed security may
  use its latest real stock bar before T only when its complete canonical Tencent T-date quote
  proves the exact no-trade pattern already defined by `validate_quote`; no synthetic bar,
  forward fill, global stale acceptance, or B change is permitted. Index remains T-date strict
  with market-env minimum `21`.
- Downstream audit: corrected diagnostic-only full chain stopped at `603356.SH` with
  `PROVIDER_FAILURE / ValueError` from HiThink historical acquisition. Three fresh single-symbol
  current-only HiThink reads then succeeded with identical 376-bar complete schemas ending on
  `2026-09-02`; Tencent returned a normal T-date quote with `no_trade=false`. The failed raw
  response was not captured, so the classification is
  `DOWNSTREAM_PROVIDER_FAILURE_NOT_REPRODUCED`; no safe correctness fix is supported and no
  independent provider architecture is bundled into PR #27.
- Verification: focused `104 passed`, full `253 passed`, compileall, diff check, JSON/hash and
  governance validation PASS. No formal package/output, B/ST result, Drive backup/readback or
  frozen-candidate prerequisite result exists; Final OOS remains unread/sealed, and C,
  Phase2F, returns, tuning, auto-freeze and promotion remain not run.
- Stop condition after the new exact-head CI is live success and clean/mergeable:
  `NEW_CORRECTNESS_FIX_PR_READY_FOR_USER_MERGE_DECISION`; user must decide whether to merge.

## 2026-09-03 — Adopt T-close source evidence checkpoints and one-shot runner

- classification：`correctness blocker` follow-up；materiality 是 provider 返回后到解析、
  Kline 遍历或 B 评估之间的任何失败都不能抹掉已取得的 T-close evidence，否则无法
  恢复、审计或证明最终 package 使用的就是同一 source bytes。该修复同时补齐当前
  `development candidate` usable path 的一次性执行入口，但不改变 Delivery Ladder。
- inputs / boundary：已合并 PR #27 的 live master `06ee637d61e7de6df4e0e7145b4ae9e79f40ef49`；
  T 固定为 `2026-09-03`，XSHG session close 为 `15:00 Asia/Shanghai`，calendar-derived
  T+1 为 `2026-09-04`；B strategy 为 `B_BREAKOUT_RETEST_LEGACY_V1_1`，role 为
  `CORRECTED_EXACT_V0_RECONSTRUCTION`，spec SHA 为
  `f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd`。不读取 Final OOS，
  不执行 returns/C/Phase 2F/tuning/promotion，不接触 forbidden probe directory。
- decision：`ADOPT_MINIMAL_T_CLOSE_EVIDENCE_AND_RESUME_PATH`。各 provider source component
  先保存 raw response 或 adapter records，再进入解析/校验；raw/adapter pair 以逻辑
  identity + SHA-256 + sidecar provenance immutable 落盘；transport/data/persistence
  failure 单独保存 failure evidence；成功 checkpoint 可恢复，部分完成结果不删除。
- product execution：采用 `scripts/t_close_runner.py` 的最小顺序
  `T-close evidence → complete GenerationInputPackage → existing B candidate lifecycle`。
  preflight 只验证同一工作目录、Python/依赖、环境凭据、日历和可写根目录，不在收盘前
  发 provider 请求。Windows 一次性任务 `Ashare TClose 20260903` 已注册为 15:05 BJT；
  它不包含 secret 参数，外部 private Drive upload/readback 保持 `NOT_CONFIGURED`。
- verification：focused recovery tests `71 passed`，full pytest `257 passed`，compileall、
  JSON/hash、diff check 通过；PR #28 exact-head `5493786b06e055a1506e0e5d845715da7d4d46ac`
  的 correctness run `33714223690` 成功。此 decision 不构成 formal T-close success、
  B/ST count、canonical output、frozen artifact 或 promotion 结论；这些必须等待任务在
  收盘后真实执行并验证。
- stop / revisit：PR #28 保持 open，停在
  `NEW_CORRECTNESS_FIX_PR_READY_FOR_USER_MERGE_DECISION`，等待 user merge decision；
  scheduled run 成功后再以实际 package/output/evidence SHA 判断是否解除 P1，若失败则
  依据 failure evidence 恢复，不放宽 B 或数据时序规则。

## 2026-09-03 — Adopt minimal retry-response identity fix for T-close recovery

- classification：`correctness blocker` + product-path recovery；研究/策略分类未改变。
  materiality 是已捕获的 T-close source bytes 必须能够在 provider transient failure 后
  继续恢复；若省略该修复，合法的 changed-response retry 会被 immutable persistence
  conflict 阻断，当前 development-candidate usable gate 无法完成。
- live conflict resolution：实时 Git/GitHub truth 已确认 PR #28 squash merge SHA 为
  `43f055e4e8e1a0e1e4a70e41cf8ec10580aab984`，master merge-after correctness run
  `33720355007` success，当前无 open PR #28。此前文档中的 PR-open snapshot 明确
  解决为 `PROJECT_GOVERNANCE_STATE_CONFLICT_RESOLVED`；这不是新的 product、strategy
  或 architecture decision。
- input/evidence boundary：T=`2026-09-03`、T+1=`2026-09-04`、strategy
  `B_BREAKOUT_RETEST_LEGACY_V1_1`、role `CORRECTED_EXACT_V0_RECONSTRUCTION`、spec SHA
  `f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd` 均保持不变。初始
  capture 的 170 个 raw/sidecar pairs 已 SHA verification PASS；既有
  `UNKNOWN_ORIGIN` sidecar、成功 volatile checkpoints 和首次 000008 response bytes
  均未修改。恢复尝试新增一条带 exact resume code SHA 的 000008 transport failure
  evidence；没有 package、manifest、watchlist 或 frozen artifact。
- finding：旧失败 response 与 changed retry response 使用同一 provider request
  identity 时，`TCloseEvidenceStore.capture_raw()` 会 fail closed 为
  `PERSISTENCE_CONFLICT`。该行为会阻断合法 resume，故 decision 为 `ADOPT`：在
  response bytes 改变时使用 `response_sha256` 派生 supplemental logical identity；同一
  bytes 仍复用原 identity，旧 sidecar 不覆盖。B、阈值、score cutoff、Top-N、universe、
  provider/fallback policy 和 T-close semantics 均未改变。
- implementation/validation：PR #29，branch
  `codex/t-close-resume-response-evidence-20260903`，code commit
  `e17d47d372094d58ce191b338c8e0ca3c1dc4feb`，base master 为上述 merge SHA；focused
  live-acquisition/runner `72 passed`，full pytest `258 passed`，compileall、governance
  JSON parse、`git diff --check` PASS；exact-head CI `33736428448` success，PR open and
  clean/mergeable。
- provenance decision：无法从已删除/不可读的 Windows task object、event log 和原始
  `UNKNOWN_ORIGIN` sidecar 严格证明初始 runner 的 clean code SHA，因此不创建 supplemental
  attestation，不把既有 sidecar 回填为 exact SHA，也不宣称 `FULLY_RECOVERABLE` 或 frozen
  prerequisite PASS。后续 retry 只允许在 user merge PR #29 后从 exact master 恢复
  `000008.SZ` 及其后缺失 component。
- final decision/stop：`ADOPT_MINIMAL_T_CLOSE_RESUME_RESPONSE_IDENTITY_FIX`；当前终态为
  `NEW_CORRECTNESS_FIX_PR_READY_FOR_USER_MERGE_DECISION_T_EVIDENCE_SECURED`。不 merge PR
  #29，不重抓已成功 volatile source，不读取 Final OOS，不执行 returns/C/Phase 2F、
  tuning、promotion、auto-freeze，也不接触 forbidden continuous-speed-probe directory。

## 2026-09-03 — Complete T-close recovery and deliver generated watchlist

- classification：原 correctness/product-path blocker 已解除；执行结果不是 research
  tuning，也不构成 strategy promotion。固定的
  `B_BREAKOUT_RETEST_LEGACY_V1_1`、spec、threshold、score、Top-N、universe、sector、ST
  与 fallback policy 均未修改。
- evidence decision：`ADOPT` 以 PR #29 merge 后 exact master
  `af45c8c83cb1a265470bae4693d80cb86708fb76` 继续恢复。最终 10,597/10,597 raw/sidecar
  pairs 为 `SHA_VERIFIED`；170 个历史 `UNKNOWN_ORIGIN` sidecar 原样保留，失败 evidence
  原样保留，不删除 mismatch、重写 provenance 或重抓已成功冻结来源。
- product result：全量 stock/index Klines、market_env、GenerationInputManifest 与 B
  lifecycle 成功完成。package=`READY_FOR_STRATEGY_EVALUATION`；watchlist 生成 0 个
  candidate，B raw qualified=0、final non-ST qualified=0、ST excluded=0；evaluation
  counts=`INSUFFICIENT_DATA:2715, MATCHED_REJECTED:5, NOT_MATCHED:2495`。因此 decision
  为交付空名单，不把空结果误报为失败或策略结论。
- postprocess/frozen decision：private Drive upload/readback 未配置，终态为
  `T_CLOSE_WATCHLIST_GENERATED_POSTPROCESS_BLOCKED`。因历史 code provenance 为
  `UNKNOWN_ORIGIN`，`FULLY_RECOVERABLE` 与
  `FROZEN_CANDIDATE_PREREQUISITES_PASS_READY_FOR_USER_FREEZE_DECISION` 保持
  `NOT_READY / PARTIAL_UNVERIFIED`；该后处理状态不阻止 B 名单计算与用户交付。
- boundary：Final OOS 保持 `SEALED / UNREAD`；C、Phase 2F、returns、tuning、promotion、
  auto-freeze 均 `NOT_RUN`；forbidden continuous-speed-probe directory 未读取或修改。

## 2026-09-03 — Adopt nominated B evaluator binding and controlled invalidation

- classification/materiality：`correctness blocker + product blocker`，研究问题未扩大。
  已确认的 material bug 为 `WRONG_EVALUATOR_WIRING_A_ON_B_PACKAGE`：formal T-close input
  nominated `B_BREAKOUT_RETEST_LEGACY_V1_1`，但 development-candidate generation routed
  it through A evaluator and A output identity. This made the persisted zero-candidate
  result invalid rather than a usable B result.
- input/stop condition：只复用既有 READY package
  `data/prospective_inputs/20260903/2026-09-03_eeb700c98a69a98fae3fa220851190a76de88984b0f451cc1ed275b2e487351f.json`
  with file SHA `a2e6da0865ff20316e4d9074f26e2cb3ba53995d2cb3e83a49f8c82988c0b38a`。停止条件
  是 B ledger 不精确等于 `42/5115/46/12`；实际结果 exact、total `5215`，随后 ST
  eligibility 得到 raw `12`、ST excluded `1`、final non-ST `11`。没有 provider refetch。
- decision：`ADOPT_MINIMAL_NOMINATED_STRATEGY_BINDING_AND_CONTROLLED_SUPERSESSION`。
  新增一个小的 explicit binding（version/spec SHA/qualification/buy label/evaluator），
  A 无 binding caller 保持 backward-compatible default；T-close runner 明确绑定 B。
  package nominated identity 与 binding、以及 evaluator output provenance 不一致时使用
  现有 `OUTPUT_CONFLICT` fail closed，不 publish canonical。B strategy/spec、threshold、
  score、Top-N、universe、sector、Kline/provider 与 ST semantics 均 unchanged。
- historical output decision：旧
  `data/watchlist_20260903.json` SHA
  `ca8cba86527550d7ba10d05083bb1c7523b54ccf8c9ecb34ef10152b8fced1fb`、strategy
  `A_PLATFORM_BREAKOUT_LEGACY_V1`、formal run
  `FFu4MlWYdPwSFrjFJ52Ak2-X2Z0a5-aOWrkdI74Azrc` 与 run manifest SHA
  `7bd047bb57dfb986de0a5bb71a9a44c8cbf5517098a6a2501770199fad34fc11` 已核对。采用一次性
  `INVALIDATED_WRONG_EVALUATOR_A_ON_B_INPUT` controlled supersession；原 bytes 在既有
  invalidated lifecycle 中保留，original run manifest 未修改；corrected B output 才占用
  canonical path。
- evidence/result：corrected local watchlist SHA 为
  `50f0717e55daaf4435e1d25b4f1d029109c566d72d63a1fc566f263cdf0fb085`，run generation
  fingerprint 为 `aae2778d21203098e0cd0d52136ad83fb5dc49b04457b7c51632208972a53c19`。
  12 raw-qualified rows、1 ST exclusion、11 final rows 的完整 actionable fields 以
  `DIAGNOSTIC_B_REPLAY_FROM_FORMAL_20260903_PACKAGE` 返回；不把它宣称为 Final OOS、
  production promotion、auto-freeze 或 external postprocess result。
- PR/verification：PR #30，title=`fix: bind T-close generation to nominated B evaluator`，
  base=`master` at `1639bfeb22e043055a4c30804a0d40e82c94eff5`，code head
  `ac801969653ae49c82b8c6d202fac25d307def68`，exact-head correctness run
  `33760664379` success，GitHub state `CLEAN`/mergeable/open. Focused `18 passed` and full
  pytest `261 passed`; compileall, JSON/hash validation and `git diff --check` passed. The
  governance sync advances the head and requires one new exact-head check before stopping.
- final decision/stop：`ADOPT`；terminal state is
  `B_EVALUATOR_WIRING_FIX_PR_READY_FOR_USER_MERGE_DECISION` once post-governance exact-head
  CI is success. User decides merge. Do not fetch providers, alter B/parameters, read Final
  OOS, run returns/C/Phase 2F/tuning/promotion/auto-freeze, or touch
  `data/validation/continuous_speed_probe/`.

## 2026-09-04 — Adopt merged-master B regeneration and close wiring blocker

- decision：`ADOPT_FINAL_MERGED_MASTER_B_REGENERATION`。用户已授权并完成 PR #30 squash
  merge，actual merge SHA=`9a57c2525c2e621ad568c59940ac2512e575b077`；merge-after
  correctness CI=`33782477205 success`，exact-head verified。该决策只覆盖已确认的
  `WRONG_EVALUATOR_WIRING_A_ON_B_PACKAGE`。
- evidence/stop condition：同一 immutable package SHA
  `a2e6da0865ff20316e4d9074f26e2cb3ba53995d2cb3e83a49f8c82988c0b38a` 在 merged master
  上复用，未重新采集 provider。B ledger 精确为 `42/5115/46/12`，total=`5215`；
  raw=`12`，ST excluded=`1`（`000632 / ST三木`），final non-ST=`11`。因此未触发
  `B_REGENERATION_SEMANTIC_MISMATCH`。
- product output：`USER_TRADABILITY_ELIGIBILITY_NON_ST_V1` 后的
  `data/watchlist_20260903.json` SHA=`50f0717e55daaf4435e1d25b4f1d029109c566d72d63a1fc566f263cdf0fb085`。
  该 development-candidate output 标记为
  `DIAGNOSTIC_B_REPLAY_FROM_FORMAL_20260903_PACKAGE`；没有 Final OOS、promotion、
  auto-freeze 或 external postprocess upload。
- audit preservation：old A output 通过 expected SHA、A identity、formal run
  `FFu4MlWYdPwSFrjFJ52Ak2-X2Z0a5-aOWrkdI74Azrc` 与原 run manifest SHA
  `7bd047bb57dfb986de0a5bb71a9a44c8cbf5517098a6a2501770199fad34fc11` 核验，status 为
  `INVALIDATED_WRONG_EVALUATOR_A_ON_B_INPUT`；原 bytes/run manifest 保留且未改写。
- final state：`T_CLOSE_WATCHLIST_GENERATED_POSTPROCESS_BLOCKED`；
  Drive/readback=`NOT_CONFIGURED_EXTERNAL_UPLOAD`；frozen prerequisite=
  `NOT_READY / PARTIAL_UNVERIFIED`。PR #30 已解决 `WRONG_EVALUATOR_WIRING_A_ON_B_PACKAGE` correctness blocker；
当前 remaining blocker 仅为 external postprocess / Drive-readback，frozen prerequisite
保持 `NOT_READY / PARTIAL_UNVERIFIED`；B strategy/spec/threshold/score/Top-N/universe/
provider/Kline/ST semantics 与 forbidden continuous-speed-probe directory 均未触碰。

## 2026-09-04 — B Phase volume-path diagnostic needs more evidence

- classification/question：`research question`，任务分类未改变。预先定义的问题是：在 corrected `B_BREAKOUT_RETEST_LEGACY_V1_1` 内，breakout、pre-T retest contraction 与 T reactivation 的 volume path 是否显示足够一致的增量关系，值得进入另一轮独立验证。Materiality 是避免在没有稳健证据时改 B，同时不把该研究升级为 current usable-gate blocker。
- inputs/stop：只使用现有 frozen reconstructed retrospective inputs 与既有 exact outcome builder；protocol commit `a182fa77a67cc41c11ce51041ca8af9c67b451ee` 在 outcome relationship 前完成。停止条件是完成 cohort reconciliation、预注册 quantiles/Spearman/5×5/year/board/proxy/episode audits，并从三个允许结论中选一。
- evidence：4,041,140 evaluations、573,586 structural first-breakout rows、17,714/17,714 qualified identities exact matched。Pre-T retest ratio 的 qualified 5D spread=+0.489161pp、rho=0.018258，但 adjacent quantile transitions non-monotonic、structural rho=-0.026749；10D 与 year/board consistency 更弱。Reactivation-vs-retest 的 5D/10D rho=-0.005357/-0.008677，且未通过 matrix/cohort/strata coherence。Repeated-breakout episode share=97.0348%，进一步限制将表面样本量当作独立证据。
- final decision：`VOLUME_PATH_NEEDS_MORE_EVIDENCE`。缺少的是跨年份/板块/结构 cohort 同方向且近似单调的独立验证证据；未来只有一个明确授权的 development validation gate 可以使用它。在此证据缺失时，现有 B、每日 development-candidate path 与外部 postprocess 工作均可继续，不修改规则、不启动 Phase 2F、不 promotion/auto-freeze。
- provenance/boundary：outputs 标记 `DEVELOPMENT / RECONSTRUCTED_RETROSPECTIVE / DIAGNOSTIC_ONLY`。未读取 Final OOS，未 provider refetch/backfill/model fit/threshold search；B spec/score/threshold/hard gate/Top-N/universe/sector/ST/pipeline/frozen bytes 未改变。143+ MB deterministic event detail local-only；tracked summary/report 保存其 exact hashes。一次普通 status 只暴露 forbidden directory 顶层名称，未读取或展开其内容，随后显式排除。

## 2026-09-04 — generated watchlist Drive postprocess/read-back verified

- classification：PR #31 merge 后的继续工作属于 `product blocker + provenance/correctness gate`，不是新的 Volume-Price research。Volume-Price 的最终 decision 仍为 `VOLUME_PATH_NEEDS_MORE_EVIDENCE`，不得据此启动 V2、阈值搜索、模型拟合或 B 语义变更。
- live decision：PR #31 已按用户授权 squash merge，真实 merge SHA=`426b230cdaf53546e5efa4e99cda99c9bcccb85a`；merged head=`1205902f34aa5d057f79a99fdf2c1b2b520e2812`，base=`79da0f527ad72c8e77693d116338ebc8ab74755f`，merge-head CI=`33858481640` success。旧治理段仍写 PR open，构成已被本次 successor snapshot supersede 的 `PROJECT_GOVERNANCE_STATE_CONFLICT`；未发现策略、artifact identity 或历史链异常。
- postprocess decision：用户明确授权后，对 `data/watchlist_20260903.json` 执行了一次 bounded private Drive upload/read-back。Drive file ID=`1N-G0LVvMtotffm5Tdq-2-f4I-fZkuTUq`，size=`6422`；raw read-back SHA=`50f0717e55daaf4435e1d25b4f1d029109c566d72d63a1fc566f263cdf0fb085`，与本地 canonical SHA exact match。因此本次生成 artifact 的 `T_CLOSE_WATCHLIST_GENERATED_POSTPROCESS_BLOCKED` 外部 read-back blocker 结论改为 `RESOLVED_DRIVE_READBACK_SHA_VERIFIED`。未来 runner 的 generic `NOT_CONFIGURED_EXTERNAL_UPLOAD` 仍保留，不宣称自动化集成完成。
- frozen decision：frozen prerequisite 仍为 `NOT_READY / PARTIAL_UNVERIFIED`；170 个历史 sidecar 的 code provenance 仍为 `UNKNOWN_ORIGIN`，所以不声称 `FULLY_RECOVERABLE`，不启动 freeze/promotion/auto-freeze，也不修改 frozen registry 或 frozen bytes。
- boundary：Final OOS 继续 `SEALED / UNREAD`；C、Phase 2F、returns、tuning 未运行。B strategy/spec/threshold/score/hard gate/Top-N/universe/provider/Kline/ST semantics、prospective pipeline 与 Volume-Price outputs 未修改。禁止目录未读取、修改、删除、hash 或上传。
- next gate：提交治理 successor PR，等待其 exact-head CI 全绿与用户 merge 决策；之后若要进入 frozen-candidate freeze，仍需独立且明确授权的 prerequisite decision。

## 2026-09-05 — Turnover x relative-volume diagnostic stopped at acquisition gate

- classification/question：`research question`。独立问题是：在 corrected
  `B_BREAKOUT_RETEST_LEGACY_V1_1` 中，历史 `turnover_rate_pct` 控制 frozen T-day
  relative volume 后是否提供稳定增量信息，并检查固定 5x5 interaction；这不改变 B，
  也不阻止现有 usable development path。
- materiality/input：使用当前 live master=`38322b91f691b23e7ebaa10818a8733169aafab8`、
  frozen daily-K 与 exact corrected-B construction；no-outcome reconciliation 得到
  `4,041,140` evaluations、`573,586` structural rows、`17,714` qualified identities。
  RV 预定义为 `volume_T / mean(volume[T-20:T-1])`。
- decision：`TURNOVER_RATE_ACQUISITION_NOT_RESEARCH_READY`。唯一授权 primary source
  AkShare `1.18.94` / `ak.stock_zh_a_hist` 在 3 次 bounded retry 后连续返回
  `ProxyError / RemoteDisconnected`；checkpoint=`0` completed、`11` failed、`5,375`
  pending of `5,386` requested symbols。未达到 turnover coverage，因此停止，不创建
  pre-outcome protocol，不读取 returns/MFE/MAE，不执行 research decision。审计注：intake 期间仅为
  识别既有 artifact schema 查看过一条 pre-existing event record，未使用任何 outcome 值做计算、筛选或结论。
- consequences：保留 resumable checkpoint、input manifest、summary/report；不引入
  第二 provider、不填补 turnover、不写 raw/canonical dataset、不修改 B/spec/score/
  threshold/hard gates/Top-N/universe/sector/ST/prospective pipeline/frozen registry，
  不读 Final OOS，不运行 C/Phase 2F，不上传 Drive。后续只有重新获得 primary source
  可用性或获得明确 source decision 后，才能从 checkpoint 继续。

## 2026-09-05 — Post-merge primary AkShare resume probe stopped

- merge：PR #33 passed its live pre-merge verification and was squash-merged. merge SHA
  `873169aeecb9eb12d32e58990677f2478f3081c0` equals the refreshed `origin/master`; GitHub
  merge event reported 2 checks passed.
- probe：from the merge-head resume branch, the same primary
  `ak.stock_zh_a_hist` source and fixed parameters were used. A bounded one-attempt probe
  of `000001.sz`, `000002.sz`, and `000006.sz` yielded `0` successes and `3` failures,
  all connection-layer `ProxyError` wrapping `RemoteDisconnected`; no HTTP/provider
  response was received. Non-empty proxy environment names were present:
  `ALL_PROXY`, `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY`.
- state：checkpoint remains `0` completed, `11` failed, `5,375` pending of `5,386`;
  raw/canonical SHA remains `NOT_CREATED`; coverage remains `NOT_EVALUATED`.
- decision：`TURNOVER_PRIMARY_SOURCE_STILL_UNAVAILABLE`。Do not switch provider or alter
  source semantics. Wait for restored primary connectivity or an explicit user/source
  decision. `SCHEMA_SAMPLE_OBSERVED_NOT_USED` remains recorded; no outcome value was used
  in computation/filtering/feature selection/conclusion. No protocol or research decision
  was created.
- boundaries：`VOLUME_PATH_NEEDS_MORE_EVIDENCE`、B、prospective pipeline、frozen registry、
  frozen prerequisite and `Final OOS=SEALED / UNREAD` remain unchanged；C/Phase 2F、freeze、
  promotion、threshold search、model fitting and Drive/upload were not run. Forbidden
  `data/validation/continuous_speed_probe/` was not read, modified, deleted, hashed or uploaded.

## 2026-09-05 — Full subprocess env proxy bypass probe stopped at no-proxy gate

- context：第一阶段 host `NO_PROXY` 后 outer exception 从 `ProxyError` 变为
  `ConnectionError`；第二阶段验证完全移除 proxy env 后 primary source 是否可用。
- probe：在 transient subprocess 内移除 `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY`（含
  lowercase 等价）并设 `NO_PROXY=push2his.eastmoney.com`；AkShare `1.18.94` /
  `ak.stock_zh_a_hist` / daily / unadjusted / 20230630--20260828 参数与三个 fixed
  symbols 不变，每个 1 次。未改系统代理、注册表、持久用户环境变量，未记录 proxy value。
- result：`0/3` success。outer=`ConnectionError`、underlying=`MaxRetryError`、链尾
  `WinError 10013`（direct socket access denied）；无 HTTP status、无 provider response。
- layer distinction：非 `ProxyError` → proxy bypass 已生效且无底层 interception；未到
  response layer → 排除 provider/server 层问题；剩余失败是本机 direct connection 到
  Eastmoney 被 socket 层拒绝。
- decision：`TURNOVER_PRIMARY_SOURCE_UNAVAILABLE_AFTER_NO_PROXY_PROBE`。不切换
  provider、不改 source semantics、不 commit pre-outcome protocol、不进行 outcome
  analysis；等待 direct connection/proxy 恢复或用户明确 source/proxy/credential 决策。
- consequences：checkpoint `0/5,386` completed、`11` failed、`5,375` pending；
  raw/canonical SHA `NOT_CREATED`；coverage `NOT_EVALUATED`；summary/report 已刷新。
  `SCHEMA_SAMPLE_OBSERVED_NOT_USED`、`VOLUME_PATH_NEEDS_MORE_EVIDENCE`、B、
  prospective pipeline、frozen registry、frozen prerequisite、Final OOS 边界均不变。
- next gate：user decision — restore direct connectivity or authorize a
  source/proxy/credential path; second provider, credential, permanent
  network/proxy change, Drive, Final OOS and freeze/promotion remain non-automatic.

## 2026-09-05 — Decision: turnover × relative-volume gateway diagnostic

- classification：`research question`；materiality 是判断 historical
  `turnover_rate_pct` 在 frozen T-day relative volume 条件下是否显示稳定增量
  信息，同时不改 B 或现有 development-candidate 产品路径。
- authorization/source：用户明确授权有界的
  `THIRD_PARTY_TUSHARE_COMPATIBLE_GATEWAY`。固定为
  `https://tuaremax.top`、`tushare==1.4.24`、`daily_basic`，字段为
  `ts_code,trade_date,turnover_rate,float_share`；不是 official Tushare、不是
  `STRICT_PIT_VERIFIED`、不是 production validated。token 仅环境读取，未持久化。
- evidence：五日 pilot coverage=`100%`，固定量纲 sample=`500/500` 通过；769 日
  full acquisition=`769/769` 成功，canonical=`3,938,059` rows。Input audit 保留
  exact `17,714` qualified / `573,586` structural reconciliation；Main/ChiNext/STAR
  in-scope coverage 与各 major year/board 均为 `100%`，无 imputation。
- protocol：正式 pre-outcome protocol commit
  `1148ebd23a567ad81e09b0c2323f9be285920858` 后才读取 outcome。固定 TQ1-TQ5、
  RVQ1-RVQ5、5×5 matrix、conditional summaries、year/board、episode-deduplicated
  和 top-1% sensitivity 均已执行；未 threshold search、parameter sweep、model fit
  或 provider switching。
- result：turnover 5D Q5-Q1 mean spread=`-0.277596pp`，median spread=`-0.969710pp`，
  Spearman rho=`-0.058525`。在 RV 五分位条件下，turnover 5D spreads 为
  `-0.674851/-0.806752/-0.331511/-0.026368/+0.060428pp`，方向不一致；year/board
  coherence 亦未通过。结构/episode/top-1% 的部分方向不能弥补 conditioned
  coherence 缺失。
- decision：`NEEDS_MORE_EVIDENCE`，对应研究终态
  `TURNOVER_X_RELATIVE_VOLUME_NEEDS_MORE_EVIDENCE`。缺少的是跨 RV 条件、年份和
  板块方向一致的独立验证证据；该缺口只限制本研究的进一步结论，不限制现有 B
  development path。
- boundaries：`VOLUME_PATH_NEEDS_MORE_EVIDENCE` 保持不变；B/spec/score/threshold/
  hard gate/Top-N/prospective pipeline/universe/frozen dataset/frozen registry 未改变；
  Final OOS=`SEALED / UNREAD`，C/Phase 2F/freeze/promotion/auto-freeze 未运行。

## 2026-09-05 — PR #34 merged; post-merge governance reconciliation

- live merge：用户明确授权 `AUTHORIZE_SQUASH_MERGE_PR_34` 后，PR #34 在
  exact head=`65d7a8329f012394b9fce6a9aad42f5834dc84e6`、base
  `master@873169aeecb9eb12d32e58990677f2478f3081c0`、exact-head checks 全部
  success 且无 unresolved review threads 的条件下 squash-merged。merge SHA 为
  `2d601360b5160739ec91400175df345f84cd2b95`；live `master` 与
  `origin/master` 均 exact 指向该 SHA。
- merge-head verification：correctness run=`33971522763`，workflow head SHA
  exact 等于 merge SHA，conclusion=`success`。
- research result：PR #34 的 turnover × relative-volume diagnostic 已完成，
  final decision=`TURNOVER_X_RELATIVE_VOLUME_NEEDS_MORE_EVIDENCE`；固定
  pre-registered joint top-1% check 为 turnover N=`171`、RV N=`171`、joint
  intersection N=`11`。该结果不改变 B 或现有 development-candidate 路径。
- protocol/provenance：pre-outcome protocol SHA 未变，仍为
  `1148ebd23a567ad81e09b0c2323f9be285920858`；labels 保持
  `DEVELOPMENT / RECONSTRUCTED_RETROSPECTIVE / DATE_ANCHORED /
  NO_VINTAGE_PROOF / THIRD_PARTY_GATEWAY / DIAGNOSTIC_ONLY`，source 为
  `THIRD_PARTY_TUSHARE_COMPATIBLE_GATEWAY`。
- governance conflict：merge 后重新读取治理文档发现其最新段落仍表达
  PR #34 open/awaiting merge，因此记录 `PROJECT_GOVERNANCE_STATE_CONFLICT`。
  本次一次性 bounded docs-only reconciliation 仅更新治理文档，不改
  research result、protocol、diagnostic summary、scripts、tests、strategy、
  data、frozen registry 或 production pipeline。
- boundaries：B spec/score/threshold/hard gate/Top-N/prospective pipeline/
  universe/frozen dataset/frozen registry unchanged；Final OOS=`SEALED / UNREAD`；
  no C、Phase 2F、promotion、freeze 或 auto-freeze。

## 2026-09-06 — Adopt B observation protocol; defer new-strategy implementation pending selection

- classification：Track A 为 `product infrastructure + correctness/provenance gate`；
  Track B 为 `research question`。Materiality 是让既有 B 在不改规则的情况下形成
  可审计的未来 evidence stream，并把主动研究转为独立、outcome 之前的候选设计选择。
- Track A decision：`ADOPT_B_V1_1_PROSPECTIVE_OBSERVATION_PROTOCOL_V1`。protocol/semantics
  先提交于 `3dd7d51a6341a60540c26db2aa4f18367520d95b`；未来 store 绑定该 SHA，仅接受
  其后代 generation commit，primary cohort 从首个真实 post-commit XSHG T-close signal
  date 开始。固定 `60 sessions AND 200 mature independent episodes`、最大 `120 sessions`，
  不设置盈利提前停止；raw signal、episode dedup、execution feasibility 和 append-only
  outcome state 均保留。
- Track B decision：`DEFER_NEW_STRATEGY_IMPLEMENTATION_PENDING_USER_SELECTION`。在未
  读取 C/任何新候选 forward outcome 的前提下，完成 4-family shortlist 与 qualitative
  design review。推荐 `NEW_CROSS_SECTIONAL_RELATIVE_STRENGTH_LEADERSHIP_V1`，secondary
  `NEW_VOLATILITY_CONTRACTION_BREAKOUT_V1`；C 保留 exact V0 provenance，但未自动 nominate。
- consequences：B/spec/threshold/score/hard gates/Top-N/universe/prospective path、
  `VOLUME_PATH_NEEDS_MORE_EVIDENCE`、`TURNOVER_X_RELATIVE_VOLUME_NEEDS_MORE_EVIDENCE`、
  frozen state 和 Final OOS=`SEALED / UNREAD` unchanged。没有实现候选 evaluator、没有
  threshold/parameter research、没有读取 outcome、没有创建 future observation data。
- next gate：bounded PR exact-head CI 后停在
  `NEW_STRATEGY_CANDIDATE_SELECTION_REQUIRED`。只有用户选择一个 family 后，才创建该
  family 的严格 pre-outcome protocol 与正式 research；不自动启动 B V2、C returns、
  Final OOS、promotion、freeze 或 merge。

## 2026-09-06 — PR #36 exact-head verification and final stop

- live PR：PR #36 open，base=`master@380313c94fdfe388157d5274c4636806d2fa9647`，
  head=`299def1d996994b4a7fffc9997dca73681b4ff4b`，GitHub state=`MERGEABLE/CLEAN`。
  push correctness=`33983380604 success`，pull_request correctness=
  `33983382506 success`；两个 workflow head SHA 均 exact 匹配 PR head。按范围不 merge。
- Track A remains `ADOPT_B_V1_1_PROSPECTIVE_OBSERVATION_PROTOCOL_V1`，pre-outcome
  protocol commit=`3dd7d51a6341a60540c26db2aa4f18367520d95b`；Track B remains
  `DEFER_NEW_STRATEGY_IMPLEMENTATION_PENDING_USER_SELECTION`。
- no-outcome confirmation：未实现 candidate evaluator，未创建 threshold，未读取 C 或
  新候选 forward returns、任何 outcome table 或 Final OOS，未创建 future observation data。
  B、turnover/RV、Volume-Path、frozen state、Final OOS sealed/unread 和受禁目录边界均
  unchanged。
- terminal state：`NEW_STRATEGY_CANDIDATE_SELECTION_REQUIRED`。PR merge、候选实现和
  formal research 必须等待用户下一步选择/授权。

## 2026-09-06 — Adopt epistemic separation for PR #36 new-strategy intake

- classification：`research question` / bounded methodological amendment；materiality
  是防止 future candidate 先形成经济故事、再用 outcome 选择指标或因果语言，同时不
  扩大 B、prospective observation 或 product ladder 范围。
- decision：`ADOPT_FEATURE_EPISTEMIC_SEPARATION`。intake 现在要求分开记录
  `DEFINITION_AND_PROXY_CLAIM`、`PREDICTIVE_EVIDENCE`、`MECHANISM_EVIDENCE`，并在
  outcome access 前满足 alternatives、simple baseline、falsification 与 causal-language
  规则。
- candidate status：四个候选、推荐和 secondary 均不变；本轮只补齐 design-level
  records，全部 predictive status=`UNTESTED`，mechanism status=`HYPOTHESIS`，不因
  returns 改变推荐。
- boundaries：未读取 C/new-candidate forward outcomes、任何 outcome table 或 Final
  OOS；未实现 evaluator、选参数、run replay、改 B 或创建数据。终态待 PR exact-head
  CI 后为 `PR_36_METHODOLOGY_AMENDMENT_READY_FOR_USER_MERGE_DECISION`，不自动 merge。

## 2026-09-06 — PR #36 merge and bounded governance reconciliation

- decision：`ADOPT_PR36_SQUASH_MERGE_AT_EXACT_HEAD`。用户授权的 PR head
  `6d5c99114a94fd6c22565a3257a4f6c634192620` 已 squash-merged，merge SHA 为
  `b21d476c16cf4828073843e578e2ee5a9ef8501b`。
- verification：merge-head correctness run=`33984699289` 为 `success`，且 workflow
  head SHA exact 匹配 merge SHA；live master 已更新并通过验证。
- reconciliation：旧治理快照把 PR #36 写为 open/awaiting merge，现已 bounded docs-only
  修正。这不是新的 research；没有读取 C/new-candidate outcomes、Final OOS 或受禁目录，
  没有修改 B、observation protocol、shortlist 或推荐。
- next gate：保持 `NEW_STRATEGY_CANDIDATE_SELECTION_REQUIRED`；只有用户选择后才
  创建下一策略的正式 pre-outcome protocol，不自动进行 outcome research。

## 2026-09-06 — VCB V1 fixed research decision

- classification：`research question`。Materiality 是检验 pre-breakout volatility
  contraction 在同一 generic breakout baseline 之上的 incremental predictive information，
  而不是把 breakout 自身的收益误归因给 contraction。
- protocol/input：用户选择后先完成 no-outcome audit；corrected semantic protocol commit=
  `411c72b1eff27ecb1ecfb125818837b6aa4a313c`。769 XSHG sessions、4,041,140 PIT identities、
  frozen daily-K/adjustment hashes 和 T-anchor OHLC semantics 通过；历史 per-bar vintage proof
  不存在，保留 `NO_VINTAGE_PROOF`。早期 `177d1b9` 仅因 daily-K SHA transcription typo 被
  corrected protocol supersede，未用于 outcome access。
- signal：固定 10/40 TRP、ratio `<1`、bottom 20%、strict prior-20 high breakout、无 volume
  qualification；generic=`195,464`，candidate=`21,988`，control=`173,476`，both-group active
  dates=`751`，research-readiness PASS。
- outcome：primary 10D date-equal mean spread=`+0.453824pp`，median=`+0.113340pp`，
  block-bootstrap CI=`[-0.381482,+1.349478]`；continuous rho mean=`+0.110340`；5D
  spread=`+0.326237pp`；cooldown mean=`+0.046626pp` with CI crossing zero；year sign
  coherence is 3/4 positive because 2026 is negative。
- decision：`VOLATILITY_CONTRACTION_BREAKOUT_NEEDS_MORE_EVIDENCE`。Positive point estimate and
  positive continuous rho do not satisfy the fixed support rule because primary and cooldown
  uncertainty intervals cross zero. No parameter tuning, volume/turnover/RV addition, board-only
  selection, provider replacement or automatic follow-up is allowed。
- governance：B/B prospective、RS、Volume-Path、turnover/RV、frozen state unchanged；C、
  controlled reversal、Final OOS=`SEALED / UNREAD` 和 forbidden directory untouched。Focused
  tests=`13 passed`，full pytest=`315 passed` under pinned venv/short basetemp，compileall、
  JSON/hash/schema and diff checks PASS。
- next gate：independent research PR exact-head CI；terminal state
  `VCB_RESEARCH_PR_READY_FOR_USER_MERGE_DECISION`，不自动 merge。

## 2026-09-06 — PR #38 squash merge and post-merge verification

- authorization：用户要求仅在 live PR head 精确为
  `2d5d61f319a2a1af84bbd58c2997ca3b07218e8e` 时 squash-merge；实时检查满足该条件，PR #38
  为 `OPEN / MERGEABLE / CLEAN`，随后执行 squash merge。
- merge identity：canonical master merge SHA 为
  `0571d57d5741faa689922c9f3a7d5c73c04772fb`。master correctness run=`34024991541`，
  `success`，workflow head SHA exact-matched该 merge SHA。
- reconciliation：只更新 `HANDOFF.md`、`docs/CURRENT_STATUS.md`、`docs/DECISION_LOG.md`
  的 stale PR #38 governance state；没有修改 VCB research decision、protocol、artifact、
  B、RS、frozen state 或 production semantics。
- stop：不启动另一 candidate，不读取 Final OOS，不调参、不 promotion、不 freeze；终态为
  `VCB_RESEARCH_MERGED_MASTER_VERIFIED`。

## 2026-09-06 — CRSR V1 fixed research decision

- classification：`research question`。Materiality 是回答在 fixed downside-extreme state
  与 positive-bounce baseline 之上，严格 prior-5-close right-side reclaim 是否仍提供
  incremental predictive information；primary identification 预先控制 T-day bounce magnitude。
- identity/boundary：用户选择 `NEW_CONTROLLED_RIGHT_SIDE_REVERSAL_V1`，这是
  `NEW_RESEARCH_HYPOTHESIS`，不是 old D 恢复、重建或替代；不得读取 old D 名单、sample、
  outcomes 或 predictive provenance。pre-outcome protocol commit=
  `123ef5299ef94411a0b1cb4ec5745ee2c472979e`，commit 后才访问 CRSR DEVELOPMENT outcomes。
- input：769 continuous XSHG sessions、4,041,140 date-symbol PIT identities；identity SHA=
  `dbc5d220f24f51a0245d047b88733c961fc4f184d02ef6f5ac0fc795576217b0`；daily-K SHA=
  `61189a4850e2eb157453e28e5375e502e20d214508bbe70ea71066ca3e05e426`；adjustment SHA=
  `a1b7d63c5826ccd3610dc9bdd949d82eeb0ba84ffad451bfb8bb30ca74962716`；signal price 为
  `HISTORICAL_T_ANCHOR_PRICE_RAW_VOLUME`；per-bar vintage proof 不存在，保留 `NO_VINTAGE_PROOF`。
- signal：T-1 `R20_PRE=close_T-1/close_T-21-1`，same-date ascending bottom-20% rank with
  symbol tie-break and absolute `<0`；T-day strict positive bounce；strict close above prior
  five-session close high；candidate=`121,698`，primary control=`250,506`，baseline=`372,204`；
  shared-bounce-bin dates=`765`；readiness gate PASS。没有 RSI/MACD/KDJ/MA/Bollinger、volume、
  turnover、RV、sector、B、VCB、RS 或 ML qualification。
- outcome：signal=T close；reference=T+1 XSHG open，`REFERENCE_EXECUTION_NOT_ACTUAL_FILL`；
  DEVELOPMENT adjusted outcome convention；candidate/control usable 10D coverage=`98.31%` /
  `98.15%`，coverage gate PASS。Primary stratified 10D mean=`-0.079350pp`，median=`-0.232037pp`，
  95% 20-session moving-block CI=`[-0.495382,+0.403562]`，positive-spread date rate=`44.90%`；
  raw unstratified spread=`-0.233054pp`；5D stratified mean=`-0.155740pp`。
- robustness：continuous reclaim-margin rho mean=`-0.025847`，positive-rho date rate=`42.14%`；
  non-downside generic reclaim spread=`-0.084147pp`，context interaction mean=`-0.023253`；
  cooldown retained candidate/control=`22,176`/`89,553`，10D mean=`+0.047685pp`，CI crosses zero；
  year primary signs are 2023 negative、2024 negative、2025 negative、2026 positive；boards、
  prior-R20、prior realized-volatility、amount、symbol/month concentration、best/worst dates 和
  post-stratification T-day balance 均保存于 summary/report。
- decision：`CONTROLLED_RIGHT_SIDE_REVERSAL_NO_CLEAR_INCREMENTAL_SIGNAL`。因为 primary mean
  `<=0` 且 continuous rho `<=0`；同时 primary CI crosses zero。不能保留“right-side reclaim
  provides incremental predictive value”作为当前 fixed evidence 结论；不得自动加指标、调窗口、
  切板块、改 horizon、重开 old D 或启动下一 candidate。该 decision 是固定 research decision，
  不是 production strategy rejection 或对其他策略的结论。
- artifacts/verification：signal detail `4,041,140` rows，SHA=
  `267995e9098c67759fe6ab401e8f1abedbca4bba452df187b7c36b715be8e203`；outcome detail local-only
  `1,935,412` rows，SHA=`e64fc9543e0bb01ccd9454c1a52d42306ae8d0613e93254ca05c0047c21ba3ca`；focused
  tests=`15 passed`，full pytest=`330 passed`，compileall、JSON/schema/hash、diff checks PASS。
- governance/stop：B/B prospective、RS、VCB、Volume-Path、turnover/RV、frozen state unchanged；
  C unread；Final OOS=`SEALED / UNREAD`；forbidden directory untouched；没有 provider change、
  parameter tuning、promotion、freeze 或 production path change。下一 gate 是 independent PR
  exact-head CI；终态为 `CRSR_RESEARCH_PR_READY_FOR_USER_MERGE_DECISION`。

## 2026-09-06 — CRSR V1 PR exact-head CI verification

- delivery：独立 PR #39 `research: controlled right-side reversal V1` 已创建；base=
  `36f8120651e8f6a0d66e1d97769dc7c6d8a66e7b`，head=`58832ac4b8deeb23e28a165232656d0567df9d81`。
- verification：push correctness run=`34030857382` 与 pull-request correctness run=
  `34030876254` 均 `success`，workflow head SHA exact-match PR head；GitHub PR state=`OPEN / CLEAN`。
- authorization boundary：不自动 merge。研究 fixed decision、B/RS/VCB/frozen state、
  production semantics、Final OOS=`SEALED / UNREAD` 与 forbidden-directory boundary 均不变。
- stop：`CRSR_RESEARCH_PR_READY_FOR_USER_MERGE_DECISION`，等待用户 merge decision；任何
  后续 head 变化都必须重新通过 exact-head CI。

## 2026-09-06 — Final workstation resume closure

- verification：PR #39 merge SHA=`1fdb099926a1172cfebee7001537910d805019e4`，merge-head
  correctness=`34031658818 success`；bounded governance reconciliation commit=
  `dd491382c5c8d5bfb07ec844ec116ece56afa526`，governance-head correctness=
  `34034984771 success`，workflow head exact；master/origin/master exact，open PR=0，tracked
  working tree clean。
- recovery：Drive project root remains private; operational watchlist readback exact，daily_k
  existing registry recovery valid；RS/VCB/CRSR research detail archive exact readback verified。
  Volume-Path missing local-only detail is an audit gap only, not a daily-operation blocker；no
  turnover/RV archive was created without manifest-confirmed raw/full bytes。
- clean clone：exact final handoff snapshot cloned from GitHub，pinned dependencies installed，
  compileall PASS，focused tests `12 passed`；historical 2026-09-03 watchlist restored outside
  clone and read-only schema/provenance/revision/hash review PASS；no-secret T-close preflight
  failed closed without provider calls；research archive not required at daily startup。
- decision：`DAILY_WORK_COMPUTER_RESUME_READY=YES` and
  `CURRENT_HOME_COMPUTER_NO_LONGER_SINGLE_POINT_OF_FAILURE=YES`。`ACTIVE_NEW_STRATEGY_RESEARCH=
  NONE` / `PAUSED / PHASE_COMPLETE`，Final OOS=`SEALED / UNREAD`，C unread，old D not
  reconstructed；no new strategy/tuning/promotion/freeze/production semantic change；forbidden
  directory untouched。
- terminal marker：`A_SHARE_RESEARCH_PHASE_CLOSED_WORKSTATION_RESUME_READY`；本轮停止。

## 2026-09-06 — PR #39 final merge and post-merge durability governance

- classification：`product infrastructure + correctness/provenance + recovery`；不是新的
  research。用户授权的 PR #39 exact head 为
  `fdb4640fb8556f7ce86c1d8d1feb7ceb41f9e822`，merge 前 push correctness
  `34030990704`、pull-request correctness `34030992465` 均为 `success` 且 head exact。
- merge：PR #39 squash merge 后的 `CRSR_MERGE_SHA` 为
  `1fdb099926a1172cfebee7001537910d805019e4`；master merge-head correctness run
  `34031658818` 为 `success`，workflow head SHA exact 匹配 merge SHA。
- reconciliation：旧 handoff/status/log 中的 `PR #39 open`、`awaiting merge` 和
  `CRSR_RESEARCH_PR_READY_FOR_USER_MERGE_DECISION` 只作为历史记录保留；当前语义已改为
  `PR_39_MERGED_AND_VERIFIED`。本次只更新治理文档并加入
  `data/governance/workstation_durability_manifest.json`，不改 CRSR fixed decision、B、
  RS、VCB、Volume-Path、turnover/RV、frozen state 或 production semantics。
- fixed decision：`CONTROLLED_RIGHT_SIDE_REVERSAL_NO_CLEAR_INCREMENTAL_SIGNAL`；它仍是
  independent DEVELOPMENT research result，不是 production rejection、freeze 或 Final OOS。
- Drive：项目根 `ashare_watchlist` ID=`13_-tlozdfe1KEtNSMxp6pCroI893g_qH` 保持私有；已
  fresh-readback `watchlist_20260903.json` SHA=`50f0717e55daaf4435e1d25b4f1d029109c566d72d63a1fc566f263cdf0fb085`。
  `daily_k.parquet` registry 仍为 `FULLY_RECOVERABLE`，现有 recovery evidence 有效，
  `NO_REUPLOAD_REQUIRED`。
- durability：Git 已保存 canonical operational files；RS、VCB、CRSR detail 以 manifest
  exact SHA 归档并逐片 readback verified。Volume-Path canonical event detail 不存在，记录
  `LOCAL_ONLY_ARTIFACT_MISSING`；turnover/RV 没有 manifest-confirmed raw/full acquisition
  bytes，未归档。未创建 fake B prospective data。
- environment/boundary：live B 所需环境变量名仅为 `HITHINK_FINANCE_API_KEY`，可选数据根
  override 为 `ASHARE_DATA_ROOT`；不记录值。Final OOS=`SEALED / UNREAD`，C unread，old D
  not reconstructed，`ACTIVE_NEW_STRATEGY_RESEARCH=NONE`；forbidden directory untouched。
- next：push this bounded governance reconciliation，等待 governance-head correctness，
  再执行 clean clone + minimum restore dry run；不自动开启新策略、调参、promotion、freeze
  或读取 Final OOS。

## 2026-09-07 — Adopt first candidate-bound V3 input instance; retain frozen recovery gate

- classification：`correctness/provenance + product-gate audit`；不是新的 research、strategy
  selection、Phase 2F、promotion 或 freeze。
- question：分别判断 (A) 首个真实 candidate-bound、`LIVE_OBSERVED`、`known_at <= T` 的
  V3 T-close input instance 是否已经存在，以及 (B) 该 package 是否已满足 frozen
  prerequisite 所需的 `FULLY_RECOVERABLE` provenance。A 与 B 不合并判断。
- evidence：2026-09-03 package schema=`CANDIDATE_BOUND_LIVE_INPUT_PACKAGE_V4`，file SHA=
  `a2e6da0865ff20316e4d9074f26e2cb3ba53995d2cb3e83a49f8c82988c0b38a`，content SHA=
  `0b1216e5c5855343dba02853eb17e9dbc43c97d50120ac7490da43eaa78cdf86`，generation
  fingerprint=`eeb700c98a69a98fae3fa220851190a76de88984b0f451cc1ed275b2e487351f`。T=
  `2026-09-03`，retrieved=`2026-09-03T18:18:51.506757+08:00`，after XSHG close，earliest
  execution=`2026-09-04`；candidate binding 为 `B_BREAKOUT_RETEST_LEGACY_V1_1` 与 spec
  SHA=`f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd`。Universe、quote、
  stock/index Kline、sector、symbol identity、generation manifest checks 均 `PASS`。
- output evidence：corrected B run=`quJ3jSEgMJjgzQ1SE2rYP7XcSbBEV7fFFjIgiXKlPBk`，run
  manifest SHA=`865eeba45974e70ff70b67b1e8422c5e36e65010d5aebb521d7b01ac197d1445`，raw
  qualified=`12`，post-B ST exclusion=`1`，canonical candidate count=`11`，watchlist SHA=
  `50f0717e55daaf4435e1d25b4f1d029109c566d72d63a1fc566f263cdf0fb085`。All 10,597
  raw/sidecar pairs passed missing/hash/byte-length/JSON checks.
- decision A：`ADOPT`。旧 `P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE` 仅针对“首个
  实例不存在”，现为 stale/closed；170 `UNKNOWN_ORIGIN` sidecars 不否定 A，因为它们是
  provenance completeness gap，而非 live/timing/binding/schema failure。
- decision B：`NEEDS_MORE_EVIDENCE`。170 个 sidecar 仍无法提供 exact runner code origin；
  且经核验的 Drive readback 只有 6,422-byte watchlist，没有 candidate-bound package 或
  raw/sidecar archive，故不能声称 `PERSISTENT_BACKUP_PRESENT` / `FULLY_RECOVERABLE`。
  缺少的 evidence 是 known-origin formal package provenance 与 persistent package
  recovery/readback，或一个经明确授权的 post-close fully-attested fresh capture；不得用
  retroactive attestation、回填、重贴 hash 或文档修改伪造。
- boundary：B strategy/spec/threshold/score/Top-N/universe、evaluator、Final OOS、C、old D、
  frozen bytes/registry 与 `data/validation/continuous_speed_probe/` 均未读取或修改；
  2026-09-07 仅执行 pre-close diagnostic，provider calls=`NOT_RUN_BEFORE_T_CLOSE`。
- terminal：`BLOCKED_REQUIRES_USER_OR_EXTERNAL_DECISION:FROZEN_RECOVERY_PROVENANCE_PARTIAL_UNVERIFIED`。

## 2026-09-07 — Resolve HiThink transient HTTP gap; adopt fresh T-close package for user freeze decision

- classification：`correctness/provenance + product-gate audit`；不是新的 research、strategy
  selection、promotion、Phase 2F 或 freeze。
- diagnosis：已持久化 evidence 足以确定 `000002.SZ` HiThink historical 请求返回 HTTP
  `429`，endpoint=`/api/a-share/prices/historical`，request identity=
  `thscode=000002.SZ&interval=1d&start=1740355200000&end=1788739200000&adjust=forward`，
  收到 64 response bytes，脱敏 body 为 `{"code":429,"message":"request limit exceeded","data":null}`。
  该请求不因诊断重复访问 provider。
- correctness fix：旧 HiThink transient classifier 漏掉 408/429/5xx；在 bounded branch
  `codex/hithink-http-transient-20260907` 的 code SHA
  `39cbd7cf2335ebee1cc7a81faee47c744c737fc3` 中以共享 helper 覆盖这些 status，普通 4xx
  仍 non-transient。max attempts=3、priority/backoff、Tencent fallback、B semantics 与
  strategy thresholds 未变；focused tests、必要 full suite、compile/import、diff check 均
  按本轮 audit 记录完成。
- fresh evidence：旧 `data/t_close_evidence/20260907` partial attempt 原样保留；新 clean
  root 为 `data/t_close_evidence/20260907_clean_39cbd7cf2335ebee1cc7a81faee47c744c737fc3/20260907`，
  10,677 pairs / 21,354 files 全部 complete、byte/hash exact，runner SHA 统一且新
  `UNKNOWN_ORIGIN=0`。package file SHA=
  `63fa8effea45cc329035dd97dbe64dfe9d84e899fbb24623190143811e08cc3a`，generation
  fingerprint=`fe54be9be5c5959bd3d690adab2423e7a89f19e4498fb1df927c142f8dab9e4c`。
- output：B `B_BREAKOUT_RETEST_LEGACY_V1_1` raw qualified=26，ST excluded=1，final
  non-ST=25；watchlist SHA=`5a99273b6304621acbf7bba2423a6e372668348a31ac436021caf5f5855db100`。
- recovery：用户已明确授权私有 Drive target
  `ashare_watchlist/t_close_20260907_v3_39cbd7cf`。formal inventory 为 14 package chunks、
  15 source-evidence chunks 与 1 chunks40 manifest；29 binary objects 和 manifest 均独立
  raw-readback 并 exact-matched inventory、byte length、SHA-256。
- decision：`ADOPT` fresh package；frozen prerequisite recovery checks 为
  `PASS / READY_FOR_USER_DECISION`。不自动 freeze；Final OOS/C/old D 与 forbidden
  continuous-speed-probe boundary 保持不变。
- terminal：`FROZEN_CANDIDATE_READY_FOR_USER_DECISION`。

## 2026-09-07 — Freeze B candidate; adopt the formal review report project boundary

- classification：`product governance + correctness/provenance reconciliation`；不是新的
  research、promotion、production approval、Final OOS unseal、C/D 评估或 B 语义变更。
- post-merge truth：PR #41 已合并到 `master`，merge SHA=
  `3308c7ab8e403d459baf1bbfe873e7320d750317`；post-merge correctness run
  `34133269448=completed / success` 且 head exact。Formal Delivery Ladder 当前为
  `frozen candidate`，B `B_BREAKOUT_RETEST_LEGACY_V1_1` 已冻结；无当前 freeze blocker。
- identity：冻结对象的 spec SHA=`f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd`，
  formal capture code SHA=`39cbd7cf2335ebee1cc7a81faee47c744c737fc3`，package SHA=
  `63fa8effea45cc329035dd97dbe64dfe9d84e899fbb24623190143811e08cc3a`，generation
  fingerprint=`fe54be9be5c5959bd3d690adab2423e7a89f19e4498fb1df927c142f8dab9e4c`，watchlist
  SHA=`5a99273b6304621acbf7bba2423a6e372668348a31ac436021caf5f5855db100`。
- recovery：私有 Drive target
  `ashare_watchlist/t_close_20260907_v3_39cbd7cf` 的 manifest identity 与此前 exact
  inventory/readback 均为 `PASS`；本次未重传、未全量 readback、未修改 package/source/
  watchlist bytes。Final OOS=`SEALED / UNREAD`，C 未读，old D 未重建，forbidden directory
  未触碰。
- review boundary decision：`ADOPT` 当前 A 股 prospective watchlist 的正式复盘边界。
  每交易日由 `review_after.py` 记录 current-day lightweight status；
  `eod_review.py` 仅保留兼容入口；signal-level `track_perf.py` 使用真实 XSHG sessions
  记录 T+3 short-term、T+5 primary、T+10 extension/closure。path result 与 fixed-horizon
  snapshot 分离，提前 target/stop、same-bar ambiguity 和缺失 historical observation
  均 fail-safe；不 fabricated replay，不回写历史 B 10D outcome。
- scope：用户可见正式报告不再默认渲染旧持仓、pairs、旧 market grading/rotation 或旧调度
  话术；底层 legacy modules 不因本次边界清理被盲目删除。B identity、Final OOS、C、old D
  和 strategy semantics 均不变。
- terminal：freeze 已在 master verified；review cleanup bounded PR #42 已创建并等待用户
  merge decision，不自动 merge。

## 2026-09-07 — Adopt the formal review report project boundary

- classification：`product infrastructure + correctness`；不是新的 research、strategy
  selection、参数调整、promotion 或 frozen-candidate 语义变更。
- problem：当前用户可见复盘输出仍包含未被当前 A 股系统正式重新采纳的旧持仓模板、配对
  指标段落和固定 14:45/09:25 调度话术；tracker 只有一个 10D 到期路径，不能表达正式的
  多节点复盘口径。
- decision：`ADOPT` 四层正式复盘制度：每交易日由 `review_after.py` 生成 canonical
  watchlist 轻量状态；由 signal-level `track_perf.py` 按信号日 T 后真实 XSHG session
  记录 T+3 短线评价、T+5 主评价、T+10 延伸观察并结案。`eod_review.py` 仅保留为每日
  轻量状态的兼容入口。
- correctness boundary：节点使用 XSHG 交易日历，不按自然日；每个
  `signal_id × horizon × review_trading_date` 使用 deterministic、可重复的 snapshot
  identity；fixed-horizon observation/return 与 execution/path result 分离。提前 target/stop
  的真实 terminal 状态和结案日不被覆盖，后续固定节点仍可记录 snapshot；错过节点不做
  历史行情回填；same-bar ambiguity 继续 fail-safe。既有历史 research 的 10D outcome 不被
  回写或重新定义。
- scope：报告不再消费旧持仓/配对指标流程；B、frozen candidate、Final OOS、C、old D
  和 `data/validation/continuous_speed_probe/` 均不触碰。

## 2026-09-08 — Reconcile governance and add daily close bundle HTML

- live truth：`master=52484a82e4a2700372c85c47991f62717d4b1196`；PR #41 与 review-cleanup
  PR #42 均已合并；post-merge correctness run `34140697889` 为 `completed / success` 且
  exact-head。旧的 PR #42 open/awaiting-merge snapshot 仅为 stale governance metadata，现已
  由 `HANDOFF.md` 与本状态记录最小纠正；不重写历史 checkpoint。
- decision：`ADOPT_DAILY_CLOSE_BUNDLE_HTML_REPORT`。独立 renderer 读取 canonical
  watchlist 与 `track_perf.py` tracker，输出 self-contained dated HTML 与完整的
  `latest.html`；T+3/T+5/T+10 继续使用真实 XSHG sessions，path result 与 fixed-horizon
  snapshot 分离，review failure fail-soft，HTML 写入 atomic。
- boundary：不修改 B strategy semantics、阈值、score、target、ST、provider、acquisition、
  package schema、frozen identity 或历史 B 10D outcome；不读 Final OOS/C/old D，不做历史 replay，
  不访问 `data/validation/continuous_speed_probe/`。daily HTML 是 operational generated
  artifact，不作为每日 Git source commit 内容。
- delivery：bounded PR #43 is open against `master`; implementation commit
  `9162c0ef73ad07adc7533b85e0b78248c539b6ff` and its governance-only follow-up are pushed.
  Exact-head CI is a live property and must be re-read for the current remote head. Stop at the
  user merge decision; do not auto-merge.


## 2026-09-08 — Current prospective review epoch and canonical continuity

ADOPT: current prospective ingest/review starts at `2026-09-03`, the first verified
candidate-bound LIVE_OBSERVED instance, and requires exact strategy
`B_BREAKOUT_RETEST_LEGACY_V1_1` plus schema-valid canonical identity. Pre-epoch or
other-strategy artifacts are skipped, not deleted or silently re-adopted. Existing
out-of-scope tracker records are removed only after a deterministic KEEP/REMOVE plan;
KEEP identities must match canonical evidence and retain their observation/path state.
Identity conflicts fail closed; code alone is never a deduplication key. Missing historical
observations remain missing. Any future legacy re-adoption requires a separate formal decision.
