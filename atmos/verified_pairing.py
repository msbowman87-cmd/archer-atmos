"""Strict bridge from QC-normalized NOAA station readings to chronological backtesting.

No availability time is inferred from an observation timestamp. To report
historical forecast skill, an independent forecast source must provide a real
model issue cycle and a verified observation availability provenance record.

This intentionally refuses to score when either provenance is absent. A
nominal hourly match is NOT an hourly average and may be +/-30 minutes.
"""
import argparse,csv,gzip,json,math
from collections import Counter,defaultdict
from datetime import timedelta
from pathlib import Path
from atmos.walk_forward import evaluate,timestamp

METRICS={
    "temp_2m":("temperature_c","C"),
    "dewpoint_2m":("dewpoint_c","C"),
    "relative_humidity":("relative_humidity_pct","percent"),
    "wind_speed":("wind_speed_mps","m/s"),
    "sea_level_pressure":("sea_level_pressure_hpa","hPa"),
    "visibility":("visibility_m","m"),
}
REQUIRED_FORECAST={"station_id","model","issue_at_utc","valid_hour_utc",
                   "metric","unit","value","source_issue_reference","source_issue_verified"}
REQUIRED_AVAILABILITY={"station_id","observed_at_utc","available_at_utc",
                       "verification_reference","availability_verified"}

def validated_forecast(row):
    if not REQUIRED_FORECAST.issubset(row):raise ValueError("Forecast lacks actual issue-cycle provenance fields")
    if row["source_issue_verified"]!="true" or not row["source_issue_reference"].strip():
        return None,"unverified_forecast_cycle"
    if row["metric"] not in METRICS or row["unit"]!=METRICS[row["metric"]][1]:
        return None,"unsupported_metric_or_unit"
    try:
        issue=timestamp(row["issue_at_utc"]);valid=timestamp(row["valid_hour_utc"])
        value=float(row["value"])
    except (ValueError,KeyError):return None,"invalid_forecast"
    if not math.isfinite(value) or issue>=valid:return None,"invalid_forecast_issue_or_value"
    if valid.minute or valid.second or valid.microsecond:return None,"not_a_nominal_hour"
    return {**row,"issue":issue,"valid":valid,"value_f":value},None

def build(forecasts,normalized,availability,*,minimum_history=30,holdout_start=None):
    """Join records only when verified issuance AND publication time are known."""
    if minimum_history<1:raise ValueError("minimum_history must be positive")
    prediction_index=defaultdict(list)
    reasons=Counter();source_count=0
    for f in forecasts:
        source_count+=1
        good,reason=validated_forecast(f)
        if reason:
            reasons[reason]+=1;continue
        key=(f["station_id"],good["valid"].isoformat(),f["metric"],f["unit"])
        prediction_index[key].append(good)
    publication={}
    for row in availability:
        if not REQUIRED_AVAILABILITY.issubset(row):
            raise ValueError("Observation availability file must document independently verified publication times")
        if row["availability_verified"]!="true" or not row["verification_reference"].strip():
            reasons["unverified_observation_availability"]+=1;continue
        try:
            observed=timestamp(row["observed_at_utc"])
            available=timestamp(row["available_at_utc"])
        except ValueError:
            reasons["invalid_observation_publication"]+=1;continue
        if available<observed:
            reasons["publication_before_observation"]+=1;continue
        key=(row["station_id"],observed.isoformat())
        if key in publication:raise ValueError("Conflicting observation availability records")
        publication[key]=available
    p=[];o=[];seen=set();eligible_hours=0
    for row in normalized:
        if not {"station_id","hour_utc","observed_at_utc"}.issubset(row):
            raise ValueError("Normalized observation schema mismatch")
        station=row["station_id"];valid=timestamp(row["hour_utc"]);actual=timestamp(row["observed_at_utc"])
        if abs((actual-valid).total_seconds())>1800:raise ValueError("Unbounded observation hourly offset")
        available=publication.get((station,actual.isoformat()))
        for metric,(field,unit) in METRICS.items():
            raw=row.get(field,"")
            key=(station,valid.isoformat(),metric,unit)
            if not prediction_index.get(key):continue
            if raw in ("",None):
                reasons["unusable_observation_metric"]+=len(prediction_index[key]);continue
            eligible_hours+=1
            if available is None:
                reasons["no_verified_observation_availability"]+=len(prediction_index[key]);continue
            try:obs_value=float(raw)
            except (ValueError,TypeError):
                reasons["invalid_observation_value"]+=len(prediction_index[key]);continue
            if not math.isfinite(obs_value):continue
            observed_interval_end=actual+timedelta(minutes=1)
            if available<observed_interval_end:
                reasons["publication_before_observation_complete"]+=len(prediction_index[key]);continue
            for f in prediction_index[key]:
                if f["issue"]>=actual:
                    reasons["forecast_issued_after_measurement"]+=1;continue
                identity=(station,actual,metric,unit)
                if identity in seen:
                    # Multiple forecasts for same truth interval are supported
                    # but truth is written just once, and individual predictions
                    # may represent separate model cycles.
                    pass
                else:
                    seen.add(identity)
                    o.append({"location_id":station,"available_at_utc":available.isoformat(),
                         "valid_start_utc":actual.isoformat(),
                         "valid_end_utc":observed_interval_end.isoformat(),
                         "metric":metric,"unit":unit,"value":str(obs_value),
                         "independent":"true","quality_flag":"verified"})
                p.append({"location_id":station,"model":f["model"],
                    "issue_at_utc":f["issue"].isoformat(),
                    "valid_start_utc":actual.isoformat(),
                    "valid_end_utc":observed_interval_end.isoformat(),
                    "metric":metric,"unit":unit,"value":str(f["value_f"])})
    if not p:
        return {"status":"blocked_no_verified_pairs",
                "forecast_rows":source_count,"eligible_observation_metric_hours":eligible_hours,
                "matched_verified_pairs":0,"rejection_reasons":dict(reasons),
                "warning":"No forecast skill or daily recalibration can be claimed without independently verified model issue cycles and observation availability times."}
    scores=evaluate(p,o,minimum_history=minimum_history,holdout_start=holdout_start)
    return {"status":scores["status"],"forecast_rows":source_count,
            "eligible_observation_metric_hours":eligible_hours,
            "matched_verified_pairs":len(p),"rejection_reasons":dict(reasons),
            "raw_mae":scores["raw_mae"],"corrected_mae":scores["corrected_mae"],
            "trained_holdout_cases":scores["trained_holdout_cases"],
            "relative_mae_change_pct":scores["relative_mae_change_pct"],
            "issue_dates_evaluated":scores["issue_dates_evaluated"],
            "warning":scores["warning"],
            "nominal_hour_tolerance_minutes":30,
            "publication_provenance_requirement":"verified, not assumed"}

def read_csv(path):
    with (gzip.open(path,"rt",newline="") if str(path).endswith(".gz") else open(path,newline="")) as f:
        yield from csv.DictReader(f)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--forecasts",required=True)
    p.add_argument("--normalized",required=True)
    p.add_argument("--observation-availability",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--holdout-start")
    p.add_argument("--minimum-history",type=int,default=30)
    args=p.parse_args()
    out=build(read_csv(args.forecasts),read_csv(args.normalized),
        read_csv(args.observation_availability),
        minimum_history=args.minimum_history,holdout_start=args.holdout_start)
    Path(args.output).write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps(out,indent=2))
if __name__=="__main__":main()
