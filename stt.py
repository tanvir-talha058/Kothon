from __future__ import annotations

import json
from pathlib import Path

from vosk import KaldiRecognizer, Model


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

    def _create_recognizer(self) -> KaldiRecognizer:
        return KaldiRecognizer(self.model, float(self.samplerate))

    def reset(self) -> None:
        self.recognizer = self._create_recognizer()

    def accept_audio(self, audio_chunk: bytes) -> str:
        if not audio_chunk:
            return ""

        if self.recognizer.AcceptWaveform(audio_chunk):
            result = json.loads(self.recognizer.Result())
            return str(result.get("text", "")).strip()

        return ""

    def get_partial_text(self) -> str:
        result = json.loads(self.recognizer.PartialResult())
        return str(result.get("partial", "")).strip()

    def finalize_text(self) -> str:
        result = json.loads(self.recognizer.FinalResult())
        text = str(result.get("text", "")).strip()
        self.reset()
        return text
