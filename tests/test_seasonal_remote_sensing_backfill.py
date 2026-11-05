"""Seasonal four-week collection: exclusions, elevation, temporal safety, coverage."""
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from atmos import seasonal_remote_sensing_backfill as seasonal
from atmos.historical_remote_sensing_pilot import CSV_FIELDS


class SeasonalArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.metadata=self.root/"stations.csv"
        self.elevations=self.root/"isd-history.csv"
        with self.metadata.open("w",newline="") as f:
            writer=csv.writer(f)
            writer.writerow(["station_id","lat","lon"])
            for n in seasonal.STATIONS:
                writer.writerow([n,43.2,-116.2])
        with self.elevations.open("w",newline="") as f:
            writer=csv.writer(f)
            writer.writerow(["USAF","WBAN","ELEV(M)"])
            for n in seasonal.STATIONS:
                writer.writerow([n[:6],n[6:],"1095.5"])

    def tearDown(self):
        self.temp.cleanup()

    def test_four_nonoverlapping_weeks_and_station_splits(self):
        self.assertEqual(len(seasonal.SEASON_STARTS),4)
        self.assertEqual(len(seasonal.STATIONS),6)
        self.assertEqual(sum(v[2]=="holdout" for v in seasonal.STATIONS.values()),2)
        from datetime import date
        starts=sorted(date.fromisoformat(s) for s in seasonal.SEASON_STARTS.values())
        self.assertTrue(all((b-a).days>=7 for a,b in zip(starts,starts[1:])))
        self.assertEqual(len(seasonal.SAMPLE_HOURS)*7*4,112)

    def test_source_elevations_audited_not_inferred(self):
        out=self.root/"audit.json"
        records=seasonal.station_audit(self.metadata,self.elevations,out)
        self.assertEqual(len(records),6)
        self.assertTrue(all(r["elevation_verified"] for r in records))
        self.assertEqual({r["elevation_m"] for r in records},{1095.5})
        self.assertEqual(len([r for r in records if r["split"]=="holdout"]),2)

    def test_missing_elevation_keeps_null(self):
        out=self.root/"audit.json"
        result=seasonal.station_audit(self.metadata,None,out)
        self.assertTrue(all(r["elevation_m"] is None for r in result))

    def test_scan_rows_are_real_and_heldouts_never_in_training_set(self):
        def mock_extract(metadata,out,day,hour,stations):
            directory=Path(out)
            directory.mkdir(parents=True,exist_ok=True)
            with (directory/"station-sensing-pilot.csv").open("w",newline="") as f:
                writer=csv.DictWriter(f,fieldnames=CSV_FIELDS)
                writer.writeheader()
                for station in stations:
                    for source in ("satellite","radar"):
                        writer.writerow({
                            "station_id":station,"source":source,
                            "product_id":f"mock-{station}-{source}",
                            "observed_at_utc":f"{day}T{hour:02d}:00:00Z",
                            "available_at_utc":f"{day}T{hour:02d}:15:00Z",
                            "cloud_fraction":"0.5" if source=="satellite" else "",
                            "max_reflectivity_dbz":"20" if source=="radar" else "",
                        })
            (directory/"source-manifest.json").write_text(json.dumps({
                "downloaded_files":[{"source_uri":"test://not-actual-archive"}]}))
            return {}
        output=self.root/"output"
        with patch.object(seasonal,"extract",side_effect=mock_extract):
            report=seasonal.collect(self.metadata,output,"summer",days=1,
                                    hours=(0,6),elevation_catalog=self.elevations)
        self.assertEqual(report["station_issue_scenarios"],12)
        self.assertEqual(report["both_sensor_coverage"],1.)
        self.assertEqual(report["satellite_rows"],12)
        self.assertEqual(report["radar_rows"],12)
        self.assertFalse(report["historical_forecast_accuracy_measured"])
        self.assertEqual(len(report["training_stations"]),4)
        self.assertEqual(len(report["excluded_validation_stations"]),2)

    def test_fails_closed_when_no_sources(self):
        def missing(*args,**kwargs):
            raise RuntimeError("upstream archive missing")
        with patch.object(seasonal,"extract",side_effect=missing):
            with self.assertRaisesRegex(RuntimeError,"coverage below"):
                seasonal.collect(self.metadata,self.root/"missing","spring",
                                 days=1,hours=(18,),minimum_coverage=0.5)


if __name__=="__main__":
    unittest.main()
