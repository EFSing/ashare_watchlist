# C_PROSPECTIVE_CAPTURE_V1

状态：`C_B_TO_C_HANDOFF_AND_PRICE_BASIS_READY_FOR_SOL_DECISION`；真实交接尚未完成，
`PROSPECTIVE_CAPTURED` 尚未成立。

这是新版 C 的独立 T-close 前瞻捕获契约。它只生成研究观察，不生成正式交易名单、不
写入 B 的 `runtime-state`、不调用 B evaluator / Shadow / return tracker / daily report，
不自动下单，也不做正式历史收益研究。

## 1. 入口与时间点

优先入口是 `scripts/c_b_input_adapter.py`：只读一个 B 成功收盘后冻结的完整
`CANDIDATE_BOUND_LIVE_INPUT_PACKAGE_V4` 文件，以调用方给出的文件 SHA-256 和包内
`content_sha256` 双重校验，再按 C 自己的 `BALANCED_A` / `CONSERVATIVE_B` 规则计算观察。
调用方必须提供 T 日和预期 SHA；候选名单、checkpoint 或 `runtime-state` 里的摘要不能代替
全量原始输入。C 只写 `data/research/c_prospective_capture_v1/shared_input/`，从不修改 B 文件。
输入未就绪时写 C 私有 `CAPTURE_FAILED` 诊断，允许同日 B 重试成功后重新消费。

当前 B package 只在生产 runner 的临时 data root 留存；`runtime-state` 白名单不包含它，
也不包含 T-close raw evidence。C 工作流已移除早于 B 的 15:15 BJT 定时任务，保持禁用。
独立 B 导出草案从成功结果的 `input_package.path/file_sha256` 读取 package，按
`provenance.evidence_capture.captures` 原样复制每个 `.raw` 与 `.json` sidecar，
用 `handoff.json` 记录逐文件 SHA、字节数、package 内部 content SHA、覆盖记录和导出时间。
独立 B Draft PR 将目录压缩后上传到配置的私有 GitHub 仓库 release asset；默认未配置，
不会运行。C 的手工工作流按 T 日和 package SHA 下载指定 asset，验证包内逐文件 SHA，
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
| 价格/量口径 | B 股票历史请求明确 `adjust=forward`，逐票标记 `PROVIDER_QFQ_SNAPSHOT`；bar 字段为 date/open/high/low/close/volume/turnover | 同日冻结响应也是 qfq，请求中没有未复权 OHLC 或调整因子；volume 有数值但单位/原始语义未获证实 | `INCOMPATIBLE` |
| provider 请求/接收时间 | B package 有运行开始的 `retrieved_at_bjt`，raw metadata 复用这一时间 | 逐请求真实时间缺失 | `NOT_PERSISTED` |
| 包 manifest、generation fingerprint、SHA | 完整 package 内可核验；成功 runner 结果有文件 SHA | checkpoint/runtime-state 只有局部引用，无完整字节 | runner 内 `AVAILABLE_VERIFIED`；跨任务 `NOT_PERSISTED` |
| `NO_VALID_INPUT`/持久化失败 | 诊断可能进入 runtime-state；raw 留 runner 临时目录 | 无完整 package | `NOT_PERSISTED` |

2026-09-22 远端 `runtime-state` checkpoint SHA-256 为
`826f02807bb58846788137bdaa85d47455fa679497dbd82f49f5cf2898b8ccb1`：
原始 universe 5,576，合格主板 3,196，实际评估 3,187，9 只
`TARGET_DAY_HISTORICAL_STALE` 被隔离。它保存覆盖缺口，但没有完整 package/raw 字节；
不能据此伪造 package SHA 或对 9 只计算 C 观察。真实 B `LiveInputPackage.to_bytes()`
兼容性测试已经核验文件 SHA、内部 content SHA、逐票 K 线 SHA、覆盖与 raw sidecar。

因此当前只读消费最多是 `CAPTURE_PARTIAL_UNVERIFIED`；完整 raw bytes、T-known ST、
逐请求时间、持久化时间及复权/成交量口径经证实兼容之前，不得生成
`PROSPECTIVE_CAPTURED`。现有 C 专属 HiThink adapter 仅作为关闭的备用路线，只有它自行发出
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
| A：采用 B qfq | 需先固定新的明确价格/成交量协议身份和 volume 来源语义，不使用未来收益选择 | 可复用 B 实际评估股票；隔离股票仍记缺口；待用户研究口径决定 |
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
