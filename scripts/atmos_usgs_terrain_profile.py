#!/usr/bin/env python3
"""Bounded, provenance-preserving USGS 3DEP terrain point sampling research.

Retrieves independent interpolated terrain heights at station center and
5 km cardinal offsets from the USGS Elevation Point Query Service. The
profiles are NOT used for training or terrain-skill claims in this step.
Unknown elevations remain missing; no synthetic elevation or silent fallback.
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request

SOURCE='https://epqs.nationalmap.gov/v1/json'
RADIUS_KM=5.0
EARTH_KM=6371.0088
# Actual target IDs from completed 2026-11-18 independent multi-region run.
SITES=(
    'USW00094129','USW00004938','USW00014922','USW00004842',
    'USW00000236','USW00004110','USW00014735','USW00024143',
)

def sample_locations(lat,lon,radius_km=RADIUS_KM):
    """Great-circle cardinal offsets. Values are query locations, NOT heights."""
    if not (-90<lat<90 and -180<=lon<=180 and 0<radius_km<=20):
        raise ValueError('Invalid station point or radius')
    d=radius_km/EARTH_KM
    latr=math.radians(lat)
    lonr=math.radians(lon)
    offsets={'center':None,'north':0.,'east':90.,'south':180.,'west':270.}
    result={}
    for name,bearing in offsets.items():
        if bearing is None:
            result[name]=(lat,lon)
            continue
        b=math.radians(bearing)
        lat2=math.asin(math.sin(latr)*math.cos(d)+math.cos(latr)*math.sin(d)*math.cos(b))
        lon2=lonr+math.atan2(math.sin(b)*math.sin(d)*math.cos(latr),
                            math.cos(d)-math.sin(latr)*math.sin(lat2))
        result[name]=(math.degrees(lat2),(math.degrees(lon2)+540)%360-180)
    return result

def endpoint(lat,lon):
    args=urllib.parse.urlencode(dict(x=f'{lon:.7f}',y=f'{lat:.7f}',
                                     units='Meters',wkid=4326,includeDate='false'))
    return SOURCE+'?'+args

def extract_elevation(payload):
    if not isinstance(payload,dict) or 'value' not in payload:
        return None
    raw=payload['value']
    if raw is None or isinstance(raw,bool):
        return None
    try:
        val=float(raw)
    except (TypeError,ValueError):
        return None
    if not math.isfinite(val) or not -600<=val<=9000:
        return None
    units=payload.get('units','Meters')
    if units not in ('Meters','meters','METERS'):
        return None
    return val

def fetch_terrain(lat,lon,timeout=13,attempts=2):
    url=endpoint(lat,lon)
    errors=[]
    for attempt in range(attempts):
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'Archer-Atmos-Research/0.1 (noncommercial verified terrain study)',
                                                     'Accept':'application/json'})
            with urllib.request.urlopen(req,timeout=timeout) as stream:
                raw=stream.read(250_001)
            if len(raw)>250_000:
                raise ValueError('Oversized USGS response')
            json_object=json.loads(raw.decode('utf-8'))
            height=extract_elevation(json_object)
            if height is None:
                raise ValueError('Unusable USGS point elevation response')
            return dict(status='observed_service_response',height_m=height,url=url,
                        raw_response_sha256=hashlib.sha256(raw).hexdigest(),
                        retrieval_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                        response_units='Meters',attempts=attempt+1)
        except (OSError,TimeoutError,ValueError,UnicodeDecodeError,json.JSONDecodeError) as error:
            errors.append(type(error).__name__+': '+str(error)[:160])
            if attempt+1<attempts:
                time.sleep(1+attempt)
    return dict(status='source_unavailable',height_m=None,url=url,
                errors=errors,attempts=attempts)

def terrain_summary(samples,radius_km=RADIUS_KM):
    heights={key:value['height_m'] for key,value in samples.items()
             if value.get('status')=='observed_service_response'}
    report=dict(measured_points=len(heights),expected_points=5,
                complete=len(heights)==5,
                terrain_source='USGS 3DEP EPQS interpolated bare-earth elevation')
    if len(heights)<5:
        report['relief_m']=None
        report['northward_slope_m_per_km']=None
        report['eastward_slope_m_per_km']=None
        report['upslope_bearing_deg']=None
        return report
    south_north=(heights['north']-heights['south'])/(2*radius_km)
    west_east=(heights['east']-heights['west'])/(2*radius_km)
    slope=math.hypot(south_north,west_east)
    report.update(relief_m=round(max(heights.values())-min(heights.values()),2),
                  northward_slope_m_per_km=round(south_north,3),
                  eastward_slope_m_per_km=round(west_east,3),
                  gradient_m_per_km=round(slope,3),
                  upslope_bearing_deg=round(math.degrees(math.atan2(west_east,south_north))%360,1))
    return report

def run(manifest,out,station_ids=SITES):
    all_rows=list(csv.DictReader(pathlib.Path(manifest).open(newline='',encoding='utf-8-sig')))
    indexed={(s['provider'],s['station_id']):s for s in all_rows}
    selections=[]
    for sid in station_ids:
        key=('NOAA_GHCNh',sid)
        if key not in indexed:
            raise ValueError('Missing station from verified manifest: '+sid)
        selections.append(indexed[key])
    output=pathlib.Path(out)
    output.mkdir(parents=True,exist_ok=True)
    records=[]
    for station in selections:
        lat=float(station['latitude'])
        lon=float(station['longitude'])
        query_points=sample_locations(lat,lon)
        samples={name:dict(lat=qlat,lon=qlon,**fetch_terrain(qlat,qlon))
                 for name,(qlat,qlon) in query_points.items()}
        profile=terrain_summary(samples)
        center=samples['center']['height_m']
        elevation=float(station['elevation_m'])
        records.append(dict(station_id=station['station_id'],
                            catalog_elevation_m=elevation,latitude=lat,longitude=lon,
                            catalog_vs_dem_m=round(center-elevation,2) if center is not None else None,
                            profile=profile,samples=samples))
        print(json.dumps(dict(station_id=station['station_id'],
                              measured=profile['measured_points'],complete=profile['complete'])),flush=True)
    summary=dict(status='terrain_provenance_research_not_training',
                 station_count=len(records),
                 full_profiles=sum(x['profile']['complete'] for x in records),
                 sampled_points=sum(x['profile']['measured_points'] for x in records),
                 expected_points=len(records)*5,radius_km=RADIUS_KM,
                 terrain_model_trained=False,training_quality_approved=False,
                 source='https://apps.nationalmap.gov/epqs/',
                 source_description='USGS EPQS elevations are interpolated from 3DEP; not official surveyed heights.',
                 methodology='center + 5 km cardinal offsets; 10 km finite differences and 5-point relief',
                 limitations=[
                    'Single points do not establish wind sheltering, canyon shape or ridgeline subgrid terrain.',
                    'Interpolation source resolution may vary with location; survey accuracy is not guaranteed.',
                    'DEM height and station reference elevation may use different vertical references.',
                    'Retrieval times are 2026; terrain model is static, not an archival weather observation.',
                    'No terrain features have entered forecast fitting or evaluation in this step.',
                    'Unavailable service responses are left missing; original station elevations are never modified.',
                 ])
    (output/'verified_usgs_terrain_points.json').write_text(json.dumps(
        dict(summary=summary,stations=records),indent=2)+'\n')
    print(json.dumps(summary,indent=2))
    return summary

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--manifest',required=True)
    parser.add_argument('--out',required=True)
    args=parser.parse_args()
    run(args.manifest,args.out)

if __name__=='__main__':
    main()
