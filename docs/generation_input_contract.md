# Phase 2B：Generation Input & Timing Contract Freeze

本阶段只冻结生成系统的输入与时点契约。仓库仍然没有正式 generation
strategy；本阶段不实现 A/B/C/D 策略、评分、选股、调参、调度或 historical
replay。

## 1. 生成时点

唯一支持的 `RunContext` 是：

| 字段 | 契约 |
| --- | --- |
| `mode` | `close` |
| `as_of_date` | 完整交易日 T |
| `signal_date` | T（由调用方按该语义产生，输入 manifest 不允许另取日期） |
| `earliest_execution_date` | XSHG 日历中的下一个交易日 T+1 |
| `timezone` | `Asia/Shanghai` |
| `calendar` | `XSHG` |

输入必须在 T 日数据完整后才冻结。禁止 premarket generation、same-bar
execution、把 T+1 数据用于 T 日信号，以及用当前数据冒充历史日期。调用方
若设置 `RunContext(historical=True)`，入口立即返回
`UNSUPPORTED_HISTORICAL_REPLAY`；这不是 replay 的降级实现。

`LIVE_OBSERVED` 不是装饰性标签：每个 live `UniverseManifest`、
`QuoteSnapshotManifest`、stock `KlineManifest`、`IndexManifest` 和
`SectorManifest` 的 `retrieved_at_bjt` 北京时间日期必须等于 T。仅有
`historical=False` 不能绕过这项约束。

`mode=close` 还要求每个 live 输入的 `retrieved_at_bjt` 不早于 XSHG 当日正式
`session_close`。正式收盘时点本身可以通过；盘中时间必须 fail-fast 为
`SESSION_NOT_CLOSED`，不添加 15:05、15:10 等人工缓冲。

`next_execution_date()` 和 `RunContext.earliest_execution_date()` 使用现有的
XSHG 日历接口，周末和法定节假日都会跳过。日历不可用或 T 不是 XSHG session
时 fail-fast 为 `CALENDAR_ERROR`。

## 2. 独立输入 manifest

`scripts/generation_contract.py` 提供以下不可变数据对象：

| 对象 | 记录内容 |
| --- | --- |
| `RunContext` | T、close 模式、时区、XSHG 日历、是否显式 historical、provider/version metadata |
| `UniverseManifest` | T、BJT 获取时间、source、排序后的 symbols、symbol count、`LIVE_OBSERVED`/`POINT_IN_TIME`、content SHA-256 |
| `QuoteSnapshotManifest` | T、BJT 获取时间、provider/source、按 symbol 的完整 quote、content SHA-256 |
| `KlineManifest` | 一个股票的 bars、provider、adjustment mode、首末 bar 日期、bar count、normalized data SHA-256 |
| `IndexManifest` | 一个指数的 bars，以及与 `KlineManifest` 相同的覆盖和复权证据 |
| `SectorManifest` | T、BJT 获取时间、source、板块 definitions/members/rank input、temporal semantics、content SHA-256 |
| `GenerationInputManifest` | 所有上述输入、READY 状态、T+1、provider/version metadata、input fingerprint |

唯一的冻结入口是：

```python
from generation_contract import freeze_generation_inputs

manifest = freeze_generation_inputs(
    run_context,
    universe,
    quote_snapshot,
    stock_klines,
    index,
    sector,
)
assert manifest.status == "READY_FOR_STRATEGY_EVALUATION"
```

返回 `GenerationInputManifest` 代表输入可以交给未来的策略评估；它本身不
执行任何策略。

## 3. 日期与覆盖校验

入口先验证 T 是 XSHG session，然后进行全量日期检查：

- 每个 quote 的 `quote_date` 必须等于 T；
- 每个个股 K 线的 `last_bar_date` 必须等于 T，任何 `date > T` 的 bar 都是
  `FUTURE_DATA_DETECTED`；
- 指数 K 线的 `last_bar_date` 必须等于 T，不能包含未来 bar；
- 股票池中的每个 symbol 都必须有 quote 和个股 K 线；
- 任一 manifest 的 as-of 日期不一致、K 线最后日期早于 T 或指数缺失，均不
  会静默继续生成。

日期不一致为 `INPUT_DATE_MISMATCH`，缺输入或空覆盖为
`INCOMPLETE_COVERAGE`。所有失败都抛出 `GenerationContractError`，并在
`.status` 上暴露机器可读状态。

## 4. 腾讯 qfq 语义

当前 live close generation 可以使用腾讯 qfq 日 K，但冻结语义只能写作：

```text
PROVIDER_QFQ_SNAPSHOT
```

它表示 provider 当次返回的 qfq snapshot，不是 point-in-time historical
adjustment。每个 `KlineManifest`/`IndexManifest` 都记录或计算：

`provider`、`adjustment_mode`、`first_bar_date`、`last_bar_date`、
`bar_count`、`normalized_data_sha256`。

本阶段不重建历史复权因子。腾讯将来重新计算 qfq 时，已经保存的 manifest
及其 SHA-256 仍是冻结的历史输入证据；新的返回值必须产生新的 normalized
data SHA-256，不得改写旧证据。

## 5. LIVE_OBSERVED 限制

当前 AkShare 股票池必须标记 `LIVE_OBSERVED`，并记录 T、
`retrieved_at_bjt`、source、排序后的 symbols、symbol count 和
`content_sha256`（排序后的 symbols 与 temporal marker 的内容哈希）。它只能
用于 observation date 等于 T 且已过 XSHG session close 的当日 close
generation，不能用于过去日期 replay。

当前 AkShare 板块 definitions/members/rank input 也必须标记
`LIVE_OBSERVED`，记录 BJT 获取时间、source、完整输入和
`temporal_semantics`/`content_sha256`（definitions、members、rank input 与
temporal marker 的内容哈希）。其 observation date 也必须等于 T，并且只能
在正式 session close 后用于当日 close generation。当前成员不能倒灌历史。未来真正的
historical replay 必须接入另一个 `POINT_IN_TIME` sector source，并在本阶段
之外单独设计；本阶段即使拿到该标记也仍不实现 replay。

## 6. Deterministic input fingerprint

`GenerationInputManifest.input_fingerprint` 是以下 payload 的 SHA-256：

```text
as_of_date
calendar
mode / timezone
universe_hash
quote_hash
stock_kline_hashes {symbol: normalized_data_sha256}
index_hash
sector_hash
adjustment_mode
provider/version metadata
provider/source identities
```

payload 不含 `input_fingerprint` 自身，也不含任何 `retrieved_at_bjt`。所有
mapping key 都按 canonical JSON 排序；symbols、stock K 线和 sector member
集合按稳定顺序归一化。因此 dict key 顺序、symbol 顺序或只改变获取时间不会
改变 fingerprint。任何实际 quote、bar、板块输入内容变化都会改变对应内容
SHA-256，并进而改变总 fingerprint。

## 7. 状态与范围边界

当前公开状态至少包括：

`READY_FOR_STRATEGY_EVALUATION`、`INPUT_DATE_MISMATCH`、
`FUTURE_DATA_DETECTED`、`INCOMPLETE_COVERAGE`、`UNSUPPORTED_MODE`、
`UNSUPPORTED_HISTORICAL_REPLAY`、`CALENDAR_ERROR`、`SESSION_NOT_CLOSED`。

本阶段明确不恢复 `screen_system.py`，不实现 A/B/C/D，不修改旧阈值、85 分
评分、`perf_tracker` 或历史 watchlist，不接生产调度，不做 historical replay，
也不 merge。Phase 2C 的策略定义、输入消费方式、是否需要 point-in-time
universe/sector/adjustment source 等决策留待下一阶段，Phase 2B 完成后停止。
