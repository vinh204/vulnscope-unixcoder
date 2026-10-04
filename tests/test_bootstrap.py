import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from bootstrap import ensure_checkpoint


class BootstrapTests(unittest.TestCase):
    def test_existing_checkpoint_is_used(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "model.bin"
            checkpoint.write_bytes(b"checkpoint")
            with patch.dict(os.environ, {"CHECKPOINT_PATH": str(checkpoint)}, clear=True):
                self.assertEqual(ensure_checkpoint(), checkpoint)

    def test_missing_configuration_fails_clearly(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "missing.bin"
            with patch.dict(os.environ, {"CHECKPOINT_PATH": str(checkpoint)}, clear=True):
                with self.assertRaisesRegex(RuntimeError, "CHECKPOINT_REPO_ID"):
                    ensure_checkpoint()


if __name__ == "__main__":
    unittest.main()
