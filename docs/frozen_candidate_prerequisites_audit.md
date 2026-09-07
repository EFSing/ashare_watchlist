# Frozen Candidate Prerequisites Audit V1

更新时间：2026-08-30（Asia/Shanghai）

> 本文件的 V1 审计、V1/V2 contract、old spec、旧 blocker、失败 attempt 和旧 decision
> 均保留为 historical evidence；当前治理解释以末尾的 superseding current section 为准。

## 1. 研究问题、范围与停止条件

研究问题：在 development eligibility 已完成后，当前项目是否已经具备一个可以
进入 frozen candidate gate 的真实 strategy candidate？

materiality：这个判断决定项目能否从 `development candidate` 进入下一层。它不是
对 A 股收益、参数或新 research hypothesis 的扩展研究，也不授权读取 Final OOS、
Phase 2F、调参或 strategy promotion。

输入证据：[`PRODUCT_CHARTER.md`](PRODUCT_CHARTER.md)、
[`generation_input_contract.md`](generation_input_contract.md)、
[`development_candidate_contract.md`](development_candidate_contract.md)、
[`strategy_candidate_nomination_v1.md`](strategy_candidate_nomination_v1.md)、
[`strategy_candidate_eligibility_report.md`](strategy_candidate_eligibility_report.md)、
[`candidate_bound_prospective_input_contract_v1.md`](candidate_bound_prospective_input_contract_v1.md)、
[`FROZEN_ARTIFACT_POLICY.md`](FROZEN_ARTIFACT_POLICY.md)、
[`data/governance/frozen_artifacts.json`](../data/governance/frozen_artifacts.json) 和
PR #12 的 development-candidate regression evidence。

停止条件：一旦候选资格和当前最小 prerequisites 缺口可以判断，不继续切分指标、
优化参数或扩大 research scope。

## 2. Decision

**`FROZEN_CANDIDATE_BLOCKED`**

唯一剩余阻塞原因：

**`P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE`**

B 已经通过冻结的 `STRATEGY_DEVELOPMENT_ELIGIBILITY_V1`，因此它是获资格进入
prerequisites 的 candidate；但尚未出现首个真实 candidate-bound、
`LIVE_OBSERVED`、`known_at <= T` 的 prospective T-close input instance。不能用
retrospective DEVELOPMENT artifact 或 contract 文档替代该 instance。

因此本审计仍不创建也不宣称满足 `FROZEN_CANDIDATE_CONTRACT_V1`。已定义的
`CANDIDATE_BOUND_PROSPECTIVE_INPUT_PROVENANCE_CONTRACT_V1` 只是下一次真实输入的
验收 contract，不是已发生的 prospective evidence。

## 3. Product infrastructure audit

下表的 PASS 只表示既有 development product path 已有受控证据；它不等价于
production readiness。

| prerequisite | 结论 | 证据与边界 |
| --- | --- | --- |
| deterministic generation | `PASS`（development scope） | PR #12 的 deterministic generation、canonical output、immutable version 与 output identity 回归。 |
| canonical output | `PASS`（development scope） | schema-valid watchlist、zero-candidate success、downstream ingest 回归已覆盖。 |
| complete generation identity | `PASS`（development scope） | fingerprint 覆盖 contract/schema、strategy identity、实际 names、canonical market_env 和 output-affecting inputs。 |
| fail-closed | `PASS`（development scope） | READY、evaluator failure、缺名字、非法/冲突输出和 write failure 均有明确失败路径。 |
| monitoring / rollback | `PASS`（development scope） | schema、output SHA、immutable provenance、known-good rollback 与 HEALTHY monitor 有回归。 |
| T close / T+1 | `PASS`（contract scope） | `Asia/Shanghai`、XSHG session close、下一交易日 T+1 和错误时 fail closed 已冻结；B 的真实 prospective instance 尚未发生。 |
| artifact recovery | `PASS`（现有 artifact scope） | Phase 2E registry required artifacts hash/recovery 已核对；daily_k 为 `FULLY_RECOVERABLE`。 |

结论：产品基础支持 `development candidate`，B 的 eligibility 也已通过，但 frozen
candidate 仍需要首个真实候选绑定的 prospective input instance。

## 4. Strategy candidate eligibility audit

### 4.1 Nomination and reconstruction

唯一 nomination：
`NOMINATE_B_BREAKOUT_RETEST_LEGACY_V1_FOR_DEVELOPMENT_ELIGIBILITY`。

B exact reconstruction、V0 parity、edge behavior、semantic spec SHA 和 numeric
projection parity 均 PASS。B spec SHA 为
`5bbeb345ebd8883149138d2f29f8606f919949ae285aa2839fa337921dfc7112`。A 仍为
`REJECT_A_PLATFORM_BREAKOUT_LEGACY_V1_AS_FROZEN_CANDIDATE`；C 未被评估。

### 4.2 Fixed eligibility decision

`STRATEGY_DEVELOPMENT_ELIGIBILITY_V1` 的 thresholds 在读取 B returns 之前已经冻结：

`ELIGIBILITY_RULE_FROZEN_BEFORE_B_RETURNS_READ = true`

Python 3.12.13 / pandas 2.2.3 / `pyarrow==17.0.0` 的单次 replay 结果为：

- Event N：`17,714`；available N 1D/3D/5D/10D：`17,689` / `17,635` / `17,602` / `17,558`；
- 10D positive rate / mean / median：`51.6403%` / `+1.4603%` / `+0.3226%`；
- robust 10D years：4；positive-mean robust years：2（2024、2025）；
- fixed gates：全部 PASS；
- final decision：`CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES`。

详细 1D/3D/5D/10D MFE/MAE、concentration、year robustness、input verification 和
event/manifest SHA 见 [`strategy_candidate_eligibility_report.md`](strategy_candidate_eligibility_report.md)。

### 4.3 Boundaries retained

- B 仍是 research/development candidate，不是 production strategy；
- 该 eligibility 不是 parameter validation、调参或 Final OOS；
- 不自动评估 C，不启动 Phase 2F，不创建 TOP-N 或 promotion path；
- retrospective output 仍标记 `DEVELOPMENT` / `RECONSTRUCTED_RETROSPECTIVE`。

## 5. Candidate-bound prospective input contract

Contract：[`candidate_bound_prospective_input_contract_v1.md`](candidate_bound_prospective_input_contract_v1.md)。
它绑定：

- B strategy version/spec SHA 与 eligibility protocol；
- T close / T+1；
- exact universe、sector semantics、names、market_env；
- provider/version、calendar；
- availability、fail-closed、recovery；
- generation fingerprint 与 canonical output identity。

contract 当前状态为 `CONTRACT_DEFINED_NO_LIVE_INSTANCE`。没有伪造 T、payload、
prospective output 或 live observation。

## 6. Minimum P0 / P1

### P0

本轮没有发现新的全局 P0 correctness/safety defect。PIT、T close/T+1、fail-closed、
identity/hash 规则在受控 path 上保持明确；历史新浪 membership 缺失仍只限制
FULL legacy retrospective scope。

### P1

1. **`P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE`**：等待首个真实、候选绑定、
   `LIVE_OBSERVED` 的 T-close package，并验证 `known_at <= T`、universe/sector/
   names/market_env、provider/version、calendar、availability/recovery 和 output
   identity。它是当前唯一剩余 frozen-candidate prerequisite P1。

不需要先建设 scheduler、broker、自动交易或复杂告警。历史新浪 membership 仍是
FULL legacy validation 的 scope-local blocker，不升级为全局或 B eligibility blocker。

## 7. Next decision, deferred research and shortest product path

下一步只等待并审计首个真实 prospective package；package 通过后回到
`FROZEN_CANDIDATE_PREREQUISITES` decision point。若 package 缺失、陈旧、冲突、
不可恢复、时间语义不符或 identity 不一致，必须 fail closed。

可以 DEFER：Phase 2F/Research V2、参数选择和调参、performance-based rule change、
完整 legacy 85-score parity、历史新浪 membership acquisition、scheduler、broker、
自动交易、复杂告警和不影响 P0/P1 的 later production hardening。

当前不创建 `FROZEN_CANDIDATE_CONTRACT_V1`，不把 development eligibility 写成
strategy promotion，不读取 Final OOS，也不自动测试 C。

## 8. Governance conflict and provenance correctness closure

本轮修复了 active PR metadata 与正式 evidence 不一致的问题：B 的 decision 保持
`CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES`，Formal Delivery Ladder 保持
`development candidate`，尚未创建 `FROZEN_CANDIDATE_CONTRACT_V1`，唯一当前 P1
仍为 `P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE`；不 promotion。

`scripts/strategy_development_eligibility.py` 现在只把稳定的 repo-relative logical
path 写入 eligibility provenance，并禁止 `Path.resolve()` 的 machine-specific 结果
进入 identity。relocated filesystem roots 以及 relative/absolute invocation 的回归均
证明 canonical manifest/content identity 相同；绝对路径不参与 semantic/content/hash。

正式 B decision evidence 已登记到 registry：event artifact 的 file SHA 为
`8940a4a346ac6911ba669f84a9ceba7ef878b0ed0ce51edf673439b52aa056b9`、semantic/content
SHA 为 `a16e48dfbe8a93f64d8bf1bad6e00d3eaf32c10fd60eed09dc5574247b8119bc`；manifest
semantic SHA 为 `f79ec9baa494f2f0256843c2540988bd25c94269ed9a1fd4ada228759bd8e0a2`，
payload content SHA 为 `e754787836b28316430278372ab2d84817091d4608da394f9207f695a4c27aee`，
file SHA 为 `5e0a557c1930de7b4f182f09f43b45c0c11b19b2d7c992bf9e7fa7e6cc6de048`。
两者均是 `required_for_decision=true`、`required_for_replay=false`，并保留
`DEVELOPMENT` / `RECONSTRUCTED_RETROSPECTIVE` 及当前 recoverability 标签。

本次 deterministic reproducibility verification 的 event count、event identities、
全部 metrics、fixed thresholds、gate audit 和 eligibility decision 与修复前完全一致；
没有 C、Phase 2F、调参、Final OOS 或 production promotion。

## 2026-08-31 — First formal post-merge package audit

| prerequisite | result | evidence |
| --- | --- | --- |
| B decision / spec / threshold | PASS unchanged | `B_BREAKOUT_RETEST_LEGACY_V1`; spec SHA remains `5bbeb345ebd8883149138d2f29f8606f919949ae285aa2839fa337921dfc7112`; frozen eligibility decision unchanged |
| SH/SZ scope / exact Sina taxonomy | PASS for selected boundary | `TRADABLE_UNIVERSE_SCOPE_V1`; exact `stock_sector_spot(indicator="新浪行业")` + `stock_sector_detail` path used |
| LIVE_OBSERVED / T-close → T+1 | PASS precondition | T=`2026-08-31`, T+1=`2026-09-01`, observed after 15:00 BJT close |
| provider / fallback provenance | BLOCKED at name consistency | `INPUT_CONFLICT` for symbol `000012`; later providers not reached |
| immutable persistence / Drive backup / recovery | NOT APPLICABLE | no READY package existed; no bytes were eligible for persistence or upload |
| deterministic input/generation identity | NOT CREATED | no complete manifest/package existed |
| Final OOS / C / Phase 2F / tuning / promotion | PASS boundary | Final OOS sealed/unread; all prohibited paths untouched |

Final decision: `FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_INPUT_CONFLICT`.
The machine-readable failure evidence is
`data/governance/prospective_input_attempt_evidence_20260831.json`; it is explicitly
not a frozen artifact. The failure classification is
`INPUT_PROVIDER_DATA_CONSISTENCY_CONFLICT`, not provider connectivity. The original
attempt did not record raw names or execution counts, so those fields remain explicitly
unrecorded rather than being backfilled from the current diagnostic. The current
read-only name diagnostic is
[`current_capability_name_diagnostic_20260831.md`](current_capability_name_diagnostic_20260831.md)
and is not prospective evidence. No `FROZEN_CANDIDATE_CONTRACT_V1` is created.

## 2026-09-01 continuation audit — historical provider dependency snapshot

> `LOCAL_CURRENT_SNAPSHOT_DIAGNOSTIC_NOT_PROSPECTIVE_EVIDENCE`

The B source audit is now explicit. Exact six-digit symbol is the security/trading
identity. Display names are not consumed by B for symbol joins, candidate selection,
hard gates, trigger, stop, target, RR, score, final status or canonical identity; the
active correction therefore adopts `DISPLAY_NAME_CONSISTENCY_POLICY_V2_SYMBOL_AUTHORITATIVE`
and retains raw/normalized mismatch diagnostics in the V2 contract and generation identity.

B does consume sector evidence: `sector_rank` and `sector_chg` feed the 85-score
`strong_sector` and `sector_linkage` components, while missing evidence returns
`INSUFFICIENT_DATA` through `SECTOR_EVIDENCE_COMPLETE`. Sector remains an executable
required input; this audit does not authorize dropping it, shrinking the universe, or
substituting EM/THS/SW taxonomy. The B spec SHA remains
`5bbeb345ebd8883149138d2f29f8606f919949ae285aa2839fa337921dfc7112`.

The fresh 2026-09-01 current-only probe passed the declared runtime and provider
capability checks but found 5,221 scoped HiThink symbols versus 2,978 unique exact-Sina
sector symbols. It reported 2,682 universe symbols without sector membership, 439 sector
symbols outside the universe, and five distinct multi-sector symbols:
`000587`, `000602`, `002217`, `002617`, `600714`. It found no exact duplicate symbol in
that snapshot. These counts are not historical T=`2026-08-31` evidence and do not create
a live package.

Decision in this historical snapshot was
`FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_SECTOR_MEMBERSHIP_AMBIGUITY`, with independent
exact-Sina coverage failure. `NEEDS_MORE_EVIDENCE` remains the research decision for a
future legitimate T-close response that is complete and unambiguous. No T=`2026-09-01`
acquisition is run because PR #18 is not merged to clean master and the sector gate is
unresolved. The detailed matrix is in
[`b_dependency_audit_20260901.md`](b_dependency_audit_20260901.md); V1 audit/evidence is
preserved unchanged.

## 9. Superseding current state — 2026-09-02

本节只 supersede 前文对 current / active / next gate 的解释，不删除或改写 V1/V2、旧
spec、旧 sector coverage/ambiguity diagnostic、失败 attempt 或旧 decision 的历史事实。

- formal Delivery Ladder：`development candidate`。
- corrected candidate：`B_BREAKOUT_RETEST_LEGACY_V1_1`；spec SHA-256：
  `f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd`；decision：
  `CORRECTED_B_CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES`。
- active contract：`CANDIDATE_BOUND_PROSPECTIVE_INPUT_PROVENANCE_CONTRACT_V3`，状态为
  `CONTRACT_DEFINED_NO_LIVE_INSTANCE`。
- exact V0 sector semantics：missing sector=`("-",50,0.0)` continue；multi-sector=
  `LEGACY_PROVIDER_ORDER_LAST_WRITE_WINS_V1`。complete sector coverage 不是额外 hard
  gate；provider failure、invalid observed fields 和 unresolved package identity 仍
  fail closed。
- current blocker：`P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE`，即首个真实、
  candidate-bound、`LIVE_OBSERVED`、`known_at <= T` 的 T-close input instance 尚未形成。
- current next gate：`T=2026-09-02` legitimate XSHG T-close 后的首个真实 package；北京
  时间 15:00 前不运行 formal acquisition，不把 probe 注册为 prospective evidence，
  不回填 `2026-09-01`。
- last-verified master snapshot：`614934e7ea98bbe94099e9bf57971cf8454c9713`；master
  exact-head correctness run `33584844019` 为 `success`。这是本治理 branch 创建前的
  provenance，不是未来 PR CI 的 self-referential invariant。

## 10. Superseding current attempt — 2026-09-02

本节只 supersede 当前 prerequisite decision，不删除 V1/V2、old spec、历史 diagnostic、
失败 attempt 或旧 decision。

| prerequisite / stage | result | evidence / boundary |
| --- | --- | --- |
| corrected B/V3 identity | `PASS unchanged` | `B_BREAKOUT_RETEST_LEGACY_V1_1`，spec SHA `f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd`，active contract V3 |
| legitimate T-close | `PASS precondition` | observed `2026-09-02T16:10:17.291775+08:00`，XSHG close `15:00:00+08:00`，T+1=`2026-09-03` |
| HiThink SH/SZ universe | `COMPLETED` | current fresh call completed；count 未由异常路径暴露，不从旧 snapshot 回填 |
| exact Sina sector definitions/members | `COMPLETED` | exact `新浪行业` spot/detail traversal completed；counts/diagnostics 未由异常路径暴露，不猜测 |
| Tencent quote snapshot | `BLOCKED` | `PROVIDER_FAILURE` / `QuoteFieldError`，data validation failure，非 connectivity failure |
| GenerationInputManifest / B evaluation | `NOT REACHED` | no READY manifest；no threshold/filter change，`score_cutoff=None` / `top_n=None` 未被执行 |
| immutable package / Drive backup / recovery | `NOT APPLICABLE` | no READY package；no bytes eligible for persistence/upload/readback |
| candidate list | `NOT EVALUATED` | 不把未运行误报为 zero candidates |

Final decision：`FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_PROVIDER_FAILURE`。机器可读证据为
[`data/governance/prospective_input_attempt_evidence_20260902.json`](../data/governance/prospective_input_attempt_evidence_20260902.json)，
并明确 `not_a_frozen_artifact=true`。本次不产生 partial canonical watchlist，不创建新的
registry artifact，不自动 retry/freeze/promotion；Final OOS、prospective returns、C、
Phase 2F 和 `2026-09-01` backfill 均未读取/执行。

## 11. Superseding current attempt — 2026-09-02 post-merge fresh capture

PR #24 已按批准 exact head `e97a6a3c525b497f57aac9cfd751b11f86ca9d5c` squash merge，真实
merge SHA 为 `05232677055c67b8b87c8d8c3c3b4139df8c477d`；local `master`、`origin/master`
和该 merge SHA 一致；merge 后 master exact-head correctness run `33616552822` 为
`success`。随后运行了新的 `T=2026-09-02` / `T+1=2026-09-03` formal
`LIVE_OBSERVED` capture，未复用历史 attempt、current-only probe 或 PR regression
payload。

| stage | result | evidence / boundary |
| --- | --- | --- |
| close-window / timing | `PASS` | `close` / `Asia/Shanghai` / `XSHG` validation passed；runner 未记录精确 `observed_at_bjt`，保持 `NOT_RECORDED_BY_RUNNER` |
| HiThink universe | `COMPLETED` | 当前 SH/SZ scope provider call 完成；异常 runner 未保存 count，不猜测回填 |
| exact Sina sector | `COMPLETED` | exact `新浪行业` spot/detail traversal 完成；异常 runner 未保存 diagnostics，不猜测回填 |
| Tencent quote snapshot | `BLOCKED` | `301686` / `sz301686` 的 `p[38]` (`turnover`) 为空，`QuoteFieldError` → `PROVIDER_FAILURE`; raw line 未保留，no-trade semantics=`UNRESOLVED_FOR_301686` |
| stock/index Kline, market_env | `NOT_REACHED` | 不触发停牌无 T bar 的 contract decision |
| GenerationInputManifest / B | `NOT_REACHED` | 没有 READY manifest；strategy/threshold/score/top-N 未改变 |
| package / local persistence / Drive recovery | `NOT_APPLICABLE` | 没有 package bytes；`data/prospective_inputs/` 不存在 |
| candidate list / Final OOS / prohibited paths | `NOT_EVALUATED` / `SEALED_UNREAD` | 不得把失败误报为 zero-candidate；C、Phase 2F、prospective returns、调参、promotion 未执行 |

机器可读 evidence：
[`data/governance/prospective_input_attempt_evidence_20260902_post_merge.json`](../data/governance/prospective_input_attempt_evidence_20260902_post_merge.json)，明确
`not_a_frozen_artifact=true`。当前 decision 仍为
`FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_PROVIDER_FAILURE`；current P1
`P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE` 未解除。本次停止，不自动重试，不放宽
Tencent parser，不缩 universe，不跳过 symbol，不创建新的 frozen registry record。

## 12. 2026-09-02 tradable-universe listing eligibility root-cause audit

本轮分类为 `correctness blocker`。研究问题是 HiThink
`/api/meta/tickers/list` 是否提供足够可靠的 listing-eligibility metadata，能够
对 `301686` 在 `as_of_date=2026-09-02` 是否已经上市作 deterministic 判断。该问题
直接决定能否修复 acquisition universe 的 correctness，而不引入 hard-code、
current-data backfill 或第二套 listing engine。

本轮只做 exact `301686` 的 current-only read-only diagnostic，明确标记为
`CURRENT_ONLY_DIAGNOSTIC_NOT_PROSPECTIVE_EVIDENCE`；没有把 response 写入 formal
input、UniverseManifest、package 或 output，也没有读取或修改
`data/validation/continuous_speed_probe/`。完整记录见
[`tradable_universe_listing_eligibility_audit_20260902.md`](tradable_universe_listing_eligibility_audit_20260902.md)。

HiThink `/api/meta/tickers/list?exchange=SZ&asset_type=a-share&limit=10000&offset=0`
返回 `code=0`、`data.timestamp=1788336018945`（`2026-09-02T16:00:18.945+08:00`），
target row 为：

```json
{"thscode":"301686.SZ","ticker":"301686","name":"中塑股份","exchange":"SZ","asset_type":"a-share","currency":"CNY"}
```

实测 raw schema 只有 `thscode`、`ticker`、`name`、`exchange`、`asset_type`、
`currency`；没有 `listing_date/list_date`、listing/security status、
`delisting_date`、`trading_status`、`market_status` 或等价 as-of 字段。因而 provider
row 只能证明它是 SZ A-share metadata record，不能证明它在 2026-09-02 已上市。

research decision：`NEEDS_MORE_EVIDENCE`；stop state：
`TRADABLE_UNIVERSE_LISTING_ELIGIBILITY_SOURCE_DECISION_REQUIRED`。任务输入中已确认
的外部事实支持 root-cause direction
`PRE_LISTING_SECURITY_INCORRECTLY_INCLUDED_IN_TRADABLE_UNIVERSE`，但不能被提升为
HiThink prospective metadata evidence。当前不修改 `_build_universe()`，不 hard-code
`301686`，不按代码新旧或历史 Kline 推断上市状态，不缩 universe，不跳过 Tencent
symbol，不删除 suspended/ST securities，不放宽 turnover parser，也不重跑 formal
capture。

如果后续获得并批准可靠 source，目标语义仍是：已上市但停牌的 `002731` 保留在
acquisition universe，已被 deterministic 证明为 T 日未上市的 `301686` 才排除；
ST 排除仍只发生在 B evaluator 后的
`USER_TRADABILITY_ELIGIBILITY_NON_ST_V1` final user-facing layer。本轮没有批准或
实现该 filter。

最终 decision：`TRADABLE_UNIVERSE_LISTING_ELIGIBILITY_SOURCE_DECISION_REQUIRED`。

## 13. 2026-09-02 official exchange listed-roster source decision and correction

Sol approved `USE_EXCHANGE_OFFICIAL_LISTED_ROSTER_VIA_EXISTING_AKSHARE` for the bounded
correctness fix. This section supersedes only the preceding listing-source stop state; it
does not rewrite the failed 2026-09-02 capture evidence, Tencent parser semantics, candidate
eligibility, strategy/spec/threshold/score, frozen artifacts, or the sealed Final OOS boundary.

The formal prospective universe remains SH/SZ A-share scope, but is now defined as:

`HiThink /api/meta/tickers/list broad metadata ∩ EXCHANGE_OFFICIAL_CURRENT_LISTED_ROSTER_V1`

The official roster uses existing AkShare APIs and their exact arguments:

| exchange | AkShare call | required fields | underlying official URL |
| --- | --- | --- | --- |
| SSE main board | `stock_info_sh_name_code(symbol="主板A股")` | `证券代码`, `上市日期` | `https://www.sse.com.cn/assortment/stock/list/share/` |
| SSE STAR | `stock_info_sh_name_code(symbol="科创板")` | `证券代码`, `上市日期` | `https://www.sse.com.cn/assortment/stock/list/share/` |
| SZSE A-share | `stock_info_sz_name_code(symbol="A股列表")` | `A股代码`, `A股上市日期` | `https://www.szse.cn/market/product/stock/list/index.html` |

The adapter canonicalizes listing dates and requires `listing_date <= as_of_date`. It
joins only exact six-digit symbols; display names are not identity keys. Missing/invalid
required fields, unavailable official rosters, and duplicate/conflicting official symbols
fail closed before sector, quote, or Kline acquisition. There is no HiThink-only fallback,
fuzzy reconciliation, hard-coded symbol exception, or second listing engine.

Existing manifest/provenance metadata now records the AkShare version, exact API/source
identity, all three source row counts, canonical combined and eligible counts, deterministic
content and semantic SHA-256 values, and HiThink-only/roster-only mismatch counts/lists.
The official roster identity is included in the existing input and candidate-bound generation
identity. This source is same-day `LIVE_OBSERVED` prospective evidence only and cannot
backfill historical T dates.

The semantic boundary is explicit: `301686` is excluded before formal Tencent quote/Kline
when the official roster evidence excludes it or its listing date is after T; already-listed
suspended `002731` remains in the acquisition universe. ST/*ST remains exclusively the
post-B `USER_TRADABILITY_ELIGIBILITY_NON_ST_V1` final user-facing layer. Formal capture was
not rerun. The bounded implementation/test work stops after one PR reaches exact-head CI
success and `CLEAN`/`MERGEABLE`, at
`TRADABLE_UNIVERSE_EXCHANGE_ROSTER_FIX_PR_READY_FOR_USER_MERGE_DECISION`; merge remains a
user decision.

Final decision: `ADOPT` — `EXCHANGE_OFFICIAL_CURRENT_LISTED_ROSTER_V1`.

## 14. PR #25 ready for user merge decision — 2026-09-02

The bounded correction is now in PR #25 at the pre-reconciliation head
`105acc9d9772539a3f799faf90bef14a83f83152`, based on
`05232677055c67b8b87c8d8c3c3b4139df8c477d`. Its pull_request exact-head correctness run
`33624209979` succeeded; the PR was verified `open`, `mergeable=true`, and
`mergeable_state=clean` before this governance-only snapshot. The snapshot itself does not
change the adopted source, any failed attempt, or any frozen identity. After pushing this
snapshot, the new head must be checked live again; no merge is authorized by this audit.

The final stop remains
`TRADABLE_UNIVERSE_EXCHANGE_ROSTER_FIX_PR_READY_FOR_USER_MERGE_DECISION`.

## 15. 2026-09-04 generated watchlist external postprocess evidence

After PR #31 merged at `426b230cdaf53546e5efa4e99cda99c9bcccb85a`, the corrected development
watchlist `data/watchlist_20260903.json` was uploaded to the existing private Drive project
folder under explicit user authorization. The Drive item is
`1N-G0LVvMtotffm5Tdq-2-f4I-fZkuTUq`, MIME `application/json`, size `6422` bytes. Raw
read-back returned bytes whose SHA-256 is
`50f0717e55daaf4435e1d25b4f1d029109c566d72d63a1fc566f263cdf0fb085`, exactly matching the
local canonical file SHA.

This is sufficient to resolve the current generated-artifact external postprocess /
Drive-readback evidence blocker. It is not evidence that the generic runner has automated
Drive upload, and it is not a frozen-candidate recovery attestation. The frozen prerequisite
therefore remains `NOT_READY / PARTIAL_UNVERIFIED`: the 170 historical sidecars with
`UNKNOWN_ORIGIN` code provenance remain unchanged. No frozen artifact registry record or
frozen bytes changed, and no freeze/promotion decision is implied.

## 16. 2026-09-07 first candidate-bound V3 instance verified; recovery still incomplete

This is the superseding audit for the stale first-instance blocker. The task classification
is `correctness/provenance + product-gate audit`, not a new research phase. The question is
whether the 2026-09-03 package satisfies (A) existence of the first real candidate-bound
`LIVE_OBSERVED` T-close input instance, and separately whether it satisfies (B) the complete
frozen prerequisite including `FULLY_RECOVERABLE` provenance.

### A — adopted as verified

The package at
`data/prospective_inputs/20260903/2026-09-03_eeb700c98a69a98fae3fa220851190a76de88984b0f451cc1ed275b2e487351f.json`
has schema `CANDIDATE_BOUND_LIVE_INPUT_PACKAGE_V4`, file SHA
`a2e6da0865ff20316e4d9074f26e2cb3ba53995d2cb3e83a49f8c82988c0b38a`, content SHA
`0b1216e5c5855343dba02853eb17e9dbc43c97d50120ac7490da43eaa78cdf86`, and generation
fingerprint `eeb700c98a69a98fae3fa220851190a76de88984b0f451cc1ed275b2e487351f`. It is bound
to `B_BREAKOUT_RETEST_LEGACY_V1_1`, spec SHA
`f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd`, with T=`2026-09-03`,
retrieval at `2026-09-03T18:18:51.506757+08:00` after the XSHG 15:00 close, and earliest
execution `2026-09-04`. The V3 universe, quote, stock/index Kline, sector, symbol identity,
and generation-manifest checks are `PASS`.

The corrected B evaluator run is
`quJ3jSEgMJjgzQ1SE2rYP7XcSbBEV7fFFjIgiXKlPBk`, with run-manifest SHA
`865eeba45974e70ff70b67b1e8422c5e36e65010d5aebb521d7b01ac197d1445`; it produced 12 raw
legacy-qualified rows, excluded one ST symbol in the existing final eligibility layer, and
produced the canonical 11-candidate watchlist with SHA
`50f0717e55daaf4435e1d25b4f1d029109c566d72d63a1fc566f263cdf0fb085`. The 10,597 raw/sidecar
pairs were independently checked: missing raw=0, content-hash mismatch=0, byte-length
mismatch=0, JSON parse failure=0.

Decision for A: `ADOPT` — the old
`P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE` is stale and is closed only for the
existence question. The 170 `UNKNOWN_ORIGIN` sidecars do not invalidate A because they do
not show a missing, future-dated, unbound, or malformed input instance; they are a separate
provenance-completeness limitation.

### B — not ready

The frozen prerequisite remains `NOT_READY / PARTIAL_UNVERIFIED` for two independently
material reasons:

1. 170 source sidecars retain `code_git_sha=UNKNOWN_ORIGIN`. Their raw bytes and declared
   lengths verify, but the original runner code identity cannot be retroactively established
   without inventing history.
2. The package and source evidence are local-only in the verified workspace. The existing
   Google Drive item is the 6,422-byte corrected watchlist and its read-back SHA matches;
   the verified project listing contains no candidate-bound package or raw/sidecar archive.
   Under V3's recoverable-package boundary and `FROZEN_ARTIFACT_POLICY.md`, this is not
   objective `PERSISTENT_BACKUP_PRESENT` / `FULLY_RECOVERABLE` evidence.

Decision for B: `NEEDS_MORE_EVIDENCE`. Missing evidence is exact known-origin provenance for
the formal live package and a persistent package recovery/read-back, or a newly authorized
post-close capture that produces both. This decision does not change B semantics, strategy
thresholds, Top-N, universe, evaluator wiring, frozen bytes, Final OOS, C, old D, or the
forbidden continuous-speed-probe directory.

The 2026-09-07 pre-close runner check returned `PRE_CLOSE_DIAGNOSTIC_READY` with provider
calls not run. No fresh package was generated. Terminal marker:
`BLOCKED_REQUIRES_USER_OR_EXTERNAL_DECISION:FROZEN_RECOVERY_PROVENANCE_PARTIAL_UNVERIFIED`.
