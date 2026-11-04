# C_PROSPECTIVE_CAPTURE_V1

## 2026-11-04 supplement: C_PROSPECTIVE_RULE_FUNNEL_CAPTURE_V1

This supplement describes the optional diagnostics for the existing same-runner
C daily report. The standalone/private handoff contract below remains a separate
historical route; this recorder does not activate that provider/capture workflow.

Research question / STRICT PATH: why are C candidates scarce, market structure
or rule strictness? The missing evidence is original full-population diagnostics,
including rejected stocks. The product decision is whether a later independently
authorized boundary/outcome study is warranted. Existing B/C operation can
continue without this evidence. `C_RULE_FUNNEL_STRICTNESS_AUDIT_V1 =
NEEDS_MORE_EVIDENCE`; `C_PROSPECTIVE_RULE_FUNNEL_CAPTURE_V1 =
USER_AUTHORIZED_EVIDENCE_COLLECTION`. No strictness conclusion, sensitivity,
return, MFE/MAE, MODEL_P/MODEL_R or Final OOS access is part of collection.

`scripts/c_rule_funnel_capture.py` runs in a separate, optional workflow step
AFTER Formal B delivery and C report publication. It verifies the exact package,
C observation and published manifest SHAs, T date and post-XSHG-close timestamps;
it neither requests provider data nor accepts historical/backfill inputs.
`c_pre_outcome_design.py`, its two rule definitions, the input adapter, daily C
evaluator/report, B and delivery are unchanged. The new step is fail-soft and
bounded to 3 minutes. Its output/status never feeds B/C qualification, priority,
completion, report sorting or user delivery. Recording is disabled by default.

Persistence contract: **FULL_UNIVERSE_COMPUTE_IN_MEMORY /
AGGREGATE_ONLY_DURABLE_PERSISTENCE / BOUNDED_NEAR_MISS_SAMPLES**.
`iter_rows` diagnoses one stock/rule, updates counters, histograms and top-five
samples, then discards the row. Only the current stock's temporary tried-pair
contexts are needed for parity. The existing package and C observations are
runner-local inputs; no new full-universe diagnostic row collection is built.
A symbol lacking an original C rule observation contributes explicit diagnostic
gap counts, not an invented C rejection. B-isolated stocks remain coverage count
gaps. Counts distinguish input/evaluated stocks/rules and complete/missing
diagnostics. Full-universe symbol lists and all-symbol margins are not persisted.

| Stage | In-memory computation (durable output is aggregate counts) |
| --- | --- |
| F0/F1 | symbol/date/rule, board, T-known ST/universe status, input gaps/quality, history availability/end/count, applicable 90-bar adapter and rule minima, input prefix/Kline SHA |
| F2 | close>fast, MA order, positive slope and numeric log slope, up-close fraction, threshold, margin and aggregate trend qualification |
| F3 | confirmed low/high pivot counts, distinct pair and pre-pullback peak availability, separation/minimum, selected pair/peak age/limit, exact original status |
| F4 | full-precision depth/min/max/lower/upper margin, peak age and its limit, separate age/depth failures, pullback sessions, original structure status |
| F5 | confirmed high availability, rebound size/min/max/margins, missing-high versus out-of-range-size diagnostic status |
| F6 | four confirmation predicates, close location/threshold/margin, failed predicates and count, original-context confirmation qualification |
| F7 | support floor, pullback/T close breaks, recovered punctures, support entry predicate |
| F8 | exact current price_structure_match, research_match_status and rule ID |

All pairs actually tried by the frozen enumeration are computed in order up to
its first selected structure (or all pairs when no selection exists). Later
pairs are not used to rescue a failed confirmation/support on that selection.
First-low peak/depth/support and second-low rebound/confirmation values and pair
references are temporary per-stock context, discarded after reduction.
`iter_pair_diagnostics` feeds overlapping failed/missing predicate aggregates.
Original rule results are preserved; any decomposition
or selection parity mismatch becomes a missing diagnostic. This also avoids
calling an earlier failed pair a stock failure when a later pair was selected.

Near-miss `failed_condition_count` is the count of false predicates in a fully
defined context. For a selected structure only that context is eligible; with
no selection it is the minimum across fully defined tried contexts. Only
aggregate pair counts/histograms survive. Classes cover one trend predicate, one confirmation
predicate, depth only, peak age only, rebound size only and support only; multiple
classes/failures can coexist. This is LOCAL_CONDITION_DIAGNOSTIC, not a Score,
primary-cause choice, parameter relaxation or proven counterfactual stock list.
Undefined predicates remain null; known-independent T predicates are retained
even without a selected rebound. Unknown stages are separately counted rather
than reported as rule attrition.

Persistence reuses the existing runtime-state writer and atomic immutable copy.
Exactly two JSON files are allowed per captured date:

- `data/research/c_rule_funnel_capture_v1/daily/YYYYMMDD.json`: small summary,
  frozen rule/config/source identities, original package/observation/report
  hashes, F0–F8 known-pass/attrition/unavailable counts, every local failure and
  missing count, pair-level failure combinations, all-pairs-failed stock counts,
  near misses, exact final rule matches, diagnostic gaps, histograms and the
  checkpoint/production/Final OOS markers. Conservative slope/fraction joint
  counts, peak-age/depth joint pair counts and rebound-high/size pair counts are
  explicit. Future funnel review needs only this summary, not sampled identities.
- `near_miss/YYYYMMDD.json`: at most N=5 per rule x class (60 total), selected by
  absolute signed margin ascending, symbol ascending on ties. For multiple
  contexts of one stock/class choose the smallest absolute margin; equal margins
  retain frozen enumeration order. Classes are `ONE_TREND_SUBCONDITION`,
  `ONE_CONFIRMATION_SUBCONDITION`, `DEPTH_ONLY`, `PEAK_AGE_ONLY`,
  `REBOUND_SIZE_ONLY`, `SUPPORT_ONLY`; absent classes are empty arrays. Each entry
  contains only symbol/date/rule/class, relevant condition/observed value/threshold/
  signed margin, canonical structure status and daily input-identity reference.
  File-level package/observation SHAs bind that reference. Negative margin means
  failure; a strict > predicate can fail at zero. For range predicates use the
  violated edge (upper-edge margin is threshold minus observed). Support margin
  uses minimum close over the frozen pullback interval through T minus support
  floor. No OHLCV, full F0-F8 row, pair table or nested context is retained.
- Full-detail persistence and its SHA/bytes/row-count contract are removed;
  runtime-state rejects the old `details/YYYYMMDD.jsonl.gz` path. There is no gzip
  generation or full-universe gzip remote readback. Local JSON/SHA verification
  and independent remote byte readback apply only to the two small JSON files.
- Same-date same-input retries are idempotent. A different input/version or
  existing content conflict is rejected, never overwritten. Only these two
  narrow paths are allowlisted/staged; no B path is changed. The namespace is
  ignored by master. Summary <=256,000 bytes/date, samples <=256,000 bytes/date,
  combined <=500,000 bytes/date (stricter than 512 KB), so at most 20 dates means
  <=10,000,000 bytes (10 MB, without rounding). This is
  research JSON payload only, not a claim about Git object/history overhead.
  Size checks occur before either file is written. Over-limit/error/timeout is
  fail-soft recording failure, not C failure or zero matches.

### Frozen histograms (no outcome-based rebinning)

The following bins and endpoint inclusivity are fixed in `HISTOGRAM_BINS` before
collection. Missing/non-finite values increment `UNAVAILABLE`, never a numeric
bin. Balanced and Conservative each have independent histograms. No quantiles,
data-fitting or outcome-based edge selection is allowed.

| Metric | Frozen bins |
| --- | --- |
| up_close_fraction | <.50; [.50,.55); [.55,.58); [.58,.60); [.60,.62); >=.62 |
| log_close_slope_per_session | <=0; (0,.0005); [.0005,.002); >=.002 |
| depth | <.03; [.03,.04); [.04,.10); [.10,.12]; (.12,.15]; >.15 |
| rebound_size | <.02; [.02,.08]; (.08,.10]; >.10 |
| peak_age minus frozen rule limit | <=-4; -3..-1; 0; +1..+3; >=+4 sessions |
| confirmation_close_location | <.50; [.50,.55); [.55,.60); [.60,.65); >=.65 |

Slope uses the existing regression of natural-log close on session index. The
fixed positive breaks .0005 and .002 correspond approximately to .05% and .2%
per session; these scale-based reporting breaks do not change the >0 rule.
Peak-age limits remain Balanced 24 and Conservative 31 sessions. The age buckets
separate well below, 1-3 before, exactly at, just over and clearly over the limit.
Depth bins expose shallow values, Conservative's .04 lower edge, Balanced's .12
upper region, .12-.15 and >.15. Exact .12/.15 and .08/.10 remain in their existing
inclusive rule ranges.

`stock_histograms` count one value per input stock/rule for trend/fraction and
confirmation close location (including independently observable T geometry when
no structure is selected). `tried_pair_histograms` and decomposition counts cover
ALL tried pairs, including rejected stocks: they are pair-weighted, not stock
counts or a causal bottleneck ranking. `selected_structure_histograms` separately
cover the canonical selection only; no-selection stocks are absent there.
`candidate_pair_count`, exact statuses and all-pairs-failed stock counts provide
the denominators. Sequential attrition/unavailable counts remain stock-level.
Near-miss aggregate counts are computed before top-five truncation. This retains
threshold-proximity evidence without preserving rejected-stock identities.

The recorder answers only why C has few matches. Per-rejected-stock future
returns are out of scope. A later outcome study needs a separately authorized
targeted prospective cohort; it is not a reason to retain full detail here.

### Synthetic capacity validation

`python -m pytest -q -s tests/test_c_rule_funnel_capture.py::test_3000_stock_6000_observation_durable_capacity`
executes the real verification/diagnostic/reducer/persistence path for 3,000
synthetic Main Board stocks, 260 bars each and both frozen rules (6,000 complete
rule observations). Half fail only the confirmation body predicate, exercising
bounded samples; the other half preserve matches. No provider/outcome data is
used. Full-suite measurement: diagnostic/validation/hashing/reduction 16.198 s
(standalone 15.655 s); daily summary 10,139 bytes, near-miss 3,795 bytes, combined
13,934 bytes. Synthetic input construction is excluded from diagnostic runtime.
Peak memory is `NOT_MEASURED`: pytest RSS includes the existing package/observations,
other tests and allocator retention, so no unsupported memory claim is made.
The one-pass generator regression checks consumption before the next row and
deterministic top-five selection for both rules and all six classes. Output size
is a synthetic capacity result, not real prospective market evidence.

This proves diagnostics derive from exact same-day C inputs by SHA and original
rule observation parity; it does not retain raw input bytes or upgrade the older
`PROSPECTIVE_CAPTURED`/volume-validity claim. No historical backfill is allowed.

After the user approves merge AND activation, configure repository variables
`ENABLE_C_RULE_FUNNEL_CAPTURE_V1=true` and `C_RULE_FUNNEL_CAPTURE_START_DATE` as
the first enabled real T date. This implementation changes neither variable.
Start date/rule identity cannot silently change within the same collection.

Checkpoint: at least 15 distinct real XSHG C run dates AND >=20,000 complete
stock-day-rule observations. Otherwise continue to no more than 20 real run
dates. Counting reads dated published C manifests, including recorder-gap dates;
duplicate report versions do not count twice. Daily summary marks
`C_PROSPECTIVE_RULE_FUNNEL_REVIEW_V1 / REVIEW_REQUIRED`, with INSUFFICIENT_DATA
when appropriate at the hard limit. Subsequent captures stop. The implementation
only emits the review checkpoint, not a premature strictness or outcome report.
Recorder failures remain explicit gaps; they do not extend the 20-run ceiling.

状态：`C_SHARED_INPUT_ACTIVATION_RELEASE_GATE_READY_FOR_SOL`；真实交接尚未完成，
`PROSPECTIVE_CAPTURED` 尚未成立。

前瞻输入版本为 `C_QFQ_INPUT_V1`。用户已选 A：唯一价格输入是 B 当日冻结的 qfq
股票历史 OHLC。原未复权设计保留历史定义，不能与该版本混算；这不是 qfq 收益优势、
正式历史收益研究或 Formal B 修改。两套 `BALANCED_A` / `CONSERVATIVE_B` 结构参数不变。
量的单位依据 [HiThink 历史行情接口](https://github.com/HiThink-Tech/Financial-API/blob/main/skills/hithink-finance/references/api/endpoints-prices.md)
`PriceBarItem.volume`（股）；`adjust=forward` 对 volume 的处理在该契约中未说明。
只读 B 输入时，C 保留 T 日 RV、回踩相对基准、前后半段、涨跌日方向性及
量价诊断的原始研究值。`VOLUME_FEATURE_COMPUTED` 不等于
`VOLUME_CONFIRMATION_VALID`；当前量能口径为 `VOLUME_BASIS_UNVERIFIED`，
正式量价确认固定为 false。无有效价格回踩结构时仍保留可计算的 T 日 RV，
回踩路径标记 `PRICE_STRUCTURE_UNAVAILABLE`。

这是新版 C 的独立 T-close 前瞻捕获契约。它只生成研究观察，不生成正式交易名单、不
写入 B 的 `runtime-state`、不调用 B evaluator / Shadow / return tracker / daily report，
不自动下单，也不做正式历史收益研究。

## 1. 入口与时间点

优先入口是 `scripts/c_b_input_adapter.py`：只读一个 B 成功收盘后冻结的完整
`CANDIDATE_BOUND_LIVE_INPUT_PACKAGE_V4` 文件，以调用方给出的文件 SHA-256 和包内
`content_sha256` 双重校验，再按 C 自己的 `BALANCED_A` / `CONSERVATIVE_B` 规则计算观察。
调用方必须提供 T 日、预期 package SHA 和 handoff manifest SHA，且下载到的
`HANDOFF_VERIFIED` receipt 必须同时绑定两者、私有仓库、release asset、archive SHA、
逐文件 SHA 和字节数；候选名单、checkpoint 或 `runtime-state` 里的摘要不能代替
全量原始输入。C 只写 `data/research/c_prospective_capture_v1/shared_input/`，从不修改 B 文件。
输入未就绪时写 C 私有 `CAPTURE_FAILED` 诊断，允许同日 B 重试成功后重新消费。

当前 B package 只在生产 runner 的临时 data root 留存；`runtime-state` 白名单不包含它，
也不包含 T-close raw evidence。C 工作流已移除早于 B 的 15:15 BJT 定时任务，保持禁用。
独立 B 导出草案从成功结果的 `input_package.path/file_sha256` 读取 package，按
`provenance.evidence_capture.captures` 原样复制每个 `.raw` 与 `.json` sidecar，
用 `handoff.json` 记录逐文件 SHA、字节数、package 内部 content SHA、覆盖记录和导出时间。
独立 B Draft PR 将目录压缩后上传到配置的私有 GitHub 仓库 release asset；默认未配置，
不会运行。上传后从私有仓库独立下载 archive，逐文件核验，并把 `HANDOFF_VERIFIED`
receipt 再上传、读回；本地导出、私有持久化、独立下载和最终读回分别留痕。
C 的手工工作流按 T 日、package SHA 和 manifest SHA 下载指定 archive 与 receipt，
验证包内逐文件 SHA、字节数及 receipt/archive 身份，
再只读消费。导出目的地必须与 B 运行目录及 `runtime-state` 分离；本地导出状态
`EXPORTED_LOCAL_UNVERIFIED_REMOTE` 不代表交接完成。只有目的地完成持久化及独立读回、
所有 SHA 和同日时间证据通过核验，才能交给 C 只读消费。B 失败则不导出；导出或私有
持久化失败仅记录交接失败，不能使已成功的 B 生产任务失败；C 失败仅保留 C 私有诊断。
B 同日重试必须按 package SHA 形成新的不可变身份，C 只能消费已验证的指定 SHA，
不得以日期覆盖、混合两次运行证据，或把后续 C 读取时间当成 B 获取时间。

字段级审计：

| 字段 | B runner 内 | 跨任务可恢复 | C 判定 |
| --- | --- | --- | --- |
| HiThink 全市场 ticker 原始响应 | 临时 evidence 有 raw SHA | `NOT_PERSISTED` | `AVAILABLE_PARTIAL` |
| 主板证券代码、名称、T 日 ST 名称证据 | 完整 package 有已筛选主板名称；原始 ticker 行在临时 evidence | `NOT_PERSISTED` | `AVAILABLE_PARTIAL` |
| T 日 OHLCV 与历史 K 线前缀 | 成功 package 对通过 B 输入门的股票具备，逐票有 SHA；被 B 输入失败隔离的合格股票不在 package 内 | `NOT_PERSISTED` | `AVAILABLE_PARTIAL` |
| 价格/量口径 | B 股票历史请求明确 `adjust=forward`，逐票标记 `PROVIDER_QFQ_SNAPSHOT`；bar 字段为 date/open/high/low/close/volume/turnover | qfq OHLC 为本版本唯一价格输入；HiThink 文档称历史 volume 单位为股，B 直接复制该字段，但前复权对 volume 的影响未获说明 | 价格 `ADOPT`；量能 `PARTIAL_UNVERIFIED` |
| provider 请求/接收时间 | B package 有运行开始的 `retrieved_at_bjt`，raw metadata 复用这一时间 | 逐请求真实时间缺失 | `NOT_PERSISTED` |
| 包 manifest、generation fingerprint、SHA | 完整 package 内可核验；成功 runner 结果有文件 SHA | checkpoint/runtime-state 只有局部引用，无完整字节 | runner 内 `AVAILABLE_VERIFIED`；跨任务 `NOT_PERSISTED` |
| `NO_VALID_INPUT`/持久化失败 | 诊断可能进入 runtime-state；raw 留 runner 临时目录 | 无完整 package | `NOT_PERSISTED` |

2026-09-22 远端 `runtime-state` checkpoint SHA-256 为
`826f02807bb58846788137bdaa85d47455fa679497dbd82f49f5cf2898b8ccb1`：
原始 universe 5,576，合格主板 3,196，实际评估 3,187，9 只
`TARGET_DAY_HISTORICAL_STALE` 被隔离。它保存覆盖缺口，但没有完整 package/raw 字节；
不能据此伪造 package SHA 或对 9 只计算 C 观察。真实 B `LiveInputPackage.to_bytes()`
兼容性测试已经核验文件 SHA、内部 content SHA、逐票 K 线 SHA、覆盖与 raw sidecar。

只读消费分别记录独立交接、逐票 T 日价格与 ST 证据、B 输入隔离、C 自身排除、
全市场覆盖和 volume 语义。HiThink 原始响应 sidecar 的逐请求开始/接收时间与
T 日 ticker 名称经 raw SHA 核验后，合格股票可以形成
`PRICE_OBSERVATION_VOLUME_UNVERIFIED`；它不是正式候选，也不是
`PROSPECTIVE_CAPTURED`。缺逐票时间/ST 证据的股票不计算规则观察；B 输入隔离的
9 只仍是全市场覆盖缺口。量能调整语义尚为 `UNRESOLVED`，量价确认继续禁用。
只有完整的同日请求、原始字节、交接、逐票资格、全市场覆盖及量能证据契约全部通过，
才可晋级 `PROSPECTIVE_CAPTURED`；receipt 成功不能单独触发晋级。
现有 C 专属 HiThink adapter 仅作为关闭的备用路线，只有它自行发出
新请求时才适用独立配额门槛；只读复用不需要第二套 API Key。

备用的 C 专属 provider 入口由 `scripts/c_provider_adapter.py` 保留并关闭；它必须独立
证明配额后才允许新增请求。旧 provider snapshot 的验证入口是代码中的
`capture_t_close_snapshot`，不改变只读主路线。

`C_PROVIDER_SNAPSHOT_V2` 由备用 C 专属 provider adapter 生成。snapshot 必须包含：

- `capture.mode=SAME_DAY_T_CLOSE`、provider/version 和每个 request 的 source、endpoint、
  `requested_at`、`received_at`、response identity；
- 每只证券的 code/symbol/exchange/name/security identity；
- T 日已知的 ST/*ST status、`known_at_t`、as-of date 和来源；
- T 日 OHLCV、严格早于 T 的 historical prefix；
- price basis、raw volume basis、调整来源和 T-known policy。

请求和接收必须在 T 日 XSHG session close 之后；runner 也必须在同一 T 日执行。任何
周末补取、次日补取、future bar、T 日前请求或缺少上述证据都会 fail closed。只有所有
必需证据完整且确实同日完成时，顶层状态才可为 `PROSPECTIVE_CAPTURED`。

### 价格口径与覆盖决策

| 路线 | 研究口径 | 数据覆盖及决定 |
| --- | --- | --- |
| 原始响应确定性恢复 | B 同日冻结股票请求只有 `adjust=forward`，无未复权 OHLC/调整因子；原始 volume 单位也未证实 | `NOT_REPRODUCIBLE_WITH_CURRENT_DATA`，不能声明与 C 原协议等价 |
| A：采用 B qfq | 已选 `C_QFQ_INPUT_V1`，价格仅用 B 冻结 qfq；volume 原值记录、量价确认未验证 | 只可复用 B 实际评估且 C ST/时间证据有效的股票；隔离股票仍记缺口 |
| B：保持 C 未复权定义 | 原 C 定义保持；B 输入不得填充所缺未复权 OHLCV | `PARTIAL_UNVERIFIED`，真实输入仍不完整 |

## 2. C 专属不可变存储

根目录固定为 `data/research/c_prospective_capture_v1/`，不使用 B 的数据路径：

| 路径 | 内容 |
| --- | --- |
| `input_snapshots/YYYYMMDD/input_<input_sha>.json` | provider snapshot 原始规范化字节 |
| `observations/YYYYMMDD/observation_<input_sha>.json` | C 的两条规则研究观察 |
| `manifests/YYYYMMDD/capture_<input_sha>.json` | source、时间点、输入/观察 SHA、质量状态 |
| `captures/YYYYMMDD/captured.json` | 一个 T 日的已核验 capture identity，仅完整时创建 |
| `logs/YYYYMMDD/capture_<input_sha>.json` | 运行、质量缺口和边界日志 |
| `failures/YYYYMMDD/failure_*.json` | 失败、补取和冲突诊断 |

同一 T 日已有 canonical capture 时，同 SHA 重跑只返回 `ALREADY_CAPTURED`；不同输入
SHA 只能写冲突诊断，不得覆盖原始输入、观察或 manifest。输入和输出均使用 canonical
JSON SHA-256，并由 `verify` 子命令复核。证据不足使用
`CAPTURE_PARTIAL_UNVERIFIED`，失败使用 `CAPTURE_FAILED`、`NOT_PROSPECTIVE_BACKFILL`、
`NOT_AFTER_T_CLOSE` 或 `INPUT_CONFLICT` 等保守状态，不伪造完整记录。

## 3. 观察内容

每个 complete、Main Board、T-known non-ST security-date 先进入
`FULL_COMPARABLE_UNIVERSE`，再分别计算 `BALANCED_A` 和 `CONSERVATIVE_B`。每个规则拥有
自己的 `MATCHED_EVENT_SAMPLE`；实现明确记录不同 rule 不天然共享 entry cohort。记录内容
分成：

- price structure：trend、higher-low/pullback、rebound confirmation、support 和 stage
  resistance；
- volume observation：T 日 `RV_T`、回踩 path、directional volume 和相关质量状态；
- signal/execution boundary：T-close signal、T+1 XSHG open reference、no same-day sell、
  no actual fill；
- security identity、ST evidence、T OHLCV、historical prefix、adjustment basis 和 source
  request identity。

`RV_T >= 2.0` 的 scope 固定为 `CONFIRMATION_DAY_ONLY`，只检验确认日 T 放量，不能写成
完整回踩量能路径。T-close observation 的 mark-to-market / 浮盈语义与 T+1 reference
execution P&L 分离；捕获阶段不读取未来价格，不计算后者。

统一成本模型、费率/滑点版本和合法来源必须在正式收益研究前固定。当前捕获只记录
`TRANSACTION_COST_MODEL_MUST_BE_PINNED_BEFORE_FORMAL_RETURN_RESEARCH`，不利用 future
outcome 调参。

## 4. 失败隔离与启用前置条件

C 失败只写 C 的 failure/log namespace，不阻断 B，也不触碰 B 的 watchlist、日报、调度、
Shadow、tracker 或 `runtime-state`。在 Sol activation audit 之前，不启用真实定时运行、
正式通知或 provider adapter。

正式启用前仍需：Sol 审计通过 C 只读交接、口径与 failure semantics；完成最小 B 原始输入
导出及其独立交接、C 私有状态持久化和一次真实同日 T-close 捕获人工验收。只有启用备用的
C 自行请求 HiThink 方案才需要独立凭证及独立配额证明。上述条件未满足时，
只能运行合成测试或显式手工验证，不能把历史补取标成前瞻证据。
