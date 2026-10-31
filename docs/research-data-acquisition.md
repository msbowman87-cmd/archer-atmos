# Archer Atmos research data acquisition plan

## Principle
Collect the broadest useful, legally usable, timestamped and quality-controlled historical data feasible, without treating reanalysis as independent ground truth. Do not launch unlimited downloads or incur paid API/cloud charges without approval.

## P0: immediately useful
- Hourly/subhourly ASOS observations; global NOAA ISD and GHCN-Daily; source-specific QC, coverage and reporting cadence.
- Historical **issued** GFS/GEFS and ECMWF forecasts with run and actual publication times, valid intervals, lead, grid and ensemble member. Archive immutable raw inputs and checksums.
- Temperature, dew point, humidity, wind speed/direction/gust, pressure, precipitation occurrence/amount, snowfall, visibility, cloud cover, solar radiation where available.
- NOAA Storm Events for event verification, with reporting-bias limitations.

## P1: environmental context
- Radar-derived rainfall and its QC, GOES/other satellite imagery and retrievals, radiosondes, upper-air analyses, soil moisture, land cover, elevation, slope, aspect, coast distance, urbanization, water temperature, snowpack.
- Reanalysis as historical predictors/context, NOT as a substitute for independent station truth.

## P2: advanced specialty sources
- Lightning, lightning network licenses, aviation observations, river gauges, flood impacts, wildfire fuels and observations, ocean/buoy measurements, tropical cyclones, air quality, UV, pollen where legal and useful.

## Data model and storage
- Append-only raw archive, normalized parquet/partitioned analytics tables, station registry, source metadata and audit manifest.
- Required: source/provider, license, source revision, retrieval timestamp, SHA256, station coordinates/elevation, unit, valid start/end UTC, issuance/availability timestamp, quality flags, spatial/temporal resolution.
- Partition by source/year/month/region; deduplicate on source/issue/valid/variable/location/member.
- Separate forecast issuance from validity, station time zones and observation coverage. Require time-aligned verification.
- Enforce sensible QC: physically possible values, unit conversion, duplicate resolution, sensor outage detection, reporting delay and coverage thresholds. Keep original values immutable.
- Do not collect private personal or location-tracking data.

## Evaluation
- Split by historical forecast issue and valid dates, weather events, regions, stations and seasons. Preserve untouched final test sets.
- Evaluate MAE/RMSE/bias, precipitation and extreme-event hit/miss/false alarm rates, Brier score, reliability and ensemble calibration; confidence intervals clustered by independent days/events.
- Compare persistence, climatology, raw ECMWF/GFS/GEFS, calibrated and blended candidates. Disable regressions; do not optimize on test results.
- Forecast days 16–30 need authentic archived subseasonal ensembles and probabilistic verification.

## Operational safeguards
- Begin with small representative station/month batches. Record request counts, retries, rate limits, bytes, missing coverage and API costs.
- Use capped exponential backoff and caching; skip unavailable data with explicit status, never silently substitute.
- Review licenses/terms and redistribution rights for every provider before serving derived products commercially.
- No live Atmos changes without explicit approval.
