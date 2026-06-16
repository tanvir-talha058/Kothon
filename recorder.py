from __future__ import annotations

import array
import math
from queue import Queue
from typing import Any, Callable

import sounddevice as sd


def _rms(chunk: bytes) -> float:
    arr = array.array("h")
    try:
        arr.frombytes(chunk)
    except Exception:
        return 0.0
    n = len(arr)
    if n == 0:
        return 0.0
    return math.sqrt(sum(s * s for s in arr) / n) / 32768.0


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
        self.on_level: Callable[[float], None] | None = None
        self.on_error: Callable[[str], None] | None = None

    def _audio_callback(self, indata: Any, frames: int, time: Any, status: Any) -> None:
        if status and self.on_error:
            self.on_error(f"Mic status: {status}")
        chunk = bytes(indata)
        self.audio_queue.put(chunk)
        if self.on_level:
            self.on_level(_rms(chunk))

    def start(self) -> None:
        if self._is_recording and self._stream is not None:
            return
        try:
            self._stream = sd.RawInputStream(
                samplerate=self.samplerate,
                blocksize=self.blocksize,
                dtype=self.dtype,
                channels=self.channels,
                callback=self._audio_callback,
            )
            self._stream.start()
            self._is_recording = True
        except Exception as exc:
            if self.on_error:
                self.on_error(str(exc))
            raise

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
