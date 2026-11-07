"""A benchmark comparison never mixes different circuits, steps or platforms."""
import tempfile
import unittest
from pathlib import Path

from benchmark import BenchmarkHistory, run_benchmark


class BenchmarkHistoryTests(unittest.TestCase):
    def test_comparable_history_and_persistence(self):
        with tempfile.TemporaryDirectory() as folder:
            store = BenchmarkHistory(Path(folder) / "history.json")
            first = run_benchmark("logic_100", 2)
            second = run_benchmark("logic_100", 2)
            other = run_benchmark("logic_100", 3)
            self.assertIsNone(store.record(first))
            self.assertEqual(store.record(second), first)
            self.assertIsNone(store.record(other))
            self.assertEqual(len(BenchmarkHistory(store.path).read()), 3)
            self.assertFalse(store.comparable(first, other))

    def test_corrupt_history_is_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "history.json"
            path.write_text("{}", encoding="utf-8")
            self.assertRaises(ValueError, BenchmarkHistory(path).read)


if __name__ == "__main__": unittest.main()
