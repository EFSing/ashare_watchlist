# Strategy Candidate Nomination / Development Eligibility V1 Report

Date: 2026-08-30 (Asia/Shanghai)  
Formal Delivery Ladder: `development candidate`  
Protocol: `STRATEGY_DEVELOPMENT_ELIGIBILITY_V1`

## Final B decision

`CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES`

The only nomination remains:

`NOMINATE_B_BREAKOUT_RETEST_LEGACY_V1_FOR_DEVELOPMENT_ELIGIBILITY`

B exact reconstruction was complete before any B returns were read. The fixed
eligibility rule was frozen before the returns read and was not changed afterward:

`ELIGIBILITY_RULE_FROZEN_BEFORE_B_RETURNS_READ = true`

The prior environment stop is recorded with the corrected vocabulary:

- status: `CANDIDATE_ELIGIBILITY_BLOCKED_ENVIRONMENT`
- reason: `B_ELIGIBILITY_NOT_EXECUTED_MISSING_PARQUET_READER`

That stop was an execution-environment failure. It was not a B performance
rejection, not evidence of no reproducible rule, and not a C rejection. After the
declared environment was installed, the same single fixed B evaluation completed.

## Environment and frozen input verification

| Item | Verified value |
| --- | --- |
| Python | `3.12.13` |
| pandas | `2.2.3` |
| parquet engine | `pyarrow==17.0.0` |
| install | `python -m pip install -e ".[test,research]"` |
| registry | `FROZEN_ARTIFACT_REGISTRY_V1`, 13/13 required artifacts verified |
| daily_k exact SHA-256 | `61189a4850e2eb157453e28e5375e502e20d214508bbe70ea71066ca3e05e426` |
| raw source content SHA-256 | `68d10afc4a0e3341c124f8a5e896292faf8ca271ab15cfbb7ac55fe485db8ccb` |
| CORE projection stream SHA-256 | `882b8925e787d67d7035de07f91cd3c941b7394661bd32d5d534cc62e3996c1b` |
| CORE projection file SHA-256 | `0d23cf54843920f5fdcc05847e4b78c5d605b05c8793f878b6021c85b3ab0c2f` |
| continuous CORE manifest semantic SHA-256 | `8209c6b252954530a216e85ef063f0594efb050ee9b9abe3e26f8534f97c0e9b` |
| root checkpoint file SHA-256 | `22f7ac7515ef2177f49fbcb316b33945c31132fe8a3b3dc360b1161ccf2256a3` |
| checkpoint identity | complete 769-session replay; `return_metrics_computed=false` |

Any mismatch was a stop condition. No frozen parquet bytes were modified.

## Candidate reconstruction identity

Candidate: `B_BREAKOUT_RETEST_LEGACY_V1`  
V0 source commit: `c8406c393c0b135eafb0aec763576ae869fddcff`  
V0 source file SHA-256: `6cac746123e315199cbeeb1a612868ef77b50af6c7c64b0d80eb387ae1d19f9`  
Canonical strategy spec SHA-256: `5bbeb345ebd8883149138d2f29f8606f919949ae285aa2839fa337921dfc7112`
Implementation: [`scripts/b_breakout_retest.py`](../scripts/b_breakout_retest.py)

Exact reconstruction, semantic hash, edge behavior, numeric projection and parity
tests passed. B retains the V0 first qualifying-breakout scan and unconditional
break behavior. C was not evaluated.

## Fixed B replay results

Scope: `DEVELOPMENT` / `RECONSTRUCTED_RETROSPECTIVE`, 769 signal sessions from
2023-06-30 through 2026-08-28, 4,041,140 candidate evaluations, T+1 XSHG open
entry. Future corporate actions were used only for ex-post outcome measurement.

| Horizon | Available N | Positive rate | Mean return | Median return | Mean MFE | Median MFE | Mean MAE | Median MAE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1D | 17,689 | 48.6065% | +0.1857% | 0.0000% | +2.2477% | +1.4379% | -1.7401% | -1.3239% |
| 3D | 17,635 | 48.7950% | +0.4335% | -0.0424% | +4.2894% | +2.7451% | -3.1110% | -2.3029% |
| 5D | 17,602 | 48.6252% | +0.6808% | -0.1137% | +5.8392% | +3.7030% | -4.0632% | -3.0155% |
| 10D | 17,558 | 51.6403% | +1.4603% | +0.3226% | +8.9776% | +5.6893% | -5.7403% | -4.3573% |

Event N (qualified B events): **17,714**.

### Year robustness, primary 10D

| Signal year | Available 10D N | Positive rate | Mean 10D return |
| --- | ---: | ---: | ---: |
| 2023 | 2,587 | 37.2632% | -0.8380% |
| 2024 | 6,177 | 60.5472% | +3.2352% |
| 2025 | 6,684 | 53.1418% | +1.5428% |
| 2026 | 2,110 | 38.4360% | -1.1795% |

Robust years: **4** (each has at least 10 events). Positive-mean robust years:
**2** (2024 and 2025).

### Signal concentration

- qualified unique symbols: `4,454`
- top-1 symbol share: `0.1186%`
- top-5 symbol share: `0.5758%`
- qualified-symbol HHI: `0.00035472`

## Fixed eligibility gate audit

| Gate | Frozen requirement | Result |
| --- | --- | --- |
| exact reconstruction / manifest parity | exact B identity and all sampled manifest projections pass | PASS; 1,538/1,538, parity SHA `bd19b7c65f934dc9b60fbe78fe9919bc41406a9eec96e0cf81224efc075437d9` |
| total events | >= 30 | PASS; 17,714 |
| available per horizon | each >= 30 | PASS; minimum 17,558 |
| primary horizon | 10D | PASS |
| 10D positive rate | >= 50% | PASS; 51.6403% |
| 10D mean return | > 0 | PASS; +1.4603% |
| 10D median return | > 0 | PASS; +0.3226% |
| robust years | >= 3 years with >= 10 events | PASS; 4 |
| positive robust-year means | >= 2 | PASS; 2 |

The thresholds above are frozen and are not eligible for post-result adjustment.
No parameter sweep, threshold search, TOP-N optimization, Phase 2F, C returns,
Final OOS read, or production-rule change occurred.

## Frozen research artifacts

- event artifact: `data/validation/strategy_candidate_eligibility_v1/b_breakout_retest_eligibility_events.jsonl.gz`
  - rows: `17,714`; bytes: `2,506,292`
  - file SHA-256: `8940a4a346ac6911ba669f84a9ceba7ef878b0ed0ce51edf673439b52aa056b9`
  - semantic/content SHA-256: `a16e48dfbe8a93f64d8bf1bad6e00d3eaf32c10fd60eed09dc5574247b8119bc`
- eligibility manifest: `data/validation/strategy_candidate_eligibility_v1/strategy_development_eligibility_manifest.json`
  - bytes: `367,674`
  - file SHA-256: `5e0a557c1930de7b4f182f09f43b45c0c11b19b2d7c992bf9e7fa7e6cc6de048`
  - semantic manifest SHA-256: `f79ec9baa494f2f0256843c2540988bd25c94269ed9a1fd4ada228759bd8e0a2`
  - content SHA-256: `e754787836b28316430278372ab2d84817091d4608da394f9207f695a4c27aee`

The manifest provenance was deterministically rematerialized after correcting path
canonicalization. All recorded paths are stable repo-relative logical paths; no
absolute/local path participates in the manifest semantic/content identity. A single
reproducibility verification with the same frozen inputs and fixed protocol produced
the same event bytes, event identities, event count, metrics, fixed gates and decision;
it was not a second candidate-selection experiment.

## Candidate-bound prospective path and final stop

B eligibility is complete and eligible. The contract is defined in
[`candidate_bound_prospective_input_contract_v1.md`](candidate_bound_prospective_input_contract_v1.md)
and binds the B strategy/spec SHA, T close/T+1, universe, sector semantics, names,
market_env, provider/version, calendar, availability/fail-closed, recovery and
generation/output identity.

No prospective live instance has been fabricated. Rejudged
`FROZEN_CANDIDATE_PREREQUISITES` status:

- decision: `FROZEN_CANDIDATE_BLOCKED`
- sole remaining P1: `P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE`
- current state: waiting for the first real candidate-bound `LIVE_OBSERVED` T-close
  input package with `known_at <= T`
- `FROZEN_CANDIDATE_CONTRACT_V1`: not created
- Formal Delivery Ladder: remains `development candidate`

If the first prospective package fails availability, provenance, timing, recovery,
or identity checks, the path fails closed. No C evaluation follows this eligible B
decision, and no automatic promotion is implied.
