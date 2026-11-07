"""Actual hourly prequential learning from NOAA observations.

At each issue hour: (1) ingest only observations that have become available,
(2) update persistent model weights from previously issued forecasts whose
target readings are now available, (3) issue new 24/48/72h predictions.
Every forecast is frozen at issuance. No rolling prediction-error corrections.
Exploratory: NOAA availability timestamps are absent; lag is assumed.
"""
import argparse
import csv
import gzip
import json
import math
import tarfile
from collections import defaultdict, deque
from datetime import timedelta
from pathlib import Path
from atmos.noaa_v3_observation_calibration import parse_noaa_hour_utc

METRICS = {
    "temperature_c":("temperature_qc",15.),
    "dewpoint_c":("dewpoint_qc",15.),
    "relative_humidity_pct":(None,30.),
    "wind_speed_mps":("wind_speed_qc",5.),
    "wind_direction_deg":("wind_direction_qc",90.),
    "sea_level_pressure_hpa":("sea_level_pressure_qc",15.),
    "visibility_m":("visibility_qc",10000.),
    "precip_1h_mm":("precip_1h_qc",2.),
}
QC={"0","1","4","5"}
HORIZONS=(24,48,72)
FEATURES=10

def angular_error(a,b):
    return (a-b+180.)%360.-180.

def clamp(metric,value):
    if metric=="wind_direction_deg": return value%360.
    if metric=="relative_humidity_pct": return max(0.,min(100.,value))
    if metric in ("wind_speed_mps","visibility_m","precip_1h_mm"): return max(0.,value)
    return value

def features(metric,issue,horizon,known):
    """Only use observations in known, whose availability precedes issue."""
    last=known.get(metric)
    if not last: return None
    time,value=last
    if (issue-time).total_seconds()>14*86400: return None
    scale=METRICS[metric][1]
    # Prediction is a learned change from latest available observation.
    # Persistent weights summarize all previous training examples.
    hour=issue.hour*2*math.pi/24
    year=(issue.timetuple().tm_yday-1)*2*math.pi/365.25
    cross=[]
    for other in ("temperature_c","dewpoint_c","relative_humidity_pct",
                  "wind_speed_mps","sea_level_pressure_hpa"):
        record=known.get(other)
        if record and (issue-record[0]).total_seconds()<=14*86400:
            ov=record[1]
            if other=="sea_level_pressure_hpa": ov-=1013.25
            if other=="relative_humidity_pct": ov-=50.
            cross.append(max(-5.,min(5.,ov/METRICS[other][1])))
        else: cross.append(0.)
    x=[1.,math.sin(hour),math.cos(hour),math.sin(year),math.cos(year),
       *cross]
    return value,x

def run(archive,shard,lag_hours=72,horizons=HORIZONS):
    if lag_hours<0 or not 0<=shard<40: raise ValueError("Invalid lag or shard")
    name=f"normalized-shard-{shard:02d}.csv.gz"
    stations=defaultdict(list)
    counts=defaultdict(int)
    with tarfile.open(archive,"r:*") as tar:
        matches=[m for m in tar if m.isfile() and Path(m.name).name==name]
        if len(matches)!=1: raise ValueError(f"Expected one {name}")
        with tar.extractfile(matches[0]) as stream:
            with gzip.open(stream,"rt",newline="") as handle:
                reader=csv.DictReader(handle)
                required={"station_id","hour_utc",*METRICS}
                if not required.issubset(reader.fieldnames or []):
                    raise ValueError("Unexpected normalized schema")
                for row in reader:
                    values={}
                    for metric,(qc,_) in METRICS.items():
                        if row[metric] and (qc is None or row.get(qc) in QC):
                            value=float(row[metric])
                            if math.isfinite(value):
                                values[metric]=value
                                counts[metric]+=1
                    if values:
                        stations[row["station_id"]].append((parse_noaa_hour_utc(row["hour_utc"]),values))
    totals=defaultdict(lambda:[0,0.,0.])
    years=defaultdict(lambda:[0,0.,0.])
    station_year=defaultdict(lambda:[0,0.,0.])
    trained=defaultdict(int)
    for station,observations in stations.items():
        observations.sort(key=lambda x:x[0])
        if len({t for t,_ in observations})!=len(observations):
            raise ValueError(f"Duplicate station-hour {station}")
        if not observations: continue
        # Each station has independent persistent weights per variable/horizon.
        weights=defaultdict(lambda:[0.]*FEATURES)
        seen=defaultdict(int)
        pending=defaultdict(list) # target time -> issued forecast records
        known={}
        index=0
        issue=observations[0][0]
        last=observations[-1][0]
        lag=timedelta(hours=lag_hours)
        while issue<=last:
            # Forecast targets become available only after lag, and training
            # uses the original frozen prediction and feature vector.
            while index<len(observations) and observations[index][0]+lag<=issue:
                observed_at,values=observations[index]
                for metric,actual in values.items():
                    known[metric]=(observed_at,actual)
                for metric,horizon,base,pred,x in pending.pop(observed_at,()):
                    if metric not in values: continue
                    actual=values[metric]
                    scale=METRICS[metric][1]
                    residual=(angular_error(actual,pred) if metric=="wind_direction_deg"
                              else actual-pred)/scale
                    residual=max(-4.,min(4.,residual))
                    key=(metric,horizon)
                    seen[key]+=1
                    # Online SGD: every matured forecast teaches persistent
                    # weights; learning rate decays as historical experience grows.
                    rate=0.015/math.sqrt(1.+seen[key]/1000.)
                    for k in range(FEATURES):
                        weights[key][k]+=rate*(residual*x[k]-0.0001*weights[key][k])
                    trained[key]+=1
                    error_base=(abs(angular_error(actual,base))
                                if metric=="wind_direction_deg" else abs(actual-base))
                    error_pred=(abs(angular_error(actual,pred))
                                if metric=="wind_direction_deg" else abs(actual-pred))
                    year=str(observed_at.year)
                    for bucket in (totals[key],years[(metric,horizon,year)],
                                   station_year[(metric,horizon,station,year)]):
                        bucket[0]+=1
                        bucket[1]+=error_base
                        bucket[2]+=error_pred
                index+=1
            for metric in METRICS:
                for horizon in horizons:
                    f=features(metric,issue,horizon,known)
                    if f is None: continue
                    base,x=f
                    key=(metric,horizon)
                    change=sum(a*b for a,b in zip(weights[key],x))*METRICS[metric][1]
                    # Bound extrapolation; does not rewrite historical forecasts.
                    change=max(-METRICS[metric][1],min(METRICS[metric][1],change))
                    predicted=clamp(metric,base+change)
                    target=issue+timedelta(hours=horizon)
                    if target<=last:
                        pending[target].append((metric,horizon,base,predicted,x))
            issue+=timedelta(hours=1)
        # The loop above stores grouped pending forecasts; conversion is
        # handled by the append-only target bucket below.
    def report_bucket(v):
        n,b,c=v
        return {"cases":n,"baseline_mae_c":b/n,"calibrated_mae_c":c/n} if n else None
    report={"status":"exploratory_not_certified","shard":shard,
            "availability_lag_hours_assumed":lag_hours,
            "availability_lag_is_not_verified":True,
            "method":"hour-by-hour persistent online SGD; frozen forecasts, delayed labels",
            "accepted_rows_by_variable":dict(counts),
            "station_counts_by_variable":{m:sum(any(m in values for _,values in obs) for obs in stations.values()) for m in METRICS},
            "variables":list(METRICS),"trained_examples":{f"{m}|{h}":v for (m,h),v in trained.items()},
            "metrics":{}}
    for metric in METRICS:
        report["metrics"][metric]={}
        for horizon in horizons:
            report["metrics"][metric][str(horizon)]={
                "units":"degrees" if metric=="wind_direction_deg" else "native_metric_units",
                "by_year":{year:report_bucket(v) for (m,h,year),v in sorted(years.items()) if (m,h)==(metric,horizon) and v[0]},
                "by_station_year":{f"{station}|{year}":report_bucket(v) for (m,h,station,year),v in sorted(station_year.items()) if (m,h)==(metric,horizon) and v[0]}}
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--archive",required=True)
    p.add_argument("--shard",type=int,required=True)
    p.add_argument("--assumed-lag-hours",type=int,default=72)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    result=run(args.archive,args.shard,args.assumed_lag_hours)
    Path(args.output).parent.mkdir(parents=True,exist_ok=True)
    Path(args.output).write_text(json.dumps(result,indent=2))
    print(json.dumps({"shard":args.shard,"trained_examples":result["trained_examples"]}))

if __name__=="__main__": main()
