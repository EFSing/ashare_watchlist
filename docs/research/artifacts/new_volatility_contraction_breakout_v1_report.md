# NEW_VOLATILITY_CONTRACTION_BREAKOUT_V1 — research report

Decision: `VOLATILITY_CONTRACTION_BREAKOUT_NEEDS_MORE_EVIDENCE`

This is DEVELOPMENT / RECONSTRUCTED_RETROSPECTIVE / DATE_ANCHORED / DIAGNOSTIC_ONLY evidence. It is not production, a frozen candidate, causal mechanism evidence, or Final OOS.

## Fixed identity

- Base: `44544b831dfb12bc03bbc9efab49704f095cce1d`; protocol commit: `411c72b1eff27ecb1ecfb125818837b6aa4a313c`.
- Sessions: 769 (2023-06-30 to 2026-08-28).
- Universe identities: 4041140; generic breakout=195464; candidate=21988; control=173476.
- Rule: TRP recent 10 sessions versus prior 40 sessions, ratio < 1, bottom 20% rank with symbol tie-break, strict close > prior 20-session high; volume qualification disabled.

## Primary incremental result

- 10D equal-weight date spread (candidate minus primary control): 0.4538241054597729 percentage points.
- Median spread: 0.1133402742547025 percentage points.
- 95% moving-block-bootstrap CI: [-0.38148186851137433, 1.3494782855469096].
- Positive-spread date rate: 0.5094594594594595; both-group valid dates: 740.
- Continuous compression rho: mean=0.11033952017189008, median=0.10848552356469778, positive-date rate=0.7378129117259552, valid dates=759.

## Secondary and robustness

- 5D candidate-control spread: 0.32623724162271156 percentage points.
- Cooldown: 0.046626218016091805 percentage points; CI=[-0.5683869874276704, 0.6434644996992309].
- Year diagnostics: {"2023": {"dates": 124, "mean_spread_10D": 0.8213351421787862, "median_spread_10D": 0.4663452434650172, "positive_date_rate": 0.5483870967741935, "sign_positive": true}, "2024": {"dates": 233, "mean_spread_10D": 1.757962734001434, "median_spread_10D": 1.1334851462636617, "positive_date_rate": 0.575107296137339, "sign_positive": true}, "2025": {"dates": 236, "mean_spread_10D": 0.31359097490991433, "median_spread_10D": 0.09372954982327908, "positive_date_rate": 0.5084745762711864, "sign_positive": true}, "2026": {"dates": 147, "mean_spread_10D": -1.6981531067415747, "median_spread_10D": -1.130231977049859, "positive_date_rate": 0.3741496598639456, "sign_positive": false}}
- Board diagnostics: {"ChiNext": {"CANDIDATE": {"10D": {"mean": 0.8301794099213239, "median": -0.6430868167202619, "n": 6053, "p25": -5.6122448979591955, "p75": 4.520166898470079}, "5D": {"mean": -0.45072131462204845, "median": -1.0828025477707004, "n": 6187, "p25": -5.04366282836553, "p75": 2.4704816719421707}}, "PRIMARY_CONTROL": {"10D": {"mean": 0.04160006427930736, "median": -1.4145306516714418, "n": 38602, "p25": -7.704975734222777, "p75": 4.927536231884061}, "5D": {"mean": -0.4826366742781723, "median": -1.3418369011290787, "n": 39064, "p25": -6.280542039449582, "p75": 3.199232245681366}}}, "Main": {"CANDIDATE": {"10D": {"mean": 0.07034333176156918, "median": -0.6651884700665023, "n": 13009, "p25": -4.61538461538461, "p75": 3.200000000000003}, "5D": {"mean": -0.4153923909494008, "median": -0.8188331627430934, "n": 13205, "p25": -3.78250591016549, "p75": 2.028081123244929}}, "PRIMARY_CONTROL": {"10D": {"mean": -0.5552914976914812, "median": -1.4869888475836368, "n": 105981, "p25": -7.08994708994709, "p75": 3.9629005059022004}, "5D": {"mean": -0.5458363213940511, "median": -1.1197243755383224, "n": 107073, "p25": -5.490196078431375, "p75": 2.9850746268656803}}}, "OUT_OF_SCOPE_PREFIX": {"CANDIDATE": {"10D": {"mean": 7.469314818188391, "median": 0.42474873292672743, "n": 966, "p25": -5.699538343164926, "p75": 13.603840370880839}, "5D": {"mean": 0.3842799173948395, "median": -1.573130157828062, "n": 992, "p25": -6.10386276464015, "p75": 3.961117514264212}}, "PRIMARY_CONTROL": {"10D": {"mean": 4.189803157376621, "median": -1.2444946357989817, "n": 5770, "p25": -8.840368598581723, "p75": 10.903900573813791}, "5D": {"mean": 0.7191407497289033, "median": -3.159407138536002, "n": 5818, "p25": -10.710464642347665, "p75": 5.039455689277905}}}, "STAR": {"CANDIDATE": {"10D": {"mean": 0.9116859443923329, "median": -0.22918258212375475, "n": 1337, "p25": -6.088004822182036, "p75": 5.609915198956306}, "5D": {"mean": -0.7299738104189838, "median": -0.7763791313686985, "n": 1380, "p25": -5.20603805946552, "p75": 2.7685357427584267}}, "PRIMARY_CONTROL": {"10D": {"mean": 1.1712343024796656, "median": -0.41695642095503915, "n": 19428, "p25": -7.069240061497911, "p75": 6.525490215347523}, "5D": {"mean": -0.0028144956157186867, "median": -0.9449694274596854, "n": 19701, "p25": -5.865986552283797, "p75": 4.213298222514816}}}}
- Prior distributions: {"CANDIDATE": {"median_traded_amount20": {"mean": 260055011.26908654, "median": 78178698.39, "n": 21988, "p25": 38793846.925, "p75": 196583890.695}, "prior_return20": {"mean": 0.1136105978504561, "median": 0.09027370717728278, "n": 21988, "p25": 0.054339218777397336, "p75": 0.14666666666666672}, "prior_volatility20_pct": {"mean": 2.2950724692512674, "median": 1.9202220628839832, "n": 21988, "p25": 1.2796853621426512, "p75": 2.985075750565514}}, "PRIMARY_CONTROL": {"median_traded_amount20": {"mean": 462321365.1889698, "median": 127117521.00999999, "n": 173476, "p25": 52228154.0, "p75": 366779777.65999997}, "prior_return20": {"mean": 0.22854417226350057, "median": 0.15564202334630362, "n": 173476, "p25": 0.08544620675668835, "p75": 0.28096225925515717}, "prior_volatility20_pct": {"mean": 3.4569713471801102, "median": 3.1121852747055363, "n": 173476, "p25": 1.98305444627961, "p75": 4.443268158170442}}}

## Input and execution boundaries

- Input audit: `PASS`; OHLC basis=`{'event_filter': 'date < ex_date <= T', 'event_order': 'ascending ex_date', 'formula': '(price - dividend_per_share + allotment_price*allotment_ratio)/(1 + per_share_bonus + allotment_ratio)', 'name': 'HISTORICAL_T_ANCHOR_PRICE_RAW_VOLUME', 'price_fields_adjusted': ['open', 'high', 'low', 'close'], 'provider_forward_used_as_t_anchor': False, 'volume_semantics': 'raw unadjusted volume'}`; universe identity=`dbc5d220f24f51a0245d047b88733c961fc4f184d02ef6f5ac0fc795576217b0`.
- Reference entry: T+1 XSHG open; `REFERENCE_EXECUTION_NOT_ACTUAL_FILL`.
- Execution/status coverage: {"CANDIDATE": {"10D": {"AVAILABLE": 21365, "INCOMPLETE_STOCK_WINDOW": 65, "INSUFFICIENT_FORWARD_COVERAGE": 487, "NO_T_PLUS_1_OPEN": 71}, "5D": {"AVAILABLE": 21764, "INCOMPLETE_STOCK_WINDOW": 23, "INSUFFICIENT_FORWARD_COVERAGE": 130, "NO_T_PLUS_1_OPEN": 71}}, "PRIMARY_CONTROL": {"10D": {"AVAILABLE": 169781, "INCOMPLETE_STOCK_WINDOW": 936, "INSUFFICIENT_FORWARD_COVERAGE": 2176, "NO_T_PLUS_1_OPEN": 583}, "5D": {"AVAILABLE": 171656, "INCOMPLETE_STOCK_WINDOW": 492, "INSUFFICIENT_FORWARD_COVERAGE": 745, "NO_T_PLUS_1_OPEN": 583}}}
- Historical PIT size and sector explanations: unresolved/not available for this V1 identification.
- B signal overlap (membership only): {"b_memberships_in_research_dates": 17714, "b_share_overlapping_candidate": 0.000508072710850175, "candidate_share_overlapping_b": 0.00040931417136619975, "same_date_overlap": 745, "same_symbol_date_overlap": 9, "source": {"file_sha256": "8940a4a346ac6911ba669f84a9ceba7ef878b0ed0ce51edf673439b52aa056b9", "logical_path": "data/validation/strategy_candidate_eligibility_v1/b_breakout_retest_eligibility_events.jsonl.gz", "outcomes_accessed": false, "rows_read_for_signal_membership": 17714, "unique_signal_memberships": 17714}}
- RS signal overlap: NOT_AVAILABLE; no canonical RS membership detail was lawfully available.
- Limit-state classification: LIMIT_STATE_EXECUTION_CLASSIFICATION_NOT_AVAILABLE.
- Transaction-cost model: TRANSACTION_COST_MODEL_NOT_PREEXISTING; reported returns are gross.

## Interpretation limit

The fixed result, if positive, is only DEVELOPMENT incremental predictive evidence over the generic-breakout control. Mechanism remains HYPOTHESIS; this is not production-ready, frozen, causal, portfolio-alpha, or Final OOS evidence.

## Governance

B and its prospective observation remain unchanged; RS, Volume-Path and turnover/RV remain unchanged; C, controlled reversal, Final OOS and the forbidden directory were not read; no provider replacement, parameter tuning, promotion, freeze or follow-up candidate was started.
