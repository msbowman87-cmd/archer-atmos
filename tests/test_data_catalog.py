import unittest
from atmos.data_catalog import SOURCES,REQUIRED_FIELDS,validate_record

class CatalogTests(unittest.TestCase):
    def test_unique_sources(self):
        self.assertEqual(len(SOURCES),len({s["id"] for s in SOURCES}))
    def test_required_provenance(self):
        record={k:"sample" for k in REQUIRED_FIELDS}
        record["valid_start_utc"]="2026-01-01T00:00:00Z"
        record["valid_end_utc"]="2026-01-01T01:00:00Z"
        self.assertTrue(validate_record(record))
        del record["raw_checksum"]
        with self.assertRaises(ValueError):validate_record(record)
    def test_bad_interval(self):
        record={k:"sample" for k in REQUIRED_FIELDS}
        record["valid_start_utc"]="2026-01-02T00:00:00Z"
        record["valid_end_utc"]="2026-01-01T00:00:00Z"
        with self.assertRaises(ValueError):validate_record(record)
if __name__=="__main__":unittest.main()
