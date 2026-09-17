# HITHINK QUOTE PRIMARY 决策点审计 — 2026-09-17

> `CURRENT_ONLY_DIAGNOSTIC_NOT_PROSPECTIVE_EVIDENCE`

## 任务与分类

- 任务：`HITHINK_QUOTE_PRIMARY_REMOVE_TENCENT_QUOTE_BLOCKER_V1`；classification =
  `correctness blocker`，STRICT PATH，NO STRATEGY CHANGE。
- 目标：把 production T-close quote snapshot 从 Tencent 改为 HiThink Financial-API，使
  Tencent quote production calls=`0`，同时保持 Tencent historical Kline fallback 原样。
- 本轮结果：实现前停在真实 decision node，未修改任何 production 行为，未创建 migration PR。
  terminal=`HITHINK_QUOTE_FORMAL_B_DEPENDENCY_DECISION_REQUIRED`，同时触发
  `HITHINK_QUOTE_TRADE_STATE_DECISION_REQUIRED` 与
  `HITHINK_QUOTE_SCHEMA_CONTRACT_DECISION_REQUIRED`。
- 本文件是只读诊断证据，不是 formal 输入/输出，不构成 provider policy 变更，也不是 Final OOS 结论。

## Live intake（实时读取）

| 项 | live 值 |
| --- | --- |
| `origin/master` | `9528484887abe724bad555f9475f2cf2fb98b144`（`fix: remove AkShare from production critical path (#70)`） |
| PR #70 | merged（2026-09-17 10:41:46 UTC；merge commit 与 `origin/master` 相同） |
| `origin/runtime-state` | `be8236629684b34dab5672df774918273536a5d9` |
| open PR | #60 / #66 / #67 / #68（本任务 untouched） |
| master correctness CI | run `35211820931` success |
| 最新 `daily-t-close` | run `35212735555`（`workflow_dispatch`，`master@9528484`）failure |

`PROJECT_GOVERNANCE_STATE_CONFLICT`：`HANDOFF.md` / `docs/CURRENT_STATUS.md` 顶层仍把 #70 记为
Draft，live GitHub 已 merged。已按最小 reconciliation 记录本次 live 事实；历史段落不改写。

## 失败点确认

run `35212735555` step 13 `Run genuine XSHG T-close production chain` 失败，错误原文：

```text
PROVIDER_FAILURE: Tencent quote acquisition failed: 001246: empty Tencent field p[38] (turnover)
```

同 run 已核对：step 10 cloud preflight success、step 8 runtime-state restore/validate success、
universe 阶段未报错、失败发生在 quote 阶段、尚未进入 stock Kline 评估。
本机只读复现（`qt.gtimg.cn/q=sz001246`）：88 字段，`p[3]/p[4]/p[5]/p[6]` 全 `0.00/0`，
`p[38]` 空串、`p[44]` 空串 → 与 parser 报错一致。

## HiThink snapshot 实测 schema（只读 probe）

endpoint：`/api/a-share/prices/snapshot`。

| 项 | 实测结果 |
| --- | --- |
| 参数 | 单数 `thscode=` 被忽略（返回全市场 5574 行）；复数 `thscodes=a,b` 生效；`limit`/`offset` 生效 |
| item 字段 | `thscode, ticker, volume, turnover, last_price, price_change, price_change_ratio_pct, open_price, high_price, low_price, prev_price` |
| 日期语义 | 无任何 per-record 交易日字段；`data.timestamp` 为响应时刻（实测与请求时刻一致），不能作为 trade date |
| `turnover` 语义 | 成交额，不是换手率（000001.SZ：`turnover=806,153,130` ÷ `volume=69,192,535` ≈ 11.65 ≈ `last_price`） |
| 无成交形态 | 未交易标的整行 null（001246.SZ：volume/last_price/open/high/low/prev_price 全 null） |
| name | snapshot 不含 name；只能来自 universe ticker list |

Tencent 对照（本机只读）：`sz000001` `p[38]=0.36`（换手率 %）、`p[37]=80615`（成交额，万元）、
`p[49]=0.83`（量比）。即 **Tencent `p[38]`（换手率）与 HiThink `turnover`（成交额）语义不同，
不可互换**。

## downstream quote contract（Formal B / trade proof 实测）

- Formal B `B_BREAKOUT_RETEST_LEGACY_V1_1` 的 executable path 经共享 evaluator 读取
  `quote["turnover"]`；缺该字段即 `INSUFFICIENT_DATA`。用现有 evaluator 实测（无 provider 调用）：

  ```text
  quote 带 turnover=11.0 → QUALIFIED_LEGACY_BASELINE（risk_flags=HIGH_TURNOVER）
  quote 无 turnover      → INSUFFICIENT_DATA failed=(NUMERIC_INPUT_COMPLETE,)
  ```

  因此把 quote core 的 `turnover` 去掉会改变 canonical watchlist 候选成员资格。
- watchlist 候选 `turnover` 字段（runtime-state `watchlist_20260916.json`：0.51–4.27）同样来自
  quote `turnover`，量级即换手率。
- quote `vol_ratio` 不是 strategy-required：watchlist `vol_ratio` 来自 kline `vol_ratio_k`，quote
  `vol_ratio` 只参与 `is_no_trade_snapshot`。
- `is_no_trade_snapshot` 要求完整显式零形态（`price==prev_close>0`、`open/high/low/chg_pct=0`、
  `volume/turnover/vol_ratio=0`）。HiThink 的全 null 行不等价；把全 null 当 NO_TRADE 属
  "missing → NO_TRADE"，现有 policy 不允许。
- `QuoteSnapshotManifest` 要求 per-symbol `quote_date == as_of_date`；HiThink 无 provider 侧
  日期，只能由 target date 赋值，失去 provider 侧 T 日证明。
- TRADED 证明（price/prev_close/open/high/low>0、volume>0、OHLC 一致）用 HiThink traded 行可以
  复现：001248.SZ `last_price=11.61`、`prev_price=11.77`、`volume=32,805,681`，与同日 HiThink
  historical bar（close 11.61 / volume 32,805,681）一致。

## 2026-09-17 的真实 root cause

`001246.SZ = 力勤资源`：

- HiThink ticker list：`list_date=null`、`end_date=null`、`last_trade_date=null`
- HiThink historical（2026-01-01 → 2026-09-18）：**0 根 bar**
- HiThink snapshot：整行 null
- Tencent：`p[3]=0.00`、`p[4]=0.00`、`p[38]` 空串

即该标的为**未上市/从未交易（pre-listing）**，不是停牌。live ticker list 中 `list_date` 为空的
共 9 行（4 只 301xxx ChiNext、4 只 920xxx BJ、1 只主板），其中 **SH/SZ 主板仅 `001246.SZ`**，
正好是本次生产失败的 symbol。

#70 把 acquisition universe 改为 `HiThink ticker list ∩ ASHARE_MAIN_BOARD_ONLY_V1`，移除了
2026-09-02 由用户批准（`USE_EXCHANGE_OFFICIAL_LISTED_ROSTER_VIA_EXISTING_AKSHARE`）的官方
listed roster 交集；provenance 中的 `universe_listing_eligibility` 现在是硬编码 `"PASS"`。
因此 pre-listing 标的进入 universe，并在 quote 阶段阻断整单。

## 为什么迁移 provider 不能单独解决 2026-09-17

即使 quote provider 迁移完成：

- 001246 的 HiThink snapshot 全 null → 现有 policy 判 `UNKNOWN` → fail-closed；
- 001246 的 HiThink historical 为空 → `HiThink historical bars are empty`（非 transient）→
  `PROVIDER_FAILURE`，不会进入 Tencent Kline fallback；即使 NO_TRADE 语义被放宽，
  `MIN_STOCK_BARS_FOR_GENERATION_INPUT=1` 的空历史仍 fail-closed。

结论：该目标日期要恢复，必须先决定"未上市标的如何处理"（universe 资格 / 显式隔离 / 其他），
而不是仅迁移 quote provider。

## Decision nodes（等待用户决定）

1. universe listing eligibility：采用 HiThink `list_date`（`list_date <= T`）作为上市资格字段 /
   恢复官方 listed roster 交集 / 保持现状。
2. quote `turnover`（Formal B dependency）：保留 Tencent 提供换手率 / 授权寻找 HiThink 换手率
   口径 / 授权修改冻结输入契约 / DEFER。
3. NO_TRADE 证据：是否授权"provider 返回该 symbol 行 + 交易字段全 null"作为无成交证据。
4. target-day 证据：是否接受"采集时刻晚于收盘"作为 T 日证明，或要求与同 provider T 日
   historical bar 交叉校验。

## 边界与调用计数

- provider 只读 probe calls：HiThink 15 次、Tencent 2 次；未持久化 raw 到 runtime-state、
  未输出 secret、未做全市场批量扫描（全市场 payload 是端点忽略单数参数时的默认返回）。
- production dispatch=`0`；runtime-state remote mutation=`0`；Cloudflare mutation=`0`。
- Formal B spec SHA=`f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd`（未修改）；
  Tencent historical Kline fallback 未修改；volume observation 定义未修改；AkShare roster
  production calls=`0`。
- Final OOS=`SEALED / UNREAD`；`data/validation/continuous_speed_probe/` 未读取或触碰。
