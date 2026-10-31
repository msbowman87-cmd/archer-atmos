import unittest
from atmos.independent_validation import evaluate

class IndependentValidationTests(unittest.TestCase):
    def test_lead_buckets_and_missing_observations(self):
        forecasts=[
            {'station_id':'A','date':'2026-10-10','issue_date':'2026-10-09','forecast_temp_max_c':'20','forecast_precip_mm':'4'},
            {'station_id':'A','date':'2026-10-10','issue_date':'2026-09-25','forecast_temp_max_c':'18','forecast_precip_mm':'2'},
            {'station_id':'B','date':'2026-10-10','issue_date':'2026-10-09','forecast_temp_max_c':'0','forecast_precip_mm':'0'}]
        observations=[{'station_id':'A','date':'2026-10-10','observed_temp_max_c':'19','observed_precip_mm':'3'}]
        result=evaluate(forecasts,observations)
        self.assertEqual(result['unmatched_rows'],1)
        self.assertEqual(result['by_lead_days']['1-7']['temperature_mae_c'],1)
        self.assertEqual(result['by_lead_days']['15-30']['precipitation_mae_mm'],1)
    def test_invalid_issue_date(self):
        with self.assertRaises(ValueError):
            evaluate([{'station_id':'A','date':'2026-10-10','issue_date':'2026-10-10'}],[])
    def test_duplicate_observations(self):
        row={'station_id':'A','date':'2026-10-10'}
        with self.assertRaises(ValueError):
            evaluate([],[row,row])
if __name__=='__main__':
    unittest.main()
