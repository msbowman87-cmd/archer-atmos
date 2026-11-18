import datetime
import io
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
from atmos_regional_actual_pilot import (
    examples, latest, ridge_fit, metrics, load_temperature, choose_cluster,
)

UTC = datetime.timezone.utc

class RegionalPilotTests(unittest.TestCase):
    def test_noaa_flags_fail_closed_and_keep_last_valid_in_hour(self):
        data = ('DATE|temperature|temperature_Quality_Code|temperature_Source_Code\n'
                '2022-01-01T00:00:00|5|1|335\n'
                '2022-01-01T00:50:00|7|1|335\n'
                '2022-01-01T01:00:00|90|3|335\n'
                '2022-01-01T02:00:00|11|1|unknown\n').encode()
        hours, summary = load_temperature(data)
        self.assertEqual(len(hours), 1)
        self.assertEqual(next(iter(hours.values())), 7)
        self.assertEqual(summary['noaa_source_quality_not_approved'], 1)
        self.assertEqual(summary['outside_plausibility_bounds'], 1)

    def test_no_future_observations_used(self):
        t0 = datetime.datetime(2022, 1, 1, tzinfo=UTC)
        obs = {t0+datetime.timedelta(hours=i): 20 for i in range(250)}
        future = t0+datetime.timedelta(hours=200)
        obs[future] = 99
        cases = list(examples(obs, {'N':{t:15 for t in obs}}, {'N':0}))
        relevant = [r for r in cases if r['valid_at'] == future]
        self.assertEqual(len(relevant), 1)
        self.assertEqual(relevant[0]['baseline'], 20)
        self.assertLess(relevant[0]['regional'][-1], 0)

    def test_ridge_fit_improves_known_relation(self):
        cases = [{'local':[1.,float(i)], 'regional':[1.,float(i),float(i)*0.5],
                  'actual':2+3*i, 'baseline':0} for i in range(100)]
        model = ridge_fit(cases,'local')
        self.assertAlmostEqual(model[0],2,delta=0.15)
        self.assertAlmostEqual(model[1],3,delta=0.02)
        m = metrics(cases, model, ridge_fit(cases,'regional'))
        self.assertEqual(m['cases'],100)

    def test_choose_cluster_train_only(self):
        with tempfile.TemporaryDirectory() as temp:
            p = pathlib.Path(temp)/'graph.jsonl'
            lines = [
                dict(role='training_target', target_provider='NOAA_GHCNh', target_station_id='A',
                     candidate_neighbors=[
                         dict(provider='NOAA_GHCNh',station_id='B',distance_km=15),
                         dict(provider='NOAA_GHCNh',station_id='C',distance_km=40)]),
                dict(role='spatial_holdout_target',target_provider='NOAA_GHCNh',target_station_id='B',
                     candidate_neighbors=[])
            ]
            p.write_text('\n'.join(map(json.dumps,lines)) + '\n')
            eligible = {name:({'elevation_m':'100'}, {y:4000 for y in (2022,2023,2024,2025)})
                        for name in ('A','B','C')}
            target, ns = choose_cluster(p,eligible)
            self.assertEqual(target,'A')
            self.assertEqual([n['station_id'] for n in ns],['B','C'])

if __name__ == '__main__':
    unittest.main()
