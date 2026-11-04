"""Causal per-station, per-hour, per-year observation-only calibration.

Exploratory: NOAA publication time is unknown; explicit lag is a scenario.
For each station and forecast horizon, correct a 28-day same-hour baseline
using the mean of up to 30 prior *realized* forecast residuals whose
observations would have been available at forecast issue time.
No future observations, random splits, or historical model forecasts.
"""
import argparse
import csv
import gzip
import json
import tarfile
from collections import defaultdict, deque
from datetime import timedelta
from pathlib import Path

from atmos.noaa_v3_observation_calibration import parse_noaa_hour_utc


def run(archive, shard, lag_hours=72, horizons=(24, 48, 72)):
    if lag_hours < 0 or not 0 <= shard < 40:
        raise ValueError("Invalid shard or availability lag")
    filename = f"normalized-shard-{shard:02d}.csv.gz"
    measures = ("temperature_c", "dewpoint_c", "relative_humidity_pct", "wind_speed_mps", "wind_direction_deg", "sea_level_pressure_hpa", "visibility_m", "precip_1h_mm")
    qc_fields = {"temperature_c":"temperature_qc", "dewpoint_c":"dewpoint_qc", "wind_speed_mps":"wind_speed_qc", "wind_direction_deg":"wind_direction_qc", "sea_level_pressure_hpa":"sea_level_pressure_qc", "visibility_m":"visibility_qc", "precip_1h_mm":"precip_1h_qc"}
    stations = defaultdict(lambda: defaultdict(dict))
    counts = defaultdict(int)
    accepted = 0
    with tarfile.open(archive, "r:*") as tar:
        matches = [m for m in tar if m.isfile() and Path(m.name).name == filename]
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one {filename}")
        with tar.extractfile(matches[0]) as stream, gzip.open(stream, "rt", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"station_id", "hour_utc", *measures, *qc_fields.values()}
            if not required.issubset(reader.fieldnames or []):
                raise ValueError("Unexpected v3 schema")
            for row in reader:
                station = row["station_id"]
                time = parse_noaa_hour_utc(row["hour_utc"])
                for metric in measures:
                    value = row[metric]
                    if not value or (metric in qc_fields and row[qc_fields[metric]] not in {"0","1","4","5"}):
                        continue
                    if time in stations[metric][station]:
                        raise ValueError(f"Duplicate station-hour: {metric}, {station}, {time}")
                    stations[metric][station][time] = float(value)
                    counts[metric] += 1

    result = {"status":"exploratory_not_certified", "shard":shard,
              "availability_lag_hours_assumed":lag_hours,
              "availability_lag_is_not_verified":True,
              "accepted_rows_by_variable":dict(counts),
              "station_counts_by_variable":{m:len(stations[m]) for m in measures},
              "variables":list(measures),
              "method":"28-day same-hour baseline plus causal rolling residual correction",
              "horizons":{}}
    lag = timedelta(hours=lag_hours)
    for metric in measures:
      result.setdefault("metrics", {})[metric] = {}
      for horizon in horizons:
        delta = timedelta(hours=horizon)
        totals = defaultdict(lambda: [0, 0., 0.])
        station_year = defaultdict(lambda: [0, 0., 0.])
        for station, readings in stations[metric].items():
            pending = deque()
            known_residuals = deque(maxlen=30)
            for target in sorted(readings):
                issue = target - delta
                # Only previous forecast errors whose verifying observations
                # have become available can influence this issue time.
                while pending and pending[0][0] <= issue:
                    _, residual = pending.popleft()
                    known_residuals.append(residual)
                candidates = []
                for day in range(1, 29):
                    past = target - timedelta(days=day)
                    if past + lag <= issue and past in readings:
                        candidates.append(readings[past])
                if len(candidates) < 7:
                    continue
                base = sum(candidates)/len(candidates)
                correction = sum(known_residuals)/len(known_residuals) if len(known_residuals) >= 7 else 0.
                predicted = base + correction
                if metric == "relative_humidity_pct": predicted = max(0, min(100, predicted))
                if metric == "precip_1h_mm" or metric == "wind_speed_mps" or metric == "visibility_m": predicted = max(0, predicted)
                if metric == "wind_direction_deg":
                    # Circular direction errors must use the shortest angular arc.
                    base %= 360
                    predicted %= 360
                actual = readings[target]
                # Residual becomes usable only once actual observation is available.
                pending.append((target + lag, actual - predicted))
                year = str(target.year)
                if metric == "wind_direction_deg":
                    baseline_error = abs((actual-base+180)%360-180)
                    calibrated_error = abs((actual-predicted+180)%360-180)
                else:
                    baseline_error = abs(actual-base)
                    calibrated_error = abs(actual-predicted)
                for bucket in (totals[year], station_year[(station, year)]):
                    bucket[0] += 1
                    bucket[1] += baseline_error
                    bucket[2] += calibrated_error
        result["metrics"][metric][str(horizon)] = {
            "units": ("degrees" if metric == "wind_direction_deg" else "native_metric_units"),
            "by_year":{year:{"cases":v[0],"baseline_mae_c":v[1]/v[0],
                              "calibrated_mae_c":v[2]/v[0]}
                       for year,v in sorted(totals.items()) if v[0]},
            "by_station_year":{f"{station}|{year}":{"cases":v[0],
                               "baseline_mae_c":v[1]/v[0],
                               "calibrated_mae_c":v[2]/v[0]}
                               for (station,year),v in sorted(station_year.items()) if v[0]},
        }
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive",required=True)
    parser.add_argument("--shard",type=int,required=True)
    parser.add_argument("--output",required=True)
    parser.add_argument("--assumed-lag-hours",type=int,default=72)
    args = parser.parse_args()
    report = run(args.archive,args.shard,args.assumed_lag_hours)
    Path(args.output).parent.mkdir(parents=True,exist_ok=True)
    Path(args.output).write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps({"shard":args.shard,"accepted_rows_by_variable":report["accepted_rows_by_variable"],
                      "station_counts_by_variable":report["station_counts_by_variable"],
                      "year_counts":{m:{h:{y:v["cases"] for y,v in x["by_year"].items()}
                                     for h,x in hs.items()} for m,hs in report["metrics"].items()}}))


if __name__=="__main__":
    main()
