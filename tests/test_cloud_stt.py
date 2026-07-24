import unittest
import wave

import providers
from stt import CloudRecognizer


class CloudRecognizerTests(unittest.TestCase):
    def setUp(self):
        self._orig = providers.transcribe
        self.transcribe_calls = []

        def fake(provider, api_key, model, wav_bytes, language=""):
            self.transcribe_calls.append((provider, api_key, model, wav_bytes))
            return "  transcribed text  "
        providers.transcribe = fake

    def tearDown(self):
        providers.transcribe = self._orig

    def test_accept_audio_buffers_and_returns_empty(self):
        rec = CloudRecognizer("openai", "gpt-4o-transcribe", "sk-x", samplerate=16000)
        self.assertEqual(rec.accept_audio(b"\x00\x01" * 100), "")
        self.assertEqual(rec.get_partial_text(), "")
        self.assertEqual(len(rec._buffer), 200)

    def test_finalize_builds_valid_wav_and_calls_provider(self):
        rec = CloudRecognizer("openai", "m", "sk-x", samplerate=16000)
        pcm = b"\x10\x20" * 8000  # 1s of int16 mono
        rec.accept_audio(pcm)
        text = rec.finalize_text()
        self.assertEqual(text, "transcribed text")  # stripped
        self.assertEqual(len(self.transcribe_calls), 1)
        provider, key, model, wav_bytes = self.transcribe_calls[0]
        self.assertEqual(provider, "openai")
        self.assertEqual(key, "sk-x")
        # The blob handed to the provider is a real 16 kHz mono WAV
        self.assertTrue(wav_bytes.startswith(b"RIFF"))
        import io
        with wave.open(io.BytesIO(wav_bytes), "rb") as w:
            self.assertEqual(w.getframerate(), 16000)
            self.assertEqual(w.getnchannels(), 1)
            self.assertEqual(w.getsampwidth(), 2)

    def test_finalize_empty_buffer_returns_empty(self):
        rec = CloudRecognizer("openai", "m", "sk-x")
        self.assertEqual(rec.finalize_text(), "")
        self.assertEqual(self.transcribe_calls, [])

    def test_reset_clears_buffer(self):
        rec = CloudRecognizer("openai", "m", "sk-x")
        rec.accept_audio(b"\x00" * 50)
        rec.reset()
        self.assertEqual(len(rec._buffer), 0)

    def test_buffer_is_capped(self):
        rec = CloudRecognizer("openai", "m", "sk-x", samplerate=16000)
        rec._max_bytes = 100  # shrink for the test
        rec.accept_audio(b"\x00" * 500)
        self.assertLessEqual(len(rec._buffer), 500)  # first chunk fits, rest dropped

    def test_provider_failure_surfaces_error_and_returns_empty(self):
        errors = []
        rec = CloudRecognizer("openai", "m", "sk-x", on_error=errors.append)

        def boom(*a, **k):
            raise providers.ProviderError("HTTP 401 — check your API key")
        providers.transcribe = boom
        rec.accept_audio(b"\x00\x01" * 100)
        self.assertEqual(rec.finalize_text(), "")
        self.assertIsNotNone(rec.last_error)
        self.assertEqual(len(errors), 1)


if __name__ == "__main__":
    unittest.main()
