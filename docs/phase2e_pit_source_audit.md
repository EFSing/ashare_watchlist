# Phase 2E：PIT Validation Dataset Source Audit

审计日期：2026-08-28（Asia/Shanghai）

审计基线：`master@4ea7b5cf050c1cc50b0043ea3608acf6c14953e3`

适用协议：`PHASE2D_VALIDATION_PROTOCOL_V1`
审计结论：`BLOCKED_NO_PIT_DATASET`

## 1. 审计标准

本阶段要求的是 future historical validation 的输入数据，不是“现在查询、再
按历史日期命名”的数据。对每个 signal date `T`，universe、sector、OHLCV 和
adjustment evidence 都必须同时满足：

- 明确的 `as_of_date=T` 或覆盖 `T`；
- `known_at<=T`，且这个关系有可核验的证据；
- source、source version / immutable vintage、原始 payload 的 SHA-256；
- sector 必须同时包含 T 日 membership、由同一 T 日板块集合得到的 rank 和
  `sector_chg`；
- 复权 OHLCV 必须有独立的 PIT adjustment evidence；不能把 provider 当前 qfq
  结果改名为历史 qfq。

如果接口只返回历史日期、纳入/剔除日期或当前数据库结果，但不提供可核验的
vintage / `known_at`，本审计将其标记为 `REJECTED_NO_PIT_PROOF`。这不是缺少
哈希的问题：对未保存的 payload 计算一个今天的哈希，仍不能证明数据在 T 日已
经可知。

## 2. 仓库内现有来源

| 来源 | 能提供的内容 | PIT 判定 | 不能满足的条件 |
| --- | --- | --- | --- |
| Tencent `qfqday` / `ifzq` | 个股或指数历史行情、provider qfq 快照 | `REJECTED_NO_PIT_PROOF` | Phase 2B/2D 已冻结为 `PROVIDER_QFQ_SNAPSHOT`；没有 T 日 adjustment vintage 或独立 adjustment evidence |
| Phase 2B AkShare live universe | 当前股票池 | `REJECTED_CURRENT_DATA` | 是 `LIVE_OBSERVED`，没有历史 T 日快照；不能回填过去 |
| Phase 2B AkShare sector inputs | 当前板块成员和实时板块排名/变化 | `REJECTED_CURRENT_DATA` | 是 `LIVE_OBSERVED`，不能提供历史 T 日 membership、rank、`sector_chg` |
| 仓库静态 JSON / legacy 文件 | 观察名单和遗留审计材料 | `REJECTED_NOT_DATASET` | 没有全市场 PIT universe、OHLCV、adjustment 或 sector payload；不能反推历史输入 |

仓库的 `pyproject.toml` 也没有安装或配置 AkShare、Tushare、BaoStock、Wind、
CSMAR、JoinQuant 等数据客户端或凭证。此次没有为了“填满”数据集而安装客户端、
请求当前接口或下载当前快照。

## 3. 公开候选接口审计

以下是文档级能力审计。文档能证明接口“可查询什么”，不自动证明其结果具有
历史版本语义；因此结论按 Phase 2D 的严格 `known_at` 标准判定。

| 候选来源 / 接口 | 文档中可见能力 | PIT 判定 | 结论 |
| --- | --- | --- | --- |
| [AkShare `stock_board_industry_cons_em`](https://akshare.akfamily.xyz/data/stock/stock.html) | 行业板块成分查询 | `REJECTED_NO_PIT_PROOF` | 没有 T 日 immutable sector membership vintage；不能作为历史 membership |
| [AkShare `stock_board_industry_name_em` / `stock_board_industry_hist_em`](https://akshare.akfamily.xyz/data/stock/stock.html) | 板块名称、行情和历史行情 | `REJECTED_NO_PIT_PROOF` | 不能证明 T 日板块集合、排名和变化值是在 T 日可知且版本冻结；不能生成完整 sector contract |
| [AkShare `index_stock_cons_csindex`](https://akshare.akfamily.xyz/data/index/index.html) | 中证指数成分目录，带日期字段 | `REJECTED_SCOPE_MISMATCH` | 是指定指数成分，不是 legacy validation 所需的全市场 universe；文档未提供可回溯的 T 日 vintage / `known_at` |
| [Tushare `stock_basic`](https://tushare.pro/document/1?doc_id=25) | 当前股票基础信息、上市/退市日期 | `REJECTED_NO_PIT_PROOF` | 当前 catalog 和 effective dates 不能证明 T 日股票池快照及其当时可知版本 |
| [Tushare `index_member_all`](https://tushare.pro/document/2?doc_id=335) | 申万成分及 `in_date` / `out_date` | `REJECTED_NO_PIT_PROOF` | 可表达有效区间，但接口没有证明历史返回结果的 immutable vintage / `known_at`；仍不能直接作为 T 日 sector evidence |
| [Tushare `index_weight`](https://tushare.pro/document/2?doc_id=96) | 指定指数的月度成分和权重 | `REJECTED_SCOPE_MISMATCH` | 只覆盖指定指数和月度权重，不提供所需 sector membership/rank/`sector_chg` 全量 PIT 输入；无 vintage 证据 |
| [Tushare `pro_bar`](https://tushare.pro/document/1?doc_id=109) | 全历史行情、未复权/qfq/hfq；qfq 按 `end_date` 动态复权 | `REJECTED_NO_PIT_PROOF` | 历史查询时间不是 T 日 known-at 证明；动态 qfq 不能替代 T 日 adjustment evidence |
| [Tushare `adj_factor`](https://tushare.pro/document/2?doc_id=28) | 股票历史复权因子 | `REJECTED_NO_PIT_PROOF` | 没有 T 日可核验的 factor vintage；不能独立证明历史复权因子在 T 已知 |
| [BaoStock historical K data](https://www.baostock.com/mainContent?file=stockKData.md) | 历史 K 线及不复权/前复权/后复权选项 | `REJECTED_NO_PIT_PROOF` | 当前查询结果没有可验证的 T 日快照/修订版本；且没有对应 sector rank/`sector_chg` PIT 来源 |

上述 `REJECTED_NO_PIT_PROOF` 是基于公开接口字段和本协议的推论：公开文档
列出了日期、历史记录或复权选项，但没有给出本项目所需的 immutable vintage、
原始响应归档或 `known_at` 证明。因此不能把这些字段人为填成
`known_at=T`。商业数据库即使可能提供 PIT 产品，也需要实际授权、产品版本和
可导出的 vintage 证据；本仓库当前没有这些条件，不能把“可能可用”当作已取得。

## 4. 阻塞项

### 4.1 正式 PIT sector evidence（硬阻塞）

没有可用来源同时提供同一 T 日的：

1. `symbol -> [sector_name, ...]` membership；
2. 覆盖同一板块集合的 rank；
3. 覆盖同一板块集合的 `sector_chg`；
4. 每一项的 source/version、`known_at<=T` 和原始内容哈希。

当前板块成员、板块排名或板块历史行情的任意组合都不能替代这四项。缺少
membership、rank 或 `sector_chg` 时，必须返回
`MISSING_POINT_IN_TIME_EVIDENCE`，而不是用当前板块或零值回填。

### 4.2 正式 PIT adjustment evidence（硬阻塞）

没有可用来源能够证明历史 qfq/adjusted bars 使用的是 T 日已知的 adjustment
factors 或公司行为快照。当前 Tencent qfq、AkShare qfq、Tushare qfq 和其他
provider 的当前复权结果均不能被改名为 `HISTORICAL_QFQ_AS_OF`。

在拿到独立 PIT adjustment evidence 前，只能选择已证明为 PIT 的
`UNADJUSTED_OHLCV_AS_OF`；本次没有这样的已归档数据。

### 4.3 PIT universe 与 OHLCV 的证据阻塞

有效日期字段（例如上市/退市日期、成分纳入/剔除日期）只能说明某个事件或
区间，不能自动说明 T 日当时可见的完整 universe snapshot。历史 OHLCV 端点的
当前返回值也没有提供本项目要求的 T 日 immutable vintage。故这两类数据也未
进入 acquisition。

## 5. Acquisition boundary

本次没有抓取、转换、补齐或冻结任何 validation data，避免产生带有伪造
`known_at`、当前 universe/sector 回填或 provider qfq 冒充历史复权的 artifact。

因此没有生成 frozen validation manifest：

```text
dataset_version: null
content_sha256: null
manifest_sha256: null
data_partition: validation (not created)
status: BLOCKED_NO_PIT_DATASET
```

机器可读审计记录见
`data/validation/phase2e_source_audit.json`。该文件是 blocker audit，不是
validation dataset，不应被 historical validation loader 读取。

## 6. 解阻条件

下一次 acquisition 必须先取得至少一种实际可用的 PIT source/export，并保留：

- provider/product/version 或 immutable vintage ID；
- T 日原始 payload、获取/归档时间和 SHA-256；
- universe 的完整 T 日成员快照；
- sector 的 T 日 membership、rank、`sector_chg` 三件套；
- raw OHLCV，或带独立 PIT adjustment evidence 的 historical adjusted/qfq bars；
- 每条记录或每个快照的 `known_at<=T` 证据。

在这些条件满足前，Phase 2E 停留在数据源审计/获取层；不运行策略、收益或
historical validation，也不创建 canonical watchlist、TOP N、portfolio 或
production 输出。
