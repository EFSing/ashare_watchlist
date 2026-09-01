# Candidate-Bound Prospective Input / Provenance Contract V3

更新时间：2026-09-01（Asia/Shanghai）

## Contract identity

- contract：`CANDIDATE_BOUND_PROSPECTIVE_INPUT_PROVENANCE_CONTRACT_V3`
- status：`CONTRACT_DEFINED_NO_LIVE_INSTANCE`
- bound candidate：`B_BREAKOUT_RETEST_LEGACY_V1_1`
- strategy spec SHA-256：`f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd`
- supersedes for future live packages：`CANDIDATE_BOUND_PROSPECTIVE_INPUT_PROVENANCE_CONTRACT_V2`

V1 and V2 remain historical governance evidence and are not rewritten. V3 binds the
corrected, explicitly versioned B reconstruction created after the exact V0 source
identity and sector semantics were resolved. It does not create a live package or
`FROZEN_CANDIDATE_CONTRACT_V1`.

## Candidate and source identity

The candidate is bound to the following immutable source tuple:

- repository：`EFSing/ashare_watchlist-V0`
- commit：`c8406c393c0b135eafb0aec763576ae869fddcff`
- path：`ashare_watchlist/scripts/screen_system.py`
- raw/LF file SHA-256：`843935d9b86ec05af848ee8cc54812334475e3d17807cb93349a02c84896417a`
- historical Windows CRLF working-tree witness：`6cac746123e3151999cbeeb1a612868ef77b50af6c7c64b0d80eb387ae1d19f9`

The historical V1 declaration with a 63-character CRLF value remains recorded as a
transcription error; it is not silently rewritten. The corrected candidate has its
own strategy version and spec hash.

## Required identity and timing policy

V3 retains the V2 symbol-authoritative display-name policy:

- exact six-digit symbol is the security identity within
  `TRADABLE_UNIVERSE_SCOPE_V1 = SH_SZ_A_SHARE_ONLY`;
- HiThink and exact Sina raw names are retained independently and normalized only for
  diagnostics using `DISPLAY_NAME_NORMALIZATION_NFKC_TRIM_EXPLICIT_ZERO_WIDTH_V1`;
- names do not create aliases, joins, filters, or universe reductions;
- missing/empty names, provider schema failures, provider request failures, and
  identity conflicts fail closed;
- signal inputs are observed at T close, `known_at <= T`, with execution at the next
  valid XSHG session; current data cannot backfill a prior T date.

## Corrected B sector boundary

The executable B path uses the exact V0 sector behavior:

- permitted source is exact Sina `stock_sector_spot(indicator="新浪行业")` followed by
  `stock_sector_detail`;
- an absent symbol membership resolves to `sector_name="-"`, `sector_rank=50`,
  `sector_chg=0.0`, and continues B evaluation;
- multiple memberships resolve by
  `LEGACY_PROVIDER_ORDER_LAST_WRITE_WINS_V1`: spot label order, then detail member
  row order; the final valid observed membership wins;
- raw sector rows, provider traversal order, outside-scope memberships, duplicate
  diagnostics, and the resolved mapping are retained and included in provenance /
  generation identity;
- exact provider taxonomy is not replaced with EM/THS/SW or another taxonomy; the
  tradable universe is not shrunk to sector coverage; no current snapshot is used to
  fill historical inputs;
- complete sector coverage is not an additional hard gate because V0 explicitly had a
  missing-symbol fallback. Provider failures, invalid observed fields, and unresolved
  package identity still fail closed.

The corrected package quality check is
`sector_membership_resolved_exact_v0`. An unresolved ambiguous membership count must
remain zero; a resolved multi-membership count and symbol list are diagnostic and are
resolved under the explicit provider-order policy.

## Package and recovery boundary

The first acceptable instance must be a new real `LIVE_OBSERVED` T-close package with
`known_at <= T`, current provider/version metadata, XSHG calendar evidence, deterministic
input/generation/output hashes, and recoverable package bytes. Failed acquisition does
not persist a formal package or canonical output. This contract does not authorize
Phase 2F, C evaluation, parameter selection/tuning, promotion, Final OOS access, or
automatic freezing.
