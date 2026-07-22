"""Tests for download_model.py — run with: python -m unittest discover tests -v"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import download_model


class TestMainArgHandling(unittest.TestCase):
    def test_no_args_exits_2(self):
        with patch.object(sys, "argv", ["download_model.py"]):
            with self.assertRaises(SystemExit) as cm:
                download_model.main()
            self.assertEqual(cm.exception.code, 2)

    def test_unknown_lang_exits_2(self):
        with patch.object(sys, "argv", ["download_model.py", "fr"]):
            with self.assertRaises(SystemExit) as cm:
                download_model.main()
            self.assertEqual(cm.exception.code, 2)

    def test_lang_is_case_insensitive(self):
        with patch.object(sys, "argv", ["download_model.py", "EN"]):
            with patch.object(download_model, "download_en") as mock_en:
                download_model.main()
            mock_en.assert_called_once()

    def test_bn_dispatches_to_download_bn(self):
        with patch.object(sys, "argv", ["download_model.py", "bn"]):
            with patch.object(download_model, "download_bn") as mock_bn:
                download_model.main()
            mock_bn.assert_called_once()

    def test_download_failure_exits_1_without_raising(self):
        with patch.object(sys, "argv", ["download_model.py", "en"]):
            with patch.object(download_model, "download_en", side_effect=OSError("no network")):
                with self.assertRaises(SystemExit) as cm:
                    download_model.main()
                self.assertEqual(cm.exception.code, 1)


class TestDownloadSkipsWhenPresent(unittest.TestCase):
    def test_download_en_skips_when_model_dir_exists(self):
        with patch.object(download_model, "MODELS_DIR") as mock_dir:
            mock_dir.__truediv__.return_value.exists.return_value = True
            with patch.object(download_model, "_download") as mock_download:
                download_model.download_en()
            mock_download.assert_not_called()

    def test_download_bn_skips_when_encoder_exists(self):
        with patch.object(download_model, "MODELS_DIR") as mock_dir:
            mock_dir.__truediv__.return_value.__truediv__.return_value.__truediv__.return_value.exists.return_value = True
            with patch.object(download_model, "_download") as mock_download:
                download_model.download_bn()
            mock_download.assert_not_called()


class TestBnFileList(unittest.TestCase):
    def test_bn_files_cover_encoder_decoder_joiner_and_lang(self):
        joined = " ".join(download_model.BN_FILES)
        for expected in ("encoder.onnx", "decoder.onnx", "joiner.onnx", "tokens.txt", "bpe.model"):
            self.assertIn(expected, joined)


if __name__ == "__main__":
    unittest.main()
