import unittest
from atmos.multimetric_validation import score

class MultiMetricValidationTests(unittest.TestCase):
    def setUp(self):
        self.fc=[{"station_id":"X","issue_date":"2026-09-01","date":"2026-09-03",
          "forecast_temp_max_c":"25","forecast_precip_mm":"2","forecast_wind_max_ms":"8",
          "forecast_humidity_pct":"60"}]
        self.obs=[{"station_id":"X","date":"2026-09-03",
          "observed_temp_max_c":"23","observed_precip_mm":"0",
          "observed_wind_max_ms":"10","observed_humidity_pct":"50"}]
    def test_alignment_required(self):
        with self.assertRaises(ValueError):score(self.fc,self.obs)
    def test_multiple_metrics_and_events(self):
        r=score(self.fc,self.obs,aligned_intervals=True)["by_lead_days"]["1-7"]
        self.assertEqual(r["temp_max_c"]["mae"],2)
        self.assertEqual(r["wind_max_ms"]["bias"],-2)
        self.assertEqual(r["humidity_pct"]["mae"],10)
        self.assertEqual(r["precip_event"]["false_alarms"],1)
        self.assertEqual(r["precip_event"]["hits"],0)
    def test_missing_fields_are_not_zeroes(self):
        r=score(self.fc,[{"station_id":"X","date":"2026-09-03",
          "observed_temp_max_c":"","observed_precip_mm":"0"}],aligned_intervals=True)
        self.assertNotIn("temp_max_c",r["by_lead_days"]["1-7"])
    def test_duplicates_rejected(self):
        with self.assertRaises(ValueError):score(self.fc*2,self.obs,aligned_intervals=True)
if __name__=="__main__":unittest.main()
