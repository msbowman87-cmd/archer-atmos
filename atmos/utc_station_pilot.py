"""UTC-aligned ASOS temperature pilot; observed maxima are sampled, not certified daily extremes."""
import argparse,csv,io,json
from collections import defaultdict
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from atmos.station_backtest import forecasts,save
from atmos.paired_comparison import compare

STATIONS={
 "TWF":("ID_ASOS",42.4818,-114.4877),
 "BOI":("ID_ASOS",43.5644,-116.2228),
 "PIH":("ID_ASOS",42.9098,-112.5959),
}
def utc_observations(station,network,start,end,fetch=None,min_hours=20):
    """Only UTC days with >= min_hours distinct hourly bins; temperature only."""
    if fetch is None:
        def fetch(url):
            with urlopen(url,timeout=90) as r:return r.read().decode("utf-8")
    finish=end+timedelta(days=1)
    params={"station":station,"data":"tmpf","year1":start.year,"month1":start.month,
        "day1":start.day,"year2":finish.year,"month2":finish.month,"day2":finish.day,
        "tz":"UTC","format":"onlycomma","latlon":"no","elev":"no",
        "missing":"M","trace":"T","direct":"no","report_type":"3"}
    url="https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?"+urlencode(params)
    raw=fetch(url)
    rows=csv.DictReader(io.StringIO(raw))
    if rows.fieldnames is None:raise RuntimeError("ASOS response has no CSV header")
    rows.fieldnames=[x.strip().lstrip("\\ufeff") for x in rows.fieldnames]
    print("ASOS",station,"columns",rows.fieldnames,"response_bytes",len(raw),flush=True)
    hours=defaultdict(set)
    temperatures=defaultdict(list)
    for row in rows:
        if row.get("station","").strip().upper()!=station.upper():continue
        stamp=(row.get("valid") or "").strip().replace("T"," ").replace("Z","")
        value=(row.get("tmpf") or "").strip()
        if not stamp or value in ("","M","None","null"):continue
        try:
            ts=datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc)
            temp=(float(value)-32)*5/9
        except ValueError:continue
        day=ts.date()
        if not start<=day<=end:continue
        hours[day].add(ts.hour)
        temperatures[day].append(temp)
    print("ASOS",station,"UTC days found",len(temperatures),"coverage",sorted((str(d),len(h)) for d,h in hours.items())[:5],flush=True)
    return [{"station_id":station,"date":d.isoformat(),
        "observed_temp_max_c":str(max(temperatures[d])),
        "observed_precip_mm":"","utc_hours_covered":str(len(hours[d]))}
        for d in sorted(temperatures) if len(hours[d])>=min_hours]

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--start",default="2026-08-01")
    p.add_argument("--end",default="2026-09-30")
    p.add_argument("--split",default="2026-09-01")
    p.add_argument("--stations",default="TWF,BOI,PIH")
    p.add_argument("--output",default="utc-station-results")
    a=p.parse_args()
    start,end=date.fromisoformat(a.start),date.fromisoformat(a.end)
    root=Path(a.output);root.mkdir(parents=True,exist_ok=True)
    summary={}
    for station in a.stations.split(","):
        station=station.strip()
        network,lat,lon=STATIONS[station]
        obs=utc_observations(station,network,start,end)
        fc=forecasts(station,lat,lon,"UTC",start,end)
        dest=root/station;dest.mkdir(exist_ok=True)
        save(dest/"observations.csv",obs,["station_id","date","observed_temp_max_c","observed_precip_mm","utc_hours_covered"])
        save(dest/"forecasts.csv",fc,["station_id","date","issue_date","forecast_temp_max_c","forecast_precip_mm"])
        if not obs or not fc:
            summary[station]={"status":"insufficient_data","observed_days":len(obs),"forecast_rows":len(fc)}
            continue
        try:
            result=compare(fc,obs,a.split)
            result["status"]="exploratory_sampled_utc_temperature"
            result["observed_days"]=len(obs)
            result["forecast_rows"]=len(fc)
            result["limitations"]=["ASOS sampled hourly temperature maximum may miss true daily maximum",
                "UTC observation and forecast dates aligned; sampling coverage threshold >=20 hours",
                "Station-specific skill only; forecast initialization not publication time",
                "No independent precipitation, severe weather, or 15-30 day verification"]
        except ValueError as e:
            result={"status":"insufficient_data","reason":str(e)}
        (dest/"comparison.json").write_text(json.dumps(result,indent=2))
        summary[station]=result
    (root/"summary.json").write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))
    if not any(v.get("status")=="exploratory_sampled_utc_temperature" for v in summary.values()):
        raise RuntimeError("No valid UTC-aligned station comparisons")
if __name__=="__main__":main()
