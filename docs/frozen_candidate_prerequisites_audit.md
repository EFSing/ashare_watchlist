# Frozen Candidate Prerequisites Audit V1

更新时间：2026-08-30（Asia/Shanghai）

## 1. 研究问题、范围与停止条件

研究问题：在 development eligibility 已完成后，当前项目是否已经具备一个可以
进入 frozen candidate gate 的真实 strategy candidate？

materiality：这个判断决定项目能否从 `development candidate` 进入下一层。它不是
对 A 股收益、参数或新 research hypothesis 的扩展研究，也不授权读取 Final OOS、
Phase 2F、调参或 strategy promotion。

输入证据：[`PRODUCT_CHARTER.md`](PRODUCT_CHARTER.md)、
[`generation_input_contract.md`](generation_input_contract.md)、
[`development_candidate_contract.md`](development_candidate_contract.md)、
[`strategy_candidate_nomination_v1.md`](strategy_candidate_nomination_v1.md)、
[`strategy_candidate_eligibility_report.md`](strategy_candidate_eligibility_report.md)、
[`candidate_bound_prospective_input_contract_v1.md`](candidate_bound_prospective_input_contract_v1.md)、
[`FROZEN_ARTIFACT_POLICY.md`](FROZEN_ARTIFACT_POLICY.md)、
[`data/governance/frozen_artifacts.json`](../data/governance/frozen_artifacts.json) 和
PR #12 的 development-candidate regression evidence。

停止条件：一旦候选资格和当前最小 prerequisites 缺口可以判断，不继续切分指标、
优化参数或扩大 research scope。

## 2. Decision

**`FROZEN_CANDIDATE_BLOCKED`**

唯一剩余阻塞原因：

**`P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE`**

B 已经通过冻结的 `STRATEGY_DEVELOPMENT_ELIGIBILITY_V1`，因此它是获资格进入
prerequisites 的 candidate；但尚未出现首个真实 candidate-bound、
`LIVE_OBSERVED`、`known_at <= T` 的 prospective T-close input instance。不能用
retrospective DEVELOPMENT artifact 或 contract 文档替代该 instance。

因此本审计仍不创建也不宣称满足 `FROZEN_CANDIDATE_CONTRACT_V1`。已定义的
`CANDIDATE_BOUND_PROSPECTIVE_INPUT_PROVENANCE_CONTRACT_V1` 只是下一次真实输入的
验收 contract，不是已发生的 prospective evidence。

## 3. Product infrastructure audit

下表的 PASS 只表示既有 development product path 已有受控证据；它不等价于
production readiness。

| prerequisite | 结论 | 证据与边界 |
| --- | --- | --- |
| deterministic generation | `PASS`（development scope） | PR #12 的 deterministic generation、canonical output、immutable version 与 output identity 回归。 |
| canonical output | `PASS`（development scope） | schema-valid watchlist、zero-candidate success、downstream ingest 回归已覆盖。 |
| complete generation identity | `PASS`（development scope） | fingerprint 覆盖 contract/schema、strategy identity、实际 names、canonical market_env 和 output-affecting inputs。 |
| fail-closed | `PASS`（development scope） | READY、evaluator failure、缺名字、非法/冲突输出和 write failure 均有明确失败路径。 |
| monitoring / rollback | `PASS`（development scope） | schema、output SHA、immutable provenance、known-good rollback 与 HEALTHY monitor 有回归。 |
| T close / T+1 | `PASS`（contract scope） | `Asia/Shanghai`、XSHG session close、下一交易日 T+1 和错误时 fail closed 已冻结；B 的真实 prospective instance 尚未发生。 |
| artifact recovery | `PASS`（现有 artifact scope） | Phase 2E registry required artifacts hash/recovery 已核对；daily_k 为 `FULLY_RECOVERABLE`。 |

结论：产品基础支持 `development candidate`，B 的 eligibility 也已通过，但 frozen
candidate 仍需要首个真实候选绑定的 prospective input instance。

## 4. Strategy candidate eligibility audit

### 4.1 Nomination and reconstruction

唯一 nomination：
`NOMINATE_B_BREAKOUT_RETEST_LEGACY_V1_FOR_DEVELOPMENT_ELIGIBILITY`。

B exact reconstruction、V0 parity、edge behavior、semantic spec SHA 和 numeric
projection parity 均 PASS。B spec SHA 为
`5bbeb345ebd8883149138d2f29f8606f919949ae285aa2839fa337921dfc7112`。A 仍为
`REJECT_A_PLATFORM_BREAKOUT_LEGACY_V1_AS_FROZEN_CANDIDATE`；C 未被评估。

### 4.2 Fixed eligibility decision

`STRATEGY_DEVELOPMENT_ELIGIBILITY_V1` 的 thresholds 在读取 B returns 之前已经冻结：

`ELIGIBILITY_RULE_FROZEN_BEFORE_B_RETURNS_READ = true`

Python 3.12.13 / pandas 2.2.3 / `pyarrow==17.0.0` 的单次 replay 结果为：

- Event N：`17,714`；available N 1D/3D/5D/10D：`17,689` / `17,635` / `17,602` / `17,558`；
- 10D positive rate / mean / median：`51.6403%` / `+1.4603%` / `+0.3226%`；
- robust 10D years：4；positive-mean robust years：2（2024、2025）；
- fixed gates：全部 PASS；
- final decision：`CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES`。

详细 1D/3D/5D/10D MFE/MAE、concentration、year robustness、input verification 和
event/manifest SHA 见 [`strategy_candidate_eligibility_report.md`](strategy_candidate_eligibility_report.md)。

### 4.3 Boundaries retained

- B 仍是 research/development candidate，不是 production strategy；
- 该 eligibility 不是 parameter validation、调参或 Final OOS；
- 不自动评估 C，不启动 Phase 2F，不创建 TOP-N 或 promotion path；
- retrospective output 仍标记 `DEVELOPMENT` / `RECONSTRUCTED_RETROSPECTIVE`。

## 5. Candidate-bound prospective input contract

Contract：[`candidate_bound_prospective_input_contract_v1.md`](candidate_bound_prospective_input_contract_v1.md)。
它绑定：

- B strategy version/spec SHA 与 eligibility protocol；
- T close / T+1；
- exact universe、sector semantics、names、market_env；
- provider/version、calendar；
- availability、fail-closed、recovery；
- generation fingerprint 与 canonical output identity。

contract 当前状态为 `CONTRACT_DEFINED_NO_LIVE_INSTANCE`。没有伪造 T、payload、
prospective output 或 live observation。

## 6. Minimum P0 / P1

### P0

本轮没有发现新的全局 P0 correctness/safety defect。PIT、T close/T+1、fail-closed、
identity/hash 规则在受控 path 上保持明确；历史新浪 membership 缺失仍只限制
FULL legacy retrospective scope。

### P1

1. **`P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE`**：等待首个真实、候选绑定、
   `LIVE_OBSERVED` 的 T-close package，并验证 `known_at <= T`、universe/sector/
   names/market_env、provider/version、calendar、availability/recovery 和 output
   identity。它是当前唯一剩余 frozen-candidate prerequisite P1。

不需要先建设 scheduler、broker、自动交易或复杂告警。历史新浪 membership 仍是
FULL legacy validation 的 scope-local blocker，不升级为全局或 B eligibility blocker。

## 7. Next decision, deferred research and shortest product path

下一步只等待并审计首个真实 prospective package；package 通过后回到
`FROZEN_CANDIDATE_PREREQUISITES` decision point。若 package 缺失、陈旧、冲突、
不可恢复、时间语义不符或 identity 不一致，必须 fail closed。

可以 DEFER：Phase 2F/Research V2、参数选择和调参、performance-based rule change、
完整 legacy 85-score parity、历史新浪 membership acquisition、scheduler、broker、
自动交易、复杂告警和不影响 P0/P1 的 later production hardening。

当前不创建 `FROZEN_CANDIDATE_CONTRACT_V1`，不把 development eligibility 写成
strategy promotion，不读取 Final OOS，也不自动测试 C。

## 8. Governance conflict and provenance correctness closure

本轮修复了 active PR metadata 与正式 evidence 不一致的问题：B 的 decision 保持
`CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES`，Formal Delivery Ladder 保持
`development candidate`，尚未创建 `FROZEN_CANDIDATE_CONTRACT_V1`，唯一当前 P1
仍为 `P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE`；不 promotion。

`scripts/strategy_development_eligibility.py` 现在只把稳定的 repo-relative logical
path 写入 eligibility provenance，并禁止 `Path.resolve()` 的 machine-specific 结果
进入 identity。relocated filesystem roots 以及 relative/absolute invocation 的回归均
证明 canonical manifest/content identity 相同；绝对路径不参与 semantic/content/hash。

正式 B decision evidence 已登记到 registry：event artifact 的 file SHA 为
`8940a4a346ac6911ba669f84a9ceba7ef878b0ed0ce51edf673439b52aa056b9`、semantic/content
SHA 为 `a16e48dfbe8a93f64d8bf1bad6e00d3eaf32c10fd60eed09dc5574247b8119bc`；manifest
semantic SHA 为 `f79ec9baa494f2f0256843c2540988bd25c94269ed9a1fd4ada228759bd8e0a2`，
payload content SHA 为 `e754787836b28316430278372ab2d84817091d4608da394f9207f695a4c27aee`，
file SHA 为 `5e0a557c1930de7b4f182f09f43b45c0c11b19b2d7c992bf9e7fa7e6cc6de048`。
两者均是 `required_for_decision=true`、`required_for_replay=false`，并保留
`DEVELOPMENT` / `RECONSTRUCTED_RETROSPECTIVE` 及当前 recoverability 标签。

本次 deterministic reproducibility verification 的 event count、event identities、
全部 metrics、fixed thresholds、gate audit 和 eligibility decision 与修复前完全一致；
没有 C、Phase 2F、调参、Final OOS 或 production promotion。

## 2026-08-31 — First formal post-merge package audit

| prerequisite | result | evidence |
| --- | --- | --- |
| B decision / spec / threshold | PASS unchanged | `B_BREAKOUT_RETEST_LEGACY_V1`; spec SHA remains `5bbeb345ebd8883149138d2f29f8606f919949ae285aa2839fa337921dfc7112`; frozen eligibility decision unchanged |
| SH/SZ scope / exact Sina taxonomy | PASS for selected boundary | `TRADABLE_UNIVERSE_SCOPE_V1`; exact `stock_sector_spot(indicator="新浪行业")` + `stock_sector_detail` path used |
| LIVE_OBSERVED / T-close → T+1 | PASS precondition | T=`2026-08-31`, T+1=`2026-09-01`, observed after 15:00 BJT close |
| provider / fallback provenance | BLOCKED at name consistency | `INPUT_CONFLICT` for symbol `000012`; later providers not reached |
| immutable persistence / Drive backup / recovery | NOT APPLICABLE | no READY package existed; no bytes were eligible for persistence or upload |
| deterministic input/generation identity | NOT CREATED | no complete manifest/package existed |
| Final OOS / C / Phase 2F / tuning / promotion | PASS boundary | Final OOS sealed/unread; all prohibited paths untouched |

Final decision: `FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_INPUT_CONFLICT`.
The machine-readable failure evidence is
`data/governance/prospective_input_attempt_evidence_20260831.json`; it is explicitly
not a frozen artifact. The failure classification is
`INPUT_PROVIDER_DATA_CONSISTENCY_CONFLICT`, not provider connectivity. The original
attempt did not record raw names or execution counts, so those fields remain explicitly
unrecorded rather than being backfilled from the current diagnostic. The current
read-only name diagnostic is
[`current_capability_name_diagnostic_20260831.md`](current_capability_name_diagnostic_20260831.md)
and is not prospective evidence. No `FROZEN_CANDIDATE_CONTRACT_V1` is created.

## 2026-09-01 continuation audit — current provider dependency boundary

> `LOCAL_CURRENT_SNAPSHOT_DIAGNOSTIC_NOT_PROSPECTIVE_EVIDENCE`

The B source audit is now explicit. Exact six-digit symbol is the security/trading
identity. Display names are not consumed by B for symbol joins, candidate selection,
hard gates, trigger, stop, target, RR, score, final status or canonical identity; the
active correction therefore adopts `DISPLAY_NAME_CONSISTENCY_POLICY_V2_SYMBOL_AUTHORITATIVE`
and retains raw/normalized mismatch diagnostics in the V2 contract and generation identity.

B does consume sector evidence: `sector_rank` and `sector_chg` feed the 85-score
`strong_sector` and `sector_linkage` components, while missing evidence returns
`INSUFFICIENT_DATA` through `SECTOR_EVIDENCE_COMPLETE`. Sector remains an executable
required input; this audit does not authorize dropping it, shrinking the universe, or
substituting EM/THS/SW taxonomy. The B spec SHA remains
`5bbeb345ebd8883149138d2f29f8606f919949ae285aa2839fa337921dfc7112`.

The fresh 2026-09-01 current-only probe passed the declared runtime and provider
capability checks but found 5,221 scoped HiThink symbols versus 2,978 unique exact-Sina
sector symbols. It reported 2,682 universe symbols without sector membership, 439 sector
symbols outside the universe, and five distinct multi-sector symbols:
`000587`, `000602`, `002217`, `002617`, `600714`. It found no exact duplicate symbol in
that snapshot. These counts are not historical T=`2026-08-31` evidence and do not create
a live package.

Current decision is
`FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_SECTOR_MEMBERSHIP_AMBIGUITY`, with independent
exact-Sina coverage failure. `NEEDS_MORE_EVIDENCE` remains the research decision for a
future legitimate T-close response that is complete and unambiguous. No T=`2026-09-01`
acquisition is run because PR #18 is not merged to clean master and the sector gate is
unresolved. The detailed matrix is in
[`b_dependency_audit_20260901.md`](b_dependency_audit_20260901.md); V1 audit/evidence is
preserved unchanged.
