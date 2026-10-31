"""Regional context experiment: compare point forecast against a surrounding-grid correction.

Archived forecasts only; train on August, evaluate on September. Neighboring grid
forecasts are issued from the SAME model initialization as the target forecast.
No future observed values are used as predictors.
"""
import argparse,csv,json
from collections import defaultdict
from datetime import date,timedelta
from pathlib import Path
from atmos.station_backtest import get,aggregate_local_days,observations

OFFSETS=((0,0),(0,1.5),(0,-1.5),(1.5,0),(-1.5,0))

def archive(lat,lon,tz,issue):
    params={'latitude':lat,'longitude':lon,'timezone':'UTC',
            'run':issue.isoformat()+'T00:00','models':'ecmwf_ifs',
            'hourly':'temperature_2m,precipitation','forecast_days':10}
    data=json.loads(get('https://single-runs-api.open-meteo.com/v1/forecast',params))
    if 'error' in data: raise RuntimeError(str(data))
    return aggregate_local_days(data['hourly'],tz)

def regional_rows(lat,lon,tz,start,end):
    result=[]; failures=[]
    issue=start-timedelta(days=9)
    while issue<end:
        try:
            grids=[archive(lat+dy,lon+dx,tz,issue) for dy,dx in OFFSETS]
            for day,(target_temp,_) in grids[0].items():
                lead=(day-issue).days
                if not start<=day<=end or not 1<=lead<=9: continue
                if any(day not in g for g in grids[1:]):continue
                neighbors=[g[day][0] for g in grids[1:]]
                result.append({'date':day.isoformat(),'issue_date':issue.isoformat(),
                               'lead':lead,'baseline':target_temp,
                               'regional_anomaly':sum(neighbors)/len(neighbors)-target_temp})
        except Exception as exc:
            failures.append({'issue':issue.isoformat(),'error':str(exc)[:200]})
        issue+=timedelta(days=1)
    return result,failures

def evaluate(rows,obs,split='2026-09-01'):
    truth={r['date']:float(r['observed_temp_max_c']) for r in obs if r['observed_temp_max_c']}
    matched=[dict(r,actual=truth[r['date']]) for r in rows if r['date'] in truth]
    output={}
    for name,leads in [('1-7',range(1,8)),('8-9',range(8,10))]:
        data=[r for r in matched if r['lead'] in leads]
        train=[r for r in data if r['date']<split]
        test=[r for r in data if r['date']>=split]
        # Only August forecasts used to fit regional coefficient.
        denominator=sum(r['regional_anomaly']**2 for r in train)
        coefficient=(sum(r['regional_anomaly']*(r['actual']-r['baseline']) for r in train)/denominator) if denominator else 0
        coefficient=max(-1.,min(1.,coefficient))
        if len({r['date'] for r in train})<14 or len({r['date'] for r in test})<14:
            output[name]={'status':'insufficient_unique_days','train_pairs':len(train),'test_pairs':len(test)}
            continue
        base=sum(abs(r['baseline']-r['actual']) for r in test)/len(test)
        regional=sum(abs(r['baseline']+coefficient*r['regional_anomaly']-r['actual']) for r in test)/len(test)
        output[name]={'train_pairs':len(train),'test_pairs':len(test),
                      'train_unique_days':len({r['date'] for r in train}),
                      'test_unique_days':len({r['date'] for r in test}),
                      'regional_coefficient':coefficient,'baseline_mae_c':base,
                      'regional_mae_c':regional,
                      'improvement_pct':100*(base-regional)/base if base else None}
    return {'method':'regional spatial gradient, 4 surrounding ECMWF grid points at +/-1.5 degrees',
            'split_date':split,'by_lead_days':output,
            'limitations':['Exploratory spatial correction, not an atmospheric dynamics model.',
              'Nearby grid points use the same ECMWF forecast and are not independent observations.',
              'IEM station-day reporting convention still needs independent verification.',
              'Overlapping forecasts are not independent verification days.',
              'Not a 30-day forecast test.']}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--station',default='TWF');p.add_argument('--network',default='ID_ASOS')
    p.add_argument('--latitude',type=float,default=42.4818)
    p.add_argument('--longitude',type=float,default=-114.4877)
    p.add_argument('--timezone',default='America/Boise')
    p.add_argument('--start',default='2026-08-01');p.add_argument('--end',default='2026-09-30')
    p.add_argument('--output',default='regional-validation-results')
    a=p.parse_args()
    start=date.fromisoformat(a.start);end=date.fromisoformat(a.end)
    obs=observations(a.station,a.network,start,end)
    rows,failures=regional_rows(a.latitude,a.longitude,a.timezone,start,end)
    report=evaluate(rows,obs)
    report.update(station=a.station,forecast_rows=len(rows),failed_initializations=failures)
    root=Path(a.output);root.mkdir(parents=True,exist_ok=True)
    (root/'report.json').write_text(json.dumps(report,indent=2))
    with (root/'regional_forecasts.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['date','issue_date','lead','baseline','regional_anomaly'])
        writer.writeheader();writer.writerows(rows)
    print(json.dumps(report,indent=2))
    if not rows or not any('baseline_mae_c' in x for x in report['by_lead_days'].values()):
        raise RuntimeError('Not enough matched regional forecasts for evaluation')
if __name__=='__main__':main()
