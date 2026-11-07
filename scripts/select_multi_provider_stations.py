#!/usr/bin/env python3
"""Select documented observation sites; never manufacture coverage to fill a quota."""
import argparse,collections,csv,datetime,html,json,math,pathlib,urllib.parse
CARIBBEAN=set('AG AI AW BB BL BQ BS CU CW DM DO GD GP HT JM KN KY LC MF MQ MS PR SX TC TT VC VG VI'.split())
TARGETS={'US':6000,'CA':2500,'MX':1500}
BASE=['provider','station_id','country','latitude','longitude','elevation_m','months_500plus','observations_2016_2025','name']
EXTRA=['history_start','history_end','coverage_basis','source_url','history_url','license','canonical_id','network','variables','timezone']
FIELDS=BASE+EXTRA+['selection_role','verification_status']

def parse(row):
    try:
        s={k:str(row.get(k,'') or '').strip() for k in BASE+EXTRA}
        s['country']=s['country'].upper()
        for k in ('latitude','longitude','elevation_m'):s[k]=float(s[k])
        for k in ('months_500plus','observations_2016_2025'):s[k]=int(s[k]) if s[k] else None
        if not s['provider'] or not s['station_id'] or s['country'] not in set(TARGETS)|CARIBBEAN:return None
        if not all(math.isfinite(s[k]) for k in ('latitude','longitude','elevation_m')):return None
        if s['elevation_m'] in {-999.9,-999,-9999,9999} or not -500<=s['elevation_m']<=6500:return None
        if not (-90<=s['latitude']<=90 and -180<=s['longitude']<=180):return None
        if not all(s[k] for k in ('source_url','history_url','license','coverage_basis')):return None
        if any(urllib.parse.urlparse(s[k]).scheme!='https' for k in ('source_url','history_url')):return None
        start=datetime.date.fromisoformat(s['history_start'][:10]);end=datetime.date.fromisoformat(s['history_end'][:10]+'-01' if len(s['history_end'])==7 else s['history_end'][:10])
        if end<start or start>datetime.date(2025,12,31) or end<datetime.date(2016,1,1):return None
        if s['coverage_basis']=='monthly_record_counts':
            if s['observations_2016_2025'] is None or s['observations_2016_2025']<=0:return None
            if s['months_500plus'] is None or not 0<=s['months_500plus']<=120:return None
        elif s['coverage_basis'] not in {'hourly_archive_period_only','METAR_archive_period_only'}:return None
        s['verification_status']='catalog_verified; hourly_completeness_unverified'
        return s
    except (KeyError,ValueError,TypeError):return None

def rank(s):
    # Count evidence beats period-only metadata; shorter histories remain eligible.
    return (-(s.get('months_500plus') or 0),-(s.get('observations_2016_2025') or 0),s['provider'],s['station_id'])

def xyz(s):
    lat=math.radians(s['latitude']);lon=math.radians(s['longitude'])
    return tuple(6371*v for v in (math.cos(lat)*math.cos(lon),math.cos(lat)*math.sin(lon),math.sin(lat)))

def distance(a,b):
    la,lb=map(math.radians,(a['latitude'],b['latitude']));dl=math.radians(b['longitude']-a['longitude'])
    q=math.sin((lb-la)/2)**2+math.cos(la)*math.cos(lb)*math.sin(dl/2)**2
    return 12742*math.asin(min(1,math.sqrt(q)))

def dedup(items,audit=None):
    # Conservative 500 m site exclusion; ECEF neighbor cells avoid grid-boundary,
    # high-latitude, and date-line bugs. Same provider IDs and canonical crosswalks
    # also deduplicate even if catalog coordinates differ. Log every exclusion.
    grid=collections.defaultdict(list);ids={};out=[]
    for s in sorted(items,key=rank):
        keys=[('provider',s['provider'],s['station_id'])]
        if s.get('canonical_id'):keys.append(('canonical',s['canonical_id']))
        same=next((ids[k] for k in keys if k in ids),None);reason='identifier_crosswalk'
        cell=tuple(math.floor(v/.5) for v in xyz(s))
        if same is None:
            nearby=[]
            for x in (-1,0,1):
                for y in (-1,0,1):
                    for z in (-1,0,1):nearby.extend(grid[(cell[0]+x,cell[1]+y,cell[2]+z)])
            same=next((a for a in nearby if distance(a,s)<=.5),None);reason='within_500m_conservative_site_exclusion'
        if same is not None:
            for k in keys:ids[k]=same
            if audit is not None:audit.append({'excluded_provider':s['provider'],'excluded_id':s['station_id'],'retained_provider':same['provider'],'retained_id':same['station_id'],'reason':reason,'distance_km':round(distance(s,same),6)})
            continue
        out.append(s);grid[cell].append(s)
        for k in keys:ids[k]=s
    return out

def spread(items,n):
    bins=collections.defaultdict(list)
    for s in sorted(items,key=rank):bins[(math.floor(s['latitude']),math.floor(s['longitude']))].append(s)
    # Quality-first ordering of occupied cells avoids southern/western truncation
    # from lexicographic cell order when a quota is smaller than the cell count.
    keys=sorted(bins,key=lambda k:rank(bins[k][0]));out=[]
    while keys and len(out)<n:
        remaining=[]
        for key in keys:
            if len(out)>=n:break
            out.append(bins[key].pop(0))
            if bins[key]:remaining.append(key)
        keys=remaining
    return out

def write_map(out,features):
    data=json.dumps(features).replace('<','\\u003c')
    page='''<!doctype html><html><head><meta charset="utf-8"><title>Atmos verified catalog locations</title><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"><style>body{margin:0;font:15px system-ui}header{padding:12px}#map{height:85vh}select{margin:8px}</style></head><body><header><b>Atmos observation locations — SELECTED sites</b><div>Catalog verified. Hourly completeness and variable coverage require archive audit. COUNT sites; 10,000 target.</div><label>Country <select id="country"><option value="">All</option></select></label><span id="count"></span></header><div id="map"></div><script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><script>const data=DATA;const map=L.map('map').setView([35,-100],3);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap contributors'}).addTo(map);const countries=[...new Set(data.features.map(f=>f.properties.country))].sort();const select=document.getElementById('country');countries.forEach(c=>{const o=document.createElement('option');o.value=c;o.textContent=c;select.append(o)});const group=L.layerGroup().addTo(map);function draw(){group.clearLayers();const fs=data.features.filter(f=>!select.value||f.properties.country===select.value);document.getElementById('count').textContent=fs.length+' locations';fs.forEach(f=>{const p=f.properties,box=document.createElement('div');box.textContent=[p.name,p.country,p.provider+': '+p.station_id,p.history_start+' to '+p.history_end,p.coverage_basis,p.verification_status].join(' | ');L.circleMarker([f.geometry.coordinates[1],f.geometry.coordinates[0]],{radius:3,weight:1,color:p.selection_role==='primary'?'#196db8':'#d07013'}).bindPopup(box).addTo(group)});}select.onchange=draw;draw();</script></body></html>'''
    (out/'map.html').write_text(page.replace('SELECTED',str(len(features['features']))).replace('COUNT',str(len(features['features']))).replace('DATA',data))

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',required=True,nargs='+');p.add_argument('--out',default='station-map');a=p.parse_args();out=pathlib.Path(a.out);out.mkdir(parents=True,exist_ok=True)
    rows=[];rejected=[]
    for path in a.input:
        with open(path,newline='',encoding='utf-8') as f:
            for i,r in enumerate(csv.DictReader(f),2):
                s=parse(r)
                if s:rows.append(s)
                else:rejected.append({'input':path,'line':i,'provider':r.get('provider'),'station_id':r.get('station_id'),'reason':'invalid_metadata_or_missing_historical_evidence'})
    audit=[];unique=dedup(rows,audit);chosen=[];counts={}
    for country,n in TARGETS.items():
        subset=spread([s for s in unique if s['country']==country],n)
        for s in subset:s['selection_role']='primary'
        chosen.extend(subset);counts[country]=len(subset)
    shortage=sum(TARGETS[c]-counts[c] for c in ('CA','MX'))
    carib=spread([s for s in unique if s['country'] in CARIBBEAN],shortage)
    for s in carib:s['selection_role']='caribbean_fallback'
    chosen+=carib
    with (out/'stations.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(chosen)
    features={'type':'FeatureCollection','features':[{'type':'Feature','geometry':{'type':'Point','coordinates':[s['longitude'],s['latitude'],s['elevation_m']]},'properties':{k:v for k,v in s.items() if k not in ('latitude','longitude')}} for s in chosen]}
    (out/'stations.geojson').write_text(json.dumps(features,separators=(',',':')));write_map(out,features)
    report={'status':'quota_complete_catalog_verified' if len(chosen)==10000 else 'blocked_shortfall','selected':len(chosen),'targets':TARGETS,'primary_counts':counts,'primary_shortfall':{c:TARGETS[c]-counts[c] for c in TARGETS},'caribbean_fallback':len(carib),'remaining_shortfall':10000-len(chosen),'provider_counts':dict(collections.Counter(s['provider'] for s in chosen)),'coverage_basis_counts':dict(collections.Counter(s['coverage_basis'] for s in chosen)),'at_least_60_months_500plus':sum((s['months_500plus'] or 0)>=60 for s in chosen),'rejected_rows':len(rejected),'duplicate_exclusions':len(audit),'unique_eligible_candidates':len(unique),'warning':'500m proximity exclusion is conservative, not proof of common operator. Review duplicate audit for distinct nearby sites. Period-only metadata does not prove observations exist within every intervening year. Counts are records, not unique hours or per-variable coverage. No modeled values or inferred elevations.'}
    for name,value in [('selection_report.json',report),('duplicate_audit.json',audit),('rejected_rows.json',rejected)]: (out/name).write_text(json.dumps(value,indent=2))
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
