"""Atmos research V2: pooled, variable-aware forecasting with multiple held-out stations.

Preserves the V1 ridge model for temperature/dewpoint/wind/pressure. Uses
zero-inflated precipitation occurrence and conditional amount models, and
a low-visibility probability model with conservative event-gated forecasts.
Forecasts always use issue-time-available observations (assumed 72-hour lag).
Models are fit on the non-holdout stations only, then frozen before testing.
This is a spatially-held-out *retrospective* global model, NOT chronological
global online training: a full 2006-2025 fit can use future calendar years
from training stations when predicting early years at held-out stations.
"""
import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
from atmos import noaa_v3_global_pooled_model as base

# Boise was previously examined in V1; the other locations are untouched
# development/validation stations and are completely excluded from V2 fitting.
HOLDOUTS = {
    "72681024131": "Boise (development)",
    "70273026451": "Anchorage (cold climate)",
    "72202012839": "Miami (humid subtropical)",
    "93436000488": "Wellington (southern hemisphere)",
}
EXPECTED_TRAINING_STATIONS = 1000 - len(HOLDOUTS)
LOW_VIS_THRESHOLD_M = 5000.0
WET_THRESHOLD_MM = 0.1
WET_LOG_SCALE = math.log1p(50.)
VIS_LOG_SCALE = math.log1p(50000.)
SPECIAL_KEYS = ("rain_occurrence", "wet_amount", "low_visibility", "visibility_level")


def ridge(gram, rhs, count, minimum_cases=1000):
    result = np.zeros(rhs.shape, dtype=np.float64)
    for i in range(rhs.shape[0]):
        if int(count[i]) < minimum_cases:
            raise ValueError(f"Insufficient labeled cases for special target {i}: {count[i]}")
        lam = max(100.0, float(count[i]) * 0.0001)
        matrix = gram[i].copy()
        matrix.flat[::base.NFEATURES + 1] += lam
        matrix[0, 0] -= lam * 0.99
        result[i] = np.linalg.solve(matrix, rhs[i])
    return result


def station_metadata(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    return {r["station_id"]: r for r in rows}


def fit_shard(archive, shard, metadata, output):
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    locations = station_metadata(metadata)
    stations = base.read_shard(archive, shard)
    gram = np.zeros((8, 3, base.NFEATURES, base.NFEATURES), dtype=np.float64)
    rhs = np.zeros((8, 3, base.NFEATURES), dtype=np.float64)
    counts = np.zeros((8, 3), dtype=np.int64)
    special_gram = np.zeros((4, 3, base.NFEATURES, base.NFEATURES), dtype=np.float64)
    special_rhs = np.zeros((4, 3, base.NFEATURES), dtype=np.float64)
    special_counts = np.zeros((4, 3), dtype=np.int64)
    trained, excluded = [], []
    for name, rows in sorted(stations.items()):
        start, observations = base.hourly_station(rows)
        if name in HOLDOUTS:
            np.savez_compressed(out / f"excluded-{name}.npz", station=name,
                                start=start, data=observations)
            excluded.append(name)
            continue
        if name not in locations:
            raise ValueError(f"Station {name} missing NOAA coordinate metadata")
        lat = float(locations[name]["lat"])
        lon = float(locations[name]["lon"])
        for hi, h in enumerate(base.HORIZONS):
            examples = base.samples(start, observations, lat, lon, h)
            for m, (x, y, _, actual, _) in enumerate(examples):
                if not len(y):
                    continue
                gram[m, hi] += x.T @ x
                rhs[m, hi] += x.T @ y
                counts[m, hi] += len(y)
                if m == 7:
                    wet = (actual > WET_THRESHOLD_MM).astype(np.float64)
                    special_gram[0, hi] += x.T @ x
                    special_rhs[0, hi] += x.T @ wet
                    special_counts[0, hi] += len(wet)
                    eligible = wet.astype(bool)
                    if eligible.any():
                        wx = x[eligible]
                        wy = np.clip(np.log1p(actual[eligible]) / WET_LOG_SCALE, 0., 2.)
                        special_gram[1, hi] += wx.T @ wx
                        special_rhs[1, hi] += wx.T @ wy
                        special_counts[1, hi] += len(wy)
                elif m == 6:
                    low = (actual < LOW_VIS_THRESHOLD_M).astype(np.float64)
                    special_gram[2, hi] += x.T @ x
                    special_rhs[2, hi] += x.T @ low
                    special_counts[2, hi] += len(low)
                    transformed = np.log1p(np.maximum(actual, 0.)) / VIS_LOG_SCALE
                    special_gram[3, hi] += x.T @ x
                    special_rhs[3, hi] += x.T @ transformed
                    special_counts[3, hi] += len(transformed)
        trained.append(name)
    np.savez_compressed(out / f"training-stats-shard-{shard:02d}.npz",
        gram=gram, rhs=rhs, counts=counts,
        special_gram=special_gram, special_rhs=special_rhs, special_counts=special_counts,
        stations=np.array(trained, dtype="U11"),
        excluded=np.array(excluded, dtype="U11"))
    print(json.dumps({"shard": shard, "trained": len(trained), "excluded": excluded,
                      "rain_events": int(special_counts[1].sum()),
                      "verified_visibility": int(special_counts[2].sum())}))


def forecast_candidates(metric, hi, x, prior, ordinary_weights, special_weights):
    raw = x @ ordinary_weights[metric, hi]
    normal = base.clamp_values(metric, prior + np.clip(raw, -1., 1.) * base.SCALES[metric])
    if metric == 7:
        rain_prob = np.clip(x @ special_weights[0, hi], 0., 1.)
        wet_log_amount = np.clip(x @ special_weights[1, hi], 0., 1.75)
        conditional_amount = np.expm1(wet_log_amount * WET_LOG_SCALE)
        # MAE-optimal median of a zero-inflated distribution is zero when
        # the estimated dry probability exceeds one half.
        revised = np.where(rain_prob > 0.5, conditional_amount, 0.)
        return revised, normal, {"wet_probability": rain_prob}
    if metric == 6:
        low_prob = np.clip(x @ special_weights[2, hi], 0., 1.)
        proposed = np.expm1(np.clip(x @ special_weights[3, hi], 0., 1.3) * VIS_LOG_SCALE)
        # An explicit confidence gate avoids lowering visibility at every
        # otherwise-clear hour, the major failure mode in V1.
        revised = np.where(low_prob > 0.5, np.minimum(prior, proposed), prior)
        return revised, normal, {"low_visibility_probability": low_prob}
    return normal, normal, {}


def validate_station(start, data, lat, lon, ordinary_weights, special_weights):
    overall = defaultdict(lambda: [0, 0., 0., 0.])
    by_year = defaultdict(lambda: [0, 0., 0., 0.])
    probability = defaultdict(lambda: [0, 0., 0., 0.])
    for hi, horizon in enumerate(base.HORIZONS):
        for m, (x, _, prior, actual, hours) in enumerate(base.samples(
                start, data, lat, lon, horizon)):
            if not len(actual):
                continue
            improved, old, probs = forecast_candidates(
                m, hi, x, prior, ordinary_weights, special_weights)
            baseline = base.clamp_values(m, prior)
            if m == 4:
                eb = np.abs((actual - baseline + 180.) % 360. - 180.)
                ev1 = np.abs((actual - old + 180.) % 360. - 180.)
                ev2 = np.abs((actual - improved + 180.) % 360. - 180.)
            else:
                eb = np.abs(actual - baseline)
                ev1 = np.abs(actual - old)
                ev2 = np.abs(actual - improved)
            years = (np.datetime64("1970-01-01T00") +
                     hours.astype("timedelta64[h]")).astype("datetime64[Y]").astype(int) + 1970
            key = (base.METRICS[m], int(horizon))
            for bucket in (overall[key],):
                bucket[0] += len(actual)
                bucket[1] += float(eb.sum())
                bucket[2] += float(ev1.sum())
                bucket[3] += float(ev2.sum())
            for year in np.unique(years):
                mask = years == year
                item = by_year[(base.METRICS[m], int(horizon), int(year))]
                item[0] += int(mask.sum())
                item[1] += float(eb[mask].sum())
                item[2] += float(ev1[mask].sum())
                item[3] += float(ev2[mask].sum())
            if m in (6, 7):
                target = (actual < LOW_VIS_THRESHOLD_M) if m == 6 else (actual > WET_THRESHOLD_MM)
                p = probs["low_visibility_probability"] if m == 6 else probs["wet_probability"]
                status = probability[key]
                status[0] += len(p)
                status[1] += float(np.square(p - target).sum())  # Brier score
                status[2] += int(target.sum())
                status[3] += int(((p > 0.5) & target).sum())
    def summarize(b):
        n, a, c, d = b
        return {"cases": n, "baseline_mae": a / n, "v1_style_mae": c / n,
                "v2_mae": d / n,
                "improvement_over_baseline_pct": 100. * (a - d) / a if a else None,
                "improvement_over_v1_style_pct": 100. * (c - d) / c if c else None}
    return {
        "overall": {f"{m}|{h}": summarize(b) for (m,h),b in sorted(overall.items()) if b[0]},
        "by_year": {f"{m}|{h}|{year}": summarize(b) for (m,h,year),b in sorted(by_year.items()) if b[0]},
        "event_probabilities": {f"{m}|{h}": {
            "cases": int(b[0]), "brier_score": b[1] / b[0],
            "actual_events": int(b[2]), "events_with_probability_over_half": int(b[3])}
            for (m,h),b in sorted(probability.items()) if b[0]},
    }


def combine(directory, metadata, output):
    paths = sorted(Path(directory).rglob("training-stats-shard-??.npz"))
    if len(paths) != 40:
        raise ValueError(f"Expected 40 training summaries, found {len(paths)}")
    gram = np.zeros((8,3,base.NFEATURES,base.NFEATURES))
    rhs = np.zeros((8,3,base.NFEATURES))
    counts = np.zeros((8,3), dtype=np.int64)
    special_gram = np.zeros((4,3,base.NFEATURES,base.NFEATURES))
    special_rhs = np.zeros((4,3,base.NFEATURES))
    special_counts = np.zeros((4,3), dtype=np.int64)
    trained, excluded = set(), []
    for path in paths:
        with np.load(path) as stats:
            new = set(map(str, stats["stations"].tolist()))
            if trained.intersection(new):
                raise ValueError("Duplicate training station")
            trained.update(new)
            excluded.extend(map(str, stats["excluded"].tolist()))
            gram += stats["gram"]; rhs += stats["rhs"]; counts += stats["counts"]
            special_gram += stats["special_gram"]
            special_rhs += stats["special_rhs"]
            special_counts += stats["special_counts"]
    if set(excluded) != set(HOLDOUTS) or len(excluded) != len(HOLDOUTS):
        raise ValueError(f"Holdout coverage mismatch: {excluded}")
    if len(trained) != EXPECTED_TRAINING_STATIONS or set(HOLDOUTS).intersection(trained):
        raise ValueError(f"Station leakage or missing training stations: {len(trained)}")
    ordinary = base.solve_global(gram, rhs, counts)
    special = np.stack([ridge(special_gram[i], special_rhs[i], special_counts[i])
                        for i in range(4)])
    locations = station_metadata(metadata)
    results = {}
    for station in HOLDOUTS:
        paths = list(Path(directory).rglob(f"excluded-{station}.npz"))
        if len(paths) != 1:
            raise ValueError(f"Missing exactly one excluded station data file for {station}")
        with np.load(paths[0]) as record:
            if str(record["station"]) != station:
                raise ValueError("Holdout identifier mismatch")
            start, data = int(record["start"]), record["data"]
        loc = locations[station]
        scores = validate_station(start, data, float(loc["lat"]), float(loc["lon"]),
                                  ordinary, special)
        results[station] = {"name": loc.get("name", station), "evaluation": scores}
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out / "atmos-global-v2-model.npz",
        weights=ordinary, specialized_weights=special,
        gram=gram, rhs=rhs, counts=counts, special_gram=special_gram,
        special_rhs=special_rhs, special_counts=special_counts,
        feature_names=np.array(base.FEATURE_NAMES),
        variables=np.array(base.METRICS), horizons=np.array(base.HORIZONS),
        training_stations=np.array(sorted(trained)), holdouts=np.array(sorted(HOLDOUTS)),
        assumed_lag_hours=np.array(base.LAG_HOURS))
    report = {
        "status":"research_spatial_holdout_not_operationally_certified",
        "model_name":"Atmos Unified Global V2 — Pooled + Event-Specific Forecasting",
        "training_station_count":len(trained),
        "holdouts":results,
        "assumed_observation_lag_hours":base.LAG_HOURS,
        "temporal_limitation":"Retrospective spatial holdout: full 2006-2025 training from other stations is used when predicting earlier years at excluded stations. This is NOT a strict historical time-causal global backtest.",
        "trained_targets": {f"{m}|{h}": int(counts[i,j])
            for i,m in enumerate(base.METRICS) for j,h in enumerate(base.HORIZONS)},
        "special_target_counts": {f"{m}|{h}":int(special_counts[i,j])
            for i,m in enumerate(SPECIAL_KEYS) for j,h in enumerate(base.HORIZONS)},
    }
    (out/"v2-independent-station-accuracy.json").write_text(json.dumps(report,indent=2)+"\n")
    lines = ["# Atmos Unified Global V2 — Independent Location Accuracy",
             "",f"Training: {len(trained)} stations. Excluded from all fitting: "+", ".join(HOLDOUTS),
             "", "**Important:** A frozen spatial holdout, not a temporally causal 2006-2025 global forecast simulation.",
             "The 72-hour NOAA observation availability lag is an unverified research assumption.",
             "", "Positive improvement percentages mean lower MAE than the baseline.",
             "", "| Station | Weather variable | Horizon | Cases | Baseline MAE | V1-like MAE | V2 MAE | V2 improvement |",
             "|---|---|---:|---:|---:|---:|---:|---:|"]
    for station,info in results.items():
        for key,score in sorted(info["evaluation"]["overall"].items()):
            metric,h = key.split("|")
            lines.append(f"| {info['name']} | {metric} | {h}h | {score['cases']:,} | "
                         f"{score['baseline_mae']:.4f} | {score['v1_style_mae']:.4f} | "
                         f"{score['v2_mae']:.4f} | {score['improvement_over_baseline_pct']:+.2f}% |")
    (out/"v2-independent-station-accuracy.md").write_text("\n".join(lines)+"\n")
    print("\n".join(lines))


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--archive")
    p.add_argument("--shard",type=int)
    p.add_argument("--input")
    p.add_argument("--metadata",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    if a.archive:
        if a.shard is None: p.error("--shard must be supplied with --archive")
        fit_shard(a.archive,a.shard,a.metadata,a.output)
    elif a.input:
        combine(a.input,a.metadata,a.output)
    else:
        p.error("Use --archive or --input")

if __name__=="__main__":
    main()
