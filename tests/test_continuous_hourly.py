import hashlib,json,pathlib,sys,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from hourly_checkpoint import complete,archived_complete,mark_and_prune
from run_hourly_collection import decision

class ContinuousTests(unittest.TestCase):
    def test_missing_raw_requires_verified_archive(self):
        with tempfile.TemporaryDirectory() as d:
            path=pathlib.Path(d)/'missing.psv';m=dict(status='complete',url='https://example.org',sha256='a'*64)
            self.assertFalse(complete(path,m,m['url']))
            m['archive']=dict(verified=True,source_sha256='a'*64,release_url='https://github.com/msbowman87-cmd/archer-atmos/releases/tag/research-hourly-test',part='part.zip',part_sha256='b'*64)
            self.assertTrue(complete(path,m,m['url']))
            m['archive']['source_sha256']='wrong';self.assertFalse(complete(path,m,m['url']))
    def test_archive_reference_does_not_hide_present_corruption(self):
        with tempfile.TemporaryDirectory() as d:
            path=pathlib.Path(d)/'file';path.write_bytes(b'bad')
            m=dict(status='complete',url='u',sha256='a'*64,archive=dict(verified=True,source_sha256='a'*64,release_url='https://github.com/msbowman87-cmd/archer-atmos/releases/tag/research-hourly-test',part='p',part_sha256='b'*64))
            self.assertFalse(complete(path,m,'u'))
    def test_prune_only_after_source_hash_matches(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d);raw=root/'observations/NOAA/X/2016.psv';raw.parent.mkdir(parents=True);raw.write_bytes(b'original')
            sidecar=raw.with_suffix('.psv.json');sha=hashlib.sha256(b'original').hexdigest();sidecar.write_text(json.dumps(dict(status='complete',sha256=sha,url='u')))
            idx=dict(parts=[dict(name='p.zip',sha256='b'*64,files=['observations/NOAA/X/2016.psv'])])
            self.assertEqual(mark_and_prune(root,idx,'https://github.com/msbowman87-cmd/archer-atmos/releases/tag/research-hourly-test'),1)
            self.assertFalse(raw.exists());self.assertTrue(archived_complete(json.loads(sidecar.read_text())))
    def test_pending_and_retryable_failures_require_continuation(self):
        self.assertEqual(decision(dict(total=dict(pending_batches=1,blocked_batches=0))),'continue')
        self.assertEqual(decision(dict(total=dict(pending_batches=0,blocked_batches=1,retryable_blocked_batches=1))),'continue')
        self.assertEqual(decision(dict(total=dict(pending_batches=0,blocked_batches=1))),'all_candidates_attempted_with_gaps')
        self.assertEqual(decision(dict(total=dict(pending_batches=0,blocked_batches=0))),'current_manifest_collected')
if __name__=='__main__':unittest.main()
