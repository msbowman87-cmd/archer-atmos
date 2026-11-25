#!/usr/bin/env python3
"""Conservative cross-provider observation normalization and QC inventory.

Do not call observations certified: blank ECCC flags and absent IEM QC are only
provisional. NOAA GHCNh QC must be interpreted with its *source code*.
Raw source records are not modified and unknown fields/codes fail closed.
"""
import argparse
import collections
import json
import math
import pathlib

MISSING = {'', 'M', 'NULL', '-9999', '-9999.0', '-9999.9', '-999.9'}
# Format: raw name -> (canonical variable, raw unit, multiplier, offset, plausible min, max)
SPECS = {
    'NOAA_GHCNh': {
        'temperature': ('temperature_c', 'C', 1, 0, -95, 65),
        'relative_humidity': ('relative_humidity_pct', '%', 1, 0, 0, 100),
        'wind_speed': ('wind_speed_mps', 'm/s', 1, 0, 0, 110),
        'wind_direction': ('wind_direction_deg', 'deg', 1, 0, 0, 360),
        'station_level_pressure': ('station_pressure_hpa', 'hPa', 1, 0, 350, 1100),
        'sea_level_pressure': ('sea_level_pressure_hpa', 'hPa', 1, 0, 800, 1100),
        'precipitation': ('precipitation_mm', 'mm', 1, 0, 0, 1000),
    },
    'ECCC': {
        'TEMP': ('temperature_c', 'C', 1, 0, -95, 65),
        'RELATIVE_HUMIDITY': ('relative_humidity_pct', '%', 1, 0, 0, 100),
        'WIND_SPEED': ('wind_speed_mps', 'km/h', 1 / 3.6, 0, 0, 110),
        'WIND_DIRECTION': ('wind_direction_deg', '10deg', 10, 0, 0, 360),
        'STATION_PRESSURE': ('station_pressure_hpa', 'kPa', 10, 0, 350, 1100),
        'PRECIP_AMOUNT': ('precipitation_mm', 'mm', 1, 0, 0, 1000),
    },
    'IEM_ASOS': {
        'tmpf': ('temperature_c', 'F', 5 / 9, -32 * 5 / 9, -95, 65),
        'relh': ('relative_humidity_pct', '%', 1, 0, 0, 100),
        'sknt': ('wind_speed_mps', 'knots', 0.514444, 0, 0, 110),
        'drct': ('wind_direction_deg', 'deg', 1, 0, 0, 360),
        'mslp': ('sea_level_pressure_hpa', 'millibar', 1, 0, 800, 1100),
        'alti': ('altimeter_hpa', 'inHg', 33.8638866667, 0, 800, 1100),
        'p01i': ('precipitation_mm', 'in', 25.4, 0, 0, 1000),
    },
}
# NOAA documentation: https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/doc/ghcnh_DOCUMENTATION.pdf
GHCNH_QUALITY = {
    **{code: {'1', '5'} for code in ('313', '314', '315', '322', '335', '343', '344', '346')},
    **{code: {'1'} for code in ('220', '221', '222', '223', '347', '348')},
}
# Source 345 only has "0" Good for wind speed / relative humidity.
GHCNH_345_FIELDS = {'relative_humidity', 'wind_speed'}

def normalize(provider, field, raw, qc=None, source_code=None):
    """Return (normalized value | None, canonical name | None, screening reason).

    A returned value is plausible and provisionally screened, NOT certified QC.
    """
    spec = SPECS.get(provider, {}).get(field)
    if not spec:
        return None, None, 'unmapped_field'
    name, unit, scale, offset, lower, upper = spec
    if raw is None or str(raw).strip().upper() in MISSING:
        return None, name, 'missing'
    if str(raw).strip().upper() in {'T', 'TRACE'}:
        return None, name, 'trace_not_numeric'
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return None, name, 'not_numeric'
    if not math.isfinite(number):
        return None, name, 'nonfinite'
    value = number * scale + offset
    if not lower <= value <= upper:
        return None, name, 'outside_plausibility_bounds'
    flag = str(qc).strip() if qc is not None else ''
    if provider == 'NOAA_GHCNh':
        src = str(source_code).strip() if source_code is not None else ''
        if src == '345' and field in GHCNH_345_FIELDS:
            allowed = {'0'}
        else:
            allowed = GHCNH_QUALITY.get(src, set())
        if not allowed or flag not in allowed:
            return None, name, 'noaa_source_quality_not_approved'
        return value, name, 'noaa_documented_source_quality_pass'
    if flag:
        return None, name, 'source_flag_uninterpreted'
    # The source does not supply a row-level certified QC code; values are for
    # provisional *research only* and must not be labeled quality-approved.
    return value, name, 'unflagged_provisional'

def profile_audit(coverage_batches):
    by_source = collections.defaultdict(lambda: collections.Counter())
    flags = collections.Counter()
    mapped = collections.Counter()
    periods = 0
    for line in pathlib.Path(coverage_batches).open(encoding='utf-8'):
        if not line.strip():
            continue
        item = json.loads(line)
        provider = item['provider']
        periods += 1
        for raw_name, stats in item.get('variables', {}).items():
            if raw_name not in SPECS.get(provider, {}):
                continue
            canonical = SPECS[provider][raw_name][0]
            key = (provider, canonical, raw_name)
            by_source[key]['periods'] += 1
            by_source[key]['nonmissing_source_records'] += int(stats.get('nonmissing_records', 0))
            by_source[key]['observed_hours_unfiltered'] += int(stats.get('observed_hours', 0))
            for code, number in stats.get('source_quality_flags', {}).items():
                flags[(provider, raw_name, str(code))] += int(number)
            mapped[(provider, canonical)] += 1
    return dict(
        status='quality_profile_not_training_certification',
        source_periods_read=periods,
        fields=[dict(provider=p, canonical_variable=c, raw_field=f, **counts)
                for (p, c, f), counts in sorted(by_source.items())],
        source_flags=[dict(provider=p, raw_field=f, flag=flag, source_record_count=count)
                      for (p, f, flag), count in sorted(flags.items())],
        unit_schema={p: {field: dict(canonical_variable=spec[0], source_unit=spec[1],
                                    multiplier=spec[2], offset=spec[3],
                                    plausible_min=spec[4], plausible_max=spec[5])
                         for field, spec in fields.items()} for p, fields in SPECS.items()},
        quality_approved=False,
        notes=[
            'Aggregated quality flags cannot identify which hourly bins were good.',
            'NOAA source-code and quality-code pairs require the individual raw observation rows.',
            'IEM has limited upstream QC; ECCC unflagged values remain provisional.',
            'No pressure reduction or altitude correction; station and sea-level pressure are separate.',
            'Precipitation report accumulation/trace semantics require further row-level validation.',
            'Plausibility screening is not station-instrument certification.',
        ])

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--coverage-batches', required=True)
    p.add_argument('--out', required=True)
    args = p.parse_args()
    report = profile_audit(args.coverage_batches)
    path = pathlib.Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(status=report['status'], audited_periods=report['source_periods_read'],
                          field_profiles=len(report['fields']), flagged_types=len(report['source_flags']),
                          quality_approved=False), indent=2))

if __name__ == '__main__':
    main()
