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

## 当前 checkpoint

本轮在继续全量 replay 前已安全停止 A/B worker。两个中断流原样保留，但 gzip 尾部没有
结束标记，因此不把最后一个部分交易日算作完成。按原始 T-day universe 逐日候选数对账后：

- A：2023-06-30 至 2024-11-07 共 329 个完整交易日；2024-11-08 为部分日期，之后 38 个
  日期待处理
- B：2025-01-02 至 2026-03-23 共 293 个完整交易日；2026-03-24 为部分日期，之后 109 个
  日期待处理

每个分片都有详细的
[`core_signal_validation_resume_checkpoint.json`](../data/validation/core_signal_validation_continuous_parts/part_a/core_signal_validation_resume_checkpoint.json)
和完整日期 clean output；根索引为
[`core_signal_validation_resume_checkpoint.json`](../data/validation/core_signal_validation_continuous_parts/core_signal_validation_resume_checkpoint.json)。
中断 output 不覆盖、不作为完整 artifact 使用。resume 必须从部分日期本身开始，clean output
先与新 resume output 合并，不能重跑已完成日期。

完整连续 manifest 尚未生成；因此本文件不把连续 replay 宣称为完成，也不写入任何收益指标。
频率、年度/月度分布和 symbol concentration 只在所有日期完成且 manifest 构建后进行最终审计。

历史新浪行业 membership 仍缺失，因此 `FULL_LEGACY_OUTPUT_VALIDATION` 和 85-score
parity 继续 blocked。retrospective dump 没有 per-bar historical vintage timestamp；该
provenance 限制仍需在任何收益 validation 前单独确认。
