import unittest
from atmos.global_validation import evaluate, lead_bucket, manifest


class GlobalValidationTests(unittest.TestCase):
    def case(self):
        f = dict(location_id='P001', issue_date='2026-08-01', date='2026-08-03',
                 metric='temp_max', unit='C', valid_start_utc='2026-08-03T00:00:00Z',
                 valid_end_utc='2026-08-04T00:00:00Z')
        o = dict(location_id='P001', date='2026-08-03', metric='temp_max',unit='C',
                 valid_start_utc=f['valid_start_utc'],valid_end_utc=f['valid_end_utc'],
                 value='20', independent='true',quality_flag='verified')
        return [dict(f,model='gfs',value='22'),dict(f,model='ecmwf',value='19')],[o]

    def test_global_coordinates_across_hemispheres(self):
        points=manifest()
        self.assertEqual(len(points),200)
        self.assertEqual(len({(p['lat'],p['lon']) for p in points}),200)
        self.assertEqual({p['hemisphere'] for p in points},{'north','south'})
        self.assertEqual({p['latitude_zone'] for p in points},{'polar','midlatitude','tropical'})
        self.assertTrue(all(p['observation_status']=='unverified' for p in points))

    def test_horizons(self):
        self.assertEqual(lead_bucket('2026-08-01','2026-08-02'),'1-3')
        self.assertEqual(lead_bucket('2026-08-01','2026-08-08'),'4-7')
        self.assertEqual(lead_bucket('2026-08-01','2026-08-15'),'8-14')
        self.assertEqual(lead_bucket('2026-08-01','2026-08-31'),'15-30')

    def test_exact_paired_comparison(self):
        f,o=self.case()
        result=evaluate(f,o)
        self.assertEqual(result['model_and_truth_paired_cases'],1)
        score=next(s for s in result['scores'] if s['dimension']=='global')
        self.assertEqual(score['gfs_mae'],2)
        self.assertEqual(score['ecmwf_mae'],1)
        self.assertEqual(score['equal_blend_mae'],.5)

    def test_non_independent_truth_is_rejected(self):
        f,o=self.case()
        o[0]['independent']='false'
        self.assertEqual(evaluate(f,o)['status'],'no_independent_pairs')

    def test_time_or_unit_mismatch_is_not_scored(self):
        f,o=self.case()
        o[0]['valid_start_utc']='2026-08-03T01:00:00Z'
        self.assertEqual(evaluate(f,o)['model_and_truth_paired_cases'],0)
        o[0]['valid_start_utc']=f[0]['valid_start_utc']
        o[0]['unit']='F'
        self.assertEqual(evaluate(f,o)['model_and_truth_paired_cases'],0)

    def test_missing_model_is_not_paired(self):
        f,o=self.case()
        self.assertEqual(evaluate(f[:1],o)['model_and_truth_paired_cases'],0)

    def test_duplicate_forecast_rejected(self):
        f,o=self.case()
        with self.assertRaises(ValueError):evaluate(f+[f[0]],o)


if __name__=='__main__':unittest.main()
