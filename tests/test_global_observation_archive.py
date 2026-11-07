import csv
import io
import unittest
from atmos.global_observation_archive import extract,select_hourly_observations

def record(at, temp="+0123,1"):
    return {"DATE":at,"TMP":temp,"DEW":"+0001,1","WND":"090,1,0020,1,1",
            "SLP":"10132,1","VIS":"016000,1,1,1","AA1":"01,0000,1,1"}

class ActualHourlySelectionTests(unittest.TestCase):
    def test_off_hour_keeps_true_timestamp_and_exact_raw_value(self):
        actual=record("2014-01-01T12:07:00")
        out=select_hourly_observations([actual],2014,"12345012345")
        self.assertEqual(len(out),1)
        self.assertEqual(out[0]["time_utc"],"2014-01-01T12:07:00")
        self.assertEqual(out[0]["hour_utc"],"2014-01-01T12:00:00")
        self.assertEqual(out[0]["offset_minutes"],7)
        self.assertEqual(out[0]["temperature_raw"],"+0123,1")

    def test_exact_observation_preferred_over_off_hour(self):
        rows=[record("2014-01-01T11:58:00"),record("2014-01-01T12:00:00"),
              record("2014-01-01T12:14:00")]
        out=select_hourly_observations(rows,2014,"code")
        self.assertEqual(len(out),1)
        self.assertEqual(out[0]["time_utc"],"2014-01-01T12:00:00")

    def test_nearest_before_hour_and_stable_order(self):
        rows=[record("2014-01-01T12:09:00"),record("2014-01-01T11:53:00")]
        for source in [rows,list(reversed(rows))]:
            out=select_hourly_observations(source,2014,"code")
            self.assertEqual(out[0]["time_utc"],"2014-01-01T11:53:00")
            self.assertEqual(out[0]["offset_minutes"],-7)

    def test_no_synthetic_hours_or_interpolated_values(self):
        rows=[record("2014-01-01T12:01:00"),record("2014-01-01T15:52:00")]
        out=select_hourly_observations(rows,2014,"code")
        self.assertEqual([x["hour_utc"] for x in out],
                         ["2014-01-01T12:00:00","2014-01-01T16:00:00"])
        self.assertEqual(len(out),2)

    def test_exact_mode_excludes_off_hour(self):
        rows=[record("2014-01-01T11:59:00"),record("2014-01-01T12:00:00")]
        out=select_hourly_observations(rows,2014,"code","exact")
        self.assertEqual(len(out),1)
        self.assertEqual(out[0]["offset_minutes"],0)

    def test_half_hour_ties_to_earlier_hour(self):
        out=select_hourly_observations([record("2014-06-01T12:30:00")],2014,"code")
        self.assertEqual(out[0]["hour_utc"],"2014-06-01T12:00:00")
        self.assertEqual(out[0]["offset_minutes"],30)

    def test_year_boundary_and_invalid_date(self):
        rows=[record("2015-01-01T00:01:00"),record("2014-12-31T23:50:00"),
              record("not-a-date")]
        out=select_hourly_observations(rows,2014,"code")
        self.assertEqual(out,[])

    def test_extract_from_csv_uses_nearest_hour(self):
        b=io.StringIO()
        w=csv.DictWriter(b,fieldnames=["DATE","TMP","DEW","WND","SLP","VIS","AA1"])
        w.writeheader();w.writerow(record("2020-09-15T07:43:00"))
        out=extract(b.getvalue().encode(),2020,"code")
        self.assertEqual(out[0]["time_utc"],"2020-09-15T07:43:00")
        self.assertEqual(out[0]["hour_utc"],"2020-09-15T08:00:00")

if __name__=="__main__":unittest.main()
