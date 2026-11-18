import datetime as dt
import io
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from atmos_multi_region_wind_pilot import (
    wind_weight, circular_offset_degrees, load_surface, build_examples,
    candidate_clusters, select_regions, fit_all, score,
)

UTC=dt.timezone.utc

class MultiRegionTests(unittest.TestCase):
    def test_upwind_bearing_is_meteorological_from(self):
        self.assertGreater(wind_weight(270,270,8),0.9)
        self.assertEqual(wind_weight(90,270,8),0)
        self.assertEqual(wind_weight(270,270,0),0)
        self.assertEqual(wind_weight(270,270,1),0)
        self.assertAlmostEqual(circular_offset_degrees(355,5),-10)

    def test_no_lookahead_and_genuine_wind_is_only_asof(self):
        t=dt.datetime(2022,1,1,tzinfo=UTC)
        time=lambda h:t+dt.timedelta(hours=h)
        a={'provider':'NOAA_GHCNh','station_id':'A','latitude':40,'longitude':-112,'elevation_m':1000}
        b={'provider':'NOAA_GHCNh','station_id':'B','latitude':40,'longitude':-113,'elevation_m':1000}
        stations={'A':a,'B':b}
        surface={
            'A':{'temperature_c':{time(i):10.0 for i in range(210)},
                 'wind_speed_mps':{time(i):9.0 for i in range(210)},
                 'wind_direction_deg':{time(i):270.0 for i in range(210)}},
            'B':{'temperature_c':{time(i):20.0 for i in range(210)}},
        }
        # At verification 150, issued at 126 and latest allowed hour is 54.
        surface['A']['temperature_c'][time(100)]=99.0
        surface['A']['wind_direction_deg'][time(100)]=90.0
        rows=list(build_examples('A',['B'],stations,surface))
        item=next(x for x in rows if x['valid_at']==time(150))
        self.assertEqual(item['baseline'],10.0)
        self.assertTrue(item['used_wind'])
        self.assertEqual(item['upwind'][-1],1.0)
        self.assertEqual(item['actual'],10.0)

    def test_screened_noaa_wind_and_temperature_are_separate(self):
        data=('DATE|temperature|temperature_Quality_Code|temperature_Source_Code|'
              'wind_speed|wind_speed_Quality_Code|wind_speed_Source_Code|'
              'wind_direction|wind_direction_Quality_Code|wind_direction_Source_Code\n'
              '2022-01-01T00:00:00|8|1|335|7|0|345|270|1|335\n'
              '2022-01-01T01:00:00|9|3|335|7|0|345|270|8|335\n').encode()
        surface, report=load_surface(data)
        self.assertEqual(len(surface['temperature_c']),1)
        self.assertEqual(len(surface['wind_speed_mps']),2)
        self.assertEqual(len(surface['wind_direction_deg']),1)
        self.assertEqual(report['temperature:noaa_source_quality_not_approved'],1)

    def test_models_share_identical_cases(self):
        samples=[dict(local=[1.,i/30,0,0,0,0,0,0],
                      geographic=[1.,i/30,0,0,0,0,0,0,0.2],
                      upwind=[1.,i/30,0,0,0,0,0,0,0.2,0,0,0],
                      actual=float(i),baseline=0.,used_wind=False)
                 for i in range(100)]
        models=fit_all(samples)
        result=score(samples,models)
        self.assertEqual(result['cases'],100)
        self.assertEqual(result['upwind_active_cases'],0)
        self.assertIn('upwind_mae_c',result)

    def test_no_overlapping_train_holdout_tiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=pathlib.Path(tmp)/'graph.jsonl'
            records=[]
            elig={}
            for ident,lat,lon,role in [
                ('A',41,-122,'training_target'),('B',39,-116,'training_target'),
                ('C',37,-108,'training_target'),('D',35,-100,'spatial_holdout_target'),
                ('E',33,-92,'spatial_holdout_target')]:
                elig[ident]=({'latitude':str(lat),'longitude':str(lon),'elevation_m':'100'},
                             {year:8000 for year in [2022,2023,2024,2025]})
                records.append(dict(target_provider='NOAA_GHCNh',target_station_id=ident,role=role,
                    latitude=lat,longitude=lon,spatial_tile=[int(lat//3),int(lon//3)],
                    candidate_neighbors=[dict(provider='NOAA_GHCNh',station_id='F',
                                             distance_km=15),
                                         dict(provider='NOAA_GHCNh',station_id='G',
                                              distance_km=50)]))
            for id in ('F','G'):
                elig[id]=({'latitude':'40','longitude':'-120','elevation_m':'100'},
                          {year:8000 for year in [2022,2023,2024,2025]})
            path.write_text('\n'.join(map(json.dumps,records))+'\n')
            chosen=select_regions(path,elig,train_count=3,holdout_count=2,
                                  separation_km=200)
            train={tuple(x['node']['spatial_tile']) for x in chosen
                   if x['node']['role']=='training_target'}
            heldout={tuple(x['node']['spatial_tile']) for x in chosen
                     if x['node']['role']=='spatial_holdout_target'}
            self.assertEqual(len(train),3)
            self.assertEqual(len(heldout),2)
            self.assertFalse(train&heldout)

if __name__=='__main__':
    unittest.main()
