import tempfile
import unittest
from pathlib import Path
from atmos.on_demand import params,regional_points,retrieve,validate_coordinates


class OnDemandTests(unittest.TestCase):
    def test_any_coordinate_and_dateline(self):
        self.assertEqual(validate_coordinates(-33.9,151.2),(-33.9,151.2))
        for lat,lon in [(0,179.9),(90,0),(-90,0)]:
            self.assertTrue(all(-90<=p['latitude']<=90 and -180<=p['longitude']<=180
                                for p in regional_points(lat,lon)))
    def test_invalid_coordinates(self):
        for lat,lon in [(91,0),(0,181),(float('nan'),0)]:
            with self.assertRaises(ValueError):params(lat,lon)
    def test_rich_fields_and_no_unavailable_long_horizon(self):
        p=params(42.48,-114.48)
        self.assertIn('relative_humidity_2m',p['hourly'])
        self.assertIn('temperature_850hPa',p['hourly'])
        self.assertIn('precipitation_sum',p['daily'])
        with self.assertRaises(ValueError):params(0,0,30)
    def test_cache_hit_and_expiry(self):
        calls=[]
        def fake(p):
            calls.append(p)
            return {'hourly':{'time':['2026-10-31T00:00']}}
        with tempfile.TemporaryDirectory() as root:
            first=retrieve(42.48,-114.48,cache_dir=root,now=1000,fetcher=fake)
            self.assertEqual(first['cache_status'],'miss')
            self.assertEqual(len(calls),5)
            second=retrieve(42.48,-114.48,cache_dir=root,now=1200,fetcher=fake)
            self.assertEqual(second['cache_status'],'hit')
            self.assertEqual(len(calls),5)
            third=retrieve(42.48,-114.48,cache_dir=root,now=5000,fetcher=fake)
            self.assertEqual(third['cache_status'],'miss')
            self.assertEqual(len(calls),10)
            self.assertIsNone(third['model_issue_time_utc'])
    def test_failed_query_does_not_cache_incomplete_region(self):
        count=[0]
        def flaky(p):
            count[0]+=1
            if count[0]==3:raise RuntimeError('unavailable')
            return {'hourly':{'time':[]}}
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(RuntimeError):retrieve(10,20,cache_dir=root,fetcher=flaky)
            self.assertEqual(list(Path(root).glob('*.json')),[])


if __name__=='__main__':unittest.main()
