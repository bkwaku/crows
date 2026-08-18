from __future__ import annotations

import unittest

from benchmarks.prototype import CASES, run


class PrototypeBenchmarkTests(unittest.TestCase):
    def test_all_gold_dependencies_are_retained_with_large_reduction(self) -> None:
        rows = run()

        self.assertEqual(len(rows), len(CASES))
        for row in rows:
            with self.subTest(need=row["need"]):
                self.assertEqual(row["projection_recall"], 1.0)
                self.assertGreater(row["context_reduction"], 0.98)


if __name__ == "__main__":
    unittest.main()

