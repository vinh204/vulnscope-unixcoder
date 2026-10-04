import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from data_utils import load_records


class DataUtilsTests(unittest.TestCase):
    def test_json_array(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.json"
            path.write_text(json.dumps([{"idx": 1}]), encoding="utf-8")
            self.assertEqual(load_records(path), [{"idx": 1}])

    def test_json_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.jsonl"
            path.write_text('{"idx": 1}\n{"idx": 2}\n', encoding="utf-8")
            self.assertEqual(load_records(path), [{"idx": 1}, {"idx": 2}])


if __name__ == "__main__":
    unittest.main()
