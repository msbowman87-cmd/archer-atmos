#!/usr/bin/env python3
"""Report active-manifest task coverage; never sum overlapping run totals."""
import argparse,collections,csv,hashlib,json,pathlib
from collect_selected_hourly import tasks,retryable_error
from hourly_checkpoint import complete

def summarize(manifest,out,verify_hashes=False):
    stations=list(csv.DictReader(manifest.open()));by_provider={};by_country={}
    def blank():return dict(planned_batches=0,complete_batches=0,blocked_batches=0,pending_batches=0,retryable_blocked_batches=0,records=0,raw_bytes=0)
    for s,period,url,ext in tasks(stations,2016,2025):
        provider=by_provider.setdefault(s['provider'],blank());country=by_country.setdefault(s['country'],blank())
        dest=out/s['provider']/s['station_id']/(period+'.'+ext);meta=dest.with_suffix(dest.suffix+'.json');state='pending';records=0;size=0
        if meta.exists():
            try:
                m=json.loads(meta.read_text())
                if m.get('url')==url:
                    if complete(dest,m,url,verify=verify_hashes):
                        state='complete';records=m['audit']['records'];size=m['bytes']
                    elif m.get('status')=='blocked':state='blocked'
            except (ValueError,KeyError):pass
        for group in (provider,country):
            group['planned_batches']+=1;group[state+'_batches']+=1;group['records']+=records;group['raw_bytes']+=size
            if state=='blocked' and m.get('retryable',retryable_error(m.get('error',''))):group['retryable_blocked_batches']+=1
    total={k:sum(v[k] for v in by_provider.values()) for k in blank()}
    return dict(manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),stations=len(stations),total=total,by_provider=by_provider,by_country=by_country,integrity_check='SHA256 for present raw files; verified archive references for archived files' if verify_hashes else 'file size/source URL or verified archive reference',notes=['Counts represent unique active station-period tasks, not sums of run logs.','Blocked means an attempted task did not yield valid measurements. Pending means not collected or not intact.','A completed batch does not establish complete per-variable hourly coverage.'])

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',required=True);p.add_argument('--out',required=True);p.add_argument('--verify-hashes',action='store_true');p.add_argument('--report',required=True);a=p.parse_args();r=summarize(pathlib.Path(a.manifest),pathlib.Path(a.out),a.verify_hashes);pathlib.Path(a.report).write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))
