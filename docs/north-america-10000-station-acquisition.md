# Atmos: 10,000-station North America acquisition

Status: acquisition specification, not completed download.

## Geographic targets
- United States: 6,000
- Canada: 2,500
- Mexico: 1,500
- Select stations by spatial coverage, 2006-present hourly coverage, variable completeness, quality, elevation, and climate diversity. Quotas are targets, not guarantees.

## Primary sources
- NOAA GHCNh (successor to retired ISD): https://www.ncei.noaa.gov/products/global-historical-climatology-network-hourly
- Environment and Climate Change Canada historical climate data: https://climate.weather.gc.ca/historical_data/search_historic_data_e.html
- Mexican CONAGUA official station archives; evaluate licensing and metadata before integrating. Do not treat third-party reanalysis-filled station values as measurements.
- Archived ISD on NOAA Open Data Dissemination can backfill earlier history, with deduplication against GHCNh.

## Pipeline stages
1. Fetch source station inventories and validate source metadata and rights.
2. Normalize identifiers; match cross-source duplicates by IDs, coordinates, name, elevation, and active dates.
3. Rank eligible stations using temporal coverage, geographic stratification, elevation, data quality, and variable completeness; publish 10,000-row selected-station manifest with selection reasons.
4. Download historical station observations in resumable year/source batches, recording checksum, URL, fetch timestamp, source version, and original timestamps.
5. Parse into partitioned Parquet (country/year/station or suitable balanced partition), retaining raw archives separately. Preserve measurement values, units, source QC flags, nulls, and observation timestamps.
6. Build per-variable missingness/coverage reports, duplicates report, source reconciliation, and cross-border spatial coverage map.
7. Join station observations with regional radar, satellite, reanalysis and forecast-model grids at forecast-issue-time, with verified product availability timestamps to prevent temporal leakage.
8. Run chronological holdout evaluations; never treat reanalysis-derived values as independently observed ground truth.

## Scale and controls
10,000 x 20 x 365.25 x 24 ~= 1.753 billion theoretical station-hour slots; actual station records may be sparse. Estimate compressed storage using pilot batches before full backfill. Implement retries, checkpointing, bounded concurrency, incremental refresh, and cost caps. Keep source-specific attribution/licensing metadata. No unverified claims of completed downloads.

## Variable policy
Capture all available source variables (temperature, dew point, humidity, pressure, wind, gust, precipitation, visibility, cloud, present weather, snow, etc.) with original units/QC. Missing source variables remain null, not invented. Separately derive atmospheric features from gridded fields and label them as modeled rather than observed.
