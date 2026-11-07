import unittest

from atmos.temporal_provenance import (
    match_truth, predictor_allowed, validate_forecast, validate_observation,
)

F = dict(source_kind="issued_forecast", source_id="gfs-cycle", model="gfs",
         issue_time_utc="2020-01-01T00:00:00Z",
         valid_start_utc="2020-01-01T01:00:00Z",
         valid_end_utc="2020-01-01T02:00:00Z",
         location_id="station-1", metric="temperature", unit="C")
O = dict(independent=True, quality_flag="verified", source_id="station-record",
         published_at_utc="2020-01-01T03:00:00Z",
         valid_start_utc=F["valid_start_utc"], valid_end_utc=F["valid_end_utc"],
         location_id="station-1", metric="temperature", unit="C")


class TemporalProvenanceTests(unittest.TestCase):
    def test_valid_truth_is_target_only(self):
        self.assertTrue(match_truth(F, O))
        with self.assertRaisesRegex(ValueError, "Missing timestamp"):
            predictor_allowed(F, {"source_id": "station-record"})

    def test_future_predictor_rejected(self):
        with self.assertRaisesRegex(ValueError, "Future information leakage"):
            predictor_allowed(F, {"source_id": "future", "available_at_utc": "2020-01-01T00:01:00Z"})

    def test_historical_predictor_allowed(self):
        self.assertTrue(predictor_allowed(F, {"source_id": "prior", "available_at_utc": "2019-12-31T23:00:00Z"}))

    def test_naive_time_rejected(self):
        with self.assertRaisesRegex(ValueError, "Timezone-naive"):
            validate_forecast({**F, "issue_time_utc": "2020-01-01T00:00:00"})

    def test_reanalysis_rejected(self):
        with self.assertRaisesRegex(ValueError, "genuine issued"):
            validate_forecast({**F, "source_kind": "reanalysis"})

    def test_unknown_observation_publication_rejected(self):
        with self.assertRaisesRegex(ValueError, "Missing timestamp"):
            validate_observation({k:v for k,v in O.items() if k != "published_at_utc"})

    def test_unverified_observation_rejected(self):
        with self.assertRaisesRegex(ValueError, "quality unverified"):
            validate_observation({**O, "quality_flag": "estimated"})

    def test_wrong_interval_rejected(self):
        with self.assertRaisesRegex(ValueError, "mismatch"):
            match_truth(F, {**O, "location_id": "station-2"})


if __name__ == "__main__":
    unittest.main()
