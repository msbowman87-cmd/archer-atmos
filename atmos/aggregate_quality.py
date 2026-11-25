"""Finalize a 40-shard NOAA observation QC archive with verified integrity.

Assemble global coverage, metric usability, station and year summaries,
SHA-256 checksums and immutable per-shard packages for a GitHub prerelease.
"""
import argparse,gzip,hashlib,json,tarfile
from collections import Counter,defaultdict
from pathlib import Path

def aggregate(root,output,source_run):
    root=Path(root);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    totals=Counter();by_year=defaultdict(Counter);by_station=defaultdict(Counter)
    metrics=Counter();issues=Counter();assets=[]
    for shard in range(40):
        directory=root/f"atmos-quality-shard-{shard}"
        report=directory/f"quality-report-{shard:02d}.json"
        csv_file=directory/f"normalized-shard-{shard:02d}.csv.gz"
        if not (report.is_file() and csv_file.is_file()):
            raise FileNotFoundError(f"Missing quality shard {shard}")
        info=json.loads(report.read_text())
        s=info["summary"]
        assert s["shard"]==shard and s["requested_years"]==500
        assert s["audited_years"]+s["missing_years"]==500
        assert len(info["station_years"])==500
        assert sum(x.get("rows",0) for x in info["station_years"])==s["row_count"]
        with gzip.open(csv_file,"rb") as f:
            header=f.readline()
            if b"observed_at_utc" not in header or b"relative_humidity_pct" not in header:
                raise ValueError("Normalized weather schema mismatch")
            while f.read(1<<20):pass  # Validates CRC of entire gzip stream
        for key in ("requested_years","audited_years","missing_years","row_count",
                    "normalized_rows","hourly_points","possible_calendar_hours","off_hour_rows"):
            totals[key]+=s[key]
        metrics.update(s["metrics_valid"]);issues.update(s["issues"])
        for item in info["station_years"]:
            station=item["station_id"];year=int(item["year"])
            by_station[station]["years_requested"]+=1
            by_year[year]["years_requested"]+=1
            if item["status"]=="audited":
                by_station[station]["years_audited"]+=1
                by_station[station]["hours_reported"]+=item["rows"]
                by_year[year]["years_audited"]+=1
                by_year[year]["hours_reported"]+=item["rows"]
                by_year[year]["hours_possible"]+=item["expected_calendar_hours"]
                for k,v in item["valid_metrics"].items():
                    by_year[year]["valid_"+k]+=v
            else:
                by_year[year]["source_missing"]+=1
                by_year[year]["hours_possible"]+=item["expected_calendar_hours"]
        tar_path=output/f"atmos-quality-shard-{shard:02d}.tar"
        with tarfile.open(tar_path,"w") as tar:
            tar.add(report,arcname=report.name)
            tar.add(csv_file,arcname=csv_file.name)
        with tar_path.open("rb") as f:sha=hashlib.file_digest(f,"sha256").hexdigest()
        with csv_file.open("rb") as f:data_sha=hashlib.file_digest(f,"sha256").hexdigest()
        assets.append({"shard":shard,"filename":tar_path.name,
                       "bytes":tar_path.stat().st_size,"sha256":sha,
                       "normalized_gzip_sha256":data_sha,
                       "rows":s["row_count"],"normalized_rows":s["normalized_rows"]})
        print("Packaged quality shard",shard,s["row_count"],s["normalized_rows"],flush=True)
    assert len(by_station)==1000,len(by_station)
    assert totals["requested_years"]==20000,totals
    assert totals["audited_years"]==19865,totals
    assert totals["missing_years"]==135,totals
    assert totals["row_count"]==162723595,totals
    assert totals["normalized_rows"]>0,totals
    report={"schema_version":3,"source_release":"atmos-noaa-observations-2006-2025-v2",
            "station_count":1000,"calendar_range":"2006-2025",
            "coverage_definition":"Reported station-hours / full UTC calendar hours",
            "hourly_data_note":"These are individual NOAA measurements nearest a UTC hour, not hourly averaged readings.",
            "2025_note":"Legacy ISD/Global Hourly stopped in August 2025; gap is real and must be filled from GHCNh separately.",
            "quality_accepted":["0","1","4","5"],
            "humidity_note":"Magnus formula from valid temperature and dewpoint, approximately valid over water, not a measured humidity sensor.",
            "time_provenance":"Original NOAA observation time preserved; publication time unknown.",
            "no_training_without_verified_forecasts_and_publication_times":True,
            "v2_source_left_unchanged":True,
            "totals":dict(totals),"valid_metrics":dict(metrics),"qc_issues":dict(issues),
            "yearly":{str(k):dict(v) for k,v in sorted(by_year.items())},
            "stations":{k:dict(v) for k,v in sorted(by_station.items())}}
    manifest={"schema_version":3,"source_run":source_run,
              "source_release":"atmos-noaa-observations-2006-2025-v2",
              "derived_not_original_noaa":True,"files":assets,
              "totals":dict(totals),"valid_metrics":dict(metrics)}
    (output/"atmos-global-quality-report.json").write_text(json.dumps(report,indent=2)+"\n")
    (output/"atmos-quality-manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print("QUALITY TOTALS",json.dumps(dict(totals)),flush=True)
    print("VARIABLE COUNTS",json.dumps(dict(metrics)),flush=True)
    return report,manifest

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input-dir",required=True)
    p.add_argument("--output-dir",required=True)
    p.add_argument("--source-run-id",type=int,required=True)
    args=p.parse_args()
    aggregate(args.input_dir,args.output_dir,args.source_run_id)
if __name__=="__main__":main()
