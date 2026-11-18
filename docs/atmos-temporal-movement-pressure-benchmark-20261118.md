# Atmos historical movement, pressure tendency, and independent regional evaluation — 2026-11-18

## Verified runs

- [Successful temporal transport workflow](https://github.com/msbowman87-cmd/archer-atmos/actions/runs/44337253373). Data artifact: atmos-temporal-transport-pressure-spatial-benchmark, including original archive/source hashes, row-level screening summaries and fitted weights.
- [Successful full code tests](https://github.com/msbowman87-cmd/archer-atmos/actions/runs/44337274480).
- Implemented in scripts/atmos_temporal_transport_pilot.py and tests/test_atmos_temporal_transport_pilot.py, on research/daily-walk-forward-20261101 only. Production main was not changed or deployed.

## Research design

- Genuine NOAA GHCNh sources: **128 original 2022–2025 annual files from 32 stations**, read from verified Atmos research archives.
- Strict source-code + quality-code screening, with no data imputation and timestamp integrity tests.
- **Five geographic training targets**, 2022–2023, **86,825 forecast cases** for fitting.
- **Three separately excluded geographic test targets**, with 2024 validation and 2025 evaluation. Test targets remain entirely absent from the fitting target rows.
- Compare predictions on **identical target timestamps** using four fitted models: station-only, station with local temperature/pressure tendencies, regional geography with tendencies, and historical wind-direction/strength plus bounded estimated parcel transport.
- All predictions are 24-hour temperature forecasts. Each feature must have an observation timestamp no later than forecast issue minus an *assumed* 72-hour data-release delay. The true historical observation availability is not verified.
- Static station elevation retained, and neighbor temperatures use a scenario lapse-rate correction (6.5°C/km). This is not terrain-raster modeling.
- Source station surface pressure and sea-level pressure are never mixed in absolute values; only within-station pressure **changes** may be compared.
- Original source files, raw units, and flags preserved. No satellite or radar features in this run.

## Measured independent holdout accuracy (lower MAE is better)

| Geography, year | Cases | Persistence MAE (°C) | Station-only | Station tendencies | Geographic | Transport |
|---|---:|---:|---:|---:|---:|---:|
| Training-target locations, 2024 | 43,606 | 5.1502 | 4.2225 | 4.1638 | 4.1506 | 4.1324 |
| Excluded regions, 2024 | 26,055 | 5.1821 | 4.2917 | 4.2204 | 4.2761 | 4.2468 |
| **Excluded regions, 2025** | **25,563** | **5.2577** | **4.1662** | **4.1382** | 4.2149 | 4.2094 |

The full transport model was 1.046% better than station-only on the independent 2024 geographic holdout, but **1.038% worse** on the independent 2025 geographic holdout. Therefore there is no verified, consistent improvement from transport; do not promote those weights.

The station-tendency variant has lower aggregate 2025 held-out MAE (4.1382°C vs 4.1662°C), but that is a small result, with different effects by region. Further independent evaluation and real availability chronology are necessary.

### 2025 location breakdown

| Held-out NOAA station | Station-only MAE °C | Station-tendency °C | Transport °C | Transport vs station-only |
|---|---:|---:|---:|---:|
| USW00004110 (southern Idaho) | 3.4940 | 3.4267 | 3.5984 | -2.990% |
| USW00014735 (near Albany, NY) | 3.7181 | 3.7559 | 3.7434 | -0.680% |
| USW00024143 (north-central Montana) | 5.2887 | 5.2340 | 5.2886 | +0.001% |

The wind-transport improvement (station-only MAE minus transport MAE) across the three excluded regions in 2025 was **-0.04325°C**. The conditional daily-block bootstrap 95% interval was **[-0.08294°C, +0.00057°C]**, spanning zero. This interval applies only to the fixed selected stations, not to generalization over North America.

Of the 25,563 evaluated 2025 held-out hours, 17,225 had upwind signal, 25,548 had local pressure tendency, and 25,551 had neighboring pressure tendency. These features are actual, quality-screened archived measurements under a conservative timing assumption.

## Interpretation and next safeguards

1. Preserve station-only as default comparator; keep station-tendency as a promising research candidate only.
2. Do not accept transport solely because it won some 2024 cases; 2025 geographic holdout regressed.
3. The assumed 72-hour availability lag creates a 96-hour gap between weather source observation and 24-hour verification. For future dynamic weather, add true source publication timestamps if available, or compare defensible lead/availability scenarios explicitly.
4. Add genuine DEM profiles and terrain exposure with full provenance; station elevations alone cannot represent local sheltering or barriers.
5. Extend to many more independent regions, variables, and prediction horizons. Report errors per terrain, climate, season, and event type. Fit model/hyperparameters without consulting 2025 evaluation outcomes.
6. Use quality-screened historical radar and satellite observation fields only after defensible as-of availability verification.
7. **No production approval** and **no trained 10,000-station Atmos model** are claimed.
