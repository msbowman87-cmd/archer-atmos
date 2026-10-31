"""Sharded worldwide archived-forecast comparison; coverage gaps are explicit.
No independent station verification and no invented issuance timestamps.
"""
import argparse,csv,json,time
from datetime import date,timedelta
from pathlib import Path
from atmos.study_batch import locations,START,END
from atmos.forecast_pilot import fetch

FIELDS=["location","date","lead_hours_nominal","predicted_temp_c","observed_temp_c","predicted_rain_mm","observed_rain_mm"]
def windows(start,end,days=45):
    while start<=end:
        stop=min(end,start+timedelta(days=days-1))
        yield start,stop
        start=stop+timedelta(days=1)
def run(year,shard,output):
    if year not in range(2016,2027) or shard not in range(10): raise ValueError("Invalid shard/year")
    start=max(START,date(year,1,1));end=min(END,date(year,12,31))
    root=Path(output);root.mkdir(parents=True,exist_ok=True)
    locs=list(locations())[shard*20:(shard+1)*20]
    results=[];failures=[];missing=0;requests=0
    for loc in locs:
        for begin,finish in windows(start,end):
            common={"latitude":loc["lat"],"longitude":loc["lon"],"start_date":str(begin),
                    "end_date":str(finish),"timezone":"UTC"}
            requests+=1
            try:
                fc=fetch("https://previous-runs-api.open-meteo.com/v1/forecast",
                    {**common,"hourly":"temperature_2m_previous_day1,precipitation_previous_day1"})
                obs=fetch("https://archive-api.open-meteo.com/v1/archive",
                    {**common,"daily":"temperature_2m_max,precipitation_sum"})
                h=fc["hourly"];o=obs["daily"]
                forecast={}
                for i,t in enumerate(h["time"]):
                    day=t[:10];b=forecast.setdefault(day,[[],[]])
                    tval=h["temperature_2m_previous_day1"][i]
                    pval=h["precipitation_previous_day1"][i]
                    if tval is not None:b[0].append(tval)
                    if pval is not None:b[1].append(pval)
                od={day:i for i,day in enumerate(o["time"])}
                for day in (begin+timedelta(days=i) for i in range((finish-begin).days+1)):
                    ds=str(day);b=forecast.get(ds);j=od.get(ds)
                    if b is None or j is None or len(b[0])!=24 or len(b[1])!=24:
                        missing+=1;continue
                    ot=o["temperature_2m_max"][j];op=o["precipitation_sum"][j]
                    if ot is None or op is None:missing+=1;continue
                    results.append([loc["id"],ds,24,max(b[0]),ot,sum(b[1]),op])
            except Exception as exc:
                failures.append({"location":loc["id"],"start":str(begin),"end":str(finish),"error":str(exc)[:250]})
                missing+=(finish-begin).days+1
            time.sleep(.3)
    with (root/f"pairs_{year}_shard_{shard}.csv").open("w",newline="") as f:
        w=csv.writer(f);w.writerow(FIELDS);w.writerows(results)
    n=len(results);temp=sum(abs(r[3]-r[4]) for r in results)/n if n else None
    rain=sum(abs(r[5]-r[6]) for r in results)/n if n else None
    report={"year":year,"shard":shard,"locations":len(locs),"expected_days":len(locs)*((end-start).days+1),
        "matched_days":n,"missing_days":missing,"request_windows":requests,
        "temperature_mae_c":temp,"precipitation_mae_mm":rain,"failures":failures,
        "forecast_source":"Open-Meteo Previous Runs hourly _previous_day1",
        "reference_source":"Open-Meteo archive model-derived reanalysis; NOT independent station truth",
        "interpretation":"Nominal 24-hour lead hourly forecast series aggregated by UTC day; not a single fixed issue-time forecast"}
    (root/f"report_{year}_shard_{shard}.json").write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!="failures"},indent=2))
    # Missing coverage is reported, not fabricated; a wholly unavailable year is not a successful backtest.
    if n==0:raise RuntimeError("No paired forecast records; check API historical coverage and report")
    return report
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--year",type=int,required=True)
    p.add_argument("--shard",type=int,required=True);p.add_argument("--output",default="global-forecast-results")
    a=p.parse_args();run(a.year,a.shard,a.output)
