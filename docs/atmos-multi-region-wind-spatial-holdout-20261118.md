# Atmos multi-region, measured-upwind, spatial-holdout benchmark — 2026-11-18

## Outcome

The experimental wind-aware multi-region benchmark executed successfully. It **did not improve forecast accuracy on excluded geographic areas**. Do not promote these fitted weights, declare forecast-skill improvement, or deploy to production.

**Code and evidence**

- [Passed multi-region workflow](https://github.com/msbowman87-cmd/archer-atmos/actions/runs/44327373078)
- [Passed code test suite](https://github.com/msbowman87-cmd/archer-atmos/actions/runs/44327385898)
- Workflow artifact: atmos-multi-region-wind-spatial-benchmark (includes multi_region_wind_benchmark.json, source_screening.json, and the training-only neighbor graph).
- Implemented by scripts/atmos_multi_region_wind_pilot.py; tests/test_atmos_multi_region_wind_pilot.py; .github/workflows/atmos-multi-region-wind-pilot.yml.
- Research branch only: research/daily-walk-forward-20261101. Production main untouched.

## Method and safeguards

- Original source: 80 hash-verified NOAA GHCNh annual files, 20 distinct stations.
- Target: 24-hour air temperature (Celsius), using authentic NOAA temperature and measured wind direction/speed where source-aware QC accepts the readings.
- Training: 2022–2023 (52,065 paired training cases) across three geographically separated training-target tiles.
- Temporal validation: 2024. Temporal evaluation: 2025. Both are scored independently of the model fit.
- Geographic independence: two excluded 3-degree tiles; no forecast targets from these tiles appear in fitting. Neighbor selection excludes all predefined holdout target stations.
- Fixed model across regions: shared ridge model trained only on the training-target stations. Models use identical target timestamps and compare persistence, station-only, inverse-distance geographic, and observed-wind upwind weighting.
- Wind from direction is interpreted meteorologically; the neighbor must lie upwind of the target. Wind strength modulates weights. Missing or calm wind does not get fabricated as directional evidence.
- True historical data publication timestamps are unavailable: a conservative **assumed 72-hour source availability lag** was used. Do not mistake the results for verified real-time operational skill.
- Nearby station temperatures use a simplistic 6.5 Celsius per km elevation correction. This is a research sensitivity assumption, not a weather-dependent physical model.
- Checks passed without changing raw source data. Overall archive source quality is not yet production-certified.

The three training targets were NOAA IDs USW00094129 (46.7439, -117.1158), USW00004938 (41.6911, -93.5661), and USW00014922 (44.8853, -93.2314). The held-out targets were USW00004110 in southern Idaho (42.7272, -114.4547) and USW00014735 near Albany, New York (42.7472, -73.7992).

Valid wind-speed hours across all loaded source files totaled 694,214; **10,937 of 17,054 matched holdout forecasts in 2025** had sufficient upwind support to activate the direction-based feature.

## Measured forecast error on matching hours

MAE below means mean absolute temperature error in degrees Celsius; lower is better.

| Target group / year | Cases | Station-only MAE | Geographic MAE | Wind-weighted MAE | Wind vs station-only |
|---|---:|---:|---:|---:|---:|
| Training-tile targets, 2024 | 26,280 | 4.1754 | 4.1750 | 4.1704 | +0.120% |
| Training-tile targets, 2025 | 25,554 | 4.3417 | 4.3401 | 4.3399 | +0.043% |
| Excluded tiles, 2024 | 17,519 | **3.8289** | 3.8537 | 3.8504 | **-0.563%** |
| Excluded tiles, 2025 | 17,054 | **3.6391** | 3.6658 | 3.6646 | **-0.700%** |

**Geographic holdout detail:**

| Excluded station / year | Cases | Station-only MAE | Wind-weighted MAE | Relative skill |
|---|---:|---:|---:|---:|
| Southern Idaho (USW00004110), 2024 | 8,735 | 3.7434 | 3.7760 | -0.872% |
| Southern Idaho (USW00004110), 2025 | 8,522 | **3.5213** | 3.5555 | **-0.971%** |
| New York (USW00014735), 2024 | 8,784 | 3.9139 | 3.9244 | -0.268% |
| New York (USW00014735), 2025 | 8,532 | **3.7568** | 3.7736 | **-0.447%** |

In wind-active holdout cases only, wind-weighted performance was also worse: 2024 3.7802 versus station-only 3.7563 Celsius; 2025 3.7700 versus station-only 3.7399 Celsius. The output does **not** support a claim that the new regional wind feature improves forecasts.

## Paired uncertainty (conditional, not geographic generalization)

A fixed-seed daily-block bootstrap (350 replicates) resampled station-days of the paired absolute-error improvement (station-only MAE minus wind-weighted MAE). Positive means wind helped.

- Excluded 2024: -0.02154 Celsius mean improvement, descriptive 95% interval **[-0.02954, -0.01348]**.
- Excluded 2025: -0.02549 Celsius mean improvement, descriptive 95% interval **[-0.03496, -0.01748]**.

These intervals condition on just two selected stations; they do not quantify the uncertainty of generalizing to other geographic regions or operational forecasts. No production significance claim.

## Recommended next engineering stage

1. **Do not deploy this regression.** Keep the station-only baseline as the active comparator.
2. Improve the wind representation. The current feature weights neighbors using wind observed at a source time at least 96 hours before target verification (24h lead plus assumed 72h availability lag). Direct advection at that age is often not representative of future synoptic conditions. Verify actual NOAA observation availability characteristics or report separate defensible availability-lag sensitivity scenarios; do not silently assume zero lag.
3. Compare physically meaningful upstream history over several earlier timestamps, pressure tendencies, wind-vector components and elevation/terrain. Train variables separately, not with a single blanket bias.
4. Expand to many truly disjoint geographies and seasons. Reserve fixed 2025 verification and completely excluded station tiles. Select hyperparameters using only earlier training and 2024 validation, not the 2025 results.
5. Include radar/satellite only with archived acquisition and availability provenance. Require improvements in independently held-out regions with reported uncertainty for each variable and forecast lead.
6. Preserve original raw observations and uncertainty for all unsupported source quality flags. No blanket acceptance of Canadian source-code 341 empty quality flags.

**Release decision: BLOCKED for regional-wind skill improvement. Research infrastructure and source verification workflows passed.**
