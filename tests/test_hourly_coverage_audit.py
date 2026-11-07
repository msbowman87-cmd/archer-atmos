import pathlib,sys,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from audit_hourly_coverage import audit_file
class AuditTests(unittest.TestCase):
    def test_subhourly_not_double_counted_and_flags_retained(self):
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)/'data.psv';p.write_text('DATE|temperature|temperature_Quality_Code|wind_speed\n2016-01-01T00:10:00|1|1|-9999\n2016-01-01T00:50:00|2|2|3\n2016-01-01T01:00:00|-9999||4\n')
            r=audit_file(p,'NOAA_GHCNh','2016');self.assertEqual(r['expected_hours'],8784);self.assertEqual(r['variables']['temperature']['observed_hours'],1);self.assertEqual(r['variables']['temperature']['nonmissing_records'],2);self.assertEqual(r['variables']['temperature']['source_quality_flags'],{'1':1,'2':1});self.assertEqual(r['variables']['wind_speed']['observed_hours'],2)
    def test_reject_wrong_period(self):
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)/'data.csv';p.write_text('station,valid,tmpf\nTEST,2017-01-01 00:00,1\n')
            with self.assertRaises(ValueError):audit_file(p,'IEM_ASOS','2016-01')
if __name__=='__main__':unittest.main()
