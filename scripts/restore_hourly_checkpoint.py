"""Restore the newest research checkpoint from a temporary artifact or verified release."""
import hashlib,json,pathlib,shutil,subprocess,tempfile,zipfile
from hourly_checkpoint import mark_and_prune,digest

def gh(*args):
    return json.loads(subprocess.check_output(['gh',*args],text=True))

def main():
    import os,sys
    root=pathlib.Path(sys.argv[1]);root.mkdir(parents=True,exist_ok=True);repo=os.environ['GH_REPO']
    artifacts=gh('api',f'repos/{repo}/actions/artifacts?name=atmos-multi-provider-checkpoint&per_page=100')['artifacts']
    artifacts=[a for a in artifacts if not a['expired'] and a.get('workflow_run',{}).get('head_branch')=='research/daily-walk-forward-20261101']
    releases=gh('api',f'repos/{repo}/releases?per_page=100')
    releases=[r for r in releases if r['tag_name'].startswith('research-hourly-') and r['prerelease'] and not r['draft']]
    artifact=max(artifacts,key=lambda a:a['created_at']) if artifacts else None
    release=max(releases,key=lambda r:r['published_at']) if releases else None
    if artifact and (not release or artifact['created_at']>=release['published_at']):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(['gh','run','download',str(artifact['workflow_run']['id']),'--name','atmos-multi-provider-checkpoint','--dir',d],check=True)
            shutil.copytree(d,root,dirs_exist_ok=True)
        print(json.dumps(dict(restored='artifact',run_id=artifact['workflow_run']['id'])));return
    if not release:raise SystemExit('No verified research checkpoint is available')
    with tempfile.TemporaryDirectory() as d:
        folder=pathlib.Path(d);tag=release['tag_name']
        subprocess.run(['gh','release','download',tag,'--dir',d],check=True)
        index_path=folder/(tag+'-index.json');index=json.loads(index_path.read_text())
        for part in index['parts']:
            path=folder/part['name']
            if path.stat().st_size!=part['bytes'] or digest(path)!=part['sha256']:raise ValueError('archive part integrity failure')
            with zipfile.ZipFile(path) as z:
                for name in z.namelist():
                    p=pathlib.PurePosixPath(name)
                    if p.is_absolute() or '..' in p.parts:raise ValueError('unsafe ZIP member')
                z.extractall(root)
        # All part hashes and source hashes are checked before source files are pruned.
        mark_and_prune(root,index,release['html_url'])
    print(json.dumps(dict(restored='release',release_url=release['html_url'])))
if __name__=='__main__':main()
