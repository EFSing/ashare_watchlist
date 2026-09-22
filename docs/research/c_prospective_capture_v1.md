# C_PROSPECTIVE_CAPTURE_V1

状态：`IMPLEMENTED_NOT_ACTIVATED`；终点：
`C_PROSPECTIVE_CAPTURE_PR_READY_FOR_SOL_ACTIVATION_AUDIT`。

这是新版 C 的独立 T-close 前瞻捕获契约。它只生成研究观察，不生成正式交易名单、不
写入 B 的 `runtime-state`、不调用 B evaluator / Shadow / return tracker / daily report，
不自动下单，也不做正式历史收益研究。

## 1. 入口与时间点

入口为：

```text
python scripts/c_prospective_capture.py capture \
  --date YYYY-MM-DD \
  --input-snapshot <C_PROVIDER_SNAPSHOT_V1.json> \
  --output-root data/research/c_prospective_capture_v1
```

`C_PROVIDER_SNAPSHOT_V1` 由未来 C 专属 provider adapter 生成。该模块本身不联网，因而
不会与 B 争用请求配额或运行资源。snapshot 必须包含：

- `capture.mode=SAME_DAY_T_CLOSE`、provider/version 和每个 request 的 source、endpoint、
  `requested_at`、`received_at`、response identity；
- 每只证券的 code/symbol/exchange/name/security identity；
- T 日已知的 ST/*ST status、`known_at_t`、as-of date 和来源；
- T 日 OHLCV、严格早于 T 的 historical prefix；
- price basis、raw volume basis、调整来源和 T-known policy。

请求和接收必须在 T 日 XSHG session close 之后；runner 也必须在同一 T 日执行。任何
周末补取、次日补取、future bar、T 日前请求或缺少上述证据都会 fail closed。只有所有
必需证据完整且确实同日完成时，顶层状态才可为 `PROSPECTIVE_CAPTURED`。

## 2. C 专属不可变存储

根目录固定为 `data/research/c_prospective_capture_v1/`，不使用 B 的数据路径：

| 路径 | 内容 |
| --- | --- |
| `input_snapshots/YYYYMMDD/input_<input_sha>.json` | provider snapshot 原始规范化字节 |
| `observations/YYYYMMDD/observation_<input_sha>.json` | C 的两条规则研究观察 |
| `manifests/YYYYMMDD/capture_<input_sha>.json` | source、时间点、输入/观察 SHA、质量状态 |
| `captures/YYYYMMDD/canonical.json` | 一个 T 日的 canonical capture identity |
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

正式启用前仍需：Sol 审计通过 C protocol/capture identity 和 failure semantics；配置
独立的 C provider adapter、凭证及配额（不能复用或争用 B 的关键配额）；配置独立持久化
根目录和保留策略；完成一次真实同日 T-close capture 的人工验收。上述条件未满足时，
只能运行合成测试或显式手工验证，不能把历史补取标成前瞻证据。
