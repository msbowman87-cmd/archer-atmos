# Atmos 2016–2025 hourly collection

Collection uses the frozen, catalog-verified partial selection of 6,809 locations from the research checkpoint. The 3,191-location selection shortfall remains; archive dates do not certify complete measurements.

The research inventory workflow now restores its last unexpired checkpoint and collects up to 100 additional source files **per provider per run**: NOAA station-years, ECCC station-months, and IEM station-months. This is a bounded collection window, not a claim that the entire archive is downloaded. It does not schedule recurring jobs or deploy production. Manual runs can request 1–120 files per provider. Concurrency serialization prevents two workflow runs from racing to replace the active checkpoint. Provider failures are logged and later tasks remain eligible. IEM uses one worker and paced requests. HTTP 429/5xx, incomplete responses and network timeouts receive bounded backoff retries; empty observation periods are reported as gaps, not successes.

The original PSV, GeoJSON, CSV, timestamps, measurement units, source/QC flags and raw METAR fields are retained. Hash-checked successful files resume without redownloading. A source-response sidecar records station ID, period, source URL, hash, original byte size and parsed record/flag counts. The progress report counts unique active station-period tasks, not overlapping run totals. Blocked and pending tasks are reported separately.

## Attribution and source-specific terms

Data Source: Environment and Climate Change Canada.

ECCC **GeoMet hourly observations**, the actual observation source used here, are provided through ECCC's open data services. The [Data Services End-use Licence, version 2.1.1](https://eccc-msc.github.io/open-data/licence/readme_en/) allows copying, publishing and redistribution, including commercial use, subject to attribution and other stated conditions. The [official hourly dataset catalog](https://open.canada.ca/data/en/dataset/df2e6e1a-6057-4c4d-a509-94aa57705a8c) also identifies the Open Government Licence – Canada. Preserve third-party attribution where supplied. No endorsement or warranty is implied.

This clarifies the earlier selection report: the legacy Historical Climate Data website terms attached to the **station metadata inventory** do not describe the GeoMet hourly observation endpoint's open-data licence. Existing station-inventory provenance is retained; new observation sidecars distinguish station metadata licensing from observation licensing. The restrictive legacy terms are not incorrectly assigned to newly downloaded GeoMet observations.

Iowa Environmental Mesonet of Iowa State University supplies its [public-domain archive](https://mesonet.agron.iastate.edu/disclaimer.php) as-is; original METAR and upstream provenance are retained. NOAA GHCNh source and quality identifiers remain in every original file; preserve upstream source attribution. No restricted MADIS or token-protected Synoptic feed is collected.

GitHub checkpoint artifacts are retained for 90 days. Their expiry is not durable long-term archival storage. A missing/expired checkpoint stops this collection workflow rather than silently changing the station selection. A future run must be explicitly started; no continuous-download promise is made.

```bash
python scripts/collect_selected_hourly.py --manifest research/station-selection-20261105/stations.csv --out research/station-selection-20261105/observations --providers NOAA_GHCNh --max-batches 100 --workers 2
python scripts/collect_selected_hourly.py --manifest research/station-selection-20261105/stations.csv --out research/station-selection-20261105/observations --providers ECCC --max-batches 100 --workers 2
python scripts/collect_selected_hourly.py --manifest research/station-selection-20261105/stations.csv --out research/station-selection-20261105/observations --providers IEM_ASOS --max-batches 100 --workers 1
python scripts/summarize_hourly_collection.py --manifest research/station-selection-20261105/stations.csv --out research/station-selection-20261105/observations --verify-hashes --report research/station-selection-20261105/collection_progress.json
```

## Coverage audit, continuation and long-term preservation

Country streams now alternate source-file tasks across the U.S., Canada, Mexico and Caribbean origins; the collector does not wait for every U.S. station before starting Mexican stations. The frozen station selection remains unchanged. IEM requests use a single worker, ten-second pacing and bounded backoff retries.

`audit_hourly_coverage.py` checks hashes and reports nonmissing **distinct hourly bins for each source field**, expected hours, missing-hour fractions and source flag frequencies. Multiple subhourly measurements do not inflate hourly completeness. Quality flags remain uninterpreted until source-specific mappings are validated; observed coverage is not quality-approved training coverage.

`package_hourly_archive.py` splits the checkpoint into CRC-checked ZIP parts, each capped at 512 MiB of uncompressed content. Its index records a SHA256 and member list for each part. Raw input inventory caches are excluded; source URLs and inventory hashes remain in the research checkpoint. Extract all parts into one directory to restore it.

The preservation workflow publishes a separate **research-data prerelease**, explicitly targeting the research commit, with `latest=false`. The collection workflow also preserves each completed window this way. These release assets do not have the temporary workflow artifacts' 90-day expiry. Publication and upload-size verification must succeed before preservation is reported as complete. Access or hosting-policy changes remain possible; this is not a promise of immutable storage or a substitute for an independent backup. No main-branch update or production deployment occurs.

The earlier statements that only 90-day storage was configured describe the previous workflow revision; the new preservation steps supersede that limitation once their runs succeed.

## Remaining station-source work

The USCRN/IEM cross-check reviewed 233 catalog records: 149 WBAN-matched stations are already selected through NOAA, and 216 matching catalog pairs have reported elevations differing by more than 20 units. This is a source/unit verification issue; no elevation has been converted or guessed. No new location was admitted from that review. The 3,191-location shortage, especially Canadian/Mexican regional archive verification, remains open. Additional source qualifications must pass the existing provenance, elevation, archive and duplicate checks before changing the collection list.

## Regional-model preparation (not yet trained)

The next model must use each station's surrounding and upstream observations, wind direction/speed, coordinates/elevation, and separately versioned radar/satellite features. Source weather variables keep their original measurements in the raw archive; a later normalized layer must document units and flag handling. Missing variables require explicit masks, not invented measurements.

Use 2016–2023 for initial training, 2024 for model/feature choices, and 2025 for chronological evaluation. Reserve geographic tiles across all dates for a separate spatial-generalization evaluation. Fit scaling and calibration only on information available before each forecast. Any daily adaptation during evaluation must occur after that day's forecasts and be reported as prequential evaluation, separately from frozen-model scores. Score temperature, wind, humidity, pressure, precipitation and probability calibration individually against persistence and the existing model. No model training, radar/satellite completeness, or forecast improvement is claimed by this preparation document. Training remains gated on source-unit/QC interpretation and adequate verified coverage.

## Verified local audit snapshot — 2026-11-05

The local checkpoint's 261 completed source files contain 2,186,118 records (40 NOAA annual files, 112 ECCC monthly files, 109 IEM monthly files). All 261 source hashes matched and every file parsed successfully. This is one checkpoint snapshot, not an additive count to combine with overlapping GitHub runs.

The audit produced 6,186 variable-period rows: 1,929 have no observed hourly bins and 2,062 have at least 90% observed hourly bins for their full year/month. These are field-period counts, not station counts. No source flags have been discarded or interpreted as acceptable for training. The raw checkpoint remains **not quality-approved for training** until source-specific units/flags and variable coverage are reviewed. The machine-readable snapshot is in `research/station-selection-20261105/audit/coverage_summary.json`.
