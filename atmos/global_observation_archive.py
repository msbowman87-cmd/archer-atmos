"""Build a distributed 1,000-station, 20-year NOAA observation archive in bounded shards.

Station selection is globally stratified by occupied 10-degree x 15-degree
lat/lon cells. Coverage of dates in the metadata is a candidate criterion,
NOT proof that all 20 years contain high-quality measurements.

This collector never invents observations or historical forecast issue times.
"""
import argparse,csv,gzip,hashlib,io,json,re,time,os,tempfile,urllib.request,shutil,random
from collections import defaultdict
from datetime import datetime,timedelta,timezone
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

OUTPUT_COLUMNS=["station_id","time_utc","hour_utc","offset_minutes","temperature_raw",
                "dewpoint_raw","wind_raw","pressure_raw","visibility_raw","precip_aa1_raw","source"]

def select_hourly_observations(records,year,code,mode="nearest"):
    """Choose an ACTUAL reading nearest each UTC hour; never fabricate or retime a measurement.

    The observed instant is preserved in time_utc. hour_utc labels the nearest
    forecast-verification hour, not the time a measurement was made. Only
    observations within 30 minutes qualify; prefer exact observations, and
    choose the earlier reading at equal offsets. No gap filling or averaging.
    """
    if mode not in ("exact","nearest"):raise ValueError("Unknown hourly selection mode")
    best={}
    for raw in records:
        moment=raw.get("DATE","")
        try:
            observed=datetime.fromisoformat(moment.replace("Z","+00:00"))
        except (ValueError,TypeError,AttributeError):continue
        if observed.tzinfo is not None:
            observed=observed.astimezone(timezone.utc).replace(tzinfo=None)
        if observed.year!=year:continue
        floor=observed.replace(minute=0,second=0,microsecond=0)
        hour=floor+(timedelta(hours=1) if observed-floor>timedelta(minutes=30) else timedelta())
        if hour.year!=year:continue
        delta=(observed-hour).total_seconds()/60.0
        if mode=="exact" and delta!=0:continue
        key=hour.isoformat(timespec="seconds")
        score=(abs(delta),0 if delta<=0 else 1,observed,moment)
        if key in best and best[key][0]<=score:continue
        best[key]=(score,{"station_id":code,"time_utc":moment,"hour_utc":key,
            "offset_minutes":round(delta,3),"temperature_raw":raw.get("TMP",""),
            "dewpoint_raw":raw.get("DEW",""),"wind_raw":raw.get("WND",""),
            "pressure_raw":raw.get("SLP",""),"visibility_raw":raw.get("VIS",""),
            "precip_aa1_raw":raw.get("AA1",""),"source":"NOAA Global Hourly"})
    return [best[key][1] for key in sorted(best)]

def extract(raw,year,code,mode="nearest"):
    source=csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    return select_hourly_observations(source,year,code,mode)

def stream_source(url,out_path,limit=250_000_000):
    """Stream response to disk with a firm 250 MB safety cap and SHA-256."""
    req=urllib.request.Request(url,headers={"User-Agent":"Archer-Atmos-Research/0.1"})
    digest=hashlib.sha256();size=0
    with urllib.request.urlopen(req,timeout=75) as response, open(out_path,"wb") as target:
        while True:
            chunk=response.read(1024*1024)
            if not chunk:break
            size+=len(chunk)
            if size>limit:raise ValueError("NOAA source exceeded 250 MB safety ceiling")
            digest.update(chunk);target.write(chunk)
        target.flush();os.fsync(target.fileno())
    return digest.hexdigest()

def download_year(year,station,out,retries=3,hourly_selection="nearest"):
    code=station["id"];url=f"https://noaa-global-hourly-pds.s3.amazonaws.com/{year}/{code}.csv"
    path=out/f"{year}_{code}.csv.gz"
    if path.exists():
        try:
            with gzip.open(path,"rt") as f:
                first=f.readline()
                if "hour_utc" in first and any(True for _ in f):
                    return {"station":code,"year":year,"status":"reused","file":str(path)}
        except (OSError,EOFError,UnicodeError):pass
        path.unlink(missing_ok=True)
    for attempt in range(retries+1):
        source=None;destination=None
        try:
            with tempfile.NamedTemporaryFile(prefix="atmos-source-",suffix=".csv",delete=False) as t:source=t.name
            digest=stream_source(url,source)
            with open(source,"r",encoding="utf-8-sig",newline="") as incoming:
                reader=csv.DictReader(incoming)
                selected=select_hourly_observations(reader,year,code,hourly_selection)
                with tempfile.NamedTemporaryFile(prefix="atmos-output-",suffix=".csv.gz",dir=out,delete=False) as t:
                    destination=t.name
                count=len(selected)
                with gzip.open(destination,"wt",newline="") as target:
                    writer=csv.DictWriter(target,fieldnames=OUTPUT_COLUMNS)
                    writer.writeheader()
                    writer.writerows(selected)
            if not count:
                return {"station":code,"year":year,"status":"no_hourly_observations","url":url}
            os.replace(destination,path);destination=None
            return {"station":code,"year":year,"status":"saved","rows":count,
                    "file":str(path),"source_sha256":digest,"hourly_selection":hourly_selection,"url":url}
        except (HTTPError,URLError,TimeoutError,ValueError,OSError,RuntimeError,UnicodeError) as exc:
            if isinstance(exc,HTTPError) and exc.code==404:
                return {"station":code,"year":year,"status":"missing","error":"404"}
            if attempt==retries:
                return {"station":code,"year":year,"status":"failed","error":str(exc)[:180]}
            time.sleep(min(20,2**attempt+random.random()))
        finally:
            if source:Path(source).unlink(missing_ok=True)
            if destination:Path(destination).unlink(missing_ok=True)
    raise AssertionError("unreachable")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--station-start",type=int,default=0)
    p.add_argument("--station-count",type=int,default=5)
    p.add_argument("--year-start",type=int,default=2006)
    p.add_argument("--year-end",type=int,default=2025)
    p.add_argument("--output",default="global-archive")
    p.add_argument("--hourly-selection",choices=("exact","nearest"),default="nearest")
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
            result=download_year(year,station,out,hourly_selection=args.hourly_selection)
            results.append(result)
            print(f'{station["id"]} {year}: {result["status"]}',flush=True)
            (out/"collection-status.json").write_text(json.dumps({"requested_station_count":1000,
                "batch_start":args.station_start,"batch_station_count":args.station_count,
                "year_range":[args.year_start,args.year_end],
                "hourly_selection":args.hourly_selection,
                "completed_requests":len(results),"successful_year_files":sum(x["status"] in ("saved","reused") for x in results),
                "failures":sum(x["status"]=="failed" for x in results),
                "missing":sum(x["status"]=="missing" for x in results),"results":results},indent=2))
    print(json.dumps({"requests":len(results),"saved":sum(x["status"]=="saved" for x in results),
                      "rows":sum(x.get("rows",0) for x in results)},indent=2))
if __name__=="__main__":main()
