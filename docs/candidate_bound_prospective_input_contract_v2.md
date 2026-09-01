# Candidate-Bound Prospective Input / Provenance Contract V2

更新时间：2026-09-01（Asia/Shanghai）

## Contract identity and relationship to V1

- contract：`CANDIDATE_BOUND_PROSPECTIVE_INPUT_PROVENANCE_CONTRACT_V2`
- status：`CONTRACT_DEFINED_NO_LIVE_INSTANCE`
- bound candidate：`B_BREAKOUT_RETEST_LEGACY_V1`
- strategy spec SHA-256：`5bbeb345ebd8883149138d2f29f8606f919949ae285aa2839fa337921dfc7112`
- supersedes for future live packages：`CANDIDATE_BOUND_PROSPECTIVE_INPUT_PROVENANCE_CONTRACT_V1`

V1 remains historical governance evidence and is not rewritten. V2 changes only the
display-name consistency policy after the B source audit proved that display names are
not security identity or B selection semantics. It does not weaken B's exact Sina
sector membership, coverage, ambiguity, timing, provider, or recovery requirements.
No live package or `FROZEN_CANDIDATE_CONTRACT_V1` is created by this contract change.

## Required identity policy

`DISPLAY_NAME_CONSISTENCY_POLICY_V2_SYMBOL_AUTHORITATIVE` applies:

- exact six-digit symbol is the security identity; exchange is already fixed by the
  `SH_SZ_A_SHARE_ONLY` scope and HiThink `thscode` validation;
- HiThink and Sina raw names are retained independently for audit;
- missing/empty names fail closed;
- name values are compared only with
  `DISPLAY_NAME_NORMALIZATION_NFKC_TRIM_EXPLICIT_ZERO_WIDTH_V1` for diagnostics;
- interior spaces, `ST`/`*ST`, A/B markers, `-U`/`-W`/`-UW`, and other substantive
  suffixes are not removed and do not create aliases;
- name mismatch count/list, raw/normalized values and code points enter provenance;
- same-source duplicate or conflicting symbol identity, unknown sector symbol,
  duplicate ambiguous sector membership, and provider symbol mismatch still fail closed.

The policy version enters the candidate-bound generation identity/fingerprint and
package provenance. Changing the policy requires another contract/package identity;
it cannot overwrite V1 evidence.

## B-required sector boundary

B's current evaluator remains unchanged. `sector_name` is retained in its feature/report
projection; `sector_rank` and `sector_chg` feed the B 85-score `strong_sector` and
`sector_linkage` components; and missing sector evidence returns `INSUFFICIENT_DATA`.
Therefore sector membership remains an executable required input for a complete B
evaluation. Exact Sina `stock_sector_spot(indicator="新浪行业")` plus
`stock_sector_detail` remains the only permitted source. V2 does not make sector an
auxiliary diagnostic and does not authorize shrinking the universe or substituting
EM/THS/SW taxonomy.

Exact duplicate provider rows in the same sector may be deterministically de-duplicated
when every semantic membership field is identical. Raw duplicate rows, count and
classification remain in provenance; the semantic membership set is unchanged. A
symbol appearing in multiple distinct sectors fails closed as
`FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_SECTOR_MEMBERSHIP_AMBIGUITY`.

## Unchanged required fields

V2 retains V1's B identity/spec SHA, T-close/T+1 and XSHG calendar, explicit
`TRADABLE_UNIVERSE_SCOPE_V1 = SH_SZ_A_SHARE_ONLY`, exact Sina taxonomy, current-data
backfill prohibition, provider/version metadata, freshness/completeness checks,
recoverable package identity, deterministic retry semantics, input/generation/output
hashes, and no formal output on failed acquisition.

The first acceptable package must still be a new real `LIVE_OBSERVED` T-close package
with `known_at <= T`. Current capability probes are not prospective evidence and cannot
construct a package for 2026-08-31 after the BJT date has advanced.
