# USDA station discovery, November 20, 2026

- The Idaho-coded SCAN inventory returned two station triplets, `2148:ID:SCAN` and `674:ID:SCAN`. Both are already represented in the research archive. This check adds zero locations. [Idaho query](https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/stations?stationTriplets=%2A%3AID%3ASCAN&returnStationElements=true)
- The Oregon-coded SCAN inventory returned an empty array. The result applies to this query and network code. [Oregon query](https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/stations?stationTriplets=%2A%3AOR%3ASCAN&returnStationElements=true)
- The Utah-coded SCAN request timed out before receiving a response. Utah coverage remains unresolved. [Utah query](https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/stations?stationTriplets=%2A%3AUT%3ASCAN&returnStationElements=true)
- The Idaho SNOTEL wildcard request returned HTTP 400. The query did not establish station availability. [SNOTEL query](https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/stations?stationTriplets=%2A%3AID%3ASNTL&returnStationElements=true)
