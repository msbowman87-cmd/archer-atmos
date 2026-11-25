"""Leakage-safe chronological bias calibration on independent forecast/observation pairs.

Forecast CSV: location_id,model,issue_at_utc,valid_start_utc,valid_end_utc,metric,unit,value
Truth CSV: location_id,available_at_utc,valid_start_utc,valid_end_utc,metric,unit,value,independent,quality_flag
"""
import argparse,csv,json,heapq
from collections import defaultdict
from datetime import datetime,timezone,timedelta
from math import isfinite
from pathlib import Path

FORECAST={'location_id','model','issue_at_utc','valid_start_utc','valid_end_utc','metric','unit','value'}
TRUTH={'location_id','available_at_utc','valid_start_utc','valid_end_utc','metric','unit','value','independent','quality_flag'}

def timestamp(value):
    value=datetime.fromisoformat(value.replace('Z','+00:00'))
    if value.tzinfo is None:raise ValueError('Time zone required')
    return value.astimezone(timezone.utc)

def parse(rows,needed,kind):
    parsed=[];seen=set()
    for record in rows:
        if not needed <= record.keys():raise ValueError('Missing '+kind+' columns: '+str(sorted(needed-record.keys())))
        row=dict(record)
        for k in ['issue_at_utc','available_at_utc','valid_start_utc','valid_end_utc']:
            if k in needed:row[k]=timestamp(row[k])
        if row['valid_start_utc']>=row['valid_end_utc']:raise ValueError('Invalid interval')
        row['value']=float(row['value'])
        if not isfinite(row['value']):continue
        identifier=tuple(row[k] for k in sorted(needed) if k not in ('value','independent','quality_flag'))
        if identifier in seen:raise ValueError('Duplicate '+kind)
        seen.add(identifier)
        if kind=='observation':
            if row['independent']!='true' or row['quality_flag']!='verified':continue
            if row['available_at_utc']<row['valid_end_utc']:raise ValueError('Truth available before measurement ended')
        elif row['issue_at_utc']>=row['valid_start_utc']:
            raise ValueError('Forecast not issued before valid interval')
        parsed.append(row)
    return parsed

def evaluate(forecasts,observations,*,minimum_history=30,holdout_start=None):
    f=parse(forecasts,FORECAST,'forecast');o=parse(observations,TRUTH,'observation')
    truth={}
    for item in o:
        key=tuple(item[x] for x in ['location_id','valid_start_utc','valid_end_utc','metric','unit'])
        if key in truth:raise ValueError('Ambiguous truth')
        truth[key]=item
    pairs=[]
    for item in f:
        key=tuple(item[x] for x in ['location_id','valid_start_utc','valid_end_utc','metric','unit'])
        if key in truth:pairs.append((item,truth[key]))
    pairs.sort(key=lambda p:(p[0]['issue_at_utc'],p[0]['location_id'],p[0]['model']))
    # Recalibrate exactly once per UTC day using all verified data available
    # strictly before its midnight cutoff, never intra-day updates.
    pending=defaultdict(list);totals=defaultdict(lambda:[0,0.0]);rows=[]
    cutoff=timestamp(holdout_start) if holdout_start else None
    # Each day's snapshots must not ingest forecast outcomes that were not
    # issued before the day's cutoff: remove them from the admission pool.
    pending=defaultdict(list);totals=defaultdict(lambda:[0,0.0])
    index=0
    daily=defaultdict(list)
    for pair in pairs:
        daily[pair[0]['issue_at_utc'].date()].append(pair)
    for day in sorted(daily):
        start=datetime.combine(day,datetime.min.time(),tzinfo=timezone.utc)
        while index<len(pairs) and pairs[index][0]['issue_at_utc']<start:
            pred,obs=pairs[index]
            group=(pred['model'],pred['metric'],pred['unit'])
            heapq.heappush(pending[group],(obs['available_at_utc'],index,obs['value']-pred['value']))
            index+=1
        for group,queue in pending.items():
            while queue and queue[0][0]<=start:
                _,_,correction=heapq.heappop(queue)
                totals[group][0]+=1;totals[group][1]+=correction
        for prediction,actual in daily[day]:
            group=(prediction['model'],prediction['metric'],prediction['unit'])
            count,total=totals[group]
            bias=total/count if count>=minimum_history else 0.0
            if cutoff is None or prediction['issue_at_utc']>=cutoff:
                rows.append({'issued_at':prediction['issue_at_utc'].isoformat(),'location_id':prediction['location_id'],
                             'model':prediction['model'],'metric':prediction['metric'],'training_cases':count,
                             'raw_abs_error':abs(prediction['value']-actual['value']),
                             'corrected_abs_error':abs(prediction['value']+bias-actual['value']),
                             'correction':bias})
    eligible=[r for r in rows if r['training_cases']>=minimum_history]
    mean=lambda name:sum(r[name] for r in eligible)/len(eligible) if eligible else None
    raw=mean('raw_abs_error');adjusted=mean('corrected_abs_error')
    return {'status':'exploratory_scored' if eligible else 'insufficient_verified_training_data',
            'paired_cases':len(pairs),'holdout_cases':len(rows),'trained_holdout_cases':len(eligible),
            'raw_mae':raw,'corrected_mae':adjusted,
            'relative_mae_change_pct':100*(1-adjusted/raw) if raw else None,
            'issue_dates_evaluated':len({r['issued_at'][:10] for r in rows}),
            'warning':'Research-only; not proof of generalization or production skill. Later holdout predictions may use already verified earlier holdout days.',
            'rows':rows}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--forecasts',required=True);p.add_argument('--observations',required=True)
    p.add_argument('--output',required=True);p.add_argument('--holdout-start')
    p.add_argument('--minimum-history',type=int,default=30)
    a=p.parse_args()
    with open(a.forecasts,newline='') as src:f=list(csv.DictReader(src))
    with open(a.observations,newline='') as src:o=list(csv.DictReader(src))
    result=evaluate(f,o,minimum_history=a.minimum_history,holdout_start=a.holdout_start)
    Path(a.output).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))
if __name__=='__main__':main()
