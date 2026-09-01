# Candidate-Bound Prospective Input / Provenance Contract V1

更新时间：2026-08-31（Asia/Shanghai）

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
| universe | exact T-date universe identity, source/version, explicit `TRADABLE_UNIVERSE_SCOPE_V1 = SH_SZ_A_SHARE_ONLY`, as-of date, file/content SHA and row identity |
| sector semantics | explicit historical membership/taxonomy status; no current-data backfill or substitute taxonomy |
| names | exact raw display-name values are retained for audit; comparison uses the fixed `DISPLAY_NAME_NORMALIZATION_NFKC_TRIM_EXPLICIT_ZERO_WIDTH_V1` rule; missing or substantively conflicting names fail closed |
| market_env | canonical T-date market-environment identity and source/provenance |
| provider/version | provider name, API/data version, acquisition timestamp, and dependency/runtime versions |
| calendar | XSHG calendar identity, `Asia/Shanghai`, session-close evidence and T+1 session identity |
| availability/fail-closed | completeness, freshness, duplicate/conflict checks, and explicit failure status when unavailable |
| recovery | recoverable input package, byte/content hashes, recovery status and deterministic retry identity |
| generation fingerprint/output identity | fingerprint binds all output-affecting inputs, candidate identity, schema/contract versions, and canonical output bytes/SHA |

## Live provider resolution policy

For this candidate-bound live path, the provider identities are explicit and part of
the input manifest:

- universe and display names: HiThink Financial-API metadata/tickers list, primary;
  current live scope is SH/SZ A-share only; BJ is explicitly excluded and its absence is
  not incomplete coverage. The scope/version participates in input and generation identity;
  adding BJ requires a new scope/version.
- stock K line: HiThink Financial-API historical `adjust=forward`, primary;
- index K line: HiThink Financial-API historical index endpoint, unadjusted and marked
  `PROVIDER_RAW_SNAPSHOT`;
- quotes: Tencent snapshot, retaining the existing quote-field semantics;
- sector: AkShare `stock_sector_spot(indicator="新浪行业")` plus
  `stock_sector_detail`, exact V0 Sina-industry taxonomy only.

Tencent K-line fallback is allowed only under the versioned
`LIVE_MARKET_DATA_FAILOVER_POLICY_V1` / `TENCENT_QFQ_FALLBACK_V1` policy. A fallback
must be recorded as `EXPLICIT_FALLBACK` in provider metadata and in the resolved
manifest provider identity. It is not an implicit taxonomy or data substitution;
universe, exact Sina sector, schema, date, coverage, and conflict failures remain
fail-closed.

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

Display-name normalization is deliberately limited to Unicode NFKC, removal of the
explicit zero-width formatting code points `U+200B`, `U+200C`, `U+200D`, `U+2060`, and
`U+FEFF`, and trimming leading/trailing whitespace. It does not remove `ST`/`*ST`, A/B
markers, interior whitespace, suffixes, or other substantive characters. The raw universe
and sector values remain in the package audit data; the normalization version is part of
the candidate-bound generation identity and provenance.

## Explicit non-creation

No live T-close package, prospective payload, canonical watchlist, or future output
has been fabricated by this task. The only remaining prerequisite blocker is the
first real prospective T-close input instance described above.
