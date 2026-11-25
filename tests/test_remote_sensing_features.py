"""Temporal leakage tests for satellite and radar observation adapters."""
import csv
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from atmos.remote_sensing_features import (
    RemoteSensingRecord, RemoteSensingStore, SOURCE_FEATURES,
)

def at(hour):
    return datetime(2024, 5, 1, tzinfo=timezone.utc)+timedelta(hours=hour)

def record(station,source,observed,available,values):
    return RemoteSensingRecord(
        station_id=station,source=source,product_id=f"{source}-{observed}",
        observed_at_utc=at(observed),available_at_utc=at(available),values=values)

class RemoteSensingTests(unittest.TestCase):
    def test_available_not_observed_time_controls_forecast(self):
        radar=record("ABC","radar",1,2,{"rain_rate_mm_h":16.})
        s=RemoteSensingStore([radar])
        self.assertIsNone(s.latest("ABC","radar",at(1.5)))
        self.assertEqual(s.latest("ABC","radar",at(2)).values["rain_rate_mm_h"],16.)
        self.assertIsNone(s.latest("OTHER","radar",at(2)))
        self.assertIsNone(s.latest("ABC","radar",at(3.2)))

    def test_delayed_old_observation_cannot_replace_newer(self):
        old=record("ABC","satellite",1,2.4,{"cloud_fraction":0.4})
        recent=record("ABC","satellite",2,2.1,{"cloud_fraction":0.8})
        s=RemoteSensingStore([old,recent])
        self.assertEqual(s.latest("ABC","satellite",at(2.5)).values["cloud_fraction"],0.8)

    def test_missing_radar_is_not_zero_precipitation(self):
        s=RemoteSensingStore([record("ABC","satellite",2,2.1,{"cloud_fraction":0.0})])
        names,features=s.model_features("ABC",at(2.2))
        v=dict(zip(names,features))
        self.assertEqual(v["satellite_available"],1.)
        self.assertEqual(v["cloud_fraction_present"],1.)
        self.assertEqual(v["cloud_fraction"],0.)
        self.assertEqual(v["radar_available"],0.)
        self.assertEqual(v["rain_rate_mm_h_present"],0.)
        self.assertEqual(v["rain_rate_mm_h"],0.)

    def test_future_knowledge_does_not_change_past_features(self):
        initial=record("ABC","satellite",1,1.2,{"cloud_fraction":0.2})
        future=record("ABC","satellite",2,2.5,{"cloud_fraction":0.9})
        a=RemoteSensingStore([initial]).model_features("ABC",at(1.4))
        b=RemoteSensingStore([initial,future]).model_features("ABC",at(1.4))
        self.assertEqual(a,b)

    def test_rejects_naive_timestamps_and_invalid_ranges(self):
        with self.assertRaises(ValueError):
            record("ABC","radar",2,1,{"rain_rate_mm_h":1.})
        with self.assertRaises(ValueError):
            record("ABC","satellite",2,2,{"cloud_fraction":1.2})
        with self.assertRaises(ValueError):
            record("ABC","radar",1,2,{"rain_rate_mm_h":-1.})
        with self.assertRaises(ValueError):
            RemoteSensingRecord("ABC","radar","source",
                                datetime(2024,1,1),at(2),{"rain_rate_mm_h":3.})

    def test_csv_ingestion_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"remote.csv"
            columns=["station_id","source","product_id","observed_at_utc",
                     "available_at_utc","cloud_fraction","max_reflectivity_dbz"]
            with path.open("w",newline="") as f:
                w=csv.DictWriter(f,fieldnames=columns)
                w.writeheader()
                w.writerow({"station_id":"ABC","source":"satellite","product_id":"GOES16",
                            "observed_at_utc":at(1).isoformat(),
                            "available_at_utc":at(1.2).isoformat(),"cloud_fraction":"0.75"})
                w.writerow({"station_id":"ABC","source":"radar","product_id":"NEXRAD",
                            "observed_at_utc":at(1).isoformat(),
                            "available_at_utc":at(1.1).isoformat(),"max_reflectivity_dbz":"43"})
            s=RemoteSensingStore.from_csv(path)
            names,values=s.model_features("ABC",at(1.4))
            data=dict(zip(names,values))
            self.assertEqual(data["satellite_available"],1.)
            self.assertEqual(data["radar_available"],1.)
            self.assertEqual(data["cloud_fraction_present"],1.)
            self.assertEqual(data["max_reflectivity_dbz_present"],1.)

if __name__=="__main__":
    unittest.main()
