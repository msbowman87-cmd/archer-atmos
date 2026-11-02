"""Build a distributed 1,000-station, 20-year NOAA observation archive in bounded shards.

Station selection is globally stratified by occupied 10-degree x 15-degree
lat/lon cells. Coverage of dates in the metadata is a candidate criterion,
NOT proof that all 20 years contain high-quality measurements.

This collector never invents observations or historical forecast issue times.
"""
import argparse,csv,gzip,hashlib,io,json,re,time
from collections import defaultdict
from pathlib import Path
from urllib.error import HTTPError,URLError
from atmos.real_data_pilot import download

CATALOG="https://www.ncei.noaa.gov/pub/data/noaa/isd-history.csv"
YEARS=list(range(2006,2026))
STATION_COUNT=1000
METRICS={"TMP":"temperature_c","DEW":"dewpoint_c","WND":"wind_ms",
         "SLP":"sea_level_pressure_hpa","VIS":"visibility_m"}

def station_manifest():
    raw=download(CATALOG,3_000_000)
    buckets=defaultdict(list)
    for r in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
        try:
            code=r["USAF"]+r["WBAN"]
            lat=float(r["LAT"]);lon=float(r["LON"])
            if len(code)!=11 or r["USAF"]=="999999" or r["WBAN"]=="99999":continue
            if not (-90<=lat<=90 and -180<=lon<=180):continue
            if r.get("BEGIN","")>"20060101" or r.get("END","")<"20250101":continue
            if not (r.get("BEGIN","").isdigit() and r.get("END","").isdigit()):continue
            cell=(min(17,int((lat+90)//10)),min(23,int((lon+180)//15)))
            buckets[cell].append({"id":code,"lat":lat,"lon":lon,"name":r.get("STATION NAME",""),
                                  "country":r.get("CTRY",""),"begin":r["BEGIN"],"end":r["END"],"cell":cell})
        except (ValueError,KeyError):continue
    for values in buckets.values():values.sort(key=lambda x:x["id"])
    selected=[];depth=0
    while len(selected)<STATION_COUNT:
        changed=0
        for cell in sorted(buckets):
            if depth<len(buckets[cell]):
                selected.append(buckets[cell][depth]);changed+=1
                if len(selected)==STATION_COUNT:break
        if not changed:break
        depth+=1
    if len(selected)<STATION_COUNT:raise ValueError(f"Only {len(selected)} eligible catalog stations")
    return selected,hashlib.sha256(raw).hexdigest()

def extract(raw,year,code):
    data=csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    rows=[];seen=set()
    for r in data:
        moment=r.get("DATE","")
        if not moment.startswith(str(year)):continue
        if len(moment)<16 or moment[11:16].split(":")[1]!="00":continue
        # Original observation values and flags retained for later QC.
        # Null/missing sentinel values are not converted into model truth.
        key=(code,moment)
        if key in seen:continue
        seen.add(key)
        rows.append({"station_id":code,"time_utc":moment,"temperature_raw":r.get("TMP",""),
                     "dewpoint_raw":r.get("DEW",""),"wind_raw":r.get("WND",""),
                     "pressure_raw":r.get("SLP",""),"visibility_raw":r.get("VIS",""),
                     "precip_aa1_raw":r.get("AA1",""),"source":"NOAA Global Hourly"})
    return rows

def download_year(year,station,out,retries=2):
    code=station["id"]
    url=f"https://noaa-global-hourly-pds.s3.amazonaws.com/{year}/{code}.csv"
    for attempt in range(retries+1):
        try:
            raw=download(url,40_000_000)
            rows=extract(raw,year,code)
            if not rows:return {"station":code,"year":year,"status":"no_top_of_hour_records","url":url}
            path=out/f"{year}_{code}.csv.gz"
            with gzip.open(path,"wt",newline="") as f:
                w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
            return {"station":code,"year":year,"status":"saved","rows":len(rows),
                    "file":str(path),"source_sha256":hashlib.sha256(raw).hexdigest(),
                    "url":url}
        except (HTTPError,URLError,TimeoutError,ValueError,OSError,RuntimeError) as exc:
            if isinstance(exc,HTTPError) and exc.code==404:
                return {"station":code,"year":year,"status":"missing","error":"404"}
            if attempt==retries:return {"station":code,"year":year,"status":"failed","error":str(exc)[:180]}
            time.sleep(1+attempt)
    raise AssertionError("unreachable")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--station-start",type=int,default=0)
    p.add_argument("--station-count",type=int,default=5)
    p.add_argument("--year-start",type=int,default=2006)
    p.add_argument("--year-end",type=int,default=2025)
    p.add_argument("--output",default="global-archive")
    args=p.parse_args()
    if args.station_start<0 or not 1<=args.station_count<=25 or args.station_start+args.station_count>1000:
        p.error("Use a station index 0-999 with a bounded batch size of 1-25")
    if not 2006<=args.year_start<=args.year_end<=2025:p.error("Year range must be 2006-2025")
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    selected,digest=station_manifest()
    (out/"stations.json").write_text(json.dumps({"catalog_sha256":digest,"selection":"global lat/lon stratification; years not yet audited","stations":selected},indent=2))
    results=[]
    for station in selected[args.station_start:args.station_start+args.station_count]:
        for year in range(args.year_start,args.year_end+1):
            result=download_year(year,station,out)
            results.append(result)
            print(f'{station["id"]} {year}: {result["status"]}',flush=True)
            (out/"collection-status.json").write_text(json.dumps({"requested_station_count":1000,
                "batch_start":args.station_start,"batch_station_count":args.station_count,
                "year_range":[args.year_start,args.year_end],
                "completed_requests":len(results),"successful_year_files":sum(x["status"]=="saved" for x in results),
                "failures":sum(x["status"]=="failed" for x in results),
                "missing":sum(x["status"]=="missing" for x in results),"results":results},indent=2))
    print(json.dumps({"requests":len(results),"saved":sum(x["status"]=="saved" for x in results),
                      "rows":sum(x.get("rows",0) for x in results)},indent=2))
if __name__=="__main__":main()
