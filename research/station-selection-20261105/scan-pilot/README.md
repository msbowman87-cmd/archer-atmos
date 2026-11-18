# USDA NRCS SCAN pilot

Data source: USDA Natural Resources Conservation Service, National Water and Climate Center. The [NRCS dataset metadata](https://catalog.data.gov/dataset/soil-climate-analysis-network-scan) lists a dataset-level public-domain designation. This pilot uses an NRCS-operated station.

The archived original AWDB response contains 24 hourly TAVG values for 2148:ID:SCAN on January 1, 2025. The [request](https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data?stationTriplets=2148%3AID%3ASCAN&elements=TAVG&duration=HOURLY&beginDate=2025-01-01&endDate=2025-01-02&returnFlags=true&returnOriginalValues=true&returnSuspectData=true) includes original values, flags and suspect data. The source and GitHub copy matched SHA-256 ff732843f6c310dda8ca6752037d8dc2518fcf523eacbecc0d686aa22f555636. Coverage beyond this sample and integration with the main research collection workflow remain open.
