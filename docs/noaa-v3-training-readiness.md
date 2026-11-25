# NOAA v3 → issued-forecast training readiness (research only)

The NOAA 2006–2025 quality-filtered v3 release is an **observation archive**,
not a collection of historical forecasts. Quality-filtered observations may
be used as verification targets, but do not imply that matching GFS/ECMWF
issued forecasts or observation publication times exist.

## Leakage barriers

- Forecast predictors must carry an independently evidenced
  `available_at_utc` no later than `issue_time_utc`.
- Issued forecasts require source identifiers, issue time, UTC validity
  interval, and an explicit `source_kind=issued_forecast`.
- Truth observations require independent source identity, a verified
  quality status, UTC observation interval and `published_at_utc`.
- **Do not substitute observation time for publication time.**
- Reanalysis, retrospective analyses and quality-derived humidity are not
  automatically independent forecasts or temporally eligible predictors.
- A missing timestamp means **blocked**, not a synthetic default.
- Split chronologically by forecast issue time, with a gap/embargo
  covering target availability. Freeze later holdout periods before fitting.
- Keep station IDs stable across splits; report station/year/variable
  completeness, and assess geographic generalization separately.

## Gate to actual training

1. Download the v3 global quality report and manifest and verify SHA-256
   checksums for every quality shard; publish exact row/flag/humidity/coverage
   totals from these files, never estimates.
2. Inspect a sample from every shard to map real field names and determine
   which timestamps are directly evidenced. If publication timestamps are
   absent, report the number of blocked records. Do not infer publication
   timestamps from the measurement timestamps.
3. Obtain archived **issued** model forecasts with issue timestamps and
   valid intervals, matching the station/metric/unit/UTC interval.
4. Produce an immutable, manifest-backed chronological split and leakage
   audit before any model fitting or skill claim.

`python -m unittest tests.test_temporal_provenance -v` exercises the
research safeguards. These synthetic unit tests are not a validation of
the actual v3 release or a certification of forecast skill.

No production deployment, v2 mutation, or automated training is performed.
