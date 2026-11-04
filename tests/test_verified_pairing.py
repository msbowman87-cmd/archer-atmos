import unittest
from datetime import datetime,timedelta,timezone
from atmos.verified_pairing import build

UTC=timezone.utc
def stamp(d):
    return d.isoformat()

def data(n=5):
    start=datetime(2024,1,1,tzinfo=UTC)
    forecasts=[];observations=[];availability=[]
    for day in range(n):
        hour=start+timedelta(days=day,hours=12)
        observed=hour+timedelta(minutes=7)
        issue=hour-timedelta(hours=6)
        forecasts.append({"station_id":"site123","model":"gfs",
            "issue_at_utc":stamp(issue),"valid_hour_utc":stamp(hour),
            "metric":"temp_2m","unit":"C","value":"12",
            "source_issue_verified":"true","source_issue_reference":"model-archive-cycle-id"})
        observations.append({"station_id":"site123","hour_utc":stamp(hour),
            "observed_at_utc":stamp(observed),"temperature_c":"10"})
        availability.append({"station_id":"site123","observed_at_utc":stamp(observed),
            "available_at_utc":stamp(observed+timedelta(hours=2)),
            "availability_verified":"true","verification_reference":"archived-available-since"})
    return forecasts,observations,availability

class VerifiedPairingTests(unittest.TestCase):
    def test_unknown_publication_time_blocks_training(self):
        f,o,a=data()
        r=build(f,o,[],minimum_history=1)
        self.assertEqual(r["status"],"blocked_no_verified_pairs")
        self.assertEqual(r["matched_verified_pairs"],0)
        self.assertEqual(r["rejection_reasons"]["no_verified_observation_availability"],5)

    def test_unverified_forecast_source_is_excluded(self):
        f,o,a=data()
        for row in f:row["source_issue_verified"]="false"
        r=build(f,o,a,minimum_history=1)
        self.assertEqual(r["status"],"blocked_no_verified_pairs")

    def test_declared_issue_after_measurement_is_excluded(self):
        f,o,a=data(1)
        f[0]["issue_at_utc"]=o[0]["observed_at_utc"]
        r=build(f,o,a,minimum_history=1)
        self.assertEqual(r["status"],"blocked_no_verified_pairs")
        self.assertEqual(r["rejection_reasons"]["forecast_issued_after_measurement"],1)

    def test_available_before_measured_is_rejected(self):
        f,o,a=data(1)
        a[0]["available_at_utc"]="2023-01-01T00:00:00+00:00"
        r=build(f,o,a,minimum_history=1)
        self.assertEqual(r["status"],"blocked_no_verified_pairs")
        self.assertEqual(r["rejection_reasons"]["publication_before_observation"],1)

    def test_three_day_chronological_walk_forward_with_provenance(self):
        f,o,a=data(7)
        r=build(f,o,a,minimum_history=2,holdout_start="2024-01-03T00:00:00Z")
        self.assertEqual(r["status"],"exploratory_scored")
        self.assertEqual(r["matched_verified_pairs"],7)
        self.assertGreater(r["trained_holdout_cases"],0)
        self.assertEqual(r["raw_mae"],2)
        self.assertEqual(r["corrected_mae"],0)

    def test_exact_hour_matching_tolerance(self):
        f,o,a=data(1)
        o[0]["observed_at_utc"]="2024-01-01T12:40:00+00:00"
        with self.assertRaises(ValueError):
            build(f,o,a)

    def test_qc_rejected_measurements_do_not_train(self):
        f,o,a=data(1);o[0]["temperature_c"]=""
        r=build(f,o,a)
        self.assertEqual(r["status"],"blocked_no_verified_pairs")
        self.assertEqual(r["rejection_reasons"]["unusable_observation_metric"],1)

if __name__=="__main__":unittest.main()
