import unittest
from datetime import date,timedelta
from atmos.regional_backtest import evaluate

class RegionalTests(unittest.TestCase):
    def test_regional_improvement_on_unseen_month(self):
        rows=[]; obs=[]
        start=date(2026,8,1)
        for i in range(61):
            d=(start+timedelta(days=i)).isoformat()
            rows.append(dict(date=d,issue_date=(start+timedelta(days=i-1)).isoformat(),
                             lead=1,baseline=20.,regional_anomaly=2.))
            obs.append(dict(date=d,observed_temp_max_c='22'))
        result=evaluate(rows,obs)['by_lead_days']['1-7']
        self.assertGreater(result['improvement_pct'],0)
        self.assertEqual(result['test_unique_days'],30)
    def test_does_not_train_on_september(self):
        rows=[];obs=[]
        start=date(2026,8,1)
        for i in range(61):
            d=(start+timedelta(days=i)).isoformat()
            rows.append(dict(date=d,lead=1,baseline=20.,regional_anomaly=2.))
            obs.append(dict(date=d,observed_temp_max_c='22' if i<31 else '18'))
        result=evaluate(rows,obs)['by_lead_days']['1-7']
        self.assertLess(result['improvement_pct'],0)
