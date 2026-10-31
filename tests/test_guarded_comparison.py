import unittest
from datetime import date,timedelta
from atmos.paired_comparison import guarded_comparison

class GuardTests(unittest.TestCase):
    def make(self,training_bias,validation_bias,test_bias):
        forecasts=[]; observations=[]
        start=date(2026,8,1)
        for i in range(61):
            d=(start+timedelta(days=i)).isoformat()
            bias=training_bias if i<15 else validation_bias if i<31 else test_bias
            forecasts.append(dict(station_id="TWF",date=d,issue_date=(start+timedelta(days=i-1)).isoformat(),forecast_temp_max_c=str(20+bias)))
            observations.append(dict(station_id="TWF",date=d,observed_temp_max_c="20"))
        return forecasts,observations
    def test_rejects_validation_regression(self):
        f,o=self.make(3,-3,3)
        r=guarded_comparison(f,o,"2026-09-01")["by_lead_days"]["1-7"]
        self.assertEqual(r["correction_weight"],0)
        self.assertEqual(r["test_improvement_pct"],0)
    def test_accepts_consistent_bias(self):
        f,o=self.make(3,3,3)
        r=guarded_comparison(f,o,"2026-09-01")["by_lead_days"]["1-7"]
        self.assertGreater(r["correction_weight"],0)
        self.assertGreater(r["test_improvement_pct"],0)
