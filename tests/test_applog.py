"""Tests for applog.py — run with: python -m unittest discover tests -v"""
import logging
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import applog


class TestSetup(unittest.TestCase):
    def tearDown(self):
        logger = logging.getLogger("kothon")
        for h in list(logger.handlers):
            logger.removeHandler(h)

    def test_skips_console_handler_when_stderr_is_none(self):
        # Regression: the packaged app is windowed (console=False in
        # kothon.spec), so sys.stderr is None there. setup() used to add a
        # StreamHandler anyway, which silently failed on every log call.
        with patch.object(sys, "stdout", None), patch.object(sys, "stderr", None):
            logger = applog.setup()
        self.assertFalse(
            any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
                for h in logger.handlers)
        )

    def test_adds_console_handler_when_stderr_present(self):
        logger = applog.setup()
        self.assertTrue(
            any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
                for h in logger.handlers)
        )

    def test_setup_is_idempotent(self):
        first = applog.setup()
        second = applog.setup()
        self.assertIs(first, second)
        self.assertEqual(len(first.handlers), len(second.handlers))


if __name__ == "__main__":
    unittest.main()
