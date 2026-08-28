# CORE_SIGNAL_VALIDATION continuous replay

本 artifact 是在既有 14 日 core-only replay 上的连续交易日扩展。既有 14 日并非
随机日期：它们是 2023-06-30 至 2026-08-28 这一已冻结 validation partition 中的
季度末共同交易日，再加上数据截止日前最后一个共同交易日，用于低成本覆盖长期阶段、
复核季度边界和保留原有 hash baseline。连续扩展保留相同首尾日期，只把日期集合替换为
区间内全部 XSHG session；不读取或改变 final OOS。

## 冻结边界

- 769 个连续 XSHG session：2023-06-30 至 2026-08-28
- 同一 `A_PLATFORM_BREAKOUT_LEGACY_V1` evaluator、阈值、原始 K、T-anchor 复权和 T+1 timing
- universe 仍为官方 daily-K 在 T 有 raw 行且截至 T 至少有 120 根历史 bar 的标的
- 不加载历史新浪行业 membership；sector score/report 保持 `UNVERIFIED`
- 结果 projection 只包含 core signal/level 字段，不含 85-score 或任何收益指标

## 完成状态

已按原 checkpoint 从 `2024-11-08` 和 `2026-03-24` 继续，未重跑此前完成的 622 日。
A/B 新增 147 日后共完成 769 个连续 XSHG session、4,041,140 个 candidate evaluations：

- A：2023-06-30 至 2024-12-31，共 367 日、1,886,529 个 candidates
- B：2025-01-02 至 2026-08-28，共 402 日、2,154,611 个 candidates

每个分片都有详细的
[`core_signal_validation_resume_checkpoint.json`](../data/validation/core_signal_validation_continuous_parts/part_a/core_signal_validation_resume_checkpoint.json)
和完整日期 final output；根索引为
[`core_signal_validation_resume_checkpoint.json`](../data/validation/core_signal_validation_continuous_parts/core_signal_validation_resume_checkpoint.json)。
原始 interrupted output 仍保留为 resume evidence，未被覆盖；final output 是旧 clean output
与本次 resume output 的按日期拼接。

完整 continuous manifest 已生成：
[`core_signal_validation_manifest.json`](../data/validation/core_signal_validation_continuous_parts/core_signal_validation_manifest.json)。
core projection SHA 为 `882b8925e787d67d7035de07f91cd3c941b7394661bd32d5d534cc62e3996c1b`。

随后已按显式授权完成独立 DEVELOPMENT historical returns validation：
[`development_historical_returns_manifest.json`](../data/validation/core_signal_validation_continuous_parts/development_returns/development_historical_returns_manifest.json)。
它使用 T+1 XSHG open、raw unadjusted OHLC，输出 1D/3D/5D/10D return、positive rate、
MFE/MAE、expectancy、年/月分层和 frequency/concentration；结果标记
`RECONSTRUCTED_RETROSPECTIVE`，不写回 core projection。

历史新浪行业 membership 仍缺失，因此 `FULL_LEGACY_OUTPUT_VALIDATION` 和 85-score
parity 继续 blocked。retrospective dump 没有 per-bar historical vintage timestamp；该
provenance 限制仍需在任何收益 validation 前单独确认。
