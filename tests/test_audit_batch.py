import csv
import json
import tempfile
import unittest
from pathlib import Path
from atmos.audit_batch import audit
from atmos.study_batch import year_window, locations
from datetime import timedelta

class TestAudit(unittest.TestCase):
    def test_rejects_incomplete_batch(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            with (folder/"observations_batch_00.csv").open("w",newline="") as f:
                w=csv.writer(f)
                w.writerow(["location_id","date_utc","temp_max_c","temp_min_c","precip_mm","wind_max_kmh"])
                w.writerow(["P001","2016-10-30",10,0,0,5])
            (folder/"summary_batch_00.json").write_text(json.dumps({"locations_succeeded":1,"location_errors":[]}))
            with self.assertRaises(RuntimeError):
                audit(0,folder)
