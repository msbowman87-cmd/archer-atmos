"""Leakage-conscious, location-specific adaptive temperature correction.

A correction is enabled only if it improves a separate validation period;
final test dates are never used to choose or fit it.
"""
from collections import defaultdict
from datetime import date
from math import sqrt

def bucket(f):
    lead=(date.fromisoformat(f["date"])-date.fromisoformat(f["issue_date"])).days
    return "1-7" if 1<=lead<=7 else "8-14" if 8<=lead<=14 else "15-30" if 15<=lead<=30 else None

def evaluate(forecasts,observations,train_end,validation_end,*,min_train=20,min_validation=10):
    if not train_end<validation_end:raise ValueError("Training must end before validation")
    obs={(r["station_id"],r["date"]):r for r in observations}
    if len(obs)!=len(observations):raise ValueError("Duplicate observations")
    groups=defaultdict(lambda:{"train":[],"validation":[],"test":[]})
    seen=set()
    for f in forecasts:
        k=(f["station_id"],f["date"],f["issue_date"])
        if k in seen:raise ValueError("Duplicate forecast")
        seen.add(k)
        o=obs.get(k[:2]);b=bucket(f)
        if not o or not b:continue
        if f.get("forecast_temp_max_c") in (None,"") or o.get("observed_temp_max_c") in (None,""):continue
        period="train" if f["date"]<train_end else "validation" if f["date"]<validation_end else "test"
        groups[(f["station_id"],b)][period].append((float(f["forecast_temp_max_c"]),float(o["observed_temp_max_c"])))
    result={}
    for (station,b),splits in sorted(groups.items()):
        tr,va,te=(splits[p] for p in ("train","validation","test"))
        key=station+"/"+b
        if len(tr)<min_train or len(va)<min_validation or not te:
            result[key]={"status":"insufficient_data","training_pairs":len(tr),
                         "validation_pairs":len(va),"test_pairs":len(te)}
            continue
        bias=sum(p-o for p,o in tr)/len(tr)
        mae=lambda pairs,correction:sum(abs(p-correction-o) for p,o in pairs)/len(pairs)
        validation_raw=mae(va,0)
        validation_corrected=mae(va,bias)
        enabled=validation_corrected<validation_raw
        raw=mae(te,0)
        adapted=mae(te,bias if enabled else 0)
        result[key]={"status":"evaluated","training_pairs":len(tr),"validation_pairs":len(va),
            "test_pairs":len(te),"trained_bias_c":bias,"enabled_on_validation":enabled,
            "validation_raw_mae_c":validation_raw,"validation_corrected_mae_c":validation_corrected,
            "test_raw_mae_c":raw,"test_adaptive_mae_c":adapted,
            "test_improvement_pct":100*(raw-adapted)/raw if raw else None}
    return {"train_end_exclusive":train_end,"validation_end_exclusive":validation_end,
      "method":"per-station lead-bucket train-only mean bias; validation-only enablement",
      "results":result,
      "limitations":["Requires independently verified identical forecast and observation UTC intervals",
        "Same-day forecasts from different issues are correlated; confidence intervals not yet calculated",
        "Selection on a short validation period can overfit; no production deployment justified"]}
