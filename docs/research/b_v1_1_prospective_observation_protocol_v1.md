# B V1_1 Prospective Observation Protocol V1

状态：`DEVELOPMENT` / `PROSPECTIVE_OBSERVATION` / `DATE_ANCHORED` / `APPEND_ONLY`

本协议只建立一次性的、未来日期锚定的 B 观察机制。它不是 B V2、turnover V2、
Volume-Path V2、promotion、freeze、Final OOS，也不是对 retrospective B returns
的再次证明。

## 1. 固定 identity 与 pre-outcome gate

- protocol：`B_V1_1_PROSPECTIVE_OBSERVATION_PROTOCOL_V1`
- strategy：`B_BREAKOUT_RETEST_LEGACY_V1_1`
- strategy spec SHA-256：
  `f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd`
- `score_cutoff=None`、`top_n=None`；B evaluator、threshold、universe、support、
  stop、target、RR、overhang、score 和 prospective generation path 不变。
- labels：`DEVELOPMENT`、`PROSPECTIVE_OBSERVATION`、`DATE_ANCHORED`、
  `APPEND_ONLY`、`NO_RULE_CHANGE`、`NOT_FROZEN`、`NOT_PRODUCTION`、
  `FINAL_OOS_UNREAD`。
- pre-outcome protocol commit：
  `B_V1_1_PROSPECTIVE_PRE_OUTCOME_PROTOCOL_COMMIT=PENDING_PRE_OUTCOME_PROTOCOL_COMMIT`

未来任何 outcome 读取前，必须先把本协议与 observation semantics 提交，并将上面的
placeholder 替换为该 protocol commit 的完整 SHA。observer 会拒绝未绑定该 commit
或其后代生成 commit 的 source。

## 2. Cohort 与 signal semantics

Primary cohort 的起点是 protocol commit 之后真实生成的第一个 XSHG T-close B signal
date。2026-09-03 或 protocol commit 以前已生成的 watchlist 可以保留为 prior
operational evidence，但不进入 primary cohort；observer 不提供历史回填入口。

信号严格使用现有 canonical B V1_1 qualification，全部已发布的 qualified candidates
都进入记录，不增加 turnover、RV、score、Top-N、industry、momentum、liquidity 或
manual preferred subset。`signal=T close`，`reference entry=T+1 XSHG open`；
1D/3D/5D/10D outcome 的读取完全晚于 signal generation，primary horizon 是 10D。

observer 消费既有 canonical watchlist 和对应 immutable development run manifest。
run manifest 中已有的 T-close input bars 仅用于 observation layer 恢复 breakout
provenance，不改 evaluator。每个 signal 保存 strategy/spec、input fingerprint、
generation fingerprint、watchlist/run-manifest SHA 和完整候选字段。

## 3. Deterministic breakout episode

canonical watchlist schema 没有 breakout index/base-hi 字段。observer 从同一个
run-manifest T-close input 的 B bars 恢复第一个满足既有 B breakout + pullback 语义的
episode；如果不能唯一恢复则 fail closed，不猜测或静默删除 signal。

`breakout_episode_id` 是以下字段的 canonical SHA identity：

`symbol + breakout_date + breakout_index + base_hi + strategy_spec_sha256`

同一 symbol、同一 episode 的第一个 prospective qualified signal 标记
`first_signal_in_episode=true`，作为 episode-level independent N；后续 signal 仍保留
在 raw signal-level stream，标记 `episode_repeat=true`，但不增加 independent N。

## 4. Execution feasibility 与 outcome record

observer 不把 T+1 open 自动声称为实际成交。每个 signal 初始为
`PENDING_REFERENCE_OPEN`，成熟 outcome 必须明确记录以下分类之一：

- `EXECUTABLE_REFERENCE_OPEN`
- `SUSPENDED`
- `LIMIT_STATE_EXECUTION_UNCERTAIN`
- `MISSING_OPEN`
- `DATA_FAILURE`
- `OTHER_EXPLICIT_NON_EXECUTABLE`

所有记录的 execution 语义均为 `REFERENCE_EXECUTION_NOT_ACTUAL_FILL`。不得用下一可用
价格替代 T+1 open、对停牌向后填充、对一字涨停假设成交，或静默删除失败 symbol。

成熟 outcome 至少追加：symbol、signal_date、breakout_episode_id、
first_signal_in_episode、strategy_version、spec_sha、input/output identity、T+1
reference open、execution classification、1D/3D/5D/10D return、5D/10D MFE/MAE、
corporate-action treatment、outcome maturity status。收益 path 复用既有 development
V2 convention：entry 是 T+1 XSHG open，target 是对应 future XSHG close；corporate
actions 只用于事后 outcome measurement，不进入 signal-time input。

`signals` 与 `outcomes` 都是 append-only event stream。signal event 的 bytes 和
identity 永不覆盖；未来成熟状态只能追加 `OUTCOME_UPDATE`。所有 event 带自身
`record_sha256`，损坏、空行、hash 不一致均 fail closed。

## 5. Fixed checkpoint

checkpoint 在任何 future outcome 读取前固定为：

- 至少 `60` 个已完成 XSHG signal sessions；
- 且至少 `200` 个 mature independent breakout episodes；
- finite maximum window：`120` 个 XSHG signal sessions。

该值按 event frequency 与统计稳定性的保守、可解释要求固定，不由 retrospective B
收益最优点反推；没有盈利表现提前停止：
`NO_EARLY_STOP_FOR_GOOD_PERFORMANCE`。

checkpoint 只产生待用户复核的状态，不自动 promotion。允许的最终 observation
conclusion 只有：

- `B_PROSPECTIVE_OBSERVATION_SUPPORTIVE`
- `B_PROSPECTIVE_OBSERVATION_NEEDS_MORE_EVIDENCE`
- `B_PROSPECTIVE_OBSERVATION_CONTRADICTORY`

无论哪一个，都必须由用户另行决定 frozen candidate、matched-control、B V2 或
reject/defer。

## 6. Output 与 diagnostics

默认 store：`data/prospective_observation/b_v1_1/`。

- `protocol_manifest.json`：一次写入、immutable；保存固定 protocol/checkpoint。
- `events.jsonl`：按 calendar time 追加 `SESSION_OBSERVED`、`SIGNAL`、
  `OUTCOME_UPDATE`；不覆盖 signal bytes。

`summary` 提供 primary episode-deduplicated 10D return（T+1 reference open）的 N、
mean、median、positive rate、mean CI 及 Wilson uncertainty estimate，并提供 raw vs
episode、first/second calendar half、monthly concentration、top contributors、symbol
/sector concentration、execution coverage、MFE/MAE 和 market-regime descriptive
split。diagnostics 只解释，不用于中途优化 B。

最小 focused tests 覆盖 signal immutability、deterministic episode identity、repeat
retention/dedup、no backfill、no outcome leakage、maturity、failed execution 和 T/T+1
calendar correctness。当前不创建 observation data，不运行 future capture，不读取
任何 retrospective outcome table 或 Final OOS。
