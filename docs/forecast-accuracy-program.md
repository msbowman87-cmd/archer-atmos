# Atmos forecast verification and improvement program

Status: foundation in progress; NOT production-certified. The successful Twin Falls pilot compared UTC model days to station daily summaries with unverified local-day boundaries. Its apparent 3.99% and 34.44% gains are exploratory, not deployable evidence.

## Mandatory prerequisites
1. Collect subdaily station observations with timestamps, time zones, QC flags, and measurement units. Aggregate to exactly the model's forecast interval (00:00–00:00 UTC for current archived runs), including daylight-saving transitions. Reject comparisons where alignment or coverage cannot be verified. Do not silently substitute reanalysis for independent observations.
2. Preserve true forecast issuance/availability timestamps and valid start/end times. Never allow observations or forecasts published after issue time into features used for prediction.
3. Track station elevation, siting, sensor reliability, network, climate, season, terrain, coastal/inland, and missingness. Record independent observation provenance.
4. Add baseline models (raw ECMWF, persistence, climatology, other legally available NWP), and train corrections only on earlier dates. Separate training, validation, and final untouched test periods. Group by forecast initialization/valid date to prevent duplicate-lead leakage; bootstrap uncertainty by dates and weather events.
5. Expand to representative US and global stations: urban/rural, mountains, deserts, tropical, maritime, polar, high elevations. Stratify by region, season, lead day, and weather regime. Never declare global skill from one station.

## Verify each forecast target separately
- Temperature: maximum, minimum, mean, apparent temperature; MAE, RMSE, bias, heat/cold threshold recall.
- Precipitation: occurrence, amount, intensity, heavy rain, snow/rain phase; MAE, event precision/recall, Brier score and reliability for probabilities, extremes.
- Wind: sustained speed, gust, direction (circular error), damaging gust events.
- Humidity/dew point, surface pressure, cloud cover, visibility/fog, solar radiation, snow depth/snowfall, UV where measured.
- Severe weather: lightning, thunderstorms, hail, tornado, flood, wildfire-weather risks; event-specific authoritative datasets, calibrated probabilities, rarity-aware verification and high recall requirements. Never imply day-30 deterministic severe weather skill.
- Validate physical consistency (dew point <= temperature, probabilities 0–100%, nonnegative precipitation, daily extrema ordering, units, timing) and uncertainty/calibration.

## Deployment gates
- Require adequate sample size, paired baseline comparisons and confidence intervals per region/season/lead/variable.
- Reject changes that materially worsen extreme-weather misses, calibration, or performance for underserved regions even when global MAE improves.
- No production change without explicit approval. Canary and rollback required.
- Days 16–30 require an actual long-range ensemble/subseasonal source, probabilistic evaluation, and separately stated confidence; do not extrapolate ECMWF 10-day runs.
- Show honest limitations and forecast confidence to users. No promise of universal accuracy.

## Current implementation
- atmos/multimetric_validation.py scores independently aligned, paired observations across 12 numerical metrics and precipitation-event confusion counts; refuses to score when interval alignment is unverified.
- tests/test_multimetric_validation.py exercises alignment gate, missing-data handling, multiple metrics, event counts and duplicate rejection.
- The previous paired_comparison.py is exploratory and must not be treated as certified.
- NEXT: obtain subdaily observations, align UTC boundaries, expand stations and variables, train cross-validated corrections, quantify uncertainty, then test prospective forecasts.
