"""Verify and gzip historical shards for durable object-storage upload.

The output is not independent station truth. The manifest is immutable
provenance for an S3-compatible object archive; storage credentials are handled
by the Actions runner, not by this module.
"""
import argparse
import csv
import gzip
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from atmos.rich_history import HOURLY


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def package_shard(summary_path, output):
    """Make a deterministic gzip and a SHA-256 manifest for one completed shard."""
    summary_path = Path(summary_path)
    if summary_path.suffix != '.json':
        raise ValueError('Expected a rich history JSON summary')
    csv_path = summary_path.with_suffix('.csv')
    if not csv_path.is_file():
        raise FileNotFoundError(csv_path)
    summary = json.loads(summary_path.read_text())
    if summary.get('source_classification') != 'model-derived historical reanalysis, NOT station truth':
        raise ValueError('Historical provenance is missing or unexpected')
    if not isinstance(summary.get('rows'), int) or summary['rows'] <= 0:
        raise ValueError('No historical rows to archive')
    if summary.get('locations_succeeded', 0) <= 0:
        raise ValueError('No historical locations succeeded')
    with csv_path.open(newline='') as handle:
        reader = csv.reader(handle)
        expected = ['location_id', 'latitude', 'longitude', 'valid_time_utc', *HOURLY]
        if next(reader, None) != expected:
            raise ValueError('CSV schema differs from the collector fields')
        row_count = 0
        missingness = {name: 0 for name in HOURLY}
        for row in reader:
            if len(row) != len(expected):
                raise ValueError('Historical CSV row has unexpected field count')
            row_count += 1
            for name, value in zip(HOURLY, row[4:]):
                if value == '':
                    missingness[name] += 1
    if row_count != summary['rows']:
        raise ValueError('Summary row count does not match CSV contents')
    if ('missing_values_by_field' in summary and
            missingness != summary['missing_values_by_field']):
        raise ValueError('Source missingness totals do not match CSV contents')

    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    result_path = output / (csv_path.name + '.gz')
    manifest_path = output / (summary_path.stem + '.manifest.json')
    # Explicit mtime and empty gzip filename make content reproducible.
    with csv_path.open('rb') as source, result_path.open('wb') as dest:
        with gzip.GzipFile(fileobj=dest, mode='wb', mtime=0, filename='') as zipped:
            shutil.copyfileobj(source, zipped)
    manifest = {
        'format_version': 1,
        'dataset_kind': 'global_hourly_model_derived_history',
        'independent_observation': False,
        'source_url': summary['source'],
        'source_classification': summary['source_classification'],
        'year': summary['year'], 'month': summary['month'],
        'grid_count': summary['grid_count'], 'shard': summary['shard'],
        'locations_attempted': summary['locations_attempted'],
        'locations_succeeded': summary['locations_succeeded'],
        'failures': summary['failures'],
        'source_response_hashes': summary['sources'],
        'missing_values_by_field': missingness,
        'missingness_reconstructed_from_csv': 'missing_values_by_field' not in summary,
        'fields': list(HOURLY), 'rows': row_count,
        'retrieved_at_utc': summary['retrieved_at_utc'],
        'packaged_at_utc': datetime.now(timezone.utc).isoformat(),
        'csv_file': result_path.name,
        'csv_sha256': digest(csv_path),
        'csv_gzip_sha256': digest(result_path),
        'csv_gzip_bytes': result_path.stat().st_size,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    return {'csv_gzip': str(result_path), 'manifest': str(manifest_path),
            'location_count': summary['locations_succeeded'], 'rows': row_count,
            'partial': bool(summary['failures'])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--summary', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(package_shard(args.summary, args.output), indent=2))


if __name__ == '__main__':
    main()
