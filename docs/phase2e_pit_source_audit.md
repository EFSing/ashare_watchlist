# Phase 2E：PIT Validation Dataset Source Audit

审计日期：2026-08-28（Asia/Shanghai）
审计基线：`master@4ea7b5cf050c1cc50b0043ea3608acf6c14953e3`
适用协议：`PHASE2D_VALIDATION_PROTOCOL_V1`

## 当前结论

当前状态是 `REQUIRES_HISTORICAL_SECTOR_MEMBERSHIP_SOURCE`，不是
`BLOCKED_NO_PIT_DATASET`。同花顺 Financial-API 的统一 Key 已验证可用，现有
Financial-API REST 与 market dump 足以覆盖历史 raw K、sector/index K、公司行为和
确定性 T-anchor 复权。唯一尚未解决的字段是：

```text
historical sector membership / effective-date membership
```

因此没有把 iFinDPy、经典 iFinD 或 `THS_DataPool` 作为当前 Financial-API 链路的前置
条件。机器可读记录见
[`phase2e_source_audit.json`](../data/validation/phase2e_source_audit.json) 和
[`phase2e_hithink_probe.json`](../data/validation/phase2e_hithink_probe.json)。

## 1. Financial-API 生态审计

已检查官方 REST 的股票/指数历史 K、THS catalog/constituents、corporate actions，
以及官方 Python `marketdb` 的 `raw_kline_daily`、`raw_adjustment_events`、
`calc_adjust_factor_daily`、`dim_symbol` 和两个全市场 dump。结论如下：

- `ths-stock-list` 是 current constituents；`as_of_date=2024-01-10` 与默认查询返回
  相同成员数组和当前时间戳，没有历史调入/调出序列。
- `marketdb` 有 raw K、公司行为、日级复权因子和标的目录，但没有 historical
  sector-membership 或 effective-date 表。
- 官方 dump 类型只有 daily-K、daily-K-10d、adjustment-factors；没有 membership
  dump。
- 本工作区在 probe 前没有本地 `marketdb`、DuckDB 或 Parquet 快照；当前使用的是
  REST 与实际下载的 adjustment dump probe，不含任何凭证值。

官方接口边界见 [THS index/constituents contract](https://github.com/HiThink-Tech/Financial-API/blob/main/docs/mcp/hithink-finance-a-share-index.md)、
[marketdb schema](https://github.com/HiThink-Tech/Financial-API/blob/main/python/toolkit/marketdb/docs/schema.md)
和 [market dumps contract](https://github.com/HiThink-Tech/Financial-API/blob/main/docs/api/endpoints-market-dumps.md)。

## 2. 真实 REST / dump probe

`HITHINK_FINANCE_API_KEY` 只通过本机环境变量读取；请求返回 HTTP 200、`code=0`。
probe 只记录环境变量名、presence/empty 状态、响应摘要和哈希，没有打印或落盘 Key。

实际验证了多个历史日期：`2024-01-10`、`2025-06-18`、`2026-08-20`。

- 历史股票 K：`600519.SH` 的 unadjusted 日线可取。
- 历史 sector/index K：`886042.TI` 的日线可取。
- `sector_chg`：由 T 日收盘与前一交易日收盘确定性计算。
- `sector_rank`：由同一 T 日的完整 sector universe 和各 sector 的 T 日涨跌排序
  确定性计算，不要求 provider 直接返回 rank。
- 当前股票代码表和 THS 成分接口均明确不能提供历史 sector membership。

## 3. T-anchor adjustment 验证

官方 individual corporate-actions endpoint 的 `to=T` 过滤生效，事件按
`ex_date<=T` 截断；官方 adjustment dump 实际下载并解析出：

```text
57,010 rows
5,419 thscode
columns: thscode, ticker, ex_date_ms, dividend_per_share,
         per_share_bonus, allotment_ratio, allotment_price, currency
nonzero allotment rows: 987
nonzero bonus rows: 12,297
nonzero dividend rows: 52,626
dump sha256: da1227be82f4e1d7cf9602a6ea6a0005542a9e0cca4b0626e7e98178aaa425f6
```

对每只股票，将不复权 OHLCV 作为 raw input，仅应用满足
`date < ex_date <= T` 的事件，并按除权日升序执行以下仿射变换：

```text
adjusted_price =
    (price - dividend_per_share + allotment_price * allotment_ratio)
    / (1 + per_share_bonus + allotment_ratio)
```

这不是把今天锚定的 provider `forward` 改名成历史 T-anchor。provider `forward` 只
作为当前结果的交叉核对，T-anchor 的锚点行必须保持 raw price 不变。

真实结果：

- `600519.SH`：773 根 raw 日线、7 个历史事件；与 provider forward 的当前锚定
  交叉核对最大绝对误差为 `0.0`；`2024-06-18`、`2025-06-18`、`2026-08-20`
  的 T-anchor identity 均通过。
- `000049.SZ`：从官方 dump 读取到 `2023-12-08` 的配股事件
  (`allotment_ratio=0.3`, `allotment_price=21.16`)；880 根 raw/forward 日线
  交叉核对最大绝对误差为 `0.0`，所有测试锚点 identity 均通过。

此前的“单纯乘法因子”假设已纠正：现金分红在该接口语义下是仿射减项；送股/配股
通过分母和配股价格进入同一变换。完整 probe 数值见 JSON artifact。

## 4. 各字段的冻结边界

| 字段 | 当前判定 |
| --- | --- |
| historical raw OHLCV | Financial-API REST / daily-K dump 可获取；采集时归档 raw payload、source version 和 hash |
| stock universe | 可由历史 raw K 行与交易日历构造 T 日 tradable/security set；current ticker list 不作历史回填 |
| sector/index K | 可获取；`sector_chg` 可确定性计算 |
| sector rank | 计算规则已确定；等待同一 T 日完整 sector membership |
| T-anchor adjustment | 已用 REST raw K + `<=T` 事件和官方 dump 配股字段验证 |
| historical sector membership | **未解决，唯一 blocker** |

## 5. 当前唯一 blocker

`HISTORICAL_SECTOR_MEMBERSHIP_UNAVAILABLE`：官方 Financial-API 当前成分接口、
marketdb schema 和 market dump 都没有历史 sector membership 或 effective-date
记录。所需新增能力被严格限制为以下之一：

1. 一个能按 T 返回 sector members 的官方/已有导出；或
2. 一个带 `effective_date` / 调入调出序列的已有数据源或权限。

这不是 OHLCV、sector_chg、sector_rank 或 adjustment 的 blocker，也不需要重新提供
同花顺 Key。拿到历史 membership 后，才能进入 acquisition contract 的完整落盘、
provenance/hash 校验和 validation dataset freeze。

## 6.1 两层 historical validation 决策点

代码已冻结两层 contract；本轮已完成 `CORE_SIGNAL_VALIDATION` 的工程 replay，尚未启动任何历史收益验证：

- `CORE_SIGNAL_VALIDATION`：只验证 exact A eligibility、hard rejects、support、stop、
  target、RR、trigger 和 qualified signal identity；sector score/report 标记为
  `UNVERIFIED`，不宣称 full legacy output parity，也不启用 returns、调参或 final OOS。
- `FULL_LEGACY_OUTPUT_VALIDATION`：除上述核心输出外，必须取得 exact V0 的历史新浪行业
  membership，才能验证完整 85-score 与 legacy sector report。

当前明确停在：`CORE_SIGNAL_VALIDATION` 已完成并冻结结果，等待是否解锁收益 validation；
`FULL_LEGACY_OUTPUT_VALIDATION` 继续因历史新浪行业 membership 缺失而 blocked。机器可读
contract 见 [`historical_validation_layers.py`](../scripts/historical_validation_layers.py)。
本次已授权的 core-only 工程 replay 记录见
[`core_signal_validation.md`](core_signal_validation.md)；它不包含收益指标，也不解除
FULL layer 的历史新浪行业 membership blocker。

## 7. 保留的禁止动作

- `current_universe_backfill`
- `current_sector_backfill`
- `provider_qfq_relabel_as_historical_qfq`
- `known_at_fabrication`
- `historical_strategy_validation`
- `parameter_tuning`
- `final_oos`
- `production_promotion`
