import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
from station_training_readiness import summarize

class StationTrainingReadinessTests(unittest.TestCase):
    def test_train_years_are_independent_of_validation_and_test(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            manifest = root / 'stations.csv'
            manifest.write_text('provider,station_id,country\nECCC,A,Canada\nECCC,B,Canada\n')
            audit = root / 'coverage_batches.jsonl'
            records = []
            for station, year, hours in [('A', 2017, 200), ('A', 2018, 200),
                                         ('A', 2024, 200), ('A', 2025, 200),
                                         ('B', 2024, 200), ('B', 2025, 200)]:
                records.append(dict(provider='ECCC', station_id=station, period=str(year), expected_hours=300,
                                    variables={'TEMP': {'observed_hours': hours, 'source_quality_flags': {'M': 1}},
                                               'WIND_SPEED': {'observed_hours': 0, 'source_quality_flags': {}}}))
            audit.write_text('\n'.join(map(json.dumps, records)) + '\n')
            rows, summary = summarize(manifest, audit)
            self.assertEqual(summary['station_status']['coverage_candidate_qc_pending'], 1)
            self.assertEqual(summary['station_status']['insufficient_training_coverage'], 1)
            self.assertEqual(rows[0]['training_year_count'], 2)
            self.assertEqual(rows[0]['training_variables'], 'temperature')
            self.assertEqual(rows[0]['validation_2024_variables'], 'temperature')
            self.assertEqual(rows[1]['training_year_count'], 0)
            self.assertFalse(summary['quality_approved'])

    def test_dont_double_count_aliases_within_period(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            manifest = root / 'stations.csv'
            manifest.write_text('provider,station_id,country\nIEM_ASOS,A,USA\n')
            audit = root / 'coverage_batches.jsonl'
            records = [dict(provider='IEM_ASOS', station_id='A', period=str(y), expected_hours=100,
                            variables={'tmpf': {'observed_hours': 40}, 'temperature': {'observed_hours': 40}})
                       for y in [2016, 2017]]
            audit.write_text('\n'.join(map(json.dumps, records)) + '\n')
            rows, _ = summarize(manifest, audit)
            self.assertEqual(rows[0]['training_year_count'], 0)
if __name__ == '__main__':
    unittest.main()
