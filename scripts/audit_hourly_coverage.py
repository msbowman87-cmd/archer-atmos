#!/usr/bin/env python3
"""Audit source measurements by station/field without changing source data or flags."""
import argparse,calendar,collections,csv,datetime,hashlib,json,pathlib
from collect_selected_hourly import tasks
MISSING={'','M','-9999','-9999.0','-9999.9','-999.9'}
NOAA_META={'STATION','Station_name','DATE','Year','Month','Day','Hour','Minute','LATITUDE','LONGITUDE','ELEVATION'}
IEM_META={'station','valid','lon','lat','elevation','metar','peak_wind_time'}
ECCC_FIELDS=['TEMP','DEW_POINT_TEMP','HUMIDEX','PRECIP_AMOUNT','RELATIVE_HUMIDITY','STATION_PRESSURE','VISIBILITY','WEATHER_ENG_DESC','WINDCHILL','WIND_DIRECTION','WIND_SPEED']

def source_rows(path,provider):
    if provider=='ECCC':
        j=json.loads(path.read_text(encoding='utf-8-sig'))
        for f in j['features']:
            r=f['properties'];yield r['LOCAL_DATE'],{k:r.get(k) for k in ECCC_FIELDS},{k:r.get(k+'_FLAG') for k in ECCC_FIELDS}
    else:
        with path.open(encoding='utf-8-sig',newline='') as stream:
            reader=csv.DictReader(stream,delimiter='|' if provider=='NOAA_GHCNh' else ',')
            selected=[k for k in (reader.fieldnames or []) if k not in (NOAA_META if provider=='NOAA_GHCNh' else IEM_META) and (provider!='NOAA_GHCNh' or not any(t in k for t in ['_Code','_Type','_ID']))]
            for r in reader:
                if provider=='NOAA_GHCNh':
                    vals={k:r.get(k) for k in selected}
                    yield r['DATE'],vals,{k:r.get(k+'_Quality_Code') for k in vals}
                else:yield r['valid'],{k:r.get(k) for k in selected},{}

def audit_file(path,provider,period):
    hours=collections.defaultdict(set);records=collections.Counter();flags=collections.defaultdict(collections.Counter);allhours=set();n=0
    expected=(366 if calendar.isleap(int(period[:4])) else 365)*24 if len(period)==4 else calendar.monthrange(int(period[:4]),int(period[5:7]))[1]*24
    fields=set()
    for stamp,values,qc in source_rows(path,provider):
        parsed=datetime.datetime.fromisoformat(stamp.replace('Z','+00:00'))
        if parsed.strftime('%Y' if len(period)==4 else '%Y-%m')!=period:raise ValueError('out-of-period source timestamp')
        hour=parsed.strftime('%Y-%m-%dT%H');n+=1;fields.update(values)
        for field,v in values.items():
            if v is None or str(v).strip() in MISSING:continue
            records[field]+=1;hours[field].add(hour);allhours.add(hour)
            flag=qc.get(field)
            if flag is not None and str(flag).strip():flags[field][str(flag)]+=1
    return dict(records=n,expected_hours=expected,observed_hours_any=len(allhours),variables={f:dict(nonmissing_records=records[f],observed_hours=len(hours[f]),missing_hour_fraction=round(1-len(hours[f])/expected,6),source_quality_flags=dict(flags[f])) for f in sorted(fields)})

def sha256(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--manifest',required=True);p.add_argument('--observations',required=True);p.add_argument('--out',required=True);a=p.parse_args();manifest=pathlib.Path(a.manifest);raw=pathlib.Path(a.observations);out=pathlib.Path(a.out);out.mkdir(parents=True,exist_ok=True)
    stations=list(csv.DictReader(manifest.open()));results=[];failures=[]
    for s,period,url,ext in tasks(stations,2016,2025):
        path=raw/s['provider']/s['station_id']/(period+'.'+ext);sidecar=path.with_suffix(path.suffix+'.json')
        if not sidecar.exists():continue
        m=json.loads(sidecar.read_text())
        if m.get('status')!='complete' or m.get('url')!=url:continue
        try:
            if not path.exists() or sha256(path)!=m['sha256']:raise ValueError('source file missing or SHA256 mismatch')
            r=audit_file(path,s['provider'],period)
            results.append(dict(provider=s['provider'],station_id=s['station_id'],country=s['country'],period=period,sha256=m['sha256'],**r))
            print(json.dumps(dict(event='batch_audited',provider=s['provider'],station_id=s['station_id'],period=period,records=r['records'])),flush=True)
        except Exception as e:failures.append(dict(provider=s['provider'],station_id=s['station_id'],period=period,error=str(e)))
    with (out/'variable_coverage.csv').open('w',newline='') as f:
        fields=['provider','station_id','country','period','variable','expected_hours','nonmissing_records','observed_hours','missing_hour_fraction','source_quality_flags','quality_interpretation']
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for r in results:
            for v,stats in r['variables'].items():w.writerow({**{k:r[k] for k in ('provider','station_id','country','period','expected_hours')},'variable':v,**stats,'source_quality_flags':json.dumps(stats['source_quality_flags'],sort_keys=True),'quality_interpretation':'uninterpreted; not quality-approved coverage'})
    report=dict(manifest_sha256=sha256(manifest),audited_batches=len(results),records=sum(r['records'] for r in results),integrity_or_parse_failures=failures,quality_approved=False,notes=['Missing-hour fractions use full source year/month expected hours; partial operating periods remain visible.','ECCC coverage uses local standard time; raw UTC_DATE is preserved. NOAA/IEM use UTC.','Subhourly reports count once per hour for each variable.','Source flags are reported without asserting they are acceptable for training. Units, flag mappings and archive completeness must be reviewed before model training.','Missing files outside completed checkpoints are pending, not assumed to contain observations.'],batches=results)
    (out/'coverage_audit.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='batches'},indent=2))
if __name__=='__main__':main()
