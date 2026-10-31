"""Global-first, strictly paired verification of already collected forecasts.

This does not download or invent independent observations. Locations without
verified ground truth are reported as missing, not as zero-error forecasts.
"""
import argparse
import csv
import json
from collections import defaultdict
from datetime import date
from math import isfinite
from pathlib import Path

from atmos.study_batch import locations

LEAD_BUCKETS = ((1, 3, '1-3'), (4, 7, '4-7'), (8, 14, '8-14'), (15, 30, '15-30'))


def latitude_zone(lat):
    a = abs(float(lat))
    return 'tropical' if a < 23.5 else 'midlatitude' if a < 66.5 else 'polar'


def manifest():
    """Equal-area global coordinate sample; not a curated station list."""
    return [dict(point, hemisphere='north' if point['lat'] >= 0 else 'south',
                 latitude_zone=latitude_zone(point['lat']),
                 observation_status='unverified', surface_type='unknown')
            for point in locations()]


def lead_bucket(issue, valid):
    days = (date.fromisoformat(valid) - date.fromisoformat(issue)).days
    for low, high, label in LEAD_BUCKETS:
        if low <= days <= high:
            return label
    raise ValueError('Forecast lead outside 1-30 days')


def evaluate(forecasts, observations, *, required_locations=200):
    """Compare models only on the same issue/date/location/metric truth.

    Forecast CSV: location_id, model, issue_date, date, metric, unit, value,
      valid_start_utc, valid_end_utc.
    Observation CSV: location_id, date, metric, unit, value,
      valid_start_utc, valid_end_utc, independent, quality_flag.
    Explicit identical UTC intervals are mandatory; gridded reanalyses must
    never be passed off as independent station observations.
    """
    truth = {}
    for o in observations:
        key = (o['location_id'], o['date'], o['metric'], o['unit'], o['valid_start_utc'], o['valid_end_utc'])
        if key in truth:
            raise ValueError('Duplicate observation interval')
        if o.get('independent') != 'true' or o.get('quality_flag') != 'verified':
            continue
        value = float(o['value'])
        if isfinite(value):
            truth[key] = value
    matched = defaultdict(dict)
    seen = set()
    for f in forecasts:
        key = (f['location_id'], f['issue_date'], f['date'], f['metric'], f['unit'],
               f['valid_start_utc'], f['valid_end_utc'])
        model = f['model']
        if (key, model) in seen:
            raise ValueError('Duplicate model forecast')
        seen.add((key, model))
        if f['valid_start_utc'] >= f['valid_end_utc']:
            raise ValueError('Invalid forecast interval')
        lead_bucket(f['issue_date'], f['date'])
        value = float(f['value'])
        if isfinite(value):
            matched[key][model] = value
    by_group = defaultdict(list)
    matched_locations = set()
    paired_count = 0
    for key, models in matched.items():
        loc, issue, day, metric, unit, start, end = key
        actual = truth.get((loc, day, metric, unit, start, end))
        if actual is None or not {'gfs', 'ecmwf'}.issubset(models):
            continue
        matched_locations.add(loc)
        paired_count += 1
        bucket = lead_bucket(issue, day)
        for group in (('global', 'all'), ('latitude_zone', latitude_zone_for_location(loc))):
            by_group[(group[0], group[1], bucket, metric, unit)].append(
                (abs(models['gfs']-actual), abs(models['ecmwf']-actual),
                 abs((models['gfs']+models['ecmwf'])/2-actual)))
    scores = []
    for (dimension, segment, bucket, metric, unit), errors in sorted(by_group.items()):
        n = len(errors)
        scores.append(dict(dimension=dimension, segment=segment, horizon=bucket,
                           metric=metric, unit=unit, paired_cases=n,
                           gfs_mae=sum(e[0] for e in errors)/n,
                           ecmwf_mae=sum(e[1] for e in errors)/n,
                           equal_blend_mae=sum(e[2] for e in errors)/n))
    return {'status':'exploratory' if paired_count else 'no_independent_pairs',
            'design_locations':required_locations,
            'independently_verified_locations':len(matched_locations),
            'model_and_truth_paired_cases':paired_count,
            'scores':scores,
            'limitations':['Equal-area global sampling does not guarantee land, ocean, elevation, or climate representation.',
                           'No claim of global accuracy until independent observations exist across regions and seasons.',
                           'Equal blend is an untrained comparator, not a production forecast.']}


def latitude_zone_for_location(location_id):
    # Only predeclared validation IDs get geographic labels; no guessing for
    # external stations. Extend with a verified station metadata registry.
    index = {p['id']:p['latitude_zone'] for p in manifest()}
    return index.get(location_id, 'unclassified')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--forecasts', required=True)
    parser.add_argument('--observations', required=True)
    parser.add_argument('--output', default='global-validation-report.json')
    args = parser.parse_args()
    with open(args.forecasts, newline='') as f:
        forecasts = list(csv.DictReader(f))
    with open(args.observations, newline='') as f:
        observations = list(csv.DictReader(f))
    report = evaluate(forecasts, observations)
    Path(args.output).write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
