import unittest
from atmos.verify import metrics, paired_improvement
class TestVerification(unittest.TestCase):
    def row(self,p,o):
        return dict(issue_time="2026-10-30T00:00Z",valid_time="2026-10-31T00:00Z",
                    horizon_hours=24,predicted_temp_c=10,observed_temp_c=12,
                    predicted_rain_mm=p,observed_rain_mm=o)
    def test_heavy_rain_misses_not_hidden(self):
        result=metrics([self.row(0,30),self.row(25,28),self.row(3,0)])["24"]
        self.assertEqual(result["heavy_hits"],1)
        self.assertEqual(result["heavy_misses"],1)
        self.assertEqual(result["heavy_recall"],.5)
        self.assertEqual(result["temp_c_mae"],2)
    def test_no_future_leakage(self):
        row=self.row(0,0);row["issue_time"]=row["valid_time"]
        with self.assertRaises(ValueError):metrics([row])
    def test_paired_skill(self):
        self.assertEqual(paired_improvement([10,10],[11,12],[12,12]),1.5)
    def test_no_observed_heavy_rain(self):
        self.assertIsNone(metrics([self.row(0,0)])["24"]["heavy_recall"])
