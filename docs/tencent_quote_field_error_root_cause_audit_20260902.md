# TENCENT_QUOTE_FIELD_ERROR_ROOT_CAUSE_AUDIT

更新时间：2026-09-02（Asia/Shanghai）

## Scope and classification

- task classification：`correctness blocker` + `product blocker`；本次是既定首个
  prospective input gate 的最小 root-cause audit，不启动新的 Phase，不进入 B
  evaluation、C、Final OOS、prospective returns、promotion、tuning 或 package
  generation。
- research decision：`NEEDS_MORE_EVIDENCE`。当前 evidence 不足以在 A、B、C 中
  选择一个；缺失的 evidence、可使用它的 gate 和未取得它时仍可继续的产品路径见下文。
- forbidden scope：未读取、修改或使用
  `data/validation/continuous_speed_probe/`。

## Historical attempt is immutable

第一次正式 `T=2026-09-02 LIVE_OBSERVED` attempt 的 immutable historical evidence
仍是 [`data/governance/prospective_input_attempt_evidence_20260902.json`](../data/governance/prospective_input_attempt_evidence_20260902.json)，由
`138b44dd3b3481b8c8a5ef648b10e67363178229` 保留。本审计没有改写该文件，也没有把
`FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_PROVIDER_FAILURE` 改写为成功或最终关闭。

现有 formal record 的 exact failure detail 是：

```text
Tencent quote acquisition failed: QuoteFieldError
```

历史执行输出的 diagnostics 也是空对象 `{}`；仓库、该 evidence、既有文档和可追溯
task output 中没有保存底层 `QuoteFieldError` message、失败 symbol、Tencent symbol、
field/index、raw Tencent line、请求 URL 或 50-symbol failure batch。因此下列字段均为
`UNRESOLVED`，不以值为 0 或异常类型猜测：

| item | result |
| --- | --- |
| exact six-digit symbol | `UNRESOLVED` |
| exact Tencent symbol | `UNRESOLVED` |
| exact failing field/index | `UNRESOLVED` |
| exact validation message | only the compressed class-level message above; underlying message `UNRESOLVED` |
| failure batch | `UNRESOLVED` |
| raw Tencent line | `NOT_RECORDED` |

## Local parser and consumer audit

当前 parser 的代码映射为：`price=p[3]`、`prev_close=p[4]`、`open=p[5]`、
`volume=p[6]`、`timestamp=p[30]`、`chg_pct=p[32]`、`high=p[33]`、`low=p[34]`、
`turnover=p[38]`、`vol_ratio=p[49]`。这些映射由仓库内 synthetic fixture regression
覆盖；这只能证明当前代码与 fixture 一致，不能证明它与第一次真实 Tencent raw
payload 一致。按用户边界，本轮不据此宣布 C。

`GenerationInputManifest` 的 quote gate 要求完整 symbol coverage 和每个 quote 的
T-date `quote_date`；其 quote record 会进入 quote content hash，但该 contract 层不
重新解释 Tencent 的每个 numeric field。corrected B 的 executable path 从 quote
record 实际读取的数值字段只有 `turnover`；price/OHLCV 和量比计算来自 stock Kline，
而 quote `quote_date`/coverage 是 manifest gate。该事实不等于允许缺失或无成交 quote
直接进入 B：在没有真实 raw 状态证明前，现有 parser 的字段规则继续保持 fail closed。

## Diagnostic probe decision

`CURRENT_ONLY_DIAGNOSTIC_NOT_PROSPECTIVE_EVIDENCE` 本轮 `NOT_RUN`。原因不是 provider
成功或失败，而是历史 evidence 没有保存可合法限定 probe 的失败 symbol 或原失败 batch；
请求任意猜测股票会超出“只请求失败 symbol/必要时原失败 batch”的范围，也不能回答第一次
attempt 的 A/B/C 根因。没有注册任何 current-only response 为 prospective input，没有
复用任何 payload，不运行 B，不生成 package。

所需的最小追加 evidence 是：失败六位代码及 Tencent prefixed symbol、原失败 batch、
对应 raw line、触发的 field/index 和完整 validator message。只有这些证据到位后，才可
判断：

- A：Tencent raw payload 能以 provider 明确的无成交/停牌状态解释，且 identity、日期和
  schema 有效；
- B：raw payload 是 malformed/inconsistent，不能由该状态解释；或
- C：真实 payload 与当前 `QUOTE_FIELD_INDEX` / parser assumption 不一致。

在上述 evidence 缺失期间，唯一可采取的代码动作是保留未来 failure diagnostics；不能
放宽 positive/OHLC/finite 规则、缩 universe、跳过股票、引入 fallback 或把失败标成合法
无成交 snapshot。

## Minimal diagnostic improvement

本地追加的 correctness/diagnostic fix 仅做两件事：

1. `fetch_quotes()` 对 `QuoteFieldError` 保留原 detail，并附加当前 six-digit
   `failure_batch` 与 Tencent-prefixed `tencent_batch`；
2. `live_acquisition.py` 不再把该异常压缩为 class name，而是将完整 detail 写入
   `LiveAcquisitionError` message 和 `diagnostics`（provider、stage、exception type、
   exception detail）。

没有修改 strategy、B、threshold、sector、universe、quote validation semantics、
provider selection 或 formal failed-attempt evidence。

## Current decision and stop

- root-cause classification：`UNRESOLVED`；A/B/C 均未被证据证明。
- research decision：`NEEDS_MORE_EVIDENCE`。
- operational blocker：仍为
  `FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_PROVIDER_FAILURE` 的历史 attempt 结果，
  但本次审计不把它当作最终关闭；当前产品状态仍不是 frozen candidate。
- next safe action：取得上述 exact failure evidence 后再做一次窄 probe/分类；在此之前
  不进行第二次正式 capture，不 push/PR 本地修复，不生成 partial package。
