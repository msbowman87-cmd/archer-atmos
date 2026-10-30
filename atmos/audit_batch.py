"""Strict validation for archived gridded daily observation batches."""
import argparse
import csv
import json
from collections import Counter
from datetime import timedelta
from pathlib import Path
from atmos.study_batch import year_window, locations

FIELDS=("temp_max_c","temp_min_c","precip_mm","wind_max_kmh")

def audit(batch, folder):
    folder=Path(folder)
    path=folder/f"observations_batch_{batch:02d}.csv"
    summary_path=folder/f"summary_batch_{batch:02d}.json"
    summary=json.loads(summary_path.read_text())
    start,end=year_window(batch)
    expected_days=(end-start).days+1
    expected_locations={p["id"] for p in locations()}
    counts=Counter()
    missing=Counter()
    duplicates=0
    seen=set()
    bad_dates=0
    invalid_values=0
    rows=0
    with path.open(newline="") as stream:
        for record in csv.DictReader(stream):
            rows+=1
            key=(record["location_id"],record["date_utc"])
            if key in seen: duplicates+=1
            seen.add(key)
            counts[record["location_id"]]+=1
            if not (start.isoformat()<=record["date_utc"]<=end.isoformat()):
                bad_dates+=1
            for field in FIELDS:
                value=record[field]
                if value=="":
                    missing[field]+=1
                else:
                    try:
                        v=float(value)
                        if not (-150<=v<=150 if field.startswith("temp") else 0<=v<=5000):
                            invalid_values+=1
                    except ValueError:
                        invalid_values+=1
    passed=(rows==200*expected_days and set(counts)==expected_locations
            and all(n==expected_days for n in counts.values())
            and not duplicates and not bad_dates and not invalid_values
            and not any(missing.values()) and summary["locations_succeeded"]==200
            and not summary["location_errors"])
    result={"batch":batch,"start":start.isoformat(),"end":end.isoformat(),
            "expected_rows":200*expected_days,"actual_rows":rows,
            "locations":len(counts),"duplicate_rows":duplicates,
            "out_of_range_dates":bad_dates,"invalid_values":invalid_values,
            "missing_fields":dict(missing),"pass":passed,
            "classification":"gridded historical estimates, NOT verified forecasts"}
    (folder/f"audit_batch_{batch:02d}.json").write_text(json.dumps(result,indent=2))
    if not passed:
        raise RuntimeError("Batch failed strict audit: "+json.dumps(result))
    return result

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--batch",type=int,required=True)
    parser.add_argument("--output",default="study-results")
    args=parser.parse_args()
    print(json.dumps(audit(args.batch,args.output),indent=2))
