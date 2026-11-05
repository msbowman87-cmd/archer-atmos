#!/usr/bin/env python3
"""Resumable station/year (NOAA) or station/month (ECCC/IEM) raw collection.
No interpolation, unit conversion, quality filtering, or timestamp rewriting.
Successful files are resumed only after source-URL and SHA256 checks.
"""
import argparse,calendar,collections,concurrent.futures,csv,datetime,hashlib,http.client,io,itertools,json,pathlib,re,time,urllib.error,urllib.parse,urllib.request
from acquire_station_inventories import NOAA,IEM

def tasks(stations,start,end):
    for s in stations:
        for year in range(start,end+1):
            if year<int(s['history_start'][:4]) or year>int(s['history_end'][:4]):continue
            provider=s['provider'];sid=s['station_id']
            if provider=='NOAA_GHCNh':
                yield s,f'{year}',NOAA+f'access/by-year/{year}/psv/GHCNh_{sid}_{year}.psv','psv'
            elif provider in {'ECCC','IEM_ASOS'}:
                for month in range(1,13):
                    first=datetime.date(year,month,1);last=datetime.date(year,month,calendar.monthrange(year,month)[1])
                    if last.isoformat()<s['history_start'][:10] or first.isoformat()>s['history_end'][:10]:continue
                    if provider=='ECCC':
                        interval=f'{year}-{month:02d}-01T00:00:00Z/{year}-{month:02d}-{last.day:02d}T23:59:59Z'
                        url='https://api.weather.gc.ca/collections/climate-hourly/items?'+urllib.parse.urlencode(dict(f='json',limit=10000,STN_ID=sid,LOCAL_YEAR=year,LOCAL_MONTH=month))
                    else:
                        nxt=datetime.date(year+(month==12),month%12+1,1)
                        params=dict(station=sid,data='all',year1=year,month1=month,day1=1,year2=nxt.year,month2=nxt.month,day2=1,tz='Etc/UTC',format='onlycomma',latlon='yes',elev='yes',missing='M',trace='T',direct='no')
                        url=IEM+'cgi-bin/request/asos.py?'+urllib.parse.urlencode(params)+'&report_type=1&report_type=2'
                    yield s,f'{year}-{month:02d}',url,'geojson' if provider=='ECCC' else 'csv'

def audit_bytes(data,s,period):
    text=data.decode('utf-8-sig');year=period[:4]
    if '<html' in text[:2000].lower() or '<!doctype' in text[:2000].lower():raise ValueError('HTML instead of observations')
    if s['provider']=='ECCC' and text.lstrip().startswith('{'):
        j=json.loads(text);features=j.get('features',[])
        if not features:raise ValueError('no ECCC observations returned')
        if any(l.get('rel')=='next' for l in j.get('links',[])) or j.get('numberMatched',len(features))!=len(features):raise ValueError('truncated ECCC page; lower batch size')
        values=collections.Counter();flags=collections.Counter();hours=set();stamps=[]
        for f in features:
            r=f['properties'];stamp=r.get('UTC_DATE','')
            if str(r.get('STN_ID'))!=s['station_id'] or not r.get('LOCAL_DATE','').startswith(period):raise ValueError('ECCC station/local-month mismatch')
            measured=False
            for k in ['TEMP','DEW_POINT_TEMP','HUMIDEX','PRECIP_AMOUNT','RELATIVE_HUMIDITY','STATION_PRESSURE','VISIBILITY','WEATHER_ENG_DESC','WINDCHILL','WIND_DIRECTION','WIND_SPEED']:
                if r.get(k) is not None:values[k]+=1;measured=True
            for k,v in r.items():
                if (k.endswith('_FLAG') or k=='FLAG') and v is not None:flags[k+':'+str(v)]+=1
            if measured:hours.add(stamp[:13])
            stamps.append(stamp)
        if not values:raise ValueError('no measured ECCC values')
        return dict(records=len(features),unique_hours_with_any_value=len(hours),first_timestamp=min(stamps),last_timestamp=max(stamps),nonmissing_by_field=dict(values),source_quality_flag_counts=dict(flags),source_columns=list(features[0]['properties']),notes='Raw GeoMet JSON retains UTC_DATE, LOCAL_DATE, nulls and flags; monthly batches use LOCAL_YEAR/LOCAL_MONTH. UTC timestamps can cross month boundaries; no transformations.')
    delimiter='|' if s['provider']=='NOAA_GHCNh' else ','
    lines=text.splitlines()
    if s['provider']=='ECCC':
        i=next((i for i,l in enumerate(lines) if 'Date/Time (LST)' in l and 'Temp' in l),None)
        if i is None:raise ValueError('missing ECCC hourly data header')
        lines=lines[i:]
    rows=csv.DictReader(lines,delimiter=delimiter);headers=rows.fieldnames or []
    count=0;value_counts=collections.Counter();flags=collections.Counter();unique_hours=set();first=None;last=None
    for r in rows:
        if s['provider']=='NOAA_GHCNh':
            if r.get('STATION')!=s['station_id'] or r.get('Year')!=year:raise ValueError('station/year mismatch')
            stamp=r.get('DATE','')
            if not stamp.startswith(year):raise ValueError('timestamp mismatch')
            vals={k:v for k,v in r.items() if k not in {'STATION','Station_name','DATE','Year','Month','Day','Hour','Minute','LATITUDE','LONGITUDE','ELEVATION'} and not any(t in k for t in ['_Code','_Type','_ID'])}
            for k,v in r.items():
                if k and 'Quality_Code' in k and v:flags[k+':'+v]+=1
        elif s['provider']=='ECCC':
            stamp=r.get('Date/Time (LST)','')
            if not stamp.startswith(period):raise ValueError('ECCC month mismatch')
            vals={k:v for k,v in r.items() if k not in {'Longitude (x)','Latitude (y)','Station Name','Climate ID','Date/Time (LST)','Year','Month','Day','Time (LST)'} and not k.endswith('Flag')}
            for k,v in r.items():
                if k and k.endswith('Flag') and v:flags[k+':'+v]+=1
        else:
            if r.get('station')!=s['station_id']:raise ValueError('IEM station mismatch')
            stamp=r.get('valid','')
            if not stamp.startswith(period):raise ValueError('IEM month mismatch')
            vals={k:v for k,v in r.items() if k not in {'station','valid','lon','lat','elevation'}}
        measured=False
        for k,v in vals.items():
            if v is not None and v.strip() not in {'','M','-9999','-9999.0','-9999.9','-999.9'}:value_counts[k]+=1;measured=True
        if measured:unique_hours.add(stamp[:13])
        first=min(first,stamp) if first else stamp;last=max(last,stamp) if last else stamp;count+=1
    if not count or not value_counts:raise ValueError('no measured observation rows')
    return dict(records=count,unique_hours_with_any_value=len(unique_hours),first_timestamp=first,last_timestamp=last,nonmissing_by_field=dict(value_counts),source_quality_flag_counts=dict(flags),source_columns=headers,notes='Counts retain source cadence and flags. Unique hours are bins with any field, not per-variable completeness. Flags are not interpreted as pass/fail.')

def retryable_error(error):
    return any(x in str(error) for x in ('HTTP Error 429','HTTP Error 500','HTTP Error 502','HTTP Error 503','HTTP Error 504','IncompleteRead','timed out','Connection reset','Remote end closed'))

def fetch_raw(url,provider):
    # IEM requests are deliberately serialized by the workflow and paced here.
    for attempt in range(3):
        if provider=='IEM_ASOS':time.sleep(3)
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Atmos-research-raw-collector/1.0'}),timeout=90) as response:
                return response.read(),response.status,response.url,attempt+1
        except (urllib.error.URLError,http.client.IncompleteRead,TimeoutError,ConnectionError) as error:
            if attempt==2 or not retryable_error(error):raise
            retry_after=getattr(error,'headers',{}).get('Retry-After','')
            try:delay=min(120,max(0,float(retry_after)))
            except (TypeError,ValueError):delay=15*(2**attempt)
            print(json.dumps(dict(event='retry',provider=provider,attempt=attempt+1,delay_seconds=delay,error=str(error))),flush=True)
            time.sleep(delay)

def collect(task,out,manifest_hash):
    s,period,url,ext=task
    if not re.fullmatch(r'[A-Za-z0-9_-]+',s['station_id']):raise ValueError('unsafe station identifier')
    dest=out/s['provider']/s['station_id']/(period+'.'+ext);meta=dest.with_suffix(dest.suffix+'.json');dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists() and meta.exists():
        m=json.loads(meta.read_text())
        if m.get('url')==url and m.get('status')=='complete' and m.get('sha256')==hashlib.sha256(dest.read_bytes()).hexdigest():
            return dict(m,resumed=True)
    m=dict(provider=s['provider'],station_id=s['station_id'],period=period,url=url,manifest_sha256=manifest_hash,retrieved_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),station_metadata_license=s['license'],license=('ECCC Data Services End-use Licence 2.1.1; attribution required; https://eccc-msc.github.io/open-data/licence/readme_en/' if s['provider']=='ECCC' else s['license']),attribution=('Data Source: Environment and Climate Change Canada' if s['provider']=='ECCC' else s['provider']))
    try:
        data,http_status,final_url,attempts=fetch_raw(url,s['provider']);m.update(http_status=http_status,final_url=final_url,attempts=attempts)
        audit=audit_bytes(data,s,period);tmp=dest.with_suffix(dest.suffix+'.part');tmp.write_bytes(data);tmp.replace(dest)
        m.update(status='complete',sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),audit=audit)
    except Exception as e:m.update(status='blocked',error=str(e),retryable=retryable_error(e))
    tmp=meta.with_suffix(meta.suffix+'.part');tmp.write_text(json.dumps(m,indent=2));tmp.replace(meta)
    return m

def main():
    p=argparse.ArgumentParser();p.add_argument('--manifest',required=True);p.add_argument('--out',required=True);p.add_argument('--start-year',type=int,default=2016);p.add_argument('--end-year',type=int,default=2025);p.add_argument('--max-batches',type=int,default=10);p.add_argument('--workers',type=int,default=2);p.add_argument('--providers',nargs='+');p.add_argument('--station-limit',type=int);p.add_argument('--retry-blocked',action='store_true');a=p.parse_args()
    if not 2016<=a.start_year<=a.end_year<=2025 or a.max_batches<1 or not 1<=a.workers<=6:p.error('invalid year range, batch count, or workers')
    manifest=pathlib.Path(a.manifest);mh=hashlib.sha256(manifest.read_bytes()).hexdigest();stations=list(csv.DictReader(manifest.open()))
    if a.providers:stations=[s for s in stations if s['provider'] in a.providers]
    if a.station_limit:stations=stations[:a.station_limit]
    out=pathlib.Path(a.out);out.mkdir(parents=True,exist_ok=True)
    todo=[];resumed=0;previously_blocked=0
    for task in tasks(stations,a.start_year,a.end_year):
        s,period,url,ext=task;dest=out/s['provider']/s['station_id']/(period+'.'+ext);meta=dest.with_suffix(dest.suffix+'.json')
        if meta.exists():
            m=json.loads(meta.read_text())
            if m.get('status')=='blocked' and m.get('url')==url and not a.retry_blocked and not m.get('retryable',retryable_error(m.get('error',''))):previously_blocked+=1;continue
        if dest.exists() and meta.exists():
            m=json.loads(meta.read_text())
            if m.get('status')=='complete' and m.get('url')==url and m.get('sha256')==hashlib.sha256(dest.read_bytes()).hexdigest():resumed+=1;continue
        todo.append(task)
        if len(todo)>=a.max_batches:break
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
        for result in pool.map(lambda t:collect(t,out,mh),todo):
            results.append(result)
            print(json.dumps({k:result.get(k) for k in ('provider','station_id','period','status','bytes','error')}),flush=True)
    report=dict(manifest_sha256=mh,attempted=len(results),resumed_skipped=resumed,previously_blocked_skipped=previously_blocked,completed=sum(r['status']=='complete' for r in results),blocked=sum(r['status']=='blocked' for r in results),raw_bytes=sum(r.get('bytes',0) for r in results),records=sum(r.get('audit',{}).get('records',0) for r in results),results=results)
    # A run report is immutable; sidecars are the resumable checkpoint.
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');(out/('run-'+stamp+'.json')).write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='results'},indent=2))
if __name__=='__main__':main()
