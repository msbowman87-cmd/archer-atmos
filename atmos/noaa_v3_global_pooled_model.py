"""Build a genuinely pooled Atmos model and evaluate an excluded station.

Training: each eligible station contributes every verifiable hourly target for
all 8 metrics / 24, 48, 72-hour horizons. Forecast features are constructed
strictly from observations available by the issue time (assumed NOAA lag).
Each shard saves linear-regression sufficient statistics; aggregation sums
those statistics across all OTHER stations and solves one shared ridge model.
The held-out station contributes ZERO training labels or fitted parameters.
All model coefficients and sufficient statistics are saved as a checkpoint.
"""
import argparse
import csv
import gzip
import json
import math
import tarfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

METRICS = (
    "temperature_c", "dewpoint_c", "relative_humidity_pct", "wind_speed_mps",
    "wind_direction_deg", "sea_level_pressure_hpa", "visibility_m", "precip_1h_mm"
)
QC_COLUMNS = (
    "temperature_qc", "dewpoint_qc", None, "wind_speed_qc",
    "wind_direction_qc", "sea_level_pressure_qc", "visibility_qc", "precip_1h_qc"
)
SCALES = np.array([15.,15.,30.,5.,90.,15.,10000.,2.],dtype=np.float64)
OFFSETS = np.array([0.,0.,50.,0.,0.,1013.25,0.,0.],dtype=np.float64)
HORIZONS = (24, 48, 72)
NFEATURES = 21
HOLDOUT = "72681024131"  # Boise Air Terminal / Gowen Field; excluded globally.
LAG_HOURS = 72
MAX_AGE_HOURS = 336
QC = {"0","1","4","5"}
EPOCH = datetime(1970,1,1,tzinfo=timezone.utc)
FEATURE_NAMES = (
    "bias","utc_sin","utc_cos","solar_sin","solar_cos",
    "year_sin","year_cos","latitude_sin","latitude_cos",
    "last_temp","last_dewpoint","last_humidity","last_wind_speed",
    "wind_dir_sin","wind_dir_cos","last_pressure","last_visibility",
    "last_precip","own_last_value","own_age","own_24h_trend"
)

def parse_hour(value):
    dt = datetime.fromisoformat(value.replace("Z","+00:00"))
    if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
    return int((dt.astimezone(timezone.utc)-EPOCH).total_seconds()//3600)

def read_shard(path,shard):
    required={"station_id","hour_utc",*METRICS}
    target=f"normalized-shard-{shard:02d}.csv.gz"
    stations=defaultdict(list)
    with tarfile.open(path,"r:*") as tar:
        members=[i for i in tar if i.isfile() and Path(i.name).name==target]
        if len(members)!=1: raise ValueError(f"Expected one {target}; got {len(members)}")
        with tar.extractfile(members[0]) as raw:
            with gzip.open(raw,"rt",newline="") as inp:
                reader=csv.DictReader(inp)
                if not required.issubset(reader.fieldnames or []): raise ValueError("Unexpected NOAA v3 schema")
                for row in reader:
                    v=np.full(8,np.nan,dtype=np.float32)
                    for i,metric in enumerate(METRICS):
                        if row[metric] and (QC_COLUMNS[i] is None or row.get(QC_COLUMNS[i]) in QC):
                            try:
                                value=float(row[metric])
                                if math.isfinite(value): v[i]=value
                            except ValueError: pass
                    if np.isfinite(v).any():
                        stations[row["station_id"]].append((parse_hour(row["hour_utc"]),v))
    return stations

def hourly_station(rows):
    rows.sort(key=lambda x:x[0])
    hours=np.array([t for t,_ in rows],dtype=np.int64)
    if len(np.unique(hours))!=len(hours): raise ValueError("Duplicate station-hour")
    start,end=int(hours[0]),int(hours[-1])
    data=np.full((end-start+1,8),np.nan,dtype=np.float32)
    data[hours-start,:]=np.stack([v for _,v in rows])
    return start,data

def latest_valid(data):
    n=len(data)
    ix=np.arange(n,dtype=np.int32)
    out=np.empty((n,8),dtype=np.int32)
    for m in range(8):
        out[:,m]=np.maximum.accumulate(np.where(np.isfinite(data[:,m]),ix,-1))
    return out

def model_rows(start,data,latitude,longitude,horizon,lag=LAG_HOURS):
    """Vectorized as-issued inputs; no observations after issue-minus-lag."""
    n=len(data)
    hours=start+np.arange(n,dtype=np.int64)
    cutoff=np.arange(n,dtype=np.int32)-horizon-lag
    latest=latest_valid(data)
    # Slice latest using an index known no later than the forecast issue.
    ids=np.full((n,8),-1,dtype=np.int32)
    valid=cutoff>=0
    ids[valid]=latest[cutoff[valid],:]
    safe=np.maximum(ids,0)
    present=(ids>=0)
    known=np.where(present,np.take_along_axis(data,safe,axis=0),np.nan)
    known=np.where(np.isfinite(known),known,np.nan)
    solar_phase=2.*np.pi*((hours%24+longitude/15.)/24.)
    utc_phase=2.*np.pi*(hours%24)/24.
    # Epoch-based tropical-year phase; consistent across all shards.
    year_phase=2.*np.pi*hours/(24.*365.2425)
    base=np.zeros((n,NFEATURES),dtype=np.float32)
    base[:,0]=1.
    base[:,1]=np.sin(utc_phase);base[:,2]=np.cos(utc_phase)
    base[:,3]=np.sin(solar_phase);base[:,4]=np.cos(solar_phase)
    base[:,5]=np.sin(year_phase);base[:,6]=np.cos(year_phase)
    base[:,7]=math.sin(math.radians(latitude))
    base[:,8]=math.cos(math.radians(latitude))
    for metric,col in [(0,9),(1,10),(2,11),(3,12),(5,15),(6,16),(7,17)]:
        z=(known[:,metric]-OFFSETS[metric])/SCALES[metric]
        base[:,col]=np.clip(np.nan_to_num(z,nan=0.),-5.,5.)
    base[:,13]=np.nan_to_num(np.sin(np.radians(known[:,4])),nan=0.)
    base[:,14]=np.nan_to_num(np.cos(np.radians(known[:,4])),nan=0.)
    return base,ids,known,hours

def samples(start,data,latitude,longitude,horizon,lag=LAG_HOURS):
    base,ids,known,hours=model_rows(start,data,latitude,longitude,horizon,lag)
    index=np.arange(len(data),dtype=np.int32)
    result=[]
    for m in range(8):
        actual=data[:,m].astype(np.float64)
        prior=known[:,m].astype(np.float64)
        # At issue time the most recent observation cannot be over 14 days old.
        eligible=np.isfinite(actual)&np.isfinite(prior)&(index-ids[:,m]-horizon<=MAX_AGE_HOURS)
        # Skip verification cases with insufficient observational history.
        chosen=np.nonzero(eligible)[0]
        if not len(chosen):
            result.append((np.empty((0,NFEATURES)),np.empty(0),np.empty(0),np.empty(0),np.empty(0,dtype=np.int64)))
            continue
        x=base[chosen,:].copy()
        x[:,18]=np.clip((prior[chosen]-OFFSETS[m])/SCALES[m],-5.,5.)
        x[:,19]=np.clip((chosen-ids[chosen,m]-horizon)/168.,0.,2.)
        # Trend uses another earlier observation (not an unavailable target reading).
        prev_cutoff=np.maximum(ids[chosen,m]-24,0)
        old=latest_valid(data)[prev_cutoff,m]
        old_safe=np.maximum(old,0)
        old_values=data[old_safe,m]
        slope=np.where((old>=0)&np.isfinite(old_values),(prior[chosen]-old_values)/SCALES[m],0.)
        if m==4:
            slope=np.where((old>=0)&np.isfinite(old_values),
                           ((prior[chosen]-old_values+180.)%360.-180.)/SCALES[m],0.)
        x[:,20]=np.clip(slope,-4.,4.)
        delta=actual[chosen]-prior[chosen]
        if m==4: delta=(delta+180.)%360.-180.
        # Robust fit target; evaluation always uses full unclipped actual readings.
        y=np.clip(delta/SCALES[m],-4.,4.)
        result.append((x,y,prior[chosen],actual[chosen],hours[chosen]))
    return result

def fit_shard(archive,shard,metadata,output,holdout=HOLDOUT):
    meta={}
    with open(metadata,newline="",encoding="utf-8-sig") as f:
        for item in csv.DictReader(f):
            meta[item["station_id"]]=(float(item["lat"]),float(item["lon"]))
    stations=read_shard(archive,shard)
    gram=np.zeros((8,3,NFEATURES,NFEATURES),dtype=np.float64)
    rhs=np.zeros((8,3,NFEATURES),dtype=np.float64)
    counts=np.zeros((8,3),dtype=np.int64)
    trained_stations=[]
    excluded=[]
    for name,rows in sorted(stations.items()):
        start,data=hourly_station(rows)
        if name==holdout:
            np.savez_compressed(Path(output)/"holdout-station.npz",station=name,start=start,data=data)
            excluded.append(name);continue
        if name not in meta: raise ValueError(f"Missing station metadata for {name}")
        lat,lon=meta[name]
        for hi,h in enumerate(HORIZONS):
            for m,(x,y,_,_,_) in enumerate(samples(start,data,lat,lon,h)):
                if len(y):
                    gram[m,hi]+=x.T@x
                    rhs[m,hi]+=x.T@y
                    counts[m,hi]+=len(y)
        trained_stations.append(name)
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(out/f"training-stats-shard-{shard:02d}.npz",
                        gram=gram,rhs=rhs,counts=counts,
                        stations=np.array(trained_stations,dtype="U11"),
                        excluded=np.array(excluded,dtype="U11"))
    print(json.dumps({"shard":shard,"stations_trained":len(trained_stations),
        "station_excluded":excluded,"temperature_24h_cases":int(counts[0,0])}))

def solve_global(grams,targets,count):
    weights=np.zeros((8,3,NFEATURES),dtype=np.float64)
    for m in range(8):
        for hi in range(3):
            if count[m,hi]<1000: raise ValueError(f"Not enough training examples: {METRICS[m]} {HORIZONS[hi]}")
            matrix=grams[m,hi].copy()
            # Shrink ill-conditioned cross-feature correlations and outliers.
            penalty=max(100.,float(count[m,hi])*0.0001)
            matrix+=np.eye(NFEATURES)*penalty
            matrix[0,0]-=penalty*0.99
            weights[m,hi]=np.linalg.solve(matrix,targets[m,hi])
    return weights

def clamp_values(metric,pred):
    if metric==4:return np.mod(pred,360.)
    if metric==2:return np.clip(pred,0.,100.)
    if metric in (3,6,7):return np.maximum(pred,0.)
    return pred

def validate_station(start,data,lat,lon,weights):
    by_year=defaultdict(lambda:[0,0.,0.])
    overall=defaultdict(lambda:[0,0.,0.])
    for hi,h in enumerate(HORIZONS):
        for m,(x,_,prior,actual,hours) in enumerate(samples(start,data,lat,lon,h)):
            if not len(actual):continue
            corrections=np.clip(x@weights[m,hi],-1.,1.)*SCALES[m]
            pred=clamp_values(m,prior+corrections)
            baseline=clamp_values(m,prior)
            if m==4:
                err_base=np.abs((actual-baseline+180.)%360.-180.)
                err_pred=np.abs((actual-pred+180.)%360.-180.)
            else:
                err_base=np.abs(actual-baseline)
                err_pred=np.abs(actual-pred)
            # Derive calendar year from hourly UTC dates; no synthetic hours inserted.
            years=(np.datetime64("1970-01-01T00")+
                   hours.astype("timedelta64[h]")).astype("datetime64[Y]").astype(int)+1970
            key=(METRICS[m],h)
            overall[key][0]+=len(actual)
            overall[key][1]+=float(err_base.sum())
            overall[key][2]+=float(err_pred.sum())
            for year in np.unique(years):
                s=years==year
                item=by_year[(METRICS[m],h,int(year))]
                item[0]+=int(s.sum());item[1]+=float(err_base[s].sum());item[2]+=float(err_pred[s].sum())
    def stats(v):
        n,b,c=v
        return {"cases":n,"baseline_mae":b/n,"model_mae":c/n,
                "improvement_pct":(b-c)*100/b if b else None}
    return {"overall":{f"{m}|{h}":stats(v) for (m,h),v in sorted(overall.items())},
            "by_year":{f"{m}|{h}|{y}":stats(v) for (m,h,y),v in sorted(by_year.items())}}

def combine(directory,metadata,output,holdout=HOLDOUT):
    paths=sorted(Path(directory).rglob("training-stats-shard-??.npz"))
    if len(paths)!=40:raise ValueError(f"Expected 40 training shard stats, got {len(paths)}")
    gram=np.zeros((8,3,NFEATURES,NFEATURES),dtype=np.float64)
    rhs=np.zeros((8,3,NFEATURES),dtype=np.float64)
    counts=np.zeros((8,3),dtype=np.int64)
    trained=set();excluded=[]
    for path in paths:
        with np.load(path) as sample:
            gram+=sample["gram"];rhs+=sample["rhs"];counts+=sample["counts"]
            names=set(str(x) for x in sample["stations"].tolist())
            if trained.intersection(names): raise ValueError("Duplicate trained station in shards")
            trained.update(names)
            excluded.extend(str(x) for x in sample["excluded"].tolist())
    if holdout in trained:raise ValueError("Holdout leaked into global training")
    if excluded!=[holdout]:raise ValueError(f"Holdout must be excluded exactly once: {excluded}")
    if len(trained)!=999:raise ValueError(f"Expected 999 training stations; found {len(trained)}")
    weights=solve_global(gram,rhs,counts)
    files=list(Path(directory).rglob("holdout-station.npz"))
    if len(files)!=1:raise ValueError("One excluded station is required")
    with np.load(files[0]) as z:
        if str(z["station"])!=holdout:raise ValueError("Incorrect holdout station")
        start=int(z["start"]);data=z["data"]
    with open(metadata,newline="",encoding="utf-8-sig") as f:
        info=next((r for r in csv.DictReader(f) if r["station_id"]==holdout),None)
    if info is None:raise ValueError("Holdout station missing metadata")
    results=validate_station(start,data,float(info["lat"]),float(info["lon"]),weights)
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(out/"atmos-global-model-v1.npz",
        weights=weights,gram=gram,rhs=rhs,counts=counts,
        feature_names=np.array(FEATURE_NAMES),variables=np.array(METRICS),
        horizons=np.array(HORIZONS),training_stations=np.array(sorted(trained)),
        lag_hours=np.array(LAG_HOURS),holdout=np.array(holdout))
    report={
        "status":"heldout_station_evaluated_not_operationally_certified",
        "model_name":"Atmos Global Pooled Ridge V1",
        "forecast_model_type":"one shared ridge coefficient vector per variable and horizon",
        "model_training_stations":len(trained),
        "excluded_station":{"id":holdout,"name":info["name"],"lat":float(info["lat"]),"lon":float(info["lon"])},
        "observation_availability_lag_assumed_hours":LAG_HOURS,
        "availability_lag_is_not_verified":True,
        "training_examples":{f"{m}|{h}":int(counts[mi,hi]) for mi,m in enumerate(METRICS) for hi,h in enumerate(HORIZONS)},
        "note":"Global pooled linear model from all available training station-hours. Full model fixed before any heldout evaluation; heldout station never trains model. Historical issue times assume 72h observation delay.",
        "validation":results}
    (out/"heldout-accuracy-report.json").write_text(json.dumps(report,indent=2)+"\n")
    lines=["# Atmos Global Model V1 — Independent Station Validation","",
          f"**Holdout:** {info['name']} ({holdout}); never included among {len(trained)} training stations.",
          "", "**Scope:** All available hours from 2006–2025, 8 variables, 24/48/72h.",
          "**Availability:** 72h observation delay is assumed (unverified).",
          "**Model:** Fixed global pooled ridge model; no training using holdout results.",
          "", "| Variable | Horizon | Verified hours | Baseline MAE | Global model MAE | Change |",
          "|---|---:|---:|---:|---:|---:|"]
    for metric in METRICS:
        for h in HORIZONS:
            x=results["overall"].get(f"{metric}|{h}")
            if x:
                lines.append(f"| {metric} | {h}h | {x['cases']:,} | {x['baseline_mae']:.4f} | {x['model_mae']:.4f} | {x['improvement_pct']:+.2f}% |")
    lines+=["","Positive changes indicate improvement over the latest-available-observation baseline.",
            "This compares an actual held-out station; it does not imply readiness for operational deployment."]
    (out/"heldout-accuracy-report.md").write_text("\n".join(lines)+"\n")
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
        if a.shard is None: p.error("--shard is required for --archive")
        fit_shard(a.archive,a.shard,a.metadata,a.output)
    elif a.input:combine(a.input,a.metadata,a.output)
    else:p.error("Specify --archive and --shard, or --input")
if __name__=="__main__":main()
