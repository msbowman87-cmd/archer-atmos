# USCRN candidate evidence, 2026-11-06 Mountain time

Three WBAN IDs marked outside the frozen manifest in [the expansion review](source_expansion_review.json) match official [NOAA station metadata](https://www.ncei.noaa.gov/access/homr/file/crn-stations.txt). The [metadata layout](https://www.ncei.noaa.gov/access/homr/file/CRN_Table.txt) specifies feet. Direct retrieval of the 2025 hourly files exposed observation rows with the corresponding WBAN and coordinates consistent with the official metadata at the hourly files' precision.

| WBAN | Station | Latitude | Longitude | NOAA elevation (ft) | Hourly evidence |
| --- | --- | ---: | ---: | ---: | --- |
| 04130 | St. Mary 1 SSW, MT | 48.7412 | -113.4330 | 4555 | [2025 Hourly02](https://www.ncei.noaa.gov/pub/data/uscrn/products/hourly02/2025/CRNH0203-2025-MT_St._Mary_1_SSW.txt) |
| 04990 | Sioux Falls 14 NNE, SD | 43.7346 | -96.6222 | 1594 | [2025 Hourly02](https://www.ncei.noaa.gov/pub/data/uscrn/products/hourly02/2025/CRNH0203-2025-SD_Sioux_Falls_14_NNE.txt) |
| 94075 | Boulder 14 W, CO | 40.0354 | -105.5409 | 9828 | [2025 Hourly02](https://www.ncei.noaa.gov/pub/data/uscrn/products/hourly02/2025/CRNH0203-2025-CO_Boulder_14_W.txt) |

The earlier directory text lookup missed these files. The direct files establish hourly evidence in scope. Physical duplicate checks against the full manifest and ingestion of the original Hourly02 format and flags are still required before admission. The samples do not establish completeness for every hour, variable, or year. This evidence does not change the frozen station selection.
