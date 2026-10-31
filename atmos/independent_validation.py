"""Validate issued forecasts against independently collected station observations."""
import csv, json, argparse
from collections import defaultdict
from datetime import date

def load(path, columns):
    with open(path, newline='', encoding='utf-8') as f:
        reader=csv.DictReader(f)
        if not set(columns).issubset(reader.fieldnames or []):
            raise ValueError('Missing required columns in '+path)
        return list(reader)

def evaluate(forecasts, observations):
    observed={}
    for row in observations:
        key=(row['station_id'],row['date'])
        if key in observed: raise ValueError('Duplicate observation '+str(key))
        observed[key]=row
    groups=defaultdict(lambda: {'matched':0,'temperature_pairs':0,'precipitation_pairs':0,'temperature_abs_error':0.,'precipitation_abs_error':0.})
    seen=set()
    unmatched=0
    for f in forecasts:
        key=(f['station_id'],f['date'],f['issue_date'])
        if key in seen: raise ValueError('Duplicate forecast '+str(key))
        seen.add(key)
        lead=(date.fromisoformat(f['date'])-date.fromisoformat(f['issue_date'])).days
        if not 1<=lead<=30: raise ValueError('Invalid forecast lead '+str(key))
        o=observed.get(key[:2])
        if o is None:
            unmatched+=1
            continue
        bucket='1-7' if lead<=7 else '8-14' if lead<=14 else '15-30'
        g=groups[bucket]
        g['matched']+=1
        for metric,fc,ob in [('temperature','forecast_temp_max_c','observed_temp_max_c'),('precipitation','forecast_precip_mm','observed_precip_mm')]:
            if f[fc]!='' and o[ob]!='':
                g[metric+'_pairs']+=1
                g[metric+'_abs_error']+=abs(float(f[fc])-float(o[ob]))
    result={}
    for bucket in ('1-7','8-14','15-30'):
        g=groups[bucket]
        result[bucket]={'matched':g['matched']}
        for metric in ('temperature','precipitation'):
            n=g[metric+'_pairs']
            result[bucket][metric+'_pairs']=n
            result[bucket][metric+'_mae_'+('c' if metric=='temperature' else 'mm')]=g[metric+'_abs_error']/n if n else None
    return {'forecast_rows':len(forecasts),'unmatched_rows':unmatched,'by_lead_days':result,
            'warning':'Independent station observations and authentic issued forecasts required. No improvement over baseline is established.'}

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('forecasts')
    p.add_argument('observations')
    p.add_argument('--output',default='independent-validation-results.json')
    a=p.parse_args()
    forecasts=load(a.forecasts,('station_id','date','issue_date','forecast_temp_max_c','forecast_precip_mm'))
    observations=load(a.observations,('station_id','date','observed_temp_max_c','observed_precip_mm'))
    result=evaluate(forecasts,observations)
    with open(a.output,'w') as f: json.dump(result,f,indent=2)
    print(json.dumps(result,indent=2))
