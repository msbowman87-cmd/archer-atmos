# Caribbean SCAN candidate evidence — November 18, 2026

The [NRCS SCAN catalog](https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/stations?stationTriplets=%2A%3A%2A%3ASCAN) returned eight entries in Puerto Rico and the US Virgin Islands. All eight reported coordinates and elevation. Elevations below retain provider feet.

A single [hourly temperature request](https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data?stationTriplets=%2A%3APR%3ASCAN%2C%2A%3AVI%3ASCAN&elements=TAVG&duration=HOURLY&beginDate=2025-01-01&endDate=2025-01-02&returnFlags=true&returnOriginalValues=true&returnSuspectData=true) returned six station series with 25 non-null values each, including endpoint timestamps. Each row included date, value, origValue, origQcFlag, qcFlag and qaFlag. Response SHA-256 was a527593ed8765fc98c3657930db5296c03cbaf664c6031f22212a4610de6e5f4.

| Triplet | Site | Latitude | Longitude | Elevation (ft) | Sample values |
| --- | --- | ---: | ---: | ---: | ---: |
| 2122:PR:SCAN | Fortuna | 18.02502 | -66.52790 | 70 | 25 |
| 2045:PR:SCAN | Guilarte Forest | 18.14638 | -66.76718 | 3330 | 25 |
| 2052:PR:SCAN | Isabela | 18.47022 | -67.04372 | 390 | 25 |
| 15:PR:SCAN | Maricao Forest | 18.15737 | -67.00392 | 2370 | 25 |
| 2232:PR:SCAN | Miradero | 18.21137 | -67.13460 | 130 | 25 |
| 2123:VI:SCAN | Upper Bethlehem | 17.71833 | -64.79518 | 120 | 25 |

Combate (2066:PR:SCAN) and Corozal (2188:PR:SCAN) were omitted from this response. Their sample availability remains unverified. No missing row was counted successful.

The sample establishes hourly measurements during part of the requested interval. Physical deduplication against the selected manifest and within the provider catalog, complete element availability, source terms, and collection integration remain pending. Miradero's catalog begins in 2022, so this site cannot supply observations for its earlier requested years. The frozen 6,809-location manifest remains the collection baseline.
