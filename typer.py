from __future__ import annotations

import pyautogui


class AutoTyper:
    def __init__(self, interval: float = 0.02) -> None:
        self.interval = interval

    def type_text(self, text: str) -> None:
        if not text:
            return

        try:
            pyautogui.write(text, interval=self.interval)
        except Exception as exc:
            raise RuntimeError(f"Failed to type text automatically: {exc}") from exc