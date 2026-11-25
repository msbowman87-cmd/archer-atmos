# Nevada SCAN station discovery

USDA metadata identified eight candidates with hourly temperature series: Buckhorn, Charkiln, Kyle Canyon, Lovell Summit, Lovelock NNR, Pine Nut, Ruby, and Trough Springs. Cross-provider deduplication and decade coverage checks remain open. [USDA inventory](https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/stations?stationTriplets=%2A%3ANV%3ASCAN&returnStationElements=true)

Buckhorn (2216:NV:SCAN, 40.87959, -119.95340, 6,470 ft) returned 8746 distinct populated hourly TOBS timestamps for 2025 before quality screening. Original response SHA-256 `789016d0e2fc007634452f7fa9e783d71155c4774b52f0823699ebd3ce58ebd9`. [USDA request](https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data?stationTriplets=2216%3ANV%3ASCAN&elements=TOBS&duration=HOURLY&beginDate=2025-01-01&endDate=2025-12-31%2023%3A00&returnFlags=true&returnOriginalValues=true&returnSuspectData=true)

The Utah SCAN inventory retry timed out without a response. Utah coverage remains unresolved.
