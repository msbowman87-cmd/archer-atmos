import datetime
import subprocess
import tempfile
import unittest
from pathlib import Path
from atmos.free_tier_guard import (BudgetError, check_and_reserve, check_size,
                                  local_size, parse_s3_size, validate_target)

R2='https://1234567890abcdef1234567890abcdef.r2.cloudflarestorage.com'


class FreeTierGuardTests(unittest.TestCase):
    def test_remote_size_is_verified_and_has_headroom(self):
        self.assertEqual(parse_s3_size('Total Objects: 2\nTotal Size: 3,123\n'),3123)
        self.assertEqual(check_size(7_900_000_000),0)
        for output in ('', 'Total Size: 0\nTotal Size: 0'):
            with self.assertRaises(BudgetError):parse_s3_size(output)
        with self.assertRaises(BudgetError):check_size(7_900_000_001)

    def test_archive_cap_and_invalid_endpoint(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'archive.gz';path.write_bytes(b'test')
            self.assertEqual(local_size(root),4)
            with path.open('wb') as file:file.truncate(25_000_001)
            with self.assertRaises(BudgetError):local_size(root)
        with self.assertRaises(BudgetError):validate_target('atmos-archive','https://s3.amazonaws.com','auto')
        with self.assertRaises(BudgetError):validate_target('atmos-archive',R2,'us-east-1')

    def test_preflight_reserves_300_calls_and_stops_after_1200(self):
        calls=[]
        def good(args,**kw):
            calls.append((args,kw.get('input')))
            if 'ls' in args:return subprocess.CompletedProcess(args,0,b'Total Size: 100\n',b'')
            if args[4]=='-':return subprocess.CompletedProcess(args,0,b'900',b'')
            return subprocess.CompletedProcess(args,0,b'',b'')
        result=check_and_reserve('atmos-archive',R2,today=datetime.date(2026,10,31),runner=good)
        self.assertEqual(result['daily_requests_reserved'],1200)
        self.assertEqual(calls[-1][1],b'1200')
        self.assertIn('20261031.txt',calls[-1][0][4])
        def full(args,**kw):
            if 'ls' in args:return subprocess.CompletedProcess(args,0,b'Total Size: 100\n',b'')
            return subprocess.CompletedProcess(args,0,b'1200',b'')
        with self.assertRaises(BudgetError):check_and_reserve('atmos-archive',R2,runner=full)

    def test_404_counter_starts_at_zero_but_permissions_fail_closed(self):
        def missing(args,**kw):
            if 'ls' in args:return subprocess.CompletedProcess(args,0,b'Total Size: 0\n',b'')
            if args[4]=='-':return subprocess.CompletedProcess(args,1,b'',b'(404) Not Found')
            return subprocess.CompletedProcess(args,0,b'',b'')
        self.assertEqual(check_and_reserve('atmos-archive',R2,runner=missing)['daily_requests_reserved'],300)
        def denied(args,**kw):return subprocess.CompletedProcess(args,1,b'',b'403 AccessDenied')
        with self.assertRaises(BudgetError):check_and_reserve('atmos-archive',R2,runner=denied)


if __name__=='__main__':unittest.main()
