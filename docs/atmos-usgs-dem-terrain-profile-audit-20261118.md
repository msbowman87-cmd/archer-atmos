# Atmos USGS 3DEP verified terrain sample — 2026-11-18

**Status:** Source extraction completed and verified. No terrain-enhanced forecasting model has been fit.

- [Successful USGS terrain-source workflow](https://github.com/msbowman87-cmd/archer-atmos/actions/runs/44338661282)
- Artifact: atmos-usgs-3dep-terrain-point-provenance (ID 14442902724), includes verified_usgs_terrain_points.json.
- Source: USGS National Map Elevation Point Query Service, https://apps.nationalmap.gov/epqs/.
- Source code: scripts/atmos_usgs_terrain_profile.py; regression tests: tests/test_atmos_usgs_terrain_profile.py.
- Study targets: NOAA GHCNh IDs USW00094129, USW00004938, USW00014922, USW00004842, USW00000236 (training), USW00004110, USW00014735, USW00024143 (geographic holdouts).
- **All eight stations have a complete five-point profile**. Success: 40 of 40 expected USGS point requests, including center and 5-kilometer offsets north, south, east and west of each station.
- Each actual service response has a source URL, original response SHA-256 digest, fetch time, unit, coordinates, and measured elevation in meters. No synthetic values or missing-height interpolation were used.
- Computed research terrain diagnostics: local 5-point relief, north/south and east/west slope estimates over 10-kilometer baselines, and uphill bearing. Differences between DEM center height and catalog station elevation are recorded rather than rewritten.

**Scientific limitations:** These heights are **interpolated DEM source values**, not independently surveyed station elevations. Five elevation points cannot establish detailed terrain sheltering, mountain passes, local valley inversions, subgrid wind channels, slope roughness, or land cover. Sources can have different horizontal resolutions and vertical references. The information is a static terrain profile acquired in 2026, not a historical weather observation.

**Training gate:** terrain_model_trained=false; training_quality_approved=false. No DEM terrain data entered Atmos forecasting training in this completed source-audit step. Integrating terrain features and testing their incremental forecast skill requires a separate controlled comparison on independent regions, using 2025 holdouts carefully because those scores were already inspected during earlier pilot development. Until then, no claim that terrain has improved forecast skill is justified.

See also the full [temporal pressure and weather movement benchmark](https://github.com/msbowman87-cmd/archer-atmos/blob/research/daily-walk-forward-20261101/docs/atmos-temporal-movement-pressure-benchmark-20261118.md). Its full wind/transport model did not outperform station-only in 2025 holdouts, although station tendency features showed a small average improvement. Research only; production main unchanged.
