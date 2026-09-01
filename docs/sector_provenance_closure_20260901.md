# Sector provenance closure — 2026-09-01

This is a current-state closure record for the continuation task. It is a
development/governance diagnostic, not prospective evidence, a frozen artifact,
or a Final OOS observation.

## Machine-readable decision

```json
{
  "decision": "B_RECONSTRUCTION_SEMANTIC_MISMATCH",
  "task_classification": ["correctness_blocker", "product_blocker"],
  "pr18": {
    "number": 18,
    "state": "MERGED",
    "merge_sha": "17371fde39a6b24241532b131caf5927cb9b8933",
    "exact_head_ci": {
      "workflow": "correctness",
      "run_id": "33476256589",
      "event": "push",
      "head_sha": "17371fde39a6b24241532b131caf5927cb9b8933",
      "conclusion": "success"
    }
  },
  "closure_branch": "codex/sector-provenance-closure-20260901",
  "closure_head": "LOCAL_UNPUBLISHED_GOVERNANCE_COMMIT",
  "origin_master": "17371fde39a6b24241532b131caf5927cb9b8933",
  "closure_branch_pushed": false,
  "strategy_version": "B_BREAKOUT_RETEST_LEGACY_V1",
  "strategy_spec_sha256": "5bbeb345ebd8883149138d2f29f8606f919949ae285aa2839fa337921dfc7112",
  "active_input_contract": "CANDIDATE_BOUND_PROSPECTIVE_INPUT_PROVENANCE_CONTRACT_V2",
  "formal_t_close_capture": "NOT_RUN",
  "canonical_watchlist": "NOT_CREATED",
  "final_oos": "SEALED_UNREAD",
  "phase_2f": "NOT_STARTED",
  "promotion": "NOT_STARTED"
}
```

The stop is correctness-first. No current response is promoted to a T-close
package, and no historical 2026-08-31 attempt is rewritten with this snapshot.

## Live Git/GitHub closure

PR #18 was reviewed against its actual head
`0bfe7d1e012ad5213b82b5bbfe42776e5f3a0652`, with the pre-merge exact-head
correctness run successful and the PR `CLEAN`/`MERGEABLE`. It was squash-merged
to `master` as `17371fde39a6b24241532b131caf5927cb9b8933`. The post-merge push
correctness run `33476256589` completed successfully at that exact merge SHA.

The closure branch was created from that merged `origin/master`. At intake and
after branch creation, the only worktree change outside this task was the
pre-existing untracked user directory
`data/validation/continuous_speed_probe/`; it was not touched.
The branch now has one local unpublished governance commit above `origin/master`;
its live SHA is recorded in the final handoff snapshot. It was not pushed and has
no new PR because no safe code correction was identified.

## Exact V0 semantics versus current B evaluator

The fixed V0 source is
`EFSing/ashare_watchlist-V0@c8406c393c0b135eafb0aec763576ae869fddcff`,
`ashare_watchlist/scripts/screen_system.py`, source SHA
`6cac746123e315199cbeeb1a612868ef77b50af6c7c64b0d80eb387ae1d19f9`.

V0 `get_sectors()` queried `stock_sector_spot()` and then
`stock_sector_detail(sector=label)`. Per-sector detail errors were caught and
skipped. The resulting mapping used assignment semantics, so a symbol in more
than one sector was last-write-wins in the provider's sector iteration order.
The V0 call did not pass an explicit indicator; with the audited runtime this
resolves to the Sina industry source, whereas the current adapter passes the
exact indicator explicitly.
For a symbol absent from that partial mapping, the main loop used:

```text
sec_name = "-"
sec_rank = 50
sec_chg = 0.0
```

The stock then continued through the B evaluator. Thus V0 missing sector data
was not a per-symbol `INSUFFICIENT_DATA` rejection and did not cause a package
level stop; it could still produce a candidate if the remaining B conditions
passed.

The current B evaluator has a different executable path: missing sector
evidence returns `INSUFFICIENT_DATA` with `MISSING_SECTOR_EVIDENCE` before B
array evaluation. A synthetic fixture confirms this current behavior. A
complete fixture repeats with the same decision object. If a malformed
multi-record manifest bypasses the live adapter, `_sector_evidence()` returns
the first valid record; ambiguity is not independently detected by the
evaluator.

| Case | V0 behavior | Current evaluator behavior |
| --- | --- | --- |
| complete sector evidence | evaluate B | evaluate B |
| missing sector evidence | `("-", 50, 0.0)` and continue | `INSUFFICIENT_DATA` / `MISSING_SECTOR_EVIDENCE` |
| multi-sector symbol | last-write-wins by sector iteration order | first valid record if malformed manifest reaches evaluator |

This is an evaluator-level semantic difference, not merely the later live
package validation. Because the user-specified stop condition is an exact B
reconstruction, the decision is `B_RECONSTRUCTION_SEMANTIC_MISMATCH`. The B
strategy, spec, thresholds, and hash were not changed.

## Contract-layer fail-close distinction

The current V2 live adapter additionally enforces full-scope sector coverage,
rejects distinct multi-sector memberships, and permits deterministic removal of
exact duplicate rows only with raw-row diagnostics. Those are package-level
input integrity rules. They are not present in the V0 evaluator semantics.

The distinction is therefore:

| Layer | Missing symbol | Multi-sector symbol | Status in this task |
| --- | --- | --- | --- |
| V0 evaluator | default `-`, rank 50, change 0 | last-write-wins | audited, not modified |
| Current B evaluator | per-symbol `INSUFFICIENT_DATA` | first valid record if adapter is bypassed | semantic mismatch found; stop |
| Current V2 live adapter | package fail-closed on incomplete scope | package fail-closed on distinct memberships | retained; not claimed to be V0 strategy semantics |
| Proposed Model S/V3 | would need explicit per-symbol statuses and a completeness policy | would need explicit ambiguity status/policy | not adopted |

No Model S/V3 contract, strategy change, fallback taxonomy, symbol dropping,
name reconciliation, or parameter choice is authorized by this closure.

## AkShare and exact Sina parity audit

The installed runtime is AkShare `1.18.94`. Its exact Sina implementation was
read from `.venv/Lib/site-packages/akshare/stock/stock_industry.py`:

- `stock_sector_spot(indicator="新浪行业")` calls
  `newSinaHy.php`, parses the JSON object, and returns 49 definitions.
- `stock_sector_detail(sector=...)` calls
  `Market_Center.getHQNodeStockCount`, calculates `ceil(count / 80)`, and
  requests pages from `Market_Center.getHQNodeData` with
  `sort=symbol`, `asc=1`, and `num=80`.
- The implementation has no retry, no count/data consistency assertion, no
  duplicate policy, and no schema-level completeness assertion.

The underlying requests were:

```text
spot:  http://vip.stock.finance.sina.com.cn/q/view/newSinaHy.php
count: http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeStockCount
data:  http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData
data params: page, num=80, sort=symbol, asc=1, node=<sector>, symbol=, _s_r_a=page
```

Sina spot JSON was sliced from the first JSON object character and decoded;
member JSON was decoded with AkShare's `demjson` helper. Requests used their
default response encoding and had no explicit retry/backoff.

For the current exact-Sina snapshot, all 49 definitions were audited against
the raw endpoint and the AkShare wrapper. Results were:

| Check | Result |
| --- | ---: |
| spot definitions | 49 / 49 |
| completed member calls | 49 / 49 |
| raw member rows | 2,983 |
| AkShare member rows | 2,983 |
| raw unique symbols across sectors | 2,978 |
| raw parse failures | 0 |
| per-sector row-count deltas | 0 / 49 |
| per-sector first/last-symbol mismatches | 0 / 49 |
| duplicate symbols within a sector | 0 |
| exact duplicate rows | 0 |
| sector-call errors | 0 |

The count endpoint was lower than the returned data in these sectors (the
returned data still fit within the page count in this snapshot):

```text
new_dlhy 61/62 (+1)    new_dzxx 245/247 (+2)  new_glql 19/20 (+1)
new_gthy 58/60 (+2)    new_jdhy 36/37 (+1)    new_jzjc 90/91 (+1)
new_nyhf 45/46 (+1)    new_qczz 102/103 (+1)  new_qtxy 159/160 (+1)
new_snhy 25/26 (+1)    new_swzz 153/155 (+2)  new_sybh 92/93 (+1)
new_syhy 23/24 (+1)    new_tchy 7/8 (+1)      new_ysjs 69/72 (+3)
```

This is a provider consistency anomaly to retain for a future hardened
adapter; it did not produce a wrapper-versus-raw coverage difference in this
audit.

Conclusion: `EXACT_SINA_AKSHARE_WRAPPER_INCOMPLETE` was not observed. The
secondary provider finding is `EXACT_SINA_CURRENT_SOURCE_INTRINSICALLY_INCOMPLETE`:
the current source itself covers only 2,978 unique symbols, so the shortfall versus
the 5,221-symbol HiThink SH/SZ A-share scope is an intrinsic source-coverage
fact in this snapshot, not a safe wrapper parsing correction.

## Current 2,682-symbol coverage decomposition

The current in-memory diagnostic used 5,565 raw HiThink universe rows, of which
5,221 are in `TRADABLE_UNIVERSE_SCOPE_V1 = SH_SZ_A_SHARE_ONLY`. Exact Sina
returned 2,983 sector rows / 2,978 unique symbols. The resulting partition is:

```text
scoped universe:                    5,221
sector unique symbols in scope:    2,539
universe symbols missing sector:    2,682
sector symbols outside scope:         439
multi-sector scoped symbols:            5
```

Missing symbols by exchange:

```text
SH  1,329       SZ  1,353
```

Missing symbols by board classification:

```text
CHINEXT                 981
OTHER_SCOPED_PREFIX       1
SH_MAIN                  739
STAR                     589
SZ_MAIN                  372
```

Missing symbols by code prefix:

```text
000  3    001 102    002 225    003  42    300 533    301 447    302 1
600 36    601  95    603 496    605 112    688 589    689 1
```

Name-derived flags on the missing rows are only raw-name diagnostics, not
listing-status conclusions: `ST/*ST`-like 52, `-U` 26, `-UW` 1, `-W` 6.
The HiThink response exposes only `asset_type`, `currency`, `exchange`,
`name`, `thscode`, and `ticker`; it has no listing date, first-trading date,
delisting/status, or code-reuse field. Therefore listing-year cohorts,
recent-versus-old classification, and current listing status are
`INSUFFICIENT_DATA` / not identifiable from this response. No stale/deprecated
code conclusion was inferred, and no current-name or alternate-code hit was
found for the missing rows.

## Five multi-sector symbols

The raw exact-Sina snapshot contained these five distinct multi-sector
identities. `legacy final` is the V0 last-write-wins value under the observed
spot iteration order; it is an audit observation, not a proposed production
resolution.

| Symbol | Raw memberships (spot ordinal; detail position; change, rank) | Raw identity | Legacy final |
| --- | --- | --- | --- |
| `000587` | `new_sybh` 商业百货 (40; 64; +2.591, 2); `new_ysjs` 有色金属 (47; 36; -1.888, 46) | `sz000587` / `*ST金洲` | 有色金属 / 46 |
| `000602` | `new_dlhy` 电力行业 (4; 44; +0.596, 22); `new_ysjs` 有色金属 (47; 37; -1.888, 46) | `sz000602` / `金马集团` | 有色金属 / 46 |
| `002217` | `new_dzqj` 电子器件 (6; 68; -2.818, 48); `new_hghy` 化工行业 (18; 77; -1.807, 45) | `sz002217` / `ST合力泰` | 化工行业 / 45 |
| `002617` | `new_dqhy` 电器行业 (5; 36; -0.779, 41); `new_ysjs` 有色金属 (47; 71; -1.888, 46) | `sz002617` / `露笑科技` | 有色金属 / 46 |
| `600714` | `new_mthy` 煤炭行业 (30; 15; -0.972, 43); `new_ysjs` 有色金属 (47; 24; -1.888, 46) | `sh600714` / `金瑞矿业` | 有色金属 / 46 |

The raw symbol and name identity was stable for both sector rows per target.
Live quote fields varied slightly between detail calls, which is another
reason not to synthesize a single sector record from separate calls. The V2
adapter remains package-fail-closed for these distinct memberships.

## Package versus per-symbol conclusion

There are two separate conclusions, and they must not be conflated:

1. A per-symbol Model S design could preserve the full universe and emit
   explicit missing/ambiguous statuses. It would require a deliberate contract
   decision and an evaluator semantic decision before adoption.
2. The current V2 package builder fails closed when the full sector evidence is
   incomplete or ambiguous. That prevents a partial package from being treated
   as a complete input, but it does not repair the evaluator's V0 missing-data
   semantics.

The second rule is not evidence that the first rule has been adopted. Because
the current evaluator already deviates from exact V0 on missing evidence, this
task stops at `B_RECONSTRUCTION_SEMANTIC_MISMATCH` before a T-close capture.

## Corrections and validation boundary

No safe code correction was identified or made in this closure:

- no wrapper/pagination/parser patch;
- no duplicate or multi-sector resolution change;
- no B evaluator/spec/threshold change;
- no universe shrink, taxonomy substitution, name join, backfill, tuning, C,
  Phase 2F, Final OOS read, promotion, or trading action.

The only new artifact is this governance evidence record. The registered B
spec SHA remains
`5bbeb345ebd8883149138d2f29f8606f919949ae285aa2839fa337921dfc7112`.
Formal `LIVE_OBSERVED` capture for `T=2026-09-01` was not run; the daytime
diagnostics are not a substitute for the XSHG close gate.

The branch must still pass the repository's normal final checks before any
commit is handed off: tests, `compileall`, JSON/hash validation,
`git diff --check`, and a final Git/GitHub/CI snapshot. Delivery Ladder remains
`development candidate`; the candidate is not promoted to a canonical
watchlist-producing milestone.
