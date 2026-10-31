# Atmos Global Validation 1.0 — research protocol

## Coverage and honesty requirements

- Preserve the original 200-point cohort for reproducible comparisons. The expanded `atmos.global_grid.points()` cohort defaults to 5,000 equal-area worldwide coordinates and supports up to 20,000. These are **benchmark points**, never an end-user forecast coverage limit.
- The points cover both hemispheres and three latitude bands. They are **not** guaranteed to cover land, oceans, mountains, deserts, or particular Köppen climates. A curated, metadata-verified station cohort must complement them before claiming climate-stratified skill.
- Target at least twelve consecutive months of *issued forecasts* from GFS and ECMWF (not reanalysis masquerading as forecasts). Collect matching independently measured observations. Older 10-year Open-Meteo gridded archives support coverage research only.
- Record exact issue timestamp, UTC validity start/end, location/station identity, variable, units, quality flags, and source provenance. Unknown or unmatched values remain missing.
- Score the *same* forecast cases for both baseline models and the simple equal-weight blend. A model with less coverage must not be rewarded through an easier comparison cohort.
- Split training, selection, and final holdout chronologically; avoid future observations in predictors. Report sample size and unique verification days, because overlapping issue cycles are correlated.
- Report separately by horizon (1–3, 4–7, 8–14, 15–30 days), variable, continent, hemisphere, geographic zone, season, and verified climate classification **where that metadata exists**.
- The 15–30 day bucket must remain empty until genuine forecasts with those lead times have been acquired; do not extend shorter-range products artificially.
- Temperature MAE is not a severe-weather skill measure. Precipitation occurrence, amount, wind, and hazards require their own independent verification and uncertainty estimates.

## Implemented starting point

Generate the expanded manifest: `python -m atmos.global_grid --count 5000 --output global-grid-5000.csv`. These are geographic samples, not independent ground stations.


`python -m atmos.global_validation --forecasts issued.csv --observations truth.csv --output global-validation-report.json`

The two CSVs require the fields documented in `atmos/global_validation.py`. This script *scores supplied evidence only*: it neither downloads data nor generates forecasts. A zero-pair report is a valid, explicit insufficient-evidence result.

## Next collection milestone

1. Build a real cross-continental station registry with source identifiers, coordinates, elevation, time-zone-independent observation intervals, observation completeness, and land/climate tags.
2. Start bounded, incremental issued-forecast archival and independent-observation collection at those sites. Track requests, rate limits, byte budgets, failed cycles, and source/license constraints.
3. Produce a twelve-month paired comparison where available. Publish per-region missingness and paired-case counts alongside accuracy. Never declare Atmos globally better from the Twin Falls pilot.
4. Train regional and multi-model corrections only after genuine paired data is sufficient; test on untouched later months and different locations.

No change to public Atmos forecast output is authorized by this protocol.
