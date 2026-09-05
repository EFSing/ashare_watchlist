# NEW_CROSS_SECTIONAL_RELATIVE_STRENGTH_LEADERSHIP_V1 — research report

Decision: `RS_LEADERSHIP_NEEDS_MORE_EVIDENCE`

This is DEVELOPMENT / RECONSTRUCTED_RETROSPECTIVE / DIAGNOSTIC_ONLY evidence. It is not production, a frozen candidate, causal mechanism evidence, or Final OOS.

## Fixed identity

- Protocol commit: `73d62f40fad92f1c85662136e50dc45fb78035bb`.
- Sessions: 769 (2023-06-30 to 2026-08-28).
- Signal rows: 808532 (candidate/control Q60 membership only).
- Candidate active sessions: 769; primary-control active sessions: 769.
- Rule: fixed R20/R60, descending rank, exact symbol tie-break, top 20%, candidate=Q20∩Q60, control=Q60\Q20.

## Primary result

- 10D equal-weight mean date spread (candidate minus primary control): -0.4479386725214781 percentage points.
- Median date spread: -0.5056620062344122 percentage points.
- 95% 20-session moving-block-bootstrap CI: [-0.8847605263271027, 0.130495402413912].
- Positive-spread date rate: 0.4031620553359684.
- Dates with both groups available: 759 / 769.
- Full Q60 baseline 10D mean return: 0.3000453555606661%; candidate-minus-baseline event mean: -0.07393541500071749 percentage points.

## Secondary and robustness

- Equal-weight mean daily Spearman(R20 rank, future 10D return) within Q60: 0.08068855491905655.
- 5D analogue mean date spread: -0.26809895651771753 percentage points.
- Candidate-minus-full-Q60 mean-date difference: 10D=-0.24968869633042348; 5D=-0.13473231834936347 percentage points.
- Calendar-year diagnostics: {"2023": {"mean_spread": 0.312566340613698, "median_spread": -0.014116466804064975, "n_dates": 125, "positive_dates": 60, "positive_rate": 0.48}, "2024": {"mean_spread": -0.948703126046079, "median_spread": -0.9141490534554958, "n_dates": 242, "positive_dates": 87, "positive_rate": 0.359504132231405}, "2025": {"mean_spread": -0.6803326263746085, "median_spread": -0.7680626347075681, "n_dates": 243, "positive_dates": 78, "positive_rate": 0.32098765432098764}, "2026": {"mean_spread": 0.10638080329977725, "median_spread": 0.6665583403682636, "n_dates": 149, "positive_dates": 81, "positive_rate": 0.5436241610738255}}
- Signal board composition (candidate/control rows): {"ChiNext": {"CANDIDATE": 115176, "PRIMARY_CONTROL": 96825}, "Main": {"CANDIDATE": 234839, "PRIMARY_CONTROL": 210417}, "OUT_OF_SCOPE_PREFIX": {"CANDIDATE": 28275, "PRIMARY_CONTROL": 24759}, "STAR": {"CANDIDATE": 54977, "PRIMARY_CONTROL": 43264}}
- Board diagnostics: {"ChiNext": {"CANDIDATE": {"10D": {"mean": 0.13597918281996443, "median": -1.9431757838450636, "n": 113322, "positive_rate": 0.42662501544272075}, "5D": {"mean": 0.12368907908057604, "median": -1.2286196097325952, "n": 114209, "positive_rate": 0.43482562670192365}}, "PRIMARY_CONTROL": {"10D": {"mean": 0.5329981699191338, "median": -1.1114970475859631, "n": 95191, "positive_rate": 0.4503471966887626}, "5D": {"mean": 0.28790680108195715, "median": -0.6040157004830848, "n": 95980, "positive_rate": 0.45731402375494895}}}, "Main": {"CANDIDATE": {"10D": {"mean": -0.24773954210070523, "median": -1.445707405359975, "n": 231110, "positive_rate": 0.4329886201375968}, "5D": {"mean": -0.07961889235152132, "median": -0.7999999999999896, "n": 232769, "positive_rate": 0.44561346227375637}}, "PRIMARY_CONTROL": {"10D": {"mean": 0.3397630478603526, "median": -0.666666666666671, "n": 204786, "positive_rate": 0.459626146318596}, "5D": {"mean": 0.23198552634974912, "median": -0.366544485171616, "n": 207731, "positive_rate": 0.46377286009310115}}}, "OUT_OF_SCOPE_PREFIX": {"CANDIDATE": {"10D": {"mean": 3.4581854189553907, "median": -0.7544120860414005, "n": 28084, "positive_rate": 0.4765702891326022}, "5D": {"mean": 1.6378998605103818, "median": -1.1491108931311167, "n": 28174, "positive_rate": 0.45478100376233405}}, "PRIMARY_CONTROL": {"10D": {"mean": 0.3969482594964856, "median": -1.3635098902210707, "n": 24488, "positive_rate": 0.4395213982358706}, "5D": {"mean": 0.4221355260061349, "median": -0.7425742574257432, "n": 24639, "positive_rate": 0.45870368115589105}}}, "STAR": {"CANDIDATE": {"10D": {"mean": 0.7611446590702062, "median": -1.1331444759206777, "n": 54119, "positive_rate": 0.4571961787911824}, "5D": {"mean": 0.4114850983755569, "median": -0.7961165048543606, "n": 54495, "positive_rate": 0.4584457289659602}}, "PRIMARY_CONTROL": {"10D": {"mean": 0.2732209101298432, "median": -1.359042112681691, "n": 42430, "positive_rate": 0.44678293660146123}, "5D": {"mean": 0.0966154432860266, "median": -0.7352941176470562, "n": 42867, "positive_rate": 0.4558984766836961}}}}

## Input and execution boundaries

- Signal input audit: PASS; existing date-anchored replay universe and validated T-anchor signal prices.
- Reference entry: T+1 XSHG open; not an actual fill.
- Outcome maturity: 5D mature through signal date 2026-08-21 (5 later signal dates censored); 10D mature through signal date 2026-08-14 (10 later signal dates censored).
- Execution coverage: {"CANDIDATE": {"10D": {"mae_mean": -9.21321599061558, "mae_median": -7.372986369268908, "mean": 0.2261099405599486, "median": -1.4997857448936003, "mfe_mean": 12.279249131528235, "mfe_median": 7.606679035250474, "n": 426635, "positive_rate": 0.4372379200018751, "status_counts": {"AVAILABLE": 426635, "INCOMPLETE_STOCK_WINDOW": 2302, "INSUFFICIENT_FORWARD_COVERAGE": 3552, "NO_T_PLUS_1_OPEN": 778}}, "5D": {"mae_mean": -6.694604794270757, "mae_median": -5.189873417721524, "mean": 0.14934042873553813, "median": -0.9197324414715657, "mfe_mean": 8.559973410651232, "mfe_median": 5.402394876079097, "n": 429647, "positive_rate": 0.444974595423685, "status_counts": {"AVAILABLE": 429647, "INCOMPLETE_STOCK_WINDOW": 1147, "INSUFFICIENT_FORWARD_COVERAGE": 1695, "NO_T_PLUS_1_OPEN": 778}}}, "PRIMARY_CONTROL": {"10D": {"mae_mean": -7.4025784709083045, "mae_median": -5.723905723905731, "mean": 0.386019369321636, "median": -0.8672609009877097, "mfe_mean": 9.491661017659924, "mfe_median": 5.905511811023612, "n": 366895, "positive_rate": 0.4543915834230502, "status_counts": {"AVAILABLE": 366895, "INCOMPLETE_STOCK_WINDOW": 1292, "INSUFFICIENT_FORWARD_COVERAGE": 6275, "NO_T_PLUS_1_OPEN": 803}}, "5D": {"mae_mean": -5.192269329776041, "mae_median": -3.88235294117647, "mean": 0.24343306361134667, "median": -0.4761904761904634, "mfe_mean": 6.3556082481514835, "mfe_median": 4.022988505747116, "n": 371217, "positive_rate": 0.46085712669408996, "status_counts": {"AVAILABLE": 371217, "INCOMPLETE_STOCK_WINDOW": 572, "INSUFFICIENT_FORWARD_COVERAGE": 2673, "NO_T_PLUS_1_OPEN": 803}}}}
- Historical PIT size and sector explanations: unresolved/not available for this V1 identification.
- B signal overlap (membership only): {"b_memberships_in_research_dates": 17714, "b_share_overlapping_candidate": 0.22592299875804447, "candidate_share_overlapping_b": 0.009236798556086662, "same_date_overlap": 763, "same_symbol_date_overlap": 4002, "source": {"file_sha256": "8940a4a346ac6911ba669f84a9ceba7ef878b0ed0ce51edf673439b52aa056b9", "logical_path": "data/validation/strategy_candidate_eligibility_v1/b_breakout_retest_eligibility_events.jsonl.gz", "outcomes_accessed": false, "rows_read_for_signal_membership": 17714, "unique_signal_memberships": 17714}}
- Transaction-cost model: not pre-existing; returns are gross and break-even cost is not a tradability guarantee.

## Governance

B, B prospective observation, Volume-Path, turnover/RV, C, production path, frozen state, and Final OOS were not modified/read for this research. No automatic follow-up was started.
