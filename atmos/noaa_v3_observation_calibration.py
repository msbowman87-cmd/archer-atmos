"""Exploratory NOAA v3 observation-only calibration adapter.

NOAA ISD does not provide publication timestamps. Assumed availability lag
is an explicit research scenario, NOT evidence of historical availability.
No raw data or production files are modified.
"""
import argparse
import csv
import gzip
import json
import tarfile
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from atmos.observation_walk_forward import evaluate, load_rows
from atmos.temporal_provenance import utc


def parse_noaa_hour_utc(value):
    """NOAA-normalized hour_utc has UTC semantics even without an offset.

    Never assume naive timestamps from unrelated input sources are UTC.
    """
    if not value:
        raise ValueError("Missing NOAA UTC hour")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return utc(parsed.isoformat())


def convert_archive(archive, destination, shard, assumed_lag_hours):
    if assumed_lag_hours < 0:
        raise ValueError("Lag cannot be negative")
    wanted = f"normalized-shard-{shard:02d}.csv.gz"
    with tarfile.open(archive, "r:*") as tar:
        members = [m for m in tar.getmembers()
                   if m.isfile() and Path(m.name).name == wanted]
        if len(members) != 1:
            raise ValueError(f"Expected one {wanted}, found {len(members)}")
        with tar.extractfile(members[0]) as source:
            with gzip.open(source, "rt", newline="", encoding="utf-8") as inp:
                reader = csv.DictReader(inp)
                required = {"station_id", "hour_utc", "temperature_c", "temperature_qc"}
                if not required.issubset(reader.fieldnames or []):
                    raise ValueError("Unexpected NOAA v3 normalized schema")
                with open(destination, "w", newline="", encoding="utf-8") as out:
                    writer = csv.DictWriter(out, fieldnames=[
                        "station_id", "observed_at_utc", "available_at_utc", "temperature_c"])
                    writer.writeheader()
                    rows = 0
                    for record in reader:
                        if not record["temperature_c"] or record["temperature_qc"] not in {"0","1","4","5"}:
                            continue
                        observed = parse_noaa_hour_utc(record["hour_utc"])
                        writer.writerow({
                            "station_id": record["station_id"],
                            "observed_at_utc": observed.isoformat(),
                            "available_at_utc": (observed + timedelta(hours=assumed_lag_hours)).isoformat(),
                            "temperature_c": record["temperature_c"]})
                        rows += 1
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True)
    parser.add_argument("--shard", required=True, type=int)
    parser.add_argument("--output", required=True)
    parser.add_argument("--assumed-lag-hours", type=int, default=72)
    args = parser.parse_args()
    if not 0 <= args.shard < 40:
        parser.error("Shard must be 0 through 39")
    with tempfile.TemporaryDirectory() as directory:
        csv_path = Path(directory) / "observations.csv"
        accepted = convert_archive(args.archive, csv_path, args.shard, args.assumed_lag_hours)
        rows = load_rows(csv_path)
        reports = {}
        for horizon in (24, 48, 72):
            reports[str(horizon)] = evaluate(rows, horizon_hours=horizon)
        result = {
            "status": "exploratory_only_not_certified",
            "source": "NOAA quality-filtered v3",
            "shard": args.shard,
            "accepted_temperature_rows": accepted,
            "availability_assumption_hours": args.assumed_lag_hours,
            "assumption_not_verified": True,
            "holdout": "2023-01-01 through 2025-12-31 UTC",
            "results": reports,
        }
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps({k:v for k,v in result.items() if k!="results"}))
        for horizon, report in reports.items():
            print(horizon, report["status"], report["paired_cases"], report["mae_c"])


if __name__ == "__main__":
    main()
