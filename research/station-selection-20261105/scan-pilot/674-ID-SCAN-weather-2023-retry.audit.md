# Orchard Range 2023 hourly weather retry

Original USDA responses for 674:ID:SCAN. Counts are distinct populated hours before screening, out of 8,760.

- WSPDV returned 8760 populated hours. SHA-256 `d057077d88eed0e078728a89aa6212c708fe660f5b45e4c0cff0dc8c5e163c24`. [USDA request](https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data?stationTriplets=674%3AID%3ASCAN&elements=WSPDV&duration=HOURLY&beginDate=2023-01-01&endDate=2023-12-31%2023%3A00&returnFlags=true&returnOriginalValues=true&returnSuspectData=true)
- DPTP returned 8760 populated hours. SHA-256 `48edb3b09bac23bdce822f5919d6f4231e223232dfecbc51079832a36f2f0c25`. [USDA request](https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data?stationTriplets=674%3AID%3ASCAN&elements=DPTP&duration=HOURLY&beginDate=2023-01-01&endDate=2023-12-31%2023%3A00&returnFlags=true&returnOriginalValues=true&returnSuspectData=true)
