"""On-demand regional weather input retrieval for arbitrary worldwide coordinates.

Research prototype only. Responses contain provider model output, not an Atmos
calibrated forecast. Cache and report retrieval time, never fabricate issue time.
"""
import argparse
import hashlib
import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = 'https://api.open-meteo.com/v1/forecast'
HOURLY = ('temperature_2m','relative_humidity_2m','dew_point_2m',
          'pressure_msl','surface_pressure','cloud_cover','precipitation',
          'rain','snowfall','wind_speed_10m','wind_direction_10m',
          'wind_gusts_10m','shortwave_radiation','visibility','cape',
          'temperature_850hPa','relative_humidity_700hPa',
          'wind_speed_500hPa','geopotential_height_500hPa')
DAILY = ('temperature_2m_max','temperature_2m_min','precipitation_sum',
         'snowfall_sum','wind_speed_10m_max','wind_gusts_10m_max')


def validate_coordinates(latitude, longitude):
    lat, lon = float(latitude), float(longitude)
    if not all(map(math.isfinite,(lat,lon))) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError('Invalid worldwide coordinates')
    return lat, lon


def regional_points(latitude, longitude, radius_km=200):
    """Center + cardinal directions. Cap longitude displacement near poles."""
    lat, lon = validate_coordinates(latitude, longitude)
    if not 25 <= radius_km <= 1000:
        raise ValueError('Regional radius must be 25-1000 km')
    delta_lat = radius_km / 111.2
    delta_lon = radius_km / (111.2 * max(.1, math.cos(math.radians(lat))))
    candidate = [(lat,lon),(min(90,lat+delta_lat),lon),
                 (max(-90,lat-delta_lat),lon),
                 (lat,((lon+delta_lon+180)%360)-180),
                 (lat,((lon-delta_lon+180)%360)-180)]
    result=[];seen=set()
    for la,lo in candidate:
        key=(round(la,5),round(lo,5))
        if key not in seen:
            result.append({'latitude':key[0],'longitude':key[1]})
            seen.add(key)
    return result


def params(latitude,longitude,forecast_days=10):
    if not 1 <= forecast_days <= 16:
        raise ValueError('Forecast days must be 1-16')
    lat,lon=validate_coordinates(latitude,longitude)
    return {'latitude':lat,'longitude':lon,'timezone':'UTC',
            'forecast_days':forecast_days,'hourly':','.join(HOURLY),
            'daily':','.join(DAILY)}


def fetch_one(parameters, *, opener=urlopen):
    url=BASE+'?'+urlencode(parameters)
    with opener(Request(url,headers={'User-Agent':'ArcherAtmosResearch/0.5'}),timeout=45) as response:
        raw=response.read(8_000_001)
    if len(raw)>8_000_000:
        raise ValueError('Provider response exceeds size budget')
    data=json.loads(raw)
    if not isinstance(data,dict) or data.get('error') or 'hourly' not in data:
        raise RuntimeError('Provider returned an invalid weather response')
    return data


def retrieve(latitude, longitude, *, cache_dir='.atmos-cache', ttl_seconds=3600,
             radius_km=200, forecast_days=10, fetcher=fetch_one, now=None):
    """Reuse fresh inputs; request at most five spatial samples when stale.

    This is data gathering, not forecast correction. No observation after the
    forecast time is used to make the prediction.
    """
    if not 60 <= ttl_seconds <= 86400:
        raise ValueError('Cache lifetime must be 1 minute to 24 hours')
    points=regional_points(latitude,longitude,radius_km)
    request_params=[params(p['latitude'],p['longitude'],forecast_days) for p in points]
    identity=json.dumps(request_params,sort_keys=True,separators=(',',':'))
    cache=Path(cache_dir)
    cache.mkdir(parents=True,exist_ok=True)
    target=cache/(hashlib.sha256(identity.encode()).hexdigest()+'.json')
    stamp=time.time() if now is None else now
    if target.exists():
        try:
            cached=json.loads(target.read_text())
            age=stamp-cached['cached_at_unix']
            if 0 <= age < ttl_seconds:
                return dict(cached['result'],cache_status='hit',cache_age_seconds=round(age))
        except (ValueError,KeyError,OSError,TypeError):
            pass
    samples=[]
    for point,request in zip(points,request_params):
        data=fetcher(request)
        samples.append({'point':point,'data':data})
    result={'status':'raw_model_inputs_not_calibrated',
            'requested_location':points[0],
            'region_radius_km':radius_km,
            'retrieved_at_utc':datetime.fromtimestamp(stamp,timezone.utc).isoformat(),
            'model_issue_time_utc':None,
            'source':'Open-Meteo Forecast API (research use; verify commercial rights)',
            'samples':samples}
    staged=target.with_suffix('.tmp')
    staged.write_text(json.dumps({'cached_at_unix':stamp,'result':result}))
    os.replace(staged,target)
    return dict(result,cache_status='miss',cache_age_seconds=0)


def main():
    cli=argparse.ArgumentParser()
    cli.add_argument('--latitude',type=float,required=True)
    cli.add_argument('--longitude',type=float,required=True)
    cli.add_argument('--radius-km',type=float,default=200)
    cli.add_argument('--forecast-days',type=int,default=10)
    cli.add_argument('--cache-dir',default='.atmos-cache')
    cli.add_argument('--output')
    args=cli.parse_args()
    result=retrieve(args.latitude,args.longitude,radius_km=args.radius_km,
                    forecast_days=args.forecast_days,cache_dir=args.cache_dir)
    payload=json.dumps(result,indent=2)
    if args.output:
        Path(args.output).write_text(payload)
    else:
        print(payload)


if __name__=='__main__':
    main()
