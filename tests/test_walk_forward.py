import unittest
from datetime import datetime,timedelta,timezone
from atmos.walk_forward import evaluate

def fixtures(n=35):
    start=datetime(2025,1,1,tzinfo=timezone.utc);pred=[];truth=[]
    for i in range(n):
        issue=start+timedelta(days=i);valid=issue+timedelta(days=1);end=valid+timedelta(days=1)
        pred.append(dict(location_id='site'+str(i%4),model='gfs',issue_at_utc=issue.isoformat(),valid_start_utc=valid.isoformat(),valid_end_utc=end.isoformat(),metric='temp_max',unit='C',value='14'))
        truth.append(dict(location_id='site'+str(i%4),available_at_utc=(end+timedelta(hours=12)).isoformat(),valid_start_utc=valid.isoformat(),valid_end_utc=end.isoformat(),metric='temp_max',unit='C',value='12',independent='true',quality_flag='verified'))
    return pred,truth

class WalkForward(unittest.TestCase):
    def test_late_truth_never_enters_prior_issue(self):
        p,o=fixtures()
        r=evaluate(p,o,minimum_history=3)
        self.assertEqual(r['rows'][3]['training_cases'],1)
        self.assertEqual(r['rows'][5]['training_cases'],3)
        self.assertEqual(r['rows'][5]['correction'],-2)
        self.assertGreater(r['relative_mae_change_pct'],90)
    def test_late_released_measurement(self):
        p,o=fixtures()
        o[0]['available_at_utc']='2026-01-01T00:00:00Z'
        r=evaluate(p,o,minimum_history=3)
        self.assertEqual(r['rows'][5]['training_cases'],2)
    def test_ineligible_records_do_not_train(self):
        p,o=fixtures()
        for item in o:item['independent']='false'
        r=evaluate(p,o)
        self.assertEqual(r['status'],'insufficient_verified_training_data')
    def test_chronological_holdout(self):
        p,o=fixtures()
        r=evaluate(p,o,minimum_history=3,holdout_start='2025-01-25T00:00:00Z')
        self.assertEqual(r['holdout_cases'],11)
    def test_duplicate_rejected(self):
        p,o=fixtures()
        with self.assertRaises(ValueError):evaluate(p+[dict(p[0])],o)
    def test_no_real_pairs_is_not_success(self):
        self.assertEqual(evaluate([],[])['status'],'insufficient_verified_training_data')
