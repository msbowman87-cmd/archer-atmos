import unittest
from datetime import date,timedelta
from unittest.mock import patch
from atmos.regional_backtest import evaluate,main
import tempfile,json,sys
from pathlib import Path

class RegionalTests(unittest.TestCase):
    def test_main_uses_same_utc_window_for_station_and_forecast(self):
        with tempfile.TemporaryDirectory() as tmp:
            argv=['regional_backtest','--start','2026-08-01','--end','2026-09-30','--output',tmp]
            fake_rows=[];fake_obs=[]
            for i in range(61):
                d=(date(2026,8,1)+timedelta(days=i)).isoformat()
                fake_rows.append(dict(date=d,lead=1,baseline=20.,regional_anomaly=2.))
                fake_obs.append(dict(date=d,observed_temp_max_c='22'))
            with patch.object(sys,'argv',argv), patch('atmos.regional_backtest.utc_observations',return_value=fake_obs) as observed, patch('atmos.regional_backtest.regional_rows',return_value=(fake_rows,[])) as forecasts:
                main()
            self.assertEqual(forecasts.call_args.args[2],'UTC')
            self.assertEqual(observed.call_args.kwargs['min_hours'],20)
            report=json.loads((Path(tmp)/'report.json').read_text())
            self.assertEqual(report['comparison_timezone'],'UTC')
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
        self.assertEqual(result['promotion_gate'],'pass_exploratory_only')
        self.assertTrue(all(h['improved'] for h in result['validation_halves']))
    def test_does_not_train_on_september(self):
        rows=[];obs=[]
        start=date(2026,8,1)
        for i in range(61):
            d=(start+timedelta(days=i)).isoformat()
            rows.append(dict(date=d,lead=1,baseline=20.,regional_anomaly=2.))
            obs.append(dict(date=d,observed_temp_max_c='22' if i<31 else '18'))
        result=evaluate(rows,obs)['by_lead_days']['1-7']
        self.assertLess(result['improvement_pct'],0)
        self.assertEqual(result['promotion_gate'],'reject')
    def test_rejects_when_one_validation_half_regresses(self):
        rows=[];obs=[]
        start=date(2026,8,1)
        for i in range(61):
            d=(start+timedelta(days=i)).isoformat()
            rows.append(dict(date=d,lead=1,baseline=20.,regional_anomaly=2.))
            # Training favors a positive correction. First test half benefits
            # greatly; second half gets worse despite positive overall skill.
            actual=22 if i<46 else 20.5
            obs.append(dict(date=d,observed_temp_max_c=str(actual)))
        result=evaluate(rows,obs)['by_lead_days']['1-7']
        self.assertGreater(result['improvement_pct'],2)
        self.assertFalse(result['validation_halves'][1]['improved'])
        self.assertEqual(result['promotion_gate'],'reject')
