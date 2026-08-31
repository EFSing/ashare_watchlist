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
fingerprint/byte determinism、immutable persistence、current-data backfill、
AkShare transient recovery / bounded exhaustion、sector-member retry、semantic/schema
no-retry 和 incomplete manifest 不写 output。

## Remaining gate

本分支完成的是 implementation/runtime readiness，不是 evidence freeze。合并和 Sol
review 前不获取真实 provider 数据；正式收盘后才允许以真实 T 日输入运行，并按
`CANDIDATE_BOUND_PROSPECTIVE_INPUT_PROVENANCE_CONTRACT_V1` 审计首个
`LIVE_OBSERVED` package。

## Post-merge execution result — 2026-08-31

PR #15 was squash-merged to master at
`f1fed4608210aa175ac268189a8d7f032b0b88e0`, with master correctness run
`33367655723` successful at that exact head. The first formal master-baseline call for
T=`2026-08-31` started at actual BJT runtime
`2026-08-31T15:21:18.969554+08:00`, after the XSHG close at 15:00 BJT, but AkShare
sector membership acquisition raised `ConnectionError`. The adapter returned
`PROVIDER_FAILURE` and stopped; no READY manifest, live package, quote/Kline package,
fingerprint, persistence, or canonical watchlist was created. `data/prospective_inputs/`
remained absent. This is a real provider blocker, not `LIVE_OBSERVED` evidence. The same
Phase 2B T-close contract permits a new independent attempt on the same BJT date T after the
official close; it must use a new real `observed_at`, re-acquire every required input, and not
reuse any partial response from the failed attempt. Once the BJT date has advanced to
`2026-09-01`, current live provider data must never be used to construct a `T=2026-08-31`
package; the next valid T-close session is then required.

## AkShare bounded transient retry — PR #16

Each of the three AkShare provider-read APIs is retried independently for transient network/
connection exceptions, with a fixed maximum of 3 attempts and bounded backoff (`0.25s`, then
`0.50s`). The retry boundary ends when a response is returned: schema, empty, duplicate,
name/sector conflict, and coverage validation are performed once and fail closed without
another read. A retry never changes source, date, universe, or strategy semantics; exhausted
transient failures map to `PROVIDER_FAILURE` and create no formal package.

Retry attempt/backoff details are process diagnostics only. They are excluded from the canonical
input fingerprint, candidate-bound generation fingerprint, package content identity, and
successful provenance; only the final captured inputs and actual provider/runtime identities are
represented there.

## Execution-scale audit

The current complete-universe execution model is: one universe read; one sector-definition read;
one logical sector-member read per returned definition (with transient retry scoped to that same
read); Tencent quote batches of 50 symbols, `ceil(universe_symbol_count / 50)`; and
`universe_symbol_count` planned stock-Kline requests, plus one index-Kline request. These are
execution diagnostics, not selection rules. No stock may be silently dropped to reduce the
scale. The first formal failure stopped in sector membership, so its real universe, definition,
quote-batch, and Kline counts remain `NOT_REACHED`.
