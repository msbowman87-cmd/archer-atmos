# Orchard Range 2025 hourly weather retry

USDA NRCS AWDB station 674:ID:SCAN. Counts are populated hours before screening out of 8,760. Original measurements and flags are preserved.

- RHUM returned 8760 hours. SHA-256 `16825d6aeab7a0c0399799308cd9ea27dad251911aefbcee9177933a22d302db`. [USDA response](https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data?stationTriplets=674%3AID%3ASCAN&elements=RHUM&duration=HOURLY&beginDate=2025-01-01&endDate=2025-12-31%2023%3A00&returnFlags=true&returnOriginalValues=true&returnSuspectData=true)
- PRCP returned 8760 hours. SHA-256 `445fea737e1e83e1f4429898bf9c3f2eccf9548bb628e4db9ef723e0bc6dc8f2`. [USDA response](https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data?stationTriplets=674%3AID%3ASCAN&elements=PRCP&duration=HOURLY&beginDate=2025-01-01&endDate=2025-12-31%2023%3A00&returnFlags=true&returnOriginalValues=true&returnSuspectData=true)
- DPTP returned 8760 hours. SHA-256 `89d554a41449db4d7deb2e840032cb0cf96684cb65bcc9f342cb4aa43c77a01d`. [USDA response](https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data?stationTriplets=674%3AID%3ASCAN&elements=DPTP&duration=HOURLY&beginDate=2025-01-01&endDate=2025-12-31%2023%3A00&returnFlags=true&returnOriginalValues=true&returnSuspectData=true)
