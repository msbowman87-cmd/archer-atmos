#!/usr/bin/env python3
"""Multi-region NOAA temperature pilot with measured upwind station context.

Experimental only. Uses original SHA-verified Atmos GHCNh archive files,
screened as source+quality pairs, and a fixed assumed 72-hour observation lag.
A pooled 2022-2023 fit is evaluated on disjoint 3-degree heldout geographic
tiles in 2024 (validation) and 2025 (evaluation). Never deploy or certify this.
"""
import argparse
import collections
import csv
import datetime as dt
import io
import json
import math
import pathlib
import random
import statistics
import tempfile

from atmos_quality_policy import normalize
from atmos_regional_actual_pilot import (
    ZipSourceLoader, qualified_noaa, ridge_fit, latest,
)
from atmos_regional_neighbors import distance_bearing

MIN_NEIGHBORS = 10
UTC = dt.timezone.utc
YEARS = (2022, 2023, 2024, 2025)
HORIZON_HOURS = 24
ASSUMED_LAG_HOURS = 72
EPOCH = dt.datetime(1970, 1, 1, tzinfo=UTC)

def load_surface(data):
    """Last accepted source row within each UTC hour, separately per variable."""
    reader = csv.DictReader(io.StringIO(data.decode('utf-8-sig')), delimiter='|')
    required = {'DATE', 'temperature', 'temperature_Quality_Code', 'temperature_Source_Code'}
    if not required.issubset(reader.fieldnames or []):
        raise ValueError('Missing GHCNh temperature or QC columns')
    accepted = collections.defaultdict(dict)
    reasons = collections.Counter()
    for row in reader:
        stamp = dt.datetime.fromisoformat(row['DATE'].replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=UTC)
        stamp = stamp.astimezone(UTC)
        hour = stamp.replace(minute=0, second=0, microsecond=0)
        for field in ('temperature', 'wind_speed', 'wind_direction'):
            value, canonical, reason = normalize(
                'NOAA_GHCNh', field, row.get(field),
                row.get(field+'_Quality_Code'), row.get(field+'_Source_Code'))
            reasons[field + ':' + reason] += 1
            if value is None:
                continue
            old = accepted[canonical].get(hour)
            if old is None or stamp >= old[0]:
                accepted[canonical][hour] = (stamp, value)
    return ({key: {hour: pair[1] for hour, pair in values.items()}
             for key, values in accepted.items()}, dict(reasons))

def candidate_clusters(graph_path, eligible):
    clusters = {'training_target': [], 'spatial_holdout_target': []}
    with pathlib.Path(graph_path).open(encoding='utf-8') as source:
        for line in source:
            node = json.loads(line)
            sid = node['target_station_id']
            role = node['role']
            if (node['target_provider'] != 'NOAA_GHCNh'
                    or role not in clusters or sid not in eligible):
                continue
            # Neighbors in the graph are never spatially held-out targets.
            neighbors = [entry for entry in node['candidate_neighbors']
                         if entry['provider'] == 'NOAA_GHCNh'
                         and entry['station_id'] in eligible
                         and entry['distance_km'] <= 250
                         and entry['station_id'] != sid]
            neighbors = list({entry['station_id']: entry for entry in neighbors}.values())
            if len(neighbors) < MIN_NEIGHBORS:
                continue
            score = (len(neighbors),
                     sum(sum(eligible[x][1].values()) for x in
                         [sid]+[entry['station_id'] for entry in neighbors]),
                     -sum(entry['distance_km'] for entry in neighbors))
            clusters[role].append((score, node, neighbors))
    for role in clusters:
        clusters[role].sort(key=lambda x:x[0], reverse=True)
    return clusters

def select_regions(graph_path, eligible, train_count=3, holdout_count=2,
                   separation_km=350):
    clusters = candidate_clusters(graph_path, eligible)
    used_tiles = set()
    chosen = []
    for role, count in (('training_target', train_count),
                        ('spatial_holdout_target', holdout_count)):
        selected = []
        for _, node, neighbors in clusters[role]:
            tile = tuple(node['spatial_tile'])
            if tile in used_tiles:
                continue
            # Diverse regions, not several adjacent airport reports.
            if any(distance_bearing(node, previous['node'])[0] < separation_km
                   for previous in chosen):
                continue
            selected.append(dict(node=node, neighbors=neighbors))
            chosen.append(selected[-1])
            used_tiles.add(tile)
            if len(selected) == count:
                break
        if len(selected) != count:
            raise ValueError('Insufficient independent regions: ' + role
                             + ' found ' + str(len(selected)) + ' of ' + str(count))
    training_tiles = {tuple(x['node']['spatial_tile']) for x in chosen
                      if x['node']['role'] == 'training_target'}
    heldout_tiles = {tuple(x['node']['spatial_tile']) for x in chosen
                     if x['node']['role'] == 'spatial_holdout_target'}
    if training_tiles & heldout_tiles:
        raise ValueError('Spatial leakage: training tile overlaps holdout tile')
    return chosen

def circular_offset_degrees(a, b):
    return (a - b + 180) % 360 - 180

def wind_weight(bearing_from_target_deg, direction_from_deg, speed_mps):
    """Meteorological wind is FROM bearing; source must lie upwind of target."""
    if not 0 <= speed_mps <= 110:
        return 0
    # Light/calm winds carry little directional guidance. Base geographical
    # weights are handled separately, not fabricated as an upwind signal.
    if speed_mps < 1.5:
        return 0
    alignment = math.cos(math.radians(
        circular_offset_degrees(bearing_from_target_deg, direction_from_deg)))
    return max(0.0, alignment) ** 2 * min(1.0, speed_mps / 8.0)

def build_examples(target_id, source_ids, station_meta, surface, years=YEARS, *, lag_hours=ASSUMED_LAG_HOURS,
                   min_neighbors=MIN_NEIGHBORS):
    own_data = surface[target_id]['temperature_c']
    own_keys = sorted(own_data)
    target_wind_speed = surface[target_id].get('wind_speed_mps', {})
    target_wind_dir = surface[target_id].get('wind_direction_deg', {})
    wind_speed_keys = sorted(target_wind_speed)
    wind_dir_keys = sorted(target_wind_dir)
    neighbors = []
    for sid in dict.fromkeys(source_ids):
        if sid == target_id:
            continue
        data = surface[sid].get('temperature_c', {})
        if not data:
            continue
        dist, bearing = distance_bearing(station_meta[target_id], station_meta[sid])
        if dist > 300:
            continue
        altitude_diff = float(station_meta[sid]['elevation_m']) - float(
            station_meta[target_id]['elevation_m'])
        neighbors.append((sid, data, sorted(data), dist, bearing, altitude_diff))
    for verification in own_keys:
        if verification.year not in years:
            continue
        issued = verification - dt.timedelta(hours=HORIZON_HOURS)
        asof = issued - dt.timedelta(hours=lag_hours)
        own = latest(own_data, own_keys, asof)
        if own is None:
            continue
        wind_speed = latest(target_wind_speed, wind_speed_keys, asof)
        wind_dir = latest(target_wind_dir, wind_dir_keys, asof)
        valid_wind = (wind_speed is not None and wind_dir is not None
                      and wind_speed >= 1.5 and wind_speed <= 110)
        geographic = []
        upwind = []
        for sid, data, stamps, distance_km, bearing, dz in neighbors:
            temp = latest(data, stamps, asof)
            if temp is None:
                continue
            # Simple sensitivity scenario; not a certified lapse correction.
            adjusted = temp + dz*0.0065
            geo_weight = 1 / (20 + distance_km)
            geographic.append((adjusted, geo_weight))
            if valid_wind:
                directional = wind_weight(bearing, wind_dir, wind_speed)
                if directional > 0:
                    upwind.append((adjusted, geo_weight*directional))
        if len(geographic) < min_neighbors:
            continue
        geo_average = sum(v*w for v,w in geographic) / sum(w for _,w in geographic)
        have_upwind = valid_wind and bool(upwind)
        upwind_average = (sum(v*w for v,w in upwind) / sum(w for _,w in upwind)
                          if have_upwind else geo_average)
        hour_angle = issued.hour * 2*math.pi / 24
        year_angle = (issued.timetuple().tm_yday-1)*2*math.pi/365.25
        base = [1.0, own/30, math.sin(hour_angle),math.cos(hour_angle),
                math.sin(year_angle),math.cos(year_angle),
                float(station_meta[target_id]['latitude'])/60,
                float(station_meta[target_id]['elevation_m'])/2000]
        geo_feature = (geo_average-own)/15
        wind_delta = (upwind_average-geo_average)/15 if have_upwind else 0
        full = base + [geo_feature,wind_delta,
                       min(wind_speed/15, 3) if have_upwind else 0,
                       1.0 if have_upwind else 0]
        yield dict(target=target_id, valid_at=verification, year=verification.year,
                   actual=own_data[verification], baseline=own,
                   local=base, geographic=base+[geo_feature], upwind=full,
                   used_wind=bool(have_upwind), neighbor_count=len(geographic))

def fit_all(training_rows):
    if len(training_rows) < 1000:
        raise ValueError('Not enough training-only target examples')
    return {name:ridge_fit(training_rows, name, lam=2.0)
            for name in ('local','geographic','upwind')}

def score(rows, models):
    if not rows:
        return dict(cases=0)
    counts = collections.Counter()
    errors = collections.defaultdict(list)
    for row in rows:
        counts['cases'] += 1
        if row['used_wind']:
            counts['upwind_active_cases'] += 1
        errors['persistence'].append(abs(row['baseline']-row['actual']))
        for name, weights in models.items():
            estimated = sum(a*b for a,b in zip(row[name],weights))
            errors[name].append(abs(estimated-row['actual']))
    mae = {key+'_mae_c':round(statistics.mean(items),4) for key,items in errors.items()}
    base = statistics.mean(errors['local'])
    return dict(cases=len(rows), upwind_active_cases=counts['upwind_active_cases'],
                upwind_active_fraction=round(counts['upwind_active_cases']/len(rows),4),
                **mae, upwind_vs_local_skill_pct=round(
                    100*(base-statistics.mean(errors['upwind']))/base,3)
                if base else None)


def paired_daily_bootstrap(rows, models, replicates=350, seed=20261118):
    """Paired daily-block bootstrap, positive C means upwind improves local.

    Descriptive conditional on tested targets and a fixed trained model;
    cannot substitute for additional independent geographic regions.
    """
    if not rows:
        return dict(cases=0)
    blocks=collections.defaultdict(lambda: [0.0,0])
    for row in rows:
        local=sum(a*b for a,b in zip(row['local'],models['local']))
        wind=sum(a*b for a,b in zip(row['upwind'],models['upwind']))
        improvement=abs(row['actual']-local)-abs(row['actual']-wind)
        key=(row['target'],row['valid_at'].date().isoformat())
        blocks[key][0]+=improvement
        blocks[key][1]+=1
    values=list(blocks.values())
    n=len(values)
    rng=random.Random(seed)
    samples=[]
    for _ in range(replicates):
        sampled=[values[rng.randrange(n)] for _ in range(n)]
        total=sum(x[0] for x in sampled)
        cases=sum(x[1] for x in sampled)
        samples.append(total/cases)
    samples.sort()
    measured=sum(v[0] for v in values)/sum(v[1] for v in values)
    return dict(cases=len(rows), daily_blocks=n,
                delta_mae_c_positive_is_better=round(measured,5),
                ci_95_c=[round(samples[int(0.025*replicates)],5),
                         round(samples[min(replicates-1,int(0.975*replicates))],5)],
                note='Days resampled within the fixed selected stations; not a geographic generalization interval.')

def run(checkpoint, graph_path, out, train_regions=3, holdout_regions=2, *,
        lag_hours=ASSUMED_LAG_HOURS):
    if lag_hours < 0:
        raise ValueError('Observation availability lag cannot be negative')
    root = pathlib.Path(checkpoint)
    output = pathlib.Path(out)
    output.mkdir(parents=True,exist_ok=True)
    stations = list(csv.DictReader((root/'stations.csv').open(newline='')))
    eligible = qualified_noaa(root, stations)
    selected = select_regions(graph_path, eligible, train_regions, holdout_regions)
    station_meta = {s['station_id']:s for s in stations if s['provider']=='NOAA_GHCNh'}
    source_ids = sorted({id for cluster in selected
                         for id in [cluster['node']['target_station_id']]
                         + [n['station_id'] for n in cluster['neighbors']]})
    # Enforce bounded cost and defend against unexpectedly large archives.
    if len(source_ids) > 24:
        raise ValueError('Pilot must remain <=24 distinct stations')
    qc = {}
    surface = collections.defaultdict(lambda:collections.defaultdict(dict))
    with tempfile.TemporaryDirectory(prefix='atmos-multiregion-') as tmp:
        loader = ZipSourceLoader(root, tmp, budget_bytes=2_600_000_000)
        for sid in source_ids:
            for year in YEARS:
                data = loader.read(sid,year)
                parsed, reasons = load_surface(data)
                for field, times in parsed.items():
                    surface[sid][field].update(times)
                qc[sid+':'+str(year)] = dict(
                    accepted_hours={field:len(values) for field,values in parsed.items()},
                    screened_source_rows=reasons)
        provenance = loader.sources
    source_report = dict(
        stations=source_ids, source_files=provenance,
        station_year_qc=qc, status='source_aware_provisional',
        notes='Row-level documented source/QC screening; not independent instrument certification.')
    (output/'source_screening.json').write_text(json.dumps(source_report,indent=2)+'\n')
    summary = dict(event='source_screened', source_files=len(provenance),
                   stations=len(source_ids),
                   wind_hours=sum(len(v.get('wind_speed_mps', {}))
                                  for v in surface.values()))
    print(json.dumps(summary), flush=True)
    train_rows=[]
    eval_rows=collections.defaultdict(list)
    region_summary=[]
    for cluster in selected:
        node=cluster['node']
        sid=node['target_station_id']
        rows=list(build_examples(sid,
            [n['station_id'] for n in cluster['neighbors']],station_meta,surface, lag_hours=lag_hours))
        split=node['role']
        for row in rows:
            if split == 'training_target' and row['year'] in (2022,2023):
                train_rows.append(row)
            if row['year'] in (2024,2025):
                eval_rows[(split,row['year'])].append(row)
        region_summary.append(dict(station_id=sid, role=split, tile=node['spatial_tile'],
                                   latitude=node['latitude'], longitude=node['longitude'],
                                   neighbors=[n['station_id'] for n in cluster['neighbors']],
                                   year_cases={str(y):sum(r['year']==y for r in rows) for y in YEARS},
                                   wind_active_cases=sum(r['used_wind'] for r in rows)))
    if len(train_rows) < 1000:
        raise ValueError('Insufficient screened training cases across regions')
    models=fit_all(train_rows)
    results={role:{str(year):score(eval_rows[(role,year)],models)
                   for year in (2024,2025)}
             for role in ('training_target','spatial_holdout_target')}
    if (results['spatial_holdout_target']['2024']['cases'] < 100
            or results['spatial_holdout_target']['2025']['cases'] < 100):
        raise ValueError('Insufficient independent spatial holdout forecast cases')
    # Surface each excluded geographic area, not only a pooled holdout average.
    holdout_station_scores={}
    for cluster in selected:
        node=cluster['node']
        if node['role'] != 'spatial_holdout_target':
            continue
        sid=node['target_station_id']
        holdout_station_scores[sid]={
            str(year):score([r for r in eval_rows[('spatial_holdout_target',year)]
                             if r['target']==sid],models) for year in (2024,2025)}
    wind_subset_scores={str(year):score([
        r for r in eval_rows[('spatial_holdout_target',year)] if r['used_wind']],models)
        for year in (2024,2025)}
    paired_intervals={str(year):paired_daily_bootstrap(
        eval_rows[('spatial_holdout_target',year)],models,seed=20261118+year)
        for year in (2024,2025)}
    report=dict(status='experimental_multiregion_temperature_results',
                train_regions=train_regions, spatial_holdout_regions=holdout_regions,
                minimum_neighbors_per_hour=MIN_NEIGHBORS,
                trained_target_hours=len(train_rows), station_selections=region_summary,
                results=results, holdout_station_results=holdout_station_scores,
                wind_active_holdout_results=wind_subset_scores,
                paired_daily_uncertainty=paired_intervals, model_weights=models,
                forecast_horizon_hours=HORIZON_HOURS,
                assumed_observation_lag_hours=lag_hours,
                lag_verified=False, source_quality_approved=False,
                fully_trained_atmos=False, production_deployed=False,
                model='shared ridge 2022-2023; station-only / distance / wind-informed',
                limitations=[
                    'Only temperature and a few station clusters; independent tiles are small exploratory samples.',
                    'Wind direction is measured FROM bearing; no wind signal is fabricated for missing observations.',
                    f'A {lag_hours}h data publication lag and simplified constant elevation correction are assumed.',
                    'No global geographic certification or radar/satellite as-of data.',
                    '2024/2025 files preselected for availability, not future weather outcomes.',
                    'No inference about improvement without repeated disjoint regional holdouts and uncertainty intervals.',
                ])
    (output/'multi_region_wind_benchmark.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='model_weights'},indent=2), flush=True)
    return report

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--checkpoint',required=True)
    parser.add_argument('--neighbor-graph',required=True)
    parser.add_argument('--out',required=True)
    parser.add_argument('--train-regions',type=int,default=3)
    parser.add_argument('--holdout-regions',type=int,default=2)
    parser.add_argument('--lag-hours', type=int, default=24,
                        help='Assumed observation availability delay for the research sensitivity run')
    args=parser.parse_args()
    run(args.checkpoint, args.neighbor_graph, args.out, args.train_regions,
        args.holdout_regions, lag_hours=args.lag_hours)

if __name__=='__main__':
    main()
