import csv
import gzip
import io
import json
import tarfile
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from atmos.noaa_v3_full_walk_forward import run


class FullWalkForwardTests(unittest.TestCase):
    def test_all_years_and_causal_reporting(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "shard.tar"
            payload = io.BytesIO()
            with gzip.GzipFile(fileobj=payload, mode="wb") as gz:
                with io.TextIOWrapper(gz, encoding="utf-8", newline="") as writer:
                    csvwriter = csv.writer(writer)
                    csvwriter.writerow(["station_id", "hour_utc", "temperature_c", "temperature_qc", "dewpoint_c", "dewpoint_qc", "relative_humidity_pct", "wind_speed_mps", "wind_speed_qc", "wind_direction_deg", "wind_direction_qc", "sea_level_pressure_hpa", "sea_level_pressure_qc", "visibility_m", "visibility_qc", "precip_1h_mm", "precip_1h_qc"])
                    base = datetime(2006, 1, 1, tzinfo=timezone.utc)
                    for day in range(45):
                        csvwriter.writerow(["station-1", (base + timedelta(days=day)).strftime("%Y-%m-%dT%H:%M:%S"), str(day % 8), "1", "2", "1", "70", "3", "1", "90", "1", "1010", "1", "10000", "1", "0", "1"])
            data = payload.getvalue()
            with tarfile.open(archive, "w") as tar:
                item = tarfile.TarInfo("normalized-shard-00.csv.gz")
                item.size = len(data)
                tar.addfile(item, io.BytesIO(data))
            report = run(archive, 0, lag_hours=72, horizons=(24,))
            self.assertEqual(report["accepted_rows_by_variable"]["temperature_c"], 45)
            self.assertEqual(report["station_counts_by_variable"]["temperature_c"], 1)
            self.assertIn("2006", report["metrics"]["temperature_c"]["24"]["by_year"])
            self.assertGreater(report["metrics"]["temperature_c"]["24"]["by_year"]["2006"]["cases"], 0)


if __name__ == "__main__":
    unittest.main()
