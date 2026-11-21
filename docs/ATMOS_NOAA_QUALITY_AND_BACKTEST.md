# Atmos NOAA historical observations: quality control and forecast-readiness

## Archive lineage (raw source remains unchanged)

- [v1 exact-hour archive](https://github.com/msbowman87-cmd/archer-atmos/releases/tag/atmos-noaa-observations-2006-2025-v1): original research snapshot.
- [v2 nearest real hourly reading archive](https://github.com/msbowman87-cmd/archer-atmos/releases/tag/atmos-noaa-observations-2006-2025-v2): 1,000 candidate stations, 2006–2025, 162,723,595 actual observations, 19,865 saved station-year files out of 20,000 requested; 135 missing. Saved files do not imply hourly completeness.
- [v3 derived QC/normalized archive](https://github.com/msbowman87-cmd/archer-atmos/releases/tag/atmos-noaa-quality-2006-2025-v3): created only after all quality jobs and release verification pass. This is derived data, **not** original NOAA measurements.
- NOAA Global Hourly/ISD format reference: https://www.ncei.noaa.gov/pub/data/noaa/isd-format-document.pdf

## Normalized fields and no synthetic observations

Each record represents one actual station observation matched to a nominal UTC hour, within 30 minutes. The actual measured instant is preserved in the observed_at_utc column, the approximate match is in hour_utc, and the signed offset is in offset_minutes. These are individual readings, **not hourly averages**. No missing hour is invented, filled, averaged or interpolated.

- Air temperature and dew point: Celsius, converted from NOAA integer tenths.
- Wind speed: m/s; wind direction: degrees.
- Sea level pressure: hPa.
- Visibility: meters.
- Precipitation (1h): mm, **only for actual 1-hour AA1 accumulation reports**; other periods are omitted rather than misrepresented.
- Relative humidity: derived percent using Magnus approximation from temperature and dew point, not a directly observed sensor reading. Large dewpoint-over-temperature inconsistencies are rejected; small rounding excesses reported and capped at 100%. Over-ice humidity is approximate.

Each missing or disqualified field is **empty**, not zero. An entire row is absent from normalized data only when every selected metric was unavailable. Raw NOAA values and flags remain preserved in v2.

## NOAA quality codes and strict training admission

The research-normalized v3 archive accepts **0, 1, 4, 5**. Codes 0/4 pass gross limits checks; 1/5 pass all NOAA QC checks. Suspect (2/6), erroneous (3/7), missing, unusual/unknown codes, invalid formats, missing sentinels and physical-limit violations are rejected on a variable-by-variable basis. Each valid field retains its original NOAA QC flag in a parallel _qc column; every rejection reason is counted in the per-station-year report.

**Strict historical forecast pairing permits only full-QC 1 or 5.** In particular, computed relative humidity requires both temperature and dewpoint flags to pass fully.

## Station-year and gap audits

Each shard report covers all 500 requested station-year files, including missing years, actual and normalized rows, QC-valid variable counts, exact/off-hour counts, first/last reported UTC hour, calendar-hour coverage (8760 or 8784 possible), missing internal hours, longest internal gap, station metadata, and source checksum/provenance.

The global v3 report summarizes 1,000 stations, 20 individual calendar years, coverage, usable variables and rejection reasons. It distinguishes station-year file availability from actual hourly data completeness.

**Legacy NOAA ISD stopped in August 2025.** The 2025 calendar-year gap must be handled using a separately collected contemporary NOAA GHCNh data source. All station/variable coverage is uneven.

## Reproducing a shard

Unpack the v2 release file atmos-nearest-hour-shard-00.tar.gz and run:

    python -m atmos.observation_quality --input-dir atmos-nearest-hour-shard-0 --output-dir qc-output --shard 0

Outputs: qc-output/normalized-shard-00.csv.gz and qc-output/quality-report-00.json.

Run the GitHub workflow .github/workflows/atmos-quality-v3.yml on the research branch for all 40 shards. It checks unit tests, normalizes real NOAA fields, verifies expected raw counts and gzip integrity, publishes 40 derived release assets plus checksummed manifest and global quality report, and leaves v2 unchanged.

## Verified historical forecast pairs and once-daily walk-forward calibration

The module atmos.verified_pairing prepares inputs for atmos.walk_forward, but refuses to claim measured forecast skill unless both required provenance inputs are supplied:

1. **Real archived forecast cycles**, including model issue time, prediction valid time, station, metric and reference documenting the real archived issue cycle.
2. **Independently verified NOAA observation availability times**, not just the measurement timestamps or when we downloaded the data. The legacy Global Hourly data does **not** supply these publication timestamps.

Forecast CSV required header:

    station_id,model,issue_at_utc,valid_hour_utc,metric,unit,value,source_issue_reference,source_issue_verified

Independent observation publication CSV required header:

    station_id,observed_at_utc,available_at_utc,verification_reference,availability_verified

Once real source evidence is available, run:

    python -m atmos.verified_pairing --forecasts verified_archived_forecasts.csv --normalized normalized-shard-00.csv.gz --observation-availability verified_publication_times.csv --holdout-start 2024-01-01T00:00:00Z --output verified-pairing-report.json

Pairs with unverified timestamps, suspect QC, missing metrics, or forecast issue times after actual measurements are rejected. Eligible chronological pairs then reach the existing daily walk-forward algorithm, which updates bias at most once per UTC day using observations already available at that day's cutoff.

If archived forecasts or observation publication evidence are missing, the pipeline reports **blocked_no_verified_pairs**, not an invented skill score. A completed 20-year backtest is therefore **not** being claimed merely because the station archive is complete.

## Operational notes

Preserve raw source v2 and derived v3 separately; off-GitHub independent backup is still recommended. This is a research branch; do not merge to main or deploy Atmos production until held-out forecast skill evaluation is complete. NOAA attribution is maintained and v3 is expressly labeled derived.
