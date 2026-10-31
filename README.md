# Archer Atmos

**Worldwide weather prediction research** — free-first development, with a public project and an existing separate production website at [archer-atmos.netlify.app](https://archer-atmos.netlify.app/).

## Current status

**Search-time weather data:** `atmos/on_demand.py` gathers rich regional model
inputs for arbitrary coordinates and reuses a short-lived local cache. This is
research infrastructure, **not yet wired to the public site** or an approved
calibrated forecast. `atmos/rich_history.py` collects bounded, multi-variable
historical shards; see [`docs/on-demand-data-architecture.md`](docs/on-demand-data-architecture.md).


**Global-first verification:** `atmos/global_validation.py` provides a strict paired
GFS/ECMWF/equal-blend scorer and uses the 200-point equal-area worldwide research
sample as a benchmark design. It does not yet have a 12-month independent station
dataset and does not substantiate global skill. See
[`docs/global-validation-1.md`](docs/global-validation-1.md) for data requirements.

This repository starts with a **small, scheduled research collector** for the public NOAA GFS global forecast grid. It accepts arbitrary latitude/longitude pairs; the six locations in `examples/global_sample.json` are only a worldwide sample, **not a forecast coverage limit**.

- `.github/workflows/ci.yml` runs offline tests on changes.
- `.github/workflows/noaa-collection.yml` requests 12 bounded NOAA GRIB2 subsets every day at 18:30 UTC (six global points, two forecast horizons), and stores 30-day run artifacts with source URLs, issue/valid/retrieval timestamps, and SHA-256 hashes.
- `atmos/collector.py` obtains raw, unmodified NOAA model data. This first workflow **does not yet decode model fields, verify against stations, calibrate, or serve web forecasts**.
- The historical Atmos v0.3 research and calibration packages remain preserved separately while we incrementally integrate and test their decoding, multi-model blending, and verification components.
- Netlify's live website is **not changed** by these GitHub workflows.

## Local commands

```bash
python -m unittest discover -s tests -v
python -m atmos.collector --date YYYYMMDD --cycle 00 --steps 24,27 --output capture
```

Use a date with a currently published NOAA GFS 00 UTC cycle. Scheduled runs can be delayed; if a valid time has already passed, the collector intentionally fails instead of silently representing a past prediction as a future forecast.

## Safety and limits

Forecast coverage anywhere on Earth is the **goal**, subject to the spatial resolution and accuracy of available models. Running six sample points daily does **not** mean all worldwide observations are being ingested. The project is **experimental**: do not use it to make severe weather safety decisions or publish confidence/accuracy claims without independent validation. No passwords, tokens, API keys, or private records should be committed.

The scheduled workflow uses standard free GitHub Actions runners for public repositories and free NOAA data, subject to provider availability and fair-use restrictions. Forecast artifacts currently expire after 30 days; permanent verification storage is future work. NOAA source: https://nomads.ncep.noaa.gov/.

**Licensing:** The source is visible because this repository is public; a software license has not been selected yet.
