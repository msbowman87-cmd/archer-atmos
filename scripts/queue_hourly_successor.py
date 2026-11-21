"""Keep one research successor queued; supervision recovers dispatch failures."""
import json,os,pathlib,subprocess
from run_hourly_collection import decision
def main():
    if os.environ.get('GITHUB_REF')!='refs/heads/research/daily-walk-forward-20261101':raise SystemExit('research branch only')
    root=pathlib.Path('research/station-selection-20261105')
    report=json.loads((root/'collection_progress.json').read_text()) if (root/'collection_progress.json').exists() else None
    if report and decision(report)!='continue':print('Current manifest exhausted; source gaps remain explicit.');return
    if report and report.get('collection_state')=='provider_failures_need_recovery':print('Provider recovery required; hourly supervisor will inspect.');return
    repo=os.environ['GH_REPO'];current=int(os.environ['GITHUB_RUN_ID'])
    runs=json.loads(subprocess.check_output(['gh','api',f'repos/{repo}/actions/workflows/408633199/runs?branch=research%2Fdaily-walk-forward-20261101&per_page=100'],text=True))['workflow_runs']
    active=[r for r in runs if r['id']!=current and r['status'] in {'queued','in_progress','waiting','pending','requested'}]
    if active:print(json.dumps(dict(successor_already_active=[r['id'] for r in active])));return
    result=subprocess.run(['gh','workflow','run','408633199','--ref','research/daily-walk-forward-20261101','-f','batches=100'],capture_output=True,text=True)
    if result.returncode:print(json.dumps(dict(successor_dispatch='failed',error=result.stderr.strip(),recovery='hourly supervisor')),flush=True)
    else:print(json.dumps(dict(successor_dispatch='accepted',branch='research/daily-walk-forward-20261101')),flush=True)
if __name__=='__main__':main()
