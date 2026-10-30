import unittest
from datetime import date
from atmos.study_batch import locations,year_window
class StudyBatchTest(unittest.TestCase):
    def test_200_unique_locations(self):
        pts=list(locations())
        self.assertEqual(len(pts),200)
        self.assertEqual(len({(p["lat"],p["lon"]) for p in pts}),200)
        self.assertTrue(all(-90<=p["lat"]<=90 and -180<=p["lon"]<=180 for p in pts))
    def test_first_year(self):
        self.assertEqual(year_window(0),(date(2016,10,30),date(2017,10,29)))
    def test_last_year(self):
        self.assertEqual(year_window(9),(date(2025,10,30),date(2026,10,29)))
    def test_invalid_year(self):
        with self.assertRaises(ValueError):year_window(10)
