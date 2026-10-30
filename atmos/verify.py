"""Out-of-sample forecast verification. No calibration on evaluation data."""
import math
from collections import defaultdict

def metrics(rows, heavy_threshold_mm=20):
    """Rows: issue_time, valid_time, location, horizon_hours, predicted_temp_c,
    observed_temp_c, predicted_rain_mm, observed_rain_mm. Missing values are None.
    Rows must represent forecasts archived BEFORE the observation was known."""
    buckets=defaultdict(list)
    for r in rows:
        if r.get("valid_time") is None or r.get("issue_time") is None:
            raise ValueError("Issue and valid timestamps required")
        if r["issue_time"] >= r["valid_time"]:
            raise ValueError("Forecast must precede observation")
        buckets[int(r["horizon_hours"])].append(r)
    out={}
    for horizon, group in sorted(buckets.items()):
        d={"n":len(group)}
        for name in ("temp_c","rain_mm"):
            pairs=[]
            for r in group:
                a=r.get("predicted_"+name);b=r.get("observed_"+name)
                if a is not None and b is not None and math.isfinite(a) and math.isfinite(b):
                    pairs.append((a,b))
            d[name+"_n"]=len(pairs)
            d[name+"_mae"]=sum(abs(a-b) for a,b in pairs)/len(pairs) if pairs else None
            d[name+"_bias"]=sum(a-b for a,b in pairs)/len(pairs) if pairs else None
            if name=="rain_mm":
                if any(a<0 or b<0 for a,b in pairs): raise ValueError("Negative precipitation")
                for threshold,label in ((0.1,"wet"),(heavy_threshold_mm,"heavy")):
                    tp=sum(a>=threshold and b>=threshold for a,b in pairs)
                    fn=sum(a<threshold and b>=threshold for a,b in pairs)
                    fp=sum(a>=threshold and b<threshold for a,b in pairs)
                    d[label+"_hits"]=tp
                    d[label+"_misses"]=fn
                    d[label+"_false_alarms"]=fp
                    d[label+"_recall"]=tp/(tp+fn) if tp+fn else None
                    d[label+"_precision"]=tp/(tp+fp) if tp+fp else None
        out[str(horizon)]=d
    return out

def paired_improvement(baseline, candidate, observed):
    """Same held-out cases; positive is improvement in MAE."""
    if not baseline or len(baseline)!=len(candidate) or len(candidate)!=len(observed):
        raise ValueError("Aligned, nonempty paired samples required")
    if not all(math.isfinite(v) for seq in (baseline,candidate,observed) for v in seq):
        raise ValueError("Non-finite value")
    return (sum(abs(a-y) for a,y in zip(baseline,observed))-
            sum(abs(a-y) for a,y in zip(candidate,observed)))/len(observed)
