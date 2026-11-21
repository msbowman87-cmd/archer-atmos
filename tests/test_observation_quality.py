import csv
import gzip
import io
import json
import tempfile
import unittest
from collections import Counter,defaultdict
from pathlib import Path

from atmos.observation_quality import (
    FIELDS, convert, humidity_percent, numeric_component,
    audited_year, run_shard,validate_time
)

def sample(hour="2024-01-01T12:00:00",real="2024-01-01T12:09:00",**mod):
    d={"station_id":"12345612345","time_utc":real,"hour_utc":hour,
       "offset_minutes":"9.0","temperature_raw":"+0200,1",
       "dewpoint_raw":"+0100,5","wind_raw":"270,1,N,0050,1",
       "pressure_raw":"10132,1","visibility_raw":"016000,1,N,1",
       "precip_aa1_raw":"01,0004,0,1"}
    d.update(mod)
    return d

class QualityTests(unittest.TestCase):
    def test_valid_values_and_derived_humidity(self):
        out=convert(sample(),defaultdict(Counter))
        self.assertEqual(out["temperature_c"],20)
        self.assertEqual(out["dewpoint_c"],10)
        self.assertEqual(out["wind_speed_mps"],5)
        self.assertEqual(out["wind_direction_deg"],270)
        self.assertEqual(out["sea_level_pressure_hpa"],1013.2)
        self.assertEqual(out["visibility_m"],16000)
        self.assertEqual(out["precip_1h_mm"],0.4)
        self.assertTrue(45<out["relative_humidity_pct"]<60)
        self.assertEqual(out["observed_at_utc"],"2024-01-01T12:09:00")
        self.assertEqual(out["hour_utc"],"2024-01-01T12:00:00")

    def test_missing_sentinels_and_suspect_flags_are_not_valid(self):
        out=convert(sample(temperature_raw="+9999,1",dewpoint_raw="+0100,2",
                           wind_raw="999,9,N,9999,9",pressure_raw="99999,9",
                           visibility_raw="999999,9,N,9",
                           precip_aa1_raw="01,9999,0,1"),defaultdict(Counter))
        for name in ("temperature_c","dewpoint_c","relative_humidity_pct",
                     "wind_speed_mps","wind_direction_deg",
                     "sea_level_pressure_hpa","visibility_m","precip_1h_mm"):
            self.assertEqual(out[name],"")

    def test_precip_not_hourly_is_not_converted_to_hourly(self):
        out=convert(sample(precip_aa1_raw="03,0200,0,1"),defaultdict(Counter))
        self.assertEqual(out["precip_1h_mm"],"")

    def test_dewpoint_physical_consistency(self):
        out=convert(sample(temperature_raw="+0100,1",dewpoint_raw="+0200,1"),
                    defaultdict(Counter))
        self.assertEqual(out["relative_humidity_pct"],"")
        out=convert(sample(temperature_raw="+0200,1",dewpoint_raw="+0203,1"),
                    defaultdict(Counter))
        self.assertEqual(out["relative_humidity_pct"],100)

    def test_time_checks_detect_mismatch(self):
        d=sample();t=validate_time(d,"12345612345",2024,None)
        self.assertEqual(t.hour,12)
        with self.assertRaises(ValueError):
            validate_time(sample(offset_minutes="0"),"12345612345",2024,None)
        with self.assertRaises(ValueError):
            validate_time(sample(real="2024-01-01T12:45:00",offset_minutes="45"),
                          "12345612345",2024,None)
        with self.assertRaises(ValueError):
            validate_time(sample(),"wrongstation",2024,None)
        with self.assertRaises(ValueError):
            validate_time(sample(),"12345612345",2024,t)

    def test_actual_hourly_gaps_and_calendar_coverage(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"2024_12345612345.csv.gz"
            with gzip.open(p,"wt",newline="") as f:
                w=csv.DictWriter(f,fieldnames=list(sample().keys()));w.writeheader()
                w.writerow(sample())
                w.writerow(sample(hour="2024-01-01T15:00:00",
                                  real="2024-01-01T14:50:00",offset_minutes="-10"))
            io_stream=io.StringIO()
            writer=csv.DictWriter(io_stream,fieldnames=FIELDS);writer.writeheader()
            a=audited_year(p,"12345612345",2024,writer)
            self.assertEqual(a["rows"],2)
            self.assertEqual(a["normalized_rows"],2)
            self.assertEqual(a["missing_interior_hours"],2)
            self.assertEqual(a["longest_interior_gap_hours"],2)
            self.assertEqual(a["expected_calendar_hours"],8784)
            self.assertEqual(a["off_hour_rows"],2)

    def test_end_to_end_shard_audit_reports_missing_years(self):
        with tempfile.TemporaryDirectory() as temp:
            src=Path(temp)/"raw";src.mkdir()
            dst=Path(temp)/"out"
            manifest={"stations":[{"id":"12345612345","country":"US","lat":41.5,"lon":-116.2}]}
            (src/"stations.json").write_text(json.dumps(manifest))
            years=[]
            for year in range(2006,2026):
                for i in range(25):
                    code="12345612345"
                    years.append({"station":code,"year":year,"status":"missing"})
            (src/"collection-status.json").write_text(json.dumps({"hourly_selection":"nearest","results":years}))
            r=run_shard(src,dst,0)
            self.assertEqual(r["missing_years"],500)
            self.assertEqual(r["row_count"],0)
            self.assertTrue((dst/"quality-report-00.json").exists())

if __name__=="__main__":unittest.main()
