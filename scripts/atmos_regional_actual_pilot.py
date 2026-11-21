#!/usr/bin/env python3
"""Bounded real-NOAA regional-vs-local *research* forecast benchmark.

Requires a verified Atmos archive restored by restore_hourly_checkpoint.py.
Fetches only selected ZIP parts from published research releases, hash verifies
ZIPs and source files, screens NOAA row-level QC, and trains in 2022-2023.
2024 is validation, 2025 evaluation. This is not a production model or a
verified historical observation-publication-time evaluation.
"""
import argparse
import bisect
import collections
import csv
import datetime
import hashlib
import io
import json
import math
import os
import pathlib
import statistics
import subprocess
import tempfile
import zipfile

from atmos_quality_policy import normalize
from atmos_regional_neighbors import distance_bearing

YEARS = (2022, 2023, 2024, 2025)
UTC = datetime.timezone.utc

def hash_bytes(data):
    return hashlib.sha256(data).hexdigest()

def qualified_noaa(root, stations, min_hours=3000):
    qualifying = {}
    for s in stations:
        # First benchmark uses US NOAA sources with published legacy QC mappings.
        # Canadian source 341 uses blank source quality codes and remains
        # provisional rather than being silently treated as QC approved.
        if s.get('provider') != 'NOAA_GHCNh' or s.get('country') != 'US':
            continue
        folder = root / 'observations' / 'NOAA_GHCNh' / s['station_id']
        coverage = {}
        for year in YEARS:
            meta = folder / (str(year) + '.psv.json')
            audit = folder / (str(year) + '.coverage.json')
            if not meta.is_file() or not audit.is_file():
                break
            m = json.loads(meta.read_text())
            a = json.loads(audit.read_text())
            if (m.get('status') != 'complete' or not m.get('sha256')
                    or m.get('sha256') != a.get('sha256')):
                break
            values = a.get('variables', {}).get('temperature', {})
            observed = int(values.get('observed_hours', 0))
            if observed < min_hours:
                break
            coverage[year] = observed
        if len(coverage) == len(YEARS):
            qualifying[s['station_id']] = (s, coverage)
    return qualifying

def choose_cluster(graph_path, eligible):
    candidates = []
    with pathlib.Path(graph_path).open() as f:
        for line in f:
            node = json.loads(line)
            if node.get('role') != 'training_target' or node['target_provider'] != 'NOAA_GHCNh':
                continue
            target = node['target_station_id']
            if target not in eligible:
                continue
            neighbors = [n for n in node['candidate_neighbors']
                         if n['provider'] == 'NOAA_GHCNh'
                         and n['station_id'] in eligible and n['distance_km'] <= 250]
            if len(neighbors) < 2:
                continue
            neighbors = neighbors[:3]
            coverage = sum(sum(eligible[x][1].values()) for x in
                           [target] + [n['station_id'] for n in neighbors])
            score = (len(neighbors), coverage, -sum(n['distance_km'] for n in neighbors))
            candidates.append((score, target, neighbors))
    if not candidates:
        raise ValueError('No qualified 2022-2025 NOAA regional cluster exists in current archive')
    _, target, neighbors = max(candidates)
    return target, neighbors

class ZipSourceLoader:
    def __init__(self, root, cache, budget_bytes=1_500_000_000):
        self.root = root
        self.cache = pathlib.Path(cache)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.budget = budget_bytes
        self.total = 0
        self.sources = []

    def read(self, station, year):
        name = str(year) + '.psv'
        folder = self.root / 'observations' / 'NOAA_GHCNh' / station
        file_path = folder / name
        meta = json.loads((folder / (name + '.json')).read_text())
        if meta.get('status') != 'complete' or not meta.get('sha256'):
            raise ValueError('Unverified NOAA source sidecar')
        if file_path.is_file():
            data = file_path.read_bytes()
        else:
            archive = meta.get('archive', {})
            if not archive.get('verified') or archive.get('source_sha256') != meta['sha256']:
                raise ValueError('Missing verified archived source')
            tag = archive['release_url'].rsplit('/', 1)[-1]
            part = archive['part']
            if not tag.startswith('research-hourly-') or '/' in part or '..' in part:
                raise ValueError('Unsafe archive reference')
            cache = self.cache / tag
            cache.mkdir(exist_ok=True)
            zipped = cache / part
            if not zipped.exists():
                subprocess.run(['gh', 'release', 'download', tag, '-R',
                                os.environ['GH_REPO'], '--pattern', part,
                                '--dir', str(cache), '--clobber'],
                               check=True, timeout=420, stdout=subprocess.DEVNULL)
                self.total += zipped.stat().st_size
                if self.total > self.budget:
                    raise ValueError('Downloaded archive exceeds pilot byte budget')
            if hash_bytes(zipped.read_bytes()) != archive['part_sha256']:
                raise ValueError('Archive ZIP SHA256 mismatch')
            member = 'observations/NOAA_GHCNh/' + station + '/' + name
            with zipfile.ZipFile(zipped) as z:
                info = z.getinfo(member)
                if info.file_size > 40_000_000:
                    raise ValueError('Single source exceeds bounded pilot size')
                data = z.read(info)
        if hash_bytes(data) != meta['sha256']:
            raise ValueError('NOAA source SHA256 mismatch')
        self.sources.append(dict(station=station, year=year, sha256=hash_bytes(data),
                                 bytes=len(data), source_url=meta.get('url')))
        return data

def load_temperature(data):
    records = {}
    counts = collections.Counter()
    reader = csv.DictReader(io.StringIO(data.decode('utf-8-sig')), delimiter='|')
    required = {'DATE', 'temperature', 'temperature_Quality_Code', 'temperature_Source_Code'}
    if not required.issubset(reader.fieldnames or []):
        raise ValueError('GHCNh headers lack required row-level QC columns')
    for row in reader:
        raw = row.get('temperature')
        value, _, status = normalize('NOAA_GHCNh', 'temperature', raw,
                                     row.get('temperature_Quality_Code'),
                                     row.get('temperature_Source_Code'))
        counts[status] += 1
        if raw is not None and str(raw).strip() not in ('', '-9999', '-9999.0'):
            counts['source_quality:' + str(row.get('temperature_Source_Code')) + ':' + str(row.get('temperature_Quality_Code'))] += 1
        if value is None:
            continue
        stamp = datetime.datetime.fromisoformat(row['DATE'].replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=UTC)
        stamp = stamp.astimezone(UTC)
        hour = stamp.replace(minute=0, second=0, microsecond=0)
        # Keep the most recent *valid* observation within the hour, no averaging.
        if hour not in records or stamp >= records[hour][0]:
            records[hour] = (stamp, value)
    return {hour: pair[1] for hour, pair in records.items()}, dict(counts)

def latest(series, stamps, asof, max_age_hours=9):
    pos = bisect.bisect_right(stamps, asof) - 1
    if pos < 0 or (asof-stamps[pos]) > datetime.timedelta(hours=max_age_hours):
        return None
    return series[stamps[pos]]

def examples(target_series, other_series, elevation_diff, horizon_hours=24, assumed_lag_hours=72):
    target_keys = sorted(target_series)
    other_keys = {key: sorted(series) for key, series in other_series.items()}
    for verification in target_keys:
        # Forecast issued 24h before verification; observation available with
        # explicitly assumed 72h delivery delay. Only old as-of rows used.
        issued = verification-datetime.timedelta(hours=horizon_hours)
        asof = issued-datetime.timedelta(hours=assumed_lag_hours)
        own = latest(target_series, target_keys, asof)
        if own is None:
            continue
        nearby = []
        for key, series in other_series.items():
            value = latest(series, other_keys[key], asof)
            if value is None:
                continue
            nearby.append(value + 0.0065 * elevation_diff[key])
        if len(nearby) < 1:
            continue
        neighbors = statistics.mean(nearby)
        d = issued.hour * 2 * math.pi / 24
        seasonal = (issued.timetuple().tm_yday-1) * 2 * math.pi / 365.25
        local = [1., own/30., math.sin(d), math.cos(d), math.sin(seasonal), math.cos(seasonal)]
        regional = local + [(neighbors-own)/15.]
        yield dict(year=verification.year, valid_at=verification, actual=target_series[verification],
                   baseline=own, local=local, regional=regional)

def ridge_fit(samples, which, lam=0.5):
    xs = [r[which] for r in samples]
    ys = [r['actual'] for r in samples]
    if not xs or len(xs) < len(xs[0]) * 5:
        raise ValueError('Insufficient training examples')
    n = len(xs[0])
    a = [[0.]* (n+1) for _ in range(n)]
    for x, y in zip(xs, ys):
        for j in range(n):
            a[j][-1] += x[j]*y
            for k in range(n):
                a[j][k] += x[j]*x[k]
    for j in range(1,n):
        a[j][j] += lam
    for j in range(n):
        pivot = max(range(j,n), key=lambda r: abs(a[r][j]))
        a[j], a[pivot] = a[pivot], a[j]
        if abs(a[j][j]) < 1e-10:
            raise ValueError('Singular training matrix')
        scale = a[j][j]
        a[j] = [v/scale for v in a[j]]
        for i in range(n):
            if i == j:
                continue
            fac = a[i][j]
            a[i] = [q - fac*v for q,v in zip(a[i], a[j])]
    return [a[j][-1] for j in range(n)]

def metrics(rows, w_local, w_region):
    if not rows:
        return dict(cases=0)
    diffs = collections.defaultdict(list)
    for item in rows:
        actual = item['actual']
        diffs['persistence'].append(abs(actual-item['baseline']))
        diffs['station_only'].append(abs(actual-sum(a*b for a,b in zip(w_local,item['local']))))
        diffs['regional'].append(abs(actual-sum(a*b for a,b in zip(w_region,item['regional']))))
    maes = {name+'_mae_c': round(statistics.mean(vals), 4) for name, vals in diffs.items()}
    delta = 100*(maes['station_only_mae_c']-maes['regional_mae_c'])/maes['station_only_mae_c'] if maes['station_only_mae_c'] else None
    return dict(cases=len(rows), **maes,
                regional_vs_station_only_skill_percent=round(delta, 2) if delta is not None else None)

def pilot(root, graph, out):
    stations = list(csv.DictReader((root/'stations.csv').open()))
    eligible = qualified_noaa(root, stations)
    target, neighbors = choose_cluster(graph, eligible)
    all_ids = [target] + [n['station_id'] for n in neighbors]
    with tempfile.TemporaryDirectory(prefix='atmos-pilot-') as tmp:
        loader = ZipSourceLoader(root, tmp)
        temps = collections.defaultdict(dict)
        qc_summary = {}
        for sid in all_ids:
            for year in YEARS:
                data = loader.read(sid, year)
                hours, qc = load_temperature(data)
                temps[sid].update(hours)
                qc_summary[sid+':'+str(year)] = dict(hours=len(hours), source_row_qc_reasons=qc)
    # Publish transparent screening diagnostics even if the pilot is blocked.
    pathlib.Path(out).mkdir(parents=True, exist_ok=True)
    diagnostics = dict(target_station=target, neighbors=all_ids[1:],
                       accepted_hours_by_station={sid:len(temps[sid]) for sid in all_ids},
                       row_level_screen=qc_summary, source_files=loader.sources)
    (pathlib.Path(out)/'quality_screen_diagnostics.json').write_text(json.dumps(diagnostics, indent=2)+'\\n')
    print(json.dumps(dict(target_station=target, accepted_hours_by_station=diagnostics['accepted_hours_by_station'],
                          screening_reasons={sid: {k:v for k,v in qc_summary.items() if k.startswith(sid+':')}
                                             for sid in all_ids}), indent=2), flush=True)
    if len(temps[target]) < 1000:
        raise ValueError('Too few quality-screened target temperature hours')
    target_alt = float(eligible[target][0]['elevation_m'])
    diff = {sid:float(eligible[sid][0]['elevation_m'])-target_alt for sid in all_ids[1:]}
    cases = list(examples(temps[target], {sid:temps[sid] for sid in all_ids[1:]}, diff))
    train = [r for r in cases if r['year'] in (2022,2023)]
    val = [r for r in cases if r['year'] == 2024]
    test = [r for r in cases if r['year'] == 2025]
    if len(train)<500 or len(val)<100 or len(test)<100:
        raise ValueError('Insufficient chronologically separated QC-screened hours: '
                         + str((len(train),len(val),len(test))))
    w_local = ridge_fit(train,'local')
    w_regional = ridge_fit(train,'regional')
    report = dict(status='exploratory_real_observation_regional_temperature_pilot',
                  target_station=target, neighbors=all_ids[1:],
                  baseline='same 24h target; latest already-available observation',
                  forecast_horizon_hours=24, assumed_observation_availability_lag_hours=72,
                  availability_lag_verified=False,
                  fit_years='2022-2023', validation_year=2024, evaluation_year=2025,
                  train_cases=len(train), validation=metrics(val,w_local,w_regional),
                  evaluation=metrics(test,w_local,w_regional),
                  source_files=loader.sources, row_level_qc=qc_summary,
                  station_only_weights=w_local, regional_weights=w_regional,
                  trained_variables=['temperature_c'],
                  quality_approved=False, production_deploy=False,
                  limitations=[
                      'Only a small same-region cluster; no spatial holdout evaluation.',
                      'Historical observation arrival timestamps unavailable; 72h lag is an assumption.',
                      'No radar, satellite, wind direction or dynamic upwind weighting.',
                      'Altitude correction uses simplified fixed lapse rate, not weather-dependent profile.',
                      'Source-specific checks are conservative, but not independent instrument certification.',
                      'A regional model must beat station-only benchmarks on broader unseen geography before claims.',
                  ])
    pathlib.Path(out).mkdir(parents=True, exist_ok=True)
    (pathlib.Path(out)/'regional_real_observation_pilot.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('source_files','row_level_qc','station_only_weights','regional_weights')},indent=2))
    return report

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--checkpoint', required=True)
    parser.add_argument('--neighbor-graph', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    pilot(pathlib.Path(args.checkpoint), args.neighbor_graph, args.out)

if __name__ == '__main__':
    main()
