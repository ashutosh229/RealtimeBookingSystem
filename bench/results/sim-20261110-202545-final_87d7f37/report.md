# C4: final comparison
Synthetic traces (demand/capacity = 2, 200 users, 100 rounds, 30 seeds, same trace for every system). Means over seeds. *Timely success* = share of all requests served within 3 rounds.

## Scenario: steady
| system | timely | success | util | p95 wait | Jain | Gini | zero-seat users | heavy share | never admitted | queue peak |
|---|---|---|---|---|---|---|---|---|---|---|
| FAIR_SHARE | 0.255 | 0.500 | 1.000 | 10.0 | 0.914 | 0.181 | 0.000 | 0.292 | 0.000 | 370 |
| FAIR_SHARE + bucket | 0.256 | 0.500 | 1.000 | 10.0 | 0.915 | 0.181 | 0.000 | 0.290 | 0.286 | 201 |
| FAIR_SHARE + credits | 0.362 | 0.500 | 1.000 | 8.3 | 0.915 | 0.181 | 0.000 | 0.290 | 0.478 | 79 |
| FAIR_SHARE + gap3 | 0.254 | 0.500 | 1.000 | 10.0 | 0.913 | 0.181 | 0.000 | 0.293 | 0.000 | 370 |
| FAIR_SHARE_D | 0.276 | 0.500 | 1.000 | 10.0 | 0.916 | 0.181 | 0.000 | 0.287 | 0.000 | 360 |
| FIFO | 0.035 | 0.500 | 1.000 | 10.0 | 0.476 | 0.169 | 0.007 | 0.600 | 0.000 | 479 |
| FIFO + bucket | 0.040 | 0.500 | 1.000 | 10.0 | 0.815 | 0.183 | 0.000 | 0.357 | 0.286 | 309 |

Difference from FIFO (paired by seed, mean +/- 95% CI; * = interval excludes 0):
| system | timely_rate | jain_alloc | chance_gini | wait_p95 |
|---|---|---|---|---|
| FAIR_SHARE | +0.219 +/- 0.006* | +0.437 +/- 0.003* | +0.013 +/- 0.004* | +0.000 +/- 0.000 |
| FAIR_SHARE + bucket | +0.221 +/- 0.006* | +0.439 +/- 0.003* | +0.012 +/- 0.004* | +0.000 +/- 0.000 |
| FAIR_SHARE + credits | +0.326 +/- 0.003* | +0.439 +/- 0.003* | +0.013 +/- 0.004* | -1.700 +/- 0.174* |
| FAIR_SHARE + gap3 | +0.218 +/- 0.006* | +0.436 +/- 0.003* | +0.013 +/- 0.004* | +0.000 +/- 0.000 |
| FAIR_SHARE_D | +0.241 +/- 0.003* | +0.440 +/- 0.003* | +0.012 +/- 0.004* | +0.000 +/- 0.000 |
| FIFO + bucket | +0.004 +/- 0.001* | +0.339 +/- 0.003* | +0.014 +/- 0.004* | +0.000 +/- 0.000 |

Pareto frontier (timely success vs Jain index): FAIR_SHARE + credits, FAIR_SHARE_D

Best per metric: timely_rate: FAIR_SHARE + credits (0.362); success_rate: FAIR_SHARE (0.500); utilization: FAIR_SHARE (1.000); wait_p95: FAIR_SHARE + credits (8.300); jain_alloc: FAIR_SHARE_D (0.916); chance_gini: FIFO (0.169); zero_alloc_rate: FAIR_SHARE (0.000); gave_up_rate: FAIR_SHARE (0.000); queue_peak: FAIR_SHARE + credits (79.200)

## Scenario: bursty heavy users
| system | timely | success | util | p95 wait | Jain | Gini | zero-seat users | heavy share | never admitted | queue peak |
|---|---|---|---|---|---|---|---|---|---|---|
| FAIR_SHARE | 0.256 | 0.500 | 1.000 | 10.0 | 0.918 | 0.181 | 0.000 | 0.289 | 0.000 | 438 |
| FAIR_SHARE + bucket | 0.260 | 0.500 | 1.000 | 9.8 | 0.919 | 0.180 | 0.000 | 0.288 | 0.286 | 201 |
| FAIR_SHARE + credits | 0.353 | 0.500 | 1.000 | 8.8 | 0.920 | 0.181 | 0.000 | 0.285 | 0.472 | 88 |
| FAIR_SHARE + gap3 | 0.254 | 0.500 | 1.000 | 10.0 | 0.917 | 0.181 | 0.000 | 0.290 | 0.000 | 440 |
| FAIR_SHARE_D | 0.283 | 0.500 | 1.000 | 10.0 | 0.918 | 0.181 | 0.000 | 0.288 | 0.000 | 431 |
| FIFO | 0.020 | 0.500 | 1.000 | 10.0 | 0.712 | 0.178 | 0.001 | 0.422 | 0.000 | 551 |
| FIFO + bucket | 0.021 | 0.500 | 1.000 | 10.0 | 0.865 | 0.184 | 0.000 | 0.315 | 0.286 | 307 |

Difference from FIFO (paired by seed, mean +/- 95% CI; * = interval excludes 0):
| system | timely_rate | jain_alloc | chance_gini | wait_p95 |
|---|---|---|---|---|
| FAIR_SHARE | +0.236 +/- 0.010* | +0.206 +/- 0.005* | +0.003 +/- 0.002* | +0.000 +/- 0.000 |
| FAIR_SHARE + bucket | +0.240 +/- 0.010* | +0.207 +/- 0.005* | +0.002 +/- 0.002* | -0.167 +/- 0.142* |
| FAIR_SHARE + credits | +0.333 +/- 0.003* | +0.208 +/- 0.005* | +0.003 +/- 0.002* | -1.233 +/- 0.161* |
| FAIR_SHARE + gap3 | +0.234 +/- 0.009* | +0.205 +/- 0.005* | +0.003 +/- 0.002* | +0.000 +/- 0.000 |
| FAIR_SHARE_D | +0.264 +/- 0.003* | +0.206 +/- 0.005* | +0.003 +/- 0.002* | +0.000 +/- 0.000 |
| FIFO + bucket | +0.001 +/- 0.000* | +0.153 +/- 0.005* | +0.006 +/- 0.002* | +0.000 +/- 0.000 |

Pareto frontier (timely success vs Jain index): FAIR_SHARE + credits

Best per metric: timely_rate: FAIR_SHARE + credits (0.353); success_rate: FAIR_SHARE (0.500); utilization: FAIR_SHARE (1.000); wait_p95: FAIR_SHARE + credits (8.767); jain_alloc: FAIR_SHARE + credits (0.920); chance_gini: FIFO (0.178); zero_alloc_rate: FAIR_SHARE (0.000); gave_up_rate: FAIR_SHARE (0.000); queue_peak: FAIR_SHARE + credits (87.900)

## Scenario: flash crowd
| system | timely | success | util | p95 wait | Jain | Gini | zero-seat users | heavy share | never admitted | queue peak |
|---|---|---|---|---|---|---|---|---|---|---|
| FAIR_SHARE | 0.328 | 0.495 | 0.990 | 10.0 | 0.629 | 0.168 | 0.000 | 0.492 | 0.000 | 2049 |
| FAIR_SHARE + bucket | 0.352 | 0.481 | 0.963 | 9.0 | 0.652 | 0.179 | 0.000 | 0.478 | 0.364 | 645 |
| FAIR_SHARE + credits | 0.393 | 0.482 | 0.965 | 9.0 | 0.630 | 0.170 | 0.000 | 0.492 | 0.482 | 194 |
| FAIR_SHARE + gap3 | 0.275 | 0.472 | 0.945 | 10.0 | 0.666 | 0.177 | 0.000 | 0.469 | 0.000 | 2084 |
| FAIR_SHARE_D | 0.343 | 0.495 | 0.990 | 10.0 | 0.616 | 0.168 | 0.000 | 0.501 | 0.000 | 2049 |
| FIFO | 0.215 | 0.495 | 0.990 | 10.0 | 0.474 | 0.172 | 0.006 | 0.602 | 0.000 | 2055 |
| FIFO + bucket | 0.360 | 0.482 | 0.964 | 9.0 | 0.602 | 0.172 | 0.002 | 0.510 | 0.364 | 647 |

Difference from FIFO (paired by seed, mean +/- 95% CI; * = interval excludes 0):
| system | timely_rate | jain_alloc | chance_gini | wait_p95 |
|---|---|---|---|---|
| FAIR_SHARE | +0.114 +/- 0.004* | +0.155 +/- 0.004* | -0.005 +/- 0.003* | +0.000 +/- 0.000 |
| FAIR_SHARE + bucket | +0.137 +/- 0.005* | +0.177 +/- 0.003* | +0.007 +/- 0.003* | -0.967 +/- 0.068* |
| FAIR_SHARE + credits | +0.178 +/- 0.003* | +0.155 +/- 0.003* | -0.002 +/- 0.004 | -1.033 +/- 0.068* |
| FAIR_SHARE + gap3 | +0.060 +/- 0.003* | +0.192 +/- 0.003* | +0.005 +/- 0.003* | +0.000 +/- 0.000 |
| FAIR_SHARE_D | +0.128 +/- 0.004* | +0.141 +/- 0.005* | -0.004 +/- 0.004 | -0.033 +/- 0.068 |
| FIFO + bucket | +0.145 +/- 0.006* | +0.127 +/- 0.003* | -0.000 +/- 0.003 | -1.000 +/- 0.000* |

Pareto frontier (timely success vs Jain index): FAIR_SHARE + bucket, FAIR_SHARE + credits, FAIR_SHARE + gap3

Best per metric: timely_rate: FAIR_SHARE + credits (0.393); success_rate: FAIR_SHARE_D (0.495); utilization: FIFO (0.990); wait_p95: FAIR_SHARE + credits (8.967); jain_alloc: FAIR_SHARE + gap3 (0.666); chance_gini: FAIR_SHARE (0.168); zero_alloc_rate: FAIR_SHARE (0.000); gave_up_rate: FAIR_SHARE (0.000); queue_peak: FAIR_SHARE + credits (193.733)

## Notes
- Door-rejected requests count as unserved attempts. `chance_gap` is the light users' mean chance minus the heavy users', so it is reported but not ranked.
- Limiter parameters are identical across systems and not tuned per scenario.
- Traces are synthetic; conclusions are about relative behaviour under stated assumptions.
