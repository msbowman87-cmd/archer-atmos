"""Pilot: verify archived day-ahead model forecasts against gridded reanalysis.
This is NOT an independent-station validation or a 10-year forecast backtest.
Open-Meteo previous-runs API documents _previous_day1 as a 24h lead-time series.
"""
import argparse,csv,json,time
from datetime import date,timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from atmos.study_batch import locations
from atmos.verify import metrics

def fetch(base,args):
    url=base+"?"+urlencode(args)
    for attempt in range(4):
        try:
            with urlopen(Request(url,headers={"User-Agent":"ArcherAtmosResearch/0.5"}),timeout=90) as r:
                data=json.load(r)
            if "error" in data: raise ValueError(str(data)[:300])
            return data
        except Exception:
            if attempt==3: raise
            time.sleep(3*(2**attempt))

def run(start,end,count,out):
    root=Path(out);root.mkdir(parents=True,exist_ok=True)
    rows=[]; failures=[]
    for loc in list(locations())[:count]:
        common={"latitude":loc["lat"],"longitude":loc["lon"],
                "start_date":start.isoformat(),"end_date":end.isoformat(),
                "timezone":"UTC"}
        try:
            fc=fetch("https://previous-runs-api.open-meteo.com/v1/forecast",
                {**common,"daily":"temperature_2m_max_previous_day1,precipitation_sum_previous_day1"})
            obs=fetch("https://archive-api.open-meteo.com/v1/archive",
                {**common,"daily":"temperature_2m_max,precipitation_sum"})
            f=fc["daily"];o=obs["daily"]
            dates={day:i for i,day in enumerate(o["time"])}
            for i,day in enumerate(f["time"]):
                if day not in dates: continue
                j=dates[day]
                temp=f["temperature_2m_max_previous_day1"][i]
                rain=f["precipitation_sum_previous_day1"][i]
                ot=o["temperature_2m_max"][j];orr=o["precipitation_sum"][j]
                if any(x is None for x in (temp,rain,ot,orr)): continue
                rows.append({"location":loc["id"],"date":day,"issue_time":day+"T00:00:00",
                             "valid_time":day+"T23:59:59","horizon_hours":24,
                             "predicted_temp_c":temp,"observed_temp_c":ot,
                             "predicted_rain_mm":rain,"observed_rain_mm":orr})
        except Exception as exc:
            failures.append({"location":loc["id"],"error":str(exc)[:300]})
        time.sleep(.4)
    with (root/"paired_forecasts.csv").open("w",newline="") as f:
        fields=["location","date","issue_time","valid_time","horizon_hours","predicted_temp_c",
                "observed_temp_c","predicted_rain_mm","observed_rain_mm"]
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    report={"status":"pilot verification only","forecast_source":"Open-Meteo Previous Runs API, previous_day1",
            "reference_source":"Open-Meteo historical archive, model-derived; not independent observations",
            "caveat":"Previous-day1 daily aggregate is a 24h lead-time model series, not necessarily a single fixed issuance daily forecast. Issue_time in CSV is a synthetic placeholder and MUST NOT be used to assert issuance provenance.",
            "start":str(start),"end":str(end),"locations_requested":count,
            "locations_with_data":len(set(r["location"] for r in rows)),
            "matched_days":len(rows),"failures":failures,
            "metrics":metrics(rows) if rows else {}}
    (root/"pilot_report.json").write_text(json.dumps(report,indent=2))
    if len(rows)<count*7: raise RuntimeError("Insufficient paired records; inspect report")
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--days",type=int,default=30)
    p.add_argument("--locations",type=int,default=10)
    p.add_argument("--output",default="verification-results")
    a=p.parse_args()
    if not 7<=a.days<=90 or not 1<=a.locations<=200: p.error("invalid scope")
    end=date.today()-timedelta(days=7)
    print(json.dumps(run(end-timedelta(days=a.days-1),end,a.locations,a.output),indent=2))
