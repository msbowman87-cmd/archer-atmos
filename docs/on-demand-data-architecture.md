# Atmos search-time data gathering — research implementation

`python -m atmos.on_demand --latitude 42.4818 --longitude -114.4877 --output sample.json`

This requests a fresh multi-variable weather profile at **any valid global coordinate** and four surrounding locations (about 200 km in cardinal directions). The center is always included. It collects temperature, humidity, dew point, pressure, clouds, rain/snow, wind, visibility, CAPE, solar radiation, and selected 850/700/500 hPa atmospheric fields. Responses are cached locally by exact coordinates, query parameters, and regional radius for up to an hour by default. Cached data must be revalidated as models update.

This is a *research data acquisition interface*, not the commercial website endpoint. It does not apply the unapproved regional correction or claim to issue an Atmos forecast. It does not identify the source model's exact run timestamp when the provider omits it. The cache is per filesystem; production needs durable shared/object caching, concurrency coordination, monitoring, provider quotas, and a server-side endpoint rather than exposing provider keys in browsers.

Historical training inputs: `python -m atmos.rich_history --year 2025 --month 1 --shard 0 --grid-count 5000 --shard-size 5`. Each bounded shard fetches one UTC month for five global points, with approximately fifteen surface variables. This is gridded historical weather/reanalysis, **not independent weather station truth**, and must not be scored as such. Outputs include per-location SHA-256 fingerprints, missingness reports, and source classification. Collect new independent observations separately for validation.

Provider terms and license review are required before commercial use. Existing GitHub Actions artifacts expire after 30 days; persistent storage and retention policy are prerequisites for scaling beyond pilot batches.

### Staged next steps

1. Confirm one live search-time sample and one rich-history pilot; audit missing fields and response times.
2. Establish persistent storage, dataset catalog, source licenses and request budgets.
3. Run bounded collection waves across years, seasons, geographies and elevation/coastal categories; do not start 5,000 × 120 months all at once.
4. Integrate a secured search endpoint with the Atmos website after the backend passes live reliability and forecast correctness tests.
