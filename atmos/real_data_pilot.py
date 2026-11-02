"""Bounded real-source pilot: archived lead-48h GFS forecasts vs independent NOAA ISD readings.

DO NOT represent this as certified skill: Open-Meteo previous_day2 is a
fixed-lead archived value, not an identified initialization cycle; NOAA ISD
publication timestamps are not recorded. A conservative 72-hour release
delay is ASSUMED, not independently verified.
"""
import csv,io,json,hashlib,re,urllib.request
from datetime import datetime,timedelta,timezone
from pathlib import Path
from urllib.parse import urlencode
from atmos.walk_forward import run

STATIONS=[
 ("denver","72565003017",39.8466,-104.6562),
 ("new_york_jfk","74486094789",40.6398,-73.7789),
 ("seattle","72793024233",47.4447,-122.3134),
]
YEAR=2024
START="2024-03-01"
END="2024-04-30"
UA="Archer-Atmos-Research/0.1 (noncommercial pilot)"

def download(url,limit=15_000_000):
    req=urllib.request.Request(url,headers={"User-Agent":UA})
    with urllib.request.urlopen(req,timeout=35) as resp:
        raw=resp.read(limit+1)
        if len(raw)>limit:raise RuntimeError("Download exceeds pilot size cap")
        return raw

def noaa_hourly(station):
    _,code,_,_=station
    url=f"https://noaa-isd-pds.s3.amazonaws.com/{YEAR}/{code}.csv"
    raw=download(url)
    digest=hashlib.sha256(raw).hexdigest()
    reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    found={}
    for record in reader:
        dt=record.get("DATE","")
        if not (START<=dt[:10]<=END):continue
        # Require a top-of-hour reading. It is an instantaneous air-temperature
        # observation, not an hourly average or 24-hour daily maximum.
        try: stamp=datetime.fromisoformat(dt.replace("Z","+00:00"))
        except ValueError:continue
        if stamp.minute!=0 or stamp.second!=0:continue
        value=record.get("TMP","")
        m=re.fullmatch(r'([+-]?\d+),(\d)',value)
        if not m:continue
        temp=int(m.group(1))/10
        qc=m.group(2)
        if qc not in ("0","1","4","5","9") or temp<-90 or temp>60 or abs(temp)>=999:continue
        stamp=stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)
        found[stamp.strftime("%Y-%m-%dT%H:%M")]=temp
    return found,{"source":url,"sha256":digest,"observations":len(found)}

def archived_forecasts(station):
    _,_,lat,lon=station
    params=urlencode({"latitude":lat,"longitude":lon,"hourly":"temperature_2m_previous_day2",
                     "start_date":START,"end_date":END,"timezone":"UTC","models":"gfs_global"})
    url="https://previous-runs-api.open-meteo.com/v1/forecast?"+params
    raw=download(url)
    payload=json.loads(raw)
    if payload.get("error"):raise RuntimeError("Provider error: "+str(payload.get("reason")))
    hourly=payload.get("hourly") or {}
    times=hourly.get("time") or []
    values=hourly.get("temperature_2m_previous_day2") or []
    if len(times)!=len(values) or not times:raise RuntimeError("Invalid previous-runs hourly response")
    return dict(zip(times,values)),{"source":url,"sha256":hashlib.sha256(raw).hexdigest(),"forecast_hours":len(times)}

def main():
    out=Path("pilot-results");out.mkdir(exist_ok=True)
    predictions=[];observations=[];sources=[];errors=[]
    for site in STATIONS:
        name=site[0]
        try:
            measured,meta=noaa_hourly(site)
            forecast,fmeta=archived_forecasts(site)
            sources.append({"station":name,"observations":meta,"forecast":fmeta})
            n=0
            for time,reading in measured.items():
                value=forecast.get(time)
                if value is None:continue
                valid=datetime.fromisoformat(time).replace(tzinfo=timezone.utc)
                issued=valid-timedelta(days=2)
                # Two-minute matching windows represent a point-reading
                # at the exact valid instant. No daily aggregate is implied.
                beg=valid.isoformat();end=(valid+timedelta(minutes=2)).isoformat()
                predictions.append(dict(location_id=name,model="gfs",issue_at_utc=issued.isoformat(),
                    valid_start_utc=beg,valid_end_utc=end,metric="temp_2m",unit="C",value=str(value)))
                observations.append(dict(location_id=name,available_at_utc=(valid+timedelta(hours=72)).isoformat(),
                    valid_start_utc=beg,valid_end_utc=end,metric="temp_2m",unit="C",
                    value=str(reading),independent="true",quality_flag="verified"))
                n+=1
            sources[-1]["pairs"]=n
        except Exception as exc:
            errors.append({"station":name,"error":str(exc)[:300]})
    if not predictions:
        (out/"collection-status.json").write_text(json.dumps({"status":"no_source_pairs","sources":sources,"errors":errors},indent=2))
        raise SystemExit("No independent forecast/observation pairs were collected")
    for path,records in [("forecasts.csv",predictions),("observations.csv",observations)]:
        with (out/path).open("w",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=records[0].keys());writer.writeheader();writer.writerows(records)
    result=run(predictions,observations,min_training=30,holdout_start="2024-04-01T00:00:00Z")
    (out/"walk-forward.json").write_text(json.dumps(result,indent=2))
    manifest={"status":"exploratory_real_observation_pilot","source_records":sources,"errors":errors,
        "paired_cases":len(predictions),"training_report_status":result["status"],
        "limits":["3 stations, 61 days; NOT 100-station 1-year dataset",
          "ISD source is independent real station data but release times not known; 72h lag is assumed",
          "Open-Meteo fixed 48h offset is not a verified cycle initiation or model publish time",
          "2-minute nominal interval represents point readings, not true hourly aggregates",
          "No claims of production/generalizable skill; no deployment to website"]}
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2))
    print(json.dumps({**manifest,"raw_mae":result["raw_mae"],"calibrated_mae":result["calibrated_mae"]},indent=2))
if __name__=="__main__":main()
