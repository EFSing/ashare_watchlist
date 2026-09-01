# B dependency source audit — 2026-09-01

> `LOCAL_CURRENT_SNAPSHOT_DIAGNOSTIC_NOT_PROSPECTIVE_EVIDENCE`

## Scope and stop condition

研究问题：在不修改 B strategy/spec/threshold、 eligibility、returns、C、Phase 2F 或
Final OOS 的前提下，审计 B 当前代码究竟把 display name、sector identity、sector
rank/change 用在哪里，并核对当前机器能否读取这些 live dependencies。

materiality：这个审计直接决定 PR #18 的 display-name correction 是否会改变 B 的
executable semantics，以及首个 frozen-candidate T-close package 是否可以继续进入
B evaluation。停止条件是 source call graph、required-field/gate 语义和当前 provider
coverage/duplicate/ambiguity 可以明确；不因发现新的分组或指标而扩展研究。

输入：`scripts/b_breakout_retest.py`、`scripts/a_platform_breakout.py`、
`docs/strategy_candidate_nomination_v1.md`、`docs/strategy_candidate_eligibility_report.md`、
`docs/candidate_bound_prospective_input_contract_v1.md`、当前 PR #18 source changes、
以及 fresh `.venv` 中的只读 HiThink/AkShare capability probe。provider payload 仅在
内存中读取，本文件不保存 raw payload，也不构造 `GenerationInputManifest`、
`LIVE_OBSERVED` package 或 watchlist。

## Source audit result

| Dependency | B use | Boundary | Classification |
| --- | --- | --- | --- |
| exact six-digit `symbol` | manifest lookup, candidate identity, evaluation hash, universe iteration | security/trading identity; SH/SZ scope is already validated by the adapter | `EXECUTABLE_REQUIRED` |
| HiThink `display_name` + Sina member name | retained in live adapter/provenance; not read by B evaluator | mismatch is diagnostic only under V2; no name join/filter/alias | `AUXILIARY_DIAGNOSTIC` |
| `sector_name` | `FeatureSnapshot`, report/provenance projection | not a selection threshold by itself | `OUTPUT_AFFECTING` (report/hash), not a name identity |
| `sector_rank` | `_score_b.strong_sector`: 10/6/2 point component | affects the B score breakdown after numeric gates pass | `OUTPUT_AFFECTING` |
| `sector_chg` | `_score_b.sector_linkage`: 10/5/1 point component | affects the B score breakdown after numeric gates pass | `OUTPUT_AFFECTING` |
| sector evidence presence | `_sector_evidence`; missing values return `INSUFFICIENT_DATA` with `SECTOR_EVIDENCE_COMPLETE` failed | every manifest universe symbol is evaluated; no silent drop or shrink | `EXECUTABLE_REQUIRED` |

The B source contains no display-name use in breakout matching, close/overextension/gain/
support/risk/RR/overhang gates, final status, candidate identity or selection. It does
consume sector rank/change in the score and requires complete sector evidence. Therefore
sector is not legacy generic baggage and cannot be downgraded to an auxiliary diagnostic.
The B strategy source and spec SHA remain unchanged:
`5bbeb345ebd8883149138d2f29f8606f919949ae285aa2839fa337921dfc7112`.

## Fresh-machine capability probe

The workspace-local `.venv` was created from repository `pyproject.toml` and installed with
`.[test,research]`. Preflight passed on Python 3.12.13 with pandas 2.2.3, requests 2.32.3,
exchange-calendars 4.13.2, AkShare 1.18.94, pytest 8.3.5 and pyarrow 17.0.0. HiThink
credential presence was recorded as boolean only. The XSHG/Asia/Shanghai calendar and the
default data root were readable and writable.

Current capability results, observed during the 2026-09-01 BJT daytime window:

- HiThink universe raw rows: `5,565`; current `SH_SZ_A_SHARE_ONLY` symbols: `5,221`.
- HiThink snapshot and adjustment-events endpoint probes: HTTP 200 / `code=0`.
- HiThink stock historical probe: 14 bars; index historical probe: 14 bars.
- AkShare exact Sina taxonomy: 49 definitions and 49 completed member calls;
  `stock_sector_spot(indicator="新浪行业")` plus `stock_sector_detail` only;
  exact legacy taxonomy: `true`.

These are current capability facts, not evidence for 2026-08-31 and not a substitute for a
future legitimate T-close capture.

## Current sector membership audit

The current in-memory exact-Sina audit reported:

| Measure | Current snapshot |
| --- | ---: |
| raw member rows | 2,983 |
| unique member symbols | 2,978 |
| common symbols with current HiThink universe | 2,539 |
| exact raw-name matches among common symbols | 2,492 |
| raw-name mismatches | 47 |
| normalized-name matches | 2,492 |
| mismatches resolved by registered normalization | 0 |
| universe symbols without a sector row | 2,682 |
| sector symbols outside the current universe | 439 |
| repeated exact-duplicate-row signal | 0 |
| exact duplicate symbols | none in this snapshot |

The five current symbols with multiple distinct sector memberships are:

| Symbol | Memberships returned by exact Sina |
| --- | --- |
| `000587` | `new_sybh/商业百货`; `new_ysjs/有色金属` |
| `000602` | `new_dlhy/电力行业`; `new_ysjs/有色金属` |
| `002217` | `new_dzqj/电子器件`; `new_hghy/化工行业` |
| `002617` | `new_dqhy/电器行业`; `new_ysjs/有色金属` |
| `600714` | `new_mthy/煤炭行业`; `new_ysjs/有色金属` |

The ambiguity is sector identity, not a display-name mismatch. It cannot be resolved by
choosing the first row, dropping the symbol, substituting another taxonomy, backfilling a
historical value, or shrinking the universe. Exact duplicate rows in a future valid input
may be deduplicated only when all semantic membership fields are identical; the raw row,
count and classification remain in provenance. This current snapshot had no such exact
duplicate symbols.

## Decisions and current gate

- `ADOPT`: `DISPLAY_NAME_CONSISTENCY_POLICY_V2_SYMBOL_AUTHORITATIVE`. Exact symbol is
  authoritative; raw names are retained independently; only the registered normalization
  is used for diagnostics; mismatch does not fail the package and never creates an alias.
- `NEEDS_MORE_EVIDENCE`: exact Sina sector membership must be both complete for the full
  SH/SZ universe and unambiguous at the future T-close observation. Missing evidence still
  maps to B `INSUFFICIENT_DATA`; no substitutions or silent drops are authorized. The
  missing evidence needed by this gate is a provider response that satisfies those exact
  coverage and membership conditions at the legitimate T-close.
- Current prerequisite decision:
  `FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_SECTOR_MEMBERSHIP_AMBIGUITY`, with an independent
  exact-coverage failure also present. The display-name blocker is resolved at the adapter
  policy level, but no complete live package exists.

No T=`2026-08-31` package is created or reconstructed from this current snapshot. Because
the current date has advanced and PR #18 has not been merged to clean master, no T=`2026-09-01`
T-close acquisition is launched in this task. `Final OOS` remains sealed/unread, and no
formal candidate contract, canonical output, promotion or Phase 2F artifact is created.
