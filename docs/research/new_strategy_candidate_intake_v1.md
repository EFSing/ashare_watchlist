# New Strategy Research Intake V1

状态：`NO_OUTCOME_CANDIDATE_INTAKE` / `SELECTION_REQUIRED`

本文件只做 no-outcome candidate intake/shortlist。它不实现 evaluator、不创建
threshold、不读取 C 或任何新候选 forward returns、不比较 candidate performance、不
打开 Final OOS，也不启动 B V2、turnover V2 或 Volume-Path V2。

## 1. Current B state and separation

当前 B identity 是 `B_BREAKOUT_RETEST_LEGACY_V1_1`，spec SHA 为
`f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd`。B 的 match、
first qualifying breakout、pullback、hard gates、support、stop、target、RR、overhang、
score、`score_cutoff=None`、`top_n=None`、universe 和 prospective generation path
保持不变。

既有研究结论 `VOLUME_PATH_NEEDS_MORE_EVIDENCE` 与
`TURNOVER_X_RELATIVE_VOLUME_NEEDS_MORE_EVIDENCE` 保持不变。B 不再进行 feature
expansion 或 parameter research；它现在只运行独立的
[`B V1_1 prospective observation protocol`](b_v1_1_prospective_observation_protocol_v1.md)，
protocol commit 为
`3dd7d51a6341a60540c26db2aa4f18367520d95b`。该后台 stream 的 evidence 只服务 B
prospective observation，不作为新 candidate 的 outcome 输入。

## 2. No-outcome rule and nomination criteria

本 intake 未读取 C forward returns、任何新候选 returns、Final OOS 或任何 outcome
table 来选择候选。所有 predictive value 均为 `UNKNOWN`。

候选只按以下设计条件做 qualitative review：hypothesis distinctness from B、
PIT/known-at feasibility、deterministic reproducibility、low parameter freedom、
T-close/T+1 compatibility、A-share execution realism、expected sample frequency、
provider dependency、provenance quality 和 relative diversification。这里的排序是
工程/研究可行性判断，不是收益 ranking。

## 3. Shortlist matrix

| candidate | provenance | current data/PIT | T-close/T+1 | expected frequency | complexity / freedom | overlap with B | diversification potential | provider |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `C_MAIN_TREND_RETEST_LEGACY_V1` | exact V0 legacy rule; strong | OHLCV + existing index/calendar sufficient; PIT feasible | compatible | medium | medium; several structural gates and one Fib branch | medium | medium; trend continuation differs from breakout-retest | none |
| `NEW_CROSS_SECTIONAL_RELATIVE_STRENGTH_LEADERSHIP_V1` | `NEW_RESEARCH_HYPOTHESIS`; no legacy performance provenance | existing same-day OHLCV/universe; PIT feasible if ranks use T and earlier only | compatible | medium-high | low; fixed lookbacks/rank rule must be frozen once | low | high; selection is cross-sectional leadership, not breakout episode timing | none |
| `NEW_VOLATILITY_CONTRACTION_BREAKOUT_V1` | `NEW_RESEARCH_HYPOTHESIS`; no legacy performance provenance | existing OHLCV; PIT feasible | compatible | medium | low-medium; compression window, breakout and volume definitions must be fixed | low-medium; shares a breakout event but not B pullback gates | medium-high; captures volatility expansion regime | none |
| `NEW_CONTROLLED_RIGHT_SIDE_REVERSAL_V1` | `NEW_RESEARCH_HYPOTHESIS`; no legacy performance provenance | existing OHLCV; PIT feasible | compatible | medium | medium; exhaustion, reclaim and invalidation definitions must be frozen | low-medium | medium-high; reversal exposure differs from B continuation | none |

## 4. Candidate design reviews

### C_MAIN_TREND_RETEST_LEGACY_V1

1. Economic/behavioral hypothesis：a strong medium-term advance can resume after a
   controlled pullback that does not destroy trend structure.
2. Entry/signal concept：use the authoritative V0 C branch at T close: within the last
   60 bars, identify the close peak; require peak run-up from its preceding 60-bar close
   low of at least 30%, drawdown of 5%–22%, Fibonacci-or-MA20 proximity, contracted
   pullback volume, and a close back above MA5 with the V0 turn-strength condition.
3. Required fields：T-close OHLCV with at least the existing B/development bar depth,
   XSHG calendar, and no new sector/provider field for the core C branch.
4. Current inputs：the existing T-close stock Kline manifest and calendar can support the
   calculation; no implementation is being added in this intake.
5. PIT/known-at：feasible when all peak, low, MA and volume windows are cut at T; no
   future bar or current-data backfill is allowed.
6. Timing：T-close signal and T+1 XSHG reference open are compatible.
7. Expected frequency：medium, because the 30% run-up plus controlled drawdown gates
   should be less frequent than an unrestricted trend rank.
8. Main failure mode：late entries after an exhausted trend, false Fibonacci/MA20
   support, and repeated signals from one long trend episode.
9. Parameter count/degrees of freedom：medium; the V0 rule contains fixed 60-bar
   windows, 30%/5%–22% structure, 61.8% branch, 6% MA20 proximity, 0.75 volume
   contraction and MA5/turn condition. These are provenance, not a license to tune.
10. Overlap with B：medium; both are pullback continuation ideas, but C is anchored on
    a prior medium-term run-up rather than B's first qualifying breakout episode.
11. Portfolio diversification：medium; it can add mature-trend continuation exposure,
    though it may still cluster with B in strong-trend markets.
12. Exact provenance：yes. `EFSing/ashare_watchlist-V0@c8406c393c0b135eafb0aec763576ae869fddcff`,
    `ashare_watchlist/scripts/screen_system.py`, historical working-tree SHA
    `6cac746123e3151999cbeeb1a612868ef77b50af6c7c64b0d80eb387ae1d19f9`. The exact
    V0 C formula is the inventory rule above; C returns have not been read and its
    predictive value remains `UNKNOWN`.
13. New provider：none expected.

### NEW_CROSS_SECTIONAL_RELATIVE_STRENGTH_LEADERSHIP_V1

1. Economic/behavioral hypothesis：relative-strength leaders can continue to attract
   capital because leadership is a cross-sectional allocation effect, not merely a
   single-stock breakout/retest pattern.
2. Entry/signal concept：at T close, rank the eligible SH/SZ universe by pre-registered
   trailing relative returns versus the same benchmark/universe and admit leaders using
   a fixed rank rule; no B breakout, pullback or B score condition is inherited.
3. Required fields：same-day universe snapshot, stock OHLCV, benchmark/index OHLCV,
   XSHG calendar, and exact symbol identity. No sector or paid alternative data is
   required for the core hypothesis.
4. Current inputs：existing T-close universe, stock Kline and index manifests are
   sufficient in principle; a later protocol must freeze the rank windows and eligible
   cross-section before any outcomes are read.
5. PIT/known-at：feasible if all ranks use only bars through T and the same-day universe
   snapshot; no future membership, rank or corporate-action information may enter signal
   generation.
6. Timing：T-close signal and T+1 XSHG reference open are compatible.
7. Expected frequency：medium-high; a fixed leadership slice should yield regular signals
   across sessions while still avoiding a manually preferred subset.
8. Main failure mode：crowded leadership, rapid factor reversal, and hidden universe or
   benchmark changes.
9. Parameter count/degrees of freedom：low; one or two fixed lookback returns, one
   benchmark definition and one pre-registered rank/eligibility rule. No threshold is
   selected in this intake.
10. Overlap with B：low; B is an event-conditioned single-stock breakout/retest with
    hard structural gates, while this candidate is cross-sectional ranking.
11. Portfolio diversification：high potential; it can supply leadership exposure when
    B's breakout episode mechanics are inactive, subject to later concentration review.
12. Exact provenance：no. This is explicitly `NEW_RESEARCH_HYPOTHESIS`; no returns or
    legacy predictive claim is attached.
13. New provider：none expected; existing OHLCV, index and universe inputs should suffice.

### NEW_VOLATILITY_CONTRACTION_BREAKOUT_V1

1. Economic/behavioral hypothesis：a sustained contraction in realized range and/or
   volume can precede an information or positioning shock that expands volatility.
2. Entry/signal concept：at T close, detect a pre-registered compressed range followed
   by a close outside the compressed range; the exact breakout and volume definitions
   must be fixed before outcomes.
3. Required fields：stock OHLCV, same-day universe, XSHG calendar, and optionally the
   existing benchmark only for descriptive regime tags; no sector data is required for
   the core signal.
4. Current inputs：existing stock Kline manifests can support range, ATR-like and volume
   features; no new provider is needed in principle.
5. PIT/known-at：feasible with windows ending at T and no use of T+1 or later bars.
6. Timing：T-close signal and T+1 XSHG reference open are compatible; limit-state
   execution uncertainty must be retained.
7. Expected frequency：medium; compression-plus-expansion is more selective than a
   generic daily move.
8. Main failure mode：false expansion, news gaps, and limit-state/non-executable opens.
9. Parameter count/degrees of freedom：low-medium; compression window, range measure,
   expansion boundary and optional volume confirmation. These must be fixed once, not
   searched after outcomes.
10. Overlap with B：low-medium; both may fire on expansion days, but this candidate has
    no B first-breakout pullback, support, RR or score logic.
11. Portfolio diversification：medium-high; it targets volatility-regime transition,
    which is different from B's breakout-retest episode identity.
12. Exact provenance：no; explicitly `NEW_RESEARCH_HYPOTHESIS`.
13. New provider：none expected.

### NEW_CONTROLLED_RIGHT_SIDE_REVERSAL_V1

1. Economic/behavioral hypothesis：after a defined downside exhaustion, a controlled
   reclaim can represent a transition from forced selling to demand without requiring a
   new 60-day breakout.
2. Entry/signal concept：at T close, identify a bounded prior decline/exhaustion and a
   deterministic reclaim of a short trend reference with a controlled range/volume
   profile; invalidation must be fixed before outcomes.
3. Required fields：stock OHLCV, same-day universe and XSHG calendar; no sector or paid
   alternative data is required for the core candidate.
4. Current inputs：existing T-close stock Kline data is sufficient in principle; exact
   exhaustion/reclaim definitions are intentionally not implemented here.
5. PIT/known-at：feasible if every decline, low, reclaim and volume feature ends at T;
   no forward low or outcome label may select the threshold.
6. Timing：T-close signal and T+1 XSHG reference open are compatible.
7. Expected frequency：medium; the controlled-reversal constraints should avoid every
   ordinary down day.
8. Main failure mode：catching a continuing downtrend, gap-down T+1 opens, and
   ambiguous limit/suspension states.
9. Parameter count/degrees of freedom：medium; decline window/depth, exhaustion test,
   reclaim reference and invalidation rule. A later protocol must keep this small and
   pre-registered.
10. Overlap with B：low-medium; it is reversal-oriented and does not require B's
    breakout-plus-pullback sequence, although reclaim mechanics can create occasional
    event overlap.
11. Portfolio diversification：medium-high; it adds potential reversal exposure rather
    than another continuation-only rule.
12. Exact provenance：no; explicitly `NEW_RESEARCH_HYPOTHESIS`.
13. New provider：none expected.

## 5. Recommendation and stop gate

`RECOMMENDED_NEXT_STRATEGY_CANDIDATE=NEW_CROSS_SECTIONAL_RELATIVE_STRENGTH_LEADERSHIP_V1`

理由：它与 B 的 event-conditioned breakout/retest identity 最不相似，仍可使用现有
T-close OHLCV/universe/index inputs，PIT 与 T+1 语义清晰，参数自由度较低，预期样本
频率较充足，并有较好的 portfolio-level diversification potential。这个推荐只表示
下一步研究设计优先级，不表示 predictive validity 或收益结论。

`SECONDARY_CANDIDATE=NEW_VOLATILITY_CONTRACTION_BREAKOUT_V1`

理由：同样不需要新 provider，行为假设清楚且 implementation complexity 可控；但
它与 B 仍共享部分 breakout/expansion event，episode overlap 与 limit-state execution
risk 需要在后续 protocol 中明确处理。

C 的 provenance 最强，但不能因为它来自 V0 就默认有效或自动 nominate；C 必须与两
个 new hypotheses 一样，等用户选择后接受同一套 no-outcome research-design review。

用户选择后，下一轮才创建严格的
`NEW_STRATEGY_PRE_OUTCOME_RESEARCH_PROTOCOL_V1`，固定 selected candidate 的 exact
identity/spec、required fields、PIT/known-at contract、T-close/T+1 execution
classification、episode/overlap semantics、sample checkpoint、outcome convention、
pre-outcome commit 和 no-early-stop rule；然后才允许一次固定 implementation/replay。

最终 stop marker：

`NEW_STRATEGY_CANDIDATE_SELECTION_REQUIRED`
