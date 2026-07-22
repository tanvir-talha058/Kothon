"""Tests for settings.py — run with: python -m unittest discover tests -v"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import settings


class TestSettingsPersistence(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._path = Path(self._tmpdir.name) / "settings.json"
        self._patcher = patch.object(settings, "_PATH", self._path)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        self._tmpdir.cleanup()

    def test_load_missing_file_returns_empty_dict(self):
        self.assertEqual(settings.load(), {})

    def test_save_then_load_roundtrips(self):
        settings.save({"language": "bn"})
        self.assertEqual(settings.load(), {"language": "bn"})

    def test_partial_save_merges_keeps_unrelated_keys(self):
        # Regression: save() used to overwrite the whole file, wiping
        # unrelated keys on a partial save (e.g. just a language switch).
        settings.save({"language": "bn", "hotkey": "ctrl+shift+v"})
        settings.save({"language": "en"})
        self.assertEqual(settings.load(), {"language": "en", "hotkey": "ctrl+shift+v"})

    def test_save_creates_parent_directory(self):
        nested = self._path.parent / "nested"
        with patch.object(settings, "_PATH", nested / "settings.json"):
            settings.save({"a": 1})
            self.assertTrue((nested / "settings.json").exists())

    def test_save_no_tmp_file_left_behind(self):
        settings.save({"a": 1})
        self.assertFalse(self._path.with_suffix(".json.tmp").exists())

    def test_load_corrupt_json_returns_empty_dict(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text("{not valid json", encoding="utf-8")
        self.assertEqual(settings.load(), {})

    def test_save_never_raises_on_unwritable_path(self):
        with patch.object(settings, "_PATH", Path("Z:/does/not/exist/settings.json")):
            settings.save({"a": 1})  # should swallow the error, not raise


if __name__ == "__main__":
    unittest.main()
