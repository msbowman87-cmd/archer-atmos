"""Four seasonal weeks of *real* archived GOES-16 and NEXRAD features.

Bounded to 4 six-hourly samples each calendar day; not 672 hourly samples.
Features include validated NOAA station elevations, but no terrain rasters.
This script performs real archive extraction, NOT model fitting or skill tests.
A smoke mode acquires one scan per season before the complete run is started.
"""
import argparse
import csv
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from atmos.historical_remote_sensing_pilot import (
    CSV_FIELDS, extract, iso
)
from atmos.remote_sensing_features import RemoteSensingStore

# ID -> nearest suitable radar site. IDs are in the verified Atmos 1000.
# BOI and MIA remain excluded holdouts, never in training.
STATIONS = {
    "72572024127": ("Salt Lake City", "KMTX", "train"),
    "72483993225": ("Sacramento", "KDAX", "train"),
    "72243012960": ("Houston", "KHGX", "train"),
    "72793024233": ("Seattle Tacoma", "KATX", "train"),
    "72681024131": ("Boise", "KCBX", "holdout"),
    "72202012839": ("Miami", "KAMX", "holdout"),
}
SEASON_STARTS = {
    "winter": "2018-02-04",
    "spring": "2018-05-06",
    "summer": "2018-08-05",
    "fall": "2018-11-04",
}
SAMPLE_HOURS = (0, 6, 12, 18)


def station_audit(metadata, elevation_catalog, output):
    with open(metadata, newline="", encoding="utf-8-sig") as f:
        coords={row["station_id"]:row for row in csv.DictReader(f)}
    elevations={}
    if elevation_catalog:
        with open(elevation_catalog,newline="",encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                key=row["USAF"].strip().zfill(6)+row["WBAN"].strip().zfill(5)
                if key in STATIONS:
                    try:
                        height=float(row["ELEV(M)"])
                        if -500.<=height<=9000.:
                            elevations[key]=height
                    except (TypeError,ValueError):
                        pass
    rows=[]
    for key,(name,radar,split) in STATIONS.items():
        if key not in coords:
            raise ValueError(f"NOAA location missing: {key}")
        lat=float(coords[key]["lat"])
        lon=float(coords[key]["lon"])
        rows.append({
            "station_id":key,"name":name,"radar_site":radar,
            "split":split,"latitude":lat,"longitude":lon,
            "elevation_m":elevations.get(key),
            "elevation_verified":key in elevations,
            "coordinate_source":"NOAA ISD site history",
            "elevation_source":"NOAA ISD station metadata" if key in elevations else "MISSING",
        })
    Path(output).write_text(json.dumps(rows,indent=2)+"\n")
    return rows


def collect(metadata,output,season,days=7,hours=SAMPLE_HOURS,
            elevation_catalog=None,minimum_coverage=0.5):
    if season not in SEASON_STARTS:
        raise ValueError("Expected spring/summer/fall/winter")
    if not 1<=days<=7:
        raise ValueError("One to seven consecutive days per season")
    if not hours or len(hours)!=len(set(hours)) or any(not 0<=h<24 for h in hours):
        raise ValueError("UTC sample hours must be unique and within 0-23")
    root=Path(output)
    root.mkdir(parents=True,exist_ok=True)
    meta=station_audit(metadata,elevation_catalog,root/"station-geography.json")
    entries=[]
    files=[]
    issues=[]
    origin=datetime.strptime(SEASON_STARTS[season],"%Y-%m-%d").replace(
        tzinfo=timezone.utc)
    picked={key:(name,radar) for key,(name,radar,_) in STATIONS.items()}
    for di in range(days):
        day=origin+timedelta(days=di)
        for hour in hours:
            folder=root/f"source-{day:%Y%m%d}-{hour:02d}"
            try:
                extraction=extract(metadata,folder,f"{day:%Y-%m-%d}",hour,
                                   stations=picked)
                with (folder/"station-sensing-pilot.csv").open(newline="") as handle:
                    found=list(csv.DictReader(handle))
                with (folder/"source-manifest.json").open() as handle:
                    manifest=json.load(handle)
                entries.extend(found)
                files.extend(manifest["downloaded_files"])
                issues.append({
                    "sample_utc":f"{day:%Y-%m-%d}T{hour:02d}:00Z",
                    "status":"retrieved",
                    "radar_rows":sum(r["source"]=="radar" for r in found),
                    "satellite_rows":sum(r["source"]=="satellite" for r in found),
                    "files_downloaded":len(manifest["downloaded_files"]),
                })
            except Exception as exc:
                # A partial pilot must accurately describe gaps; never
                # infer missing rainfall=0 or synthetic cloud cover.
                issues.append({
                    "sample_utc":f"{day:%Y-%m-%d}T{hour:02d}:00Z",
                    "status":"error","error":f"{type(exc).__name__}: {exc}",
                })
            finally:
                shutil.rmtree(folder,ignore_errors=True)
    path=root/"station-sensing-history.csv"
    with path.open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=CSV_FIELDS)
        writer.writeheader();writer.writerows(entries)
    store=RemoteSensingStore.from_csv(path)
    matched=[]
    for di in range(days):
        day=origin+timedelta(days=di)
        for hour in hours:
            # Availability known only by conservative assumed 15-min delay.
            issue=day+timedelta(hours=hour+1)
            for station in STATIONS:
                sat=store.latest(station,"satellite",issue)
                radar=store.latest(station,"radar",issue)
                matched.append({
                    "station_id":station,"split":STATIONS[station][2],
                    "forecast_issue_scenario_utc":iso(issue),
                    "satellite_available":sat is not None,
                    "radar_available":radar is not None,
                    "both_available":sat is not None and radar is not None,
                })
    both=sum(x["both_available"] for x in matched)
    coverage=both/len(matched) if matched else 0.
    summary={
        "season":season,"week_start":SEASON_STARTS[season],
        "days":days,"sample_hours_utc":list(hours),
        "forecast_issue_hours_sampled":days*len(hours),
        "training_stations":sorted(k for k,v in STATIONS.items() if v[2]=="train"),
        "excluded_validation_stations":sorted(k for k,v in STATIONS.items() if v[2]=="holdout"),
        "station_issue_scenarios":len(matched),
        "both_sensor_coverage":coverage,
        "satellite_rows":sum(r["source"]=="satellite" for r in entries),
        "radar_rows":sum(r["source"]=="radar" for r in entries),
        "original_archive_files":len(files),
        "verified_elevation_count":sum(s["elevation_verified"] for s in meta),
        "availability_timestamps":"ASSUMED 15min latency after source created/end; unverified",
        "historical_forecast_accuracy_measured":False,
        "sensor_records_are_real":True,
        "source_files":[*files],
        "sample_results":issues,
        "station_issue_coverage":matched,
    }
    (root/"coverage-and-source-provenance.json").write_text(
        json.dumps(summary,indent=2)+"\n")
    compact={key:value for key,value in summary.items()
             if key not in ("source_files","sample_results","station_issue_coverage")}
    print(json.dumps(compact,indent=2))
    if coverage<minimum_coverage:
        raise RuntimeError(f"Real matched sensor coverage below required {minimum_coverage}: {coverage:.1%}")
    return summary


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--metadata",required=True)
    p.add_argument("--elevation-catalog")
    p.add_argument("--output",required=True)
    p.add_argument("--season",required=True,choices=SEASON_STARTS)
    p.add_argument("--days",type=int,default=7)
    p.add_argument("--hours",default="0,6,12,18")
    p.add_argument("--minimum-coverage",type=float,default=0.5)
    a=p.parse_args()
    collect(a.metadata,a.output,a.season,a.days,
            tuple(int(i) for i in a.hours.split(",")),
            a.elevation_catalog,a.minimum_coverage)

if __name__=="__main__":
    main()
