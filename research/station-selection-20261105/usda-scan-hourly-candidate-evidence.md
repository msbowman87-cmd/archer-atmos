# USDA SCAN hourly station candidates

Two Idaho stations passed the current 500 m proximity screen against the 6,809-location manifest (SHA-256 `59c8b81c025dd752a2b76cadca8815805adcad04a6935274d524f24c1cb3ef06`). The provider reports elevations in feet.

| Station triplet | Site | Latitude | Longitude | Elevation (ft) | Nearest selected location | Distance |
| --- | --- | ---: | ---: | ---: | --- | ---: |
| 2148:ID:SCAN | Jordan Valley CWMA | 42.94863 | -117.01060 | 4500 | USC00354321 | 4.86 km |
| 674:ID:SCAN | Orchard Range Site | 43.32268 | -115.99643 | 3190 | USC00101018 | 23.01 km |

The provider's [station metadata](https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/stations?stationTriplets=%2A%3AID%3ASCAN) and [hourly temperature response](https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data?stationTriplets=2148%3AID%3ASCAN%2C674%3AID%3ASCAN&elements=TAVG&duration=HOURLY&beginDate=2025-01-01&endDate=2025-01-02&returnFlags=true&returnOriginalValues=true&returnSuspectData=true) establish historical hourly observations in the study interval. The test returned 24 and 25 rows respectively. Both responses exposed fields for the original value and original QC, current QC and QA flags. The sample is insufficient to certify continuity or other variables.

The [agency's legacy AWDB terms link](https://www.nrcs.usda.gov/wps/portal/wcc/home/dataAccessHelp/webService/webServiceTerms) redirects to a reports page. Redistribution terms for the AWDB observation responses remain unverified. The candidates are pending that check and collector integration. No rows were added to the frozen manifest and no raw SCAN observations were published.
