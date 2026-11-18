#!/usr/bin/env python3
"""Experimental atmospheric tendency/advection regional benchmark.

Only original verified NOAA GHCNh archived observations (not simulations).
Fit 2022-2023 on training tiles. 2024 and 2025 outcomes remain outside fitting,
and selected spatial-holdout tiles are excluded from all fitted target rows.
Observation release timestamps are unavailable: as-of uses an *assumed* 72h
delay and is NOT certified to reflect historically available forecast inputs.
"""
import argparse
import collections
import csv
import datetime as dt
import io
import json
import math
import pathlib
import random
import statistics
import tempfile

from atmos_quality_policy import normalize
from atmos_regional_actual_pilot import (
    ZipSourceLoader, qualified_noaa, ridge_fit, latest,
)
from atmos_regional_neighbors import distance_bearing
from atmos_multi_region_wind_pilot import select_regions, wind_weight

UTC = dt.timezone.utc
YEARS = (2022, 2023, 2024, 2025)
HORIZON_H = 24
ASSUMED_LAG_H = 72
FIELDS = ('temperature', 'wind_speed', 'wind_direction',
          'sea_level_pressure', 'station_level_pressure')

def decode_source(data):
    """Read source-specific row QC for each field, last valid value per UTC hour."""
    r = csv.DictReader(io.StringIO(data.decode('utf-8-sig')), delimiter='|')
    required = {'DATE','temperature','temperature_Quality_Code','temperature_Source_Code'}
    if not required.issubset(r.fieldnames or []):
        raise ValueError('Missing required GHCNh fields')
    records = collections.defaultdict(dict)
    reasons = collections.Counter()
    for row in r:
        timestamp = dt.datetime.fromisoformat(row['DATE'].replace('Z','+00:00'))
        if timestamp.tzinfo is None:
            timestamp=timestamp.replace(tzinfo=UTC)
        timestamp=timestamp.astimezone(UTC)
        hour=timestamp.replace(minute=0,second=0,microsecond=0)
        for field in FIELDS:
            value, name, why = normalize(
                'NOAA_GHCNh',field,row.get(field),
                row.get(field+'_Quality_Code'),row.get(field+'_Source_Code'))
            reasons[field+':'+why]+=1
            if value is None:
                continue
            previous=records[name].get(hour)
            if previous is None or timestamp >= previous[0]:
                records[name][hour]=(timestamp,value)
    return {name:{hour:pair[1] for hour,pair in values.items()}
            for name,values in records.items()}, dict(reasons)

def cap(value,scale,limit=4):
    return max(-limit,min(limit,value/scale)) if value is not None else 0.

class History:
    def __init__(self, values):
        self.values=values
        self.keys=sorted(values)
    def at(self,time,age=9):
        if not self.keys:
            return None
        return latest(self.values,self.keys,time,max_age_hours=age)
    def trend(self,time,hours,scale=None):
        recent=self.at(time)
        older=self.at(time-dt.timedelta(hours=hours))
        return recent-older if recent is not None and older is not None else None

def pressure_history(raw):
    # No pressure surfaces are pooled as absolute hPa. Only *changes*
    # computed within the same station and same pressure type are used.
    name=('sea_level_pressure_hpa' if raw.get('sea_level_pressure_hpa')
          else 'station_pressure_hpa')
    return History(raw.get(name,{})),name

def features_for_station(target_id,neighbor_ids,metadata,measurements,years=YEARS):
    raw=measurements[target_id]
    own=History(raw.get('temperature_c',{}))
    if not own.keys:
        return
    pressure,pressure_type=pressure_history(raw)
    speed=History(raw.get('wind_speed_mps',{}))
    direction=History(raw.get('wind_direction_deg',{}))
    neighbors=[]
    for sid in neighbor_ids:
        if sid not in measurements:
            continue
        neighbor=measurements[sid]
        tmp=History(neighbor.get('temperature_c',{}))
        if not tmp.keys:
            continue
        d,bearing=distance_bearing(metadata[target_id],metadata[sid])
        if d<=0 or d>300:
            continue
        alt=float(metadata[sid]['elevation_m'])-float(metadata[target_id]['elevation_m'])
        press,press_type=pressure_history(neighbor)
        neighbors.append((sid,tmp,press,d,bearing,alt))
    for valid in own.keys:
        if valid.year not in years:
            continue
        # Every input timestamp must precede verification - 24h - 72h.
        asof=valid-dt.timedelta(hours=HORIZON_H+ASSUMED_LAG_H)
        target=own.at(asof)
        if target is None:
            continue
        t6=own.trend(asof,6)
        t24=own.trend(asof,24)
        p6=pressure.trend(asof,6)
        p24=pressure.trend(asof,24)
        ws=speed.at(asof)
        wd=direction.at(asof)
        active_wind=bool(ws is not None and wd is not None and ws>=2.0)
        angle_h=(valid.hour-HORIZON_H)*2*math.pi/24
        # Day-of-year at the forecast issue, not target verification.
        issued=valid-dt.timedelta(hours=HORIZON_H)
        angle_y=(issued.timetuple().tm_yday-1)*2*math.pi/365.25
        baseline=[1.,target/30,math.sin(angle_h),math.cos(angle_h),
                  math.sin(angle_y),math.cos(angle_y),
                  float(metadata[target_id]['latitude'])/60,
                  float(metadata[target_id]['elevation_m'])/2000]
        history=baseline + [
            cap(t6,15),cap(t24,15),float(t6 is not None),float(t24 is not None),
            cap(p6,10),cap(p24,10),float(p6 is not None),float(p24 is not None),
        ]
        geographically=[]
        physically_upwind=[]
        region_p=[]
        for sid,temps,press,d,bearing,dz in neighbors:
            current=temps.at(asof)
            if current is None:
                continue
            # Fixed lapse is a *scenario*, not an independently derived terrain
            # lapse rate. No DEM/land-cover features are claimed.
            scaled_temp=current+0.0065*dz
            w=1/(20+d)
            geographically.append((scaled_temp,w,temps.trend(asof,6)))
            tendency=press.trend(asof,6)
            if tendency is not None:
                region_p.append((tendency,w))
            if active_wind:
                alignment=wind_weight(bearing,wd,ws)
                if alignment<=0:
                    continue
                # Delay for an idealized steady wind from neighbor to target.
                # Use the *earlier* source temperature: no forward-time parcel
                # advection, no extrapolating unobserved weather.
                travel=d/(3.6*ws)
                if not 1<=travel<=36:
                    continue
                older_at=asof-dt.timedelta(hours=travel)
                advected=temps.at(older_at)
                if advected is None:
                    continue
                earlier_trend=temps.trend(older_at,6)
                physically_upwind.append((advected+0.0065*dz,w*alignment,earlier_trend))
        if not geographically:
            continue
        def weighted(items):
            return sum(v*w for v,w in items)/sum(w for _,w in items)
        regional_temp=weighted([(v,w) for v,w,_ in geographically])
        regional_tendency_items=[(t,w) for _,w,t in geographically if t is not None]
        regional_tendency=weighted(regional_tendency_items) if regional_tendency_items else None
        regional_pressure=weighted(region_p) if region_p else None
        geographic=history+[
            cap(regional_temp-target,15),
            cap(regional_tendency,15),
            cap(regional_pressure,10),
            float(regional_tendency is not None),
            float(regional_pressure is not None),
        ]
        wind_signal=bool(physically_upwind)
        advected_temp=weighted([(v,w) for v,w,_ in physically_upwind]) if wind_signal else None
        advected_trends=[(tr,w) for _,w,tr in physically_upwind if tr is not None]
        advected_trend=weighted(advected_trends) if advected_trends else None
        # Conventional u/v wind components ("toward" east and north) are
        # signed oppositely to the meteorological *FROM* bearing.
        east=-ws*math.sin(math.radians(wd)) if active_wind else None
        north=-ws*math.cos(math.radians(wd)) if active_wind else None
        transport=geographic+[
            cap(advected_temp-target,15) if wind_signal else 0.,
            cap(advected_trend,15),cap(east,20),cap(north,20),
            float(wind_signal),float(advected_trend is not None),
        ]
        yield dict(target=target_id,valid_at=valid,year=valid.year,actual=own.values[valid],
                   persistence=target,station_only=baseline,
                   station_tendency=history,geographic=geographic,
                   transport=transport,upwind_active=wind_signal,
                   pressure_tendency_available=p6 is not None,
                   neighbor_pressure_available=regional_pressure is not None,
                   pressure_type=pressure_type)

MODEL_NAMES=('station_only','station_tendency','geographic','transport')

def score(rows,models):
    if not rows:
        return dict(cases=0)
    totals=collections.Counter()
    for row in rows:
        totals['cases']+=1
        totals['wind_cases']+=int(row['upwind_active'])
        totals['pressure_trend_cases']+=int(row['pressure_tendency_available'])
        totals['neighbor_pressure_cases']+=int(row['neighbor_pressure_available'])
        totals['persistence_abs_error']+=abs(row['actual']-row['persistence'])
        for model,weights in models.items():
            pred=sum(a*b for a,b in zip(row[model],weights))
            totals[model+'_abs_error']+=abs(row['actual']-pred)
    n=totals['cases']
    out=dict(cases=n,wind_cases=totals['wind_cases'],
             pressure_trend_cases=totals['pressure_trend_cases'],
             neighbor_pressure_cases=totals['neighbor_pressure_cases'],
             persistence_mae_c=round(totals['persistence_abs_error']/n,4))
    for name in MODEL_NAMES:
        out[name+'_mae_c']=round(totals[name+'_abs_error']/n,4)
    out['transport_skill_over_station_pct']=round(
        100*(totals['station_only_abs_error']-totals['transport_abs_error'])/
        totals['station_only_abs_error'],3) if totals['station_only_abs_error'] else None
    return out

def paired_interval(rows,models,seed=26,replicates=300):
    blocks=collections.defaultdict(lambda:[0.,0])
    for row in rows:
        local=sum(a*b for a,b in zip(row['station_only'],models['station_only']))
        transport=sum(a*b for a,b in zip(row['transport'],models['transport']))
        key=(row['target'],row['valid_at'].date())
        blocks[key][0]+=abs(row['actual']-local)-abs(row['actual']-transport)
        blocks[key][1]+=1
    if not blocks:
        return dict(cases=0)
    items=list(blocks.values())
    rng=random.Random(seed)
    boot=[]
    for _ in range(replicates):
        sample=(items[rng.randrange(len(items))] for _ in items)
        tot_n=0;total=0
        for s,n in sample:total+=s;tot_n+=n
        boot.append(total/tot_n)
    boot.sort()
    return dict(station_day_blocks=len(items),
                delta_mae_c_positive_is_improvement=round(sum(s for s,n in items)/
                                                          sum(n for s,n in items),5),
                interval_95_c=[round(boot[int(replicates*.025)],5),
                               round(boot[min(replicates-1,int(replicates*.975))],5)],
                conditional_on_fixed_test_regions=True)

def run(checkpoint,graph_path,out,training_regions=5,holdout_regions=3):
    root=pathlib.Path(checkpoint)
    output=pathlib.Path(out)
    output.mkdir(parents=True,exist_ok=True)
    rows=list(csv.DictReader((root/'stations.csv').open(newline='')))
    eligible=qualified_noaa(root,rows)
    regions=select_regions(graph_path,eligible,training_regions,holdout_regions,
                           separation_km=350)
    chosen=[x['node']['target_station_id'] for x in regions]
    ids=sorted(set(chosen)|{n['station_id'] for x in regions for n in x['neighbors']})
    if len(ids)>36:
        raise ValueError('Too many distinct NOAA source stations for bounded benchmark')
    metadata={r['station_id']:r for r in rows if r['provider']=='NOAA_GHCNh'}
    data=collections.defaultdict(lambda:collections.defaultdict(dict))
    per_source_qc={}
    with tempfile.TemporaryDirectory(prefix='atmos-transport-') as tmp:
        loader=ZipSourceLoader(root,tmp,budget_bytes=3_500_000_000)
        for station in ids:
            for year in YEARS:
                raw=loader.read(station,year)
                values,qc=decode_source(raw)
                for name,observations in values.items():
                    data[station][name].update(observations)
                per_source_qc[station+':'+str(year)]=dict(
                    accepted_distinct_hours={n:len(v) for n,v in values.items()},
                    rejection_reasons=qc)
        provenance=loader.sources
    (output/'source_provenance_and_qc.json').write_text(json.dumps(
        dict(source_files=provenance,per_source_qc=per_source_qc,
             quality_approved=False),indent=2)+'\n')
    print(json.dumps(dict(source_files=len(provenance),stations=len(ids),
                          pressure_hours=sum(len(v.get('sea_level_pressure_hpa',{}))
                                          +len(v.get('station_pressure_hpa',{}))
                                          for v in data.values()),
                          wind_hours=sum(len(v.get('wind_speed_mps',{})) for v in data.values())) ,flush=True)
    training=[]
    holdouts=collections.defaultdict(list)
    train_year_2024=[]
    region_info=[]
    for region in regions:
        node=region['node']
        target=node['target_station_id']
        feats=list(features_for_station(target,[n['station_id'] for n in region['neighbors']],
                                         metadata,data))
        is_train=node['role']=='training_target'
        if is_train:
            training.extend(x for x in feats if x['year'] in (2022,2023))
            train_year_2024.extend(x for x in feats if x['year']==2024)
        else:
            for year in (2024,2025):
                holdouts[year].extend(x for x in feats if x['year']==year)
        region_info.append(dict(target=target,role=node['role'],
                                latitude=node['latitude'],longitude=node['longitude'],
                                tile=node['spatial_tile'],
                                cases_by_year={str(y):sum(x['year']==y for x in feats) for y in YEARS},
                                pressure_trend_cases=sum(x['pressure_tendency_available'] for x in feats),
                                wind_signal_cases=sum(x['upwind_active'] for x in feats)))
    if len(training)<5000 or len(holdouts[2024])<500 or len(holdouts[2025])<500:
        raise ValueError('Insufficient independent fit/holdout cases: '+str(
            (len(training),len(holdouts[2024]),len(holdouts[2025]))))
    # Fixed lambda from design stage. Do not use 2025 for tuning.
    models={name:ridge_fit(training,name,lam=2.0) for name in MODEL_NAMES}
    report=dict(status='experimental_temporal_transport_spatial_benchmark',
                fit_period='2022-2023',validation_year=2024,evaluation_year=2025,
                source_file_count=len(provenance),source_station_count=len(ids),
                training_regions=training_regions,heldout_regions=holdout_regions,
                training_cases=len(training),regions=region_info,
                training_region_2024=score(train_year_2024,models),
                heldout_2024=score(holdouts[2024],models),
                heldout_2025=score(holdouts[2025],models),
                heldout_2025_per_station={
                    sid:score([r for r in holdouts[2025] if r['target']==sid],models)
                    for sid in sorted({r['target'] for r in holdouts[2025]})},
                heldout_paired_daily_interval_2025=paired_interval(holdouts[2025],models),
                fitted_weights=models,
                forecast_horizon_hours=HORIZON_H,assumed_availability_lag_hours=ASSUMED_LAG_H,
                availability_lag_verified=False,quality_approved=False,
                model_deployed=False,radar_satellite_used=False,
                terrain_raster_used=False,
                limitations=[
                    'Station elevation is used as a simplified proxy; no terrain DEM, slope, or sheltering data.',
                    'Pressure tendency is taken within station and pressure type; missing QC is not manufactured.',
                    'Parcel time is an idealized constant wind-speed assumption; not an atmospheric trajectory.',
                    'Historical observation release time is unknown; 72h availability lag is explicitly assumed.',
                    'Selected stations require 2022-25 source availability, creating sample-selection bias.',
                    'The five/three region subset is not a continental certification or full Atmos training.',
                    'Future-year measurements are reserved for evaluation; no 2025 outcomes enter fitting.',
                ])
    (output/'temporal_transport_benchmark.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='fitted_weights'},indent=2),flush=True)
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--checkpoint',required=True)
    p.add_argument('--neighbor-graph',required=True)
    p.add_argument('--out',required=True)
    p.add_argument('--training-regions',type=int,default=5)
    p.add_argument('--holdout-regions',type=int,default=3)
    a=p.parse_args()
    run(a.checkpoint,a.neighbor_graph,a.out,a.training_regions,a.holdout_regions)

if __name__=='__main__':
    main()
