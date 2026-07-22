from __future__ import annotations

import array
import math
from collections.abc import Callable
from queue import Queue
from typing import Any

import sounddevice as sd

try:
    import numpy as _np
except ImportError:      # numpy ships with the app, but stay runnable without it
    _np = None


def _rms(chunk: bytes) -> float:
    if len(chunk) < 2 or len(chunk) % 2:
        return 0.0
    if _np is not None:
        samples = _np.frombuffer(chunk, dtype=_np.int16)
        return float(_np.sqrt(_np.mean(samples.astype(_np.float64) ** 2)) / 32768.0)
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
        device: int | None = None,
    ) -> None:
        self.audio_queue = audio_queue
        self.samplerate = samplerate
        self.channels = channels
        self.dtype = dtype
        self.blocksize = blocksize
        self.device = device          # None = system default input
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
                device=self.device,
                callback=self._audio_callback,
            )
            self._stream.start()
            self._is_recording = True
        except Exception as exc:
            # The stream may have been constructed but failed to start; close it
            # here or it stays open forever (stop() bails out on _is_recording).
            if self._stream is not None:
                try:
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None
            self._is_recording = False
            if self.on_error:
                self.on_error(str(exc))
            raise

    @staticmethod
    def list_input_devices() -> list[dict]:
        """Input devices for the settings picker: [{"id", "name", "default"}]."""
        devices = []
        try:
            default_in = sd.default.device[0]
            for idx, info in enumerate(sd.query_devices()):
                if info.get("max_input_channels", 0) > 0:
                    devices.append({
                        "id": idx,
                        "name": info.get("name", f"Device {idx}"),
                        "default": idx == default_in,
                    })
        except Exception:
            pass
        return devices

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
