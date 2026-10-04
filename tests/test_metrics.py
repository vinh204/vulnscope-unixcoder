import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from metrics import binary_metrics


class BinaryMetricsTests(unittest.TestCase):
    def test_perfect_predictions(self):
        result = binary_metrics([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9])
        self.assertEqual(result["f1"], 1.0)
        self.assertEqual(result["confusion_matrix"], [[2, 0], [0, 2]])
        self.assertEqual(result["roc_auc"], 1.0)

    def test_single_class_does_not_crash(self):
        result = binary_metrics([0, 0], [0.1, 0.2])
        self.assertIsNone(result["roc_auc"])
        self.assertIsNone(result["pr_auc"])


if __name__ == "__main__":
    unittest.main()
