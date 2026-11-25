#!/usr/bin/env python3
"""Audit source measurements by station/field without changing source data or flags."""
import argparse,calendar,collections,csv,datetime,hashlib,json,pathlib
from collect_selected_hourly import tasks
from hourly_checkpoint import archived_complete
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
    stations=list(csv.DictReader(manifest.open()));failures=[];count=0;record_count=0;reused=0;parsed=0
    # One-time migration from the original cumulative report.
    legacy=out/'coverage_audit.json'
    if legacy.exists():
        previous=json.loads(legacy.read_text())
        for r in previous.get('batches',[]):
            if r.get('sha256'):
                cache=raw/r['provider']/r['station_id']/(r['period']+'.coverage.json')
                if not cache.exists():cache.write_text(json.dumps(dict(r,audit_version=1)))
    with (out/'variable_coverage.csv').open('w',newline='') as stream,(out/'coverage_batches.jsonl').open('w') as detailed:
        fields=['provider','station_id','country','period','variable','expected_hours','nonmissing_records','observed_hours','missing_hour_fraction','source_quality_flags','quality_interpretation']
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for station,period,url,ext in tasks(stations,2016,2025):
            path=raw/station['provider']/station['station_id']/(period+'.'+ext);sidecar=path.with_suffix(path.suffix+'.json')
            cache=path.parent/(period+'.coverage.json')
            if not sidecar.exists():continue
            meta=json.loads(sidecar.read_text())
            if meta.get('status')!='complete' or meta.get('url')!=url:continue
            try:
                if path.exists():
                    if sha256(path)!=meta['sha256']:raise ValueError('source SHA256 mismatch')
                elif not archived_complete(meta):raise ValueError('source missing without verified archive')
                cached=json.loads(cache.read_text()) if cache.exists() else {}
                if cached.get('audit_version')==1 and cached.get('sha256')==meta['sha256']:
                    result=cached;reused+=1
                else:
                    if not path.exists():raise ValueError('archived source needs an audit cache or restoration')
                    result=dict(provider=station['provider'],station_id=station['station_id'],country=station['country'],period=period,sha256=meta['sha256'],audit_version=1,**audit_file(path,station['provider'],period))
                    cache.write_text(json.dumps(result));parsed+=1
                count+=1;record_count+=result['records'];detailed.write(json.dumps(result)+'\n')
                for variable,stats in result['variables'].items():
                    writer.writerow({**{k:result[k] for k in ('provider','station_id','country','period','expected_hours')},'variable':variable,**stats,'source_quality_flags':json.dumps(stats['source_quality_flags'],sort_keys=True),'quality_interpretation':'uninterpreted; not quality-approved coverage'})
            except Exception as error:failures.append(dict(provider=station['provider'],station_id=station['station_id'],period=period,error=str(error)))
    report=dict(manifest_sha256=sha256(manifest),audited_batches=count,records=record_count,incremental_cache_reused=reused,new_files_parsed=parsed,integrity_or_parse_failures=failures,quality_approved=False,batches_file='coverage_batches.jsonl',notes=['Coverage is distinct source hours per variable; source flags are not interpreted as training approval.','Full expected source year/month hours are used. ECCC uses local standard time; NOAA/IEM use UTC.','Present raw files are hash checked; archived files require verified archive references and matching versioned audit caches.'])
    (out/'coverage_audit.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    if failures:raise SystemExit('Integrity/audit failures prevent archival pruning')

if __name__=='__main__':main()
