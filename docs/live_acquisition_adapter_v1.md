# Live acquisition adapter V1

更新时间：2026-08-31（Asia/Shanghai）

## Decision boundary

本文件描述首个 B candidate-bound prospective input 所需的执行路径，不是
`LIVE_OBSERVED` evidence，也不创建或冻结任何正式 prospective package、canonical
watchlist 或 `FROZEN_CANDIDATE_CONTRACT_V1`。

本次审计确认 master 原有代码只有 Phase 2B manifest validator，没有 AkShare 或
Tencent daily-K acquisition adapter。因此当前 P1
`P1-FC-LIVE-ACQUISITION-ADAPTER_MISSING` 在本分支以最小实现解决；合并前仍不改变
formal Delivery Ladder，首个真实 T-close input instance 仍是后续 prerequisites gate。

## Implemented path

[`scripts/live_acquisition.py`](../scripts/live_acquisition.py) 只允许以下顺序：

1. 验证 `as_of_date` 是 XSHG session、当前 BJT 日期就是 T，并且当前时间不早于
   官方 session close；否则分别 fail closed 为 `CALENDAR_ERROR`、
   `INPUT_DATE_MISMATCH` 或 `SESSION_NOT_CLOSED`，且 provider 不会被调用。
2. 通过 AkShare `stock_info_a_code_name` 获取 T 日 universe 与 display names。
3. 通过 AkShare `stock_board_industry_name_em` 获取行业 definitions/rank/change，
   再通过 `stock_board_industry_cons_em` 获取每个行业的 members；缺列、空结果、
   缺覆盖、重复/跨行业冲突或名字冲突均失败。
4. 通过既有 Tencent quote parser 获取所有 universe symbols 的 T 日 quote。
5. 通过 Tencent `appstock/fqkline/get` 的 `qfqday` 获取每只股票和 `sh000001`
   指数的 daily K；只接受 `PROVIDER_QFQ_SNAPSHOT`，缺 T、未来 bar、重复日期、
   不完整 OHLCV 或覆盖不足均失败。
6. 从 T 日 qfq index K 派生带 T、provider、adjustment 和 index hash 的 canonical
   `market_env`，再调用既有 `freeze_generation_inputs()` 构造 READY
   `GenerationInputManifest`。
7. 返回内存 `LiveInputPackage`，将 candidate/spec、display names、market_env、
   provider/runtime versions、quality checks、recovery state 和 generation
   fingerprint 绑定。显式持久化时按完整 fingerprint 使用 immutable path；该模块
   不写 canonical watchlist。

`GenerationInputManifest.input_fingerprint` 保持 Phase 2B 语义；display names 和
`market_env` 进入 candidate-bound `generation_fingerprint`，以避免同一 raw input
下的辅助输入变化被静默接受。

## Runtime readiness snapshot

- Python：`3.12.13`
- AkShare：实际安装并由 `importlib.metadata.version("akshare")` 读取为
  `1.18.94`
- pandas：`2.2.3`
- requests：`2.32.3`
- exchange-calendars：`4.13.2`
- pyarrow：保留当前 `25.0.1`；未为 prospective runtime 降级，`17.0.0` 仍只是
  research optional pin

已做的 capability probe 只 import AkShare 并检查三个 API callable；没有调用任何
live endpoint，没有获取或保存正式 T 日数据。

## Acceptance tests

`tests/test_live_acquisition.py` 使用 fake AkShare frames、Tencent response fixture
和固定时间，覆盖 pre-close、wrong date、provider unavailable、空/不完整 universe、
sector rank/member/name errors、stale/missing quote、stale/future Kline、T+1、
fingerprint/byte determinism、immutable persistence、current-data backfill 和
incomplete manifest 不写 output。

## Remaining gate

本分支完成的是 implementation/runtime readiness，不是 evidence freeze。合并和 Sol
review 前不获取真实 provider 数据；正式收盘后才允许以真实 T 日输入运行，并按
`CANDIDATE_BOUND_PROSPECTIVE_INPUT_PROVENANCE_CONTRACT_V1` 审计首个
`LIVE_OBSERVED` package。
