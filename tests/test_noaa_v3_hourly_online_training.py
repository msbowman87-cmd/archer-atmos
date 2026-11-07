import csv
import gzip
import io
import tarfile
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from atmos.noaa_v3_hourly_online_training import run,angular_error,features

class HourlyTrainingTests(unittest.TestCase):
    def test_direction_wrap(self):
        self.assertEqual(angular_error(1,359),2)
    def test_future_data_not_used(self):
        t=datetime(2006,1,1,tzinfo=timezone.utc)
        self.assertIsNone(features("temperature_c",t,24,{}))
        self.assertIsNone(features("temperature_c",t,24,{"temperature_c":(t-timedelta(days=15),1.)}))
    def test_frozen_forecasts_train_only_when_labels_mature(self):
        with tempfile.TemporaryDirectory() as folder:
            archive=Path(folder)/"sample.tar"
            payload=io.BytesIO()
            with gzip.GzipFile(fileobj=payload,mode="wb") as gz:
                with io.TextIOWrapper(gz,encoding="utf-8",newline="") as f:
                    w=csv.writer(f)
                    w.writerow(["station_id","hour_utc","temperature_c","temperature_qc","dewpoint_c","dewpoint_qc","relative_humidity_pct","wind_speed_mps","wind_speed_qc","wind_direction_deg","wind_direction_qc","sea_level_pressure_hpa","sea_level_pressure_qc","visibility_m","visibility_qc","precip_1h_mm","precip_1h_qc"])
                    start=datetime(2006,1,1,tzinfo=timezone.utc)
                    for hour in range(24*12):
                        t=start+timedelta(hours=hour)
                        w.writerow(["station-1",t.isoformat(),str(10.+hour/100.),"1","5","1","70","2","1","359","1","1013","1","10000","1","0","1"])
            data=payload.getvalue()
            with tarfile.open(archive,"w") as tar:
                info=tarfile.TarInfo("normalized-shard-00.csv.gz")
                info.size=len(data)
                tar.addfile(info,io.BytesIO(data))
            result=run(archive,0,lag_hours=72,horizons=(24,))
            self.assertGreater(result["trained_examples"]["temperature_c|24"],0)
            self.assertGreater(result["metrics"]["temperature_c"]["24"]["by_year"]["2006"]["cases"],0)
            self.assertEqual(result["method"].startswith("hour-by-hour"),True)

if __name__=="__main__":unittest.main()
