# CURRENT STATUS

更新时间：2026-09-07（Asia/Shanghai）
Formal Delivery Ladder：`frozen candidate`
Live `master@3308c7ab8e403d459baf1bbfe873e7320d750317`；PR #41 已合并。post-merge
correctness run `34133269448` 为 `completed / success` 且 head exact。
Phase 2E research baseline：PR #6 / `74ccf86dfdea3b9d4b0124fb54346aa429735508`
职责：记录项目正式处于什么状态，以及哪些研究结论已经成立。长期产品目标和 usable gate 见 [`PRODUCT_CHARTER.md`](PRODUCT_CHARTER.md)，接手动作见 [`HANDOFF.md`](../HANDOFF.md)，决策理由见 [`DECISION_LOG.md`](DECISION_LOG.md)。

## Current checkpoint — post-merge frozen candidate and review cleanup — 2026-09-07

PR #41 已在 live `master` 合并为 `3308c7ab8e403d459baf1bbfe873e7320d750317`，post-merge
correctness run `34133269448` 为 `completed / success` 且 head exact。Formal Delivery Ladder
当前为 `frozen candidate`；B `B_BREAKOUT_RETEST_LEGACY_V1_1` 已冻结。该 freeze 只绑定
candidate 规则和 formal identity，不表示 promotion、production approval 或 Final OOS unseal。

- spec SHA-256：`f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd`
- formal capture code SHA：`39cbd7cf2335ebee1cc7a81faee47c744c737fc3`
- package SHA-256：`63fa8effea45cc329035dd97dbe64dfe9d84e899fbb24623190143811e08cc3a`
- generation fingerprint：`fe54be9be5c5959bd3d690adab2423e7a89f19e4498fb1df927c142f8dab9e4c`
- watchlist SHA-256：`5a99273b6304621acbf7bba2423a6e372668348a31ac436021caf5f5855db100`
- B output：raw qualified=26，ST excluded=1，final non-ST=25

The authorized private Drive target remains
`ashare_watchlist/t_close_20260907_v3_39cbd7cf`; its manifest identity and prior exact
inventory/readback are `PASS`. Package/source/watchlist bytes were not changed. Recovery truth
remains the remote recovery branch, with runtime verification requiring
`git rev-parse HEAD == git rev-parse @{u}`. Final OOS remains `SEALED / UNREAD`, C remains
unread, old D is not reconstructed, and `data/validation/continuous_speed_probe/` remains
untouched. There is no current freeze blocker.

本次独立 bounded review cleanup 叠加在 frozen candidate 之上，只处理当前 A 股 prospective
watchlist 的用户可见复盘边界与评价节奏。`review_after.py` 是 current-day lightweight status
review；`eod_review.py` 仅为兼容入口；signal-level `track_perf.py` 负责 T+3/T+5/T+10
正式跨日复盘。节点使用真实 XSHG trading sessions，T+5 是 primary horizon；path result
与 fixed-horizon snapshot 分离，提前 target/stop、same-bar ambiguity 和缺失 historical
observation 均保持 fail-safe，不做 fabricated replay，也不回写历史 B 10D outcome。

当前 review cleanup 仍需在该 branch 上完成 focused verification、push 和独立 bounded PR；
本段不改变已冻结 B identity、Final OOS 或 C/D 边界。

## Superseding current checkpoint — formal review report boundary cleanup — 2026-09-07

本次独立 bounded task 只处理复盘用户可见输出与既定评价节奏，不改变 B、frozen
candidate、Final OOS、C、历史 research outcome 或任何策略语义。`review_after.py` 现在只
生成每个真实 XSHG 交易日的 canonical watchlist 轻量状态；`eod_review.py` 仅保留为该
入口的兼容调用，不再生成独立的旧持仓/大盘/配对报告。正式跨日绩效由
`track_perf.py` 的 signal-level tracker 维护，不消费旧持仓模板或配对指标流程。

每个 signal 以信号日 T 后第 3 个真实 XSHG session 记录 T+3 短线评价，第 5 个 session
记录 T+5 主评价，第 10 个 session 做 T+10 延伸观察并结案；节点不按自然日计算。信号
若提前触发 target/stop，真实 terminal 状态与结案日保留，后续固定节点仍可记录快照；
错过节点不做历史行情回填。same-bar 同时触碰多个边界继续 fail-safe 为
`AMBIGUOUS_SAME_BAR`。这只是复盘边界清理，不回写既有历史 10D outcome。

## Superseding current checkpoint — 2026-09-07 T-close fresh package and recovery

本轮分类为 `correctness/provenance + product-gate audit`，不是新的 research、strategy
selection、promotion、Phase 2F 或 freeze。HiThink `000002.SZ` 的已持久化失败 evidence
显示 HTTP status=`429`，endpoint=`/api/a-share/prices/historical`，logical request identity
为 `thscode=000002.SZ&interval=1d&start=1740355200000&end=1788739200000&adjust=forward`，
实际收到 64 response bytes，脱敏 body 摘要为 `{"code":429,"message":"request limit exceeded","data":null}`。
这属于 transient HTTP failure；此前 HiThink transient classification 漏掉 408/429/5xx，
已在单一 bounded branch 中以共享 helper 最小修复。408、429、5xx 现在 retry，普通 4xx
仍 non-transient；HiThink max attempts=3、provider priority、backoff、Tencent fallback
contract、B strategy/spec/threshold/score 均未改变。focused tests=`33 passed, 52 deselected`；
safe full suite=`260 passed, 2 existing environmental/temp failures`，两项环境测试单独重跑
均 `2 passed`，compile/import 与 diff check 均 PASS。

正式 fresh capture 使用 acquisition code SHA
`39cbd7cf2335ebee1cc7a81faee47c744c737fc3`，并从旧的失败 partial root
`data/t_close_evidence/20260907` 重新建立 clean evidence root：
`data/t_close_evidence/20260907_clean_39cbd7cf2335ebee1cc7a81faee47c744c737fc3/20260907`。
旧 partial attempt 保留为 FAILED audit evidence，不与新 SHA 的 source evidence 混合。新
root 有 10,677 raw/sidecar pairs（21,354 files），missing/hash/byte-length/failure 均为 0，
所有 sidecar code SHA 均为 `39cbd7cf2335ebee1cc7a81faee47c744c737fc3`，新
`UNKNOWN_ORIGIN=0`。

Gate A 的 fresh package 为
`data/prospective_inputs/20260907/2026-09-07_fe54be9be5c5959bd3d690adab2423e7a89f19e4498fb1df927c142f8dab9e4c.json`，
schema=`CANDIDATE_BOUND_LIVE_INPUT_PACKAGE_V4`，status=`READY_FOR_STRATEGY_EVALUATION`，
file SHA=`63fa8effea45cc329035dd97dbe64dfe9d84e899fbb24623190143811e08cc3a`，content SHA=
`792442ff35b5f1e5858180d3e6fc8965c661e4fd6e0c3abd5f9247d90dd6e31e`，generation fingerprint=
`fe54be9be5c5959bd3d690adab2423e7a89f19e4498fb1df927c142f8dab9e4c`。B
`B_BREAKOUT_RETEST_LEGACY_V1_1` run succeeded：raw qualified=26，ST excluded=1，final
non-ST=25；canonical watchlist SHA=
`5a99273b6304621acbf7bba2423a6e372668348a31ac436021caf5f5855db100`。

Gate B 的 persistent recovery 已完成独立核验。私有 Drive target 为
`ashare_watchlist/t_close_20260907_v3_39cbd7cf`；formal inventory 是 14 package archive
chunks、15 source-evidence archive chunks 和 1 chunks40 manifest，共 30 项。每项均通过
独立 raw fetch、decoded byte length 与 SHA-256 exact match；manifest 本身也 exact readback。
原始 package-output archive 为 555,823,686 bytes / SHA
`b089e21da3ac4d0ef5f3f9e252161f48e264a897d7d19a2fc6152b3cae9b99cf`，source-evidence archive
为 564,307,360 bytes / SHA
`411240bb96536484664c7ec288c033e32a6ec86b24862e6b90d70df17cdf14ea`。目标中保留的早期
80MB 中间 chunks 未删除，且不属于上述 formal inventory。

因此 `FROZEN_CANDIDATE_PREREQUISITES` 当前为 `PASS / READY_FOR_USER_DECISION`，但本轮
不自动 freeze；Final OOS=`SEALED / UNREAD`，C=`UNREAD / CANDIDATE INVENTORY ONLY`，old
D=`NOT_RECONSTRUCTED`，`data/validation/continuous_speed_probe/` 未触碰，复盘旧项目脚本
未修改。当前 terminal marker：
`FROZEN_CANDIDATE_READY_FOR_USER_DECISION`。

## Historical checkpoint — WORKSTATION RESUME VERIFIED — 2026-09-06

本轮 post-merge governance、Drive durability 和 clean-workstation dry run 已完成；下方旧
checkpoint 是历史静态记录。PR #39 authorized head=`fdb4640fb8556f7ce86c1d8d1feb7ceb41f9e822`，
merge SHA=`1fdb099926a1172cfebee7001537910d805019e4`，merge-head correctness
`34031658818=success`；governance reconciliation commit=`dd491382c5c8d5bfb07ec844ec116ece56afa526`，
governance-head correctness `34034984771=success`，两者 workflow head 均 exact。

- final live state：master/origin/master exact，open PR=0，tracked working tree clean；formal
  Delivery Ladder=`development candidate`，B=`B_BREAKOUT_RETEST_LEGACY_V1_1` fixed rule +
  prospective observation。
- Drive root `ashare_watchlist`=`13_-tlozdfe1KEtNSMxp6pCroI893g_qH` remains private owner-only。
  2026-09-03 watchlist exact readback verified；daily_k existing recovery valid and no re-upload。
  RS/VCB/CRSR detail archive exact readback verified；Volume-Path local-only detail missing，
  turnover/RV raw/full archive condition not met。
- clean clone HEAD=`dd491382c5c8d5bfb07ec844ec116ece56afa526`，pinned dependencies installed，
  compileall PASS，focused tests=`12 passed`，historical watchlist restore/read-only review PASS，
  no-secret T-close preflight fail-closed and provider calls NOT RUN，status clean。
- `ACTIVE_NEW_STRATEGY_RESEARCH=NONE` / `PAUSED / PHASE_COMPLETE`；Final OOS=`SEALED / UNREAD`；
  C unread/candidate inventory only；old D not reconstructed；forbidden directory untouched。
- close marker：`A_SHARE_RESEARCH_PHASE_CLOSED_WORKSTATION_RESUME_READY`。

## Superseding current checkpoint — first candidate-bound T-close input verified — 2026-09-07

本轮任务分类：`correctness/provenance + product-gate audit`，不是新的 research、strategy
selection、promotion 或 Phase 2F。实时 Git intake 已确认 `origin/master` 为
`9757a12514e2d423e95ea7de6758ab033803ce2b`；本地原始 `master` 为
`38322b91f691b23e7ebaa10818a8733169aafab8`，落后 14 commits，故本次治理修正使用隔离
分支。本次 intake 已取得 GitHub live evidence：remote branch
`codex/p1-gate-20260907` 与 exact HEAD `916c11934a2b76aa9cf3019154cb858978833bbb` 已存在；
push-triggered correctness run `34082842448` 为 `success`，且 workflow head SHA exact-matched
该 commit；PR 尚未创建。创建 successor commit/PR 后，必须以最终 PR head 重新核对 PR
base/head、mergeability 与 exact-head CI。

### Gate A — first real candidate-bound live instance

旧 P1 `P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE` 的语义是“尚无首个真实实例”，
现已不成立，决定为 `STALE_CLOSED_FOR_FIRST_INSTANCE`。可复核身份如下：

| item | verified identity |
| --- | --- |
| package | `CANDIDATE_BOUND_LIVE_INPUT_PACKAGE_V4`; file SHA `a2e6da0865ff20316e4d9074f26e2cb3ba53995d2cb3e83a49f8c82988c0b38a` |
| content / generation | content SHA `0b1216e5c5855343dba02853eb17e9dbc43c97d50120ac7490da43eaa78cdf86`; generation fingerprint `eeb700c98a69a98fae3fa220851190a76de88984b0f451cc1ed275b2e487351f` |
| candidate binding | `B_BREAKOUT_RETEST_LEGACY_V1_1`; spec SHA `f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd` |
| time | T=`2026-09-03`; XSHG close=`15:00`; retrieved=`2026-09-03T18:18:51.506757+08:00`; earliest execution=`2026-09-04` |
| live inputs | universe 5,215; quote 5,215; stock Kline 5,215; index bars 109; sector member containers 49; all V3 quality checks `PASS` |
| corrected B output | run `quJ3jSEgMJjgzQ1SE2rYP7XcSbBEV7fFFjIgiXKlPBk`; run manifest SHA `865eeba45974e70ff70b67b1e8422c5e36e65010d5aebb521d7b01ac197d1445`; raw qualified 12; post-B ST excluded 1; final candidate count 11; canonical watchlist SHA `50f0717e55daaf4435e1d25b4f1d029109c566d72d63a1fc566f263cdf0fb085` |

The raw evidence audit independently verified all 10,597 JSON/raw pairs: missing raw=0,
hash mismatch=0, byte-length mismatch=0, parse failure=0. Therefore the 170
`UNKNOWN_ORIGIN` sidecars do not invalidate Gate A: they are provenance-completeness gaps,
not evidence that the package was not live, candidate-bound, or T-close compliant.

### Gate B — frozen prerequisite remains not ready

`FROZEN_CANDIDATE_PREREQUISITES` remains `NOT_READY / PARTIAL_UNVERIFIED`, but its exact
reason is now split from the stale first-instance P1:

1. `FROZEN_RECOVERY_PROVENANCE_PARTIAL_UNVERIFIED`: 170 source sidecars retain
   `code_git_sha=UNKNOWN_ORIGIN` (the content and byte hashes still verify). This cannot be
   repaired by retroactive attestation or by relabeling old sidecars.
2. `FROZEN_PACKAGE_PERSISTENT_RECOVERY_UNVERIFIED`: the candidate-bound package and source
   evidence are present only in the local workspace for this audit. The existing Drive
   readback is the 6,422-byte corrected watchlist; no package or raw/sidecar archive is in
   the verified Drive project listing. Under V3 and `FROZEN_ARTIFACT_POLICY.md`, this is not
   objective `PERSISTENT_BACKUP_PRESENT` / `FULLY_RECOVERABLE` evidence.

The 2026-09-03 package therefore establishes the first live input instance but not frozen
candidate recoverability. No new package is generated on 2026-09-07 before close. The
12:01 preflight returned `PRE_CLOSE_DIAGNOSTIC_READY`, credential context `READY`, and
`provider_calls=NOT_RUN_BEFORE_T_CLOSE`; this is readiness only, not a fresh capture.

Current terminal marker:
`BLOCKED_REQUIRES_USER_OR_EXTERNAL_DECISION:FROZEN_RECOVERY_PROVENANCE_PARTIAL_UNVERIFIED`.
The missing decision/evidence is either known-origin evidence plus persistent package
recovery/readback, or explicit authorization for a new fully attested post-close capture;
the project does not default to either action.

## Historical checkpoint — PR #39 MERGED + DURABILITY AUDIT (superseded)

这是当前 post-merge、pre-governance-commit 的 authoritative snapshot；下方旧段均为历史
记录。PR #39 authorized head=`fdb4640fb8556f7ce86c1d8d1feb7ceb41f9e822`，merge SHA=
`1fdb099926a1172cfebee7001537910d805019e4`，master correctness run=`34031658818`，
`success` 且 workflow head exact。固定 research decision 为
`CONTROLLED_RIGHT_SIDE_REVERSAL_NO_CLEAR_INCREMENTAL_SIGNAL`。

- 本轮只做 post-merge governance reconciliation、Drive durability、recovery audit 和
  clean-workstation resume dry run；不改策略、protocol、evaluator、production semantics 或
  frozen registry。
- Drive project root `ashare_watchlist` ID=`13_-tlozdfe1KEtNSMxp6pCroI893g_qH` 已验证为
  私有 owner-only；watchlist_20260903 exact readback SHA=`50f071…`，daily_k existing
  recovery remains `FULLY_RECOVERABLE` / `NO_REUPLOAD_REQUIRED`。
- Git-canonical operational files remain in Git；B prospective datastore 未实例化且未创建
  fake observation。RS/VCB/CRSR local-only details 已按 manifest 备份并 exact readback；
  Volume-Path event detail 缺失，turnover/RV raw/full acquisition bytes 未满足 manifest 条件。
- Formal product state remains `development candidate`。B active strategy 为
  `B_BREAKOUT_RETEST_LEGACY_V1_1`，B state 为 fixed rule + prospective observation；主动新
  strategy research=`NONE` / `PAUSED / PHASE_COMPLETE`，不是 production validated。
- Final OOS=`SEALED / UNREAD`；C=`UNREAD / CANDIDATE INVENTORY ONLY`；old D=`NOT_RECONSTRUCTED`；
  forbidden directory untouched。

## Historical checkpoint — POST-PR37 GOVERNANCE RECONCILIATION (superseded)

本段是本次最终交接文档提交前的 last-verified live snapshot；文档提交会使 HEAD 前进，
因此下一台电脑必须重新实时核对 Git/GitHub/CI，而不是把本段静态 SHA 当成不变量。

- last-verified live master：`547feebb88e7b755785c2ae590ea7e4cca0c7a0d`；PR #37 已 merged，
  merge-head correctness runs `33987664237` / `33987644452` 均 `success`。
- 旧治理快照把 PR #37 / 前序任务写成 open；本段与 `HANDOFF.md`、`DECISION_LOG.md` 的修正
  仅为 bounded docs-only reconciliation，不改变任何研究或生产语义。
- 当前任务：`NEW_VOLATILITY_CONTRACTION_BREAKOUT_V1`；仍在 no-outcome input audit，尚未
  读取该候选 forward outcomes，尚未提交其 pre-outcome protocol。
- 当前正式状态仍为 `development candidate`；`B_BREAKOUT_RETEST_LEGACY_V1_1`、B
  prospective observation、RS、Volume-Path、turnover/RV、Final OOS 和 frozen state 均不变。
- `data/validation/continuous_speed_probe/` 作为本机未跟踪目录保留，永不读取、修改、删除、
  hash 或上传。
- 下一步：本 reconciliation 的 master exact-head correctness 通过后，从 reconciled master
  创建独立 VCB research branch，先完成 input audit，再 commit protocol。

本次 handoff 的最终目标是 `WORKSTATION_STATE_DURABLY_PUSHED_AND_HOME_RESUME_READY`，
不是 merge 或 candidate-list 生成。

## Formal project status

PR #12 已 squash merge，项目正式处于 `development candidate` 层。该晋级只表示
deterministic generation → canonical watchlist → fail-closed → provenance/versioning
→ monitoring/rollback 的受控产品路径已经建立，不是 strategy promotion。active PR
的最终 head、CI 和 merge state 仍属于每次 intake 的 live state；本文件中的 merge
commit 和 CI 仅是历史/last-verified provenance snapshot，不是永久 current-state
invariant。

- Phase 2A：legacy strategy audit 完成；缺失历史 provenance 的部分保持 `UNKNOWN_ORIGIN` / `NOT_REPRODUCIBLE_WITH_CURRENT_DATA`。
- Phase 2B：generation input/timing contract 已冻结：仅 T 日收盘、`Asia/Shanghai`、XSHG T+1、`exchange-calendars==4.13.2`。
- Phase 2C：`A_PLATFORM_BREAKOUT_LEGACY_V1` 仍是 research-only wiring witness；PR #12
  的 product-ladder 晋级不改变 strategy semantics，不是 production strategy。
- Phase 2D：PIT validation protocol 已冻结；任何输入必须证明 `known_at <= T`，当前值不能回填历史。
- Phase 2E：HiThink CORE replay、continuous replay 和 adjusted DEVELOPMENT returns V2 已提交并合并到 master（PR #6）。

## Provider architecture correction — 2026-08-31

Sol identified `P0-LIVE-SECTOR-TAXONOMY-MISMATCH` in the merged live adapter: its
Eastmoney industry endpoints could not satisfy B's frozen exact `新浪行业` provenance.
PR #17 subsequently merged this correction to formal master at
`91e9ec76e3f4ea8ffaa1badeb759c1d2a7f5f73b`; the merge exact-head correctness run
`33399324692` succeeded. The two pre-merge `2026-08-31` attempts
remain fail-closed before package construction, so no contaminated prospective artifact
exists.

Current capability decisions are `HITHINK_LIVE_PRIMARY = SUPPORTED` and
`EXACT_SINA_SECTOR_SOURCE = AVAILABLE`. The branch uses HiThink metadata for current
universe/names, HiThink stock/index K as primary (stock forward-adjusted, index explicitly
`PROVIDER_RAW_SNAPSHOT`), exact AkShare Sina sector APIs, and a separately versioned
Tencent Kline transport fallback. EM/THS/SW substitution is rejected; provider, API,
taxonomy, adjustment and fallback identities are included in manifest provenance.

This is a correctness/product architecture correction. B strategy/spec/thresholds and the
`5bbeb345ebd8883149138d2f29f8606f919949ae285aa2839fa337921dfc7112` spec SHA are unchanged;
T-close/T+1 semantics are unchanged. No prospective package was run by this correction.

## Product readiness

- 已有：canonical watchlist schema、盘前/盘后复核、表现追踪、持仓/配对工具；Phase 2B 的 T close / XSHG T+1 contract；Phase 2D PIT contract；Phase 2E CORE / DEVELOPMENT artifacts、registry、hash 和 recovery governance。
- PR #12 的 development-candidate path 已在受控输入上证明端到端 deterministic
  generation → canonical watchlist output → explicit failure → monitoring/rollback/
  versioning；该产品里程碑现已写入 master 的正式 Ladder。
- PR #17 的 HiThink/exact-Sina/Tencent live acquisition adapter、以及其后 PR #20 的
  corrected B governance state 均已进入 master；2026-08-31 的正式 acquisition 失败
  事实仍保留为 historical `INPUT_CONFLICT`，未形成 live package。当前 candidate-bound
  path 绑定 `B_BREAKOUT_RETEST_LEGACY_V1_1`、spec SHA
  `f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd` 和 V3 contract；
  exact V0 sector semantics 为 missing fallback continue 与 provider-order last-write-wins。
- 当前已达到 `development candidate`，仍未达到 frozen candidate、prospective/paper
  observation 或 production strategy promotion；下一层须通过
  [`frozen_candidate_prerequisites_audit.md`](frozen_candidate_prerequisites_audit.md)。
- 进入 observation / paper-use 必须满足 [`docs/PRODUCT_CHARTER.md`](PRODUCT_CHARTER.md) 的十项 Definition of Usable；deferred research 不要求全部先完成。

## What is established

- Continuous CORE replay 覆盖 769 个连续 XSHG sessions（2023-06-30 至 2026-08-28）、4,041,140 个 candidate evaluations。
- CORE projection 只包含 A match、hard reject、support、stop、target、RR、trigger 和 signal identity；没有 score、P&L、return、MFE 或 MAE。
- DEVELOPMENT returns V2 对 8,463 个 qualified events 完成 corporate-action-adjusted outcome measurement；entry 是 T+1 open。
- V2 的正式标签是 `DEVELOPMENT` / `RECONSTRUCTED_RETROSPECTIVE`，不是 Final OOS；旧 V1 raw outcome 只保留作 diagnostic。
- signal 只使用 T 及以前数据；未来 corporate actions 只用于事后 outcome measurement。

## What is not established

- 历史新浪行业 membership / effective-date membership 仍不可得，因此 `FULL_LEGACY_OUTPUT_VALIDATION`、完整 85-score parity 和 legacy sector report 均为 `BLOCKED_HISTORICAL_SINA_MEMBERSHIP`。
- sector score/report 为 `UNVERIFIED`；不得使用当前 sector constituents、其他 taxonomy 或 current data backfill。
- retrospective official dump 没有 per-bar historical vintage timestamp；该 known-at 限制仍需在后续 validation decision 中单独接受或解决。
- `A_PLATFORM_BREAKOUT_LEGACY_V1` 没有 production promotion；没有参数有效性证明，
  未做参数选择、调参或 Final OOS read。
- historical `B_BREAKOUT_RETEST_LEGACY_V1` 及其 old spec/eligibility evidence 保留为
  superseded reconstruction history，不是当前 candidate-bound identity。
- corrected `B_BREAKOUT_RETEST_LEGACY_V1_1` 已获得
  `CORRECTED_B_CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES`；这只是 candidate
  eligibility，不是 frozen strategy、production promotion 或 Final OOS。
- active candidate-bound contract 为 V3，Gate A 状态已更新为
  `FIRST_LIVE_INSTANCE_VERIFIED_A__FROZEN_RECOVERY_NOT_READY_B`；2026-09-03 的首个
  `LIVE_OBSERVED` T-close input instance 已通过 fail-closed audit，但 Gate B 的 frozen
  recovery 仍未完成。
- 本机 Phase 2F diagnostic commit `3eeb5df9f7cf4ef5c30b3380b323f26f2491f873` 尚未 push、无 PR、无 CI；它是 local candidate work，不改变 formal master status。
- Phase 2F local diagnostic 的研究边界保持不变：它没有修改 legacy strategy、冻结阈值或 Final OOS；其退出 decision 为 `NEEDS_MORE_EVIDENCE`，不能直接形成 production threshold 或 promotion。

## Production boundary

生产 ingest/review 的 canonical watchlist schema 和 `ASHARE_DATA_ROOT` 路径约定保持不变。Phase 2E CORE / returns harness 与生产 review 路径分离，不写 canonical watchlist，不改变 `perf_tracker`，不接 scheduler，也不代表可直接交易。

## Current blockers and deferred items

1. **Gate A 已完成**：`P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE` 作为“尚无
   首个实例”的 blocker 已 stale/closed。2026-09-03 package 是首个真实 candidate-bound、
   `LIVE_OBSERVED`、`known_at <= T` 的 V3 T-close input instance。
2. **当前 frozen recovery blocker：`FROZEN_RECOVERY_PROVENANCE_PARTIAL_UNVERIFIED`**。
   170 个 source sidecars 的 `code_git_sha` 仍为 `UNKNOWN_ORIGIN`；candidate-bound
   package 与 source evidence 也没有经验证的 persistent external backup/readback，故
   不能把 B 的 frozen prerequisite 标为 `FULLY_RECOVERABLE`。这不否定 Gate A。
3. **Current V3 sector boundary**：missing sector 解析为 `("-", 50, 0.0)` 并继续
   B evaluation；multiple memberships 使用
   `LEGACY_PROVIDER_ORDER_LAST_WRITE_WINS_V1`。2026-09-01 coverage/ambiguity counts
   仅为 current-only diagnostic，不是当前 blocker；future package 仍须保留 raw rows、
   traversal order、resolved mapping 和 provenance，并对 provider/invalid/unresolved
   package identity failure fail closed。
4. **Scope-local correctness blocker — FULL legacy only**：历史新浪行业 membership /
   effective-date evidence 缺失，阻止 `FULL_LEGACY_OUTPUT_VALIDATION`、完整 85-score
   parity 和 legacy sector report；它不阻止 development-candidate product path 或当前
   candidate-bound gate，不能写成整个系统 blocker。
5. **Scope-local provenance limitation**：retrospective official dump 没有 per-bar
   historical vintage timestamp，限制历史 known-at 结论的强度；live prospective
   inputs 仍必须按 T 的 observed-at contract 处理。

已解决：`daily_k.parquet` recovery evidence 与 registry exact SHA 匹配，状态为 `FULLY_RECOVERABLE`。

Deferred（当前不阻止 usable milestone）：Phase 2F 后续 Research V2、历史新浪 membership acquisition 的完整研究、完整 legacy 85-score parity、任何参数选择/调参、performance-based rule change，以及 later production hardening 中不影响 P0/P1 的运营增强。

## Current continuation audit — 2026-09-01 historical snapshot

本节记录 2026-09-01 当时的 current-only provider audit；其中的旧 blocker、V2
contract 和 sector coverage/ambiguity 结论均为 historical evidence，不代表本文当前
live governance state。当前 corrected B/V3 状态见本文末的 superseding section。

本机已从 repository declaration 重建 workspace-local `.venv`，并以
`.[test,research]` 安装验证 Python 3.12.13、pandas 2.2.3、requests 2.32.3、
exchange-calendars 4.13.2、AkShare 1.18.94、pytest 8.3.5 和 pyarrow 17.0.0；
XSHG/Asia/Shanghai、数据根目录和 HiThink credential presence 已核对。当前 Codex
app 的 Google Drive profile、private backup metadata/raw streamed reference 以及临时
upload/readback/delete probe 已完成；正式 `daily_k.parquet` 未在本轮重新物化 byte hash。

`scripts/development_preflight.py --probe-provider` 的结果明确标记为
`LOCAL_CURRENT_SNAPSHOT_DIAGNOSTIC_NOT_PROSPECTIVE_EVIDENCE`。当前 HiThink 返回 5,565
raw rows / 5,221 个 SH/SZ A-share symbols，snapshot、adjustment-events、stock/index
historical capability 均 PASS；exact Sina 返回 49 definitions / 49 member calls。
sector audit 为 2,983 raw rows、2,978 unique member symbols、2,539 common symbols、
2,682 个 universe symbols 缺 sector、439 个 sector symbols 在 universe 外、47 个
raw-name mismatch（registered normalization 解决 0 个），并发现 000587、000602、
002217、002617、600714 五个同一 symbol 多 sector membership。完整 source/dependency
matrix 与当前计数见 [`b_dependency_audit_20260901.md`](b_dependency_audit_20260901.md)。

本次 historical snapshot 的 decision：`ADOPT` symbol-authoritative display-name policy；
`NEEDS_MORE_EVIDENCE` for complete and unambiguous exact-Sina sector evidence at a
legitimate future T-close。当时 formal blocker 为
`FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_SECTOR_MEMBERSHIP_AMBIGUITY`，并伴随 exact
coverage failure。PR #18 尚未合并，故没有构造 T=`2026-08-31` 或 T=`2026-09-01` package，
没有 canonical output、promotion、Phase 2F、C evaluation 或 Final OOS access；Formal
Delivery Ladder 仍为 `development candidate`。
当时的 P1 为 `P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE`；2026-08-31 正式
master-baseline acquisition 在 AkShare sector membership 阶段发生 `ConnectionError`，
未形成 package。后续需要一个 candidate-bound、`LIVE_OBSERVED`、`known_at <= T` 的
真实 T-close package，并证明 universe/sector/names/market_env、provider/version、
calendar、availability/recovery 和 output identity。
3. **Scope-local correctness blocker — FULL legacy only**：历史新浪行业 membership /
   effective-date evidence 缺失，阻止 `FULL_LEGACY_OUTPUT_VALIDATION`、完整 85-score
   parity 和 legacy sector report；它不阻止 development-candidate product path 或当前
   candidate-bound gate，不能写成整个系统 blocker。
4. **Scope-local provenance limitation**：retrospective official dump 没有 per-bar
   historical vintage timestamp，限制历史 known-at 结论的强度；live prospective
   inputs 仍必须按 T 的 observed-at contract 处理。

已解决：`daily_k.parquet` recovery evidence 与 registry exact SHA 匹配，状态为 `FULLY_RECOVERABLE`。

Deferred（当前不阻止 usable milestone）：Phase 2F 后续 Research V2、历史新浪 membership acquisition 的完整研究、完整 legacy 85-score parity、任何参数选择/调参、performance-based rule change，以及 later production hardening 中不影响 P0/P1 的运营增强。

治理校验注意：现有、非 replay-required 的 `phase2e.hithink_probe` registry record
预存 `working_tree_sha256=af694b...`，但当前 exact bytes 的 SHA 为其 registered
`file_sha256=395601b...`。本轮未修改 frozen registry，也未用该 provider probe 作为
live package/recovery evidence；该 pre-existing provenance discrepancy 需另行显式
修复或决策，不改变本轮正式 acquisition 的 provider blocker。

## Phase 2F product rationale and exit decision

Phase 2E V2 的 DEVELOPMENT returns 是描述性、`RECONSTRUCTED_RETROSPECTIVE`、非 promotion 证据；Phase 2F 值得做，是因为它能在不改策略/阈值的前提下回答当前候选的失败结构是否足以拒绝候选，或是否值得另立一个预注册、范围受限的 research protocol。local-only Phase 2F diagnostic 已给出边界内画像，但未证明稳定可迁移 edge。

**Decision：`NEEDS_MORE_EVIDENCE`。** 不 adopt 当前诊断为 production rule，不自动启动 Research V2；若未来要继续，只能先定义 materiality、预注册比较和 exit gate。该 decision 不阻止当前 product path 的 development work，也不授权读取 Final OOS。

## First prospective acquisition attempt — 2026-08-31

正式 master baseline 为 `f1fed4608210aa175ac268189a8d7f032b0b88e0`。T=`2026-08-31`
是 XSHG session，session close=`2026-08-31T15:00:00+08:00`，下一交易日
T+1=`2026-09-01`。调用开始于实际运行时 `2026-08-31T15:21:18.969554+08:00`；
AkShare universe/sector acquisition 在 sector membership 请求阶段以
`ConnectionError` fail closed，状态为 `PROVIDER_FAILURE`。

没有形成 READY `GenerationInputManifest`，没有 `LIVE_OBSERVED` package，没有
input/generation fingerprint、package content/file SHA 或 logical path，
`data/prospective_inputs/` 未创建；没有 canonical watchlist，也没有 recovery
artifact 可登记。未进入 Tencent quote/Kline、market_env、persistence 或
frozen-candidate prerequisite 的后续 checks。Formal Delivery Ladder 仍为
`development candidate`；不创建 `FROZEN_CANDIDATE_CONTRACT_V1`。

## PR #16 — same-day retry semantics and AkShare bounded retry

Sol review 将 `PROJECT_GOVERNANCE_STATE_CONFLICT` 限定为旧草稿把 retry 语义写成
“只能等下一个 T-close session”。Phase 2B contract 没有这个限制：在同一北京时间
日期 T、正式收盘后，可以发起新的独立 live acquisition attempt。每次 attempt 必须
使用新的真实 `observed_at`，不复用失败 attempt 的 partial provider responses，也不把
第一次失败改写为成功；跨到 `2026-09-01` 后，当前 live provider 数据绝不能构造
`T=2026-08-31` package。

PR #16 的最小代码 hardening 只对 AkShare
`stock_info_a_code_name`、`stock_board_industry_name_em` 和每个
`stock_board_industry_cons_em` provider read 提供固定最多 3 次的 transient
network/connection retry，并使用 bounded backoff。schema、empty、duplicate、name/
sector conflict 和 coverage 等语义错误仍在 retry 边界外 fail closed；attempt/backoff
不进入 canonical input/generation/package identity。新增回归覆盖 transient recovery、
3-attempt exhaustion、sector-member recovery、semantic/schema no-retry 和 no-output。

执行规模审计（execution diagnostics，不是筛选规则）保持完整 universe：AkShare
universe 1 次 read、sector definitions 1 次 read、每个 definition 1 次逻辑 member
read（transient retry 只增加同一 read 的 provider attempts）、Tencent quote 每 50
个 symbol 一个 batch，即 `ceil(universe_symbol_count / 50)`，planned stock Kline
request 数为 `universe_symbol_count`，另加 1 次 index Kline request。此前正式失败发生
在 sector membership，尚无真实 universe/definition 完成计数或后续 quote/Kline 计数；
不得用缩小 universe、跳过股票或改 strategy 解决潜在规模问题。

PR #16 合并后，在 clean merged master `c9d5e50be833bf5bb1c3c83c0a2fa1b3e83979c1`
上于新的真实 `observed_at_bjt=2026-08-31T16:27:36.974203+08:00` 重新获取全部
required input。第二次 attempt 的 AkShare `stock_info_a_code_name` 在固定 attempts
`3/3` 后仍以 `ConnectionError` 失败，adapter acquisition elapsed 为 `0.782s`；
sector code/name 不适用，completed sector calls `0`，sector definition count
`NOT_REACHED`，universe symbol count `0`，Tencent quote batch、stock/index Kline、
market_env、manifest 和 persistence 均 `NOT_REACHED`。没有创建
`data/prospective_inputs/` 或任何 partial formal evidence。

## Current next action

当前已在 `development candidate`。B 已通过一次且仅一次的冻结 eligibility，结果为
`CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES`。candidate-bound contract 已定义，
但 `FROZEN_CANDIDATE_PREREQUISITES` 仍为 `FROZEN_CANDIDATE_BLOCKED`，当前 P1 是
`P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE`，具体 blocker 为 AkShare sector
provider failure；本次已完成同日独立 retry attempt 并在 attempts `3/3` 后再次 fail closed，
本任务停在该真实 blocker，不自动无限重试。后续若得到新的明确运行授权且 provider 可用，
必须重新获取全部 input；跨到下一北京时间日后，不得再用当前 live provider 数据构造
本次 T 的 package。不启动 Phase 2F、不调参、不读 Final OOS、不把 product-ladder 晋级写成
strategy promotion。

PR #17 的 review-branch snapshot 已结束；该 PR 已从 final head
`ef48d192c7709a7194348369c689070c665da2b4` squash-merged to master at
`91e9ec76e3f4ea8ffaa1badeb759c1d2a7f5f73b`，merge master exact-head correctness run
`33399324692` succeeded。后续 acquisition 结果见本文末的 post-merge decision。

## Strategy Candidate Nomination V1 — 2026-08-30 — historical final eligibility update

唯一 nomination 仍为
`NOMINATE_B_BREAKOUT_RETEST_LEGACY_V1_FOR_DEVELOPMENT_ELIGIBILITY`；A 仍为
`REJECT_A_PLATFORM_BREAKOUT_LEGACY_V1_AS_FROZEN_CANDIDATE`，C 未被评估。

B exact reconstruction 已完成，spec SHA 为
`5bbeb345ebd8883149138d2f29f8606f919949ae285aa2839fa337921dfc7112`。固定
`STRATEGY_DEVELOPMENT_ELIGIBILITY_V1` 在 parquet 环境修复后只运行一次，并保持
`ELIGIBILITY_RULE_FROZEN_BEFORE_B_RETURNS_READ = true`。环境为 Python 3.12.13、
pandas 2.2.3、pyarrow 17.0.0；registry required artifacts 13/13 通过校验，
daily_k SHA 为 `61189a4850e2eb157453e28e5375e502e20d214508bbe70ea71066ca3e05e426`。

结果：Event N `17,714`；1D/3D/5D/10D available N 为 `17,689` / `17,635` /
`17,602` / `17,558`；10D positive rate / mean / median 为 `51.6403%` /
`+1.4603%` / `+0.3226%`；4 个 robust years 中 2 个 mean 为正。固定 gates 全部
PASS，最终 B decision 为 `CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES`。完整指标、
MFE/MAE、concentration、year robustness、gate audit 和 event/manifest SHA 见
[`strategy_candidate_eligibility_report.md`](strategy_candidate_eligibility_report.md)。

已定义 [`candidate_bound_prospective_input_contract_v1.md`](candidate_bound_prospective_input_contract_v1.md)，
但没有伪造 prospective live instance。重新判断后的
`FROZEN_CANDIDATE_PREREQUISITES` 为 `FROZEN_CANDIDATE_BLOCKED`，唯一 P1 为
`P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE`；在首个真实
`LIVE_OBSERVED` T-close package 到来前，不创建 `FROZEN_CANDIDATE_CONTRACT_V1`，
不测试 C、不启动 Phase 2F、不调参、不读 Final OOS。

## Governance correctness closure — 2026-08-31

已修复 active PR metadata 与正式 B evidence 的 `PROJECT_GOVERNANCE_STATE_CONFLICT`：
B decision 为 `CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES`；Formal Delivery Ladder
仍为 `development candidate`；尚未创建 `FROZEN_CANDIDATE_CONTRACT_V1`；唯一当前
P1 仍为 `P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE`；不 promotion。

eligibility provenance 已改为稳定 repo-relative logical paths。不同 filesystem root、
relative/absolute invocation 的 canonical identity 回归均通过；绝对 path 与
`Path.resolve()` machine-specific result 不进入 semantic/content/manifest hash。

正式 B decision artifacts 已在 `data/governance/frozen_artifacts.json` 登记：event
file SHA `8940a4a346ac6911ba669f84a9ceba7ef878b0ed0ce51edf673439b52aa056b9`、event
semantic SHA `a16e48dfbe8a93f64d8bf1bad6e00d3eaf32c10fd60eed09dc5574247b8119bc`；manifest
manifest semantic SHA `f79ec9baa494f2f0256843c2540988bd25c94269ed9a1fd4ada228759bd8e0a2`、
payload content SHA `e754787836b28316430278372ab2d84817091d4608da394f9207f695a4c27aee`、
manifest file SHA `5e0a557c1930de7b4f182f09f43b45c0c11b19b2d7c992bf9e7fa7e6cc6de048`。
两项均为 `required_for_decision=true`、`required_for_replay=false`。

同一冻结输入与固定 B protocol 的 deterministic reproducibility verification 证明
event count、event identities、全部 metrics、fixed thresholds、gate audit 和
eligibility decision 与修复前完全一致；这不是第二次 candidate-selection experiment。
Phase 2B T-close/T+1、anti-lookahead、Final OOS sealed invariants 未改变。

## Live acquisition adapter readiness — 2026-08-31

本任务对当前 master 做了执行路径审计：原有代码只有 Phase 2B
`freeze_generation_inputs()` validator 和旧 Tencent quote/Kline utility，没有能从
AkShare/HiThink/Tencent provider 构造完整 candidate-bound `GenerationInputManifest` 的
acquisition adapter。因此 `P1-FC-LIVE-ACQUISITION-ADAPTER_MISSING` 被识别为本轮
真正的产品 P1，并在未改变任何 B strategy/spec/threshold 的单一实现分支中补齐。

[`live_acquisition_adapter_v1.md`](live_acquisition_adapter_v1.md) 和
[`scripts/live_acquisition.py`](../scripts/live_acquisition.py) 定义并测试了
HiThink SH/SZ A-share universe/names、exact Sina sector definitions/membership/rank、
Tencent T quote、HiThink forward stock / raw index daily K（Tencent qfq fallback）、display names、market_env、runtime/
provider provenance、T-close/T+1、freshness/completeness/conflict、deterministic
identity、immutable input persistence 和 fail-closed 行为。实际 runtime 的 AkShare
版本为 `1.18.94`；pyarrow 保持 `25.0.1`，没有为 prospective path 降级。

这是 implementation/runtime readiness；PR #15 已合并到 master；PR #17 随后完成 provider correction。合并前本分支和
测试没有调用 live endpoint；合并后首个正式 master-baseline acquisition 已在
AkShare sector membership 阶段以 `PROVIDER_FAILURE / ConnectionError` fail closed，
没有冻结 `LIVE_OBSERVED` T 日数据、没有生成 canonical watchlist 或 prospective
package。Formal Delivery Ladder 仍为 `development candidate`，prerequisite
decision 仍为 `FROZEN_CANDIDATE_BLOCKED`；provider 可用时，可以在同一 T 日正式收盘后
以新的 observed_at 独立重试并重新审计；本轮 post-merge attempt 的失败结果见本文末。

## PR #17 final contract hardening — 2026-08-31 (historical review snapshot)

PR #17 在现有 provider correction 上补齐最后一个 correctness boundary：stock
`KlineManifest` 只接受 `PROVIDER_QFQ_SNAPSHOT`；HiThink index primary 只接受
`HiThink Financial-API` + `PROVIDER_RAW_SNAPSHOT`；Tencent index fallback 只接受
`Tencent` + `PROVIDER_QFQ_SNAPSHOT`，其他 provider/adjustment 配对 fail closed。

当前 live universe contract 正式版本化为
`TRADABLE_UNIVERSE_SCOPE_V1 = SH_SZ_A_SHARE_ONLY`：沪市/深市 A 股 included，北交所
explicitly excluded，BJ absence 不计为 incomplete coverage。scope/version 进入
UniverseManifest content identity、GenerationInput input fingerprint、live generation
identity、provider metadata 和 prospective provenance。未来纳入 BJ 必须形成新的
scope/version identity。

既有 B development eligibility 的历史 universe scope 不被重跑、改写或用来选择新
candidate；若其历史输入包含 BJ，只保留
`KNOWN_DEVELOPMENT_VS_PROSPECTIVE_UNIVERSE_SCOPE_DIFFERENCE` 作为 scope 差异记录，
不据此否定既有 B decision。B strategy/spec/threshold、冻结历史 artifact 和 Final OOS
sealed 状态均不变。

## Post-merge formal acquisition decision — 2026-08-31

PR #17 was squash-merged at `91e9ec76e3f4ea8ffaa1badeb759c1d2a7f5f73b` from final
head `ef48d192c7709a7194348369c689070c665da2b4`; merge master exact-head correctness
run `33399324692` succeeded. A new `LIVE_OBSERVED` attempt for T=`2026-08-31`
used fresh `observed_at_bjt=2026-08-31T22:01:28.307161+08:00` and T+1=`2026-09-01`.

The attempt failed closed at exact Sina sector/member display-name consistency:

    INPUT_CONFLICT: display-name conflict for 000012: universe/member

The final frozen-candidate prerequisites status is
`FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_INPUT_CONFLICT`. This is an
`INPUT_PROVIDER_DATA_CONSISTENCY_CONFLICT`, not provider connectivity. No READY manifest
or package was created; quotes, Klines, hashes, persistence, Google Drive backup/recovery,
canonical watchlist, prospective returns, C, Phase 2F, tuning, paper/live trading,
and production promotion were not performed. The attempt evidence is recorded in
[`prospective_acquisition_evidence_20260831.md`](prospective_acquisition_evidence_20260831.md)
and the machine-readable record is explicitly not a frozen artifact.

The formal Delivery Ladder remains `development candidate`; B remains
`CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES` at candidate eligibility. Strategy/spec/
thresholds, frozen artifacts, Final OOS sealed/unread status, and all no-backfill/no-future
boundaries are unchanged.

## PR #18 continuation — display-name blocker diagnosis and minimal fix

本节为 PR #18 时点的 historical pre-correction snapshot；其 V1/V2 identity、coverage /
ambiguity gate 和 provider diagnostic 不代表本文当前 live governance state。

The 2026-08-31 formal attempt remains a failed `LIVE_OBSERVED` attempt; it is not
rewritten as success. Its `INPUT_CONFLICT` is classified as
`INPUT_PROVIDER_DATA_CONSISTENCY_CONFLICT`, with final decision
`FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_INPUT_CONFLICT`. Provider connectivity is
explicitly false. The original attempt did not record raw names or execution counts,
so those fields remain unrecorded rather than being backfilled from a later current
diagnostic.

The 2026-09-01 fresh-machine current capability diagnostic read the complete HiThink
`SH_SZ_A_SHARE_ONLY` universe and exact Sina sector/member source: 5,565 raw universe
rows / 5,221 scoped symbols, 49 definitions, 49 completed member calls, 2,539 common
symbols, 2,492 exact raw-name matches, and 47 raw-name mismatches. The registered
normalization resolved zero mismatches. The current snapshot also has 2,682 universe
symbols without sector membership, 439 sector symbols outside the universe, and five
multi-sector symbols: `000587`, `000602`, `002217`, `002617`, `600714`. There were no
exact duplicate symbols in this snapshot. All of these counts are current diagnostics
only and are not a rewrite of the 2026-08-31 historical diagnostic or attempt.

PR #18 keeps `B_BREAKOUT_RETEST_LEGACY_V1`, its spec SHA and thresholds,
`TRADABLE_UNIVERSE_SCOPE_V1 = SH_SZ_A_SHARE_ONLY`, exact Sina taxonomy, T-close/T+1,
Final OOS sealed/unread, C exclusion, and no-tuning/no-promotion boundaries unchanged.
The live adapter retains both raw provider names, compares normalized values, keeps
symbol as the security identity, versions the normalization and policy in generation
identity/provenance, and exposes safe structured mismatch diagnostics. Exact duplicate
same-sector provider rows may be deterministically deduplicated with raw row/count
provenance; distinct sector memberships remain fail closed. No partial formal package
is persisted. The source audit confirms B consumes sector evidence/rank/change, so the
sector requirement remains executable and cannot be relaxed or substituted.

At the pre-merge snapshot, the decision was
`FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_SECTOR_MEMBERSHIP_AMBIGUITY`, with independent
exact-Sina coverage failure. The active contract is
`CANDIDATE_BOUND_PROSPECTIVE_INPUT_PROVENANCE_CONTRACT_V2`; V1 remains historical.
At that snapshot, PR #18 had not been merged, so no T=`2026-08-31` or T=`2026-09-01`
package had been constructed. The full source matrix and current snapshot audit are in
[`b_dependency_audit_20260901.md`](b_dependency_audit_20260901.md).

## 2026-09-01 sector-provenance closure — historical pre-correction status

Formal Delivery Ladder remains `development candidate`. PR #18 is now merged at
`17371fde39a6b24241532b131caf5927cb9b8933`; exact merge push correctness run
`33476256589` succeeded. The current closure branch was created from that clean
merged master.

The current blocker is `B_RECONSTRUCTION_SEMANTIC_MISMATCH`: exact V0 missing-sector
behavior defaults to `("-", 50, 0.0)` and continues evaluation, while the current B
evaluator returns per-symbol `INSUFFICIENT_DATA`. The current V2 live adapter also
has package-level full-coverage and distinct-multi-sector fail-close rules; these
are recorded separately and are not treated as proof that Model S/V3 is adopted.

Current exact-Sina diagnostics remain non-prospective: 49/49 definitions audited,
2,983 raw and wrapper rows, 2,978 raw unique symbols, 2,682 scoped-universe symbols
without membership, 439 outside-scope symbols, and five distinct multi-sector
symbols. No safe wrapper correction was found. No formal `LIVE_OBSERVED` T-close
capture, READY manifest, package, canonical watchlist, prospective result, C,
Phase 2F, promotion, or Final OOS read was performed. Final OOS remains
`SEALED / UNREAD`.

Closure evidence and the machine-readable decision are in
[`sector_provenance_closure_20260901.md`](sector_provenance_closure_20260901.md).

## 2026-09-01 continuation — frozen B spec text conflict

本轮继续核对指定 V0 commit 后发现，当前 B executable spec 不能直接进入语义修复：
`scripts/b_breakout_retest.py` 的 `LEGACY_SPEC["input_contract"]["sector_evidence"]`
明确声明 `silent_fallback=False` 与 `missing_status=INSUFFICIENT_DATA`，而 exact V0
在缺失 sector 时使用 `("-", 50, 0.0)` 并继续评估。因此当前正式 stop state 为
`B_FROZEN_SPEC_TEXT_CONFLICT`，需 Sol review；不能静默改 evaluator 后继续使用原
spec SHA，也不继续 T-close acquisition。

本次 live intake：closure branch rebase 后 HEAD 为
`3d5f3b185f95a8215eed3eb0a88a54e568333acc`，`origin/master` 为
`fc0698c20fb3e7909090cf5073c59d1a2dd710f3`；open PR 为 0，PR #18 已 merge 到
`17371fde39a6b24241532b131caf5927cb9b8933`，merge exact-head run `33476256589`
成功。closure branch 未能推送到 origin，remote protection 为
`REMOTE_PROTECTION_NOT_ESTABLISHED`；未通过替代路径外发内部治理/诊断证据。

另一个独立的 frozen identity audit 发现，指定 V0 commit 的 Git blob SHA 为
`843935d9b86ec05af848ee8cc54812334475e3d17807cb93349a02c84896417a`，而现有声明为
`6cac746123e315199cbeeb1a612868ef77b50af6c7c64b0d80eb387ae1d19f9`；原声明未覆盖，
因此同时保持 `PROJECT_GOVERNANCE_STATE_CONFLICT` / `UNKNOWN_ORIGIN`，不继续生成。
旧 17,714-event eligibility artifact 尚未审计，
`EXISTING_B_ELIGIBILITY_ARTIFACT_AFFECTED=UNRESOLVED`；没有 supersede 标记、corrected
artifact、contract 修改或 `T=2026-09-01` capture。Formal Delivery Ladder 仍为
`development candidate`，B eligibility decision 和旧 frozen bytes 均未改写。

## 2026-09-01 — B candidate identity/provenance closure

本轮完成了停止状态要求的 provenance 与 candidate identity 审计，没有修改
evaluator、live contract、spec、threshold、旧 frozen artifact 或任何 live input。

V0 repository identity 已确认为 `EFSing/ashare_watchlist-V0`、`main` ref、commit
`c8406c393c0b135eafb0aec763576ae869fddcff`、path
`ashare_watchlist/scripts/screen_system.py`。其 Git object format 为 `sha1`，Git blob
OID 为 `ede1ee62451fa9b817bf390ab75e963115a678dc`，raw/LF file SHA-256 为
`843935d9b86ec05af848ee8cc54812334475e3d17807cb93349a02c84896417a`。CRLF 转换后的
64-char SHA 为 `6cac746123e3151999cbeeb1a612868ef77b50af6c7c64b0d80eb387ae1d19f9`，
而历史声明 `6cac746123e315199cbeeb1a612868ef77b50af6c7c64b0d80eb387ae1d19f9` 只有
63 chars，二者不相等。因此 repository/commit/path 已建立，但 required source-file
declaration 仍未验证；声明值未覆盖，完整 audit 见
[`b_candidate_identity_provenance_20260901.md`](b_candidate_identity_provenance_20260901.md)。

PR #14 创建的 `scripts/b_breakout_retest.py:LEGACY_SPEC` 由
`copy.deepcopy(A_LEGACY_SPEC)` 产生；A 的 generic sector block 已有
`silent_fallback=False` / `missing_status=INSUFFICIENT_DATA`，B-specific overrides 未
重写它。exact V0 的实际 B path 则是缺失 sector 使用 `("-",50,0.0)` 继续评估、
multi-sector 按 provider traversal last-write-wins；nomination/history/tests 没有发现
pre-returns 的 B-specific stricter adoption evidence。因此当前 candidate identity
classification 已从未决审计推进为：

`B_CANDIDATE_IDENTITY_UNRESOLVED`

按 mandated stop condition，本轮没有形成 eligibility artifact impact 结论：
`EXISTING_B_ELIGIBILITY_ARTIFACT_AFFECTED=UNRESOLVED`。旧 17,714-event bytes 未
supersede/overwrite，未重跑 eligibility。虽然现有 generator 的结构性 call path 使用
不接收 sector 的 `evaluate_numeric_projection`、fixed parity sample 仅使用 neutral
sentinel、score 不在 projection/event，但这些事实要在 source/candidate identity 解决后
才能形成正式 impact decision；真实 missing/multi-sector symbol-date 数量不填猜测。
Formal Delivery Ladder 仍为 `development candidate`，B spec/evaluator/contract/old
artifact 不变，Final OOS 仍 `SEALED / UNREAD`，formal T-close capture 仍 `NOT_RUN`。

当前停止点是 Sol/user 解决 declared SHA 的正确 64-char identity 或 historical
source/canonicalization 证据；在此之前不宣布 Case A/B，不创建新的 spec/version，不修
evaluator，不重跑 eligibility，不继续 T-close acquisition。

## 2026-09-01 corrected B reconstruction — historical post-merge snapshot

PR #19 已按授权以 squash merge 合并；final head 为
`f99c33993fed00e38e87785a88155034ceaf57c3`，merge SHA 为
`28e871552da0813fd51b510a9ef0980976556d29`，post-merge master exact-head
correctness run `33491720346` 成功。PR #19 的 unresolved identity 结论保留为历史
审计时点，不被删除或改写。

本轮正式关闭 source identity conflict，decision 为
`V0_SOURCE_IDENTITY_RESOLVED_AUTHORITATIVE_RAW_GIT_BYTES`；旧 63-character SHA
分类为 `HISTORICAL_SOURCE_SHA_TRANSCRIPTION_ERROR`。旧
`B_BREAKOUT_RETEST_LEGACY_V1` / spec SHA 保留为历史 reconstruction，分类为
`SUPERSEDED_RECONSTRUCTION_WITH_PROVENANCE_AND_SECTOR_SEMANTIC_DEFECT`。新的
`B_BREAKOUT_RETEST_LEGACY_V1_1` / spec SHA
`f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd` 是唯一用于
future candidate-bound work 的 corrected exact-V0 identity。

corrected semantic parity decision 为 `B_CORRECTED_RECONSTRUCTION_SEMANTICS_ADOPTED`。
Structural impact audit decision 为 `ELIGIBILITY_ARTIFACT_EVENT_SET_INVARIANT`：
769 sessions、4,041,140 evaluated symbol-dates、old/corrected event count 都为
17,714，projection/status/event membership differences 都为 0，故
`EXISTING_B_ELIGIBILITY_ARTIFACT_AFFECTED=FALSE`，不需要 returns regeneration，旧
artifact 不覆盖。corrected candidate decision 为
`CORRECTED_B_CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES`。

Formal Delivery Ladder 仍为 `development candidate`，尚未达到 frozen candidate。
Future binding 已切换到 `CANDIDATE_BOUND_PROSPECTIVE_INPUT_PROVENANCE_CONTRACT_V3`，
但尚无新的 `LIVE_OBSERVED` package；在 correctness PR 合并且其 master exact-head
CI 成功前不运行 T=`2026-09-01` capture。Final OOS 仍 `SEALED / UNREAD`，C、Phase 2F、
调参、promotion、自动 freeze 和 current-data backfill 均未执行。

## Current governance state — 2026-09-02

本节 supersede 旧段落对 current/active/next 的解释，不删除或改写其 historical
evidence。当前 formal state 为 `development candidate`；corrected candidate 为
`B_BREAKOUT_RETEST_LEGACY_V1_1`，spec SHA 为
`f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd`，decision 为
`CORRECTED_B_CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES`。

- active contract：`CANDIDATE_BOUND_PROSPECTIVE_INPUT_PROVENANCE_CONTRACT_V3`，状态为
  `CONTRACT_DEFINED_NO_LIVE_INSTANCE`。
- exact V0 sector semantics：missing sector=`("-",50,0.0)` continue；multi-sector=
  `LEGACY_PROVIDER_ORDER_LAST_WRITE_WINS_V1`。旧 V1/V2、old spec、旧 sector
  coverage/ambiguity diagnostic 和 failed attempts 仅作为 historical evidence。
- current blocker：`P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE`。
- current next gate：`T=2026-09-02` legitimate XSHG T-close 后的首个真实
  `LIVE_OBSERVED` package；北京时间 15:00 前绝不运行 formal acquisition，不把任何
  probe 注册为 prospective evidence，不回填 `2026-09-01`。
- last-verified master snapshot：`614934e7ea98bbe94099e9bf57971cf8454c9713`；exact-head
  master correctness run `33584844019` 为 `success`。该 snapshot 是本治理 branch 前的
  provenance，不是未来 PR CI 的 self-referential invariant。

## Superseding current state — 2026-09-02 corrected-B prospective attempt

- formal Delivery Ladder：仍为 `development candidate`；corrected candidate 仍为
  `B_BREAKOUT_RETEST_LEGACY_V1_1`，spec SHA 为
  `f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd`，V3 contract
  仍为 `CANDIDATE_BOUND_PROSPECTIVE_INPUT_PROVENANCE_CONTRACT_V3`。
- timing gate：`2026-09-02T16:10:17.291775+08:00` BJT 已晚于 XSHG close；T=`2026-09-02`，
  T+1=`2026-09-03`。本次不是 pre-close、historical replay 或 current-data backfill。
- concrete decision：`FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_PROVIDER_FAILURE`。
  underlying P1 仍为 `P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE`，本次真实
  blocker 是 Tencent quote snapshot 的 `QuoteFieldError`；分类为 provider data
  validation failure，不是 connectivity failure。
- acquisition boundary：HiThink universe 与 exact Sina `新浪行业` sector traversal
  已完成，但异常 runner 未暴露其 counts/diagnostics，故不填猜测；Tencent quotes
  fail closed，后续 stock/index Kline、market_env、GenerationInputManifest、B
  evaluation 和 output 均未执行。
- artifact/output state：证据记录于
  [`data/governance/prospective_input_attempt_evidence_20260902.json`](../data/governance/prospective_input_attempt_evidence_20260902.json)，
  明确不是 frozen artifact。没有 READY manifest、immutable package、canonical
  watchlist、Drive backup、recovery identity 或 candidate list；本次 candidate count
  是 `NOT_EVALUATED`，不是合法的 zero-candidate result。
- boundaries：Final OOS、prospective returns、MFE/MAE/P&L、C、Phase 2F、调参、promotion、
  automatic freeze 和 `2026-09-01` backfill 均未读取/执行。Formal status 不晋级，不自动
  重试；未来重试必须重新取得 fresh T-close inputs。

## Superseding current state — 2026-09-02 Tencent QuoteFieldError audit

- formal Delivery Ladder：仍为 `development candidate`；corrected B/V3 identity、
  strategy、threshold、sector taxonomy、universe semantics 和 Final OOS sealed/unread
  状态均不变。
- current audit decision：`NEEDS_MORE_EVIDENCE`；root-cause classification 为
  `UNRESOLVED`，尚不能在 A/B/C 中选择。第一次 attempt 的
  `FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_PROVIDER_FAILURE` 保留为 historical
  operational result，但本审计不把它视为最终关闭。
- missing evidence：第一次 formal detail 被压缩为
  `Tencent quote acquisition failed: QuoteFieldError`，diagnostics 为空；exact symbol、
  Tencent symbol、field/index、underlying validation message、raw line 和 failure batch
  没有记录。不得用 0 值或异常类型推断停牌，也不得据此宣布 parser mapping bug。
- current-only boundary：没有合法 target symbol/batch，故未运行窄 Tencent probe；不请求
  猜测股票，不注册 probe，不复用 payload，不运行 B、不生成 package。
- local code state：已追加最小 diagnostic-only fix，使后续 `QuoteFieldError` 保留原
  detail、six-digit/Tencent failure batch 和 formal diagnostics；字段规则仍 fail closed。
- historical evidence：commit `138b44dd3b3481b8c8a5ef648b10e67363178229` 与
  `data/governance/prospective_input_attempt_evidence_20260902.json` 未修改。详见
  [`tencent_quote_field_error_root_cause_audit_20260902.md`](tencent_quote_field_error_root_cause_audit_20260902.md)。

## Superseding current state — 2026-09-02 PR #24 merge and fresh capture blocker

- live Git/GitHub：PR #24 已按批准 exact head
  `e97a6a3c525b497f57aac9cfd751b11f86ca9d5c` squash merge；merge SHA、local `master` 和
  `origin/master` 均为 `05232677055c67b8b87c8d8c3c3b4139df8c477d`；master exact-head
  correctness run `33616552822` 为 `success`；当前无 active product PR。
- formal state：仍为 `development candidate`。corrected candidate、V3 contract、
  B spec SHA、threshold、sector taxonomy 和 `Final OOS=SEALED / UNREAD` 均不变；未
  创建 frozen candidate。
- latest fresh attempt：新的 post-merge `T=2026-09-02` / `T+1=2026-09-03`
  `LIVE_OBSERVED` capture 在 close-window validation 通过后，于 Tencent quote stage
  对 `301686` / `sz301686` 发现 `p[38] (turnover)` empty，返回
  `QuoteFieldError` / `PROVIDER_FAILURE`。该 symbol 的 no-trade/suspension semantics
  未被证明；不与 PR #24 已核验的 `002731` pattern 混同。精确证据为
  [`data/governance/prospective_input_attempt_evidence_20260902_post_merge.json`](../data/governance/prospective_input_attempt_evidence_20260902_post_merge.json)。
- no artifact：universe/sector 的 counts 因异常 runner 未记录，不能猜测回填；stock/index
  Kline、market_env、READY `GenerationInputManifest`、B、package、Drive recovery 和
  candidate list 均 `NOT_REACHED`/`NOT_CREATED`；`data/prospective_inputs/` 不存在。
- current decision：`FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_PROVIDER_FAILURE`；
  current P1 `P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE` 仍未解除。停止于该
  correctness blocker，不自动重试，不修改 frozen strategy/protocol/registry，不启动
  Kline 停牌语义 decision，也不执行任何被禁止的 research/production path。

## 2026-09-02 — User tradability eligibility adopted

- 新增产品约束：`USER_TRADABILITY_ELIGIBILITY_NON_ST_V1`。它是 evaluator 完成后的
  final candidate eligibility，使用 T-close HiThink universe 的 provider `name`；
  `*ST`/`ST` prefix（trim + case-insensitive）标记为 `INELIGIBLE_ST`，不做 fuzzy
  matching。
- ST 不从 acquisition universe 删除，也不跳过 quote/Kline/manifest completeness；
  B evaluator、spec、threshold、score、strategy identity、历史 development evidence
  和 universe scope 均未改变。该规则不是 B alpha filter，不改变历史 performance claim。
- final watchlist 只输出 `final_non_st_qualified`；run manifest/`DevelopmentRunResult`
  同时报告 `b_raw_qualified_count`、`st_excluded_count`、
  `final_non_st_qualified_count` 和 symbol/name exclusion audit list。
- 该产品约束不解除当前 Tencent quote blocker；当前 formal state 仍为
  `development candidate`，P1 prospective T-close input instance 仍未通过。

## Superseding current state — 2026-09-02 listing eligibility source audit

本轮对第三次 `2026-09-02` capture 暴露的 `301686 / sz301686 / p[38] turnover empty`
进行了 bounded root-cause audit。任务分类为 `correctness blocker`，研究退出为
`NEEDS_MORE_EVIDENCE`，最终 stop state 为
`TRADABLE_UNIVERSE_LISTING_ELIGIBILITY_SOURCE_DECISION_REQUIRED`。

诊断严格限定为 exact `301686` 的 HiThink `/api/meta/tickers/list` current-only
读取，标记为 `CURRENT_ONLY_DIAGNOSTIC_NOT_PROSPECTIVE_EVIDENCE`；没有复用 response
构造 formal input、package、watchlist 或 capture，也没有读取或修改
`data/validation/continuous_speed_probe/`。HiThink provider timestamp 为
`2026-09-02T16:00:18.945+08:00`，exact row 为
`{"thscode":"301686.SZ","ticker":"301686","name":"中塑股份","exchange":"SZ","asset_type":"a-share","currency":"CNY"}`。

该 endpoint 实测 raw schema 只有 `thscode`、`ticker`、`name`、`exchange`、
`asset_type`、`currency`，没有 listing date/status、delisting/trading/market status
或其他可作 as-of eligibility 的字段。因此 HiThink row 只能证明 `301686` 是 SZ
A-share metadata record，不能 deterministic 证明其在 `2026-09-02` 已上市。任务输入
中的外部事实支持 root-cause direction
`PRE_LISTING_SECURITY_INCORRECTLY_INCLUDED_IN_TRADABLE_UNIVERSE`，但当前 provider
source 不足以安全实现过滤；不修改 `_build_universe()`，不 hard-code、猜测或建立
第二套 listing engine。

当前 formal Delivery Ladder 仍为 `development candidate`，现有
`USER_TRADABILITY_ELIGIBILITY_NON_ST_V1` 仍位于 B evaluator 后的最终 user-facing
层；ST 不从 acquisition universe 删除。若后续 source decision 通过，已上市停牌
`002731` 保留，只有被 deterministic 证明为 T 日未上市的 `301686` 才排除。本轮未
形成 listing fix、未重跑 formal capture、未 push PR、未创建新 frozen registry record。

## Superseding current state — Official exchange listed-roster correction — 2026-09-02

本轮 Sol 已批准 source decision：`USE_EXCHANGE_OFFICIAL_LISTED_ROSTER_VIA_EXISTING_AKSHARE`。
任务分类为 `correctness blocker`；任务分类未改变，不启动策略研究、Phase 2F、C、Final
OOS、prospective returns、调参、promotion 或 formal capture。

- HiThink `/api/meta/tickers/list` 继续作为 broad SH/SZ A-share metadata source；
  `EXCHANGE_OFFICIAL_CURRENT_LISTED_ROSTER_V1` 使用现有 AkShare 的
  `stock_info_sh_name_code("主板A股")`、`stock_info_sh_name_code("科创板")` 和
  `stock_info_sz_name_code("A股列表")`。SSE source URL 为
  `https://www.sse.com.cn/assortment/stock/list/share/`；SZSE source URL 为
  `https://www.szse.cn/market/product/stock/list/index.html`。
- canonical universe：两路 source 的 exact six-digit symbol intersection，listing
  date 必须 canonical parse 且 `listing_date <= as_of_date`。官方 roster unavailable、
  missing/invalid required field、duplicate/conflicting symbol 均 fail closed；不回退到
  HiThink-only，不做 fuzzy name reconciliation。
- manifest/provenance：保存 AkShare package version、exact API/argument/URL、SSE main /
  STAR / SZSE row counts、canonical combined/eligible counts、content/semantic SHA-256、
  HiThink-only/roster-only mismatch counts/lists；roster identity进入现有 provider
  metadata、input fingerprint 和 candidate-bound generation identity。
- semantic result：被官方 evidence 证明为 T 日未上市或不在 roster 的 301686 在 quote/Kline
  前排除；已上市停牌 `002731` 保留在 acquisition universe。ST/*ST 仍只由既有
  `USER_TRADABILITY_ELIGIBILITY_NON_ST_V1` 在 B evaluator 后排除。
- current formal product state：仍为 `development candidate`；当前 Tencent quote
  blocker 和 P1 `P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE` 不因本 fix 自动解除；
  formal capture 未重跑，Final OOS 仍 `SEALED / UNREAD`，没有新 frozen artifact。
- implementation state：listing fix 与 focused tests 已加入当前本地分支；三次失败 evidence
  和旧治理记录保持 immutable；未跟踪的本地 validation probe 保留但不纳入本次 PR。
- stop state：实现、全量验证、push 和单个 PR 的 exact-head CI 完成后，停在
  `TRADABLE_UNIVERSE_EXCHANGE_ROSTER_FIX_PR_READY_FOR_USER_MERGE_DECISION`；不 merge。

## Superseding current state — PR #25 ready for user merge decision — 2026-09-02

官方 exchange-roster correction 已完成本地验证并推送到 PR #25；本段只更新 live
governance snapshot，不改变 formal product/research state。

- PR #25：`https://github.com/EFSing/ashare_watchlist/pull/25`，pre-reconciliation
  head=`105acc9d9772539a3f799faf90bef14a83f83152`，base=
  `05232677055c67b8b87c8d8c3c3b4139df8c477d`。
- 已核验 pull_request exact-head correctness run `33624209979`=`success`；PR 状态为
  `open`、`mergeable=true`、`mergeable_state=clean`。随后只追加 governance-only
  snapshot；新 head 的 CI 需以实时 GitHub 状态核验，不能把 self-referential run 写回同一
  commit。
- local validation：full pytest `240 passed`，compileall PASS，JSON/hash/governance
  validation PASS，`git diff --check` PASS；frozen registry、strategy、B/spec/threshold/
  score、Tencent parser 未改变；formal capture 未重跑。
- final stop：保持 PR #25 open，不 merge，等待 user merge decision；Formal Delivery Ladder
  仍为 `development candidate`，当前 P1 prospective input blocker、Final OOS
  `SEALED / UNREAD` 和所有既有 deferred 状态不变。

## Superseding current state — PR #26 merge and stock-Kline suspension blocker — 2026-09-02

Formal Delivery Ladder 仍为 `development candidate`。PR #25 的旧 open 快照已由 live
Git/GitHub 状态纠正：PR #25 已 squash merge 到
`f0c1fe56972fe1d1d3db99dd51f75ae9b75e1b74`。随后批准的 PR #26 exact head
`1e736979f394401f5fab2e38caa39408cdc1377b` 已 squash merge，真实 merge SHA 为
`7bd620e72daac1c8239daa982e958edab94fd236`；merge-after master correctness run
`33646931153` 为 `success`，local master 与 origin/master 一致。

实时 BJT 仍为 2026-09-02，fresh `T=2026-09-02` / `T+1=2026-09-03` formal
`LIVE_OBSERVED` capture 已启动，但在首个 exact stock-Kline blocker 停止，没有创建
partial package/output。`002731.SZ` 的 HiThink 非空历史为 330 根、最后交易 bar 为
`2026-08-31`；Tencent T 日 quote 是合法 no-trade snapshot。当前分类为
`correctness blocker`，根因为 stock-Kline suspension/as-of semantics，非 provider
malformation、quote parser、listing/universe、manifest identity 或 B bug。

当前 correctness fix 分支为 `codex/stock-kline-suspension-asof-20260902`，实现并测试：
股票 Kline 非空且允许 `last_bar_date <= T`、拒绝 future bar；index 仍必须最后一根为
T，minimum 仍为 21；B 仍保持 `<120 -> INSUFFICIENT_DATA`。focused tests `94 passed`，
full pytest `249 passed`，compileall PASS；尚未 push 新 PR。当前 P1
`P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE` 仍未解除，Final OOS 仍
`SEALED / UNREAD`，formal capture、package、Drive recovery 和 frozen-candidate audit
均停在该修复 PR 决策前。

## Superseding live state — PR #27 stock-Kline correctness fix — 2026-09-02

- PR #27：`https://github.com/EFSing/ashare_watchlist/pull/27`，base=
  `master@7bd620e72daac1c8239daa982e958edab94fd236`，pre-governance head=
  `028d6e33b1411b6d0d52188427aaccf988882e07`；PR 为 `OPEN`/`MERGEABLE`，reviews 为空，
  未进行 self-approval。
- pull_request exact-head correctness `33649816076` 与 push run `33649783681` 均为
  `success`，精确对应上述 head。本节追加的 governance-only commit 会推进 PR head；
  新 head 的 CI 需由 live GitHub 状态重新核验。
- fix scope：stock Kline 的合法非空真实历史允许 `last_bar_date <= T`，HiThink 与
  Tencent fallback 一致；future bar、schema、OHLCV、duplicate、coverage 仍 fail closed；
  index 仍要求 T 日 bar。B、260 retrieval target、`<120 -> INSUFFICIENT_DATA`、index
  minimum `21`、official-roster 和 non-ST final boundary 均保持不变。
- verification：focused `95 passed`，full pytest `250 passed`，compileall、`git diff --check`
  和 JSON/hash/governance validation PASS。formal capture 在 `002731.SZ` suspension/as-of
  blocker 停止，未生成 evaluation、manifest、candidate list、package 或 Drive backup。
  Final OOS=`SEALED / UNREAD`；C、Phase 2F、prospective returns、tuning、auto-freeze、
  promotion=`NOT_RUN`。新 head CI 成功后停在
  `NEW_CORRECTNESS_FIX_PR_READY_FOR_USER_MERGE_DECISION`，不 merge。

## Superseding execution state — PR #27 narrow no-trade gate and downstream diagnostic — 2026-09-03

- grace window：至 `2026-09-03T08:00:00+08:00`；T=`2026-09-02`、T+1=`2026-09-03`，
  all trading-state data remains anchored to T. Diagnostic-only chain requested
  `observed_at_bjt=2026-09-02T23:59:52.143765+08:00` and is not formal evidence.
- PR #27 technical head before this governance update=`474f1e78f9db856f5cd6813f78479bbe5bb5e317`，
  base master=`7bd620e72daac1c8239daa982e958edab94fd236`；push CI `33651616418` and
  pull_request CI `33651627289` both success. This governance-only update advances the
  head and requires a fresh live exact-head CI check.
- contract correction：ordinary traded stock requires `last_bar_date == T`; only a complete
  canonical T-date Tencent no-trade quote can authorize a non-empty real stock history whose
  last bar is `< T`. No synthetic/forward-filled bars; future/schema/OHLCV/duplicate/coverage
  failures remain fail-closed; index remains T-date strict. B and all retrieval/universe/ST
  semantics remain unchanged.
- downstream diagnostic：the corrected full diagnostic-only chain reached `603356.SH` and
  returned `PROVIDER_FAILURE` with a HiThink `ValueError`. A single-symbol current-only audit
  then succeeded 3/3 times with 376 normalized bars ending `2026-09-02`; its Tencent quote was
  a normal T-date traded quote (`no_trade=false`). Because the failed response was not captured,
  the evidence is `DOWNSTREAM_PROVIDER_FAILURE_NOT_REPRODUCED`; no safe fallback or freshness
  relaxation is justified, and no unrelated fix is bundled into PR #27.
- validation：focused `104 passed`，full pytest `253 passed`，compileall、diff check、
  JSON/hash/governance validation PASS。No formal package, manifest, B/ST evaluation, final
  list, Drive backup/readback or frozen-candidate audit was created; forbidden probe directory
  was not read or changed. Final OOS remains `SEALED / UNREAD`；C、Phase 2F、returns、tuning、
  auto-freeze、promotion=`NOT_RUN`。
- stop after live verification of the new head：
  `NEW_CORRECTNESS_FIX_PR_READY_FOR_USER_MERGE_DECISION`，PR #27 remains open for user merge.

## Superseding current state — 2026-09-03 T-close evidence recovery path

Formal Delivery Ladder remains `development candidate`; no strategy promotion, Final OOS,
Phase 2F, C, returns validation, tuning or auto-freeze was started. PR #27 has since been
explicitly merged at `06ee637d61e7de6df4e0e7145b4ae9e79f40ef49` with successful merge-after
correctness run `33712100053`.

PR #28 (`https://github.com/EFSing/ashare_watchlist/pull/28`) adds the minimum correctness
and product-path fix for volatile T-close evidence: immutable raw/adapter checkpoints with
sidecar provider/version/code-SHA metadata, parse-before-persistence protection, failure
evidence, and resumable per-source/per-symbol acquisition. The final write order is source
evidence → complete generation-input package → existing B development-candidate output;
B/spec/threshold/score/top-N and post-B non-ST eligibility are unchanged. Exact-head run
`33714223690` succeeded for head `5493786b06e055a1506e0e5d845715da7d4d46ac`; PR remains
open pending user merge decision.

The one-time Windows task `Ashare TClose 20260903` is enabled for 15:05 BJT after the
repository XSHG close at 15:00; the calendar-derived next session is `2026-09-04`. Pre-close
diagnostic status was `PRE_CLOSE_DIAGNOSTIC_READY`, credential context was ready, and no
provider call or formal package/output was created before the close. Therefore the P1
`P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE` remains unresolved until the scheduled run
completes with auditable evidence and output. Private Drive backup/readback is not configured
by this runner. The forbidden continuous-speed-probe directory remains untouched.

## Superseding current state — 2026-09-03 recovery stopped at PR #29

Formal Delivery Ladder remains `development candidate`; the task did not enter strategy
promotion, Final OOS, returns validation, C, Phase 2F, tuning or auto-freeze. Live GitHub
confirms PR #28 merged at `43f055e4e8e1a0e1e4a70e41cf8ec10580aab984` and merge-after run
`33720355007` succeeded. The stale PR-open snapshot is therefore resolved as
`PROJECT_GOVERNANCE_STATE_CONFLICT_RESOLVED`.

The actual 2026-09-03 runner captured the volatile source boundary from 15:30:04 through
15:30:57 BJT. HiThink universe, all three official roster sources, exact Sina sector inputs,
all Tencent T-date quote batches and four completed stock-Kline checkpoints are retained;
the initial 170 raw/sidecar pairs passed SHA verification. The run stopped at `000008.SZ`
with HiThink `HTTPError`; a later resume attempt used the existing checkpoints, then its
allowed Tencent qfq fallback failed after three `ConnectionError` attempts. No READY manifest,
package, canonical watchlist or B/ST result exists.

The resume path exposed a concrete persistence correctness blocker: a changed retry response
could collide with an immutable prior response at the same request identity. PR #29 adds only
a deterministic `response_sha256` supplemental identity for changed response bytes and a
regression test; original `UNKNOWN_ORIGIN` sidecars remain unchanged. PR #29 is open against
master, with exact-head correctness run `33736428448` successful and state `CLEAN`/mergeable.
The current stop is
`NEW_CORRECTNESS_FIX_PR_READY_FOR_USER_MERGE_DECISION_T_EVIDENCE_SECURED`; after user merge,
resume starts at `000008.SZ` and must not refetch successful volatile components. Original
runner code provenance remains incomplete, so `FULLY_RECOVERABLE` and frozen-prerequisite PASS
are not claimed. Private Drive remains `NOT_CONFIGURED`; the forbidden probe directory remains
untouched.

## Superseding current state — 2026-09-03 T-close watchlist generated

Formal Delivery Ladder remains `development candidate`. PR #29 is merged at
`af45c8c83cb1a265470bae4693d80cb86708fb76`; merge-after correctness run `33738791786` is
success, and local `master=origin/master` at that SHA. The exact T-close evidence integrity
gate passes for 10,597/10,597 raw/sidecar pairs (`MISSING=0`, `HASH_MISMATCH=0`,
`SIDECAR_INVALID=0`). Original `UNKNOWN_ORIGIN` sidecars remain unchanged; no provenance
attestation or frozen-prerequisite PASS is claimed.

The recovery completed full stock/index inputs, market_env, GenerationInputManifest and the
existing B development-candidate lifecycle. Package status is
`READY_FOR_STRATEGY_EVALUATION`; the canonical watchlist is persisted at
`data/watchlist_20260903.json` with candidate count 0 and no actionable candidate fields.
Run manifest status is `SUCCESS / NO_CANDIDATES`; B raw qualified=0, final non-ST qualified=0,
ST excluded=0, and evaluation counts are `INSUFFICIENT_DATA=2715`, `MATCHED_REJECTED=5`,
`NOT_MATCHED=2495`.

Current terminal is `T_CLOSE_WATCHLIST_GENERATED_POSTPROCESS_BLOCKED`: private Drive
upload/readback is `NOT_CONFIGURED_EXTERNAL_UPLOAD`. The empty generated list is deliverable;
no strategy promotion, Final OOS read, C, Phase 2F, returns validation, tuning, or auto-freeze
was started, and the forbidden continuous-speed-probe directory remains untouched.

## Superseding current status — 2026-09-03 B evaluator wiring correction

Formal Delivery Ladder remains `development candidate`; no Final OOS, returns, C, Phase 2F,
tuning, promotion or auto-freeze was started. The prior 0-candidate status is superseded in
meaning: the formal B package was incorrectly evaluated by A and is
`INVALIDATED_WRONG_EVALUATOR_A_ON_B_INPUT`. The actual product blocker is
`WRONG_EVALUATOR_WIRING_A_ON_B_PACKAGE`, not a valid B zero-candidate market result.

PR #30 (`https://github.com/EFSing/ashare_watchlist/pull/30`) is open for user merge decision,
based on `master` at `1639bfeb22e043055a4c30804a0d40e82c94eff5`, with code head
`ac801969653ae49c82b8c6d202fac25d307def68`; live GitHub reported `CLEAN`/mergeable and
exact-head correctness run `33760664379` success. The governance snapshot itself advances
the head and needs a new exact-head CI check.

The same READY package was reused without provider refetch: file SHA
`a2e6da0865ff20316e4d9074f26e2cb3ba53995d2cb3e83a49f8c82988c0b38a`. Deterministic B replay
is exact: `INSUFFICIENT_DATA=42`, `NOT_MATCHED=5115`, `MATCHED_REJECTED=46`,
`QUALIFIED_LEGACY_BASELINE=12`, total `5215`; post-B
`USER_TRADABILITY_ELIGIBILITY_NON_ST_V1` excludes one ST and leaves 11 final non-ST candidates.
The full candidate details are delivered in the task response under
`DIAGNOSTIC_B_REPLAY_FROM_FORMAL_20260903_PACKAGE`.

Controlled supersession retained the original canonical bytes/SHA
`ca8cba86527550d7ba10d05083bb1c7523b54ccf8c9ecb34ef10152b8fced1fb`, A identity, formal run
`FFu4MlWYdPwSFrjFJ52Ak2-X2Z0a5-aOWrkdI74Azrc`, and original run manifest SHA
`7bd047bb57dfb986de0a5bb71a9a44c8cbf5517098a6a2501770199fad34fc11` under the existing
development-candidate invalidated evidence path. Corrected local B output now occupies
`data/watchlist_20260903.json` with SHA
`50f0717e55daaf4435e1d25b4f1d029109c566d72d63a1fc566f263cdf0fb085` and 11 candidates; it is
diagnostic/development output only, not promotion or Final OOS.

Validation is complete for the code head: focused `18 passed`, full pytest `261 passed`,
compileall, JSON/hash validation and `git diff --check` passed. No B strategy semantics,
thresholds, score, Top-N, ST rule, provider acquisition, universe, sector or Kline policy was
changed. The forbidden `data/validation/continuous_speed_probe/` directory remains untouched.
Current status is `B_EVALUATOR_WIRING_FIX_PR_READY_FOR_USER_MERGE_DECISION` pending the final
post-governance exact-head CI verification and user merge decision.

## Final delivered status — 2026-09-04

PR #30 has been squash-merged by explicit user authorization at
`9a57c2525c2e621ad568c59940ac2512e575b077`. The merge-after master correctness CI is
`33782477205`, `success`, with an exact-head match. This is the completed correction for
`WRONG_EVALUATOR_WIRING_A_ON_B_PACKAGE`; the merge-time base was
`master@1639bfeb22e043055a4c30804a0d40e82c94eff5`.

The immutable 2026-09-03 package was SHA-verified as
`a2e6da0865ff20316e4d9074f26e2cb3ba53995d2cb3e83a49f8c82988c0b38a` and reused without any
provider refetch. Merged-master deterministic B regeneration is exact:
`INSUFFICIENT_DATA=42`, `NOT_MATCHED=5115`, `MATCHED_REJECTED=46`,
`QUALIFIED_LEGACY_BASELINE=12`, total `5215`; raw qualified `12`, ST excluded `1`
(`000632 / ST三木`), final non-ST `11`.

Corrected canonical `data/watchlist_20260903.json` is SHA
`50f0717e55daaf4435e1d25b4f1d029109c566d72d63a1fc566f263cdf0fb085` and contains the 11
post-`USER_TRADABILITY_ELIGIBILITY_NON_ST_V1` B candidates. It is retained as a
development-candidate result marked `DIAGNOSTIC_B_REPLAY_FROM_FORMAL_20260903_PACKAGE`, not
Final OOS, production promotion, auto-freeze, or external upload.

The old A zero-output remains auditable under the existing invalidated lifecycle with status
`INVALIDATED_WRONG_EVALUATOR_A_ON_B_INPUT`, original SHA
`ca8cba86527550d7ba10d05083bb1c7523b54ccf8c9ecb34ef10152b8fced1fb`, A identity,
formal run `FFu4MlWYdPwSFrjFJ52Ak2-X2Z0a5-aOWrkdI74Azrc`, and unchanged original run manifest
(SHA `7bd047bb57dfb986de0a5bb71a9a44c8cbf5517098a6a2501770199fad34fc11`).

Final terminal status is `T_CLOSE_WATCHLIST_GENERATED_POSTPROCESS_BLOCKED`.
Drive/readback is `NOT_CONFIGURED_EXTERNAL_UPLOAD`; frozen prerequisite is
`NOT_READY / PARTIAL_UNVERIFIED`. The forbidden continuous-speed-probe directory and all
B strategy/spec/threshold/score/Top-N/universe/provider/Kline/ST semantics remain unchanged.

## Development diagnostic status — 2026-09-04

Formal Delivery Ladder remains `development candidate`; this research does not promote or block it. `B_PHASE_VOLUME_PATH_DIAGNOSTIC_V1` completed against the corrected B reconstruction with exact reconciliation of 4,041,140 evaluations and all 17,714 qualified identities. Its final decision is `VOLUME_PATH_NEEDS_MORE_EVIDENCE`: small overall relationships exist, but they are non-monotonic and not coherent across the pre-registered structural, year, board and horizon checks. No B rule, threshold, score, hard gate, Top-N, production path or frozen artifact changed. Final OOS, C and Phase 2F remain untouched/not run.

PR #31 is open for user decision at `https://github.com/EFSing/ashare_watchlist/pull/31`. The result head `f62109545d865d7a547d65327e28b07f576253b3` showed `1/1 checks OK` and automatically mergeable at PR creation; the final governance-only successor requires its own exact-head CI. Do not merge automatically.

## Post-merge current status — artifact Drive postprocess verified — 2026-09-04

Formal Delivery Ladder remains `development candidate`. PR #31 was squash-merged by explicit
authorization at `426b230cdaf53546e5efa4e99cda99c9bcccb85a`; its exact merge-head correctness
run is `33858481640`, `success`. The merged PR head was
`1205902f34aa5d057f79a99fdf2c1b2b520e2812`, based on
`79da0f527ad72c8e77693d116338ebc8ab74755f`.

The corrected development watchlist remains
`data/watchlist_20260903.json`, SHA
`50f0717e55daaf4435e1d25b4f1d029109c566d72d63a1fc566f263cdf0fb085`. With explicit user
authorization it was uploaded to the existing private `ashare_watchlist` Drive folder and
read back as raw bytes. Drive file ID is `1N-G0LVvMtotffm5Tdq-2-f4I-fZkuTUq`, size is `6422`
bytes, and the read-back SHA exactly matches the local SHA. The current artifact-level
external postprocess / Drive-readback blocker is therefore resolved. The generic runner
default remains `NOT_CONFIGURED_EXTERNAL_UPLOAD` for future automated runs; no automatic
Drive integration is claimed.

The frozen prerequisite remains `NOT_READY / PARTIAL_UNVERIFIED`, because 170 historical
sidecars still have `UNKNOWN_ORIGIN` code provenance. Drive read-back of this development
output does not establish `FULLY_RECOVERABLE`, does not freeze a candidate, and does not
change the 13/13 frozen artifact registry. The stale pre-merge PR #31-open snapshot has been
superseded by this post-merge governance update; no strategy/product identity conflict was
found.

`VOLUME_PATH_NEEDS_MORE_EVIDENCE` remains final. B spec, score, threshold, hard gate, Top-N,
universe, provider/Kline policy, ST semantics and prospective pipeline are unchanged. Final
OOS remains `SEALED / UNREAD`; C, Phase 2F, promotion and auto-freeze remain not run. The
forbidden `data/validation/continuous_speed_probe/` directory was not read, modified,
deleted, hashed or uploaded. Next gate is the successor governance PR's exact-head CI and
user merge decision.

## 2026-09-05 — Turnover x relative-volume incremental diagnostic gate A

The independent research question `B_TURNOVER_X_RELATIVE_VOLUME_INCREMENTAL_DIAGNOSTIC_V1`
is classified as `DEVELOPMENT` / `RECONSTRUCTED_RETROSPECTIVE` / `DATE_ANCHORED` /
`NO_VINTAGE_PROOF` / `DIAGNOSTIC_ONLY`. Its no-outcome cohort construction reconciled
`4,041,140` evaluations, `573,586` structural first-breakout rows, `17,714` qualified
identities and `5,386` symbols. The canonical RV definition remains
`volume_T / mean(volume[T-20:T-1])` from corrected B shared numeric semantics.

The task stopped at `TURNOVER_RATE_ACQUISITION_NOT_RESEARCH_READY`: primary AkShare
`ak.stock_zh_a_hist` acquisition (`1.18.94`, daily, unadjusted, 20230630--20260828) had
`0/5,386` completed symbols after bounded retries, `11` failed and `5,375` pending due to
`ProxyError / RemoteDisconnected`. Turnover coverage is therefore `NOT_EVALUATED`, no
canonical/raw SHA exists, and no pre-outcome protocol commit or research decision exists.
Outcome analysis was not started. Intake inspected one pre-existing event record only for
artifact-schema identification; no outcome value was used. Final OOS and the forbidden
continuous-speed-probe directory were not used. B, prospective pipeline, frozen inputs/registry and all production boundaries remain
unchanged. Resume evidence and gate-A report are recorded under
`data/validation/b_turnover_x_relative_volume_incremental_v1/` and
`docs/research/b_turnover_x_relative_volume_incremental_v1_report.md`.

## 2026-09-05 — PR #33 merged; post-merge primary probe blocked

PR #33 was live-verified and squash-merged after exact-head CI remained green and the
base/head were unchanged. Merge SHA and current `origin/master` are both
`873169aeecb9eb12d32e58990677f2478f3081c0`; GitHub recorded 2 merge checks passed.
The resume branch is `codex/b-turnover-x-relative-volume-resume-20260905`, based on that
merge-head, with the existing ignored checkpoint/cohort preserved.

The bounded same-primary probe retried `000001.sz`, `000002.sz`, and `000006.sz` once
each using AkShare `1.18.94` / `ak.stock_zh_a_hist` with unchanged daily, unadjusted,
20230630--20260828 parameters. It produced `0` successes and `3` failures, all
`ProxyError` wrapping `RemoteDisconnected`; no HTTP/provider response was received.
Non-empty proxy environment names observed were `ALL_PROXY`, `HTTP_PROXY`, `HTTPS_PROXY`,
and `NO_PROXY` (values not recorded). The full checkpoint remains `0/5,386` completed,
`11` failed, `5,375` pending. The stop gate is
`TURNOVER_PRIMARY_SOURCE_STILL_UNAVAILABLE`.

No provider substitution, source-semantic change, protocol commit, outcome analysis,
Final OOS access, C/Phase 2F, promotion, freeze, or upload occurred. The prior
`SCHEMA_SAMPLE_OBSERVED_NOT_USED` status remains truthful: one schema-only event sample
was observed earlier, but no outcome value entered computation, filtering, feature
selection, or conclusion. `VOLUME_PATH_NEEDS_MORE_EVIDENCE`, B, prospective pipeline,
frozen registry and frozen prerequisite remain unchanged; the forbidden
`data/validation/continuous_speed_probe/` directory remains untouched.

## 2026-09-06 — PR #36 merged; governance reconciliation complete

PR #36 was squash-merged at authorized exact head
`6d5c99114a94fd6c22565a3257a4f6c634192620`, producing merge SHA
`b21d476c16cf4828073843e578e2ee5a9ef8501b`. Live `master` and `origin/master` both point
to that SHA. Merge-head correctness run `33984699289` completed `success` with exact
workflow head SHA.

The prior `PR #36 OPEN/awaiting merge` text was a stale governance snapshot and has been
superseded by this bounded docs-only reconciliation. No strategy evaluator, outcome table,
Final OOS or new provider was read; B, the prospective observation protocol, the four-family
shortlist, recommendation and methodology principles remain unchanged. Formal Delivery
Ladder remains `development candidate`; next stop is user candidate selection.

## 2026-09-06 — PR #36 epistemic methodology amendment

Formal Delivery Ladder, B state and the B prospective protocol remain unchanged. The new
strategy intake now adopts `FEATURE_EPISTEMIC_SEPARATION`: `DEFINITION_AND_PROXY_CLAIM`,
`PREDICTIVE_EVIDENCE`, and `MECHANISM_EVIDENCE` are separate evidence layers. It also
requires `ALTERNATIVE_EXPLANATIONS_REQUIRED`, `SIMPLE_BASELINE_REQUIRED`,
`FALSIFICATION_CRITERIA_REQUIRED`, and `CAUSAL_LANGUAGE_RULE` before future candidate
outcome access.

The four-candidate shortlist and recommendation are unchanged. In particular,
`NEW_CROSS_SECTIONAL_RELATIVE_STRENGTH_LEADERSHIP_V1` is observable cross-sectional
trailing relative-return leadership with `PREDICTIVE_EVIDENCE=UNTESTED` and
`MECHANISM_EVIDENCE=HYPOTHESIS`; future research must distinguish incremental leadership
information from generic momentum and other exposure explanations using a simple baseline.

This is a no-outcome documentation amendment: no candidate evaluator, threshold, replay,
forward outcome, C return, Final OOS or new provider was used. B, turnover/RV, Volume-Path,
frozen state and the forbidden directory remain unchanged.

## Final live PR snapshot — 2026-09-06

PR #36 is open at
[`https://github.com/EFSing/ashare_watchlist/pull/36`](https://github.com/EFSing/ashare_watchlist/pull/36),
base `master@380313c94fdfe388157d5274c4636806d2fa9647`, head
`299def1d996994b4a7fffc9997dca73681b4ff4b`, and GitHub reports `MERGEABLE/CLEAN`.
Push correctness run `33983380604` and pull_request correctness run `33983382506` both
completed `success` with exact head matching. This PR is not merged.

No prospective observation data store has been created yet. The protocol is bound to
`3dd7d51a6341a60540c26db2aa4f18367520d95b`; no C/new-candidate outcomes, Final OOS or
forbidden-directory contents were read. The next user decision remains
`NEW_STRATEGY_CANDIDATE_SELECTION_REQUIRED`.

## 2026-09-05 — Phase 2 full subprocess env proxy bypass probe: no-proxy stop gate

The second bounded probe ran the same primary AkShare `1.18.94` /
`ak.stock_zh_a_hist` source and fixed daily, unadjusted, 20230630--20260828
parameters for `000001.sz`, `000002.sz`, and `000006.sz` inside a transient
subprocess whose `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` (and lowercase
equivalents) were removed and whose `NO_PROXY` was set to
`push2his.eastmoney.com`. No system proxy, registry, persistent user
environment, or Git/pip proxy change occurred, and no proxy value was recorded.

Result: `0/3` success. All three symbols failed with outer `ConnectionError`,
underlying `MaxRetryError`, and a chain ending in `WinError 10013` (direct
socket access denied); no HTTP status and no provider response were received.
Because the outer class is not `ProxyError` and no response layer was reached,
the proxy bypass is confirmed effective and the remaining failure is a direct
connection-layer block to the Eastmoney endpoint.

The task stops at `TURNOVER_PRIMARY_SOURCE_UNAVAILABLE_AFTER_NO_PROXY_PROBE`.
No provider substitution, endpoint/source semantic change, pre-outcome protocol
commit, or outcome analysis occurred. Checkpoint state is unchanged at
`0` completed, `11` failed, `5,375` pending of `5,386`; raw/canonical SHA
`NOT_CREATED`; coverage `NOT_EVALUATED`. Summary/report evidence was refreshed
with the new gate. `SCHEMA_SAMPLE_OBSERVED_NOT_USED` remains truthful and
`VOLUME_PATH_NEEDS_MORE_EVIDENCE`, B, prospective pipeline, frozen registry and
frozen prerequisite remain unchanged; Final OOS remains `SEALED / UNREAD`, and
the forbidden `data/validation/continuous_speed_probe/` directory was not read,
modified, deleted, hashed or uploaded.

## 2026-09-05 — Tushare-compatible gateway diagnostic complete

The independent turnover × relative-volume research task was resumed only after
explicit user authorization for a bounded `THIRD_PARTY_TUSHARE_COMPATIBLE_GATEWAY`.
The formal Delivery Ladder remains `development candidate`; this diagnostic does
not promote or block the existing usable path.

The fixed source contract is `https://tuaremax.top`, `tushare==1.4.24`, endpoint
`daily_basic`, fields `ts_code,trade_date,turnover_rate,float_share`. It is not
official Tushare, has `NO_VINTAGE_PROOF`, and is not production validated. The
environment token was never persisted, printed, hashed or uploaded. The prior
AkShare evidence remains preserved and was not overwritten.

The five-date pilot passed: coverage was `24,941/24,941`, and the fixed 500-row
turnover semantics sample was `500/500` within tolerance with median provider /
implied ratio `0.9999992421`. Full acquisition then completed `769/769` frozen
sessions with zero failed or pending dates. The gateway canonical has `3,938,059`
rows sorted by `symbol,date`; raw and canonical hashes are recorded in the
gateway manifests and checkpoint. Full raw responses remain local resumable
evidence because of their size.

The input audit preserved exact reconciliation of `17,714` qualified and
`573,586` structural rows. Under the fixed Main/ChiNext/STAR boundary, the
in-scope counts are `17,008` and `543,616`; qualified and structural coverage,
all major years and boards, are `100%`. Missing, null, negative and extreme
turnover checks passed with no imputation.

The pre-outcome protocol was committed at
`1148ebd23a567ad81e09b0c2323f9be285920858` before outcome analysis. The final
research decision is `TURNOVER_X_RELATIVE_VOLUME_NEEDS_MORE_EVIDENCE`: turnover
5D Q5-Q1 mean spread is `-0.277596pp` and rho is `-0.058525`, but the fixed
turnover-after-RV spreads are not directionally coherent and year/board
coherence does not pass. This is evidence for further bounded research only,
not a rule or parameter change.

Final OOS remains `SEALED / UNREAD`; B/spec/score/threshold/hard gates/Top-N/
prospective pipeline/universe/frozen dataset are unchanged. C, Phase 2F,
threshold search, model fitting, freeze and promotion were not run. The next
delivery state is an independent research PR awaiting exact-head CI and user
merge decision.

## 2026-09-05 — PR #34 merged and verified

The previous pre-merge snapshot has been superseded by the live merged state.
PR #34 was squash-merged from exact head
`65d7a8329f012394b9fce6a9aad42f5834dc84e6` into
`master@873169aeecb9eb12d32e58990677f2478f3081c0`, producing merge SHA
`2d601360b5160739ec91400175df345f84cd2b95`. GitHub reports PR #34 as
`MERGED`; live `master` and `origin/master` both point to that SHA.

The merge-head correctness workflow is run `33971522763`; its workflow head
SHA exactly equals the merge SHA and its conclusion is `success`. The completed
research decision remains
`TURNOVER_X_RELATIVE_VOLUME_NEEDS_MORE_EVIDENCE`. The pre-registered joint
top-1% check is turnover N=`171`, RV N=`171`, joint intersection N=`11`.
The pre-outcome protocol SHA remains
`1148ebd23a567ad81e09b0c2323f9be285920858`.

This remains `DEVELOPMENT` / `RECONSTRUCTED_RETROSPECTIVE` / `DATE_ANCHORED` /
`NO_VINTAGE_PROOF` / `THIRD_PARTY_GATEWAY` / `DIAGNOSTIC_ONLY`, using the
`THIRD_PARTY_TUSHARE_COMPATIBLE_GATEWAY`. B/spec/score/threshold/hard gate/
Top-N/prospective pipeline/universe/frozen dataset/frozen registry remain
unchanged. Final OOS remains `SEALED / UNREAD`; C, Phase 2F, promotion,
freeze and auto-freeze were not run. The prior governance conflict was resolved
by a bounded docs-only reconciliation; no research, protocol, data or
production files were changed.

## 2026-09-06 — B V1_1 observation protocol and no-outcome strategy intake

Formal Delivery Ladder remains `development candidate`. B is unchanged:
`B_BREAKOUT_RETEST_LEGACY_V1_1`, spec SHA
`f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd`, including match,
first qualifying breakout, pullback, hard gates, support/stop/target/RR/overhang/score,
`score_cutoff=None`, `top_n=None`, universe and prospective generation path. The completed
diagnostic decisions `VOLUME_PATH_NEEDS_MORE_EVIDENCE` and
`TURNOVER_X_RELATIVE_VOLUME_NEEDS_MORE_EVIDENCE` remain unchanged.

Track A adopted the one-time `B_V1_1_PROSPECTIVE_OBSERVATION_PROTOCOL_V1`; its pre-outcome
protocol/semantics commit is
`3dd7d51a6341a60540c26db2aa4f18367520d95b` and its store is a future-only,
append-only calendar-time stream under `data/prospective_observation/b_v1_1/`. The primary
cohort starts at the first real post-commit XSHG T-close signal date; prior watchlists are
not backfilled. Signal-level records and deterministic episode-deduplicated records are
both retained. Mature outcomes are appended separately with explicit execution feasibility;
the protocol never claims a reference open was an actual fill. Fixed checkpoint is 60
completed XSHG signal sessions AND 200 mature independent episodes, with a 120-session
maximum window and no early stop for good performance.

Track B is a separate `NO_OUTCOME_CANDIDATE_INTAKE`. The shortlist is in
[`docs/research/new_strategy_candidate_intake_v1.md`](research/new_strategy_candidate_intake_v1.md).
It contains exact-provenance `C_MAIN_TREND_RETEST_LEGACY_V1` plus three explicitly marked
new hypotheses. Recommended candidate is
`NEW_CROSS_SECTIONAL_RELATIVE_STRENGTH_LEADERSHIP_V1`; secondary is
`NEW_VOLATILITY_CONTRACTION_BREAKOUT_V1`. No candidate evaluator, threshold, forward return,
Final OOS, or new provider was used.

Current stop marker: `NEW_STRATEGY_CANDIDATE_SELECTION_REQUIRED`. Frozen state remains
unchanged; Final OOS remains `SEALED / UNREAD`; the forbidden
`data/validation/continuous_speed_probe/` directory remains untouched.

## Superseding current state — VCB V1 research complete — 2026-09-06

用户已正式选择 `NEW_VOLATILITY_CONTRACTION_BREAKOUT_V1`，并完成独立 DEVELOPMENT
retrospective research。研究 branch 为
`codex/new-volatility-contraction-breakout-v1`，reconciled master base 为
`44544b831dfb12bc03bbc9efab49704f095cce1d`；pre-outcome protocol semantic commit 为
`411c72b1eff27ecb1ecfb125818837b6aa4a313c`，Final OOS 保持 `SEALED / UNREAD`。

Input audit PASS：769 个 XSHG sessions、2023-06-30 至 2026-08-28、4,041,140 个 date-symbol
identities，validated `HISTORICAL_T_ANCHOR_PRICE_RAW_VOLUME`，`NO_VINTAGE_PROOF`。
固定 signal pass 产生 195,464 generic breakouts、21,988 candidates、173,476 primary
controls；both-group readiness 751 dates，gate PASS。

固定 DEVELOPMENT outcome 结果：10D date-equal candidate-control spread `+0.453824pp`，
95% moving-block-bootstrap CI `[-0.381482,+1.349478]`；continuous compression rho
`+0.110340`；5D spread `+0.326237pp`；10-session cooldown spread `+0.046626pp`
且 CI 跨零；2023–2025 sign positive、2026 negative。固定 decision 为
`VOLATILITY_CONTRACTION_BREAKOUT_NEEDS_MORE_EVIDENCE`，不是 promotion、freeze、causal
mechanism proof 或 production alpha。

Focused tests `13 passed`，full pytest `315 passed`（pinned project venv + short basetemp），
compileall、JSON/schema/hash validation 和 `git diff --check` 均通过。当前终态为
`VCB_RESEARCH_PR_READY_FOR_USER_MERGE_DECISION`；等待独立 PR exact-head CI 和 user merge
decision。B、B prospective observation、RS、Volume-Path、turnover/RV、frozen state 均不变；
C、controlled reversal、Final OOS 和受禁目录未读取。

## Post-merge current state — VCB PR #38 merged — 2026-09-06

PR #38 已在 live head 精确为
`2d5d61f319a2a1af84bbd58c2997ca3b07218e8e` 时 squash-merged。新的 canonical master 为
`0571d57d5741faa689922c9f3a7d5c73c04772fb`；master correctness run
`34024991541` 为 `success`，workflow head SHA 与该 merge SHA 精确匹配。

本次仅做 post-merge governance reconciliation。VCB fixed decision
`VOLATILITY_CONTRACTION_BREAKOUT_NEEDS_MORE_EVIDENCE`、protocol、signal/outcome artifact、
B、B prospective observation、RS、Volume-Path、turnover/RV、frozen state 均未改变。没有
启动另一候选、没有读取 Final OOS、没有调参、promotion、freeze 或生产路径变更；受禁目录
保持 untouched。当前终态：`VCB_RESEARCH_MERGED_MASTER_VERIFIED`。

## Superseding current state — CRSR V1 research complete — 2026-09-06

用户正式选择 `NEW_CONTROLLED_RIGHT_SIDE_REVERSAL_V1`，完成独立 DEVELOPMENT
retrospective research。研究问题是：在相同 T-1 downside-extreme state、相同 positive
T-day bounce baseline、并控制 T-day bounce magnitude 后，strict prior-5-close reclaim
是否有未来增量信息。该研究不是 old D reconstruction、恢复或替代。

Protocol commit=`123ef5299ef94411a0b1cb4ec5745ee2c472979e`。Input audit PASS：769 个
continuous XSHG sessions、4,041,140 个 historical PIT identities、validated
`HISTORICAL_T_ANCHOR_PRICE_RAW_VOLUME`、`NO_VINTAGE_PROOF`。Signal readiness PASS：candidate
121,698、primary control 250,506、full downside-bounce baseline 372,204、downside
shared-bounce-bin dates 765。

固定 DEVELOPMENT outcome：primary stratified 10D spread=`-0.079350pp`，median=`-0.232037pp`，
95% 20-session moving-block CI=`[-0.495382,+0.403562]`；continuous reclaim-margin rho
mean=`-0.025847`；5D stratified spread=`-0.155740pp`；context interaction mean=`-0.023253`；
10-session cooldown spread=`+0.047685pp`，CI crosses zero；2023/2024/2025 primary sign negative、
2026 positive。Candidate/control usable 10D coverage 为 98.31% / 98.15%，coverage gate PASS。

固定 decision：`CONTROLLED_RIGHT_SIDE_REVERSAL_NO_CLEAR_INCREMENTAL_SIGNAL`。这不是 causal
proof、mechanism proof、production alpha、frozen candidate 或 Final OOS validation；不启动
volume/turnover/RSI/MACD/MA/sector/board/window/horizon rescue。B、B prospective observation、
RS、VCB、Volume-Path、turnover/RV、frozen state 和 production semantics unchanged；C unread；
old D not reconstructed；Final OOS remains `SEALED / UNREAD`；forbidden directory untouched。

当前正式层级仍为 `development candidate`，CRSR 仅为独立 research artifact，不改变 production
路径或现有 decisions。当前停止标记：`CRSR_RESEARCH_PR_READY_FOR_USER_MERGE_DECISION`；等待
独立 PR exact-head CI 和用户 merge decision。

## CRSR V1 PR exact-head CI verified — 2026-09-06

独立 PR #39（`research: controlled right-side reversal V1`）已创建，live base 为
`36f8120651e8f6a0d66e1d97769dc7c6d8a66e7b`，live head 为
`58832ac4b8deeb23e28a165232656d0567df9d81`。push run `34030857382` 与 pull-request run
`34030876254` 均成功，workflow head SHA 均精确匹配该 PR head；GitHub 状态为 `OPEN / CLEAN`。

正式 research decision 仍为 `CONTROLLED_RIGHT_SIDE_REVERSAL_NO_CLEAR_INCREMENTAL_SIGNAL`，
不改变 `development candidate` 层级、production path 或其他 preserved strategy。当前终态：
`CRSR_RESEARCH_PR_READY_FOR_USER_MERGE_DECISION`，不自动 merge，等待用户决定。
