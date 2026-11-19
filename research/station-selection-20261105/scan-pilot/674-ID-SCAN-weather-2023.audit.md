# Orchard Range hourly weather, 2023

Original USDA NRCS AWDB responses for station 674:ID:SCAN. Counts are distinct populated hours before quality screening out of 8,760. Original values and flags are preserved.

- RHUM returned 8760 hours. SHA-256 `601d0845c28f962f3f1daea7f3ad0728c39e4e4b4f2d3aece2d09fea7d8e8b1d`. [USDA request](https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data?stationTriplets=674%3AID%3ASCAN&elements=RHUM&duration=HOURLY&beginDate=2023-01-01&endDate=2023-12-31%2023%3A00&returnFlags=true&returnOriginalValues=true&returnSuspectData=true)
- PRCP returned 8760 hours. SHA-256 `01260dd63f79d39a72615fab383a36e14753f34862725fbc17867dbf16204c0d`. [USDA request](https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data?stationTriplets=674%3AID%3ASCAN&elements=PRCP&duration=HOURLY&beginDate=2023-01-01&endDate=2023-12-31%2023%3A00&returnFlags=true&returnOriginalValues=true&returnSuspectData=true)
- WSPDV remains pending. curl: (28) Operation timed out after 18002 milliseconds with 0 bytes received
- DPTP remains pending. curl: (28) Operation timed out after 18001 milliseconds with 0 bytes received
