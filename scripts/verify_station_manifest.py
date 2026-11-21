#!/usr/bin/env python3
"""Independent output checks: schema, geometry, identity, and site separation."""
import argparse,csv,hashlib,json,math,pathlib,sys
from select_multi_provider_stations import parse,distance,xyz

def verify(root):
    rows=list(csv.DictReader((root/'stations.csv').open()));geo=json.loads((root/'stations.geojson').read_text());report=json.loads((root/'selection_report.json').read_text());features=geo['features'];assert len(rows)==len(features)==report['selected']
    cells={};identities=set();canon=set();nearby=0
    for r,f in zip(rows,features):
        s=parse(r);assert s is not None,(r['provider'],r['station_id'])
        identity=(s['provider'],s['station_id']);assert identity not in identities;identities.add(identity)
        if s['canonical_id']:assert s['canonical_id'] not in canon;canon.add(s['canonical_id'])
        assert f['geometry']['coordinates']==[s['longitude'],s['latitude'],s['elevation_m']]
        assert f['properties']['station_id']==s['station_id'] and f['properties']['provider']==s['provider']
        cell=tuple(math.floor(v/.5) for v in xyz(s))
        for x in (-1,0,1):
            for y in (-1,0,1):
                for z in (-1,0,1):
                    for t in cells.get((cell[0]+x,cell[1]+y,cell[2]+z),[]):
                        assert distance(s,t)>.5,(identity,t['station_id'])
        cells.setdefault(cell,[]).append(s)
    page=(root/'map.html').read_text();embedded=page.split('const data=',1)[1].split(';const map=',1)[0];assert json.loads(embedded)==geo
    return dict(status='passed',locations=len(rows),checks=['all records revalidated','CSV/GeoJSON identity and coordinates agree','map embedded features exactly match GeoJSON','no repeated provider IDs or canonical crosswalk IDs','no retained site pair within 500 m'],sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'stations.csv',root/'stations.geojson',root/'map.html')},limitations=['Map GUI interactions not exercised; JavaScript syntax checked separately.','Source catalog verification is not a per-station or per-variable hourly completeness certification.'])
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);a=p.parse_args();root=pathlib.Path(a.input);r=verify(root);(root/'manifest_verification.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))
