# B Turnover × Relative Volume Incremental Diagnostic V1 — Tushare gateway

Labels: `DEVELOPMENT` / `RECONSTRUCTED_RETROSPECTIVE` / `DATE_ANCHORED` / `NO_VINTAGE_PROOF` / `THIRD_PARTY_GATEWAY` / `DIAGNOSTIC_ONLY`

## Decision

`TURNOVER_X_RELATIVE_VOLUME_NEEDS_MORE_EVIDENCE`

A fixed turnover relationship is visible in part of the pre-registered diagnostic, but complete conditioned, strata and sensitivity coherence is not established.

## Provenance

- source: `THIRD_PARTY_TUSHARE_COMPATIBLE_GATEWAY` at `https://tuaremax.top`; `tushare==1.4.24`; endpoint `daily_basic`
- input audit: `data/validation/b_turnover_x_relative_volume_incremental_v1/tushare_gateway/manifest/input_audit_manifest.json`; status `RESEARCH_READY`
- pre-outcome protocol commit: `1148ebd23a567ad81e09b0c2323f9be285920858`
- exact cohort: `17714` qualified / `573586` structural; in-scope: `17008` / `543616`
- pair-complete qualified rows: `17008`; episode-deduplicated qualified rows: `9331`

## Fixed checks

- turnover 5D Q5-Q1 mean return: `-0.2775957832476869` percentage points
- turnover 5D Q5-Q1 median return: `-0.9697097923057951` percentage points
- turnover conditional on RV coherent: `False`
- year/board coherent: `False`
- episode-deduplicated coherent: `True`
- turnover top-1% coherent: `True`
- relative-volume top-1% coherent with turnover direction: `True`
- joint top-1% coherent: `True`
- structural coherent: `True`

## Pre-registered top-1% sensitivity

- eligible definition: `qualified in-scope cohort; each feature's top 1% is selected independently from its non-null rows using the existing stable-ranked definition; joint eligible rows require both feature values and the intersection is the exact membership intersection`
- turnover top-1% N: `171` (eligible rows: `17008`)
- relative-volume top-1% N: `171` (eligible rows: `17008`)
- joint intersection N: `11` (joint eligible rows: `17008`)
- comparison baseline: `qualified_pair_complete_non_joint` — the same qualified pair-complete cohort excluding the fixed joint intersection; outcome availability does not define membership

| Group | Horizon | N | Mean return | Median return | Positive rate | Mean MFE | Mean MAE |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| joint intersection | 5D | 11 | -0.002859459964440864 | 0.5105046141763214 | 0.5454545454545454 | 7.01647906309851 | -4.294153699503632 |
| joint intersection | 10D | 11 | -3.193592768836777 | -2.513253485175737 | 0.2727272727272727 | 8.954717023565955 | -7.134764935191731 |
| baseline (non-joint) | 5D | 16890 | 0.5887951204290701 | -0.0811166438592914 | 0.4886323268206039 | 5.581076798717208 | -3.9972144198024644 |
| baseline (non-joint) | 10D | 16847 | 1.3808100595866493 | 0.3620273531777851 | 0.5181337923665934 | 8.667530074089305 | -5.652147069296993 |
- joint minus baseline mean-return difference: 5D `-0.5916545803935109`, 10D `-4.574402828423427` percentage points

## 5×5 matrix

| TQ | RVQ | N | 5D mean | 5D median | 10D mean | 5D MFE | 5D MAE |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 939 | 0.2649226083984465 | -0.2174940898345079 | 1.2461715267362679 | 3.73270672221962 | -3.0286335560052935 |
| 1 | 2 | 851 | 0.5747434202472321 | 0.16683510310208094 | 1.7478975482160752 | 3.9846086190823313 | -2.8889881000834774 |
| 1 | 3 | 778 | 0.45850416003863576 | 0.0 | 1.2716015471900846 | 3.9889263901800165 | -2.823701890067576 |
| 1 | 4 | 555 | 0.6705340860186316 | 0.2135231316725994 | 1.09142514703067 | 3.9721053262030304 | -2.8141311084604896 |
| 1 | 5 | 279 | 0.2114736263873801 | -0.35927887901572864 | 0.1547123883983583 | 3.5149413993913274 | -2.922157099341476 |
| 2 | 1 | 763 | 0.5856209212645198 | -0.02608242044861986 | 1.7357979205291263 | 4.8786906490475115 | -3.5103071041763148 |
| 2 | 2 | 688 | 0.586411098696621 | 0.3965305785513795 | 1.7930415698854192 | 4.622604187800254 | -3.105906355738238 |
| 2 | 3 | 733 | 0.4635142001446211 | 0.14662756598240456 | 1.8888814732989427 | 4.628225867288937 | -3.2901649614081783 |
| 2 | 4 | 701 | 0.957894782434676 | 0.08064516129031585 | 2.2382259260485804 | 4.931814095864066 | -3.0817249365166166 |
| 2 | 5 | 517 | 0.8353693016463157 | 0.02983293556085842 | 1.136802763473704 | 4.532002408347273 | -2.825444832725488 |
| 3 | 1 | 745 | 0.9291485038681585 | -0.056899004267418896 | 1.6496569204580314 | 5.5970848002815075 | -4.024781336263026 |
| 3 | 2 | 663 | 0.7181207569545944 | 0.2538071065989911 | 3.0039712870147475 | 5.684707513071823 | -4.035835652231302 |
| 3 | 3 | 636 | 1.0248459509726342 | 0.3643408568566264 | 1.8283367380891764 | 5.594718640064024 | -3.6000447150066583 |
| 3 | 4 | 745 | 1.1253640067038828 | 0.44613104415552884 | 2.25815504722323 | 5.769573212259151 | -3.5551775443400513 |
| 3 | 5 | 612 | 0.9362881544887219 | -0.11890606420926764 | 1.2070188288776273 | 5.451887039892365 | -3.5973874267044708 |
| 4 | 1 | 618 | -0.25180708179658295 | -0.9201669291654557 | 0.14474580982570381 | 5.5770436494037705 | -5.0625509923272105 |
| 4 | 2 | 632 | 0.6434145356302984 | -0.3765845401922985 | 1.938095248930037 | 6.400762468542548 | -4.690534933756008 |
| 4 | 3 | 634 | 0.8823255602234108 | -0.0768639508070712 | 1.3286355021118637 | 6.290147751364766 | -4.429208491576408 |
| 4 | 4 | 691 | 1.12585091409892 | 0.6699147381242332 | 1.994952395311232 | 6.2784077942246395 | -4.063603214086539 |
| 4 | 5 | 827 | 0.9664602010648696 | -0.1134807753221112 | 1.606582800375345 | 6.038414631082373 | -3.9215979564408747 |
| 5 | 1 | 337 | -0.40992821450916445 | -1.3385826771653564 | -0.20420766189331274 | 6.38378286216578 | -5.34729551519587 |
| 5 | 2 | 568 | -0.23200828541340462 | -1.1604075554513815 | 0.46346277478113806 | 7.11058041828509 | -5.91468198289011 |
| 5 | 3 | 620 | 0.12699295359254695 | -0.9415262636273569 | 0.5969038422704105 | 7.758867449933617 | -5.840037995634524 |
| 5 | 4 | 710 | 0.6441665274514935 | -0.49676255104650346 | 0.911744971985008 | 8.146709999388952 | -5.833113273213086 |
| 5 | 5 | 1166 | 0.271901868810498 | -1.1137943439840148 | 0.14293658334575798 | 7.645184837952821 | -5.614044359540275 |

## Boundaries

B/spec/score/threshold/hard gate/Top-N/prospective pipeline/universe/frozen dataset were unchanged. Final OOS was not read; C and Phase 2F were not run; no threshold search, parameter sweep, model fitting, promotion or freeze occurred. `turnover_rate_f` was not used.

Event detail: `data/validation/b_turnover_x_relative_volume_incremental_v1/tushare_gateway/diagnostic/events.jsonl.gz` (local-only deterministic artifact). Summary SHA-256: `9d5aa71d8c3043b48dd5412e0198b434d3b159ba4408078173acb085f0b2eeac`.
