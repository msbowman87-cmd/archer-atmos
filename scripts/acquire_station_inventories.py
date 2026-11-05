#!/usr/bin/env python3
"""Retrieve source inventories with hash-checked caching; never infer missing metadata."""
import argparse, concurrent.futures, csv, datetime, hashlib, io, json, pathlib, urllib.request
NOAA='https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/'
ECCC='https://collaboration.cmc.ec.gc.ca/cmc/climate/Get_More_Data_Plus_de_donnees/Station%20Inventory%20EN.csv'
IEM='https://mesonet.agron.iastate.edu/'
SMN='https://smn.conagua.gob.mx/tools/GUI/sivea_v3/'

def retrieve(url, path):
    meta=path.with_suffix(path.suffix+'.retrieval.json')
    if path.exists() and meta.exists():
        m=json.loads(meta.read_text())
        if m.get('url')==url and m.get('sha256')==hashlib.sha256(path.read_bytes()).hexdigest():return m
    m={'url':url,'retrieved_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Atmos-research-inventory/1.0'}),timeout=45) as r:
            data=r.read();m.update(status='retrieved',http_status=r.status,final_url=r.url,bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
        path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.part');tmp.write_bytes(data);tmp.replace(path)
    except Exception as e:m.update(status='inaccessible',error=str(e))
    meta.write_text(json.dumps(m,indent=2));return m

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();out=pathlib.Path(a.out);out.mkdir(parents=True,exist_ok=True)
    urls={'ghcnh-station-list.csv':NOAA+'doc/ghcnh-station-list.csv','ghcnh-inventory.txt':NOAA+'doc/ghcnh-inventory.txt','eccc.csv':ECCC,'iem-networks.geojson':IEM+'geojson/networks.geojson','smn-stations.json':SMN+'php/getTodasEstaciones.php','smn-sivea.js':SMN+'js/sivea.js','sih-climas.html':'https://sih.conagua.gob.mx/climas.html','iem-policy.html':IEM+'disclaimer.php','eccc-license.html':'https://climate.weather.gc.ca/prods_servs/attachment1_e.html','synoptic.html':'https://docs.synopticdata.com/services/time-series','madis.html':'https://madis.ncep.noaa.gov/madis_restrictions.shtml'}
    ledger=[]
    def get(kv):
        k,u=kv;m=retrieve(u,out/k);print(k,m['status'],m.get('bytes',m.get('error')),flush=True);return m
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:ledger.extend(pool.map(get,urls.items()))
    networks=json.loads((out/'iem-networks.geojson').read_text())['features']
    # ASOS has an accessible historical METAR archive. Also inspect regional
    # mesonets and Mexican DCP inventories; DCP inventory alone is not hourly proof.
    carib=set('AG AI AW BB BL BM BQ BS CU CW DM DO GD GP HT JM KN KY LC MF MQ MS PR SX TC TT VC VG VI'.split())
    wanted=[]
    for f in networks:
        n=f['id']
        if (n.endswith('ASOS') and (len(n)==7 or n.startswith('CA_') or n[:2] in carib or n.startswith('MX_'))) or n in {'USCRN','SCAN','ISUAG','ISUSM'} or (n.startswith('MX_') and n.endswith('DCP')):
            wanted.append((n+'.geojson',IEM+'geojson/network.php?network='+n))
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:ledger.extend(pool.map(get,wanted))
    (out.parent/'retrieval_ledger.json').write_text(json.dumps(ledger,indent=2))
if __name__=='__main__':main()
