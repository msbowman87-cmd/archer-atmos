"""Collect real station observations and archived fixed-initialisation ECMWF forecasts.

US ASOS station example: TWF (Twin Falls, Idaho), coordinates 42.4818,-114.4877.
IEM daily summaries use LOCAL dates; forecast daily timezone must match the station.
Run e.g. python -m atmos.station_backtest --station TWF --network ID_ASOS
 --latitude 42.4818 --longitude -114.4877 --timezone America/Boise
 --start 2026-09-01 --end 2026-09-07
"""
import argparse,csv,io,json,time
from datetime import date,datetime,timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import HTTPError
from atmos.independent_validation import evaluate

def get(url,params):
    try:
        with urlopen(url+'?'+urlencode(params),timeout=45) as response:
            return response.read().decode('utf-8')
    except HTTPError as exc:
        raise RuntimeError('API HTTP '+str(exc.code)+': '+exc.read().decode('utf-8',errors='replace')[:500]) from exc

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
    # Issue-time is the archived run INITIALISATION, not the public availability time.
    # Choose 00 UTC runs with UTC daily aggregation; compare UTC dates only.
    # Station observations must be aligned to UTC daily boundaries before interpreting error.
    issue=start-timedelta(days=9)
    while issue<end:
        run=issue.isoformat()+'T00:00'
        params={'latitude':lat,'longitude':lon,'timezone':'UTC','run':run,
                'models':'ecmwf_ifs','daily':'temperature_2m_max,precipitation_sum',
                'forecast_days':10}
        try:
            obj=json.loads(get('https://single-runs-api.open-meteo.com/v1/forecast',params))
            if 'error' in obj: raise RuntimeError(obj.get('reason',str(obj)))
            daily=obj['daily']
            for ds,t,p in zip(daily['time'],daily['temperature_2m_max'],daily['precipitation_sum']):
                d=date.fromisoformat(ds)
                lead=(d-issue).days
                if start<=d<=end and 1<=lead<=9 and t is not None and p is not None:
                    result.append({'station_id':station,'date':ds,'issue_date':issue.isoformat(),
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
    report['observation_source']='Iowa Environmental Mesonet ASOS daily summary'
    report['limitations']=['CRITICAL: UTC model days vs IEM station-local days are not aligned; metrics are exploratory until observation time boundaries are reconciled.',
      'Run initialisation is not the publication timestamp.',
      'This tests ECMWF baseline, not Atmos improvements.',
      'ECMWF archive does not cover 30-day forecast horizon.']
    (root/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    if not fc or not obs: raise RuntimeError('No forecast/observation pairs to validate')
if __name__=='__main__':main()
