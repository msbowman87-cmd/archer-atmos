# Atmos Caribbean fallback for the 10,000-station network

Status: selection policy; inventory not yet processed.

## Priority and counts
Primary target: 6,000 United States, 2,500 Canada, 1,500 Mexico. Select qualifying mainland/national stations first. If Canada or Mexico has fewer qualifying stations than its target, fill only the shortfall using verified Caribbean island stations. Do not replace qualifying Canadian or Mexican stations merely to improve the total. Preserve original country and territory in station metadata and separately tag `selection_role=caribbean_fallback`. Report actual counts and remaining shortfall. Do not fabricate records or relax coordinate/elevation requirements.

## Caribbean scope
Eligible islands include the Bahamas, Cuba, Jamaica, Hispaniola (Haiti/Dominican Republic), Puerto Rico, U.S. and British Virgin Islands, Cayman Islands, Turks and Caicos, Aruba, Curaçao, Bonaire, Trinidad and Tobago, Barbados, and the Lesser Antilles. Select from official GHCNh station metadata using authoritative country/territory codes and geographic polygons; **do not** use only a broad Caribbean latitude-longitude rectangle, which would accidentally include mainland Central America and Mexico. Avoid double-counting Puerto Rico/U.S. Virgin Islands in the U.S. quota and the Caribbean fallback.

## Non-negotiable eligibility
- Valid finite latitude and longitude within the verified territory geometry.
- Valid finite elevation, not NOAA's -999.9 missing sentinel; retain elevation source and units.
- Station ID and inventory record, with adequate hourly observation density during 2016–2025. The current initial screen (at least 60 months with 500+ observations) is only a preliminary eligibility threshold; separately report whether the full ten-year hourly target is met.
- Keep source QC, variable coverage, temporal completeness, and station identity; de-duplicate across networks.
- Prioritize geographic diversity, coastal/island exposure, altitude, and long records. Record whether the source is an actual station measurement versus modeled/reanalysis data.

## Execution order
1. Obtain GHCNh station metadata, country-code lookup, inventory, and verified island boundaries.
2. Select and count qualifying US, CA, MX stations.
3. Compute Canada and Mexico shortfalls.
4. Select geographically distributed qualifying island stations up to combined shortfall; do not exceed 10,000 overall.
5. Export CSV/GeoJSON with station ID, source country, role, lat/lon/elevation, coverage, and quality; audit the map.
6. Only after selection, download observation archives in resumable batches.

No downloads or verified station counts are claimed by this policy.
