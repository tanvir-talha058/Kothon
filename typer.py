from __future__ import annotations

import ctypes


user32 = ctypes.windll.user32

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_uint),
        ("time", ctypes.c_uint),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [
        ("ki", KEYBDINPUT),
    ]


class INPUT(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = [
        ("type", ctypes.c_uint),
        ("data", _INPUTUNION),
    ]


class AutoTyper:
    def type_text(self, text: str) -> None:
        if not text:
            return

        try:
            for char in text:
                self._send_unicode_char(char)
        except Exception as exc:
            raise RuntimeError(f"Failed to type text automatically: {exc}") from exc

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
