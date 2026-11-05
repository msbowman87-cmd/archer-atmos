import importlib.util
import pathlib
import unittest

p=pathlib.Path(__file__).resolve().parents[1]/"scripts"/"select_multi_provider_stations.py"
spec=importlib.util.spec_from_file_location("station_selection",p)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def station(country="US",lat=40.0,lon=-110.0,elev=1200,months=100,provider="NOAA",station_id="X"):
    return dict(provider=provider,station_id=station_id,country=country,latitude=str(lat),longitude=str(lon),elevation_m=str(elev),months_500plus=str(months),observations_2016_2025="50000",name="Sample")

class SelectionTests(unittest.TestCase):
    def test_accept_valid_station(self):self.assertIsNotNone(m.parse(station()))
    def test_reject_missing_elevation(self):self.assertIsNone(m.parse(station(elev="-999.9")))
    def test_reject_nan_elevation(self):self.assertIsNone(m.parse(station(elev="nan")))
    def test_reject_missing_coordinates(self):self.assertIsNone(m.parse(station(lat="")))
    def test_reject_low_coverage(self):self.assertIsNone(m.parse(station(months=12)))
    def test_caribbean_eligible(self):self.assertIsNotNone(m.parse(station(country="JM")))
    def test_dedup_colocated(self):
        a=m.parse(station(station_id="A"))
        b=m.parse(station(station_id="B",provider="ECCC"))
        self.assertEqual(len(m.dedup([a,b])),1)
    def test_spread(self):
        a=m.parse(station(station_id="A"))
        b=m.parse(station(station_id="B",lat=42,lon=-112))
        self.assertEqual(len(m.spread([a,b],2)),2)
if __name__=="__main__":unittest.main()
