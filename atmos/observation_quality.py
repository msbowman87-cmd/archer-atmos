"""Audit and normalize actual NOAA ISD observations without changing source archives.

All retained points are real station reports, matched to a nominal UTC hour
within 30 minutes. No averaging, interpolation or fabricated observations.
Original v2 release remains authoritative for raw reported fields and QC codes.

NOAA format: https://www.ncei.noaa.gov/pub/data/noaa/isd-format-document.pdf
Strict research QC accepts 0/1/4/5 (passed gross/all checks); conservative
rejection of suspect 2/6, erroneous 3/7, missing 9 and other unusual flags.
NOAA ISD ended in August 2025; historical yearly coverage is not guaranteed.

CRITICAL: Historical observation publication/availability timestamps are not
part of ISD. This module DOES NOT assert that data were known to a forecast
model on their observation date. The separate forecast pairing stage must
require independently established availability timestamps.
"""
import argparse
import csv
import gzip
import hashlib
import json
import math
from collections import Counter,defaultdict
from datetime import datetime,timedelta,timezone
from pathlib import Path

GOOD_QC=frozenset({"0","1","4","5"})
FIELDS=("station_id","year","observed_at_utc","hour_utc","offset_minutes",
        "temperature_c","temperature_qc","dewpoint_c","dewpoint_qc",
        "relative_humidity_pct","wind_speed_mps","wind_speed_qc",
        "wind_direction_deg","wind_direction_qc","sea_level_pressure_hpa",
        "sea_level_pressure_qc","visibility_m","visibility_qc",
        "precip_1h_mm","precip_1h_qc")
MEASURES=("temperature_c","dewpoint_c","relative_humidity_pct",
          "wind_speed_mps","wind_direction_deg","sea_level_pressure_hpa",
          "visibility_m","precip_1h_mm")
OBS_REQUIRED={"station_id","time_utc","hour_utc","offset_minutes","temperature_raw",
              "dewpoint_raw","wind_raw","pressure_raw","visibility_raw","precip_aa1_raw"}
DOC="https://www.ncei.noaa.gov/pub/data/noaa/isd-format-document.pdf"

def numeric_component(raw,part,qc_part,scale,missing,minimum,maximum,counts,label):
    parts=(raw or "").split(",")
    if len(parts)<=max(part,qc_part):
        counts[label]["missing_field"]+=1
        return None,""
    code=parts[qc_part].strip()
    try:value=int(parts[part].strip())
    except ValueError:
        counts[label]["invalid_number"]+=1
        return None,code
    if value==missing or value==-missing:
        counts[label]["sentinel_missing"]+=1
        return None,code
    if code not in GOOD_QC:
        counts[label]["qc_rejected_"+(code or "blank")]+=1
        return None,code
    scaled=value/scale
    if not minimum<=scaled<=maximum:
        counts[label]["physical_limit"]+=1
        return None,code
    counts[label]["accepted"]+=1
    return scaled,code

def humidity_percent(temp,dew,counts):
    if temp is None or dew is None:
        counts["relative_humidity_pct"]["missing_inputs"]+=1
        return None
    # Dew point > air temperature by >1 C is physically inconsistent. Smaller
    # overshoots can result from measurement/rounding; report them and clamp RH.
    if dew>temp+1:
        counts["relative_humidity_pct"]["dew_exceeds_temp"]+=1
        return None
    if dew>temp:
        counts["relative_humidity_pct"]["small_overshoot_clamped"]+=1
    # Magnus formula, water saturation; research approximation, especially
    # uncertain over ice at very cold temperatures.
    rh=100*math.exp(17.625*dew/(243.04+dew)-17.625*temp/(243.04+temp))
    if not math.isfinite(rh) or rh<0:
        counts["relative_humidity_pct"]["invalid"]+=1
        return None
    counts["relative_humidity_pct"]["accepted"]+=1
    return round(max(0,min(100,rh)),2)

def convert(row,counts):
    temp,tqc=numeric_component(row.get("temperature_raw"),0,1,10,9999,-93.2,61.8,counts,"temperature_c")
    dew,dqc=numeric_component(row.get("dewpoint_raw"),0,1,10,9999,-98.2,50,counts,"dewpoint_c")
    wind,wqc=numeric_component(row.get("wind_raw"),3,4,10,9999,0,100,counts,"wind_speed_mps")
    direction,wdqc=numeric_component(row.get("wind_raw"),0,1,1,999,0,360,counts,"wind_direction_deg")
    slp,pqc=numeric_component(row.get("pressure_raw"),0,1,10,99999,860,1090,counts,"sea_level_pressure_hpa")
    vis,vqc=numeric_component(row.get("visibility_raw"),0,1,1,999999,0,160000,counts,"visibility_m")
    rain=None;rain_qc=""
    precip=(row.get("precip_aa1_raw") or "").split(",")
    if precip and precip[0]=="01":
        rain,rain_qc=numeric_component(row.get("precip_aa1_raw"),1,3,10,9999,0,1000,counts,"precip_1h_mm")
    else:counts["precip_1h_mm"]["no_1h_report"]+=1
    humidity=humidity_percent(temp,dew,counts)
    values=dict(station_id=row["station_id"],year=row["hour_utc"][:4],
                observed_at_utc=row["time_utc"],hour_utc=row["hour_utc"],
                offset_minutes=row["offset_minutes"],
                temperature_c=temp,temperature_qc=tqc,dewpoint_c=dew,dewpoint_qc=dqc,
                relative_humidity_pct=humidity,
                wind_speed_mps=wind,wind_speed_qc=wqc,
                wind_direction_deg=direction,wind_direction_qc=wdqc,
                sea_level_pressure_hpa=slp,sea_level_pressure_qc=pqc,
                visibility_m=vis,visibility_qc=vqc,
                precip_1h_mm=rain,precip_1h_qc=rain_qc)
    return {k:("" if v is None else v) for k,v in values.items()}

def parse_utc(value):
    t=datetime.fromisoformat(value.replace("Z","+00:00"))
    if t.tzinfo is None:t=t.replace(tzinfo=timezone.utc)
    return t.astimezone(timezone.utc)

def validate_time(row,station,year,previous):
    if row.get("station_id")!=station:raise ValueError("Station mismatch")
    hour=parse_utc(row["hour_utc"])
    actual=parse_utc(row["time_utc"])
    if actual.year!=year or hour.year!=year:raise ValueError("Observation out of source year")
    if hour.minute or hour.second or hour.microsecond:raise ValueError("Invalid nominal UTC hour")
    offset=(actual-hour).total_seconds()/60
    if not -30<=offset<=30:raise ValueError("Observation more than 30 minutes from UTC hour")
    if abs(offset-float(row["offset_minutes"]))>0.01:raise ValueError("Minute offset inconsistent")
    if previous is not None and hour<=previous:raise ValueError("Duplicate or unsorted station-hour")
    return hour

def audited_year(path,station,year,writer,source=None):
    counts=defaultdict(Counter);n=0;kept=0;exact=0;offhour=0
    interior_missing=0;longest_missing=0;first=None;last=None
    p=Path(path)
    with gzip.open(p,"rt",newline="",encoding="utf-8") as f:
        reader=csv.DictReader(f)
        if not reader.fieldnames or not OBS_REQUIRED.issubset(reader.fieldnames):
            raise ValueError("Missing v2 archive fields: "+str(p))
        for row in reader:
            hour=validate_time(row,station,year,last)
            n+=1
            if first is None:first=hour
            if last is not None:
                gap=int((hour-last).total_seconds()/3600)-1
                interior_missing+=gap
                longest_missing=max(longest_missing,gap)
            last=hour
            exact+=row["offset_minutes"] in ("0","0.0","0.000")
            offhour+=row["offset_minutes"] not in ("0","0.0","0.000")
            normalized=convert(row,counts)
            if any(normalized[k]!="" for k in MEASURES):
                writer.writerow(normalized);kept+=1
            else:counts["row"]["all_metrics_rejected"]+=1
    expected=int((datetime(year+1,1,1,tzinfo=timezone.utc)-
                  datetime(year,1,1,tzinfo=timezone.utc)).total_seconds()/3600)
    if n>expected:raise ValueError("More hourly points than possible calendar hours")
    return {"station_id":station,"year":year,"status":"audited","rows":n,
            "normalized_rows":kept,"exact_hour_rows":exact,"off_hour_rows":offhour,
            "expected_calendar_hours":expected,"coverage_fraction":round(n/expected,6),
            "missing_calendar_hours":expected-n,
            "missing_interior_hours":interior_missing,"longest_interior_gap_hours":longest_missing,
            "first_hour_utc":first.isoformat() if first else None,
            "last_hour_utc":last.isoformat() if last else None,
            "source_file":p.name,"source_sha256":(source or {}).get("source_sha256"),
            "valid_metrics":{name:counts[name].get("accepted",0) for name in MEASURES},
            "qc_audit":{name:dict(values) for name,values in counts.items()}}

def run_shard(input_dir,output_dir,shard):
    source=Path(input_dir);output=Path(output_dir);output.mkdir(parents=True,exist_ok=True)
    report=json.loads((source/"collection-status.json").read_text())
    results=report["results"]
    if len(results)!=500:raise ValueError("Shard must hold exactly 500 station-year requests")
    if report.get("hourly_selection")!="nearest":raise ValueError("Not a v2 nearest-hour archive")
    inventory=json.loads((source/"stations.json").read_text())
    stations={s["id"]:s for s in inventory["stations"]}
    by_year=[];summary={"shard":shard,"requested_years":0,"audited_years":0,
        "missing_years":0,"row_count":0,"normalized_rows":0,"hourly_points":0,
        "possible_calendar_hours":0,"off_hour_rows":0,
        "metrics_valid":Counter(),"issues":Counter()}
    normalized_path=output/f"normalized-shard-{shard:02d}.csv.gz"
    with gzip.open(normalized_path,"wt",newline="",encoding="utf-8",compresslevel=6) as out:
        writer=csv.DictWriter(out,fieldnames=FIELDS);writer.writeheader()
        for item in results:
            station=item["station"];year=int(item["year"])
            if station not in stations:raise ValueError("Unknown station in inventory")
            summary["requested_years"]+=1
            if item["status"]=="missing":
                summary["missing_years"]+=1
                by_year.append({"station_id":station,"year":year,"status":"source_missing","rows":0,
                                "expected_calendar_hours":(8784 if year%4==0 else 8760)})
                continue
            if item["status"] not in ("saved","reused"):
                raise ValueError("Unanticipated collection status "+item["status"])
            name=f"{year}_{station}.csv.gz"
            path=source/name
            if not path.is_file():raise FileNotFoundError(str(path))
            info=audited_year(path,station,year,writer,source=item)
            if info["rows"]!=item.get("rows",info["rows"]):
                raise ValueError("Row count differs from source manifest: "+name)
            info["country"]=stations[station].get("country")
            info["lat"]=stations[station].get("lat")
            info["lon"]=stations[station].get("lon")
            by_year.append(info)
            summary["audited_years"]+=1
            summary["row_count"]+=info["rows"]
            summary["normalized_rows"]+=info["normalized_rows"]
            summary["hourly_points"]+=info["rows"]
            summary["off_hour_rows"]+=info["off_hour_rows"]
            for metric,count in info["valid_metrics"].items():summary["metrics_valid"][metric]+=count
            for metric,reasons in info["qc_audit"].items():
                for reason,num in reasons.items():
                    if reason!="accepted":summary["issues"][metric+":"+reason]+=num
    for entry in by_year:
        summary["possible_calendar_hours"]+=entry["expected_calendar_hours"]
    if summary["requested_years"]!=500:raise ValueError("Incomplete audit")
    summary["metrics_valid"]=dict(summary["metrics_valid"])
    summary["issues"]=dict(summary["issues"])
    summary["coverage_fraction"]=round(summary["hourly_points"]/summary["possible_calendar_hours"],6)
    summary["data_availability"]="unknown: NOAA ISD does not provide per-observation publication times"
    summary["derived_data_not_original_noaa"]=True
    (output/f"quality-report-{shard:02d}.json").write_text(json.dumps({
        "schema_version":1,"source_release":"atmos-noaa-observations-2006-2025-v2",
        "source_format_document":DOC,"quality_flags_accepted":sorted(GOOD_QC),
        "humidity_method":"Magnus, derived, approximate; over-ice caveat",
        "no_interpolation":True,"summary":summary,"station_years":by_year},indent=2)+"\n")
    print(json.dumps(summary,indent=2),flush=True)
    return summary

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--input-dir",required=True)
    parser.add_argument("--output-dir",required=True)
    parser.add_argument("--shard",type=int,required=True)
    args=parser.parse_args()
    if not 0<=args.shard<40:parser.error("shard must be 0..39")
    run_shard(args.input_dir,args.output_dir,args.shard)
if __name__=="__main__":main()
