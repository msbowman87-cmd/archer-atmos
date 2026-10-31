import unittest
from atmos.station_backtest import aggregate_local_days

class LocalDayTests(unittest.TestCase):
    def test_complete_local_day(self):
        from datetime import datetime,timedelta
        stamps=[(datetime(2026,9,1,6)+timedelta(hours=i)).isoformat(timespec="minutes") for i in range(24)]
        data={'time':stamps,'temperature_2m':[float(i) for i in range(24)],'precipitation':[1.]*24}
        result=aggregate_local_days(data,'America/Boise')
        self.assertEqual(len(result),1)
        self.assertEqual(result[next(iter(result))],(23.,24.))
    def test_incomplete_day_rejected(self):
        from datetime import datetime,timedelta
        stamps=[(datetime(2026,9,1,6)+timedelta(hours=i)).isoformat(timespec="minutes") for i in range(23)]
        data={'time':stamps,'temperature_2m':[1.]*23,'precipitation':[0.]*23}
        self.assertEqual(aggregate_local_days(data,'America/Boise'),{})
