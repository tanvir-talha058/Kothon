"""Tests for AudioRecorder.start() failure handling — run with: python -m pytest tests/"""
import sys
import unittest
from pathlib import Path
from queue import Queue
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from recorder import AudioRecorder


class TestStartFailureCleanup(unittest.TestCase):
    def setUp(self):
        self.rec = AudioRecorder(Queue())

    def test_stream_closed_when_start_raises(self):
        # Regression: the stream was constructed and assigned, then .start()
        # raised — leaving an open stream that stop() would never close
        # because _is_recording was still False.
        fake_stream = MagicMock()
        fake_stream.start.side_effect = OSError("device busy")

        with patch("recorder.sd.RawInputStream", return_value=fake_stream):
            with self.assertRaises(OSError):
                self.rec.start()

        fake_stream.close.assert_called_once()
        self.assertIsNone(self.rec._stream)
        self.assertFalse(self.rec._is_recording)

    def test_on_error_still_called_when_start_raises(self):
        errors = []
        self.rec.on_error = errors.append
        fake_stream = MagicMock()
        fake_stream.start.side_effect = OSError("device busy")

        with patch("recorder.sd.RawInputStream", return_value=fake_stream):
            with self.assertRaises(OSError):
                self.rec.start()

        self.assertEqual(errors, ["device busy"])

    def test_constructor_failure_leaves_no_stream(self):
        with patch("recorder.sd.RawInputStream", side_effect=OSError("no device")):
            with self.assertRaises(OSError):
                self.rec.start()
        self.assertIsNone(self.rec._stream)
        self.assertFalse(self.rec._is_recording)

    def test_retry_after_failure_succeeds(self):
        failing = MagicMock()
        failing.start.side_effect = OSError("device busy")
        working = MagicMock()

        with patch("recorder.sd.RawInputStream", side_effect=[failing, working]):
            with self.assertRaises(OSError):
                self.rec.start()
            self.rec.start()

        self.assertIs(self.rec._stream, working)
        self.assertTrue(self.rec._is_recording)


if __name__ == "__main__":
    unittest.main()
