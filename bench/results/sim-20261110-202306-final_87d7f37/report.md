# C4: final comparison
Synthetic traces (demand/capacity = 2, 200 users, 100 rounds, 5 seeds, same trace for every system). Means over seeds. *Timely success* = share of all requests served within 3 rounds.

## Scenario: steady
| system | timely | success | util | p95 wait | Jain | Gini | zero-seat users | heavy share | never admitted | queue peak |
|---|---|---|---|---|---|---|---|---|---|---|
| FAIR_SHARE | 0.262 | 0.500 | 1.000 | 10.0 | 0.909 | 0.179 | 0.000 | 0.295 | 0.000 | 362 |
| FAIR_SHARE + bucket | 0.265 | 0.500 | 1.000 | 10.0 | 0.910 | 0.178 | 0.000 | 0.294 | 0.292 | 188 |
| FAIR_SHARE + credits | 0.368 | 0.500 | 1.000 | 8.0 | 0.912 | 0.179 | 0.000 | 0.292 | 0.480 | 78 |
| FAIR_SHARE + gap3 | 0.262 | 0.500 | 1.000 | 10.0 | 0.908 | 0.179 | 0.000 | 0.296 | 0.000 | 364 |
| FAIR_SHARE_D | 0.283 | 0.500 | 1.000 | 10.0 | 0.913 | 0.178 | 0.000 | 0.290 | 0.000 | 358 |
| FIFO | 0.034 | 0.500 | 1.000 | 10.0 | 0.476 | 0.171 | 0.008 | 0.599 | 0.000 | 477 |
| FIFO + bucket | 0.039 | 0.500 | 1.000 | 10.0 | 0.814 | 0.181 | 0.000 | 0.357 | 0.292 | 304 |

Difference from FIFO (paired by seed, mean +/- 95% CI; * = interval excludes 0):
| system | timely_rate | jain_alloc | chance_gini | wait_p95 |
|---|---|---|---|---|
| FAIR_SHARE | +0.228 +/- 0.016* | +0.433 +/- 0.012* | +0.008 +/- 0.011 | +0.000 +/- 0.000 |
| FAIR_SHARE + bucket | +0.231 +/- 0.016* | +0.434 +/- 0.012* | +0.007 +/- 0.012 | +0.000 +/- 0.000 |
| FAIR_SHARE + credits | +0.334 +/- 0.007* | +0.436 +/- 0.013* | +0.008 +/- 0.011 | -2.000 +/- 0.000* |
| FAIR_SHARE + gap3 | +0.228 +/- 0.013* | +0.432 +/- 0.011* | +0.008 +/- 0.012 | +0.000 +/- 0.000 |
| FAIR_SHARE_D | +0.249 +/- 0.008* | +0.437 +/- 0.013* | +0.007 +/- 0.011 | +0.000 +/- 0.000 |
| FIFO + bucket | +0.005 +/- 0.004* | +0.338 +/- 0.011* | +0.010 +/- 0.006* | +0.000 +/- 0.000 |

Pareto frontier (timely success vs Jain index): FAIR_SHARE + credits, FAIR_SHARE_D

Best per metric: timely_rate: FAIR_SHARE + credits (0.368); success_rate: FAIR_SHARE (0.500); utilization: FAIR_SHARE (1.000); wait_p95: FAIR_SHARE + credits (8.000); jain_alloc: FAIR_SHARE_D (0.913); chance_gini: FIFO (0.171); zero_alloc_rate: FAIR_SHARE (0.000); gave_up_rate: FAIR_SHARE (0.000); queue_peak: FAIR_SHARE + credits (78.200)

## Scenario: bursty heavy users
| system | timely | success | util | p95 wait | Jain | Gini | zero-seat users | heavy share | never admitted | queue peak |
|---|---|---|---|---|---|---|---|---|---|---|
| FAIR_SHARE | 0.256 | 0.500 | 1.000 | 10.0 | 0.919 | 0.180 | 0.000 | 0.288 | 0.000 | 437 |
| FAIR_SHARE + bucket | 0.258 | 0.500 | 1.000 | 10.0 | 0.920 | 0.180 | 0.000 | 0.286 | 0.285 | 200 |
| FAIR_SHARE + credits | 0.356 | 0.500 | 1.000 | 8.4 | 0.921 | 0.181 | 0.000 | 0.283 | 0.471 | 88 |
| FAIR_SHARE + gap3 | 0.253 | 0.500 | 1.000 | 10.0 | 0.919 | 0.181 | 0.000 | 0.288 | 0.000 | 439 |
| FAIR_SHARE_D | 0.284 | 0.500 | 1.000 | 10.0 | 0.919 | 0.180 | 0.000 | 0.286 | 0.000 | 432 |
| FIFO | 0.020 | 0.500 | 1.000 | 10.0 | 0.712 | 0.180 | 0.002 | 0.422 | 0.000 | 553 |
| FIFO + bucket | 0.021 | 0.500 | 1.000 | 10.0 | 0.865 | 0.185 | 0.000 | 0.315 | 0.285 | 304 |

Difference from FIFO (paired by seed, mean +/- 95% CI; * = interval excludes 0):
| system | timely_rate | jain_alloc | chance_gini | wait_p95 |
|---|---|---|---|---|
| FAIR_SHARE | +0.236 +/- 0.037* | +0.207 +/- 0.020* | +0.001 +/- 0.009 | +0.000 +/- 0.000 |
| FAIR_SHARE + bucket | +0.238 +/- 0.039* | +0.208 +/- 0.020* | +0.001 +/- 0.009 | +0.000 +/- 0.000 |
| FAIR_SHARE + credits | +0.336 +/- 0.006* | +0.208 +/- 0.019* | +0.001 +/- 0.010 | -1.600 +/- 0.680* |
| FAIR_SHARE + gap3 | +0.233 +/- 0.033* | +0.206 +/- 0.020* | +0.001 +/- 0.009 | +0.000 +/- 0.000 |
| FAIR_SHARE_D | +0.265 +/- 0.009* | +0.206 +/- 0.018* | +0.001 +/- 0.008 | +0.000 +/- 0.000 |
| FIFO + bucket | +0.000 +/- 0.001 | +0.153 +/- 0.019* | +0.005 +/- 0.006 | +0.000 +/- 0.000 |

Pareto frontier (timely success vs Jain index): FAIR_SHARE + credits

Best per metric: timely_rate: FAIR_SHARE + credits (0.356); success_rate: FAIR_SHARE (0.500); utilization: FAIR_SHARE (1.000); wait_p95: FAIR_SHARE + credits (8.400); jain_alloc: FAIR_SHARE + credits (0.921); chance_gini: FIFO (0.180); zero_alloc_rate: FAIR_SHARE (0.000); gave_up_rate: FAIR_SHARE (0.000); queue_peak: FAIR_SHARE + credits (88.000)

## Scenario: flash crowd
| system | timely | success | util | p95 wait | Jain | Gini | zero-seat users | heavy share | never admitted | queue peak |
|---|---|---|---|---|---|---|---|---|---|---|
| FAIR_SHARE | 0.334 | 0.495 | 0.990 | 10.0 | 0.624 | 0.170 | 0.000 | 0.495 | 0.000 | 2054 |
| FAIR_SHARE + bucket | 0.353 | 0.479 | 0.957 | 9.0 | 0.652 | 0.182 | 0.000 | 0.477 | 0.367 | 642 |
| FAIR_SHARE + credits | 0.393 | 0.480 | 0.961 | 9.0 | 0.629 | 0.172 | 0.000 | 0.492 | 0.483 | 196 |
| FAIR_SHARE + gap3 | 0.274 | 0.471 | 0.942 | 10.0 | 0.664 | 0.179 | 0.000 | 0.470 | 0.000 | 2095 |
| FAIR_SHARE_D | 0.351 | 0.495 | 0.990 | 9.8 | 0.613 | 0.170 | 0.000 | 0.502 | 0.000 | 2055 |
| FIFO | 0.215 | 0.495 | 0.990 | 10.0 | 0.475 | 0.170 | 0.006 | 0.603 | 0.000 | 2060 |
| FIFO + bucket | 0.352 | 0.480 | 0.959 | 9.0 | 0.600 | 0.175 | 0.002 | 0.510 | 0.367 | 645 |

Difference from FIFO (paired by seed, mean +/- 95% CI; * = interval excludes 0):
| system | timely_rate | jain_alloc | chance_gini | wait_p95 |
|---|---|---|---|---|
| FAIR_SHARE | +0.119 +/- 0.013* | +0.148 +/- 0.014* | +0.000 +/- 0.007 | +0.000 +/- 0.000 |
| FAIR_SHARE + bucket | +0.138 +/- 0.019* | +0.176 +/- 0.008* | +0.012 +/- 0.009* | -1.000 +/- 0.000* |
| FAIR_SHARE + credits | +0.178 +/- 0.008* | +0.153 +/- 0.012* | +0.002 +/- 0.006 | -1.000 +/- 0.000* |
| FAIR_SHARE + gap3 | +0.059 +/- 0.010* | +0.188 +/- 0.012* | +0.009 +/- 0.006* | +0.000 +/- 0.000 |
| FAIR_SHARE_D | +0.136 +/- 0.012* | +0.137 +/- 0.013* | -0.000 +/- 0.009 | -0.200 +/- 0.555 |
| FIFO + bucket | +0.137 +/- 0.025* | +0.125 +/- 0.008* | +0.006 +/- 0.007 | -1.000 +/- 0.000* |

Pareto frontier (timely success vs Jain index): FAIR_SHARE + bucket, FAIR_SHARE + credits, FAIR_SHARE + gap3

Best per metric: timely_rate: FAIR_SHARE + credits (0.393); success_rate: FAIR_SHARE_D (0.495); utilization: FAIR_SHARE_D (0.990); wait_p95: FAIR_SHARE + bucket (9.000); jain_alloc: FAIR_SHARE + gap3 (0.664); chance_gini: FAIR_SHARE_D (0.170); zero_alloc_rate: FAIR_SHARE (0.000); gave_up_rate: FAIR_SHARE (0.000); queue_peak: FAIR_SHARE + credits (196.200)

## Notes
- Door-rejected requests count as unserved attempts. `chance_gap` is the light users' mean chance minus the heavy users', so it is reported but not ranked.
- Limiter parameters are identical across systems and not tuned per scenario.
- Traces are synthetic; conclusions are about relative behaviour under stated assumptions.
