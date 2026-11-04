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
    stations = defaultdict(dict)
    accepted = 0
    with tarfile.open(archive, "r:*") as tar:
        matches = [m for m in tar if m.isfile() and Path(m.name).name == filename]
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one {filename}")
        with tar.extractfile(matches[0]) as stream, gzip.open(stream, "rt", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"station_id", "hour_utc", "temperature_c", "temperature_qc"}
            if not required.issubset(reader.fieldnames or []):
                raise ValueError("Unexpected v3 schema")
            for row in reader:
                if not row["temperature_c"] or row["temperature_qc"] not in {"0","1","4","5"}:
                    continue
                station = row["station_id"]
                time = parse_noaa_hour_utc(row["hour_utc"])
                if time in stations[station]:
                    raise ValueError(f"Duplicate station-hour: {station}, {time}")
                stations[station][time] = float(row["temperature_c"])
                accepted += 1

    result = {"status":"exploratory_not_certified", "shard":shard,
              "availability_lag_hours_assumed":lag_hours,
              "availability_lag_is_not_verified":True,
              "accepted_temperature_rows":accepted,
              "station_count":len(stations),
              "method":"28-day same-hour baseline plus causal rolling residual correction",
              "horizons":{}}
    lag = timedelta(hours=lag_hours)
    for horizon in horizons:
        delta = timedelta(hours=horizon)
        totals = defaultdict(lambda: [0, 0., 0.])
        station_year = defaultdict(lambda: [0, 0., 0.])
        for station, readings in stations.items():
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
                actual = readings[target]
                # Residual becomes usable only once actual observation is available.
                pending.append((target + lag, actual - predicted))
                year = str(target.year)
                for bucket in (totals[year], station_year[(station, year)]):
                    bucket[0] += 1
                    bucket[1] += abs(actual-base)
                    bucket[2] += abs(actual-predicted)
        result["horizons"][str(horizon)] = {
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
    print(json.dumps({"shard":args.shard,"accepted_rows":report["accepted_temperature_rows"],
                      "stations":report["station_count"],
                      "year_counts":{h:{y:v["cases"] for y,v in x["by_year"].items()}
                                     for h,x in report["horizons"].items()}}))


if __name__=="__main__":
    main()
