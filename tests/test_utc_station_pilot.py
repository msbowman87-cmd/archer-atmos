import unittest
from datetime import date
from atmos.utc_station_pilot import utc_observations

class UtcStationTests(unittest.TestCase):
    def test_utc_coverage_and_conversion(self):
        header="station,valid,tmpf\n"
        rows="".join("TWF,2026-09-01 %02d:30:00,%s\n"%(h,68+h) for h in range(20))
        result=utc_observations("TWF","ID_ASOS",date(2026,9,1),date(2026,9,1),
            fetch=lambda url:header+rows)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]["utc_hours_covered"],"20")
        self.assertEqual(result[0]["observed_precip_mm"],"")
        self.assertAlmostEqual(float(result[0]["observed_temp_max_c"]),(87-32)*5/9)
    def test_reject_incomplete_day(self):
        result=utc_observations("TWF","ID_ASOS",date(2026,9,1),date(2026,9,1),
            fetch=lambda url:"station,valid,tmpf\nTWF,2026-09-01 12:00:00,80\n")
        self.assertEqual(result,[])
    def test_utc_boundary(self):
        data="station,valid,tmpf\nTWF,2026-08-31 23:59:00,90\nTWF,2026-09-01 00:00:00,70\n"
        result=utc_observations("TWF","ID_ASOS",date(2026,9,1),date(2026,9,1),
            fetch=lambda url:data,min_hours=1)
        self.assertEqual(len(result),1)
        self.assertAlmostEqual(float(result[0]["observed_temp_max_c"]),(70-32)*5/9)
if __name__=="__main__":unittest.main()
