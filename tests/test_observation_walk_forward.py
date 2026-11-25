import csv
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from atmos.observation_walk_forward import evaluate, load_rows


class ObservationWalkForwardTests(unittest.TestCase):
    def sample(self, leak=False):
        base = datetime(2023, 1, 1, tzinfo=timezone.utc)
        rows = []
        for day in range(45):
            observed = base + timedelta(days=day)
            available = observed + timedelta(hours=1)
            if leak and day < 28:
                available = observed + timedelta(days=50)
            rows.append((observed, available, float(day)))
        return {"s1": rows}

    def test_no_future_observations(self):
        clean = evaluate(self.sample(), start="2023-02-01T00:00:00Z",
                         end="2023-02-15T00:00:00Z")
        leaked = evaluate(self.sample(leak=True), start="2023-02-01T00:00:00Z",
                          end="2023-02-15T00:00:00Z")
        self.assertGreater(clean["paired_cases"], 0)
        self.assertLess(leaked["paired_cases"], clean["paired_cases"])

    def test_empty_holdout(self):
        report = evaluate(self.sample(), start="2025-01-01T00:00:00Z",
                          end="2026-01-01T00:00:00Z")
        self.assertEqual(report["status"], "insufficient_evidence")

    def test_reject_duplicate(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "rows.csv"
            with path.open("w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["station_id","observed_at_utc","available_at_utc","temperature_c"])
                for _ in range(2):
                    writer.writerow(["s1","2023-01-01T00:00:00Z","2023-01-01T01:00:00Z","5"])
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                load_rows(path)

    def test_reject_missing_availability(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "rows.csv"
            path.write_text("station_id,observed_at_utc,available_at_utc,temperature_c\ns1,2023-01-01T00:00:00Z,,5\n")
            with self.assertRaisesRegex(ValueError, "Invalid observation"):
                load_rows(path)


if __name__ == "__main__":
    unittest.main()
