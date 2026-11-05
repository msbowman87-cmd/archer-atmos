# Atmos satellite and radar calibration: implementation requirements

**Status (2026-11-05): Real GOES-16 and NEXRAD archive extraction is implemented and a two-station, one-scan pilot passed; a six-hour coverage backfill is running. Model training on these inputs is NOT implemented and accuracy has NOT been measured.** Do not describe V1 or V2 as satellite/radar informed.

## Forecast inputs

For each training location and issue hour, combine:
- Quality-controlled, previously available weather-station readings;
- Latitude, longitude and (when verified) elevation/terrain;
- Satellite cloud fraction, cloud-top temperature/height, water-vapor channel values and cloud motion;
- Radar reflectivity, precipitation rate and (where available) Doppler/echo motion.

Every feature is stamped with station_id, source product_id, observed_at_utc, and historically defensible available_at_utc. The prediction must use the last **actually available** remote-sensing measurement, never one created or received after the forecast issue. Satellite and radar have their own age thresholds and should not automatically inherit the assumed 72-hour NOAA surface-observation lag.

All 8 target variables and the 24-, 48-, 72-hour horizons keep separate model parameters and target-specific losses. Shared satellite/radar inputs do NOT imply the same calibration applied to temperature, pressure, wind, precipitation, etc. For rainfall we must score occurrence probability and amount independently; for visibility, low-visibility event probability and continuous error separately.

## Historical coverage and original sources

- United States: NEXRAD Level II/III historical observations (NCEI archive since 1991); AWS Open Data for distribution. Radar does not give global surface coverage.
- Americas: archival GOES imagery, and GOES-R Advanced Baseline Imager products from 2017 onward.
- Europe/Africa: EUMETSAT Meteosat historical imagery and derived products.
- Asia-Pacific: seek verified Himawari/other meteorological satellite products with historical product timestamps and licenses.
- Other regions and years: source coverage and availability must be audited, not silently filled.

Sources:
- https://www.ncei.noaa.gov/has/HAS.DsSelect
- https://registry.opendata.aws/noaa-nexrad/
- https://www.ncei.noaa.gov/products/goes-terrestrial-weather-abi-glm
- https://www.eumetsat.int/storing-data

## Data extraction and backfill acceptance gates

1. Acquire genuine archived products and provenance; record immutable source file, hash, time, location, resolution, satellite/radar ID, unit conversion and quality.
2. Geospatially match each product with a station coordinate and a neighborhood/upwind area; preserve missing radar coverage as **unknown**, never an observed zero.
3. Produce a compact table by source/station/hour for the vetted fields consumed by atmos.remote_sensing_features.RemoteSensingStore. Note actual coverage per station and date. Never substitute synthetic features for missing archives.
4. Verify no-lookahead with explicit observed/available times. Fail training on malformed/future product timestamps.
5. Compare station-only V2 with station + satellite, station + radar, and all-input models on **identical** matched, excluded station hours and fixed horizons.
6. Require a skill increase by target variable, not an aggregate that conceals regressions, including event detection metrics for rainfall and low visibility. Save frozen, durable model checkpoints and the complete data coverage manifest.
7. Use temporal holdout in addition to excluded locations before declaring production forecast skill. The current V2 spatial-holdout fit can incorporate future years from other training stations; this is not a historical walk-forward global model.

## Immediate next engineering deliverable

Run a small real-data archive extraction/coverage pilot (e.g. NEXRAD + GOES-R for US stations from 2018 onwards), compare against station-only predictions for the same verified hours, then expand sensor coverage progressively without sacrificing chronological integrity.

**Do not launch another 40-shard training run claiming radar/satellite skill before these features have actually been sourced and matched.**

## First real-file validation (June 1, 2018)

[Passing 2018 source extraction workflow](https://github.com/msbowman87-cmd/archer-atmos/actions/runs/42070428370) downloaded original GOES-16 ACMC and MCMIPC imagery and Unidata NEXRAD Level II KCBX and KAMX archives. All four objects were SHA-256 hashed. At 18:05 UTC, the geographic samples were:

| Station | Cloud mask 5x5 fraction | ABI band 8 water-vapor brightness temperature | NEXRAD nearby peak reflectivity |
|---|---:|---:|---:|
| Boise Air Terminal | 0.28 | 239.16 K | 53.0 dBZ |
| Miami International | 1.00 | 236.34 K | 48.5 dBZ |

These are actual extracted values, not generated observations. Radar peak reflectivity **is not precipitation amount**, and radar clutter may produce spuriously strong returns; quality checks must precede training. The runner successfully produced `station-sensing-pilot.csv`, `source-manifest.json`, and `coverage.json`. Historical actual product arrival times were **not available**, so +15 minutes after the GOES product creation and radar scan end were only explicitly labeled timing scenarios; do not certify them as verified forecaster availability. No coupled training or skill comparison was possible with a single scan.

The bounded continuation is in `atmos/historical_remote_sensing_batch.py` and `.github/workflows/atmos-remote-sensing-hourly-batch.yml`; it samples six consecutive UTC issue hours at two actual NOAA stations and reports missingness, source provenance, and as-of coverage. The next step after verifying coverage is to backfill many days/seasons, join to station targets, implement per-variable satellite/radar model coefficients, and evaluate against V2 on matched examples with both spatial and temporal holdouts.
