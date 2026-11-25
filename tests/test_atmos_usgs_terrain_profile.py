import io
import json
import math
import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from atmos_usgs_terrain_profile import (
    sample_locations,endpoint,extract_elevation,terrain_summary,fetch_terrain,
)

class TerrainProfileTests(unittest.TestCase):
    def test_cardinal_sampling_surrounds_actual_point(self):
        p=sample_locations(42.7272,-114.4547)
        self.assertEqual(p['center'],(42.7272,-114.4547))
        self.assertGreater(p['north'][0],p['center'][0])
        self.assertLess(p['south'][0],p['center'][0])
        self.assertGreater(p['east'][1],p['center'][1])
        self.assertLess(p['west'][1],p['center'][1])
        self.assertTrue(endpoint(*p['center']).startswith('https://epqs.nationalmap.gov/v1/json?'))

    def test_service_invalid_numbers_do_not_become_terrain(self):
        for obj in [{'value':None}, {'value':'NaN'},{'value':99999},
                    {'value':500,'units':'Feet'}, {'oops':500}]:
            self.assertIsNone(extract_elevation(obj))
        self.assertEqual(extract_elevation({'value':0,'units':'Meters'}),0)
        self.assertEqual(extract_elevation({'value':1005,'units':'Meters'}),1005)

    def test_known_north_and_east_slopes(self):
        samples={direction:dict(status='observed_service_response',height_m=h)
                 for direction,h in [('center',1000),('north',1030),('south',970),
                                     ('east',1020),('west',980)]}
        r=terrain_summary(samples)
        self.assertTrue(r['complete'])
        self.assertAlmostEqual(r['northward_slope_m_per_km'],6)
        self.assertAlmostEqual(r['eastward_slope_m_per_km'],4)
        self.assertEqual(r['relief_m'],60)
        r=terrain_summary({**samples,'west':{'status':'source_unavailable','height_m':None}})
        self.assertFalse(r['complete'])
        self.assertIsNone(r['northward_slope_m_per_km'])

    def test_fetch_hashes_genuine_response_bytes(self):
        payload=json.dumps({'value':1030.8,'units':'Meters'}).encode()
        with patch('atmos_usgs_terrain_profile.urllib.request.urlopen',return_value=io.BytesIO(payload)):
            out=fetch_terrain(42.7272,-114.4547,attempts=1)
        self.assertEqual(out['status'],'observed_service_response')
        self.assertAlmostEqual(out['height_m'],1030.8)
        self.assertEqual(len(out['raw_response_sha256']),64)

if __name__=='__main__':
    unittest.main()
