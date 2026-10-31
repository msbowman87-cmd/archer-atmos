"""Bounded historical multi-variable research collection by month and grid shard.

Gridded reanalysis is NOT independent station truth. This archive supplies
features/climatology, not verification of Atmos predictions.
"""
import argparse
import calendar
import csv
import hashlib
import json
import time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from atmos.global_grid import shard_points

BASE='https://archive-api.open-meteo.com/v1/archive'
HOURLY=('temperature_2m','relative_humidity_2m','dew_point_2m',
        'pressure_msl','surface_pressure','cloud_cover','precipitation',
        'rain','snowfall','snow_depth','wind_speed_10m','wind_direction_10m',
        'wind_gusts_10m','shortwave_radiation','soil_moisture_0_to_7cm')


def request(point,year,month,*,opener=urlopen):
    if not 1940<=year<=2026 or not 1<=month<=12:
        raise ValueError('Invalid historical month')
    final=calendar.monthrange(year,month)[1]
    args={'latitude':point['lat'],'longitude':point['lon'],
          'start_date':f'{year:04d}-{month:02d}-01',
          'end_date':f'{year:04d}-{month:02d}-{final:02d}',
          'timezone':'UTC','hourly':','.join(HOURLY)}
    url=BASE+'?'+urlencode(args)
    last=None
    for attempt in range(3):
        try:
            with opener(Request(url,headers={'User-Agent':'ArcherAtmosResearch/0.5'}),timeout=65) as response:
                data=response.read(10_000_001)
            break
        except (OSError,TimeoutError) as exc:
            last=exc
            if attempt==2:raise RuntimeError('Historical source unavailable after retries') from last
            time.sleep(2**attempt)
    if len(data)>10_000_000:raise ValueError('Monthly response over byte limit')
    payload=json.loads(data)
    if not isinstance(payload,dict) or payload.get('error') or 'hourly' not in payload:
        raise RuntimeError('Historical source missing hourly data')
    hourly=payload['hourly']
    if not isinstance(hourly.get('time'),list):raise RuntimeError('Missing timestamps')
    for field in HOURLY:
        if field not in hourly or len(hourly[field])!=len(hourly['time']):
            raise RuntimeError('Missing or misaligned historical field: '+field)
    return payload,hashlib.sha256(data).hexdigest()


def run(year,month,shard,*,grid_count=5000,shard_size=5,output='rich-history-results',fetch=request):
    if not 1<=shard_size<=10:raise ValueError('Max 10 locations per research job')
    points=shard_points(shard,count=grid_count,shard_size=shard_size)
    root=Path(output);root.mkdir(parents=True,exist_ok=True)
    label=f'rich_{grid_count}_{year}{month:02d}_shard_{shard:04d}'
    file=root/(label+'.csv')
    if file.exists():raise FileExistsError('Research shard already exists')
    summary={'year':year,'month':month,'grid_count':grid_count,'shard':shard,
             'source':BASE,'source_classification':'model-derived historical reanalysis, NOT station truth',
             'locations_attempted':len(points),'locations_succeeded':0,'rows':0,
             'failures':[],'sources':[], 'missing_values_by_field':{field:0 for field in HOURLY}}
    with file.open('x',newline='') as handle:
        writer=csv.writer(handle)
        writer.writerow(['location_id','latitude','longitude','valid_time_utc',*HOURLY])
        for point in points:
            try:
                data,digest=fetch(point,year,month)
                hourly=data['hourly']
                for i,stamp in enumerate(hourly['time']):
                    values=[hourly[field][i] for field in HOURLY]
                    for field,value in zip(HOURLY,values):
                        if value is None:summary['missing_values_by_field'][field]+=1
                    writer.writerow([point['id'],point['lat'],point['lon'],stamp,*values])
                    summary['rows']+=1
                summary['locations_succeeded']+=1
                summary['sources'].append({'location_id':point['id'],'raw_sha256':digest})
            except Exception as exc:
                summary['failures'].append({'location_id':point['id'],'reason':str(exc)[:200]})
            handle.flush()
            time.sleep(.25)
    summary['retrieved_at_utc']=datetime.now(timezone.utc).isoformat()
    (root/(label+'.json')).write_text(json.dumps(summary,indent=2))
    if summary['locations_succeeded']==0:
        raise RuntimeError('No rich historical data retrieved')
    return summary


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--year',type=int,required=True)
    p.add_argument('--month',type=int,required=True)
    p.add_argument('--shard',type=int,required=True)
    p.add_argument('--grid-count',type=int,default=5000)
    p.add_argument('--shard-size',type=int,default=5)
    p.add_argument('--output',default='rich-history-results')
    a=p.parse_args()
    print(json.dumps(run(a.year,a.month,a.shard,grid_count=a.grid_count,
                         shard_size=a.shard_size,output=a.output),indent=2))


if __name__=='__main__':main()
