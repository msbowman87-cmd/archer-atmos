import unittest
from atmos.collector import point,subset,url_for,collect
class TestCollector(unittest.TestCase):
    def test_date_line(self):
        self.assertEqual(point(0,180),(0,-180))
        self.assertTrue(subset(0,180)["rightlon"]<=180)
    def test_poles(self):
        self.assertEqual(subset(90,0)["toplat"],90)
        self.assertEqual(subset(-90,0)["bottomlat"],-90)
    def test_invalid_coordinates(self):
        for a,b in [(91,0),(0,181),(float("nan"),0)]:
            with self.assertRaises(ValueError):point(a,b)
    def test_url(self):
        self.assertIn("f024",url_for("20261030","00",24,42.563,-114.46))
    def test_budget_before_network(self):
        with self.assertRaises(ValueError):
            collect([{"lat":0,"lon":0}]*7,"20261030","00",[24,27],"/tmp/unused",12)
