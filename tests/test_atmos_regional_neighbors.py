import csv
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
from atmos_regional_neighbors import generate, distance_bearing

class NeighborTests(unittest.TestCase):
    def test_distance_and_bearing(self):
        km, b = distance_bearing(dict(latitude=40, longitude=-114),
                                 dict(latitude=40, longitude=-113))
        self.assertTrue(80 < km < 90)
        self.assertTrue(85 < b < 95)

    def test_training_only_neighbors_and_geographic_radius(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            m = base/'stations.csv'
            r = base/'readiness.csv'
            with m.open('w', newline='') as f:
                w = csv.DictWriter(f, fieldnames=['provider', 'station_id', 'latitude', 'longitude', 'elevation_m'])
                w.writeheader()
                for sid, lon in [('A', -114), ('B', -113.99), ('C', -95)]:
                    w.writerow(dict(provider='IEM_ASOS', station_id=sid, latitude=40,
                                    longitude=lon, elevation_m=1000))
            with r.open('w', newline='') as f:
                w = csv.DictWriter(f, fieldnames=['provider', 'station_id', 'readiness',
                                                   'training_variables', 'training_years'])
                w.writeheader()
                for sid in ['A','B','C']:
                    w.writerow(dict(provider='IEM_ASOS', station_id=sid,
                                    readiness='coverage_candidate_qc_pending',
                                    training_variables='temperature;wind_speed',
                                    training_years='2017;2018'))
            rows, report = generate(m, r)
            self.assertEqual(len(rows), 3)
            self.assertEqual(report['graph_targets'], 3)
            a = next(row for row in rows if row['target_station_id']=='A')
            self.assertLessEqual(len(a['candidate_neighbors']), 1)
            if a['candidate_neighbors']:
                self.assertEqual(a['candidate_neighbors'][0]['station_id'], 'B')
            self.assertEqual(next(row for row in rows if row['target_station_id']=='C')['candidate_neighbors'], [])

    def test_dateline_distance(self):
        km, _ = distance_bearing(dict(latitude=60, longitude=179.8),
                                 dict(latitude=60, longitude=-179.8))
        self.assertLess(km, 30)

if __name__ == '__main__':
    unittest.main()
