"""Restore the newest research checkpoint from a temporary artifact or verified release."""
import hashlib,json,pathlib,shutil,subprocess,tempfile,time,zipfile
from hourly_checkpoint import mark_and_prune,digest

def gh(*args):
    return json.loads(subprocess.check_output(['gh',*args],text=True))

def download_with_retry(command,folder,attempts=4):
    """Retain no partial download between attempts; use bounded network retries."""
    for attempt in range(1,attempts+1):
        if folder.exists():shutil.rmtree(folder)
        folder.mkdir(parents=True)
        try:
            subprocess.run([*command,'--dir',str(folder)],check=True)
            return
        except subprocess.CalledProcessError as exc:
            print(json.dumps(dict(checkpoint_download='retry',attempt=attempt,max_attempts=attempts,error=str(exc))),flush=True)
            if attempt==attempts:raise
            time.sleep(min(45,6*attempt))

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
        try:
            with tempfile.TemporaryDirectory() as d:
                folder=pathlib.Path(d)/'artifact'
                download_with_retry(['gh','run','download',str(artifact['workflow_run']['id']),'--name','atmos-multi-provider-checkpoint'],folder)
                if not (folder/'stations.csv').is_file():
                    raise ValueError('downloaded artifact has no station manifest')
                shutil.copytree(folder,root,dirs_exist_ok=True)
            print(json.dumps(dict(restored='artifact',run_id=artifact['workflow_run']['id'])));return
        except (subprocess.CalledProcessError,OSError,ValueError) as error:
            # A verified release is preferable to losing collection continuity.
            # Reprocessing newer windows is safe because source hashes are tracked.
            print(json.dumps(dict(artifact_restore='failed',reason=str(error),fallback='latest_verified_research_release')),flush=True)
    if not release:raise SystemExit('No verified research checkpoint is available')
    with tempfile.TemporaryDirectory() as d:
        folder=pathlib.Path(d)/'release';tag=release['tag_name']
        download_with_retry(['gh','release','download',tag],folder)
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
