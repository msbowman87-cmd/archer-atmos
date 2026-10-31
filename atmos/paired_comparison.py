"""Chronological, paired baseline-vs-bias-corrected forecast experiment.

No leakage: fit corrections on earlier valid dates, evaluate on later valid dates.
Forecasts and observations must refer to the SAME daily time boundaries.
"""
import argparse,csv,json
from collections import defaultdict
from datetime import date
from pathlib import Path

def compare(forecasts, observations, split_date):
    obs={(r["station_id"],r["date"]):r for r in observations}
    train=defaultdict(list)
    test=[]
    for f in forecasts:
        o=obs.get((f["station_id"],f["date"]))
        if not o or not f["forecast_temp_max_c"] or not o["observed_temp_max_c"]:
            continue
        lead=(date.fromisoformat(f["date"])-date.fromisoformat(f["issue_date"])).days
        if not 1<=lead<=30: continue
        bucket="1-7" if lead<=7 else "8-14" if lead<=14 else "15-30"
        record=(bucket,float(f["forecast_temp_max_c"]),float(o["observed_temp_max_c"]))
        if f["date"]<split_date: train[bucket].append(record)
        else: test.append(record)
    if not train or not test: raise ValueError("Need both historical training dates and later held-out dates")
    bias={k:sum(pred-actual for _,pred,actual in rows)/len(rows) for k,rows in train.items()}
    result={}
    for bucket in ("1-7","8-14","15-30"):
        paired=[(pred,actual) for b,pred,actual in test if b==bucket and b in bias]
        if not paired:
            result[bucket]={"held_out_pairs":0,"status":"insufficient_data"}
            continue
        base=sum(abs(pred-actual) for pred,actual in paired)/len(paired)
        corrected=sum(abs(pred-bias[bucket]-actual) for pred,actual in paired)/len(paired)
        result[bucket]={"training_pairs":len(train[bucket]),"held_out_pairs":len(paired),
          "trained_bias_c":bias[bucket],"baseline_mae_c":base,"corrected_mae_c":corrected,
          "improvement_pct":100*(base-corrected)/base if base else None}
    return {"split_date":split_date,"method":"train-only mean bias correction by lead bucket",
      "by_lead_days":result,
      "caution":"Exploratory only unless model forecast and station observation day boundaries are aligned; not production Atmos model."}

def guarded_comparison(forecasts, observations, split_date, min_days=7):
    """Train / validate / test by valid date; never select a correction using test outcomes."""
    obs={(r["station_id"],r["date"]):r for r in observations}
    rows=defaultdict(list)
    for f in forecasts:
        o=obs.get((f["station_id"],f["date"]))
        if not o or not f["forecast_temp_max_c"] or not o["observed_temp_max_c"]: continue
        lead=(date.fromisoformat(f["date"])-date.fromisoformat(f["issue_date"])).days
        if not 1<=lead<=30: continue
        bucket="1-7" if lead<=7 else "8-14" if lead<=14 else "15-30"
        rows[bucket].append((f["date"],float(f["forecast_temp_max_c"]),float(o["observed_temp_max_c"])))
    result={}
    for bucket,entries in rows.items():
        dates=sorted({d for d,_,_ in entries if d<split_date})
        if len(dates)<min_days*2:
            result[bucket]={"status":"insufficient_training_and_validation_days","correction_weight":0}
            continue
        boundary=dates[len(dates)//2]
        train=[(p,o) for d,p,o in entries if d<boundary]
        validation=[(d,p,o) for d,p,o in entries if boundary<=d<split_date]
        test=[(d,p,o) for d,p,o in entries if d>=split_date]
        if len({d for d,_,_ in validation})<min_days or not test:
            result[bucket]={"status":"insufficient_validation_or_test_days","correction_weight":0}
            continue
        bias=sum(p-o for p,o in train)/len(train)
        baseline=sum(abs(p-o) for _,p,o in validation)/len(validation)
        # Conservative weights; demand improvement on validation before using one.
        candidates=(0.,.25,.5,1.)
        scores={w:sum(abs(p-w*bias-o) for _,p,o in validation)/len(validation) for w in candidates}
        winner=min(candidates,key=lambda w:(scores[w],w))
        # Require at least 2% improvement, and not worse on either half of validation dates.
        vdates=sorted({d for d,_,_ in validation})
        mid=vdates[len(vdates)//2]
        halves=([x for x in validation if x[0]<mid],[x for x in validation if x[0]>=mid])
        safe=(winner>0 and scores[winner]<=baseline*.98 and
              all(sum(abs(p-winner*bias-o) for _,p,o in h)<=sum(abs(p-o) for _,p,o in h) for h in halves))
        weight=winner if safe else 0.
        original=sum(abs(p-o) for _,p,o in test)/len(test)
        corrected=sum(abs(p-weight*bias-o) for _,p,o in test)/len(test)
        result[bucket]={"status":"evaluated","train_unique_days":len({d for d,_,_ in entries if d<boundary}),
          "validation_unique_days":len(vdates),"test_unique_days":len({d for d,_,_ in test}),
          "test_pairs":len(test),"trained_bias_c":bias,"correction_weight":weight,
          "validation_baseline_mae_c":baseline,"validation_selected_mae_c":scores[weight],
          "test_baseline_mae_c":original,"test_guarded_mae_c":corrected,
          "test_improvement_pct":100*(original-corrected)/original if original else None}
    return {"split_date":split_date,"method":"chronological train/validation/test, gated bias shrinkage",
      "by_lead_days":result,"caution":"Experimental: limited stations and seasons; no guarantee of non-regression on unseen weather."}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("forecasts");p.add_argument("observations");p.add_argument("--split",required=True)
    p.add_argument("--output",default="station-validation-results/paired-comparison.json")
    a=p.parse_args()
    def read(path):
        with open(path,newline="",encoding="utf-8") as f:return list(csv.DictReader(f))
    forecasts=read(a.forecasts); observations=read(a.observations)
    result=compare(forecasts,observations,a.split)
    result["guarded_experiment"]=guarded_comparison(forecasts,observations,a.split)
    Path(a.output).parent.mkdir(parents=True,exist_ok=True)
    Path(a.output).write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
if __name__=="__main__":main()
