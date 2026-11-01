"""Fail-closed budgets for Atmos's dedicated Cloudflare R2 research archive.

Not an account-wide spending cap: other R2 buckets and the public site are
outside this workflow's controls.
"""
import argparse
import datetime
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

ARCHIVE_LIMIT_BYTES = 8_000_000_000
LANE_LIMIT_BYTES = 25_000_000
LANES = 4
DAILY_REQUEST_BUDGET = 1200
# 4 lanes × 5 shards × 5 locations × 3 possible HTTP attempts.
REQUESTS_RESERVED_PER_RUN = 300


class BudgetError(RuntimeError):
    pass


def validate_target(bucket, endpoint, region):
    url = urlparse(endpoint)
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]', bucket or ''):
        raise BudgetError('A dedicated R2 bucket is required')
    if (region != 'auto' or url.scheme != 'https' or not url.hostname or
            not url.hostname.endswith('.r2.cloudflarestorage.com') or
            url.username or url.password or url.path not in ('', '/') or url.query):
        raise BudgetError('Free-tier guard requires a Cloudflare R2 HTTPS endpoint and region=auto')
    return ['--endpoint-url', endpoint]


def parse_s3_size(output):
    matches = re.findall(r'^Total Size:\s*([\d,]+)\s*$', output, re.MULTILINE)
    if len(matches) != 1:
        raise BudgetError('Archive size is unverifiable; refusing collection')
    return int(matches[0].replace(',', ''))


def check_size(used_bytes):
    if not isinstance(used_bytes, int) or used_bytes < 0 or (
            used_bytes + LANE_LIMIT_BYTES * LANES > ARCHIVE_LIMIT_BYTES):
        raise BudgetError('Archive near 8 GB safety limit; collection paused')
    return ARCHIVE_LIMIT_BYTES - used_bytes - LANE_LIMIT_BYTES * LANES


def local_size(directory):
    root = Path(directory)
    if not root.is_dir():
        raise BudgetError('Archive directory not found')
    files = [p for p in root.rglob('*') if p.is_file()]
    if not files:
        raise BudgetError('No verified archive files to upload')
    total = sum(p.stat().st_size for p in files)
    if total > LANE_LIMIT_BYTES:
        raise BudgetError('Lane exceeds reserved 25 MB; upload blocked')
    return total


def check_and_reserve(bucket, endpoint, region='auto', *, today=None, runner=subprocess.run):
    opts = validate_target(bucket, endpoint, region)

    def invoke(args, **kwargs):
        return runner(args, capture_output=True, **kwargs)

    result = invoke(['aws','s3','ls',f's3://{bucket}/atmos/',
                     '--recursive','--summarize',*opts])
    if result.returncode:
        raise BudgetError('Cannot list archive usage; no provider calls permitted')
    used = parse_s3_size(result.stdout.decode('utf-8','replace'))
    headroom = check_size(used)

    day = today or datetime.datetime.now(datetime.timezone.utc).date()
    key = f's3://{bucket}/atmos/control/request-budget/{day:%Y%m%d}.txt'
    previous = invoke(['aws','s3','cp',key,'-','--only-show-errors',*opts])
    if previous.returncode == 0:
        text = previous.stdout.decode('ascii','strict').strip()
        if not text.isdecimal():
            raise BudgetError('Invalid persisted daily request counter')
        old = int(text)
    elif '404' in previous.stderr.decode('utf-8','replace'):
        old = 0
    else:
        raise BudgetError('Daily budget unavailable; no provider calls permitted')
    total = old + REQUESTS_RESERVED_PER_RUN
    if total > DAILY_REQUEST_BUDGET:
        raise BudgetError('Daily historical request budget exhausted')
    saved = invoke(['aws','s3','cp','-',key,'--only-show-errors',*opts],
                   input=str(total).encode('ascii'))
    if saved.returncode:
        raise BudgetError('Could not reserve daily budget; no provider calls permitted')
    return {'archive_bytes':used,'reserved_headroom_bytes':headroom,
            'daily_requests_reserved':total}


def main():
    parser=argparse.ArgumentParser()
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--preflight',action='store_true')
    mode.add_argument('--local-archive')
    args=parser.parse_args()
    if args.preflight:
        result=check_and_reserve(os.getenv('ATMOS_ARCHIVE_BUCKET',''),
            os.getenv('ATMOS_ARCHIVE_ENDPOINT',''),os.getenv('AWS_DEFAULT_REGION',''))
    else:
        result={'lane_bytes':local_size(args.local_archive)}
    print('Atmos free-tier guard:',result)


if __name__=='__main__':
    main()
