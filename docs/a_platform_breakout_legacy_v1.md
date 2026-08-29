# Phase 2C：A Platform Breakout Legacy Baseline

本文件定义 `A_PLATFORM_BREAKOUT_LEGACY_V1`。该实现仅用于 research baseline / legacy parity，不是 production strategy，不代表参数已经验证有效，也不可直接用于交易。

V0 sector provenance 固定为 `get_sectors()` → AKShare
`stock_sector_spot()` / `stock_sector_detail()`，底层 taxonomy 为新浪行业。申万行业
或同花顺行业不构成 exact legacy sector，不能替代该 provenance。代码级定义见
`scripts/a_platform_breakout.py::LEGACY_SECTOR_PROVENANCE`。

## 输入与执行边界

唯一策略入口为 `scripts/a_platform_breakout.py` 的 `evaluate_candidate()` / `evaluate_universe()`，仅接受 Phase 2B 状态为 `READY_FOR_STRATEGY_EVALUATION` 的冻结 `GenerationInputManifest`。策略不联网、不读取 raw 当前行情、不做 historical replay、不读取 `perf_tracker`、不写 canonical watchlist，也不做 TOP N、score cutoff、portfolio selection 或 position sizing。

`signal_date=T`，`earliest_execution_date` 继续由 Phase 2B XSHG 日历定义为下一交易日 T+1。`trigger` 仅为 legacy planned trigger，不是 T 日成交价或 same-bar execution 价格。

每只股票必须有完整 Sector evidence：`sector_name`、`sector_rank`、`sector_chg`。缺少、不可解释或数值无效时返回 `INSUFFICIENT_DATA`；禁止恢复 V0 的 `rank=50`、`sector_chg=0` silent fallback。个股 K 线少于 120 根同样为 `INSUFFICIENT_DATA`。

## A 平台突破固定公式

令 `c`、`v`、`hi`、`lo` 分别为冻结个股 K 线的 close、volume、high、low 序列：

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
bp_price = prev60_hi_c
```

A 必须同时满足：

```text
plat_range <= 0.30
close > prev60_hi_c
vol_ratio_k >= 1.8
chg1 >= 3
close > ma20
```

`ud_ratio` 严格使用 `np.diff(c[-21:])` 对应 `v[-20:]`；上涨日均量除以下跌日均量；任一组为空或下跌日均量不大于 0 时固定 fallback 为 `1.0`。

## Legacy hard gates、support、target 与 RR

A matched 后，hard gates 按以下顺序执行：

```text
SECTOR_EVIDENCE_COMPLETE
CLOSE_GT_2
NO_ACCELERATION_OVEREXTENDED
NO_GAIN_EXHAUSTED
VALID_SUPPORT_EXISTS
RISK_IN_0_TO_9_PCT
RR_GE_2
OVERHANG_RR_COMBINATION_ACCEPTED
```

固定否决条件：

- `close <= 2`；
- `chg10 > 35 and bias20 > 15`；
- `pos250 > 0.9 and chg20 > 40`；
- 无有效 support；
- `risk <= 0` 或 `risk > 0.09`；
- `rr < 2`；
- `overhang > 0.5 and rr < 2.5`。

support candidates 固定为：`ma20`、`bp_price`、近 10 日最大成交量 K 线 low、`min(lo[-20:])`。仅保留 `< close` 的候选并取最大值。

```text
stop = round(support * 0.98, 2)
risk = (close - stop) / close
```

120 日 volume-price distribution 固定为：

```text
bins = np.linspace(min(lo[-120:]), max(hi[-120:]), 21)
indices = np.digitize(c[-120:], bins) - 1
indices = clip(indices, 0, 19)
20 bins
```

按 clipped bin index 累加 `v[-120:]`。上方 volume bin 的候选要求 bin price `> close * 1.03`；如成交量并列，按 ascending bin 顺序选择第一个。

三类 pressure candidate 为：

- `h60=max(hi[-60:])`，且 `h60 > close*1.03`；
- 上述最高成交量的上方 volume bin；
- `hhv120=max(hi[-120:])`，且 `hhv120 > close*1.03`。

存在候选时 `target=min(candidates)`，`target_type=PRESSURE`；无候选时：

```text
target = close * (1 + 2.5 * risk)
target_type = TREND_2_5R
```

```text
rr = (target - close) / (close - stop)
overhang = sum(vol_by_price[bins[:-1] > close*1.02]) / sum(vol_by_price)
trigger = round(max(bp_price, ma5), 2)
```

当总成交量为 0 时 `overhang=0.0`。

## 85 分 Legacy Score

仅通过全部 hard gates 的 candidate 计算完整八项 breakdown：

| 项目 | 固定规则 | 最大分 |
| --- | --- | ---: |
| `strong_sector` | rank≤10:10；rank≤20:6；否则2 | 10 |
| `relative_low` | pos250<0.35 且 chg10≤30:15；否则 pos250<0.5:10；否则 pos250<0.65:5；否则0 | 15 |
| `volume_price_health` | ud_ratio≥1.3:8；≥1.1:5；否则2；再按 1.5≤vol_ratio_k≤4 加4、>4 加2、否则加1；A setup 加3；封顶15 | 15 |
| `clear_support` | risk≤0.04:10；≤0.06:6；否则3 | 10 |
| `five_day_strength` | close>ma5 且 ma5≥mean(c[-6:-1]):5；仅 close>ma5:3；否则0 | 5 |
| `sector_linkage` | sector_chg≥1:10；>0:5；否则1 | 10 |
| `relative_strength` | rs=chg5-index_chg5；rs>3:10；>0:6；否则2 | 10 |
| `risk_reward` | rr≥3:10；rr≥2.5:8；否则5 | 10 |

总分为八项之和，最高 85。Phase 2C 不设置 score cutoff，也不进行排序发布或组合构建。

## Risk flags 与状态词汇

Risk flags 只记录，不增加 hard reject：

```text
quote.turnover > 10 -> HIGH_TURNOVER
overhang > 0.35 -> OVERHANG
chg20 > 30 -> TWENTY_DAY_GAIN
```

状态词汇固定为：

- `NOT_MATCHED`：A 五项未全部满足；
- `INSUFFICIENT_DATA`：覆盖、数值或 Sector evidence 不完整；
- `MATCHED_REJECTED`：A 已 matched，但 legacy hard gate 否决；
- `QUALIFIED_LEGACY_BASELINE`：A matched 且全部 legacy hard gates 通过。

## Phase 2C.1 semantic provenance

`LEGACY_SPEC` 是 canonical semantic config，而不是 Python source hash。它覆盖 minimum bars、全部 feature 窗口/fallback、A 五项精确比较符、全部 hard gates、support/stop/risk、120 日 volume distribution、target/RR/overhang/trigger、八项 85 分、三个 risk flags、Sector evidence hardening 以及 status vocabulary。因此源码注释、格式化或文档文字变化不会改变 spec hash；任何进入 canonical payload 的核心规则变化都会改变 hash。

当前固定：

```text
STRATEGY_SPEC_SHA256 = 7ce0bf660e3ae685405e01fb9d1ef8e27e7dec44a201ab290da5d8fa8079068d
```

该 SHA 写入每个 `CandidateEvaluation.provenance.spec_sha256`。`provenance` 不包含 `retrieved_at_bjt` 或运行时间；Phase 2B 的 content/input fingerprint 同样排除这些非语义时间戳，因此仅改变 retrieval/runtime metadata 不应改变 `evaluation_hash`。

`matched_conditions` / `failed_conditions` 按实际执行顺序记录。每个 hard gate 一旦通过就立即进入 `matched_conditions`，中途 reject 不会丢失此前已经通过的 gate；失败 gate 单独进入 `failed_conditions`。

## Differential parity witness

Phase 2C.1 新增独立 reference calculation 测试。reference 不调用 evaluator 内部 helper，直接按冻结 V0 公式对 synthetic inputs 计算 A match、support、stop、120 日 volume distribution、pressure/2.5R target、RR 以及完整 score breakdown，并覆盖 qualified、pressure target 和 RR reject。该测试只验证 legacy parity，不读取 forward return、胜率、MFE、MAE、P&L 或 `perf_tracker`，也不用于调参。

Sector differential witness 进一步固定了依赖边界：改变有效的
`sector_name` / `sector_rank` / `sector_chg` 只改变报告中的 sector 字段以及合格样本的
85 分 breakdown；A match、hard reject、support、stop、target、RR、trigger 和
qualified signal identity 必须保持不变。由于 sector provenance 缺失，未来历史验证
分为两层：`CORE_SIGNAL_VALIDATION` 可将 sector score/report 标为 `UNVERIFIED`，不
宣称 full legacy output parity；`FULL_LEGACY_OUTPUT_VALIDATION` 必须取得历史新浪行业
membership，并用于完整 85 分 parity。两层 contract 见
`scripts/historical_validation_layers.py`。

## 明确不代表什么

本阶段不表示 A 的阈值已经优化或验证有效，不表示 85 分具有预测有效性，不表示 target/stop 已经经过收益验证，也不表示 production rule 已冻结。B/C/D、scheduler、historical replay、canonical watchlist、TOP N、score cutoff、portfolio/position sizing 和 production promotion 均未进入 Phase 2C/2C.1。

Phase 2D 的 point-in-time universe/sector/adjustment source、frozen validation dataset、promotion gate 和 replay protocol 仍需后续独立设计；Phase 2C.1 不启动 Phase 2D。
