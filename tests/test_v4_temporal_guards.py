import unittest
from atmos.v4_temporal_guards import asof_sensor, chronological_split, reject_frozen_v2_for_chronological_claim

class TemporalGuardsTests(unittest.TestCase):
    def test_future_available_product_excluded(self):
        row=dict(observed_at_utc="2018-06-01T12:00:00Z",available_at_utc="2018-06-01T12:20:00Z",availability_provenance="VERIFIED_ARCHIVE")
        self.assertFalse(asof_sensor(row,"2018-06-01T12:10:00Z"))
        self.assertTrue(asof_sensor(row,"2018-06-01T12:30:00Z"))
    def test_assumed_lag_not_certified(self):
        row=dict(observed_at_utc="2018-06-01T12:00:00Z",available_at_utc="2018-06-01T12:15:00Z",availability_provenance="ASSUMED_15_MIN")
        with self.assertRaisesRegex(ValueError,"Unverified"):
            asof_sensor(row,"2018-06-01T13:00:00Z")
    def test_training_future_label_rejected(self):
        train=[dict(issue_at_utc="2018-05-01T00:00:00Z",target_at_utc="2018-06-02T00:00:00Z")]
        test=[dict(issue_at_utc="2018-06-01T00:00:00Z",target_at_utc="2018-06-02T00:00:00Z")]
        with self.assertRaisesRegex(ValueError,"Temporal leakage"):
            chronological_split(train,test)
    def test_prior_training_accepted(self):
        train=[dict(issue_at_utc="2018-01-01T00:00:00Z",target_at_utc="2018-01-04T00:00:00Z")]
        test=[dict(issue_at_utc="2018-06-01T00:00:00Z",target_at_utc="2018-06-02T00:00:00Z")]
        self.assertTrue(chronological_split(train,test))
    def test_v2_future_training_rejected(self):
        with self.assertRaisesRegex(ValueError,"refit"):
            reject_frozen_v2_for_chronological_claim("2025-12-31T00:00:00Z","2018-02-04T00:00:00Z")
    def test_naive_time_rejected(self):
        with self.assertRaisesRegex(ValueError,"Naive"):
            asof_sensor(dict(observed_at_utc="2018-01-01T00:00:00",available_at_utc="2018-01-01T01:00:00Z",availability_provenance="VERIFIED"),"2018-01-02T00:00:00Z")
if __name__ == "__main__":
    unittest.main()
