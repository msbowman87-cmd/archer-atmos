"""Repeatable bounded multi-hour GOES-16 and NEXRAD archive backfill.

Each UTC hour selects actual source files, extracts weather features at
verified NOAA station coordinates, and emits a stitched source table and
coverage/provenance manifest. Sensor timing remains a labeled scenario.
This collector does NOT train a model or compute forecast accuracy.
"""
import argparse
import csv
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from atmos.historical_remote_sensing_pilot import CSV_FIELDS, STATIONS, extract, iso
from atmos.remote_sensing_features import RemoteSensingStore


def batch(metadata,output,date="2018-06-01",start_hour=18,hours=6):
    if not (0<=start_hour<24 and 1<=hours<=24 and start_hour+hours<=24):
        raise ValueError("Select 1 to 24 UTC hours within one calendar day")
    root=Path(output)
    root.mkdir(parents=True,exist_ok=True)
    every_hour=[]
    rows=[]
    provenance=[]
    for hour in range(start_hour,start_hour+hours):
        folder=root/f"hour-{hour:02d}"
        summary=extract(metadata,folder,date,hour)
        with open(folder/"station-sensing-pilot.csv",newline="") as f:
            records=list(csv.DictReader(f))
        with open(folder/"source-manifest.json") as f:
            source=json.load(f)
        rows.extend(records)
        provenance.extend(source["downloaded_files"])
        every_hour.append({
            "hour_utc":f"{date}T{hour:02d}:00Z",
            "records":summary["records"],
            "by_source":summary["by_source"],
            "usable_at_scenario_issue":summary["usable_at_scenario_issue"],
            "source_sha256":source["downloaded_files"],
            "source_observation_selection":source["selection"],
        })
        # Original data stays immutable upstream; avoid retaining gigabytes
        # of downloaded raw imagery/radar in the ephemeral GitHub runner.
        shutil.rmtree(folder/"raw-cache",ignore_errors=True)
    csv_path=root/"station-sensing-history.csv"
    with csv_path.open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    store=RemoteSensingStore.from_csv(csv_path)
    coverage=[]
    origin=datetime.strptime(date,"%Y-%m-%d").replace(tzinfo=timezone.utc)
    for hour in range(start_hour,start_hour+hours):
        issue=origin+timedelta(hours=hour+1)
        for station in STATIONS:
            names,values=store.model_features(station,issue)
            fitted=dict(zip(names,values))
            coverage.append({
                "station_id":station,"forecast_issue_scenario_utc":iso(issue),
                "satellite_available":bool(fitted["satellite_available"]),
                "radar_available":bool(fitted["radar_available"]),
                "satellite_feature_count":sum(fitted[f"{k}_present"]>0 for k in
                    ("cloud_fraction","cloud_top_temperature_k","cloud_top_height_m",
                     "water_vapor_brightness_temperature_k",
                     "cloud_motion_u_mps","cloud_motion_v_mps")),
                "radar_feature_count":sum(fitted[f"{k}_present"]>0 for k in
                    ("max_reflectivity_dbz","rain_rate_mm_h","radial_velocity_mps",
                     "echo_motion_u_mps","echo_motion_v_mps")),
            })
    report={
        "status":"real_historical_remote_sensing_coverage_only",
        "dates":date,
        "station_ids":sorted(STATIONS),
        "hours_attempted":hours,
        "station_issue_pairs":len(coverage),
        "collected_rows":len(rows),
        "satellite_rows":sum(row["source"]=="satellite" for row in rows),
        "radar_rows":sum(row["source"]=="radar" for row in rows),
        "both_available_at_assumed_issue":sum(
            r["satellite_available"] and r["radar_available"] for r in coverage),
        "source_availability_time":"ASSUMED (not historically independently verified)",
        "training_pairs":0,
        "accuracy_measured":False,
        "issue_hour_coverage":coverage,
        "hourly_extraction":every_hour,
        "source_objects":provenance,
    }
    (root/"station-sensing-hourly-coverage.json").write_text(
        json.dumps(report,indent=2)+"\n")
    concise={key:val for key,val in report.items()
             if key not in ("issue_hour_coverage","hourly_extraction","source_objects")}
    print(json.dumps(concise,indent=2))
    if not report["satellite_rows"] or not report["radar_rows"]:
        raise RuntimeError("No verified sensor measurements; cannot pass collector")
    return report


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--metadata",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--date",default="2018-06-01")
    p.add_argument("--start-hour",type=int,default=18)
    p.add_argument("--hours",type=int,default=6)
    args=p.parse_args()
    batch(args.metadata,args.output,args.date,args.start_hour,args.hours)

if __name__=="__main__":
    main()
