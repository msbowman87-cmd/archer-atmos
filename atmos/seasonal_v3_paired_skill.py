"""Atmos V3 per-variable and per-horizon sensor-enhanced spatial validation.

Held-out Boise/Miami readings are never used for fitting. V2 checkpoint was
trained on full 2006–25 history elsewhere; results are retrospective and not
temporally independent operational scores. Historical sensor arrival lag is a
documented but UNVERIFIED 15-minute assumption.
"""
import argparse
import csv
import json
import math
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from atmos import noaa_v3_global_pooled_model as core
from atmos import noaa_v3_global_model_v2 as v2
from atmos.remote_sensing_features import RemoteSensingStore
from atmos.seasonal_remote_sensing_backfill import STATIONS, SEASON_STARTS
from atmos.historical_remote_sensing_pilot import CSV_FIELDS

FEATURES = (
    "bias","elevation_km","elevation_present",
    "sat_present","cloud","cloud_present","vapor_temp","vapor_present",
    "radar_present","radar_reflectivity","reflectivity_present",
    "radial_wind","radial_wind_present","cloud_reflectivity",
    "solar_sin","solar_cos",
)
ABLATIONS = {
    "satellite": (0,3,4,5,6,7,14,15),
    "radar": (0,8,9,10,11,12,14,15),
    "joint_elevation": tuple(range(len(FEATURES))),
}


def issue_hours():
    hours=set()
    for date in SEASON_STARTS.values():
        first=datetime.fromisoformat(date).replace(tzinfo=timezone.utc)
        for day in range(7):
            for h in (0,6,12,18):
                hours.add(core.parse_hour((first+timedelta(days=day,hours=h+1)).isoformat()))
    return hours


def read_sources(seasons):
    rows=[]
    geography={}
    for season in SEASON_STARTS:
        folder=Path(seasons)/f"atmos-v3-season-{season}"
        if not folder.exists():
            raise ValueError(f"Missing season: {season}")
        with (folder/"station-sensing-history.csv").open(newline="") as handle:
            rows.extend(csv.DictReader(handle))
        for geo in json.loads((folder/"station-geography.json").read_text()):
            station=geo["station_id"]
            if station in geography:
                for key in ("split","latitude","longitude","elevation_m"):
                    if geo[key]!=geography[station][key]:
                        raise ValueError("Inconsistent station metadata across seasons")
            geography[station]=geo
    if set(geography)!=set(STATIONS):
        raise ValueError("Missing station geography")
    if any(not row["availability_provenance"].startswith("ASSUMED_") for row in rows):
        raise ValueError("Missing assumed-availability provenance labels")
    with tempfile.NamedTemporaryFile(mode="w+",suffix=".csv",newline="") as tmp:
        writer=csv.DictWriter(tmp,fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
        tmp.flush()
        store=RemoteSensingStore.from_csv(tmp.name)
    return store,geography


def read_actual_stations(directory):
    stations=set(STATIONS)
    found={}
    lower=core.parse_hour("2017-12-01T00:00:00Z")
    upper=core.parse_hour("2019-01-10T00:00:00Z")
    for file in sorted(Path(directory).glob("atmos-quality-shard-??.tar")):
        shard=int(file.stem.rsplit("-",1)[-1])
        records=core.read_shard(file,shard)
        for station,values in records.items():
            if station in stations:
                if station in found:
                    raise ValueError(f"Duplicate station {station}")
                found[station]=core.hourly_station([
                    (h,row) for h,row in values if lower<=h<=upper
                ])
    if set(found)!=stations:
        raise ValueError(f"Missing actual NOAA station history: {sorted(stations-set(found))}")
    return found


def feature_vector(store,geo,station,issue):
    names,values=store.model_features(station,issue)
    d=dict(zip(names,values))
    elevation=geo["elevation_m"]
    longitude=float(geo["longitude"])
    n=core.parse_hour(issue.isoformat())
    phase=2*math.pi*(n%24+longitude/15.)/24.
    cloud=d["cloud_fraction"] if d["cloud_fraction_present"] else 0.
    reflectivity=d["max_reflectivity_dbz"] if d["max_reflectivity_dbz_present"] else 0.
    return np.array([
        1.,0. if elevation is None else float(elevation)/2000.,
        float(elevation is not None),
        d["satellite_available"],cloud,d["cloud_fraction_present"],
        d["water_vapor_brightness_temperature_k"],
        d["water_vapor_brightness_temperature_k_present"],
        d["radar_available"],reflectivity,d["max_reflectivity_dbz_present"],
        d["radial_velocity_mps"],d["radial_velocity_mps_present"],
        cloud*reflectivity,math.sin(phase),math.cos(phase),
    ],dtype=np.float64)


def station_examples(station,history,geo,store,weights,special,selected_issues):
    start,data=history
    lat,lon=float(geo["latitude"]),float(geo["longitude"])
    output={}
    for hi,h in enumerate(core.HORIZONS):
        source=core.samples(start,data,lat,lon,h)
        for m,(x,_,prior,actual,targets) in enumerate(source):
            if not len(targets):
                continue
            select=np.flatnonzero(np.isin(targets-h,list(selected_issues)))
            if not len(select):
                continue
            x=x[select];prior=prior[select];actual=actual[select]
            targets=targets[select]
            sensor=[]
            allowed=[]
            for i,target in enumerate(targets):
                issue=core.EPOCH+timedelta(hours=int(target)-h)
                # Evaluation on IDENTICAL hours with both sources available.
                if store.latest(station,"satellite",issue) is None:
                    continue
                if store.latest(station,"radar",issue) is None:
                    continue
                allowed.append(i)
                sensor.append(feature_vector(store,geo,station,issue))
            if not allowed:
                continue
            x=x[allowed];prior=prior[allowed];actual=actual[allowed]
            remote=np.stack(sensor)
            forecast,_,_=v2.forecast_candidates(m,hi,x,prior,weights,special)
            if m==7:
                p2=np.clip(x@special[0,hi],0.,1.)
                residual=(actual>v2.WET_THRESHOLD_MM).astype(float)-p2
                task="precip_event"
            elif m==6:
                p2=np.clip(x@special[2,hi],0.,1.)
                residual=(actual<v2.LOW_VIS_THRESHOLD_M).astype(float)-p2
                task="visibility_event"
            else:
                p2=None
                residual=actual-forecast
                if m==4:
                    residual=(residual+180.)%360.-180.
                residual=residual/core.SCALES[m]
                task="continuous"
            output[(m,hi)]={
                "remote":remote,"residual":np.clip(residual,-2.,2.),
                "actual":actual,"prior":prior,"v2":forecast,
                "v2_features":x,"v2_event_p":p2,"task":task
            }
    return output


def fit_ablation(training):
    fitted={}
    sample_counts={}
    for ablation,cols in ABLATIONS.items():
        for m in range(8):
            for hi in range(3):
                buckets=[rows[(m,hi)] for rows in training.values()
                         if (m,hi) in rows]
                n=sum(len(b["residual"]) for b in buckets)
                sample_counts[(ablation,m,hi)]=n
                coef=np.zeros(len(FEATURES),dtype=float)
                if n>=24:
                    features=np.concatenate([b["remote"][:,cols] for b in buckets])
                    target=np.concatenate([b["residual"] for b in buckets])
                    gram=features.T@features
                    ridge=max(25.,n*.06)
                    gram+=np.eye(len(cols))*ridge
                    gram[0,0]-=ridge*.95
                    coef[np.asarray(cols)]=np.linalg.solve(gram,features.T@target)
                fitted[(ablation,m,hi)]=coef
    return fitted,sample_counts


def predict(bucket,m,hi,coef,special):
    adjustment=np.clip(bucket["remote"]@coef,-1.,1.)
    if m in (6,7):
        probability=np.clip(bucket["v2_event_p"]+adjustment,0.,1.)
        if m==7:
            conditional=np.expm1(np.clip(
                bucket["v2_features"]@special[1,hi],0.,1.75
            )*v2.WET_LOG_SCALE)
            return np.where(probability>.5,conditional,0.),probability
        level=np.expm1(np.clip(
            bucket["v2_features"]@special[3,hi],0.,1.3
        )*v2.VIS_LOG_SCALE)
        return np.where(probability>.5,np.minimum(bucket["prior"],level),
                        bucket["prior"]),probability
    value=core.clamp_values(m,bucket["v2"]+adjustment*core.SCALES[m])
    return value,None


def score(holdouts,coefficients,special):
    output={}
    for ablation in ABLATIONS:
        by_station={}
        for station,examples in sorted(holdouts.items()):
            by_metric={}
            for (m,hi),bucket in sorted(examples.items()):
                pred,prob=predict(bucket,m,hi,coefficients[(ablation,m,hi)],special)
                actual=bucket["actual"]
                earlier=bucket["v2"]
                if m==4:
                    err=lambda forecast:np.abs((actual-forecast+180.)%360.-180.)
                else:
                    err=lambda forecast:np.abs(actual-forecast)
                old=float(np.mean(err(earlier)))
                new=float(np.mean(err(pred)))
                cell={
                    "cases":len(actual),
                    "v2_mae":old,"v3_mae":new,
                    "v3_vs_v2_skill_pct":(old-new)*100/old if old else None,
                }
                if prob is not None:
                    event=(actual>v2.WET_THRESHOLD_MM if m==7 else
                           actual<v2.LOW_VIS_THRESHOLD_M).astype(float)
                    p2=bucket["v2_event_p"]
                    cell["v2_brier"]=float(np.mean((event-p2)**2))
                    cell["v3_brier"]=float(np.mean((event-prob)**2))
                    cell["observed_events"]=int(event.sum())
                by_metric[f"{core.METRICS[m]}|{core.HORIZONS[hi]}"]=cell
            by_station[station]=by_metric
        output[ablation]=by_station
    return output


def run(seasons,archives,v2_checkpoint,output):
    root=Path(output);root.mkdir(parents=True,exist_ok=True)
    store,geo=read_sources(seasons)
    station_history=read_actual_stations(archives)
    with np.load(v2_checkpoint) as cp:
        training_from_v2=set(cp["training_stations"].tolist())
        weights=cp["weights"]
        special=cp["specialized_weights"]
    train_ids={k for k,(_,_,s) in STATIONS.items() if s=="train"}
    heldout_ids=set(STATIONS)-train_ids
    if len(train_ids)!=4 or len(heldout_ids)!=2:
        raise ValueError("Train/holdout split size incorrect")
    if not train_ids.issubset(training_from_v2) or heldout_ids & training_from_v2:
        raise ValueError("V2 checkpoint contains a heldout station or lacks training station")
    issues=issue_hours()
    examples={
        station:station_examples(station,station_history[station],geo[station],
                                 store,weights,special,issues)
        for station in STATIONS
    }
    training={k:examples[k] for k in train_ids}
    holdouts={k:examples[k] for k in heldout_ids}
    coefficients,counts=fit_ablation(training)
    evaluations=score(holdouts,coefficients,special)
    if not any(v for rows in holdouts.values() for v in rows.values()):
        raise RuntimeError("No matched validation weather readings")
    coefficient_array=np.stack([
        np.stack([np.stack([coefficients[(ablation,m,h)]
                           for h in range(3)]) for m in range(8)])
        for ablation in ABLATIONS
    ])
    np.savez_compressed(root/"atmos-v3-seasonal-calibration-checkpoint.npz",
        coefficients=coefficient_array,
        feature_names=np.array(FEATURES),
        ablations=np.array(list(ABLATIONS)),
        training_stations=np.array(sorted(train_ids)),
        heldout_stations=np.array(sorted(heldout_ids)),
        horizon_hours=np.array(core.HORIZONS),
        variables=np.array(core.METRICS),
        training_case_counts=np.stack([
            np.stack([[counts[(a,m,h)] for h in range(3)]
                      for m in range(8)]) for a in ABLATIONS
        ]),
    )
    report={
        "status":"research_only_not_operationally_certified",
        "training_stations":sorted(train_ids),
        "heldout_stations":sorted(heldout_ids),
        "source_forecast_issue_hours":len(issues),
        "satellite_radar_availability_assumption":"15min not historically verified",
        "v2_time_leakage_caveat":"V2 learned from 2006-2025 training-station data, so early 2018 predictions are retrospective",
        "global_v3_time_leakage_caveat":"Seasonal fit across all seasons uses later calendar months when scoring earlier holdout months",
        "training_counts":{f"{a}|{core.METRICS[m]}|{core.HORIZONS[h]}":
                           n for (a,m,h),n in counts.items()},
        "matched_heldout_scores":evaluations,
    }
    (root/"atmos-v3-matched-validation.json").write_text(
        json.dumps(report,indent=2)+"\n"
    )
    lines=["# Atmos V3: Paired spatial holdout skill (research only)","",
           "The source data are real, but historical sensor availability latency is assumed.",
           "V2 global pretraining includes future calendar years relative to the historical issue hour.",
           "Four seasonal weeks, every six hours; not a full hourly backtest.","",
           "| Station | Variable | Horizon | Matched cases | V2 MAE | V3 combined MAE | Skill |",
           "|---|---|---:|---:|---:|---:|---:|"]
    for station,rows in sorted(evaluations["joint_elevation"].items()):
        for key,cell in sorted(rows.items()):
            name,h=key.split("|")
            change=cell["v3_vs_v2_skill_pct"]
            lines.append(f"| {station} | {name} | {h}h | {cell['cases']} | "+
                         f"{cell['v2_mae']:.4f} | {cell['v3_mae']:.4f} | "+
                         (f"{change:+.2f}%" if change is not None else "N/A")+" |")
    (root/"atmos-v3-matched-validation.md").write_text("\n".join(lines)+"\n")
    print("\n".join(lines))
    return report


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--seasons",required=True)
    p.add_argument("--archives",required=True)
    p.add_argument("--v2-checkpoint",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    run(a.seasons,a.archives,a.v2_checkpoint,a.output)

if __name__=="__main__":
    main()
