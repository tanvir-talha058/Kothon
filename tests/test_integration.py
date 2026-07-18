"""End-to-end pipeline test: WAV audio → recognizer → normalizer → typed text.

Drives the real VoiceTyperApp worker loop (VAD, segmentation, cleanup) with the
Bengali model's bundled test recording. The AutoTyper is stubbed so nothing is
injected into the desktop. Skipped automatically if the Bangla model is absent.

Run: python -m unittest tests.test_integration -v
"""
import sys
import time
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main as kothon_main

BN_MODEL = Path("models/vosk-model-small-streaming-bn")
CHUNK_BYTES = 16000  # 0.5 s of 16 kHz int16 mono — same as the live recorder


class CapturingTyper:
    def __init__(self):
        self.typed: list[str] = []

    def type_text(self, text: str) -> None:
        self.typed.append(text)


@unittest.skipUnless(BN_MODEL.exists(), "Bangla model not installed")
class TestBanglaVoiceTyping(unittest.TestCase):
    def test_wav_is_typed_as_bangla(self):
        app = kothon_main.VoiceTyperApp(
            model_path=kothon_main.resolve_model_path("Bangla"), language="Bangla"
        )
        typer = CapturingTyper()
        app.typer = typer
        auto_stopped = []
        app.on_auto_stop = lambda: auto_stopped.append(True)

        raw = wave.open(str(BN_MODEL / "test.wav")).readframes(10**9)

        # Simulate the live mic: real audio then 3 s of silence for the VAD
        app.is_listening = True
        worker = __import__("threading").Thread(target=app._process_audio_loop, daemon=True)
        worker.start()
        for i in range(0, len(raw), CHUNK_BYTES):
            app.audio_queue.put(raw[i : i + CHUNK_BYTES])
        for _ in range(7):
            app.audio_queue.put(b"\x00" * CHUNK_BYTES)
        worker.join(timeout=30)

        self.assertFalse(worker.is_alive(), "worker loop did not finish")
        self.assertTrue(auto_stopped, "VAD auto-stop never fired")

        # Flush whatever the recognizer still holds, mirroring stop_listening
        app.is_listening = False
        final = app.recognizer.finalize_text()
        if final:
            typer.typed.append(final)

        output = " ".join(typer.typed)
        self.assertTrue(output.strip(), "nothing was typed")
        # Output must be Bangla script, not Latin
        bangla_chars = sum(1 for ch in output if "ঀ" <= ch <= "৿")
        self.assertGreater(bangla_chars, 20, f"expected Bangla script, got: {output!r}")
        # Known words from the test recording
        self.assertIn("টুইট", output)


@unittest.skipUnless(BN_MODEL.exists(), "Bangla model not installed")
class TestBanglaLatency(unittest.TestCase):
    def test_chunk_decode_is_realtime(self):
        rec = kothon_main.get_recognizer(kothon_main.resolve_model_path("Bangla"))
        raw = wave.open(str(BN_MODEL / "test.wav")).readframes(10**9)
        chunks = [raw[i : i + CHUNK_BYTES] for i in range(0, len(raw), CHUNK_BYTES)]
        start = time.perf_counter()
        for c in chunks:
            rec.accept_audio(c)
        rec.finalize_text()
        elapsed = time.perf_counter() - start
        audio_seconds = len(raw) / 2 / 16000
        # Each 0.5 s chunk must decode faster than it arrives (real-time factor < 1)
        self.assertLess(elapsed, audio_seconds, f"slower than real-time: {elapsed:.2f}s for {audio_seconds:.2f}s audio")


if __name__ == "__main__":
    unittest.main()
