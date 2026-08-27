# Phase 2C：A Platform Breakout Legacy Baseline

本文件定义 `A_PLATFORM_BREAKOUT_LEGACY_V1` 的 research baseline evaluator。
它是从 V0 固定脚本恢复的可审计、确定性基线，不是已验证的 production
strategy。

## 范围与输入边界

唯一入口是 `scripts/a_platform_breakout.py` 的
`evaluate_candidate()` / `evaluate_universe()`。入口只接受 Phase 2B
`GenerationInputManifest`，且要求：

```text
status == READY_FOR_STRATEGY_EVALUATION
```

策略只读取冻结 manifest 中的个股 K 线、指数 K 线、quote turnover 和
Sector evidence；不联网、不读取 raw 当前数据、不做 historical replay、不
读取 `perf_tracker`，也不写入 canonical watchlist。

Phase 2B 的 `signal_date` 是 T，`earliest_execution_date` 是 XSHG 日历的下
一个交易日 T+1。`trigger` 是 legacy planned trigger，不是 T 日成交价，
也不是 same-bar execution 价格。

每个股票的 `SectorManifest.rank_input`（或 `members`）必须能够通过股票代码
解释出以下完整记录：

```json
{
  "600000": {
    "sector_name": "银行",
    "sector_rank": 5,
    "sector_chg": 1.5
  }
}
```

缺少任一字段、字段不可解释或数值无效时，结果为
`INSUFFICIENT_DATA`。不会恢复 V0 在板块失败时偷偷使用 `rank=50`、
`sector_chg=0` 的 silent fallback。

个股 K 线少于 120 根时为 `INSUFFICIENT_DATA`。K 线日期、T、T+1 和复权/来源
语义由 Phase 2B 合同负责；本策略不重新定义日期或日历。

## A 平台突破公式

令 `c`、`v`、`hi`、`lo` 分别为 manifest 中按日期排序的 close、volume、high、
low 序列：

```text
close = c[-1]
ma5 = mean(c[-5:])
ma20 = mean(c[-20:])
vma20_prev = mean(v[-21:-1])
vol_ratio_k = v[-1] / vma20_prev if vma20_prev > 0 else 0

chg1 = (c[-1] / c[-2] - 1) * 100
chg5 = (c[-1] / c[-6] - 1) * 100
chg10 = (c[-1] / c[-11] - 1) * 100
chg20 = (c[-1] / c[-21] - 1) * 100
bias20 = (close / ma20 - 1) * 100

llv250 = min(lo[-250:])
hhv250 = max(hi[-250:])
pos250 = (close - llv250) / (hhv250 - llv250) if hhv250 > llv250 else 0.5

prev60_hi_c = max(c[-61:-1])
prev60_lo = min(lo[-61:-1])
plat_range = (max(hi[-61:-1]) - prev60_lo) / prev60_lo
```

A 只在以下条件全部满足时 matched：

```text
plat_range <= 0.30
close > prev60_hi_c
vol_ratio_k >= 1.8
chg1 >= 3
close > ma20
```

`bp_price = prev60_hi_c`。量价健康仍使用旧口径：`np.diff(c[-21:])` 对应
`v[-20:]`，上涨日均量除以下跌日均量；任一组为空或下跌日均量不大于零时
`ud_ratio = 1.0`。

## Legacy hard rejects 与价位

匹配 A 后，以下规则和阈值原样保留：

- `close <= 2` → `REJECTED_CLOSE_TOO_LOW`；
- `chg10 > 35 and bias20 > 15` → `ACCELERATION_OVEREXTENDED`；
- `pos250 > 0.9 and chg20 > 40` → `GAIN_EXHAUSTED`；
- 支撑候选为 `ma20`、`bp_price`、近十日最大量 K 线 low、`min(lo[-20:])`，
  只保留小于 close 的值并取最大者；没有候选 → `REJECTED_NO_SUPPORT`；
- `stop = round(support * 0.98, 2)`，`risk = (close - stop) / close`；
  `risk <= 0` 或 `risk > 0.09` → `REJECTED_STOP_DISTANCE`；
- 120 日价格成交量分布使用
  `bins = np.linspace(min(lo[-120:]), max(hi[-120:]), 21)`，20 个 bin，
  按 `np.digitize(c[-120:], bins)` 累加 volume；
- `h60`、上方 volume bin、`hhv120` 中的有效压力候选取最小值，
  `target_type = PRESSURE`；没有候选时使用
  `target = close * (1 + 2.5 * risk)`，`target_type = TREND_2_5R`；
- `rr = (target - close) / (close - stop)`，`rr < 2` → `REJECTED_RR`；
- `overhang > 0.5 and rr < 2.5` → `REJECTED_OVERHANG_RR`；
- `trigger = round(max(bp_price, ma5), 2)`。

上述风险否决只属于 legacy baseline；它们不代表生产规则已经冻结。

## 85 分 breakdown

只有通过全部 hard conditions 的 A candidate 才计算分数。输出始终保存完整的
`ScoreBreakdown`，不会只保留 total：

| English field | 旧规则 | 最大分 |
| --- | --- | ---: |
| `strong_sector` | rank ≤10: 10；≤20: 6；否则 2 | 10 |
| `relative_low` | pos250 <.35 且 chg10 ≤30: 15；否则 pos250 <.5: 10；否则 pos250 <.65: 5；否则 0 | 15 |
| `volume_price_health` | ud_ratio 按 1.3/1.1 分档，加 volume ratio 1.5..4/>4 分档，再加 A setup 3，封顶 15 | 15 |
| `clear_support` | risk ≤.04: 10；≤.06: 6；否则 3 | 10 |
| `five_day_strength` | close>ma5 且 ma5≥前五日均值: 5；仅 close>ma5: 3；否则 0 | 5 |
| `sector_linkage` | sector_chg ≥1: 10；>0: 5；否则 1 | 10 |
| `relative_strength` | `rs=chg5-index_chg5`，rs>3: 10；>0: 6；否则 2 | 10 |
| `risk_reward` | rr≥3: 10；≥2.5: 8；否则 5 | 10 |

八项之和为 `score_total`，没有 score cutoff、TOP N、排序发布、组合选择或
仓位分配。

## 输出、状态与 provenance

输出模型为 `FeatureSnapshot`、`LevelPlan`、`ScoreBreakdown` 和
`CandidateEvaluation`。`CandidateEvaluation` 至少保存：策略版本、input
fingerprint、T/T+1 元数据、symbol/setup/status、完整 features、匹配/失败
条件、reject reasons、support/trigger/stop/target、risk/rr、完整 score
breakdown、score total 和 risk flags。

状态含义：

- `NOT_MATCHED`：A 五项条件未全部满足；
- `INSUFFICIENT_DATA`：覆盖、数值或 Sector evidence 不足；
- `MATCHED_REJECTED`：A 已匹配，但触发 legacy hard reject；
- `QUALIFIED_LEGACY_BASELINE`：通过 legacy hard conditions，可计算 85 分。

风险标记只记录、不新增 hard reject：quote turnover `>10` →
`HIGH_TURNOVER`，overhang `>0.35` → `OVERHANG`，chg20 `>30` →
`TWENTY_DAY_GAIN`。

`STRATEGY_SPEC_SHA256` 是固定规则 spec/config 的 deterministic SHA-256，写入
每个结果的 `provenance.spec_sha256`。provenance 同时写入 strategy version、
input fingerprint、T、signal date、T+1、calendar、timezone 和 adjustment
mode，但不写入 `retrieved_at_bjt` 或运行时间。`evaluation_hash` 由完整语义
结果计算，因此同一 `GenerationInputManifest + strategy_version` 必须产生
相同 evaluation hash；任何输入 fingerprint 变化都会反映到 provenance 和
evaluation hash。

## 明确不代表什么

Phase 2C 不表示：

- A 的 30%、1.8、3%、9%、RR 等参数已被优化或验证有效；
- 正式 production rule 已冻结；
- 85 分具有预测有效性；
- target/stop 经过历史收益、MFE/MAE 或 performance tracker 验证；
- 结果可以直接交易；
- B/C/D、scheduler、historical replay 或 canonical watchlist 已恢复。

Phase 2D 仍需单独决定：是否需要 point-in-time universe/sector/adjustment
source、production promotion gate、正式输出契约和后续验证设计。本阶段不替
这些未知决策做选择。

## Legacy 与 hardening 的差异

以下内容保持 V0 legacy baseline 的公式和阈值：A 的五个 matched 条件、
`close <= 2`、连续加速/高位透支否决、四类支撑候选、止损与 9% 风险上限、
120 日成交量价格分布、压力/2.5R target、RR/overhang 组合否决、trigger、
八项 85 分评分和三个风险标记。Phase 2C 没有用收益、胜率、P&L、MFE/MAE
或 `perf_tracker` 选择或修改这些参数。

以下内容是 Phase 2C 的审计 hardening，不是策略阈值变化：

- 输入必须来自 Phase 2B READY manifest，禁止联网、raw 当前数据和 replay；
- Sector 必须提供逐股票的 `sector_name`、`sector_rank`、`sector_chg`，缺失即
  `INSUFFICIENT_DATA`，不使用 rank=50/chg=0 fallback；
- 每只股票都保留 matched/failed/reject 路径、完整 features 和 score breakdown；
- 规则 spec、输入 fingerprint、T/T+1 和来源/复权身份进入 deterministic
  provenance，并计算 `evaluation_hash`；
- batch 只返回逐股审计结果，不做 TOP N、score cutoff、组合/仓位选择或
  canonical watchlist publish。
