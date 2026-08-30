# Candidate-Bound Prospective Input / Provenance Contract V1

更新时间：2026-08-30（Asia/Shanghai）

## Contract identity

- contract：`CANDIDATE_BOUND_PROSPECTIVE_INPUT_PROVENANCE_CONTRACT_V1`
- status：`CONTRACT_DEFINED_NO_LIVE_INSTANCE`
- bound candidate：`B_BREAKOUT_RETEST_LEGACY_V1`
- strategy spec SHA-256：`5bbeb345ebd8883149138d2f29f8606f919949ae285aa2839fa337921dfc7112`
- eligibility protocol：`STRATEGY_DEVELOPMENT_ELIGIBILITY_V1`
- eligibility rule：`ELIGIBILITY_RULE_FROZEN_BEFORE_B_RETURNS_READ = true`

This is a contract for the first real prospective input package. It is not a
prospective observation, does not create a watchlist, and does not create
`FROZEN_CANDIDATE_CONTRACT_V1`.

## Required bound fields

| Field | Contract requirement |
| --- | --- |
| candidate identity | B strategy version and exact spec SHA above; no silent rule or threshold change |
| timing | signal uses T close only; execution is the next XSHG session T+1 |
| universe | exact T-date universe identity, source/version, as-of date, file/content SHA and row identity |
| sector semantics | explicit historical membership/taxonomy status; no current-data backfill or substitute taxonomy |
| names | exact normalized/display-name mapping used for this T input; missing or conflicting names fail closed |
| market_env | canonical T-date market-environment identity and source/provenance |
| provider/version | provider name, API/data version, acquisition timestamp, and dependency/runtime versions |
| calendar | XSHG calendar identity, `Asia/Shanghai`, session-close evidence and T+1 session identity |
| availability/fail-closed | completeness, freshness, duplicate/conflict checks, and explicit failure status when unavailable |
| recovery | recoverable input package, byte/content hashes, recovery status and deterministic retry identity |
| generation fingerprint/output identity | fingerprint binds all output-affecting inputs, candidate identity, schema/contract versions, and canonical output bytes/SHA |

## Acceptance rules for the first instance

1. The package must be marked `LIVE_OBSERVED` and have `known_at <= T`; a
   retrospective artifact cannot stand in for this instance.
2. T must be an actual XSHG session after the official close. Same-bar execution,
   future-bar inputs, current-data backfill, and guessed sector membership fail closed.
3. Every required field above must be present and identity-stable. A missing,
   stale, duplicate, conflicting, or unrecoverable input produces an explicit
   failure and no canonical output.
4. The generated output must carry the B strategy/spec identity, T/T+1 identity,
   input fingerprint, and output hash. Re-running the same complete identity must
   be byte-identical; a different identity must not overwrite the prior output.
5. The first instance must be audited at the next
   `FROZEN_CANDIDATE_PREREQUISITES` decision point. Until then, the project remains
   at `development candidate` and no paper/live promotion is implied.

## Explicit non-creation

No live T-close package, prospective payload, canonical watchlist, or future output
has been fabricated by this task. The only remaining prerequisite blocker is the
first real prospective T-close input instance described above.
