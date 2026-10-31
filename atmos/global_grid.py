"""Stable equal-area worldwide research grid, separate from legacy 200 points."""
import argparse
import csv
import math
from pathlib import Path

DEFAULT_COUNT = 5000
MAX_COUNT = 20000
GOLDEN_ANGLE = math.pi * (3 - math.sqrt(5))

def points(count=DEFAULT_COUNT):
    if not isinstance(count, int) or not 1 <= count <= MAX_COUNT:
        raise ValueError('Grid count must be an integer from 1 to 20000')
    for i in range(count):
        z = 1 - 2 * (i + .5) / count
        yield {'id': f'G{i+1:05d}',
               'lat': round(math.degrees(math.asin(z)), 5),
               'lon': round(((math.degrees(i * GOLDEN_ANGLE) + 180) % 360) - 180, 5)}

def shard_points(shard, *, count=DEFAULT_COUNT, shard_size=50):
    if not isinstance(count, int) or not 1 <= count <= MAX_COUNT:
        raise ValueError('Invalid grid count')
    if not isinstance(shard_size, int) or not 1 <= shard_size <= 200:
        raise ValueError('Shard size must be 1-200')
    if not isinstance(shard, int) or not 0 <= shard < math.ceil(count / shard_size):
        raise ValueError('Shard index is out of range')
    start = shard * shard_size
    return [p for i, p in enumerate(points(count)) if start <= i < start + shard_size]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--count', type=int, default=DEFAULT_COUNT)
    parser.add_argument('--output', default='global-grid-5000.csv')
    args = parser.parse_args()
    rows = list(points(args.count))
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['id','lat','lon'])
        writer.writeheader()
        writer.writerows(rows)
    print(f'Generated {len(rows)} coordinates: {path}')

if __name__ == '__main__':
    main()
