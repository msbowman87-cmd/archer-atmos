import importlib.util
import pathlib
import unittest

p=pathlib.Path(__file__).resolve().parents[1]/"scripts"/"select_multi_provider_stations.py"
spec=importlib.util.spec_from_file_location("station_selection",p)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def station(country="US",lat=40.0,lon=-110.0,elev=1200,months=100,provider="NOAA",station_id="X"):
    return dict(provider=provider,station_id=station_id,country=country,latitude=str(lat),longitude=str(lon),elevation_m=str(elev),months_500plus=str(months),observations_2016_2025="50000",name="Sample",history_start="2016-01-01",history_end="2025-12-31",coverage_basis="monthly_record_counts",source_url="https://example.org/inventory",history_url="https://example.org/history",license="Test fixture only",canonical_id="")

class SelectionTests(unittest.TestCase):
    def test_accept_valid_station(self):self.assertIsNotNone(m.parse(station()))
    def test_reject_missing_elevation(self):self.assertIsNone(m.parse(station(elev="-999.9")))
    def test_reject_nan_elevation(self):self.assertIsNone(m.parse(station(elev="nan")))
    def test_reject_missing_coordinates(self):self.assertIsNone(m.parse(station(lat="")))
    def test_short_histories_remain_eligible(self):self.assertIsNotNone(m.parse(station(months=12)))
    def test_caribbean_eligible(self):self.assertIsNotNone(m.parse(station(country="JM")))
    def test_dedup_colocated(self):
        a=m.parse(station(station_id="A"))
        b=m.parse(station(station_id="B",provider="ECCC"))
        self.assertEqual(len(m.dedup([a,b])),1)
    def test_missing_provenance_rejected(self):
        r=station();r.pop("history_url");self.assertIsNone(m.parse(r))
    def test_negative_counts_rejected(self):
        r=station();r["observations_2016_2025"]="-1";self.assertIsNone(m.parse(r))
    def test_impossible_months_rejected(self):self.assertIsNone(m.parse(station(months=121)))
    def test_no_period_overlap_rejected(self):
        r=station();r["history_end"]="2015-12-31";self.assertIsNone(m.parse(r))
    def test_period_only_has_no_invented_counts(self):
        r=station();r.update(coverage_basis="hourly_archive_period_only",months_500plus="",observations_2016_2025="")
        parsed=m.parse(r);self.assertIsNotNone(parsed);self.assertIsNone(parsed["observations_2016_2025"])
    def test_dedup_boundary(self):
        a=m.parse(station(lat=40.000,station_id="A"));b=m.parse(station(lat=40.003,station_id="B"))
        self.assertEqual(len(m.dedup([a,b])),1)
    def test_dedup_high_latitude(self):
        a=m.parse(station(lat=80,lon=-100,station_id="A"));b=m.parse(station(lat=80,lon=-99.99,station_id="B"))
        self.assertEqual(len(m.dedup([a,b])),1)
    def test_dedup_dateline(self):
        a=m.parse(station(lon=179.999,station_id="A"));b=m.parse(station(lon=-179.999,station_id="B"))
        self.assertEqual(len(m.dedup([a,b])),1)
    def test_same_station_id_far_apart(self):
        a=m.parse(station());b=m.parse(station(lat=42))
        self.assertEqual(len(m.dedup([a,b])),1)
    def test_distinct_station_ids_far_apart(self):
        a=m.parse(station(station_id="A"));b=m.parse(station(lat=42,station_id="B"))
        self.assertEqual(len(m.dedup([a,b])),2)
    def test_spread(self):
        a=m.parse(station(station_id="A"))
        b=m.parse(station(station_id="B",lat=42,lon=-112))
        self.assertEqual(len(m.spread([a,b],2)),2)
if __name__=="__main__":unittest.main()
