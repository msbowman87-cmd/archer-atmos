"""Run resumable collection windows until data exhaustion or the runner deadline."""
import argparse,json,pathlib,subprocess,sys,time
from summarize_hourly_collection import summarize

def decision(report):
    total=report['total']
    if total['pending_batches'] or total.get('retryable_blocked_batches',0):return 'continue'
    return 'all_candidates_attempted_with_gaps' if total['blocked_batches'] else 'current_manifest_collected'

def main():
    p=argparse.ArgumentParser();p.add_argument('--checkpoint',required=True);p.add_argument('--seconds',type=int,default=16200);p.add_argument('--batches',type=int,default=100);a=p.parse_args()
    if not 1<=a.batches<=120 or a.seconds<60:p.error('invalid limits')
    root=pathlib.Path(a.checkpoint);deadline=time.monotonic()+a.seconds;window=0;stalled=0;needs_recovery=False
    import os
    while time.monotonic()<deadline:
        before=summarize(root/'stations.csv',root/'observations',False)
        if decision(before)!='continue':
            before['collection_state']=decision(before);(root/'collection_progress.json').write_text(json.dumps(before,indent=2));break
        window+=1
        for provider,workers in [('NOAA_GHCNh',2),('ECCC',2),('IEM_ASOS',1)]:
            remaining=int(deadline-time.monotonic())
            if remaining<60:break
            command=[sys.executable,'scripts/collect_selected_hourly.py','--manifest',str(root/'stations.csv'),'--out',str(root/'observations'),'--providers',provider,'--max-batches',str(a.batches),'--workers',str(workers)]
            try:subprocess.run(command,check=True,timeout=min(2400,remaining))
            except subprocess.TimeoutExpired:print(json.dumps(dict(provider=provider,event='runner_deadline_checkpointing')),flush=True);break
        report=summarize(root/'stations.csv',root/'observations',True)
        gain=report['total']['complete_batches']-before['total']['complete_batches']
        stalled=stalled+1 if gain==0 else 0
        report['collection_state']=decision(report);report['consecutive_no_progress_windows']=stalled
        (root/'collection_progress.json').write_text(json.dumps(report,indent=2))
        label=f"research-hourly-{os.environ['GITHUB_RUN_ID']}-{os.environ['GITHUB_RUN_ATTEMPT']}-w{window:04d}"
        folder=os.path.join(os.environ['RUNNER_TEMP'],label)
        subprocess.run(['bash','scripts/preserve_hourly_checkpoint.sh',str(root),folder,os.environ['GITHUB_SHA'],label],check=True)
        # Archive upload, source verification and pruning succeeded. Archive ZIPs
        # themselves must not accumulate on the runner across windows.
        import shutil
        shutil.rmtree(folder)
        print(json.dumps(dict(event='window_archived',window=window,new_complete=gain,state=report['collection_state'])),flush=True)
        if decision(report)!='continue':break
        if stalled>=3:
            needs_recovery=True;report['collection_state']='provider_failures_need_recovery';(root/'collection_progress.json').write_text(json.dumps(report,indent=2));break
        if gain==0:time.sleep(min(300,max(0,deadline-time.monotonic())))
    report=summarize(root/'stations.csv',root/'observations',False)
    report['collection_state']='provider_failures_need_recovery' if needs_recovery else decision(report)
    (root/'collection_progress.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
