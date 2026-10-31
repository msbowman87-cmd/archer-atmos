import unittest
from atmos.global_grid import points, shard_points

class GlobalGridTests(unittest.TestCase):
    def test_5000_distinct_points(self):
        grid = list(points())
        self.assertEqual(len(grid), 5000)
        self.assertEqual(len({(x['lat'], x['lon']) for x in grid}), 5000)
        self.assertTrue(all(-90 <= p['lat'] <= 90 and -180 <= p['lon'] <= 180 for p in grid))
        self.assertEqual(grid[0]['id'], 'G00001')
        self.assertEqual(grid[-1]['id'], 'G05000')
    def test_scales_to_20000(self):
        self.assertEqual(len(list(points(20000))), 20000)
    def test_shard_edges(self):
        parts = [shard_points(i, count=105, shard_size=50) for i in range(3)]
        self.assertEqual([len(p) for p in parts], [50, 50, 5])
        self.assertEqual([x['id'] for part in parts for x in part], [x['id'] for x in points(105)])
    def test_invalid(self):
        for count in (0, 20001):
            with self.assertRaises(ValueError): list(points(count))
        with self.assertRaises(ValueError): shard_points(100, count=5000)

if __name__ == '__main__': unittest.main()
