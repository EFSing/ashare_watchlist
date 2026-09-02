# TRADABLE UNIVERSE LISTING ELIGIBILITY AUDIT — 2026-09-02

> `CURRENT_ONLY_DIAGNOSTIC_NOT_PROSPECTIVE_EVIDENCE`

## Classification and research question

- classification: `correctness blocker`
- research question: whether HiThink `/api/meta/tickers/list` supplies a reliable
  listing-eligibility field that can deterministically decide whether `301686` was
  already listed on `as_of_date=2026-09-02`.
- materiality: the answer determines whether the acquisition universe can be corrected
  without look-ahead, code-specific exceptions, historical backfill, or a second
  listing engine. Including a pre-listing security can make the `TRADABLE_UNIVERSE_SCOPE_V1`
  contract materially false.
- stop condition: record the exact current row/schema and provider semantics; if no
  reliable listing-eligibility field exists, stop at
  `TRADABLE_UNIVERSE_LISTING_ELIGIBILITY_SOURCE_DECISION_REQUIRED`.

## Diagnostic boundary

This was one current-only, read-only provider diagnostic for exact target `301686`.
The response was not used as a formal T-close input, was not persisted as a
`UniverseManifest`, was not reused in a package, and did not trigger B evaluation,
watchlist generation, or a formal capture retry. No data under
`data/validation/continuous_speed_probe/` was read or modified.

## HiThink request and provider response

| field | value |
| --- | --- |
| provider | HiThink Financial-API |
| endpoint | `/api/meta/tickers/list` |
| query | `exchange=SZ&asset_type=a-share&limit=10000&offset=0` |
| response code | `0` |
| provider `data.timestamp` | `1788336018945` ms Unix = `2026-09-02T16:00:18.945+08:00` |
| local retrieval timestamp | `2026-09-02T18:37:39.8513903+08:00` |
| returned page item count | `5566` |
| exact target row count | `1` |

The provider's published endpoint contract says `data` is `{timestamp, item[]}` and
each item uses the `TickerItem` schema. The published fields are `thscode`, `ticker`,
`name`, `exchange`, `asset_type`, and `currency`.

Source: [HiThink Financial-API metadata endpoint contract](https://github.com/HiThink-Tech/Financial-API/blob/main/skills/hithink-finance/references/api/endpoints-meta.md).

### Exact raw target row

```json
{
  "thscode": "301686.SZ",
  "ticker": "301686",
  "name": "中塑股份",
  "exchange": "SZ",
  "asset_type": "a-share",
  "currency": "CNY"
}
```

### Exact observed row schema

```text
["thscode", "ticker", "name", "exchange", "asset_type", "currency"]
```

No additional raw fields were present in the target row. In particular, the response
did not provide `listing_date`, `list_date`, `listing_status`, `security_status`,
`delisting_date`, `trading_status`, `market_status`, first-trading date, or another
field with equivalent as-of listing semantics.

## Decision

The HiThink universe response is sufficient to classify the row as an SZ A-share
metadata record, but it is **not sufficient** to determine whether that security was
listed on `2026-09-02`. The deterministic provider-based result is therefore:

```text
301686 @ 2026-09-02 = NOT_DETERMINABLE_FROM_HITHINK_LIST_METADATA
decision = TRADABLE_UNIVERSE_LISTING_ELIGIBILITY_SOURCE_DECISION_REQUIRED
research_exit = NEEDS_MORE_EVIDENCE
```

The task-provided external fact that `301686 中塑股份` had not yet begun trading on
2026-09-02 supports the root-cause direction
`PRE_LISTING_SECURITY_INCORRECTLY_INCLUDED_IN_TRADABLE_UNIVERSE`, but this endpoint
cannot prove that fact. It must not be silently promoted into a prospective provider
field or used to create a formal package.

Accordingly, this audit does **not** adopt a listing filter. It does not authorize:

- a hard-coded `301686` exception;
- code-age or historical-Kline inference;
- treating empty Tencent turnover as a valid quote;
- shrinking the universe or skipping a symbol at the Tencent stage;
- deleting suspended or ST securities from the acquisition universe; or
- a second listing/lifecycle engine without an approved authoritative source.

## Required semantic boundary if a source is later approved

If Sol approves a reliable listing-eligibility source, the smallest future correction
must make `TRADABLE_UNIVERSE_SCOPE_V1` retain already-listed SH/SZ A-share securities,
including suspended `002731`, while excluding `301686` only when its pre-listing status
is deterministically established for `as_of_date`. ST status remains outside this
acquisition-universe filter: `USER_TRADABILITY_ELIGIBILITY_NON_ST_V1` runs only after
B evaluation at the final user-facing eligibility layer.

No such source or filter was approved or implemented in this audit.

## Scope and final status

- universe code: unchanged; `_build_universe()` still has no listing-status filter.
- Tencent parser: unchanged by this audit; no empty-turnover relaxation was added.
- B/spec/threshold/score/top-N/sector semantics: unchanged.
- `USER_TRADABILITY_ELIGIBILITY_NON_ST_V1`: preserved as a post-evaluator final layer;
  it does not remove ST securities from acquisition inputs.
- formal capture: not rerun; no formal input or output artifact was created.
- registry: no new frozen artifact record; this document is a current-only diagnostic.
- final decision: `TRADABLE_UNIVERSE_LISTING_ELIGIBILITY_SOURCE_DECISION_REQUIRED`.

## Superseding source decision — 2026-09-02

Sol approved `USE_EXCHANGE_OFFICIAL_LISTED_ROSTER_VIA_EXISTING_AKSHARE`. The HiThink
metadata finding above remains immutable current-only evidence and is not being promoted to
listing evidence. The correction uses the existing AkShare official exchange wrappers only:

| exchange | exact API call | required fields | official source |
| --- | --- | --- | --- |
| SSE main board | `stock_info_sh_name_code(symbol="主板A股")` | `证券代码`, `上市日期` | `https://www.sse.com.cn/assortment/stock/list/share/` |
| SSE STAR | `stock_info_sh_name_code(symbol="科创板")` | `证券代码`, `上市日期` | `https://www.sse.com.cn/assortment/stock/list/share/` |
| SZSE A-share | `stock_info_sz_name_code(symbol="A股列表")` | `A股代码`, `A股上市日期` | `https://www.szse.cn/market/product/stock/list/index.html` |

The adopted identity is `EXCHANGE_OFFICIAL_CURRENT_LISTED_ROSTER_V1`. For prospective T,
listing dates are canonically parsed and the eligible roster is the exact six-digit symbol
set satisfying `listing_date <= as_of_date`; the acquisition universe is the exact
intersection with HiThink's broad SH/SZ A-share metadata. Missing/invalid fields,
unavailable rosters, or duplicate/conflicting official symbols fail closed before sector,
quote, and Kline calls. This same-day source is not a historical security master and cannot
backfill earlier T dates.

The implementation records package version, API/source identity, per-source row counts,
combined/eligible counts, content/semantic SHA-256 values, and HiThink-only/roster-only
mismatch diagnostics. It retains listed suspended `002731` in acquisition and excludes
`301686` before quote/Kline when official evidence excludes it or has `listing_date > T`.
ST/*ST remains the post-B `USER_TRADABILITY_ELIGIBILITY_NON_ST_V1` filter. Formal capture
was not rerun.

Final decision: `ADOPT` — `EXCHANGE_OFFICIAL_CURRENT_LISTED_ROSTER_V1`.
