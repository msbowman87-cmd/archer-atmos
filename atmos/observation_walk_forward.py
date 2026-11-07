"""Observation-only, causal walk-forward baseline for hourly station data.

CSV columns: station_id, observed_at_utc, available_at_utc, temperature_c.
Only observations available at issue time are eligible. No historical model
forecasts are needed. Does not modify raw observations or production.
"""
import argparse
import csv
import json
from collections import defaultdict
from datetime import timedelta
from math import isfinite
from pathlib import Path

from atmos.temporal_provenance import utc


def load_rows(path):
    rows = defaultdict(list)
    with open(path, newline="", encoding="utf-8") as handle:
        for number, row in enumerate(csv.DictReader(handle), 2):
            try:
                station = row["station_id"].strip()
                observed = utc(row["observed_at_utc"])
                available = utc(row["available_at_utc"])
                value = float(row["temperature_c"])
                if not station or not isfinite(value) or available < observed:
                    raise ValueError("invalid station/value/availability")
                rows[station].append((observed, available, value))
            except (KeyError, ValueError, TypeError) as exc:
                raise ValueError(f"Invalid observation at CSV line {number}: {exc}") from exc
    for station in rows:
        rows[station].sort()
        times = [r[0] for r in rows[station]]
        if len(times) != len(set(times)):
            raise ValueError(f"Duplicate station observation time: {station}")
    return rows


def evaluate(rows, *, horizon_hours=24, start="2023-01-01T00:00:00Z",
             end="2026-01-01T00:00:00Z"):
    """Causal seasonal-hour baseline; exact hourly targets, no interpolation.

    Forecast: mean of same UTC hour from the last 28 days, using only
    observations published before issue. Missing targets are excluded.
    """
    if horizon_hours < 1:
        raise ValueError("Horizon must be positive")
    begin, finish = utc(start), utc(end)
    if begin >= finish:
        raise ValueError("Invalid evaluation period")
    errors = []
    by_station = defaultdict(list)
    predictions = 0
    for station, records in rows.items():
        lookup = {t: (available, value) for t, available, value in records}
        for target, _, actual in records:
            if not begin <= target < finish:
                continue
            issue = target - timedelta(hours=horizon_hours)
            candidates = []
            for day in range(1, 29):
                past = target - timedelta(days=day)
                entry = lookup.get(past)
                if entry and past < issue and entry[0] <= issue:
                    candidates.append(entry[1])
            if len(candidates) < 7:
                continue
            predicted = sum(candidates) / len(candidates)
            error = abs(predicted - actual)
            errors.append(error)
            by_station[station].append(error)
            predictions += 1
    return dict(status="evaluated" if errors else "insufficient_evidence",
                method="28-day same-UTC-hour mean, >=7 causal observations",
                horizon_hours=horizon_hours, evaluation_start=start,
                evaluation_end=end, paired_cases=predictions,
                station_count=len(by_station),
                mae_c=sum(errors)/len(errors) if errors else None,
                station_mae_c={k:sum(v)/len(v) for k,v in sorted(by_station.items())},
                limitations=["Observation-only baseline; not a trained global forecast.",
                             "Requires independently evidenced available_at_utc.",
                             "Targets must be actual observations, not derived forecasts."])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Normalized, timestamp-audited CSV")
    parser.add_argument("--output", required=True)
    parser.add_argument("--horizon-hours", type=int, default=24)
    parser.add_argument("--start", default="2023-01-01T00:00:00Z")
    parser.add_argument("--end", default="2026-01-01T00:00:00Z")
    args = parser.parse_args()
    report = evaluate(load_rows(args.input), horizon_hours=args.horizon_hours,
                      start=args.start, end=args.end)
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k!="station_mae_c"}, indent=2))


if __name__ == "__main__":
    main()
