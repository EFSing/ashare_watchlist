# CORE_SIGNAL_VALIDATION

本 artifact 是 PR #6 的 core-only historical replay。它不声称
`FULL_LEGACY_OUTPUT_VALIDATION` 或完整 legacy 85-score parity。

## 冻结边界

- 数据集：`core-signal-hithink-quarter-end-2023-06-to-2026-08-v1`
- T 日：2023-06-30 至 2026-08-28 的 14 个季度末/最新共同交易日
- universe：同花顺官方 daily-K 在 T 有 raw 行且截至 T 至少有 120 根历史 bar 的标的
- K：官方 unadjusted daily-K；价格字段按 `date < ex_date <= T` 的公司行为事件做
  deterministic T-anchor 仿射变换，成交量保持 raw
- benchmark：官方 `000001.SH` 历史 K
- sector：不加载历史新浪行业 membership；仅给 legacy evaluator 一个中性 sentinel，
  不把其结果写入 core projection；score/report 均为 `UNVERIFIED`

原始输入哈希、结果流哈希和 manifest 哈希见
[`core_signal_validation_manifest.json`](../data/validation/core_signal_validation/core_signal_validation_manifest.json)。
结果流只包含 A match、hard rejects、support、stop、target、RR、trigger 和 signal
identity 所需字段，不包含 score、return、win rate、MFE、MAE、P&L 或 expectancy。

## 工程验收结果

- 73,555 个候选评估；raw T-day universe 与结果流逐日 coverage 对账一致
- 0 duplicate key、0 null numeric field、0 negative volume row
- 两次独立全量 evaluator replay 的结果文件 SHA、canonical projection stream SHA、行数、
  status counts 和 source content hash 完全一致；另有固定 168 行 evaluator double-pass
  determinism witness 通过
- 所有 evaluator bars 截止 T；公司行为只使用 `ex_date <= T`；signal timing 为 T 收盘，
  earliest execution 为下一个 XSHG session T+1；没有 same-bar execution
- 已按 `2023_H2`、`2024`、`2025`、`2026_YTD` 汇总 signal count/frequency，并计算
  qualified symbol concentration / HHI

2024-09-30 的 A-match 与 qualified frequency 出现明显结构峰值，已作为结构观察项保留；
本阶段不将其解释为收益或预测有效性。

## 尚未解锁的边界

历史新浪行业 membership 仍缺失，因此 FULL layer 继续 blocked。官方 retrospective dump
也没有 per-bar historical vintage timestamp；该限制已写入 manifest，在任何收益 validation
前仍需单独确认 provenance 接受边界。当前 artifact 只证明 core signal/level replay 的工程
正确性，不自动解锁收益指标。
