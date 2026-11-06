"""Verified archive references allow resumption without retaining every raw file."""
import hashlib,json,pathlib

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def archived_complete(meta):
    a=meta.get('archive',{})
    return (a.get('verified') is True and a.get('source_sha256')==meta.get('sha256')
            and bool(meta.get('sha256')) and a.get('release_url','').startswith('https://github.com/msbowman87-cmd/archer-atmos/releases/tag/research-hourly-')
            and bool(a.get('part')) and len(a.get('part_sha256',''))==64)

def complete(dest,meta,url,verify=True):
    if meta.get('status')!='complete' or meta.get('url')!=url:return False
    if dest.exists():
        return digest(dest)==meta.get('sha256') if verify else dest.stat().st_size==meta.get('bytes')
    return archived_complete(meta)

def mark_and_prune(root,index,release_url):
    """Call only after release upload and asset sizes have been verified."""
    count=0
    for part in index['parts']:
        for member in part['files']:
            relative=pathlib.PurePosixPath(member)
            if relative.is_absolute() or '..' in relative.parts:raise ValueError('unsafe member')
            raw=root/member
            if not member.startswith('observations/') or member.endswith('.json') or not raw.is_file():continue
            sidecar=raw.with_suffix(raw.suffix+'.json')
            if not sidecar.exists():continue
            meta=json.loads(sidecar.read_text())
            if meta.get('status')!='complete':continue
            if digest(raw)!=meta.get('sha256'):raise ValueError('source changed before archive marking')
            meta['archive']=dict(verified=True,release_url=release_url,part=part['name'],part_sha256=part['sha256'],source_sha256=meta['sha256'])
            tmp=sidecar.with_suffix(sidecar.suffix+'.part');tmp.write_text(json.dumps(meta,indent=2));tmp.replace(sidecar)
            raw.unlink();count+=1
    return count

if __name__=='__main__':
    import sys
    root,folder,label=map(str,sys.argv[1:4]);folder=pathlib.Path(folder)
    index=json.loads((folder/(label+'-index.json')).read_text())
    published=json.loads((folder/'published.json').read_text());assets={a['name']:a for a in published['assets']}
    for part in index['parts']:
        assert assets[part['name']]['size']==part['bytes']
    print(json.dumps(dict(archived_raw_files_pruned=mark_and_prune(pathlib.Path(root),index,published['url']))))
