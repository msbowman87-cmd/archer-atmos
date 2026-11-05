import importlib.util,pathlib,sys,unittest,tempfile,hashlib,json
from unittest.mock import patch,MagicMock
scripts=pathlib.Path(__file__).resolve().parents[1]/'scripts';sys.path.insert(0,str(scripts))
import collect_selected_hourly as c

class CollectionTests(unittest.TestCase):
    def station(self):return dict(provider='NOAA_GHCNh',station_id='US_TEST',history_start='2016-01-01',history_end='2025-12-31',license='fixture only')
    def data(self,sid='US_TEST',year=2016):return f'STATION|Year|DATE|temperature|temperature_Quality_Code\n{sid}|{year}|{year}-01-01T01:00:00|12|1\n'.encode()
    def test_html_rejected(self):
        with self.assertRaises(ValueError):c.audit_bytes(b'<html>error</html>',self.station(),'2016')
    def test_wrong_station_rejected(self):
        with self.assertRaises(ValueError):c.audit_bytes(self.data('wrong'),self.station(),'2016')
    def test_wrong_year_rejected(self):
        with self.assertRaises(ValueError):c.audit_bytes(self.data(year=2017),self.station(),'2016')
    def test_flags_preserved_in_audit(self):
        r=c.audit_bytes(self.data(),self.station(),'2016');self.assertEqual(r['source_quality_flag_counts'],{'temperature_Quality_Code:1':1})
    def test_no_observations_rejected(self):
        with self.assertRaises(ValueError):c.audit_bytes(b'STATION|Year|DATE|temperature\n',self.station(),'2016')
    def test_eccc_empty_rows_rejected(self):
        s=dict(self.station(),provider='ECCC')
        with self.assertRaises(ValueError):c.audit_bytes(b'"Date/Time (LST)","Temp (C)"\n"2016-01-01 01:00",""\n',s,'2016-01')
    def test_resume_hash_checked(self):
        with tempfile.TemporaryDirectory() as d:
            dest=pathlib.Path(d)/'NOAA_GHCNh/US_TEST/2016.psv';dest.parent.mkdir(parents=True);dest.write_bytes(self.data());meta=dest.with_suffix('.psv.json');meta.write_text(json.dumps(dict(url='https://example.org/data',status='complete',sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),manifest_sha256='test')))
            task=(self.station(),'2016','https://example.org/data','psv')
            with patch.object(c.urllib.request,'urlopen',side_effect=RuntimeError('fixture network blocked')) as mock:
                self.assertTrue(c.collect(task,pathlib.Path(d),'test')['resumed']);mock.assert_not_called()
                dest.write_bytes(b'corrupt');self.assertEqual(c.collect(task,pathlib.Path(d),'test')['status'],'blocked');mock.assert_called_once()
    def test_eccc_local_month_boundary_retained(self):
        s=dict(self.station(),provider='ECCC',station_id='10076')
        data=json.dumps(dict(type='FeatureCollection',numberMatched=1,features=[dict(properties=dict(STN_ID=10076,LOCAL_DATE='2016-01-31 23:00:00',UTC_DATE='2016-02-01T06:00:00',TEMP=-5,TEMP_FLAG='E'))])).encode()
        r=c.audit_bytes(data,s,'2016-01');self.assertEqual(r['records'],1);self.assertEqual(r['source_quality_flag_counts'],{'TEMP_FLAG:E':1})
    def test_eccc_truncation_rejected(self):
        s=dict(self.station(),provider='ECCC')
        data=json.dumps(dict(numberMatched=2,features=[dict(properties={})])).encode()
        with self.assertRaises(ValueError):c.audit_bytes(data,s,'2016-01')
    def test_transient_http_error_retried(self):
        import urllib.error
        error=urllib.error.HTTPError('https://example.org',429,'Too Many Requests',{'Retry-After':'0'},None)
        response=MagicMock();response.__enter__.return_value=response;response.read.return_value=b'raw';response.status=200;response.url='https://example.org'
        with patch.object(c.urllib.request,'urlopen',side_effect=[error,response]) as request,patch.object(c.time,'sleep'):
            data,status,url,attempts=c.fetch_raw('https://example.org','IEM_ASOS')
        self.assertEqual((data,status,attempts),(b'raw',200,2));self.assertEqual(request.call_count,2)
    def test_empty_period_not_transient(self):
        self.assertFalse(c.retryable_error('no ECCC observations returned'))
        self.assertTrue(c.retryable_error('IncompleteRead(100 bytes read)'))
    def test_no_tasks_outside_source_period(self):
        s=dict(self.station(),history_start='2020-01-01',history_end='2021-12-31')
        self.assertEqual([t[1] for t in c.tasks([s],2016,2025)],['2020','2021'])
if __name__=='__main__':unittest.main()
