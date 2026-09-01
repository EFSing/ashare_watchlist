# B corrected reconstruction and eligibility impact — 2026-09-01

## Scope and classification

本次是 `correctness blocker` + `product blocker` closure。目标是解决 exact V0
identity / semantic mismatch，并判断已有 B eligibility evidence 是否受影响；不是
新的 strategy research，不启动 C、Phase 2F、调参、promotion、Final OOS 或 T-close
acquisition。

## Decision

`ADOPT_AUTHORITATIVE_RAW_V0_SOURCE_AND_CREATE_CORRECTED_B_RECONSTRUCTION`

The historical `B_BREAKOUT_RETEST_LEGACY_V1` remains immutable retrospective evidence,
but its identity/spec is not used as the authoritative exact-V0 reconstruction because
its source SHA declaration was transcribed at 63 characters and its inherited sector
text did not preserve the V0 missing-sector behavior. A new versioned candidate is used:

- strategy：`B_BREAKOUT_RETEST_LEGACY_V1_1`
- role：`CORRECTED_EXACT_V0_RECONSTRUCTION`
- supersedes：`B_BREAKOUT_RETEST_LEGACY_V1` for future candidate-bound work only
- spec SHA-256：`f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd`
- source tuple：`EFSing/ashare_watchlist-V0@c8406c393c0b135eafb0aec763576ae869fddcff`,
  `ashare_watchlist/scripts/screen_system.py`, raw/LF SHA
  `843935d9b86ec05af848ee8cc54812334475e3d17807cb93349a02c84896417a`

The historical CRLF witness is the valid 64-character value
`6cac746123e3151999cbeeb1a612868ef77b50af6c7c64b0d80eb387ae1d19f9`; the old 63-character
declaration is classified as `HISTORICAL_SOURCE_SHA_TRANSCRIPTION_ERROR` and is not
overwritten.

## Semantic parity decision

The corrected spec explicitly records the V0 semantics and reuses only the already
audited numeric B calculator:

- first qualifying breakout in the 15-session scan is the only breakout candidate;
  the first qualifying breakout's pullback failure ends evaluation;
- breakout, pullback, volume, strength, support, stop, risk/reward, overhang and hard
  gate ordering remain the fixed V0 rule;
- missing sector is `("-", 50, 0.0)` and continues evaluation;
- multiple memberships use provider traversal last-write-wins, with raw membership
  rows retained and provenanced;
- score components remain qualified-only and there is no score cutoff or TOP-N
  selection.

Decision: `B_CORRECTED_RECONSTRUCTION_SEMANTICS_ADOPTED`.

## Eligibility impact audit

The existing frozen development input and old event bytes were not overwritten. The
impact audit used exact shared callable identity for the sector-independent numeric
projection, then checked the existing event-artifact membership. It intentionally did
not construct outcomes or read forward returns. This is a structural parity proof for
the actual eligibility call path, not a new return replay.

Evidence is recorded in
[`b_reconstruction_impact_audit.json`](../data/validation/strategy_candidate_eligibility_v1_1/b_reconstruction_impact_audit.json):

- frozen continuous input：769 sessions, 2023-06-30 through 2026-08-28;
- evaluated symbol-dates：4,041,140;
- old event count：17,714；corrected event count：17,714;
- projection differences：0；status differences：0；event-membership differences：0;
- candidate threshold crossings：0, because both identities have no score cutoff or
  TOP-N selection;
- historical sector missing/multi counts：`NOT_AVAILABLE_IN_FROZEN_DEVELOPMENT_INPUT`,
  because the CORE replay intentionally carries no historical sector membership and
  the neutral sentinel is outside the numeric projection.

Decision: `ELIGIBILITY_ARTIFACT_EVENT_SET_INVARIANT` and
`EXISTING_B_ELIGIBILITY_ARTIFACT_AFFECTED=FALSE` for the existing eligibility event set.
No returns regeneration is required for the existing development outcome evidence;
the old artifact remains a historical artifact and is not relabeled or overwritten.

The corrected candidate therefore retains the fixed eligibility decision:
`CORRECTED_B_CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES`. This does not mean frozen
candidate, production promotion, paper/live use, or Final OOS evidence.

## Remaining gate and exclusions

The active next gate remains the first legitimate candidate-bound
`LIVE_OBSERVED` T-close package under V3 with `known_at <= T`, complete package
provenance, exact source identity, and fail-closed recovery checks. No package was
created by this reconstruction/audit. C, Phase 2F, tuning, parameter selection,
promotion, Final OOS access, and automatic freeze remain out of scope.
