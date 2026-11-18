import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
from atmos_quality_policy import normalize, profile_audit

class QualityPolicyTests(unittest.TestCase):
    def test_units_and_separate_pressure_types(self):
        self.assertAlmostEqual(normalize('IEM_ASOS', 'tmpf', 68)[0], 20)
        self.assertAlmostEqual(normalize('ECCC', 'WIND_SPEED', 36)[0], 10)
        self.assertAlmostEqual(normalize('ECCC', 'STATION_PRESSURE', 100.3)[0], 1003)
        self.assertEqual(normalize('ECCC', 'STATION_PRESSURE', 100.3)[1], 'station_pressure_hpa')
        self.assertEqual(normalize('IEM_ASOS', 'mslp', 1013)[1], 'sea_level_pressure_hpa')
        self.assertAlmostEqual(normalize('IEM_ASOS', 'sknt', 10)[0], 5.14444)
        self.assertAlmostEqual(normalize('IEM_ASOS', 'p01i', '0.50')[0], 12.7)
        self.assertAlmostEqual(normalize('ECCC', 'WIND_DIRECTION', 27)[0], 270)

    def test_missing_flags_and_noaa_source_context(self):
        self.assertEqual(normalize('IEM_ASOS', 'p01i', 'T')[2], 'trace_not_numeric')
        self.assertEqual(normalize('IEM_ASOS', 'tmpf', 'M')[2], 'missing')
        self.assertEqual(normalize('IEM_ASOS', 'tmpf', '500')[2], 'outside_plausibility_bounds')
        self.assertEqual(normalize('ECCC', 'TEMP', 20, 'E')[2], 'source_flag_uninterpreted')
        self.assertEqual(normalize('NOAA_GHCNh', 'temperature', 20, '1', '335')[0], 20)
        self.assertEqual(normalize('NOAA_GHCNh', 'temperature', 20, '2', '335')[0], None)
        self.assertEqual(normalize('NOAA_GHCNh', 'temperature', 20, '1', 'unknown')[0], None)
        self.assertEqual(normalize('NOAA_GHCNh', 'wind_speed', 10, '0', '345')[0], 10)
        self.assertEqual(normalize('NOAA_GHCNh', 'wind_speed', 10, '1', '345')[0], None)
        self.assertEqual(normalize('NOAA_GHCNh', 'temperature', 20, '1', None)[0], None)

    def test_aggregate_profile_does_not_certify(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'coverage.jsonl'
            path.write_text(json.dumps(dict(provider='ECCC', variables={'TEMP': {
                'nonmissing_records': 5, 'observed_hours': 4,
                'source_quality_flags': {'M': 2}}})) + '\n')
            report = profile_audit(path)
            self.assertEqual(report['source_periods_read'], 1)
            self.assertEqual(report['source_flags'][0]['source_record_count'], 2)
            self.assertFalse(report['quality_approved'])

if __name__ == '__main__':
    unittest.main()
