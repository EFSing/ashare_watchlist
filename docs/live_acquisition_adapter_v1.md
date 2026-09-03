# Live acquisition adapter V1 (current candidate contract V2)

更新时间：2026-09-01（Asia/Shanghai）

## Decision boundary

本文件描述首个 B candidate-bound prospective input 所需的执行路径，不是
`LIVE_OBSERVED` evidence，也不创建或冻结任何正式 prospective package、canonical
watchlist 或 `FROZEN_CANDIDATE_CONTRACT_V1`。

PR #17 已将 live path 修正为 B 所需的 exact 新浪行业 provider architecture；本次
治理修正将 display-name consistency 从 security hard gate 改为 symbol-authoritative
diagnostic policy。它不改变 formal Delivery Ladder，首个真实 T-close input instance
仍是后续 prerequisites gate。

## Implemented path

[`scripts/live_acquisition.py`](../scripts/live_acquisition.py) 只允许以下顺序：

1. 验证 `as_of_date` 是 XSHG session、当前 BJT 日期就是 T，并且当前时间不早于
   官方 session close；否则分别 fail closed 为 `CALENDAR_ERROR`、
   `INPUT_DATE_MISMATCH` 或 `SESSION_NOT_CLOSED`，且 provider 不会被调用。
2. 通过 authenticated HiThink Financial-API `/api/meta/tickers/list` 获取当前
   `TRADABLE_UNIVERSE_SCOPE_V1 = SH_SZ_A_SHARE_ONLY` 范围内的 SH/SZ A-share
   universe 与 display names；BJ 明确排除，不属于该 scope 的 incomplete coverage。
   分页、资产类型、交易所、代码/名称冲突或 SH/SZ 空覆盖均失败。该 current snapshot
   只用于当日 live T，不用于历史回填。scope/version 写入 UniverseManifest、input/
   generation identity 和 provenance；未来纳入 BJ 必须使用新 scope/version。
3. 通过 AkShare `stock_sector_spot(indicator="新浪行业")` 获取 exact Sina
   industry definitions/change，按涨跌幅稳定计算 rank，再通过
   `stock_sector_detail` 获取每个 label 的 members；EM/THS/SW schema、taxonomy
   marker、空结果、缺覆盖或跨行业冲突均失败。display name 的 raw 值保留，按
   `DISPLAY_NAME_CONSISTENCY_POLICY_V2_SYMBOL_AUTHORITATIVE` 做诊断；同 sector 的
   exact duplicate provider row 可确定性去重并进入 provenance，名字差异不再用于
   symbol join/filter/security identity。
4. 通过既有 Tencent quote parser 获取所有 universe symbols 的 T 日 quote。
5. 以 HiThink `/api/a-share/prices/historical?adjust=forward` 获取每只股票 daily
   K，以 `/api/a-share-index/prices/historical` 获取 `000001.SH` 指数 K。股票只接受
   `PROVIDER_QFQ_SNAPSHOT`；HiThink 指数诚实标记为 `PROVIDER_RAW_SNAPSHOT`，Tencent
   explicit fallback index 才标记为 `PROVIDER_QFQ_SNAPSHOT`。stock raw、HiThink qfq
   index 和其他 provider/adjustment 配对均 fail closed。普通交易股票的最后一根必须为
   T；只有完整 T 日 Tencent quote 明确证明 no-trade/suspended 时，才允许非空真实历史的
   最后一根早于 T，但禁止 future bar；指数最后一根必须为 T。重复日期、不完整 OHLCV
   或覆盖不足均失败。只有 `LIVE_MARKET_DATA_FAILOVER_POLICY_V1`
   明确允许时，单只 HiThink transport failure 才可解析为版本化 Tencent `qfqday`
   fallback；语义/日期/schema failure 不触发 fallback。
6. 从 T 日 provider index K 派生带 T、provider、adjustment 和 index hash 的 canonical
   `market_env`，再调用既有 `freeze_generation_inputs()` 构造 READY
   `GenerationInputManifest`。
7. 返回内存 `LiveInputPackage`，将 candidate/spec、display names、market_env、
   provider/runtime versions、quality checks、recovery state 和 generation
   fingerprint 绑定。显式持久化时按完整 fingerprint 使用 immutable path；该模块
   不写 canonical watchlist。

`GenerationInputManifest.input_fingerprint` 保持 Phase 2B 语义；display names 和
`market_env` 进入 candidate-bound `generation_fingerprint`，以避免同一 raw input
下的辅助输入变化被静默接受。

The live package schema is now `CANDIDATE_BOUND_LIVE_INPUT_PACKAGE_V3` and its
generation identity is `CANDIDATE_BOUND_GENERATION_IDENTITY_V3`; both identities carry
the registered display-name normalization and
`DISPLAY_NAME_CONSISTENCY_POLICY_V2_SYMBOL_AUTHORITATIVE` versions. The active
provenance contract is `CANDIDATE_BOUND_PROSPECTIVE_INPUT_PROVENANCE_CONTRACT_V2`;
V1 remains preserved historical contract evidence.

## Runtime readiness snapshot

- Python：`3.12.13`
- AkShare：实际安装并由 `importlib.metadata.version("akshare")` 读取为
  `1.18.94`
- pandas：`2.2.3`
- requests：`2.32.3`
- exchange-calendars：`4.13.2`
- pyarrow：保留当前 `25.0.1`；未为 prospective runtime 降级，`17.0.0` 仍只是
  research optional pin

当前 capability verification（非 formal evidence）结果：HiThink authenticated
metadata、snapshot、stock/index historical K 和 adjustment-events endpoint 均返回
HTTP 200 / `code=0` 与结构化字段；AkShare 1.18.94 的 exact Sina APIs callable，
live spot 返回 49 个行业，首个 label 的 detail 返回 19 个成员。probe 没有保存
payload、没有构造 manifest/package，也没有改变 `2026-08-31` 的两次失败事实。

Capability decision：`HITHINK_LIVE_PRIMARY = SUPPORTED`；
`EXACT_SINA_SECTOR_SOURCE = AVAILABLE`。

## Acceptance tests

`tests/test_live_acquisition.py` 使用 fake HiThink/Sina frames、Tencent response
fixture 和固定时间，覆盖 pre-close、wrong date、HiThink/Sina unavailable、空/不完整
universe、exact Sina acceptance、EM/THS/SW taxonomy rejection、sector member/name
errors、stale/missing quote、stale/future Kline、T+1、HiThink primary、显式 Tencent
fallback、provider identity/fingerprint/byte determinism、immutable persistence、
semantic/schema no-retry、registered display-name normalization/raw-name preservation、
symbol-authoritative substantive ST/`*ST`/company-name diagnostics、exact duplicate
de-duplication、sector membership ambiguity and incomplete manifest 不写 output。

## Remaining gate

本分支完成的是 implementation/runtime readiness，不是 evidence freeze。合并和 Sol
review 前不获取真实 provider input/package；已允许的 capability probe 不保存 payload、
不构造 manifest/package，也不改变历史失败事实。正式收盘后才允许以真实 T 日输入运行，并按
`CANDIDATE_BOUND_PROSPECTIVE_INPUT_PROVENANCE_CONTRACT_V2` 审计首个
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

## Same-day post-merge retry result — 2026-08-31

After PR #16 was squash-merged at `c9d5e50be833bf5bb1c3c83c0a2fa1b3e83979c1` and
master correctness run `33372781495` passed at that exact head, a new complete acquisition
attempt was run with `observed_at_bjt=2026-08-31T16:27:36.974203+08:00`. It did not reuse
the earlier `15:21:18.969554+08:00` attempt or any partial response.

AkShare `stock_info_a_code_name` failed with `ConnectionError` after the fixed 3 attempts.
The adapter returned `PROVIDER_FAILURE` after `0.782s` of acquisition time. Sector code/name
were not applicable; completed sector calls were `0`; sector definition count and all later
stages were `NOT_REACHED`; the known universe count was `0`. No Tencent quote batch, stock or
index Kline request, market_env, READY manifest, persistence, or canonical watchlist occurred.

No `data/prospective_inputs/` directory, partial formal evidence, fingerprint, or SHA was
created. The final prerequisite decision remains
`FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_PROVIDER_FAILURE`; the task stops at this provider
blocker without automatic further attempts.

## P0 live taxonomy correction — 2026-08-31 (this branch)

Sol identified that the merged master path used Eastmoney industry APIs
`stock_board_industry_name_em` / `stock_board_industry_cons_em`, which cannot satisfy B's
frozen exact Sina-industry provenance. This is a correctness blocker, not a reason to alter
B's strategy or thresholds. The two same-day master attempts above remain failures and no
contaminated prospective artifact exists.

The correction in this branch makes HiThink Financial-API metadata the primary current
SH/SZ A-share universe/name source, HiThink forward-adjusted stock K and unadjusted index K
the primary market-data source, and AkShare `1.18.94`'s exact
`stock_sector_spot(indicator="新浪行业")` / `stock_sector_detail` pair the only sector
source. EM, THS and SW taxonomies are rejected before a package can be constructed. Tencent
Kline is available only as the explicitly versioned
`LIVE_MARKET_DATA_FAILOVER_POLICY_V1` / `TENCENT_QFQ_FALLBACK_V1` transport fallback; it
never substitutes the sector taxonomy. The index raw mode is named
`PROVIDER_RAW_SNAPSHOT`, so it is not mislabeled as qfq.

Capability probes were read-only and non-formal: HiThink metadata, snapshot, stock/index
historical K and adjustment-events endpoints returned HTTP 200 / `code=0`; exact AkShare
Sina spot returned 49 sectors and the first detail call returned 19 members. No payload was
saved, no package was run, and T=`2026-08-31` remains failed. The branch is ready for Sol
review; after review/merge, a new real T-close acquisition still requires explicit user
authorization and a fresh complete provider capture.

## Post-merge formal attempt — 2026-08-31

After PR #17 was squash-merged at `91e9ec76e3f4ea8ffaa1badeb759c1d2a7f5f73b` and
merge master correctness run `33399324692` succeeded, a new complete acquisition was
started with fresh `observed_at_bjt=2026-08-31T22:01:28.307161+08:00` for
T=`2026-08-31` / T+1=`2026-09-01`. It reached exact Sina sector/member display-name
validation and failed closed:

    INPUT_CONFLICT: display-name conflict for 000012: universe/member

No READY manifest, package, hash, local persistence, Drive upload, recovery read-back,
canonical watchlist, prospective return, or performance output was created. The exact
failure is an input/provider-data consistency conflict, not provider connectivity; the
correct prerequisite status is
`FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_INPUT_CONFLICT`. See the compact evidence record
and audit for the exact no-artifact boundary.

## PR #18 continuation — display-name consistency correctness fix

The current live capability diagnostic compared the complete
`SH_SZ_A_SHARE_ONLY` universe against all exact Sina sector definitions and their
member responses. The 2026-08-31 snapshot remains historical diagnostic evidence in
[`current_capability_name_diagnostic_20260831.md`](current_capability_name_diagnostic_20260831.md).
The fresh 2026-09-01 probe is recorded separately as a current snapshot only; its
counts must not be used to rewrite the 2026-08-31 formal attempt.

The implementation retains both raw provider values, compares only their normalized
forms, keeps the exact symbol as the security identity, and puts both the normalization
and policy versions in the candidate-bound generation identity and provenance. A name
mismatch is a non-secret structured diagnostic containing the symbol, both raw names,
both normalized names, and code points; it is not used for join/filter/security identity.
An exact duplicate sector row retains its raw row/count diagnostic without changing the
semantic membership set. A symbol in multiple distinct sectors remains fail-closed.
Historical 2026-08-31 evidence is not rewritten with current raw values or counts, and
no partial formal package is persisted.

## Current official exchange-roster correction — 2026-09-02

The current prospective universe path supersedes the earlier HiThink-only universe step.
HiThink `/api/meta/tickers/list` remains the broad SH/SZ A-share metadata source and keeps
the raw provider name for final user eligibility, but it does not provide listing-date or
listing-status evidence. Before sector, quote, or Kline acquisition, the adapter now reads
the official exchange-listed rosters through AkShare `1.18.94` and performs an exact
six-digit-symbol intersection:

- SSE: `stock_info_sh_name_code(symbol="主板A股")` and
  `stock_info_sh_name_code(symbol="科创板")`, required fields `证券代码` and `上市日期`,
  underlying source `https://www.sse.com.cn/assortment/stock/list/share/`;
- SZSE: `stock_info_sz_name_code(symbol="A股列表")`, required fields `A股代码` and
  `A股上市日期`, underlying source
  `https://www.szse.cn/market/product/stock/list/index.html`.

These sources and their API arguments define
`EXCHANGE_OFFICIAL_CURRENT_LISTED_ROSTER_V1`. Listing dates are canonically parsed and
must satisfy `listing_date <= as_of_date`; missing/invalid fields, unavailable rosters,
and duplicate/conflicting official symbols fail closed. The manifest/provenance records
package version, exact APIs and URLs, per-source row counts, combined/eligible counts,
content and semantic SHA-256 values, and the HiThink-only/roster-only mismatch lists.
Names are never used as identity or join keys. A pre-listing symbol such as `301686` is
excluded before Tencent quote/Kline calls only when the official roster evidence excludes
it; an already-listed suspended `002731` remains in the acquisition universe. The existing
`USER_TRADABILITY_ELIGIBILITY_NON_ST` filter remains after B evaluation and does not remove
ST securities from acquisition.

This is a same-day `LIVE_OBSERVED` source for prospective T-close acquisition only. It is
not a historical security master and must not be used to backfill any earlier T date.
