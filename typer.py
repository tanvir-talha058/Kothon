from __future__ import annotations

import ctypes
import time

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_BACK = 0x08
VK_CONTROL = 0x11
VK_V = 0x56
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_uint),
        ("time", ctypes.c_uint),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_uint),
        ("dwFlags", ctypes.c_uint),
        ("time", ctypes.c_uint),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _INPUTUNION(ctypes.Union):
    # MOUSEINPUT must be present even though only ki is used: it is the largest
    # member, and without it sizeof(INPUT) is 32 instead of the 40 bytes
    # Windows expects — SendInput then rejects every event (invalid cbSize).
    _fields_ = [
        ("ki", KEYBDINPUT),
        ("mi", MOUSEINPUT),
    ]


class INPUT(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = [
        ("type", ctypes.c_uint),
        ("data", _INPUTUNION),
    ]


class AutoTyper:
    def __init__(self, char_delay: float = 0.0) -> None:
        # Seconds between characters. 0 = fastest; a few ms helps apps that
        # drop bursty synthetic input (games, RDP, some Electron apps).
        self.char_delay = float(char_delay)

    def type_text(self, text: str) -> None:
        if not text:
            return

        try:
            for char in text:
                self._send_unicode_char(char)
                if self.char_delay > 0:
                    time.sleep(self.char_delay)
        except Exception as exc:
            raise RuntimeError(f"Failed to type text automatically: {exc}") from exc

    def send_backspaces(self, count: int) -> None:
        """Erase the last `count` characters in the focused app (for undo)."""
        for _ in range(max(0, count)):
            self._send_vk(VK_BACK)
            if self.char_delay > 0:
                time.sleep(self.char_delay)

    def paste_text(self, text: str) -> None:
        """Put text on the clipboard and send Ctrl+V.

        Fast and burst-proof, but replaces the user's clipboard text —
        offered as an opt-in typing mode for apps that drop SendInput.
        """
        if not text:
            return
        self._set_clipboard(text)
        self._send_vk_combo(VK_CONTROL, VK_V)

    # ── internals ─────────────────────────────────────────────────

    def _set_clipboard(self, text: str) -> None:
        if not user32.OpenClipboard(None):
            raise OSError("Could not open the Windows clipboard.")
        try:
            user32.EmptyClipboard()
            data = text.encode("utf-16-le") + b"\x00\x00"
            handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
            locked = kernel32.GlobalLock(handle)
            ctypes.memmove(locked, data, len(data))
            kernel32.GlobalUnlock(handle)
            user32.SetClipboardData(CF_UNICODETEXT, handle)
        finally:
            user32.CloseClipboard()

    def _send_vk(self, vk: int) -> None:
        events = (
            INPUT(type=INPUT_KEYBOARD, data=_INPUTUNION(ki=KEYBDINPUT(
                wVk=vk, wScan=0, dwFlags=0, time=0, dwExtraInfo=None))),
            INPUT(type=INPUT_KEYBOARD, data=_INPUTUNION(ki=KEYBDINPUT(
                wVk=vk, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=None))),
        )
        arr = (INPUT * len(events))(*events)
        sent = user32.SendInput(len(arr), ctypes.byref(arr), ctypes.sizeof(INPUT))
        if sent != len(arr):
            raise OSError("Windows SendInput did not send all key events.")

    def _send_vk_combo(self, modifier: int, key: int) -> None:
        events = (
            INPUT(type=INPUT_KEYBOARD, data=_INPUTUNION(ki=KEYBDINPUT(
                wVk=modifier, wScan=0, dwFlags=0, time=0, dwExtraInfo=None))),
            INPUT(type=INPUT_KEYBOARD, data=_INPUTUNION(ki=KEYBDINPUT(
                wVk=key, wScan=0, dwFlags=0, time=0, dwExtraInfo=None))),
            INPUT(type=INPUT_KEYBOARD, data=_INPUTUNION(ki=KEYBDINPUT(
                wVk=key, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=None))),
            INPUT(type=INPUT_KEYBOARD, data=_INPUTUNION(ki=KEYBDINPUT(
                wVk=modifier, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=None))),
        )
        arr = (INPUT * len(events))(*events)
        sent = user32.SendInput(len(arr), ctypes.byref(arr), ctypes.sizeof(INPUT))
        if sent != len(arr):
            raise OSError("Windows SendInput did not send all key events.")

    def _send_unicode_char(self, char: str) -> None:
        code_point = ord(char)
        inputs = (
            INPUT(
                type=INPUT_KEYBOARD,
                data=_INPUTUNION(
                    ki=KEYBDINPUT(
                        wVk=0,
                        wScan=code_point,
                        dwFlags=KEYEVENTF_UNICODE,
                        time=0,
                        dwExtraInfo=None,
                    )
                ),
            ),
            INPUT(
                type=INPUT_KEYBOARD,
                data=_INPUTUNION(
                    ki=KEYBDINPUT(
                        wVk=0,
                        wScan=code_point,
                        dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP,
                        time=0,
                        dwExtraInfo=None,
                    )
                ),
            ),
        )
        input_array = (INPUT * len(inputs))(*inputs)
        sent = user32.SendInput(len(input_array), ctypes.byref(input_array), ctypes.sizeof(INPUT))
        if sent != len(input_array):
            raise OSError("Windows SendInput did not send all Unicode key events.")
