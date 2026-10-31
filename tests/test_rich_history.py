import tempfile
import unittest
from pathlib import Path
from atmos.rich_history import HOURLY,run,request


class RichHistoryTests(unittest.TestCase):
    def test_bounded_month_and_fields(self):
        observed=[]
        def fake(point,year,month):
            observed.append(point['id'])
            return {'hourly':{'time':['2025-01-01T00:00'],
                              **{name:[1] for name in HOURLY}}},'fake-sha256'
        with tempfile.TemporaryDirectory() as root:
            report=run(2025,1,0,grid_count=5000,shard_size=5,output=root,fetch=fake)
            self.assertEqual(report['locations_succeeded'],5)
            self.assertEqual(report['rows'],5)
            self.assertEqual(observed,['G00001','G00002','G00003','G00004','G00005'])
            with self.assertRaises(FileExistsError):run(2025,1,0,output=root,fetch=fake)
            rows=Path(root).glob('*.csv')
            self.assertEqual(len(list(rows)),1)
    def test_partial_failure_reported(self):
        def fake(point,year,month):
            if point['id']=='G00002':raise RuntimeError('temporarily missing')
            return {'hourly':{'time':['2025-01-01T00:00'],
                              **{name:[None] for name in HOURLY}}},'checksum'
        with tempfile.TemporaryDirectory() as root:
            report=run(2025,1,0,shard_size=3,output=root,fetch=fake)
            self.assertEqual(report['locations_succeeded'],2)
            self.assertEqual(report['failures'][0]['location_id'],'G00002')
    def test_request_month_validation(self):
        with self.assertRaises(ValueError):request({'lat':0,'lon':0},2025,13)
    def test_request_budget(self):
        with self.assertRaises(ValueError):run(2025,1,0,shard_size=100)


if __name__=='__main__':unittest.main()
