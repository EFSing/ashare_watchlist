# B candidate identity and reconstruction provenance — 2026-09-01

This is a governance/correctness closure record. It does not modify the B
evaluator, B spec, candidate-bound live contract, thresholds, or frozen
eligibility artifact. It does not run T-close acquisition, replay, Final OOS,
parameter selection, C, Phase 2F, or promotion.

## Decision summary

```json
{
  "decision": "B_CANDIDATE_IDENTITY_UNRESOLVED",
  "task_classification": ["correctness_blocker", "product_blocker"],
  "v0_source_identity": {
    "repository": "EFSing/ashare_watchlist-V0",
    "remote_ref": "refs/heads/main",
    "commit": "c8406c393c0b135eafb0aec763576ae869fddcff",
    "path": "ashare_watchlist/scripts/screen_system.py",
    "git_object_format": "sha1",
    "commit_parent_count": 0,
    "git_blob_oid": "ede1ee62451fa9b817bf390ab75e963115a678dc",
    "raw_blob_byte_length": 21770,
    "raw_blob_sha256": "843935d9b86ec05af848ee8cc54812334475e3d17807cb93349a02c84896417a",
    "lf_normalized_sha256": "843935d9b86ec05af848ee8cc54812334475e3d17807cb93349a02c84896417a",
    "crlf_checkout_variant_sha256": "6cac746123e3151999cbeeb1a612868ef77b50af6c7c64b0d80eb387ae1d19f9",
    "declared_candidate_source_sha256": "6cac746123e315199cbeeb1a612868ef77b50af6c7c64b0d80eb387ae1d19f9",
    "declared_candidate_source_sha256_length": 63,
    "declared_sha_matches_raw_or_crlf": false,
    "working_tree_sha256": null,
    "working_tree_checked_out": false,
    "identity_status": "V0_SOURCE_FILE_IDENTITY_UNVERIFIED_DECLARED_SHA_MISMATCH"
  },
  "canonical_v0_source_tuple": {
    "repository": "EFSing/ashare_watchlist-V0",
    "commit": "c8406c393c0b135eafb0aec763576ae869fddcff",
    "path": "ashare_watchlist/scripts/screen_system.py",
    "raw_file_sha256": "843935d9b86ec05af848ee8cc54812334475e3d17807cb93349a02c84896417a"
  },
  "declared_candidate_source_sha_basis": "unresolved; CRLF variant found but declared value does not match",
  "b_spec": {
    "path": "scripts/b_breakout_retest.py:LEGACY_SPEC",
    "creating_commit": "4e685ba28668ada29f78e6fa4a56be1cacc259ea",
    "creating_commit_parent": "005fa552b046ee35d35f51e0c7da430a9dc17fbe",
    "creating_pr": 14,
    "semantic_sha256": "5bbeb345ebd8883149138d2f29f8606f919949ae285aa2839fa337921dfc7112",
    "creation_method": "copy.deepcopy(A_LEGACY_SPEC) plus B-specific overrides"
  },
  "eligibility": {
    "artifact_affected": "UNRESOLVED",
    "artifact_semantically_invariant": "UNRESOLVED",
    "impact_audit_performed": false,
    "regeneration_required": "UNRESOLVED"
  }
}
```

The raw Git bytes do not equal the historical declaration `6cac…`. LF-to-CRLF
conversion produces a valid 64-character SHA-256 beginning with the same prefix,
but the exact result is
`6cac746123e3151999cbeeb1a612868ef77b50af6c7c64b0d80eb387ae1d19f9`, while the
repository declaration is a 63-character value,
`6cac746123e315199cbeeb1a612868ef77b50af6c7c64b0d80eb387ae1d19f9`. The
declared value is therefore not verified by raw bytes or the tested CRLF
variant. The Git blob OID is a separate SHA-1 identity and is not a file
SHA-256. The declaration is not changed here.

## 1. V0 repository and byte identity

The V0 remote is `EFSing/ashare_watchlist-V0`; its `main` ref currently points
to `c8406c393c0b135eafb0aec763576ae869fddcff`. The commit is a root commit
with no parent and contains the exact path
`ashare_watchlist/scripts/screen_system.py`. The current repository also has
that immutable commit object, but no branch containing it; this is consistent
with an imported source object rather than current-repository ancestry.

The exact object audit is:

| Identity layer | Exact result |
| --- | --- |
| Git repository object format | `sha1` |
| Git blob OID | `ede1ee62451fa9b817bf390ab75e963115a678dc` |
| Raw blob bytes | 21,770 bytes |
| SHA-256 of raw Git blob bytes | `843935d9b86ec05af848ee8cc54812334475e3d17807cb93349a02c84896417a` |
| LF-normalized SHA-256 | `843935d9b86ec05af848ee8cc54812334475e3d17807cb93349a02c84896417a` |
| CRLF-converted SHA-256 | `6cac746123e3151999cbeeb1a612868ef77b50af6c7c64b0d80eb387ae1d19f9` |
| Existing declared candidate SHA-256 | `6cac746123e315199cbeeb1a612868ef77b50af6c7c64b0d80eb387ae1d19f9` (63 chars; not equal) |
| Raw line-ending state | 472 LF, 0 CRLF, 0 bare CR |
| Working-tree bytes | not checked out; no working-tree SHA claimed |

The repository/commit/path is established, and the raw source bytes are
reproducible, but the declared candidate file SHA is not verified. The
canonical raw-source tuple found for comparison is:

```text
EFSing/ashare_watchlist-V0
+ c8406c393c0b135eafb0aec763576ae869fddcff
+ ashare_watchlist/scripts/screen_system.py
+ 843935d9b86ec05af848ee8cc54812334475e3d17807cb93349a02c84896417a
```

The historical candidate declaration remains unchanged. A separate governance
decision is required to identify the intended 64-character value or to issue a
new candidate/spec identity. No spec hash is rewritten in this closure.

## 2. B spec creation lineage

The provenance chain is:

```text
V0 source
  -> A common semantic spec in scripts/a_platform_breakout.py
  -> B LEGACY_SPEC in scripts/b_breakout_retest.py
  -> B evaluator / numeric projection
  -> STRATEGY_DEVELOPMENT_ELIGIBILITY_V1 generator
```

The common A semantic spec was introduced in commit
`297f7f4e50b20a60875df46868a4e50d3d0024ad` (PR #4). Its
`input_contract.sector_evidence` already declared
`silent_fallback=False` and `missing_status=INSUFFICIENT_DATA`; this was part
of A's generic hardened evaluator/spec, not a B-specific V0 extraction.

PR #14 introduced `scripts/b_breakout_retest.py` in squash commit
`4e685ba28668ada29f78e6fa4a56be1cacc259ea` (parent
`005fa552b046ee35d35f51e0c7da430a9dc17fbe`). At module load it creates the
machine-readable spec object with:

```python
LEGACY_SPEC = copy.deepcopy(A_LEGACY_SPEC)
```

It then replaces the identity, adds `legacy_source`, removes `a_match`, adds
`b_match`, changes the B setup score increment to `B_setup:+2`, and replaces
the status vocabulary. It does not override `input_contract.sector_evidence`,
`hard_gates_in_order`, `support_stop_risk`, `volume_price_distribution`,
`target_rr_trigger`, or the other shared fields. The resulting object is
`scripts/b_breakout_retest.py:LEGACY_SPEC` and its runtime semantic SHA is
`5bbeb345ebd8883149138d2f29f8606f919949ae285aa2839fa337921dfc7112`.

The B source is byte-identical between PR #14's creating commit and this
closure HEAD; the A source is also unchanged over that interval. The
eligibility generator introduced in the same PR calls
`evaluate_numeric_projection()` for every candidate and uses the full
manifest evaluator only for the fixed sample parity check. It does not create
a second B spec or dynamically load sector semantics.

## 3. Exhaustive V0-versus-B semantic matrix

`MATCH` means the B reconstruction expresses the same V0 rule. `SPEC_ADDED_NOT_IN_V0`
means an audit/provenance wrapper was added without changing the V0 accepted
numeric path. `SPEC_CHANGED_FROM_V0` means the B spec changes the V0 behavior.
`UNRESOLVED` means the current B spec does not define the case, even though a
current evaluator behavior can be observed.

| Semantic field | Exact V0 source behavior | Current B spec/evaluator | Classification |
| --- | --- | --- | --- |
| Breakout search window | `range(max(61,n-15), n-1)` | Same expression in `b_match.scan_window` and `_b_match` | `MATCH` |
| Breakout base/high | `max(close[i-60:i])`; require `close[i] > base_hi` | Same | `MATCH` |
| Breakout volume/change | `volume[i] >= 1.8*mean(volume[i-20:i])`; one-day change `>= 3%` | Same | `MATCH` |
| First qualifying breakout | Stop at first breakout satisfying the three breakout gates | `first_qualifying_breakout_only=true`; same unconditional return/break behavior | `MATCH` |
| Pullback timing/window | Mean `volume[i+1:]`, with `volume[-1]` fallback when only one later bar exists | Same expression in `b_match.pullback.pull_volume` and `_b_match` | `MATCH` |
| Pullback price | `abs(close/base_hi-1)<=4%` or `base_hi*0.97 <= close <= base_hi*1.04`, plus `close >= base_hi*0.97` | Same | `MATCH` |
| Pullback volume | Pullback mean `< breakout volume * 0.7` | Same | `MATCH` |
| Turn strength | `close >= close[-2]` or `close >= ma5` | Same | `MATCH` |
| Numeric hard gates | `close>2`; acceleration/gain vetoes; support/stop/risk; pressure or 2.5R target; `rr>=2`; overhang/RR veto | Same shared hard gates, support, target and RR expressions | `MATCH` |
| 85-score components | Same V0 scoring; B setup receives `+2` in volume-price health | Same eight components; B override explicitly uses `B_setup:+2` | `MATCH` |
| Final score threshold / TOP-N | V0 does not filter by score or TOP-N | `score_cutoff=None`, `top_n=None` | `MATCH` |
| Missing sector | `sec_map.get(code, "-")`; continue evaluation | Missing evidence returns `INSUFFICIENT_DATA` before array evaluation | `SPEC_CHANGED_FROM_V0` |
| Multiple sector membership | Mapping assignment means provider traversal `last-write-wins` | No spec field; evaluator returns the first valid traversed record if an ambiguous manifest bypasses adapter | `UNRESOLVED` |
| Default sector tuple | `("-", 50, 0.0)` | No default tuple; strict missing-evidence status instead | `SPEC_CHANGED_FROM_V0` |
| Candidate output status | Accepted rows are returned as dictionaries; rejected/non-selected paths return no row; no status vocabulary | Adds `NOT_MATCHED`, `MATCHED_REJECTED`, `INSUFFICIENT_DATA`, `QUALIFIED_LEGACY_BASELINE` audit statuses | `SPEC_ADDED_NOT_IN_V0` |

The V0 evidence is on the actual B execution path: `get_sectors()` iterates
spot `label`, calls `stock_sector_detail()` for each label, assigns
`mapping[str(c).zfill(6)] = name`, and the main loop uses `sec_map.get(code,
"-")` before calling `analyze()`. Thus the sector difference is not a
misread of an unused helper or another strategy path.

## 4. Why the sector divergence occurred

The semantic evidence points toward Case A, but the requested Case A rule also
requires verified source provenance. That prerequisite is not met because the
declared V0 source SHA is invalid/unmatched. Therefore the fail-closed final
candidate classification for this task is Case C:

1. The nomination documents repeatedly call B an exact V0 reconstruction and
   record the exact V0 source. The pre-returns nomination commits
   `08aa5ff0f88d19171969c6429f3ee00a3f6b4363` and
   `20bada2d70c6323a8b8fd6cf56414f5cf638957d` describe the exact B formula and
   sector sentinel/record compatibility; neither adopts a stricter B-specific
   missing-sector rule.
2. The actual V0 source path uses the default tuple and provider-order
   last-write-wins semantics described above.
3. PR #14's B file is created by copying A's already-hardened spec and does
   not modify its sector evidence block. The B-specific overrides are visible
   and limited to identity, legacy-source metadata, B match, B score increment,
   and status vocabulary.
4. The PR #14 commit message lists the squashed research and provenance work,
   but its code, nomination, eligibility report, and B tests contain no
   explicit pre-returns decision adopting a stricter B sector rule. The tests
   pin the semantic hash and exercise B numeric/pullback behavior; they do not
   test missing or multiple sector membership.

The source/history evidence still records a likely semantic divergence: the
PR #14 B spec mechanically inherited generic hardening that conflicts with the
simultaneous `exact legacy reconstruction` claim. It is not promoted to a final
Case A decision while the source identity declaration remains unresolved:

```text
B_CANDIDATE_IDENTITY_UNRESOLVED
```

This classification does not authorize a repair or the eligibility impact
audit. The current B spec SHA, evaluator, thresholds, and old artifact remain
untouched pending Sol/user decision.

## 5. Eligibility impact audit is blocked

The mandated eligibility impact audit is not entered because Case A or Case B
has not been established. No new dataset was loaded, no Final OOS was read, and
no eligibility replay or returns computation was rerun.

The existing artifact is retained as historical evidence, but its impact status
remains unresolved:

| Item | Result |
| --- | --- |
| `EXISTING_B_ELIGIBILITY_ARTIFACT_AFFECTED` | `UNRESOLVED` |
| `ELIGIBILITY_ARTIFACT_SEMANTICALLY_INVARIANT` | `UNRESOLVED` |
| `ELIGIBILITY_ARTIFACT_REGENERATION_REQUIRED` | `UNRESOLVED` |
| Old bytes | retained; not superseded or overwritten |

The structural call-path audit and requested difference counters must wait for
the source/candidate identity decision. No count is fabricated from the
unverified identity.

The exact stop state is:

```text
EXISTING_B_ELIGIBILITY_ARTIFACT_AFFECTED = UNRESOLVED
```

## 6. Stop and next decision node

Current formal status remains `development candidate`. `Final OOS` remains
`SEALED / UNREAD`; formal `LIVE_OBSERVED` capture remains `NOT_RUN` for this
task. No B evaluator/spec/contract/threshold/artifact was modified.

The next true decision node is Sol/user review of the unresolved source
declaration. Missing evidence is one of: the correct historical 64-character
source SHA, a documented historical source copy/canonicalization that yields
the declared value, or an explicit decision to bind the candidate to the raw
Git source SHA. Until then the semantic Case A/B choice and eligibility impact
audit remain blocked:

```text
B_CANDIDATE_IDENTITY_UNRESOLVED
```

Only after that decision may a separately versioned correction decide how to
represent exact V0 sector fallback and multi-sector semantics. Such a repair
must not mutate the existing `5bbeb345…` spec identity or overwrite the old
eligibility artifact. If the source identity is verified and no pre-returns
intentional stricter B definition is produced, the semantic evidence can be
re-entered as Case A review; no such pre-returns evidence was found so far.
