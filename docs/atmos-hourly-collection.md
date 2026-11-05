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
