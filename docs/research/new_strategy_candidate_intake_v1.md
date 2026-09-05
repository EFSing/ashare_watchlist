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

本轮新增的方法论原则为 `FEATURE_EPISTEMIC_SEPARATION`。任何 future
strategy/feature/rule 都必须把以下三层证据分开记录：

1. `DEFINITION_AND_PROXY_CLAIM`：精确 calculation/observable definition、它实际
   描述的 market state，以及对不可直接观察概念的 proxy/mechanism claim。observable
   不得被写成已经证明的 mechanism；例如“成交量下降”是 observable，“卖方耗尽”只
   能是 proxy/mechanism hypothesis。
2. `PREDICTIVE_EVIDENCE`：只使用 `UNTESTED`、`EXPLORATORY_ONLY`、
   `DEVELOPMENT_SUPPORTED`、`PROSPECTIVE_SUPPORTED`、`FAILED` 或 `INCONCLUSIVE`。
   predictive status 与 mechanism status 独立；经济故事不能提升 predictive evidence，
   正收益也不能自动提升 mechanism evidence。
3. `MECHANISM_EVIDENCE`：只使用 `NONE`、`HYPOTHESIS` 或
   `INDEPENDENT_EVIDENCE_SUPPORTED`，并可附 `REFLEXIVE`、`BEHAVIORAL`、
   `FLOW / POSITIONING`、`INFORMATION_DIFFUSION` 或 `UNKNOWN` mechanism type。流行
   指标或正收益不能单独证明 mechanism。

因此每个正式 candidate protocol 还必须包含
`ALTERNATIVE_EXPLANATIONS_REQUIRED`、`SIMPLE_BASELINE_REQUIRED` 和
`FALSIFICATION_CRITERIA_REQUIRED`。在 outcome access 前，至少要写出最简单的
competing explanations，预注册一个最简单合理 baseline，并回答“What result would
make us reject or materially downgrade this hypothesis?”。失败后不得自动加 filter、
加 indicator、改 threshold、换 horizon、换 subgroup 或换 rank definition；若要继续，
必须另建独立 protocol。

`CAUSAL_LANGUAGE_RULE`：descriptor、proxy、predictor、mechanism、causal driver
不得混写。类似“缩量说明卖压减弱”“站上均线说明资金重新进入”“高位导致衰竭”的句子，
在没有独立机制证据时必须显式标为 mechanism hypothesis。一个 feature 可以有 predictive
value 但 mechanism unknown；反过来 plausible mechanism 但没有 predictive evidence，
不得进入 strategy。

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

## 5. Epistemic separation and pre-outcome review

以下是对当前四个候选的 design-level record。这里的 `UNTESTED`、`HYPOTHESIS` 和
baseline/falsification 只是未读 outcome 前的 protocol prerequisites，不是收益或机制
结论。

### C_MAIN_TREND_RETEST_LEGACY_V1

- `DEFINITION_AND_PROXY_CLAIM`：observable 是 V0 的 60-bar peak、preceding
  60-bar close low、run-up、drawdown、Fib/MA20 proximity、pullback volume 和 MA5
  reclaim。它描述的是已经发生的中期价格路径与当前回撤位置；“趋势可能延续”或
  “回撤代表健康整理”只能是 `BEHAVIORAL` mechanism hypothesis。
- `PREDICTIVE_EVIDENCE=UNTESTED`：C 只有 inventory/provenance，C returns 尚未读取。
- `MECHANISM_EVIDENCE=HYPOTHESIS`，`mechanism_type=BEHAVIORAL`；V0 provenance
  不是独立机制证据。
- `ALTERNATIVE_EXPLANATIONS_REQUIRED`：generic momentum、sector/market beta、
  size/liquidity、volatility exposure、sample selection、同一长趋势 episode 的重复
  计数，以及 Fib/MA20 只是 price-pattern re-description。
- `SIMPLE_BASELINE_REQUIRED`：未来至少预注册一个最简单的 trailing-return momentum
  或 benchmark-relative trend baseline；exact lookback、ranking 和 matching 在正式
  protocol 中固定，本轮不选参数。
- `FALSIFICATION_CRITERIA_REQUIRED`：若 C 相对 simple momentum/beta/sector/size/
  liquidity controls 无稳定增量，或结果主要由少数 trend episodes/months/regimes
  驱动，则 reject 或 materially downgrade；不得事后增加 C filter。

### NEW_CROSS_SECTIONAL_RELATIVE_STRENGTH_LEADERSHIP_V1

- `DEFINITION_AND_PROXY_CLAIM`：observable 是
  `cross-sectional trailing relative-return leadership`，即在 T-close eligible
  universe 内按截至 T 的 trailing relative returns 排名。possible proxy/mechanism
  是 persistent capital allocation、information diffusion 或 momentum；不得写成
  “强者恒强，因此有 alpha”。
- `PREDICTIVE_EVIDENCE=UNTESTED`：本轮没有读取该 candidate 的 forward outcome。
- `MECHANISM_EVIDENCE=HYPOTHESIS`，`mechanism_type=FLOW / POSITIONING +
  INFORMATION_DIFFUSION`；没有 independent mechanism evidence。
- `ALTERNATIVE_EXPLANATIONS_REQUIRED`：generic momentum、sector momentum、size
  exposure、volatility exposure、liquidity exposure、market beta、same-regime
  concentration 和 universe construction effect。若未来有效，必须区分 leadership
  的增量预测力与已有 exposure 的重新包装。
- `SIMPLE_BASELINE_REQUIRED`：未来 protocol 至少预注册一个简单 trailing-return
  momentum baseline，并固定 matching/exposure controls；具体 lookback、ranking 和
  controls 留待下一轮 protocol，本轮不选择参数。
- `FALSIFICATION_CRITERIA_REQUIRED`：若相对 simple momentum 加 sector/size/
  volatility/liquidity/beta controls 后没有稳定 incremental information，或优势只在
  单一 market regime/month/universe slice 出现，则 reject 或 materially downgrade；
  不得失败后改 rank definition 或换 horizon。

### NEW_VOLATILITY_CONTRACTION_BREAKOUT_V1

- `DEFINITION_AND_PROXY_CLAIM`：observable 是预注册的 range/realized-volatility
  contraction 与随后 T-close range expansion/outside-close state。possible proxy 是
  positioning compression、information arrival 或 supply-demand imbalance；这些是
  `FLOW / POSITIONING` / `INFORMATION_DIFFUSION` hypotheses，不是已证明的 cause。
- `PREDICTIVE_EVIDENCE=UNTESTED`：没有读取该 candidate 的 forward outcome。
- `MECHANISM_EVIDENCE=HYPOTHESIS`，`mechanism_type=INFORMATION_DIFFUSION`；没有
  independent mechanism evidence。
- `ALTERNATIVE_EXPLANATIONS_REQUIRED`：generic breakout/momentum、market-wide
  volatility regime、sector shock、size/liquidity、gap/news effect、limit-state
  selection 和 compression rule 的 sample selection。
- `SIMPLE_BASELINE_REQUIRED`：未来至少预注册不带 contraction 条件的最简单 range/
  expansion breakout baseline，另保留 market-volatility descriptive control；exact
  windows/thresholds 在 protocol 中固定，本轮不调参。
- `FALSIFICATION_CRITERIA_REQUIRED`：若 contraction 没有相对 simple breakout 的稳定
  增量，或收益只来自 gap/news/limit-state subset，则 reject 或 materially downgrade；
  不得事后加 volume filter 或改 compression window。

### NEW_CONTROLLED_RIGHT_SIDE_REVERSAL_V1

- `DEFINITION_AND_PROXY_CLAIM`：observable 是截至 T 的 bounded prior decline/
  exhaustion 与短趋势 reference reclaim、range/volume state。possible proxy 是 seller
  exhaustion、forced-selling release 或 demand return；这些只能标为 `BEHAVIORAL` /
  `FLOW / POSITIONING` hypotheses。
- `PREDICTIVE_EVIDENCE=UNTESTED`：没有读取该 candidate 的 forward outcome。
- `MECHANISM_EVIDENCE=HYPOTHESIS`，`mechanism_type=BEHAVIORAL`；没有 independent
  mechanism evidence。
- `ALTERNATIVE_EXPLANATIONS_REQUIRED`：generic mean reversion、market beta rebound、
  sector rebound、size/liquidity、high-volatility exposure、gap/news effect、oversold
  selection 和 same-regime concentration。
- `SIMPLE_BASELINE_REQUIRED`：未来至少预注册一个简单 trailing-return reversal/
  rebound baseline，并固定 benchmark/sector/beta descriptive controls；exact windows
  留待正式 protocol，本轮不选择参数。
- `FALSIFICATION_CRITERIA_REQUIRED`：若相对 simple rebound baseline 没有稳定增量，或
  结果主要来自极端波动、少数 sector/regimes 或不可执行 T+1 opens，则 reject 或
  materially downgrade；不得失败后自动放宽 exhaustion/reclaim 条件。

## 6. Recommendation and stop gate

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
