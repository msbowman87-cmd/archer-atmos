# Atmos North America station selection — 2026-11-05

Research branch: `research/daily-walk-forward-20261101`. Production was not changed.

## Result: partial selection, blocked at 6,809 locations

The requested 10,000-location selection is **not complete**. The exported manifest contains real source-catalog records with valid coordinates, reported elevations, and documented observational archives overlapping 2016–2025. It is a **catalog-verified partial manifest**, not a certification of complete hourly observations at every station.

| Region | Target | Selected primary | Primary shortage |
|---|---:|---:|---:|
| United States | 6,000 | 5,183 | 817 |
| Canada | 2,500 | 1,163 | 1,337 |
| Mexico | 1,500 | 182 | 1,318 |

281 qualifying Caribbean locations fill part of the Canadian/Mexican shortage. Caribbean sites never fill the U.S. quota. Origin country and fallback role remain in every record. Total remaining shortage: **3,191**. These are shortages in the retrieved, verified catalogs, not proof that additional qualifying stations do not exist elsewhere.

| Selected provider | Locations | Evidence |
|---|---:|---|
| NOAA GHCNh | 5,799 | Actual monthly observation-record counts in 2016–2025 |
| ECCC | 570 | Official hourly-archive first/last years; intervening completeness unknown |
| Iowa Environmental Mesonet ASOS | 440 | Historical METAR archive bounds; intervening completeness unknown |

5,018 locations have at least 60 months with 500 or more **records**, not necessarily 500 distinct hours or adequate coverage of each variable. No per-variable completeness claim is made. Shorter histories remain eligible because the objective prioritizes 2016–2025 rather than requiring five complete years as an absolute gate. Missing coverage counts remain blank/null, never zero-filled as invented evidence.

## Retrieved sources and outstanding blockers

133 inventory/document requests were recorded: 132 successful and one inaccessible. SHA256, URL, response size and retrieval time are in `retrieval_ledger.json`. Cached source bytes are reused only when their recorded hash matches.

| Source | Actual outcome | Remaining limitation / rights |
|---|---|---|
| [NOAA GHCNh](https://www.ncei.noaa.gov/products/global-historical-climatology-network-hourly) | Station CSV and monthly-count inventory retrieved and joined by source ID | Record counts are not distinct-hour or variable counts. Preserve embedded source/QC provenance; do not assume every upstream feed has identical rights. |
| [ECCC station inventory](https://collaboration.cmc.ec.gc.ca/cmc/climate/Get_More_Data_Plus_de_donnees/Station%20Inventory%20EN.csv) | 1,070 hourly station records overlap the study years before validation/deduplication | This inventory alone cannot meet Canada's 2,500 target. First/last years do not establish continuous intervening observations. |
| [ECCC hourly API](https://api.weather.gc.ca/collections/climate-hourly) | Two monthly batches downloaded, parsed and identity checked | Legacy CSV endpoint returned HTML. GeoMet UTC timestamps can cross local-month boundaries; use explicit LOCAL_YEAR/LOCAL_MONTH filters and retain both timestamps. |
| [SMN automatic-station service](https://smn.conagua.gob.mx/tools/GUI/sivea_v3/php/getTodasEstaciones.php) | 236 current records with location/elevation retrieved | No verified 2016–2025 hourly archive established for these records; excluded. Current values are not historical evidence. No unrestricted redistribution licence established. |
| [CONAGUA SIH catalog](https://sih.conagua.gob.mx/climas.html) | Retrieval failed with an HTTP 302 redirect loop | No catalog or historical files from this endpoint admitted. FTP access described in provider documentation was not exercised; historical cadence and redistribution rights remain unverified. |
| [IEM ASOS archive](https://mesonet.agron.iastate.edu/request/download.phtml) | U.S., Canadian, Mexican and Caribbean network catalogs retrieved; two actual monthly batches collected | Archive is supplied as-is with limited QC. Original METAR strings retained. Provider catalogs can be rounded or have missing elevations. |
| IEM regional inventories | ISUAG, ISUSM, SCAN, USCRN and Mexican DCP catalogs retrieved | Not admitted through these adapters without verified historical hourly archive mapping. This is an adapter/verification blocker, not a claim that their archives are inaccessible. NOAA cross-listings may already be represented. |
| [MADIS restrictions](https://madis.ncep.noaa.gov/madis_restrictions.shtml) | Official restrictions reviewed | Mesonet distribution categories vary. Restricted archive access and redistribution permission were not established; no restricted MADIS records collected. |
| [Synoptic](https://docs.synopticdata.com/services/time-series) | Documentation retrieved after correcting an obsolete documentation URL | Requires a token; historical and geographic access depend on account entitlements. No token-backed archive access or rights were verified; no stations admitted merely from advertised totals. |

The remaining work requires additional verified hourly archives, provider adapters and rights checks, especially Canadian/Mexican regional networks. Daily climatological stations, modeled grid points and stations without reported elevation were not substituted to reach 10,000. These blockers prevent a truthful full selection today.

### ECCC redistribution conditions

This work is based on Environment and Climate Change Canada data. The [ECCC licence](https://climate.weather.gc.ca/prods_servs/attachment1_e.html) requires attribution, prohibits explicitly charging for the source data product, and requires downstream recipients to agree to the same redistribution restrictions. Value-added service charges are permitted. The product is supplied as-is. Raw ECCC records and the derived catalog are delivered privately to the requesting user, not committed as public repository data. Review the source licence before onward redistribution.

[IEM's disclaimer](https://mesonet.agron.iastate.edu/disclaimer.php) states that its site materials are public domain and may be used for lawful purposes; attribution is appreciated. The archive has no warranty. Preserve upstream and raw report provenance.

## Corrections and selection method

- The previous program accepted unsupported numeric CSV claims, imposed an unrequested hard 60-month threshold, and lacked provider retrieval or map generation. New adapters retain source URLs, archival evidence, licence notes, timestamps, and unknown coverage explicitly.
- NOAA country labels use the CSV's ISO_CODE field. Station identifier prefixes are FIPS codes and cannot safely stand in for Caribbean ISO codes.
- Coordinate grid rounding was replaced with neighbor-aware spherical distance checks, including high-latitude and date-line cases. Repeated provider IDs and explicit GHCNh crosswalks are collapsed. ECCC WMO and IEM ICAO cross-checks link a single nearby NOAA catalog match within 2 km; ambiguous multiple matches are not asserted as crosswalks.
- 11,072 normalized records produced 609 metadata/evidence rejections and 3,654 duplicate/site exclusions, leaving 6,809 locations. Every exclusion has an audit entry. A conservative 500 m exclusion can remove genuinely separate nearby sensors; it is not proof of common ownership. Very imprecise source coordinates may still require manual relocation review.
- One-degree grid round-robin selection spreads locations within country quotas. Source record-count evidence determines priority within cells. This is reproducible catalog selection, not an optimized meteorological network design.

## Collection actually performed

| Provider | Complete batches | Original records | Raw bytes |
|---|---:|---:|---:|
| NOAA GHCNh — USW00013766, 2016–2025 | 10 annual files | 526,609 | 341,060,387 |
| ECCC — 10076, Jan–Feb 2016 | 2 monthly files | 1,439 | 1,462,695 |
| IEM ASOS — 10U, Apr–May 2023 | 2 monthly files | 1,168 | 250,339 |
| **Total** | **14** | **529,216** | **342,773,421** |

Only downloaded files with parsed measurements and matching station/period identities are counted. Raw source bytes, nulls/sentinels, measurement/QC/source flags, METAR strings, and original timestamp fields are preserved without interpolation or unit conversion. Per-file sidecars contain hashes, URLs, retrieval times and field/flag counts. Flags are counted, not interpreted as quality passes.

Earlier HTML and UTC/local-month validation failures are documented in run logs; they are not successes. Successful checkpoints are skipped only after matching source URL and file hash. A real rerun skipped all ten NOAA files and requested zero new batches. Failed checkpoints are skipped on subsequent runs unless `--retry-blocked` is supplied, preventing repeated failures from starving later batches. Source-URL identity permits safe resumption when the selected manifest grows; each sidecar retains its originating manifest hash.

## Validation actually performed

- Full repository Python suite: **169 tests passed**. Offline tests include fixtures and mocks; they are not evidence of live provider downloads.
- Independent manifest validation: valid metadata, provider/canonical ID uniqueness, matching CSV/GeoJSON coordinates, no retained pair within 500 m, exact equality between map-embedded features and exported GeoJSON.
- Node JavaScript syntax check passed for the generated map. Browser GUI interactions were **not** exercised. The map needs internet access for Leaflet and OpenStreetMap tiles; selected coordinates are embedded locally.
- Live collection checks and actual resumption are reported separately above. Ten-year completeness for all stations, per-variable calibration readiness, and every-provider round trips remain unverified.

## Reproduce and resume

```bash
python scripts/acquire_station_inventories.py --out research/station-selection-20261105/input
python scripts/normalize_station_inventories.py --input research/station-selection-20261105/input --out research/station-selection-20261105
python scripts/select_multi_provider_stations.py --input research/station-selection-20261105/normalized.csv --out research/station-selection-20261105
python scripts/verify_station_manifest.py --input research/station-selection-20261105
python scripts/collect_selected_hourly.py --manifest research/station-selection-20261105/stations.csv --out research/station-selection-20261105/observations --providers NOAA_GHCNh --max-batches 10 --workers 2
```

The existing inventory workflow now performs multi-provider selection, verification, bounded NOAA collection and checkpoint artifact upload on the research branch only. It restores the latest unexpired research checkpoint when available. Artifacts expire after 90 days; retain an external copy for long-term preservation. ECCC and IEM collection are available via the CLI provider selector. No recurring job or production deployment was configured. A future workflow run is not counted as a completed download in this report.

Deliverables include `stations.csv`, `stations.geojson`, `map.html`, normalized inputs, source snapshots, retrieval/deduplication/rejection audits, verification hashes, raw collected files with sidecars, and this report. Large source/data artifacts are distributed in the saved checkpoint package rather than public git source.

### Subsequent collection clarification

See [the hourly collection notes](atmos-hourly-collection.md) for the expanded provider runs, backoff/retry handling and unique-task progress reporting. The GeoMet hourly observation API has an open-data licence permitting redistribution with attribution; the legacy website inventory licence discussed above is not applied to those newly downloaded API observations. The 529,216-record count above remains the original pilot snapshot, not the latest collection total.
