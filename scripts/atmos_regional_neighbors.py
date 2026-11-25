#!/usr/bin/env python3
"""Generate geographic/upstream candidate graph, never a fitted forecast model.

Only 2016-2023 training readiness is used to select neighbors. The 2024 and
2025 observations are not examined or used to create graph eligibility.
Spatial holdouts are deterministic geographic 3x3-degree tiles.
"""
import argparse
import collections
import csv
import hashlib
import json
import math
import pathlib

RADIUS_EARTH_KM = 6371.0088

def distance_bearing(a, b):
    la, lo = map(math.radians, (float(a['latitude']), float(a['longitude'])))
    lb, lob = map(math.radians, (float(b['latitude']), float(b['longitude'])))
    dlat = lb - la
    dlon = (lob - lo + math.pi) % (2 * math.pi) - math.pi
    h = math.sin(dlat/2)**2 + math.cos(la)*math.cos(lb)*math.sin(dlon/2)**2
    distance = 2 * RADIUS_EARTH_KM * math.asin(min(1, math.sqrt(h)))
    y = math.sin(dlon)*math.cos(lb)
    x = math.cos(la)*math.sin(lb)-math.sin(la)*math.cos(lb)*math.cos(dlon)
    bearing = math.degrees(math.atan2(y, x)) % 360
    return distance, bearing

def spatial_tile(station):
    return (math.floor(float(station['latitude']) / 3),
            math.floor(float(station['longitude']) / 3))

def is_spatial_holdout(station):
    tile = spatial_tile(station)
    digest = hashlib.sha256(('atmos-tile-v1:' + str(tile)).encode()).digest()
    return int.from_bytes(digest[:4], 'big') % 5 == 0

def generate(manifest, readiness, k=20, radius_km=300):
    if not 1 <= k <= 40 or not 10 <= radius_km <= 1500:
        raise ValueError('Invalid neighbor graph size or distance')
    stations = list(csv.DictReader(pathlib.Path(manifest).open(encoding='utf-8-sig', newline='')))
    indexed = {(s['provider'], s['station_id']): s for s in stations}
    ready = list(csv.DictReader(pathlib.Path(readiness).open(encoding='utf-8-sig', newline='')))
    if len(indexed) != len(stations) or len(ready) != len(stations):
        raise ValueError('Manifest or readiness count does not match')
    selected = {}
    for row in ready:
        key = (row['provider'], row['station_id'])
        if key not in indexed or key in selected:
            raise ValueError('Missing or duplicate readiness identity')
        if row['readiness'] != 'coverage_candidate_qc_pending':
            continue
        station = indexed[key]
        if not all(math.isfinite(float(station[geo])) for geo in ('latitude', 'longitude', 'elevation_m')):
            raise ValueError('Nonfinite station coordinates')
        selected[key] = dict(station, train_variables=set(filter(None, row['training_variables'].split(';'))),
                             train_years=set(filter(None, row['training_years'].split(';'))),
                             heldout=is_spatial_holdout(station))
    # Two-degree grid provides a bounded neighbor search over continental-scale areas.
    # Longitude wraps across the dateline.
    grid = collections.defaultdict(list)
    for key, station in selected.items():
        grid[(math.floor(float(station['latitude'])/2),
              math.floor((float(station['longitude'])+180)/2) % 180)].append(key)
    targets = []
    status = collections.Counter()
    for key, site in sorted(selected.items()):
        lat = float(site['latitude'])
        lon = float(site['longitude'])
        lat_cells = math.ceil(radius_km/111/2)+1
        lon_cells = min(90, math.ceil(radius_km/max(1,111*abs(math.cos(math.radians(lat))))/2)+1)
        center_lat = math.floor(lat/2)
        center_lon = math.floor((lon+180)/2) % 180
        neighbors = []
        for ilat in range(center_lat-lat_cells, center_lat+lat_cells+1):
            for ilon_offset in range(-lon_cells, lon_cells+1):
                for candidate_key in grid.get((ilat, (center_lon+ilon_offset) % 180), []):
                    if candidate_key == key:
                        continue
                    candidate = selected[candidate_key]
                    # Spatial holdouts are targets for evaluation, never training
                    # sources. Prevent leakage into training via neighbor features.
                    if candidate['heldout']:
                        continue
                    shared_vars = site['train_variables'] & candidate['train_variables']
                    shared_years = site['train_years'] & candidate['train_years']
                    if not shared_vars or not shared_years:
                        continue
                    km, bearing = distance_bearing(site, candidate)
                    if km > radius_km:
                        continue
                    neighbors.append(dict(provider=candidate_key[0], station_id=candidate_key[1],
                                          distance_km=round(km, 2),
                                          bearing_from_target_deg=round(bearing, 1),
                                          elevation_difference_m=round(
                                              float(candidate['elevation_m'])-float(site['elevation_m']), 1),
                                          overlapping_train_years=sorted(shared_years),
                                          shared_train_variables=sorted(shared_vars)))
        neighbors.sort(key=lambda n:(n['distance_km'],n['provider'],n['station_id']))
        chosen = neighbors[:k]
        if site['heldout']:
            role = 'spatial_holdout_target'
        else:
            role = 'training_target'
        status[role] += 1
        status['targets_with_neighbors' if chosen else 'targets_without_neighbors'] += 1
        targets.append(dict(target_provider=key[0], target_station_id=key[1],
                            spatial_tile=list(spatial_tile(site)), role=role,
                            latitude=float(site['latitude']), longitude=float(site['longitude']),
                            elevation_m=float(site['elevation_m']),
                            target_training_years=sorted(site['train_years']),
                            target_training_variables=sorted(site['train_variables']),
                            candidate_neighbors=chosen))
    report = dict(station_manifest_sha256=hashlib.sha256(pathlib.Path(manifest).read_bytes()).hexdigest(),
                  readiness_sha256=hashlib.sha256(pathlib.Path(readiness).read_bytes()).hexdigest(),
                  graph_targets=len(targets), count=dict(status), k=k, radius_km=radius_km,
                  training_years='2016-2023', spatial_holdout='deterministic 3-degree geographic tiles; 20% hash allocation',
                  quality_approved=False, trained=False,
                  notes=[
                      'Graph is only geographic/temporal candidate topology; no actual forecast training has run.',
                      'No real-time upwind weighting yet: wind speed/direction must be read as of forecast issue.',
                      '2024 and 2025 observations have not been used to choose graph neighbors.',
                      'Spatial holdout stations cannot serve as neighbors for training targets.',
                      'Station altitude is retained; pressure levels require physically consistent reduction before combining.',
                      'Neighbors must have overlap in 2016-2023 training years and source variables.',
                  ])
    return targets, report

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--readiness', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--neighbors', type=int, default=20)
    parser.add_argument('--radius-km', type=int, default=300)
    args = parser.parse_args()
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    targets, report = generate(args.manifest, args.readiness, args.neighbors, args.radius_km)
    with (out / 'regional_neighbor_candidates.jsonl').open('w') as stream:
        for record in targets:
            stream.write(json.dumps(record, separators=(',', ':')) + '\n')
    (out / 'regional_graph_summary.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
