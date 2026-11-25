import json,pathlib,random,sys,tempfile,unittest,zipfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from package_hourly_archive import package,digest
class PackageTests(unittest.TestCase):
    def test_split_restore_and_hashes(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d)/'checkpoint';out=pathlib.Path(d)/'parts';root.mkdir();(root/'a').write_bytes(b'abc');(root/'b').write_bytes(b'def');(root/'input').mkdir();(root/'input/private').write_bytes(b'ignored')
            r=package(root,out,'research-test',max_bytes=4);self.assertEqual(len(r['parts']),2);restore=pathlib.Path(d)/'restored'
            for part in r['parts']:
                self.assertEqual(digest(out/part['name']),part['sha256'])
                with zipfile.ZipFile(out/part['name']) as z:z.extractall(restore)
            self.assertEqual((restore/'a').read_bytes(),b'abc');self.assertEqual((restore/'b').read_bytes(),b'def');self.assertFalse((restore/'input').exists())
    def test_oversized_file_fails(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d)/'checkpoint';root.mkdir();(root/'a').write_bytes(b'12345')
            with self.assertRaises(ValueError):package(root,pathlib.Path(d)/'out','research-test',max_bytes=4)
    def test_oversized_compressible_audit_roundtrips(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d)/'checkpoint';out=pathlib.Path(d)/'parts'
            (root/'audit').mkdir(parents=True)
            source=root/'audit/coverage_batches.jsonl'
            source.write_bytes(b'{"station":"TEST","quality":"original"}\\n'*100)
            result=package(root,out,'research-audit',max_bytes=256)
            self.assertEqual(len(result['parts']),1)
            self.assertLessEqual(result['parts'][0]['bytes'],256)
            with zipfile.ZipFile(out/result['parts'][0]['name']) as z:
                self.assertEqual(z.read('audit/coverage_batches.jsonl'),source.read_bytes())
    def test_oversized_incompressible_source_fails(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d)/'checkpoint';root.mkdir()
            (root/'random.bin').write_bytes(random.Random(123).randbytes(2048))
            with self.assertRaisesRegex(ValueError,'compressed part limit'):
                package(root,pathlib.Path(d)/'parts','research-random',max_bytes=256)
if __name__=='__main__':unittest.main()
