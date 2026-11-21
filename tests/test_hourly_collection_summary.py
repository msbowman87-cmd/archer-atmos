import csv,hashlib,json,pathlib,sys,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
import summarize_hourly_collection as m
from collect_selected_hourly import tasks

class SummaryTests(unittest.TestCase):
    def test_unique_task_counts_ignore_duplicate_run_logs(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d);manifest=root/'stations.csv';s=dict(provider='NOAA_GHCNh',station_id='TEST',country='US',history_start='2016-01-01',history_end='2016-12-31')
            with manifest.open('w') as f:w=csv.DictWriter(f,fieldnames=list(s));w.writeheader();w.writerow(s)
            task=next(tasks([s],2016,2025));dest=root/'NOAA_GHCNh/TEST/2016.psv';dest.parent.mkdir(parents=True);dest.write_bytes(b'fixture')
            dest.with_suffix('.psv.json').write_text(json.dumps(dict(url=task[2],status='complete',sha256=hashlib.sha256(b'fixture').hexdigest(),bytes=7,audit=dict(records=3))))
            for n in range(3):(root/f'run-{n}.json').write_text(json.dumps(dict(records=3)))
            r=m.summarize(manifest,root,True);self.assertEqual(r['total']['records'],3);self.assertEqual(r['total']['complete_batches'],1)
            dest.write_bytes(b'corruption');r=m.summarize(manifest,root,True);self.assertEqual(r['total']['complete_batches'],0);self.assertEqual(r['total']['pending_batches'],1)
    def test_blocked_separate_from_pending(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d);manifest=root/'stations.csv';s=dict(provider='NOAA_GHCNh',station_id='TEST',country='MX',history_start='2016-01-01',history_end='2017-12-31')
            with manifest.open('w') as f:w=csv.DictWriter(f,fieldnames=list(s));w.writeheader();w.writerow(s)
            task=next(tasks([s],2016,2025));meta=root/'NOAA_GHCNh/TEST/2016.psv.json';meta.parent.mkdir(parents=True);meta.write_text(json.dumps(dict(url=task[2],status='blocked')))
            r=m.summarize(manifest,root,True);self.assertEqual(r['total']['blocked_batches'],1);self.assertEqual(r['total']['pending_batches'],1)
if __name__=='__main__':unittest.main()
