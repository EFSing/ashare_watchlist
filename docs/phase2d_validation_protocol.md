# Phase 2D：Validation Protocol / Point-in-Time Data Design

本阶段只冻结 `A_PLATFORM_BREAKOUT_LEGACY_V1` 的历史验证输入与 replay
治理协议。它不抓取大规模数据，不执行正式历史验证，不读取收益结果，不调
legacy 参数，不创建 production watchlist，也不做 promotion。

协议版本：`PHASE2D_VALIDATION_PROTOCOL_V1`

当前 protocol semantic SHA-256：
`a7db6dc2d6f2dba2555855236fce5580f5e13e192e66991f0f9f63cb0eb9e7ee`

协议 semantic SHA-256 由 `scripts/validation_contract.py` 中的
`VALIDATION_PROTOCOL_SEMANTIC_SPEC` 以 canonical JSON 计算。它只覆盖语义
规则，不覆盖源码格式、文档排版、`created_at`、`retrieved_at` 或运行结果。

## 1. Validation data contract

历史信号日记为 `T`。任何进入验证输入的字段都必须证明其首次可知时间
`known_at <= T`，并且用于 T 的 observation/effective date 必须明确覆盖 T。
没有证明的字段不能降级为当前值；必须返回机器可读失败状态并排除该输入。

### Universe

Universe 必须是 `POINT_IN_TIME` 的 T 日快照，并记录：

- `symbols`；
- `source` 与 `source_version`；
- `as_of_date=T`；
- `known_at<=T`；
- `content_sha256`。

当前成分股、当前指数成分、当前筛选结果或 `LIVE_OBSERVED` 数据不得回填过去。
`is_current_snapshot=true`、`backfilled_from_current=true`、缺 source/version/hash、
日期在 T 之后，均 fail-safe；不返回“近似可用”的股票池。

### Sector evidence

Sector 也必须是 `POINT_IN_TIME` 的 T 日证据，不能只提供一个当前分类名称。
每个验证输入至少要保留：

- `membership`：T 日成员关系；
- `rank`：由同一 T 日可用的板块集合计算/发布的 rank；
- `sector_chg`：同一 T 日可用的板块变化值；
- `source`、`source_version`、`as_of_date=T`、`known_at<=T`、`content_sha256`。

冻结的 payload 形状为：`membership` 是非空的
`symbol -> [sector_name, ...]` mapping；`rank` 是非空的
`sector_name -> finite positive number` mapping；`sector_chg` 是非空的
`sector_name -> finite number` mapping。`rank` 与 `sector_chg` 必须覆盖同一
组板块，membership 中引用的板块必须有对应 rank/change。`sector_chg=0` 是
合法数值，不代表字段缺失；任意 truthy 的字符串、对象、非 finite 数值或错误
结构都会返回 `INVALID_SECTOR_EVIDENCE`。

Phase 2B 的当前 AkShare 板块成员和现货排名是 `LIVE_OBSERVED`，不能用于
历史 replay。当前 sector classification 不得静默回填过去；缺 membership、
rank 或 `sector_chg` 时返回 `MISSING_POINT_IN_TIME_EVIDENCE`。

### Historical OHLCV and adjustment

OHLCV 必须记录 `source`、`source_version`、`as_of_date=T`、`known_at<=T`、
`content_sha256` 和 `adjustment_semantics`。允许的历史语义是：

| 语义 | 是否可用于未来 validation | 条件 |
| --- | --- | --- |
| `UNADJUSTED_OHLCV_AS_OF` | 可以 | 原始 OHLCV 的 T 日可知快照 |
| `HISTORICAL_ADJUSTED_AS_OF` | 可以 | 另有独立、point-in-time 的 adjustment evidence |
| `HISTORICAL_QFQ_AS_OF` | 可以 | 明确写明历史 qfq 重建语义，并有独立 adjustment evidence |
| `PROVIDER_QFQ_SNAPSHOT` | 不可以 | 这是 Phase 2B provider 返回快照，不是历史时点复权 |

因此，“历史 qfq”不能把 `PROVIDER_QFQ_SNAPSHOT` 改名后当成历史复权。
调整因子/公司行为证据本身也必须满足 PIT；调整后的 bars 如果含有任何
`date > T` 或 bar-level `known_at > T`，直接返回 `FUTURE_DATA_INPUT`。

## 2. Frozen validation dataset schema

Phase 2D 只定义 manifest，不抓取或提交正式数据。冻结记录由
`freeze_validation_dataset()` 生成，schema 为
`FROZEN_VALIDATION_DATASET_MANIFEST_V1`，且 `data_partition` 必须为
`validation`。

manifest 至少包含：

| 字段 | 语义 |
| --- | --- |
| `dataset_version` | 数据集版本，而非策略版本 |
| `market` | 市场身份，例如 `CN_STOCKS` |
| `symbol` | 该 artifact 的标的身份 |
| `date_range` | canonical `{start, end}`，其中 `end` 为 signal date |
| `universe_source`, `universe_source_version` | PIT universe 来源与版本 |
| `sector_source`, `sector_source_version` | PIT sector 来源与版本 |
| `ohlcv_source`, `ohlcv_source_version` | OHLCV 来源与版本 |
| `adjustment_semantics` | 明确历史复权语义 |
| `calendar` | 固定 `XSHG` |
| `timezone` | 固定 `Asia/Shanghai` |
| `content_sha256` | 外部冻结内容的 SHA-256；本阶段不生成内容 |
| `manifest_sha256` | manifest canonical payload 的 SHA-256，不含自身 |
| `created_at`, `retrieved_at` | provenance/runtime metadata，不参与 protocol semantic hash |
| `*_provenance` | 完整 PIT evidence，保留 source/version/date/known_at/hash |
| `protocol_semantic_sha256` | 本协议规则 hash |

加载 manifest 时，`schema_version` 必须严格等于
`FROZEN_VALIDATION_DATASET_MANIFEST_V1`，`protocol_version` 必须严格等于
`PHASE2D_VALIDATION_PROTOCOL_V1`；缺失或错误版本均 fail-safe，不能被 pop 后
忽略。

canonical manifest 使用 UTF-8、无空白分隔符、稳定 key 顺序、稳定的日期/时间
表示；mapping 顺序、JSON 缩进和字段排版不影响 canonical payload。manifest 的
内容 hash、manifest hash、协议 semantic hash 是三种不同身份：内容变化应改变
`content_sha256`；manifest 元数据变化可改变 `manifest_sha256`；只有协议规则
变化才能改变 `protocol_semantic_sha256`。

`load_validation_manifest()` 会在文件读取前拒绝路径中的 `final_oos`；加载后
仍拒绝 manifest/source/provenance 中的 final OOS 标识，并拒绝 development/
engineering 分区。Phase 2D loader 不提供读取 final OOS 的 fallback。

## 3. Replay protocol

未来实现 replay 时必须遵守以下顺序和边界：

1. `signal_date=T`，先冻结 T 收盘后的验证输入；
2. 所有 universe、sector、adjustment evidence、bar 和已知时间都只能来自
   `<=T`；
3. strategy evaluation 只能在 T 收盘数据冻结后运行；
4. 最早执行日固定为 XSHG 下一交易日 `T+1`；
5. 禁止 same-bar execution，禁止任何 future bar；
6. 缺失历史 universe、sector 或 adjustment evidence 时返回明确状态，不得补
   当前 universe、当前 sector 或当前复权结果；
7. replay 输出必须携带 `strategy_spec_sha256` 与 `dataset_manifest_sha256`，
   并同时保留 protocol semantic hash。

`ReplayPlan` 只生成/校验这个 envelope，不包含收益结果，也不启动 evaluator。
`A_PLATFORM_BREAKOUT_LEGACY_V1` 的 strategy spec SHA 继续使用 Phase 2C.1
冻结值；本阶段不修改它。

## 4. Data partitions and tuning boundary

| 分区 | 用途 | Phase 2D 是否读取 |
| --- | --- | --- |
| `development` / `engineering` | 工程 fixture、schema 和单元测试 | 仅作为概念分区；validation loader 拒绝 |
| `validation` | 未来按本协议冻结并 replay 的验证数据 | 只定义 loader/schema，不运行正式验证 |
| `final_oos` | 最终封存的 out-of-sample 数据 | 完全封存，Phase 2D 不读取 |

不得根据 validation 输出继续调 `A_PLATFORM_BREAKOUT_LEGACY_V1`。如果未来
确实需要调参，必须创建新的 strategy version、新的 strategy spec hash，并
重新声明 validation boundary；不能把同一版本的 validation 结果当作新的
research 自由度。

## 5. Promotion gate：只冻结允许的证据

`PromotionGateSpec` 只是一份 evidence checklist，不计算结果、不打分、不
给出 promotion decision。未来允许评估的非收益证据至少包括：

- deterministic replay；
- input completeness；
- point-in-time provenance；
- signal frequency；
- cross-period structural stability；
- concentration；
- sensitivity / robustness。

未来 validation 可以把 `return`、`win_rate`、`MFE`、`MAE`、`expectancy`、
`P&L`、`profit factor` 作为评价证据，但 Phase 2D 不读取、不计算，也不使用
这些指标修改 legacy 参数。

Phase 2C 的 85 分是 legacy feature score；本协议明确声明它不是已经验证的
predictive score。target/stop、score cutoff、TOP N、portfolio/position sizing、
收益回测和 production promotion 均不在本阶段。

## 6. Frozen statuses

实现至少使用以下 fail-safe 状态：

`MISSING_POINT_IN_TIME_EVIDENCE`、`CURRENT_DATA_BACKFILL`、
`FUTURE_DATA_INPUT`、`INPUT_DATE_MISMATCH`、`UNSUPPORTED_ADJUSTMENT_SEMANTICS`、
`SAME_BAR_EXECUTION`、`REPLAY_TIMING_INVALID`、`FINAL_OOS_FORBIDDEN`、
`PARTITION_FORBIDDEN`、`MANIFEST_HASH_MISMATCH`、
`MANIFEST_SCHEMA_VERSION_INVALID`、`MANIFEST_PROTOCOL_VERSION_INVALID`、
`INVALID_SECTOR_EVIDENCE`。

这些状态只描述输入/治理问题；没有任何状态会自动切换到当前数据或把
Phase 2B live snapshot 视为历史证据。

## 7. Phase 2D boundary

本阶段不修改 `scripts/a_platform_breakout.py`，不修改 Phase 2C evaluator
eligibility、阈值、85 分 score、target/stop 公式，不执行正式历史收益验证，
不读取 `final_oos`，不做 B/C/D、canonical watchlist、TOP N、portfolio、
position sizing、scheduler、production promotion 或 merge。
