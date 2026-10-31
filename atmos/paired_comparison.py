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

def main():
    p=argparse.ArgumentParser()
    p.add_argument("forecasts");p.add_argument("observations");p.add_argument("--split",required=True)
    p.add_argument("--output",default="station-validation-results/paired-comparison.json")
    a=p.parse_args()
    def read(path):
        with open(path,newline="",encoding="utf-8") as f:return list(csv.DictReader(f))
    result=compare(read(a.forecasts),read(a.observations),a.split)
    Path(a.output).parent.mkdir(parents=True,exist_ok=True)
    Path(a.output).write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
if __name__=="__main__":main()
