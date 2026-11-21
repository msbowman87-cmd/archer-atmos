"""Aggregate all 40 NOAA calibration artifacts into an auditable report."""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

VARIABLE_UNITS = {
    "temperature_c":"°C", "dewpoint_c":"°C",
    "relative_humidity_pct":"percentage points",
    "wind_speed_mps":"m/s", "wind_direction_deg":"degrees",
    "sea_level_pressure_hpa":"hPa", "visibility_m":"m",
    "precip_1h_mm":"mm"
}

def add(bucket, record):
    n = int(record["cases"])
    bucket[0] += n
    # Aggregate absolute error totals, NEVER average station/year MAEs unweighted.
    bucket[1] += n * float(record["baseline_mae_c"])
    bucket[2] += n * float(record["calibrated_mae_c"])

def summary(bucket):
    n, base, calibrated = bucket
    if not n:
        return {"cases":0}
    b, c = base/n, calibrated/n
    return {"cases":n, "baseline_mae":b, "calibrated_mae":c,
            "absolute_improvement":b-c,
            "relative_improvement_pct":100*(b-c)/b if b else None,
            "improved":c<b}

def aggregate(directory):
    paths = list(Path(directory).rglob("shard-??-report.json"))
    if len(paths) != 40:
        raise ValueError(f"Expected exactly 40 shard reports; found {len(paths)}")
    reports = [json.loads(p.read_text(encoding="utf-8")) for p in paths]
    shards = [r["shard"] for r in reports]
    if sorted(shards) != list(range(40)):
        raise ValueError(f"Duplicate or missing shards: {sorted(shards)}")
    for r in reports:
        if r.get("status") != "exploratory_not_certified" or r.get("availability_lag_hours_assumed") != 72:
            raise ValueError(f"Unexpected provenance or lag in shard {r['shard']}")
        if set(r["metrics"]) != set(VARIABLE_UNITS):
            raise ValueError(f"Missing metrics in shard {r['shard']}")
    buckets = defaultdict(lambda:[0,0.,0.])
    year_buckets = defaultdict(lambda:[0,0.,0.])
    station_buckets = defaultdict(lambda:[0,0.,0.])
    observations = defaultdict(int)
    for r in reports:
        for metric, count in r["accepted_rows_by_variable"].items():
            observations[metric] += count
        for metric, horizons in r["metrics"].items():
            if set(horizons) != {"24","48","72"}:
                raise ValueError(f"Missing horizon in shard {r['shard']}")
            for horizon, data in horizons.items():
                for year, item in data["by_year"].items():
                    add(buckets[(metric,horizon)],item)
                    add(year_buckets[(metric,horizon,year)],item)
                for key, item in data["by_station_year"].items():
                    station, year = key.rsplit("|",1)
                    add(station_buckets[(metric,horizon,station,year)],item)
    return {
        "status":"exploratory_not_certified",
        "completed_shards":40,
        "source_run":41934856062,
        "assumed_observation_availability_delay_hours":72,
        "historical_availability_unverified":True,
        "note":"This is adaptive same-hour climatology residual calibration, not a trained atmospheric model.",
        "accepted_observations_by_variable":dict(observations),
        "overall":{f"{m}|{h}":summary(v) for (m,h),v in sorted(buckets.items())},
        "by_year":{f"{m}|{h}|{y}":summary(v) for (m,h,y),v in sorted(year_buckets.items())},
        "by_station_year":{f"{m}|{h}|{s}|{y}":summary(v) for (m,h,s,y),v in sorted(station_buckets.items())},
    }

def markdown(report):
    lines = [
        "# Atmos — Historical Calibration Progress Report",
        "",
        "## Scope and scientific limitations",
        "",
        "40 NOAA v3 quality shards; available station-hours, 2006–2025; eight weather variables; 24/48/72-hour horizons.",
        "These are exploratory results using an **assumed** 72-hour observation availability lag. Historical publication timestamps are unavailable. Missing station-hours are not imputed.",
        "The model is a 28-day same-hour baseline with sequential rolling residual corrections, not a full atmospheric forecasting model.",
        "The year-by-year table measures changing error across years; it is **not** proof that learning alone caused a trend, because the weather and data coverage also change.",
        "2023–2025 is reported separately, but the online calibration continues updating within those years; it is not a frozen independent holdout.",
        "",
        "## Overall accuracy (weighted by actual verification cases)",
        "",
        "| Variable | Horizon | Cases | Baseline MAE | Calibrated MAE | Change |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for key, v in sorted(report["overall"].items()):
        m,h=key.split("|")
        lines.append(f'| {m} ({VARIABLE_UNITS[m]}) | {h}h | {v["cases"]:,} | {v["baseline_mae"]:.4f} | {v["calibrated_mae"]:.4f} | {v["relative_improvement_pct"]:+.2f}% |')
    lines += ["", "## Chronological year-by-year calibration progress", "",
              "| Variable | Horizon | Year | Cases | Baseline MAE | Calibrated MAE | Improvement |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for key,v in sorted(report["by_year"].items()):
        m,h,y=key.split("|")
        lines.append(f'| {m} | {h}h | {y} | {v["cases"]:,} | {v["baseline_mae"]:.4f} | {v["calibrated_mae"]:.4f} | {v["relative_improvement_pct"]:+.2f}% |')
    lines += ["", "## 2023–2025 evaluation period", "",
              "The evaluation below remains walk-forward and adaptive; it is not a frozen-model holdout.",
              "", "| Variable | Horizon | Cases | Baseline MAE | Calibrated MAE | Improvement |",
              "|---|---:|---:|---:|---:|---:|"]
    for m in VARIABLE_UNITS:
        for h in ("24","48","72"):
            v=[report["by_year"].get(f"{m}|{h}|{y}") for y in ("2023","2024","2025")]
            totals=[sum(x["cases"] for x in v if x),
                    sum(x["cases"]*x["baseline_mae"] for x in v if x),
                    sum(x["cases"]*x["calibrated_mae"] for x in v if x)]
            if totals[0]:
                s=summary(totals)
                lines.append(f'| {m} | {h}h | {s["cases"]:,} | {s["baseline_mae"]:.4f} | {s["calibrated_mae"]:.4f} | {s["relative_improvement_pct"]:+.2f}% |')
    lines += ["", "## Interpretation", "",
              "A positive improvement percentage means the calibrated error is smaller; negative means calibration made predictions worse.",
              "The accompanying JSON contains all station-by-year results, including failures and sparse coverage.",
              "Do not claim causal certification or production readiness from this report alone."]
    return "\n".join(lines)+"\n"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    report=aggregate(a.input)
    output=Path(a.output)
    output.mkdir(parents=True,exist_ok=True)
    (output/"calibration-summary.json").write_text(json.dumps(report,indent=2)+"\n")
    (output/"calibration-progress.md").write_text(markdown(report))
    with (output/"station-year-results.csv").open("w",newline="") as f:
        writer=csv.writer(f)
        writer.writerow(["variable","horizon_hours","station_id","year","cases","baseline_mae","calibrated_mae","relative_improvement_pct"])
        for key,v in sorted(report["by_station_year"].items()):
            m,h,s,y=key.split("|")
            writer.writerow([m,h,s,y,v["cases"],v["baseline_mae"],v["calibrated_mae"],v["relative_improvement_pct"]])
    print(markdown(report),flush=True)

if __name__=="__main__":
    main()
