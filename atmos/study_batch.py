"""First-year observation coverage audit. NOT a historical forecast backtest."""
import argparse, csv, json, math, time
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

START=date(2016,10,30)
END=date(2026,10,29)
FIELDS="temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max"
def locations():
    for i in range(200):
        z=1-2*(i+.5)/200
        yield {"id":f"P{i+1:03d}","lat":round(math.degrees(math.asin(z)),5),
               "lon":round(((math.degrees(i*math.pi*(3-math.sqrt(5)))+180)%360)-180,5)}
def year_window(batch):
    if not 0<=batch<=9: raise ValueError("Batch must be 0 through 9")
    start=date(2016+batch,10,30)
    end=min(date(2017+batch,10,29),END)
    return start,end
def request(loc,start,end):
    args={"latitude":loc["lat"],"longitude":loc["lon"],
          "start_date":start.isoformat(),"end_date":end.isoformat(),
          "daily":FIELDS,"timezone":"UTC"}
    url="https://archive-api.open-meteo.com/v1/archive?"+urlencode(args)
    for attempt in range(4):
        try:
            with urlopen(Request(url,headers={"User-Agent":"ArcherAtmosResearch/0.4"}),timeout=55) as response:
                result=json.load(response)
            if "daily" not in result: raise ValueError("No daily archive")
            return result,url
        except Exception:
            if attempt==3: raise
            time.sleep(2**attempt*4)
def run(batch,output,limit=200):
    start,end=year_window(batch)
    root=Path(output);root.mkdir(parents=True,exist_ok=True)
    path=root/f"observations_batch_{batch:02d}.csv"
    summary={"batch":batch,"start":start.isoformat(),"end":end.isoformat(),
             "source":"Open-Meteo historical archive; gridded/model-derived, not independent station truth",
             "status":"observation coverage audit ONLY; no forecast skill computed",
             "locations_attempted":0,"locations_succeeded":0,"location_errors":[]}
    with path.open("w",newline="") as f:
        w=csv.writer(f)
        w.writerow(["location_id","latitude","longitude","date_utc","temp_max_c",
                    "temp_min_c","precip_mm","wind_max_kmh","source"])
        for loc in list(locations())[:limit]:
            summary["locations_attempted"]+=1
            try:
                data,url=request(loc,start,end)
                daily=data["daily"];days=daily.get("time",[])
                for i,day in enumerate(days):
                    values=[daily.get(field,[])[i] if i<len(daily.get(field,[])) else None
                            for field in FIELDS.split(",")]
                    w.writerow([loc["id"],loc["lat"],loc["lon"],day,*values,"open-meteo-archive"])
                summary["locations_succeeded"]+=1
            except Exception as exc:
                summary["location_errors"].append({"id":loc["id"],"error":str(exc)[:180]})
            f.flush()
            time.sleep(.25)
    (root/f"summary_batch_{batch:02d}.json").write_text(json.dumps(summary,indent=2))
    if summary["locations_succeeded"]==0: raise RuntimeError("No locations collected")
    return summary
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--batch",type=int,default=0)
    p.add_argument("--limit",type=int,default=200)
    p.add_argument("--output",default="study-results")
    a=p.parse_args()
    if not 1<=a.limit<=200: p.error("limit must be 1-200")
    print(json.dumps(run(a.batch,a.output,a.limit),indent=2))
