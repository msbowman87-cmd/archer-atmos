"""Collect real station observations and archived fixed-initialisation ECMWF forecasts.

US ASOS station example: TWF (Twin Falls, Idaho), coordinates 42.4818,-114.4877.
IEM daily summaries use LOCAL dates; forecast daily timezone must match the station.
Run e.g. python -m atmos.station_backtest --station TWF --network ID_ASOS
 --latitude 42.4818 --longitude -114.4877 --timezone America/Boise
 --start 2026-09-01 --end 2026-09-07
"""
import argparse,csv,io,json,time,random
from collections import defaultdict
from zoneinfo import ZoneInfo
from urllib.error import URLError
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import HTTPError
from atmos.independent_validation import evaluate

def get(url,params):
    last=None
    for attempt in range(4):
        try:
            with urlopen(url+'?'+urlencode(params),timeout=35) as response:
                return response.read().decode('utf-8')
        except HTTPError as exc:
            detail=exc.read().decode('utf-8',errors='replace')[:500]
            if exc.code not in (429,500,502,503,504):
                raise RuntimeError('API HTTP '+str(exc.code)+': '+detail) from exc
            last=RuntimeError('API HTTP '+str(exc.code)+': '+detail)
        except (URLError,TimeoutError) as exc:
            last=exc
        if attempt<3: time.sleep(min(2**attempt,8)+random.random()*.25)
    raise RuntimeError('API unavailable after four attempts: '+str(last))

def aggregate_local_days(hourly, tz):
    """UTC hourly forecasts -> complete station-local calendar days, including DST."""
    zone=ZoneInfo(tz)
    grouped=defaultdict(list)
    for stamp,t,p in zip(hourly['time'],hourly['temperature_2m'],hourly['precipitation']):
        utc=datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc)
        grouped[utc.astimezone(zone).date()].append((utc,t,p))
    result={}
    for day,values in grouped.items():
        local_start=datetime(day.year,day.month,day.day,tzinfo=zone)
        local_end=datetime.combine(day+timedelta(days=1),datetime.min.time(),tzinfo=zone)
        expected=int((local_end.astimezone(timezone.utc)-local_start.astimezone(timezone.utc)).total_seconds()/3600)
        timestamps={v[0] for v in values}
        if len(values)!=expected or len(timestamps)!=expected or any(t is None or p is None for _,t,p in values):
            continue
        result[day]=(max(t for _,t,_ in values),sum(p for _,_,p in values))
    return result

def observations(station,network,start,end):
    params={'network':network,'stations':station,'year1':start.year,'month1':start.month,
            'day1':start.day,'year2':end.year,'month2':end.month,'day2':end.day,
            'na':'blank','format':'csv'}
    rows=list(csv.DictReader(io.StringIO(get('https://mesonet.agron.iastate.edu/cgi-bin/request/daily.py',params))))
    if not rows: raise RuntimeError('No IEM station observations returned')
    result=[]
    for r in rows:
        if r.get('station')!=station: continue
        ds=(r.get('day') or r.get('date') or '')[:10]
        if not ds: continue
        t=r.get('max_temp_f','')
        p=r.get('precip_in','')
        if not t and not p: continue
        result.append({'station_id':station,'date':ds,
                       'observed_temp_max_c':str((float(t)-32)*5/9) if t else '',
                       'observed_precip_mm':str(float(p)*25.4) if p else ''})
    return result

def forecasts(station,lat,lon,tz,start,end):
    result=[]
    issue=start-timedelta(days=9)
    while issue<end:
        run=issue.isoformat()+'T00:00'
        params={'latitude':lat,'longitude':lon,'timezone':'UTC','run':run,
                'models':'ecmwf_ifs','hourly':'temperature_2m,precipitation',
                'forecast_days':10}
        try:
            obj=json.loads(get('https://single-runs-api.open-meteo.com/v1/forecast',params))
            if 'error' in obj: raise RuntimeError(obj.get('reason',str(obj)))
            for d,(t,p) in aggregate_local_days(obj['hourly'],tz).items():
                lead=(d-issue).days
                if start<=d<=end and 1<=lead<=9:
                    result.append({'station_id':station,'date':d.isoformat(),'issue_date':issue.isoformat(),
                                   'forecast_temp_max_c':str(t),'forecast_precip_mm':str(p)})
        except Exception as exc:
            print('SKIPPED',run,str(exc)[:500],flush=True)
        issue+=timedelta(days=1)
        time.sleep(.25)
    return result

def save(path,rows,fields):
    with open(path,'w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields)
        w.writeheader();w.writerows(rows)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--station',default='TWF')
    p.add_argument('--network',default='ID_ASOS')
    p.add_argument('--latitude',type=float,default=42.4818)
    p.add_argument('--longitude',type=float,default=-114.4877)
    p.add_argument('--timezone',default='America/Boise')
    p.add_argument('--start',default='2026-09-01')
    p.add_argument('--end',default='2026-09-07')
    p.add_argument('--output',default='station-validation-results')
    a=p.parse_args()
    start=date.fromisoformat(a.start);end=date.fromisoformat(a.end)
    if start>end: p.error('start must precede end')
    root=Path(a.output);root.mkdir(parents=True,exist_ok=True)
    obs=observations(a.station,a.network,start,end)
    fc=forecasts(a.station,a.latitude,a.longitude,a.timezone,start,end)
    save(root/'observations.csv',obs,['station_id','date','observed_temp_max_c','observed_precip_mm'])
    save(root/'forecasts.csv',fc,['station_id','date','issue_date','forecast_temp_max_c','forecast_precip_mm'])
    report=evaluate(fc,obs)
    report['station']=a.station
    report['forecast_model']='ECMWF IFS archived 00 UTC initialisation'
    report['observation_source']='Iowa Environmental Mesonet ASOS daily summary (local station day)'
    report['limitations']=['Forecast UTC hours aggregated to complete station-local days; IEM daily station reporting conventions still require independent verification.',
      'Run initialisation is not the publication timestamp.',
      'This tests ECMWF baseline, not Atmos improvements.',
      'ECMWF archive does not cover 30-day forecast horizon.']
    (root/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    if not fc or not obs: raise RuntimeError('No forecast/observation pairs to validate')
if __name__=='__main__':main()
