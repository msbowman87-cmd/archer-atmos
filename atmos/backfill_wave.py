"""Bounded, geographically and seasonally interleaved global history backfill.

The 5,000-site cohort is a research sampling grid, not the model's worldwide
resolution. A wave collects only a few monthly shards, never the whole planet.
"""
import argparse
import json
import math
from pathlib import Path

from atmos.archive_package import package_shard
from atmos.rich_history import run as collect


def plan(wave, *, grid_count=5000, shard_size=5, years=(2024, 2025),
         per_wave=5):
    if not isinstance(wave, int) or wave < 0:
        raise ValueError('Wave must be a non-negative integer')
    if not 1 <= shard_size <= 10 or grid_count not in (5000, 20000):
        raise ValueError('Use a supported 5,000/20,000-site bounded grid')
    if not 1 <= per_wave <= 20:
        raise ValueError('At most 20 five-point shards per runner')
    years = tuple(years)
    if not years or any(not 1940 <= y <= 2025 for y in years):
        raise ValueError('Use completed historic years through 2025')
    months = [(y, month) for y in years for month in range(1, 13)]
    shards = math.ceil(grid_count / shard_size)
    total = len(months) * shards
    start = wave * per_wave
    if start >= total:
        return []
    # The multiplier is coprime with both 1,000 and 4,000 shard counts.
    stride = 541
    return [
        {'year': months[i % len(months)][0],
         'month': months[i % len(months)][1],
         'shard': ((i // len(months)) * stride + 379) % shards}
        for i in range(start, min(total, start + per_wave))
    ]


def run_wave(wave, *, output='atmos-backfill', grid_count=5000, shard_size=5,
             years=(2024, 2025), per_wave=5, collector=collect):
    root = Path(output)
    raw, archive = root / 'raw', root / 'archive'
    tasks = plan(wave, grid_count=grid_count, shard_size=shard_size,
                 years=years, per_wave=per_wave)
    if not tasks:
        raise ValueError('Wave is past the end of the backfill plan')
    results = []
    for task in tasks:
        summary = collector(task['year'], task['month'], task['shard'],
                            grid_count=grid_count, shard_size=shard_size,
                            output=raw)
        label = f"rich_{grid_count}_{task['year']}{task['month']:02d}_shard_{task['shard']:04d}"
        archived = package_shard(raw / (label + '.json'), archive)
        results.append({**task, 'rows': summary['rows'],
                        'failures': summary['failures'], 'archive': archived})
    report = {'wave':wave, 'grid_count':grid_count, 'shard_size':shard_size,
              'years':list(years), 'completed_tasks':len(results),
              'rows':sum(item['rows'] for item in results),
              'partial_tasks':sum(bool(item['failures']) for item in results),
              'results':results}
    archive.mkdir(parents=True, exist_ok=True)
    (archive / f'wave_{wave:06d}.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--wave', type=int, required=True)
    parser.add_argument('--output', default='atmos-backfill')
    parser.add_argument('--grid-count', type=int, default=5000)
    parser.add_argument('--per-wave', type=int, default=5)
    parser.add_argument('--years', default='2024,2025')
    args = parser.parse_args()
    years = tuple(int(y.strip()) for y in args.years.split(','))
    result = run_wave(args.wave, output=args.output, grid_count=args.grid_count,
                      per_wave=args.per_wave, years=years)
    print(json.dumps({'wave':args.wave,'rows':result['rows'],
                      'partial_tasks':result['partial_tasks']},indent=2))
    if result['partial_tasks']:
        raise SystemExit('Partial collection: archive was prepared, inspect failures and rerun this wave')


if __name__ == '__main__':
    main()
