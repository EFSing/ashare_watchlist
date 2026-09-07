# Candidate-Bound Prospective Input / Provenance Contract V3

更新时间：2026-09-07（Asia/Shanghai）

## Contract identity

- contract：`CANDIDATE_BOUND_PROSPECTIVE_INPUT_PROVENANCE_CONTRACT_V3`
- status：`FRESH_T_CLOSE_INSTANCE_VERIFIED_A__FROZEN_PREREQUISITES_READY_FOR_USER_DECISION`
- bound candidate：`B_BREAKOUT_RETEST_LEGACY_V1_1`
- strategy spec SHA-256：`f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd`
- supersedes for future live packages：`CANDIDATE_BOUND_PROSPECTIVE_INPUT_PROVENANCE_CONTRACT_V2`

V1 and V2 remain historical governance evidence and are not rewritten. V3 binds the
corrected, explicitly versioned B reconstruction created after the exact V0 source
identity and sector semantics were resolved. The original `CONTRACT_DEFINED_NO_LIVE_INSTANCE`
status was true at the 2026-09-01 declaration and is superseded by the 2026-09-03 verified
instance recorded below. This does not create a `FROZEN_CANDIDATE_CONTRACT_V1`.

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

## Current instance status — 2026-09-07

Gate A is satisfied by the 2026-09-03 package at
`data/prospective_inputs/20260903/2026-09-03_eeb700c98a69a98fae3fa220851190a76de88984b0f451cc1ed275b2e487351f.json`.
The package schema is `CANDIDATE_BOUND_LIVE_INPUT_PACKAGE_V4`, its immutable file SHA-256 is
`a2e6da0865ff20316e4d9074f26e2cb3ba53995d2cb3e83a49f8c82988c0b38a`, its content SHA is
`0b1216e5c5855343dba02853eb17e9dbc43c97d50120ac7490da43eaa78cdf86`, and its generation
fingerprint is `eeb700c98a69a98fae3fa220851190a76de88984b0f451cc1ed275b2e487351f`.
The package is bound to B spec
`f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd`; T is
`2026-09-03`, retrieval was after the `15:00` XSHG close, and earliest execution is
`2026-09-04`. Universe, quote, stock Kline, index Kline, sector resolution, symbol identity,
and generation-manifest quality checks are all `PASS`.

This proves the existence and timing of the first live candidate-bound input instance. It
does not prove gate B (`FULLY_RECOVERABLE`): 170 raw/sidecar pairs retain
`code_git_sha=UNKNOWN_ORIGIN`, and the package/source-evidence bytes have no verified
persistent external backup/readback. The existing Drive readback is the corrected 11-name
watchlist only, not the input package. No strategy, threshold, evaluator, or frozen artifact
identity is changed by this status correction.

## Superseding current instance status — 2026-09-07 fresh post-close capture

The 2026-09-07 XSHG post-close run is the current candidate-bound `LIVE_OBSERVED` instance. It
uses acquisition code SHA `39cbd7cf2335ebee1cc7a81faee47c744c737fc3` and the clean evidence root
`data/t_close_evidence/20260907_clean_39cbd7cf2335ebee1cc7a81faee47c744c737fc3/20260907`.
All 10,677 raw/sidecar pairs are complete and byte/hash exact; all sidecars carry that exact
runner SHA; new `UNKNOWN_ORIGIN=0`. The old 2026-09-07 partial root remains preserved as failed
audit evidence and is not mixed into this package.

The package is
`data/prospective_inputs/20260907/2026-09-07_fe54be9be5c5959bd3d690adab2423e7a89f19e4498fb1df927c142f8dab9e4c.json`,
schema `CANDIDATE_BOUND_LIVE_INPUT_PACKAGE_V4`, status `READY_FOR_STRATEGY_EVALUATION`, file
SHA-256 `63fa8effea45cc329035dd97dbe64dfe9d84e899fbb24623190143811e08cc3`, content SHA-256
`792442ff35b5f1e5858180d3e6fc8965c661e4fd6e0c3abd5f9247d90dd6e31e`, and generation
fingerprint `fe54be9be5c5959bd3d690adab2423e7a89f19e4498fb1df927c142f8dab9e4c`. B remains
`B_BREAKOUT_RETEST_LEGACY_V1_1`; raw qualified=26, ST excluded=1, final non-ST=25; the
2026-09-07 watchlist SHA-256 is
`5a99273b6304621acbf7bba2423a6e372668348a31ac436021caf5f5855db100`.

The package and source-evidence archives are persistently backed up in the authorized private
Drive target `ashare_watchlist/t_close_20260907_v3_39cbd7cf`. Its formal chunks40 inventory
contains 14 package chunks, 15 source-evidence chunks, and one manifest. Every binary chunk was
independently raw-fetched and matched manifest byte length and SHA-256; the manifest itself was
also exact-readback verified. Thus the recovery checks are `PASS / READY_FOR_USER_DECISION`.
This does not create `FROZEN_CANDIDATE_CONTRACT_V1` or automatically freeze the candidate.
