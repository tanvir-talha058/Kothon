from __future__ import annotations

import json
import threading
from pathlib import Path

from vosk import KaldiRecognizer, Model


def is_sherpa_model(model_path: Path | str) -> bool:
    """A sherpa-onnx transducer model ships ONNX files under am-onnx/."""
    return (Path(model_path) / "am-onnx" / "encoder.onnx").exists()


def create_recognizer(model_path: Path | str, samplerate: int = 16000):
    """Pick the right engine for the model folder layout."""
    if is_sherpa_model(model_path):
        return SherpaRecognizer(model_path, samplerate=samplerate)
    return OfflineSpeechRecognizer(model_path, samplerate=samplerate)


class OfflineSpeechRecognizer:
    def __init__(self, model_path: str = "models/vosk-model-small", samplerate: int = 16000) -> None:
        self.model_path = Path(model_path)
        self.samplerate = samplerate

        if not self.model_path.exists() or not self.model_path.is_dir():
            raise FileNotFoundError(
                f"Vosk model not found at '{self.model_path}'. "
                "Download a compatible model and place it inside the project's 'models' directory."
            )

        self.model = Model(str(self.model_path))
        self.recognizer = KaldiRecognizer(self.model, float(self.samplerate))
        # KaldiRecognizer is not thread-safe; the audio worker thread and the
        # stop/finalize path may run concurrently if the worker join times out.
        self._lock = threading.Lock()

    def _create_recognizer(self) -> KaldiRecognizer:
        return KaldiRecognizer(self.model, float(self.samplerate))

    def reset(self) -> None:
        with self._lock:
            self.recognizer = self._create_recognizer()

    def accept_audio(self, audio_chunk: bytes) -> str:
        if not audio_chunk:
            return ""

        with self._lock:
            if self.recognizer.AcceptWaveform(audio_chunk):
                result = json.loads(self.recognizer.Result())
                return str(result.get("text", "")).strip()

        return ""

    def get_partial_text(self) -> str:
        with self._lock:
            result = json.loads(self.recognizer.PartialResult())
        return str(result.get("partial", "")).strip()

    def finalize_text(self) -> str:
        with self._lock:
            result = json.loads(self.recognizer.FinalResult())
            text = str(result.get("text", "")).strip()
            self.recognizer = self._create_recognizer()
        return text


class SherpaRecognizer:
    """Streaming transducer engine (sherpa-onnx) — used for the Bengali model.

    Same contract as OfflineSpeechRecognizer: accept_audio returns finalized
    segment text when the engine detects an endpoint, get_partial_text returns
    the in-progress hypothesis, finalize_text flushes and resets.
    """

    def __init__(self, model_path: Path | str, samplerate: int = 16000) -> None:
        import numpy as np
        import sherpa_onnx

        self._np = np
        self.model_path = Path(model_path)
        self.samplerate = samplerate

        required = [
            self.model_path / "am-onnx" / "encoder.onnx",
            self.model_path / "am-onnx" / "decoder.onnx",
            self.model_path / "am-onnx" / "joiner.onnx",
            self.model_path / "lang" / "tokens.txt",
        ]
        missing = [str(p) for p in required if not p.exists()]
        if missing:
            raise FileNotFoundError(
                f"Incomplete sherpa-onnx model at '{self.model_path}': missing {missing}"
            )

        self.recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=str(required[3]),
            encoder=str(required[0]),
            decoder=str(required[1]),
            joiner=str(required[2]),
            num_threads=2,
            sample_rate=samplerate,
            feature_dim=80,
            enable_endpoint_detection=True,
            rule1_min_trailing_silence=2.4,
            rule2_min_trailing_silence=1.2,
            rule3_min_utterance_length=20.0,
        )
        self.stream = self.recognizer.create_stream()
        self._lock = threading.Lock()

    def _to_float(self, audio_chunk: bytes):
        return (
            self._np.frombuffer(audio_chunk, dtype=self._np.int16)
            .astype(self._np.float32)
            / 32768.0
        )

    def _decode(self) -> None:
        while self.recognizer.is_ready(self.stream):
            self.recognizer.decode_stream(self.stream)

    def reset(self) -> None:
        with self._lock:
            self.stream = self.recognizer.create_stream()

    def accept_audio(self, audio_chunk: bytes) -> str:
        if not audio_chunk:
            return ""
        with self._lock:
            self.stream.accept_waveform(self.samplerate, self._to_float(audio_chunk))
            self._decode()
            if self.recognizer.is_endpoint(self.stream):
                text = self.recognizer.get_result(self.stream).strip()
                self.recognizer.reset(self.stream)
                return text
        return ""

    def get_partial_text(self) -> str:
        with self._lock:
            return self.recognizer.get_result(self.stream).strip()

    def finalize_text(self) -> str:
        with self._lock:
            # Tail padding so the last words are decoded before flushing
            padding = self._np.zeros(int(self.samplerate * 0.6), dtype=self._np.float32)
            self.stream.accept_waveform(self.samplerate, padding)
            self.stream.input_finished()
            self._decode()
            text = self.recognizer.get_result(self.stream).strip()
            self.stream = self.recognizer.create_stream()
        return text


class CloudRecognizer:
    """Speech-to-text via a cloud provider (OpenAI / Gemini).

    Cloud STT is not streaming: ``accept_audio`` buffers the utterance and
    returns "" (no live partials), then ``finalize_text`` uploads the buffered
    audio as a WAV and returns the transcript. It honours the same recognizer
    contract as the offline engines so it drops into the audio worker loop
    unchanged — text is emitted only through the stop/finalize path.

    On any provider failure it returns "" and records ``last_error`` (surfaced
    via ``on_error``); the offline engines remain available.
    """

    _MAX_SECONDS = 60  # cap the buffer so a stuck mic can't build a huge upload

    def __init__(self, provider: str, model: str, api_key: str,
                 samplerate: int = 16000, on_error=None) -> None:
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.samplerate = samplerate
        self.on_error = on_error
        self.last_error: str | None = None
        self._max_bytes = self._MAX_SECONDS * samplerate * 2  # int16 mono
        self._buffer = bytearray()
        self._lock = threading.Lock()

    def reset(self) -> None:
        with self._lock:
            self._buffer = bytearray()

    def accept_audio(self, audio_chunk: bytes) -> str:
        if not audio_chunk:
            return ""
        with self._lock:
            if len(self._buffer) < self._max_bytes:
                self._buffer.extend(audio_chunk)
        return ""  # cloud STT has no mid-stream endpoints

    def get_partial_text(self) -> str:
        return ""  # no live partials for cloud STT

    def _build_wav(self, pcm: bytes) -> bytes:
        import io
        import wave

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)  # int16
            wav.setframerate(self.samplerate)
            wav.writeframes(pcm)
        return buf.getvalue()

    def finalize_text(self) -> str:
        import providers

        with self._lock:
            pcm = bytes(self._buffer)
            self._buffer = bytearray()
        if not pcm:
            return ""
        self.last_error = None
        try:
            wav_bytes = self._build_wav(pcm)
            return providers.transcribe(self.provider, self.api_key, self.model, wav_bytes).strip()
        except Exception as exc:
            self.last_error = str(exc)
            if self.on_error:
                self.on_error(f"Cloud transcription failed: {exc}")
            return ""
