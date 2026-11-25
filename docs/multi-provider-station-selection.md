# Atmos multi-provider station selection policy

Use multiple official and licensed station networks to reach 10,000 distinct qualifying locations across the U.S., Canada, Mexico, and Caribbean fallback regions.

Candidate providers: NOAA GHCNh/ISD; Environment and Climate Change Canada; Mexico SMN/CONAGUA; U.S. state mesonets; NOAA MADIS (subject to archival access and use rights); licensed Synoptic Data networks; Caribbean national meteorological services; university and regional mesonets.

## Requirements
1. Every selected station must have verified finite latitude, longitude, and elevation; reject unknown/sentinel elevations.
2. Prefer measured hourly observations for 2016–2025. Track actual variable-by-variable coverage; never infer full hourly completeness from mere station existence.
3. Record source, source station ID, licensing, location, elevation, observation interval, available variables, source QC, timestamp timezone, and retrieval provenance.
4. Deduplicate co-located/cross-listed stations using canonical IDs, geographic proximity, elevation, name, and operator metadata. Preserve distinct sensors where physically meaningful without double-counting locations.
5. Select geographically balanced stations across the U.S. (target 6,000), Canada (2,500), and Mexico (1,500); use verified Caribbean island stations to fill Canadian/Mexican shortages, retaining origin labels.
6. Validate rights and access before downloading or publishing provider-derived records. No claim of access to proprietary archives without verification.
7. Produce reproducible CSV/GeoJSON manifests with selected station IDs, sources, coordinates, elevations, historical coverage and rejection reasons.
8. Treat modeled/reanalysis values separately from direct station observations.

## Current execution status
This is a source-expansion specification. Existing NOAA-only selection script and workflow must be extended with provider-specific inventory adapters, normalization, cross-source deduplication and Caribbean fallback. No 10,000-station selection or historical download has been verified.

## Executed 2026-11-05

The former specification-only status above is superseded by the [executed selection report](station-selection-20261105-report.md). The partial manifest has 6,809 catalog-verified locations, a 3,191-location shortfall, and 529,216 raw observations actually collected. This is not a completed 10,000-station selection or an all-station hourly completeness certification. Inventory acquisition, normalization, distance/crosswalk deduplication, map generation, independent manifest validation and resumable raw collection are now implemented.
