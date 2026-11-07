#!/usr/bin/env python3
"""Normalize verified source catalog records. Period bounds do not imply completeness."""
import argparse, collections, csv, json, pathlib, sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from select_multi_provider_stations import CARIBBEAN, TARGETS, distance
from acquire_station_inventories import NOAA,ECCC,IEM
FIELDS=['provider','station_id','country','latitude','longitude','elevation_m','months_500plus','observations_2016_2025','name','history_start','history_end','coverage_basis','source_url','history_url','license','canonical_id','network','variables','timezone']

def normalize(root):
    rows=[];excluded=collections.Counter();counts=collections.defaultdict(dict)
    with (root/'ghcnh-inventory.txt').open() as f:
        for line in f:
            p=line.split()
            if len(p)!=14:continue
            try:year=int(p[1]);v=list(map(int,p[2:]))
            except ValueError:continue
            if 2016<=year<=2025:
                # A station-year must occur once; duplicate lines must not inflate evidence.
                if year in counts[p[0]]:raise ValueError('duplicate station-year '+p[0])
                counts[p[0]][year]=v
    noaa_records=list(csv.DictReader((root/'ghcnh-station-list.csv').open()))
    wmo=collections.defaultdict(list);icao=collections.defaultdict(list)
    for r in noaa_records:
        if r['GHCN_ID'] not in counts:continue
        if r['WMO_ID']:wmo[r['WMO_ID'].lstrip('0')].append(r)
        if r['ICAO']:icao[r['ICAO']].append(r)
    def crosswalk(candidates,lat,lon):
        try:
            here=dict(latitude=float(lat),longitude=float(lon));near=[r for r in candidates if distance(here,dict(latitude=float(r['LATITUDE']),longitude=float(r['LONGITUDE'])))<=2]
            return 'GHCNH:'+near[0]['GHCN_ID'] if len(near)==1 else None
        except (ValueError,TypeError):return None
    for r in noaa_records:
        country=r['ISO_CODE'];sid=r['GHCN_ID'];years=counts.get(sid,{})
        if country not in set(TARGETS)|CARIBBEAN:continue
        obs=sum(sum(max(0,x) for x in v) for v in years.values())
        if not obs:excluded['NOAA_no_2016_2025_records']+=1;continue
        months=[f'{y}-{i+1:02d}' for y,v in sorted(years.items()) for i,x in enumerate(v) if x>0]
        rows.append(dict(provider='NOAA_GHCNh',station_id=sid,country=country,latitude=r['LATITUDE'],longitude=r['LONGITUDE'],elevation_m=r['ELEVATION'],name=r['NAME'],months_500plus=sum(sum(x>=500 for x in v) for v in years.values()),observations_2016_2025=obs,history_start=months[0]+'-01',history_end=months[-1],coverage_basis='monthly_record_counts',source_url=NOAA+'doc/ghcnh-station-list.csv',history_url=NOAA+'doc/ghcnh-inventory.txt',license='NOAA public archive; retain source attribution and embedded provenance; third-party source terms may apply',canonical_id='GHCNH:'+sid,network='GHCNh',variables='station-specific; not certified by record counts',timezone='UTC'))
    lines=(root/'eccc.csv').read_text(encoding='utf-8-sig').splitlines()
    start=next(i for i,l in enumerate(lines) if l.startswith('"Name","Province"'))
    for r in csv.DictReader(lines[start:]):
        first=r['HLY First Year'];last=r['HLY Last Year']
        if not first or not last or int(first)>2025 or int(last)<2016:continue
        rows.append(dict(provider='ECCC',station_id=r['Station ID'],country='CA',latitude=r['Latitude (Decimal Degrees)'],longitude=r['Longitude (Decimal Degrees)'],elevation_m=r['Elevation (m)'],name=r['Name'],months_500plus='',observations_2016_2025='',history_start=first+'-01-01',history_end=last+'-12-31',coverage_basis='hourly_archive_period_only',source_url=ECCC,history_url='https://climate.weather.gc.ca/climate_data/bulk_data_e.html?format=csv&stationID='+r['Station ID']+'&Year=2016&Month=1&timeframe=1',license='ECCC licence: attribution required; no explicit fee for source data; same redistribution restrictions must accompany onward use; as-is; https://climate.weather.gc.ca/prods_servs/attachment1_e.html',canonical_id=crosswalk(wmo.get(r['WMO ID'].lstrip('0'),[]),r['Latitude (Decimal Degrees)'],r['Longitude (Decimal Degrees)']) or 'ECCC:'+r['Climate ID'],network=r['Province'],variables='station-specific; must audit downloaded values',timezone='local standard time; retain source timestamp'))
    for path in sorted(root.glob('*.geojson')):
        if path.name=='iem-networks.geojson':continue
        try:j=json.loads(path.read_text())
        except ValueError:excluded['IEM_invalid_inventory']+=1;continue
        for f in j.get('features',[]):
            p=f['properties'];n=p.get('network',path.stem);country=p.get('country');begin=p.get('archive_begin');end=p.get('archive_end')
            if country not in set(TARGETS)|CARIBBEAN:continue
            if not n.endswith('ASOS'):
                excluded['IEM_'+n+'_hourly_archive_not_verified']+=1;continue
            if not begin or begin[:4]>'2025' or (end and end[:4]<'2016'):continue
            coords=(f.get('geometry') or {}).get('coordinates',[])
            if len(coords)<2:excluded['IEM_no_coordinates']+=1;continue
            gh=(p.get('attributes') or {}).get('GHCNH_ID','')
            linked=crosswalk(icao.get(f['id'],[]) or icao.get('K'+f['id'],[]) if country=='US' else icao.get(f['id'],[]),coords[1],coords[0])
            rows.append(dict(provider='IEM_ASOS',station_id=f['id'],country=country,latitude=coords[1],longitude=coords[0],elevation_m=p.get('elevation'),name=p.get('sname',''),months_500plus='',observations_2016_2025='',history_start=begin,history_end=end or '2025-12-31',coverage_basis='METAR_archive_period_only',source_url=IEM+'geojson/network.php?network='+n,history_url=IEM+'cgi-bin/request/asos.py',license='IEM public archive; no warranty; upstream attribution retained; see IEM disclaimer',canonical_id='GHCNH:'+gh if gh else linked or 'IEM:'+n+':'+f['id'],network=n,variables='METAR fields; availability varies',timezone='UTC'))
    smn=root/'smn-stations.json'
    if smn.exists():
        try:
            j=json.loads(smn.read_text());excluded['SMN_current_inventory_no_verified_2016_2025_hourly_archive']=len(j) if isinstance(j,list) else 1
        except ValueError:excluded['SMN_non_JSON_response']=1
    return rows,dict(excluded)

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--out',required=True);a=p.parse_args();out=pathlib.Path(a.out);out.mkdir(parents=True,exist_ok=True)
    rows,excluded=normalize(pathlib.Path(a.input))
    with (out/'normalized.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    (out/'normalization_report.json').write_text(json.dumps({'normalized_records':len(rows),'excluded':excluded},indent=2))
    print(len(rows),excluded)
if __name__=='__main__':main()
