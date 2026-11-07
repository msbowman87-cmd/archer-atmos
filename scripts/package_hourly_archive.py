#!/usr/bin/env python3
"""Create size-bounded, CRC-checked research archives with original bytes and SHA256."""
import argparse,hashlib,json,pathlib,zipfile

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def package(root,out,label,max_bytes=512*1024*1024):
    if not label or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in label):raise ValueError('unsafe archive label')
    out.mkdir(parents=True,exist_ok=True);files=[]
    for p in sorted(root.rglob('*')):
        rel=p.relative_to(root)
        if not p.is_file() or p.is_symlink() or rel.parts[0] in {'input','code','archives'} or '__pycache__' in rel.parts or p.suffix=='.part':continue
        # Source inventories remain retrievable by URL/hash; only the research
        # checkpoint and original observation source bytes are packaged here.
        if p.stat().st_size>max_bytes:raise ValueError('single file exceeds part limit: '+str(rel))
        files.append(p)
    parts=[];batch=[];size=0
    def write_part(batch):
        name=f'{label}-part{len(parts)+1:04d}.zip';dest=out/name
        with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for p in batch:z.write(p,str(p.relative_to(root)))
        with zipfile.ZipFile(dest) as z:
            if z.testzip() is not None:raise ValueError('ZIP CRC failure')
        parts.append(dict(name=name,bytes=dest.stat().st_size,sha256=digest(dest),files=[str(p.relative_to(root)) for p in batch]))
    for p in files:
        n=p.stat().st_size
        if batch and size+n>max_bytes:write_part(batch);batch=[];size=0
        batch.append(p);size+=n
    if batch:write_part(batch)
    index=dict(label=label,parts=parts,notes=['Extract every part into the same directory to restore the checkpoint.','SHA256 values verify the integrity of each part; original source bytes and per-file sidecars are retained.','Data Source: Environment and Climate Change Canada. See DATA_ATTRIBUTION.md for source-specific terms.','This research data archive is not a production software release and does not certify complete hourly coverage.'])
    path=out/(label+'-index.json');path.write_text(json.dumps(index,indent=2));return index
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--checkpoint',required=True);p.add_argument('--out',required=True);p.add_argument('--label',required=True);a=p.parse_args();r=package(pathlib.Path(a.checkpoint),pathlib.Path(a.out),a.label);print(json.dumps({'parts':len(r['parts']),'compressed_bytes':sum(x['bytes'] for x in r['parts'])}))
