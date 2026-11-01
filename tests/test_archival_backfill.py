import csv
import json
import tempfile
import unittest
from pathlib import Path

from atmos.archive_package import package_shard
from atmos.backfill_wave import plan, run_wave
from atmos.rich_history import HOURLY


class ArchivalBackfillTests(unittest.TestCase):
    def test_plan_is_bounded_global_and_seasonally_interleaved(self):
        first = plan(0, per_wave=20)
        self.assertEqual(len(first), 20)
        self.assertEqual(len({(x['year'],x['month']) for x in first}), 20)
        self.assertEqual(first[0]['shard'], 379)
        self.assertEqual(len(plan(4799, per_wave=5)), 5)
        self.assertEqual(plan(4800), [])
        with self.assertRaises(ValueError):plan(-1)
        with self.assertRaises(ValueError):plan(0, per_wave=100)

    def test_archive_checks_rows_schema_provenance_and_digest(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            label = 'rich_5000_202401_shard_0379'
            with (root/(label+'.csv')).open('w',newline='') as handle:
                writer = csv.writer(handle)
                writer.writerow(['location_id','latitude','longitude','valid_time_utc',*HOURLY])
                writer.writerow(['G01896',1,2,'2024-01-01T00:00',*[1]*len(HOURLY)])
            summary = {'source':'https://archive-api.open-meteo.com/v1/archive',
                'source_classification':'model-derived historical reanalysis, NOT station truth',
                'year':2024,'month':1,'grid_count':5000,'shard':379,
                'locations_attempted':1,'locations_succeeded':1,'rows':1,
                'failures':[],'sources':[{'location_id':'G01896','raw_sha256':'abc'}],
                'missing_values_by_field':{name:0 for name in HOURLY},
                'retrieved_at_utc':'2026-11-01T00:00:00+00:00'}
            source = root/(label+'.json')
            source.write_text(json.dumps(summary))
            result = package_shard(source,root/'out')
            self.assertTrue(Path(result['csv_gzip']).exists())
            manifest=json.loads(Path(result['manifest']).read_text())
            self.assertFalse(manifest['independent_observation'])
            self.assertEqual(manifest['rows'],1)
            summary['rows']=2
            source.write_text(json.dumps(summary))
            with self.assertRaises(ValueError):package_shard(source,root/'bad')

    def test_wave_archives_results_from_injected_collector(self):
        with tempfile.TemporaryDirectory() as folder:
            def fake(year,month,shard,*,grid_count,shard_size,output):
                output=Path(output);output.mkdir(parents=True,exist_ok=True)
                label=f'rich_{grid_count}_{year}{month:02d}_shard_{shard:04d}'
                with (output/(label+'.csv')).open('w',newline='') as handle:
                    writer=csv.writer(handle)
                    writer.writerow(['location_id','latitude','longitude','valid_time_utc',*HOURLY])
                    writer.writerow(['G00001',0,0,'2024-01-01T00:00',*[0]*len(HOURLY)])
                summary={'source':'https://archive-api.open-meteo.com/v1/archive',
                    'source_classification':'model-derived historical reanalysis, NOT station truth',
                    'year':year,'month':month,'grid_count':grid_count,'shard':shard,
                    'locations_attempted':1,'locations_succeeded':1,'rows':1,
                    'failures':[],'sources':[],
                    'missing_values_by_field':{name:0 for name in HOURLY},
                    'retrieved_at_utc':'2026-11-01T00:00:00+00:00'}
                (output/(label+'.json')).write_text(json.dumps(summary))
                return summary
            result=run_wave(0, output=folder, per_wave=2, collector=fake)
            self.assertEqual(result['rows'],2)
            self.assertEqual(len(list((Path(folder)/'archive').glob('*.gz'))),2)


if __name__ == '__main__':unittest.main()
