"""No fabricated sensor data, product name and timestamp integrity checks."""
import unittest
from datetime import datetime,timezone
from unittest.mock import MagicMock
from atmos.historical_remote_sensing_pilot import (
    STATIONS,filename_time,find_scene,
)

class HistoricalArchivePilotTests(unittest.TestCase):
    def test_goes_product_times_from_real_filename_pattern(self):
        name=("OR_ABI-L2-ACMC-M3_G16_s20181521800000_"
              "e20181521805000_c20181521806400.nc")
        self.assertEqual(filename_time(name,"s"),
                         datetime(2018,6,1,18,0,tzinfo=timezone.utc))
        self.assertEqual(filename_time(name,"c"),
                         datetime(2018,6,1,18,6,40,tzinfo=timezone.utc))
        with self.assertRaises(ValueError):
            filename_time(name,"z")

    def test_select_nearest_2018_radar_file(self):
        fake=MagicMock()
        fake.get_paginator.return_value.paginate.return_value=[{"Contents":[
            {"Key":"2018/06/01/KCBX/KCBX20180601_161500_V06","Size":100},
            {"Key":"2018/06/01/KCBX/KCBX20180601_175800_V06","Size":100},
            {"Key":"2018/06/01/KCBX/KCBX20180601_180200_V06","Size":100},
        ]}]
        chosen=find_scene(fake,"unidata-nexrad-level2","2018/06/01/KCBX/",
                          datetime(2018,6,1,18,tzinfo=timezone.utc),radar=True)
        self.assertEqual(chosen[2],"2018/06/01/KCBX/KCBX20180601_175800_V06")

    def test_missing_archive_returns_none_not_fabricated_zero(self):
        fake=MagicMock()
        fake.get_paginator.return_value.paginate.return_value=[{"Contents":[]}]
        chosen=find_scene(fake,"noaa-goes16","ABI-L2-ACMC/2018/152/18/",
                          datetime(2018,6,1,18,tzinfo=timezone.utc))
        self.assertIsNone(chosen)

    def test_station_ids_are_distinct(self):
        self.assertEqual(len(STATIONS),len(set(STATIONS)))
        self.assertEqual(len(set(r for _,r in STATIONS.values())),len(STATIONS))

if __name__=="__main__":
    unittest.main()
