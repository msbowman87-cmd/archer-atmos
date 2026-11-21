# Atmos regional preparation and first real-observation benchmark — 2026-11-18

Research branch only: research/daily-walk-forward-20261101. Production main is unchanged.

## Verified execution

- [Regional QC and neighbor preparation](https://github.com/msbowman87-cmd/archer-atmos/actions/runs/44320995381): passed, with a downloadable regional-preparation artifact.
- [Real NOAA regional temperature benchmark](https://github.com/msbowman87-cmd/archer-atmos/actions/runs/44323318189): passed, with a downloadable real-observation benchmark artifact.
- No complete Atmos regional forecast model was certified or deployed.

## Station preparation

- Inventory: 6,809 candidate locations; 6,166 pass initial historical coverage screening; 643 have insufficient training coverage.
- Neighbor graph: 6,150 candidates with one or more neighbors within 300 km; 16 without eligible neighbors.
- Geographic tile allocation: 5,039 training targets, 1,127 spatial evaluation targets.
- Up to 20 neighbors for each candidate, with overlap in training years and variables. Spatial holdout stations are excluded as training input neighbors.
- Audit covers 144,924 completed source periods, 20 provider-variable profiles and 70 observed quality-flag types.
- Source quality flags are not certified good-hour counts. The original observations and provenance are unchanged.

## Unit conversions and quality controls

Source-aware screening is implemented in scripts/atmos_quality_policy.py.

- IEM temperature Fahrenheit to Celsius; wind knots to m/s; precipitation inches to mm; altimeter inHg to hPa; sea-level pressure remains distinct.
- ECCC station pressure kPa to hPa; wind km/h to m/s; wind direction tens of degrees to degrees.
- NOAA GHCNh recorded units and per-source quality-code interpretation. Unrecognized quality-code/source pairs fail closed.
- Station pressure, sea-level pressure, and altimeter values are never silently mixed.
- IEM and ECCC unflagged observations are provisional, not independent instrument certification.
- Canadian NOAA GHCNh source 341 carried blank quality codes in the first pilot cluster, so it was excluded from the strict initial training benchmark, not discarded.

Official source references:
- https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/doc/ghcnh_DOCUMENTATION.pdf
- https://mesonet.agron.iastate.edu/request/download.phtml?network=IA
- https://www.canada.ca/en/environment-climate-change/services/climate-change/canadian-centre-climate-services/display-download/technical-documentation-hourly-data.html

## Bounded genuine-archive regional benchmark

The source files were recovered from verifiable Atmos research releases and checked by ZIP and original source SHA256.

- NOAA GHCNh target USW00094129; neighbors USW00024149, USW00024157, USW00094176.
- Variable: temperature (Celsius); lead time: 24 hours.
- Fitting: 2022–2023, 17,384 paired samples.
- Validation: 2024, 8,760 paired cases.
- Evaluation: 2025, 8,517 paired cases.
- Forecast issue features are limited to observations before issue minus an assumed 72-hour delivery delay. Original publication timestamps are unavailable; this lag is not independently verified.
- Separate station-only and regional ridge regressions were scored on the same timestamp set against a persistence baseline. Neighbor elevation correction uses a simplified fixed 6.5 C/km lapse-rate assumption.

| Period | Persistence MAE (C) | Station-only MAE (C) | Regional MAE (C) | Regional skill relative to station-only |
|---|---:|---:|---:|---:|
| 2024 validation | 4.2176 | 3.5776 | 3.5936 | -0.45% (worse) |
| 2025 evaluation | 4.2247 | 3.4137 | 3.4081 | +0.16% (better) |

These are exploratory retrospective benchmarks only. The 2025 absolute gain of 0.0056 C is extremely small, and the 2024 regional result is worse. There is no basis for claiming improved forecast skill overall. No spatially held-out station was used as the target in this pilot.

No radar, satellite, dynamic upwind weighting, pressure, precipitation or other weather-variable model was fitted. Full archive row-level quality certification has not been completed and no model was deployed.

## Next steps after first baseline

1. Interpret QC source and flag semantics across the full archived dataset and publish per-variable qualifying observed-hour counts; preserve original observations and rejected readings in the raw archive.
2. Expand training and evaluation to many disjoint geographic tiles and climates while preserving independent 2024/2025 temporal tests.
3. Add real wind direction and speed for issue-time upwind weighting, then compare identical target cases and geographic holdouts.
4. Train pressure, humidity, precipitation and other weather variables separately with individual calibration; add radar and satellite only after provenance and timing audits.
5. Compute uncertainty and evaluate by season, terrain and extreme-event categories before any production promotion.
