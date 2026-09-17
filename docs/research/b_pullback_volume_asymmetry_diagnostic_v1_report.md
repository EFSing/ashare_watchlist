# B Pullback Volume Asymmetry Diagnostic V1 Report

DEVELOPMENT / DIAGNOSTIC_ONLY / INDEPENDENT_PROTOCOL. Formal B is unchanged.

## 1. Question

Test whether fixed pullback volume observables distinguish TARGET from FAST_STOP in the #66 frozen cohort.

## 2. Frozen cohort

Rows=17714; TARGET=4338; FAST_STOP=4623; all STOP=7953; unique episodes=9766.

Primary is TARGET versus FAST_STOP. Secondary is TARGET versus all STOP, with FAST_STOP included once.

## 3. Feature definitions

- `down_volume_share`: sum(volume on close[d] < close[d-1] days in R) / sum(volume in R).
- `up_down_volume_ratio`: mean(up-day volume in R) / mean(down-day volume in R); both classes required.
- `worst_price_day_volume_ratio`: volume on earliest minimum low[d]/L day in R / volume[i].
- `pullback_volume_decay_ratio`: mean(volume in later half of R) / mean(volume in earlier half of R); len(R)>=4.
- `reactivation_vs_pullback_volume`: exact alias of existing reactivation_vs_retest_ratio = volume[T] / mean(volume[i+1:T]).
- Exact path: #66 `_first_breakout_trace`, breakout level `L=base_hi`, and pullback `R=i+1:T-1`; signal day T is excluded.
- Price-defense control: exact #66 `max_retest_depth_vs_breakout_level`.

## 4. Overall result

| feature | TARGET median | FAST_STOP median | TARGET IQR | FAST_STOP IQR | missing | direction | all-STOP direction |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `down_volume_share` | 0.552069 | 0.566183 | 0.221707 | 0.211664 | 1368 | YES | YES |
| `up_down_volume_ratio` | 1.098455 | 1.059305 | 0.444822 | 0.396701 | 3414 | YES | YES |
| `worst_price_day_volume_ratio` | 0.408884 | 0.402751 | 0.229518 | 0.235569 | 1368 | NO | NO |
| `pullback_volume_decay_ratio` | 0.613563 | 0.648121 | 0.285954 | 0.315637 | 4278 | YES | YES |
| `reactivation_vs_pullback_volume` | 0.730660 | 0.769322 | 0.378891 | 0.393096 | 1368 | NO | NO |

The direction column requires the pre-registered median and fixed-tertile endpoint comparison.

## 5. Main Board

| feature | TARGET median | FAST_STOP median | TARGET IQR | FAST_STOP IQR | missing | direction | all-STOP direction |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `down_volume_share` | 0.533469 | 0.561461 | 0.220434 | 0.223654 | 899 | YES | YES |
| `up_down_volume_ratio` | 1.124841 | 1.050919 | 0.456959 | 0.417509 | 2221 | YES | YES |
| `worst_price_day_volume_ratio` | 0.415869 | 0.415458 | 0.227162 | 0.249148 | 899 | NO | NO |
| `pullback_volume_decay_ratio` | 0.593288 | 0.641504 | 0.270871 | 0.316188 | 2835 | YES | YES |
| `reactivation_vs_pullback_volume` | 0.726392 | 0.767983 | 0.363830 | 0.408239 | 899 | NO | NO |

## 6. Year split

| feature | year | TARGET median | FAST_STOP median | direction | all-STOP direction |
| --- | --- | ---: | ---: | --- | --- |
| `down_volume_share` | 2023 | 0.573189 | 0.597074 | YES | YES |
| `down_volume_share` | 2024 | 0.502331 | 0.533705 | YES | YES |
| `down_volume_share` | 2025 | 0.587621 | 0.585943 | NO | NO |
| `down_volume_share` | 2026 | 0.595924 | 0.575055 | NO | NO |
| `up_down_volume_ratio` | 2023 | 1.090998 | 1.029797 | YES | YES |
| `up_down_volume_ratio` | 2024 | 1.175775 | 1.094896 | YES | YES |
| `up_down_volume_ratio` | 2025 | 1.019834 | 1.039025 | NO | NO |
| `up_down_volume_ratio` | 2026 | 1.049196 | 1.040067 | YES | NO |
| `worst_price_day_volume_ratio` | 2023 | 0.364922 | 0.375078 | NO | YES |
| `worst_price_day_volume_ratio` | 2024 | 0.392615 | 0.387198 | NO | NO |
| `worst_price_day_volume_ratio` | 2025 | 0.420608 | 0.415617 | NO | NO |
| `worst_price_day_volume_ratio` | 2026 | 0.466977 | 0.438515 | NO | NO |
| `pullback_volume_decay_ratio` | 2023 | 0.633610 | 0.583770 | NO | NO |
| `pullback_volume_decay_ratio` | 2024 | 0.564119 | 0.661477 | YES | YES |
| `pullback_volume_decay_ratio` | 2025 | 0.652811 | 0.642200 | NO | NO |
| `pullback_volume_decay_ratio` | 2026 | 0.661364 | 0.677800 | YES | NO |
| `reactivation_vs_pullback_volume` | 2023 | 0.694683 | 0.717745 | NO | NO |
| `reactivation_vs_pullback_volume` | 2024 | 0.726308 | 0.775232 | NO | NO |
| `reactivation_vs_pullback_volume` | 2025 | 0.729497 | 0.765289 | NO | NO |
| `reactivation_vs_pullback_volume` | 2026 | 0.760108 | 0.800251 | NO | NO |

## 7. Unique episode

| feature | TARGET median | FAST_STOP median | TARGET IQR | FAST_STOP IQR | missing | direction | all-STOP direction |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `down_volume_share` | 0.572559 | 0.574374 | 0.223828 | 0.217598 | 1368 | YES | YES |
| `up_down_volume_ratio` | 1.109383 | 1.078440 | 0.470604 | 0.408850 | 2641 | YES | YES |
| `worst_price_day_volume_ratio` | 0.416473 | 0.406395 | 0.230424 | 0.235376 | 1368 | NO | NO |
| `pullback_volume_decay_ratio` | 0.600971 | 0.640610 | 0.258663 | 0.313749 | 2966 | YES | YES |
| `reactivation_vs_pullback_volume` | 0.714836 | 0.768247 | 0.389794 | 0.413871 | 1368 | NO | NO |

Unique episode view keeps the earliest qualified signal per `(symbol, breakout_date)`.

## 8. Two matrices

#### `down_volume_share` × price defense

| price defense | volume tertile | cell count | TARGET | FAST_STOP | all STOP | FAST_STOP rate | STOP rate |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| LOW | LOW | 2175 | 457 | 322 | 776 | 0.413350 | 0.629359 |
| LOW | MID | 1338 | 282 | 243 | 518 | 0.462857 | 0.647500 |
| LOW | HIGH | 1936 | 383 | 464 | 919 | 0.547816 | 0.705837 |
| MID | LOW | 1647 | 509 | 336 | 664 | 0.397633 | 0.566070 |
| MID | MID | 1908 | 491 | 513 | 856 | 0.510956 | 0.635486 |
| MID | HIGH | 1894 | 482 | 503 | 832 | 0.510660 | 0.633181 |
| HIGH | LOW | 1627 | 414 | 550 | 815 | 0.570539 | 0.663141 |
| HIGH | MID | 2203 | 593 | 796 | 1144 | 0.573074 | 0.658607 |
| HIGH | HIGH | 1618 | 441 | 522 | 769 | 0.542056 | 0.635537 |

#### `worst_price_day_volume_ratio` × price defense

| price defense | volume tertile | cell count | TARGET | FAST_STOP | all STOP | FAST_STOP rate | STOP rate |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| LOW | LOW | 1253 | 260 | 231 | 493 | 0.470468 | 0.654714 |
| LOW | MID | 1632 | 353 | 291 | 610 | 0.451863 | 0.633437 |
| LOW | HIGH | 2564 | 509 | 507 | 1110 | 0.499016 | 0.685608 |
| MID | LOW | 2077 | 546 | 509 | 884 | 0.482464 | 0.618182 |
| MID | MID | 1876 | 528 | 428 | 771 | 0.447699 | 0.593533 |
| MID | HIGH | 1496 | 408 | 415 | 697 | 0.504253 | 0.630769 |
| HIGH | LOW | 2119 | 551 | 729 | 1074 | 0.569531 | 0.660923 |
| HIGH | MID | 1941 | 514 | 678 | 980 | 0.568792 | 0.655957 |
| HIGH | HIGH | 1388 | 383 | 461 | 674 | 0.546209 | 0.637654 |

## 9. Reactivation incremental check

F5 is a direct alias of #66 `reactivation_vs_retest_ratio`; it was not recomputed against breakout volume.

Incremental information established: `NO`; F5 is exactly #66 reactivation_vs_retest_ratio; no additional model or matrix is permitted.

Descriptive pullback day-pair counts (not features or rules):

| label | A | B | C | D | OTHER |
| --- | ---: | ---: | ---: | ---: | ---: |
| FAST_STOP | 16255 | 7868 | 7292 | 3990 | 109 |
| OTHER | 16698 | 8838 | 7518 | 4155 | 159 |
| STOP | 10157 | 5500 | 4692 | 2551 | 114 |
| TARGET | 14570 | 7633 | 6584 | 3823 | 141 |

## 10. Falsification

- H1-H4 overall supported count: `3/4`; Main Board: `3/4`.
- H1-H4 unique-episode supported count: `3/4`; year majority non-reversed count: `1/4`.
- H1-H4 secondary all-STOP supported count: `3/4`.
- Matrix A consistent: `NO`; Matrix B consistent: `NO`.
- No threshold, window, tertile, label, technical indicator, or small-cell rule was selected after observing results.

## 11. Conclusion

Terminal status: `B_PULLBACK_VOLUME_ASYMMETRY_PROSPECTIVE_EVIDENCE_REQUIRED`.
Formal B remains unchanged; no B V2, prospective deployment, production dispatch, or runtime-state mutation is created.

## Provenance

Protocol commit: `d0a477db3f375ef19fdec51bb091ac3162ea6278`; source branch: `codex/b-false-breakout-path-diagnostic-v1`; source head: `9dcd93f6460006eed9f1d0e421b45c3abe5adc99`.
Production dispatch=0; runtime-state mutation=0; Final OOS=SEALED / UNREAD.
