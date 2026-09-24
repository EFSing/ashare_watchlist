# C_RAW_T_ANCHOR_LIMITED_EXPLORATION_V1 — 证据受限历史探索报告

- 研究身份：`C_RAW_T_ANCHOR_LIMITED_EXPLORATION_V1` / 输入身份 `RAW_DAILY_K_DECLARED_T_ANCHOR_V1`
- 样本身份：`MAIN_BOARD_ST_UNVERIFIED_CANDIDATE_SAMPLE`（**不是** formal C universe）
- **不是** `C_QFQ_INPUT_V1` 结果；#87 的原始阻断结论保持有效，未被重新解释
- 最终状态：`C_RAW_T_ANCHOR_EXPLORATION_COMPLETED`
- 日历：769 个 XSHG session (2023-06-30 – 2026-08-28)
- Formal B 变更：`False`；runtime-state 变更：`False`；provider calls：`0`；Final OOS：`SEALED / UNREAD`

## 1. 输入身份与转换规则核验

| 输入 | 字节 | SHA-256 | 状态 |
| --- | ---: | --- | --- |
| `data/validation/core_signal_validation/raw/daily_k.parquet` | 180203424 | `61189a4850e2eb157453e28e5375e502e20d214508bbe70ea71066ca3e05e426` | `HASH_VERIFIED` |
| `data/validation/core_signal_validation/raw/adjustment_factors.parquet` | 295284 | `a1b7d63c5826ccd3610dc9bdd949d82eeb0ba84ffad451bfb8bb30ca74962716` | `HASH_VERIFIED` |
| `data/validation/core_signal_validation_continuous_parts/core_signal_validation_manifest.json` | 540863 | `008643a64e0070433f3d63dca8243f8dad294b049a7accb5d49af3597aae17b0 (LF-normalised)` | `HASH_VERIFIED` |

声明公式：`(price - dividend_per_share + allotment_price*allotment_ratio)/(1 + per_share_bonus + allotment_ratio)`；事件过滤：`date < ex_date <= T`；顺序：`ascending ex_date`；volume：`raw unadjusted volume`。

除权日连续性核验：观察 `34501` 个 ex-date；平均绝对跳变 raw `6.26%` → T-anchor `2.01%`；|跳变|≥2% 的 ex-date 数 raw `19389` → T-anchor `12353`；最大 raw 跳变 `-76.67%`，最大 T-anchor 重建跳变 `57.87%`。

前缀不变性：`PASS`，比较跨度 [120, 250, 500]，检查 400 个 (symbol, T)，不一致 0。
全历史对照探针：400 次中 2 次因重建价格非正被冻结纯函数判为非法输入。

预筛超集验证：`PASS`，检查 2000 个被预筛拒绝的 (symbol, T)，假阴性 0。

## 2. 事件数量与样本

| rule | 原始事件 | 去重 episode | 涉及股票 | 单股票最大事件 | 同一 episode 多次确认 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `BALANCED_A` | 4130 | 2453 | 1479 | 16 | 1074 |
| `CONSERVATIVE_B` | 246 | 127 | 110 | 7 | 61 |

枚举口径：`entry_candidate=True`，universe 为沪深 00/60 主板、ST 状态未核验；预筛只是必要条件的加速，已验证为超集。

## 3. T+3 / T+5 / T+10 观察统计

### BALANCED_A

| 窗口 | 事件 | 可计算 | 缺失 session | 正收益比例 | 平均 | 中位 | T+1 开盘参考正比例 | 参考平均 | MFE 均值 | MAE 均值 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| T+3 | 4130 | 4112 | 6 | 44.99% (1850/4112) | 0.0009 | -0.0037 | 44.50% (1830/4112) | -0.0012 | 0.0411 | -0.0356 |
| T+5 | 4130 | 4109 | 7 | 44.07% (1811/4109) | 0.0001 | -0.0064 | 43.30% (1779/4109) | -0.0020 | 0.0543 | -0.0455 |
| T+10 | 4130 | 4094 | 6 | 45.80% (1875/4094) | 0.0002 | -0.0070 | 45.04% (1844/4094) | -0.0018 | 0.0782 | -0.0628 |

episode 去重后的正收益比例（T+3 / T+5 / T+10）：46.01% (1123/2441) / 45.82% (1118/2440) / 47.74% (1161/2432)。

成本边界：`NOT_CALCULABLE_COST_MODEL_NOT_PREEXISTING`；实际成交胜率：`NOT_AVAILABLE_NO_ACTUAL_FILL_EVIDENCE`。

按年事件数：2023 286，2024 1261，2025 2103，2026 480。

按年正收益观察比例（T+3 / T+5 / T+10，分子/分母）：

| 年份 | T+3 | T+5 | T+10 |
| --- | --- | --- | --- |
| 2023 | 36.01% (103/286) | 33.57% (96/286) | 34.97% (100/286) |
| 2024 | 45.32% (571/1260) | 45.48% (573/1260) | 48.85% (616/1261) |
| 2025 | 47.55% (998/2099) | 46.49% (975/2097) | 47.07% (987/2097) |
| 2026 | 38.12% (178/467) | 35.84% (167/466) | 38.22% (172/450) |

量能描述（`DESCRIPTIVE_ONLY_VOLUME_BASIS_UNVERIFIED`，仅描述、不作 gate）：T 日 RV 有效 4130，中位 1.5025，均值 2.0739。
事件最多的月份：2025-08 538，2024-12 404，2025-07 389，2025-06 334，2025-09 215。

### CONSERVATIVE_B

| 窗口 | 事件 | 可计算 | 缺失 session | 正收益比例 | 平均 | 中位 | T+1 开盘参考正比例 | 参考平均 | MFE 均值 | MAE 均值 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| T+3 | 246 | 246 | 0 | 47.97% (118/246) | -0.0027 | -0.0009 | 46.75% (115/246) | -0.0036 | 0.0329 | -0.0333 |
| T+5 | 246 | 246 | 0 | 43.09% (106/246) | -0.0088 | -0.0051 | 43.09% (106/246) | -0.0097 | 0.0420 | -0.0455 |
| T+10 | 246 | 246 | 0 | 41.06% (101/246) | -0.0068 | -0.0120 | 39.84% (98/246) | -0.0077 | 0.0653 | -0.0637 |

episode 去重后的正收益比例（T+3 / T+5 / T+10）：45.67% (58/127) / 42.52% (54/127) / 41.73% (53/127)。

成本边界：`NOT_CALCULABLE_COST_MODEL_NOT_PREEXISTING`；实际成交胜率：`NOT_AVAILABLE_NO_ACTUAL_FILL_EVIDENCE`。

按年事件数：2023 9，2024 72，2025 156，2026 9。

按年正收益观察比例（T+3 / T+5 / T+10，分子/分母）：

| 年份 | T+3 | T+5 | T+10 |
| --- | --- | --- | --- |
| 2023 | 66.67% (6/9) | 22.22% (2/9) | 44.44% (4/9) |
| 2024 | 44.44% (32/72) | 45.83% (33/72) | 26.39% (19/72) |
| 2025 | 49.36% (77/156) | 43.59% (68/156) | 46.79% (73/156) |
| 2026 | 33.33% (3/9) | 33.33% (3/9) | 55.56% (5/9) |

量能描述（`DESCRIPTIVE_ONLY_VOLUME_BASIS_UNVERIFIED`，仅描述、不作 gate）：T 日 RV 有效 246，中位 1.3323，均值 2.0381。
事件最多的月份：2025-07 35，2024-12 31，2025-08 30，2025-06 26，2025-09 15。

## 4. 不能计算的项目与证据缺口

| 缺口 | 状态 |
| --- | --- |
| `historical_t_known_st` | UNRESOLVED; sample is ST_STATUS_UNVERIFIED and is not the formal C universe |
| `per_bar_known_at_or_vintage` | MISSING; T-anchor reconstruction stays PARTIAL_UNVERIFIED |
| `c_qfq_input` | NOT_APPLICABLE; this exploration is not C_QFQ_INPUT_V1 |
| `execution_and_fill` | UNAVAILABLE; T+1 open is a reference price only |
| `transaction_cost_model` | NOT_CALCULABLE_COST_MODEL_NOT_PREEXISTING |
| `volume_basis` | VOLUME_BASIS_UNVERIFIED; descriptive only, never a gate |
| `intraday_limit_or_break_sequence` | UNAVAILABLE; daily OHLCV cannot establish intraday order |

## 5. 诊断计数

- `entry_candidates_BALANCED_A` = 4130
- `entry_candidates_CONSERVATIVE_B` = 246
- `main_board_symbols` = 3193
- `prefilter_passed_BALANCED_A` = 70413
- `prefilter_passed_CONSERVATIVE_B` = 5359
- `prefilter_rejected_BALANCED_A` = 2330121
- `prefilter_rejected_CONSERVATIVE_B` = 2395175
- `rule_bar_candidates_BALANCED_A` = 2400534
- `rule_bar_candidates_CONSERVATIVE_B` = 2400534
- `rule_rejected_BALANCED_A` = 66283
- `rule_rejected_CONSERVATIVE_B` = 5113
- `symbols_below_min_bars` = 13

## 6. 判读边界

- 这些正收益比例是**观察统计**，不是策略胜率、不是 OOS 证据、不是可执行收益。
- 样本未核验历史 ST/*ST，因此**不满足** formal `C_MAIN_BOARD_NON_ST_V1` 的 PIT 有效样本条件。
- T-anchor 重建缺逐 bar vintage 证明，状态保持 `PARTIAL_UNVERIFIED`。
- 量能语义未核验，仅作描述，不构成确认。
- 本报告不得被引用为 `C_QFQ_INPUT_V1` 的正式回测结论，也不改变 #87 的原始阻断结论。
