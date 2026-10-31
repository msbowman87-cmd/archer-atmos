"""Independent, multi-variable weather forecast verification.

Requires observations aggregated to exactly the forecast's valid interval.
Does not assume all variables are equally predictable or that one station generalizes.
"""
from collections import defaultdict
from datetime import date
from math import sqrt, isfinite

METRICS={
 "temp_max_c":("forecast_temp_max_c","observed_temp_max_c"),
 "temp_min_c":("forecast_temp_min_c","observed_temp_min_c"),
 "temp_mean_c":("forecast_temp_mean_c","observed_temp_mean_c"),
 "precip_mm":("forecast_precip_mm","observed_precip_mm"),
 "wind_max_ms":("forecast_wind_max_ms","observed_wind_max_ms"),
 "wind_gust_ms":("forecast_wind_gust_ms","observed_wind_gust_ms"),
 "humidity_pct":("forecast_humidity_pct","observed_humidity_pct"),
 "pressure_hpa":("forecast_pressure_hpa","observed_pressure_hpa"),
 "cloud_pct":("forecast_cloud_pct","observed_cloud_pct"),
 "snowfall_cm":("forecast_snowfall_cm","observed_snowfall_cm"),
 "visibility_m":("forecast_visibility_m","observed_visibility_m"),
 "solar_radiation_mj_m2":("forecast_solar_radiation_mj_m2","observed_solar_radiation_mj_m2"),
}
def score(forecasts,observations,*,aligned_intervals=False,precip_threshold_mm=1.0):
    if not aligned_intervals:
        raise ValueError("Forecast and observation time intervals must be aligned and verified before scoring")
    obs={}
    for o in observations:
        k=(o["station_id"],o["date"])
        if k in obs:raise ValueError("Duplicate observation "+str(k))
        obs[k]=o
    groups=defaultdict(lambda:defaultdict(list))
    events=defaultdict(list)
    unmatched=0
    seen=set()
    for f in forecasts:
        k=(f["station_id"],f["date"],f["issue_date"])
        if k in seen:raise ValueError("Duplicate forecast "+str(k))
        seen.add(k)
        lead=(date.fromisoformat(f["date"])-date.fromisoformat(f["issue_date"])).days
        if not 1<=lead<=30:raise ValueError("Forecast lead outside 1-30 days")
        o=obs.get(k[:2])
        if o is None:
            unmatched+=1
            continue
        bucket="1-7" if lead<=7 else "8-14" if lead<=14 else "15-30"
        for metric,(fc,ob) in METRICS.items():
            a,b=f.get(fc,""),o.get(ob,"")
            if a in ("",None) or b in ("",None):continue
            a,b=float(a),float(b)
            if not (isfinite(a) and isfinite(b)):continue
            groups[bucket][metric].append((a,b))
            if metric=="precip_mm":
                events[bucket].append((a>=precip_threshold_mm,b>=precip_threshold_mm))
    out={}
    for bucket in ("1-7","8-14","15-30"):
        result={}
        for metric,pairs in groups[bucket].items():
            errors=[a-b for a,b in pairs]
            n=len(errors)
            result[metric]={"pairs":n,"mae":sum(map(abs,errors))/n,
                "bias":sum(errors)/n,"rmse":sqrt(sum(e*e for e in errors)/n)}
        if events[bucket]:
            tp=sum(a and b for a,b in events[bucket])
            fp=sum(a and not b for a,b in events[bucket])
            fn=sum(not a and b for a,b in events[bucket])
            tn=sum(not a and not b for a,b in events[bucket])
            result["precip_event"]={"threshold_mm":precip_threshold_mm,"hits":tp,
              "false_alarms":fp,"misses":fn,"correct_negatives":tn,
              "precision":tp/(tp+fp) if tp+fp else None,
              "recall":tp/(tp+fn) if tp+fn else None}
        out[bucket]=result
    return {"forecast_rows":len(forecasts),"unmatched_rows":unmatched,
       "interval_alignment_verified":True,"by_lead_days":out,
       "warning":"Scores describe the provided forecasts only; no Atmos improvement or global skill is implied."}
