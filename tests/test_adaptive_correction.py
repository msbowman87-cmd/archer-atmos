import unittest
from datetime import date,timedelta
from atmos.adaptive_correction import evaluate

class AdaptiveCorrectionTests(unittest.TestCase):
    def dataset(self,training_bias=2,validation_bias=2,test_bias=2):
        fc=[];obs=[]
        start=date(2026,1,1)
        for i in range(90):
            day=start+timedelta(days=i)
            phase=training_bias if i<30 else validation_bias if i<60 else test_bias
            key=day.isoformat()
            fc.append({"station_id":"X","date":key,"issue_date":(day-timedelta(days=2)).isoformat(),"forecast_temp_max_c":str(20+phase)})
            obs.append({"station_id":"X","date":key,"observed_temp_max_c":"20"})
        return fc,obs
    def test_improvement_on_held_out_data(self):
        f,o=self.dataset()
        r=evaluate(f,o,"2026-01-31","2026-03-02")["results"]["X/1-7"]
        self.assertTrue(r["enabled_on_validation"])
        self.assertAlmostEqual(r["test_adaptive_mae_c"],0)
    def test_reject_harmful_correction(self):
        f,o=self.dataset(validation_bias=-2,test_bias=-2)
        r=evaluate(f,o,"2026-01-31","2026-03-02")["results"]["X/1-7"]
        self.assertFalse(r["enabled_on_validation"])
        self.assertEqual(r["test_adaptive_mae_c"],r["test_raw_mae_c"])
    def test_insufficient_data(self):
        f,o=self.dataset()
        r=evaluate(f,o,"2026-01-31","2026-03-02",min_train=100)["results"]["X/1-7"]
        self.assertEqual(r["status"],"insufficient_data")
    def test_invalid_splits(self):
        with self.assertRaises(ValueError):evaluate([],[],"2026-03-01","2026-02-01")
if __name__=="__main__":unittest.main()
