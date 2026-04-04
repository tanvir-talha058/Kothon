from __future__ import annotations

from queue import Queue
from typing import Any

import sounddevice as sd


class AudioRecorder:
    def __init__(
        self,
        audio_queue: Queue[bytes],
        samplerate: int = 16000,
        channels: int = 1,
        dtype: str = "int16",
        blocksize: int = 8000,
    ) -> None:
        self.audio_queue = audio_queue
        self.samplerate = samplerate
        self.channels = channels
        self.dtype = dtype
        self.blocksize = blocksize
        self._stream: sd.RawInputStream | None = None
        self._is_recording = False

    def _audio_callback(self, indata: Any, frames: int, time: Any, status: Any) -> None:
        if status:
            print(f"Audio input status: {status}")

        self.audio_queue.put(bytes(indata))

    def start(self) -> None:
        if self._is_recording and self._stream is not None:
            return

        self._stream = sd.RawInputStream(
            samplerate=self.samplerate,
            blocksize=self.blocksize,
            dtype=self.dtype,
            channels=self.channels,
            callback=self._audio_callback,
        )
        self._stream.start()
        self._is_recording = True

    def stop(self) -> None:
        if not self._is_recording:
            return

        if self._stream is not None:
            try:
                self._stream.stop()
            finally:
                self._stream.close()
                self._stream = None

        self._is_recording = False