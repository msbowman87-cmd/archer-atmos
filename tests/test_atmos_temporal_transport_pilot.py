import datetime as dt
import pathlib
import sys
import unittest

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from atmos_temporal_transport_pilot import (
    decode_source,History,pressure_history,features_for_station,
    score,paired_interval,MODEL_NAMES,
)
UTC=dt.timezone.utc

class TransportPilotTests(unittest.TestCase):
    def test_independent_quality_flags_for_pressure_wind_and_temperature(self):
        raw=('DATE|temperature|temperature_Source_Code|temperature_Quality_Code|'
             'wind_speed|wind_speed_Source_Code|wind_speed_Quality_Code|'
             'wind_direction|wind_direction_Source_Code|wind_direction_Quality_Code|'
             'sea_level_pressure|sea_level_pressure_Source_Code|sea_level_pressure_Quality_Code\n'
             '2022-01-01T00:00:00|8|335|1|10|345|0|270|335|1|1010|335|1\n'
             '2022-01-01T01:00:00|100|335|1|8|345|0|90|335|8|1020|335|2\n').encode()
        values,counts=decode_source(raw)
        self.assertEqual(len(values['temperature_c']),1)
        self.assertEqual(len(values['wind_speed_mps']),2)
        self.assertEqual(len(values['wind_direction_deg']),1)
        self.assertEqual(len(values['sea_level_pressure_hpa']),1)
        self.assertEqual(counts['sea_level_pressure:noaa_source_quality_not_approved'],1)

    def test_pressure_station_level_not_used_as_sea_level_absolute(self):
        data={'station_pressure_hpa':{dt.datetime(2022,1,1,tzinfo=UTC):899}}
        p,kind=pressure_history(data)
        self.assertEqual(kind,'station_pressure_hpa')
        self.assertEqual(p.at(dt.datetime(2022,1,1,tzinfo=UTC)),899)
        self.assertIsNone(p.trend(dt.datetime(2022,1,1,tzinfo=UTC),6))

    def test_forecast_no_lookahead_wind_and_pressure_change(self):
        t=dt.datetime(2022,1,1,tzinfo=UTC)
        h=lambda i:t+dt.timedelta(hours=i)
        me={'latitude':'40','longitude':'-112','elevation_m':'1000'}
        nw={'latitude':'40','longitude':'-113','elevation_m':'1200'}
        meta={'T':me,'N':nw}
        surf={'T':{
                'temperature_c':{h(i):10.+i*.02 for i in range(220)},
                'sea_level_pressure_hpa':{h(i):1000.+i*.1 for i in range(220)},
                'wind_speed_mps':{h(i):10. for i in range(220)},
                'wind_direction_deg':{h(i):270. for i in range(220)}
              },'N':{
                'temperature_c':{h(i):15.+i*.01 for i in range(220)},
                'station_pressure_hpa':{h(i):900.+i*.2 for i in range(220)}
              }}
        target_time=h(150)
        a=next(x for x in features_for_station('T',['N'],meta,surf)
               if x['valid_at']==target_time)
        # Latest eligible timestamp for target at 150: 150 - (24+72) = 54.
        self.assertAlmostEqual(a['persistence'],10.+54*.02)
        self.assertTrue(a['upwind_active'])
        self.assertTrue(a['pressure_tendency_available'])
        self.assertTrue(a['neighbor_pressure_available'])
        self.assertEqual(len(a['station_only']),8)
        self.assertEqual(len(a['station_tendency']),16)
        self.assertEqual(len(a['geographic']),21)
        self.assertEqual(len(a['transport']),27)
        # Change all post-as-of readings; same features and forecast inputs.
        for sid in ['T','N']:
            surf[sid]['temperature_c'][h(100)]=50.
        surf['T']['sea_level_pressure_hpa'][h(100)]=1040.
        surf['T']['wind_direction_deg'][h(100)]=90.
        b=next(x for x in features_for_station('T',['N'],meta,surf)
               if x['valid_at']==target_time)
        self.assertEqual(a['station_only'],b['station_only'])
        self.assertEqual(a['station_tendency'],b['station_tendency'])
        self.assertEqual(a['geographic'],b['geographic'])
        self.assertEqual(a['transport'],b['transport'])

    def test_no_fake_pressure_and_wind_when_missing(self):
        t=dt.datetime(2022,1,1,tzinfo=UTC)
        h=lambda i:t+dt.timedelta(hours=i)
        meta={'T':{'latitude':'40','longitude':'-112','elevation_m':'1000'},
              'N':{'latitude':'40','longitude':'-113','elevation_m':'1200'}}
        s={'T':{'temperature_c':{h(i):10. for i in range(150)}},
           'N':{'temperature_c':{h(i):12. for i in range(150)}}}
        item=next(iter(features_for_station('T',['N'],meta,s)))
        self.assertFalse(item['upwind_active'])
        self.assertFalse(item['pressure_tendency_available'])
        self.assertFalse(item['neighbor_pressure_available'])
        self.assertEqual(item['transport'][-1],0.)

    def test_scoring_and_block_resampling_use_identical_cases(self):
        start=dt.datetime(2025,1,1,tzinfo=UTC)
        row=dict(target='X',valid_at=start,year=2025,actual=4.,persistence=5.,
                 station_only=[1.]*8,station_tendency=[1.]*16,
                 geographic=[1.]*21,transport=[1.]*27,
                 upwind_active=False,pressure_tendency_available=False,
                 neighbor_pressure_available=False)
        models={name:[0.]*len(row[name]) for name in MODEL_NAMES}
        rows=[dict(row,valid_at=start+dt.timedelta(hours=i)) for i in range(50)]
        result=score(rows,models)
        self.assertEqual(result['cases'],50)
        self.assertEqual(result['station_only_mae_c'],4)
        self.assertEqual(result['transport_mae_c'],4)
        interval=paired_interval(rows,models)
        self.assertEqual(interval['delta_mae_c_positive_is_improvement'],0)
        self.assertEqual(interval['interval_95_c'],[0,0])

if __name__=='__main__':
    unittest.main()
