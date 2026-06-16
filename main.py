import json
import math
import queue
import threading
import time
from pathlib import Path
from typing import Any

import webview

import settings as _settings
from banglish_fix import normalize_text
from recorder import AudioRecorder, _rms
from stt import OfflineSpeechRecognizer
from typer import AutoTyper

try:
    import keyboard as _keyboard
    _HAS_KEYBOARD = True
except ImportError:
    _HAS_KEYBOARD = False

try:
    import pystray
    from PIL import Image, ImageDraw
    _HAS_TRAY = True
except ImportError:
    _HAS_TRAY = False


MODELS_DIR = Path("models")
LANGUAGE_OPTIONS = ("Bangla", "English", "Banglish")
RECOGNIZER_CACHE: dict[Path, OfflineSpeechRecognizer] = {}
LANGUAGE_HINTS = {
    "Bangla": "Best with a Bangla-capable Vosk model. Falls back to the best available local model.",
    "English": "Optimized for English dictation with the current local model.",
    "Banglish": "Works with mixed Bangla-English speech and also normalizes common Banglish words.",
}

# Auto-stop: stop after this many consecutive silent chunks (each chunk ≈ 0.5 s)
_SILENCE_RMS_THRESHOLD = 0.008
_SILENCE_CHUNKS_TO_STOP = 5   # 2.5 s of silence
_MIN_SPEECH_CHUNKS = 2         # need ≥ 1 s of speech before silence kicks in


# ── Model helpers ─────────────────────────────────────────────────────────────

def _find_matching_model(*keywords: str) -> Path | None:
    if not MODELS_DIR.exists():
        return None
    matches = []
    for path in MODELS_DIR.iterdir():
        if not path.is_dir():
            continue
        name = path.name.lower()
        if all(keyword in name for keyword in keywords):
            matches.append(path)
    return sorted(matches)[0] if matches else None


def resolve_model_path(language: str) -> Path:
    preferred_map: dict[str, tuple[tuple[str, ...], ...]] = {
        "Bangla":   (("bangla",), ("bn",), ("vosk-model-small",)),
        "English":  (("english",), ("en",), ("vosk-model-small-en",), ("vosk-model-small",)),
        "Banglish": (("banglish",), ("multilingual",), ("bangla", "english"), ("vosk-model-small",)),
    }
    for keywords in preferred_map.get(language, ()):
        match = _find_matching_model(*keywords)
        if match is not None:
            return match
    if MODELS_DIR.exists():
        candidate_dirs = sorted(p for p in MODELS_DIR.iterdir() if p.is_dir())
        if candidate_dirs:
            return candidate_dirs[0]
    raise FileNotFoundError(
        "No Vosk model found in the 'models' directory. "
        "Add a model folder such as 'models/vosk-model-small' and run again."
    )


def has_dedicated_model(language: str) -> bool:
    checks: dict[str, tuple[tuple[str, ...], ...]] = {
        "Bangla":   (("bangla",), ("bn",)),
        "English":  (("english",), ("en",), ("vosk-model-small-en",)),
        "Banglish": (("banglish",), ("multilingual",), ("bangla", "english")),
    }
    return any(
        _find_matching_model(*kw) is not None
        for kw in checks.get(language, ())
    )


def get_recognizer(model_path: Path) -> OfflineSpeechRecognizer:
    resolved = model_path.resolve()
    if resolved not in RECOGNIZER_CACHE:
        RECOGNIZER_CACHE[resolved] = OfflineSpeechRecognizer(model_path=resolved)
    return RECOGNIZER_CACHE[resolved]


# ── Core app ──────────────────────────────────────────────────────────────────

class VoiceTyperApp:
    def __init__(self, model_path: Path, language: str) -> None:
        self.audio_queue: queue.Queue[bytes] = queue.Queue()
        self.recorder = AudioRecorder(self.audio_queue)
        self.typer = AutoTyper()
        self.is_listening = False
        self.worker_thread: threading.Thread | None = None
        self.language = language
        self.model_path = model_path
        self.recognizer = get_recognizer(model_path)
        # Callbacks wired by Api
        self.on_partial = None
        self.on_typed = None
        self.on_error = None
        self.on_auto_stop = None
        self.on_level = None
        # VAD counters
        self._speech_chunks = 0
        self._silence_chunks = 0

    def set_language(self, language: str) -> None:
        if self.is_listening:
            raise RuntimeError("Stop listening before switching language.")
        self.language = language
        self.model_path = resolve_model_path(language)
        self.recognizer = get_recognizer(self.model_path)
        self._flush_queue()

    def start_listening(self) -> None:
        if self.is_listening:
            return
        self._speech_chunks = 0
        self._silence_chunks = 0
        self.is_listening = True
        self.recorder.on_level = self.on_level
        self.recorder.on_error = self._on_recorder_error
        self.recorder.start()
        self.worker_thread = threading.Thread(
            target=self._process_audio_loop, daemon=True
        )
        self.worker_thread.start()

    def stop_listening(self) -> str:
        if not self.is_listening:
            return ""
        self.is_listening = False
        self.recorder.on_level = None
        self.recorder.stop()
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=1.0)
        try:
            final_text = self.recognizer.finalize_text()
        except Exception:
            final_text = ""
        if self.language in {"Bangla", "Banglish"}:
            final_text = normalize_text(final_text)
        cleaned = self._cleanup_text(final_text)
        if cleaned:
            print(f"Typed ({self.language}): {cleaned}")
            self.typer.type_text(cleaned + " ")
        self._flush_queue()
        return cleaned

    def _on_recorder_error(self, message: str) -> None:
        print(f"Recorder error: {message}")
        if self.on_error:
            self.on_error(message)

    def _flush_queue(self) -> None:
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break

    def _process_audio_loop(self) -> None:
        while self.is_listening:
            try:
                chunk = self.audio_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                # VAD — silence detection
                level = _rms(chunk)
                if level >= _SILENCE_RMS_THRESHOLD:
                    self._speech_chunks += 1
                    self._silence_chunks = 0
                elif self._speech_chunks >= _MIN_SPEECH_CHUNKS:
                    self._silence_chunks += 1
                    if self._silence_chunks >= _SILENCE_CHUNKS_TO_STOP:
                        if self.on_auto_stop:
                            self.on_auto_stop()
                        break

                # Speech recognition
                text = self.recognizer.accept_audio(chunk)
                if text:
                    if self.language in {"Bangla", "Banglish"}:
                        text = normalize_text(text)
                    cleaned = self._cleanup_text(text)
                    if cleaned:
                        print(f"Typed ({self.language}): {cleaned}")
                        if self.on_typed:
                            self.on_typed(cleaned)
                        self.typer.type_text(cleaned + " ")
                else:
                    partial = self.recognizer.get_partial_text()
                    if partial and self.on_partial:
                        if self.language in {"Bangla", "Banglish"}:
                            partial = normalize_text(partial, is_partial=True)
                        self.on_partial(partial)

            except Exception as exc:
                print(f"Audio loop error: {exc}")
                if self.on_error:
                    self.on_error(str(exc))

    def _cleanup_text(self, text: str) -> str:
        cleaned = " ".join(text.split()).strip()
        if not cleaned:
            return ""
        if self.language in {"Bangla", "Banglish"}:
            return cleaned
        if cleaned.lower() == "i":
            return "I"
        return cleaned[0].upper() + cleaned[1:] if len(cleaned) > 1 else cleaned.upper()


# ── Tray icon ─────────────────────────────────────────────────────────────────

def _make_tray_image() -> "Image.Image":
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([2, 2, 62, 62], fill=(124, 58, 237, 255))
    draw.rounded_rectangle([22, 10, 42, 36], radius=9, fill=(255, 255, 255, 220))
    draw.rectangle([29, 36, 35, 47], fill=(255, 255, 255, 220))
    draw.arc([18, 30, 46, 52], start=0, end=180, fill=(255, 255, 255, 220), width=3)
    draw.rectangle([29, 50, 35, 54], fill=(255, 255, 255, 220))
    return img


# ── pywebview API ─────────────────────────────────────────────────────────────

class Api:
    def __init__(self, app: VoiceTyperApp) -> None:
        self._app = app
        self._window: webview.Window | None = None
        self._tray: Any = None
        self._last_level_t: float = 0.0

    def set_window(self, window: webview.Window) -> None:
        self._window = window
        self._app.on_partial = self._push_partial
        self._app.on_typed = self._push_typed
        self._app.on_error = self._push_error
        self._app.on_auto_stop = self._handle_auto_stop
        self._app.on_level = self._push_level

    # ── JS-callable methods ───────────────────────────────────────

    def get_state(self) -> dict:
        return {
            "language": self._app.language,
            "model": self._app.model_path.name,
            "is_listening": self._app.is_listening,
            "languages": list(LANGUAGE_OPTIONS),
            "hints": LANGUAGE_HINTS,
            "dedicated": {lang: has_dedicated_model(lang) for lang in LANGUAGE_OPTIONS},
        }

    def start_listening(self) -> dict:
        try:
            self._app.start_listening()
            self._set_tray_title("Kothon — Listening")
            return {"success": True}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def stop_listening(self) -> dict:
        try:
            text = self._app.stop_listening()
            self._set_tray_title("Kothon")
            return {"success": True, "text": text}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def set_language(self, language: str) -> dict:
        try:
            self._app.set_language(language)
            _settings.save({"language": language, **self._window_pos()})
            return {"success": True, "model": self._app.model_path.name}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def minimize_window(self) -> None:
        if self._window:
            self._window.hide()

    def close_app(self) -> None:
        _settings.save({"language": self._app.language, **self._window_pos()})
        try:
            self._app.stop_listening()
        finally:
            if self._tray:
                try:
                    self._tray.stop()
                except Exception:
                    pass
            if self._window:
                self._window.destroy()

    # ── Python→JS pushes ─────────────────────────────────────────

    def _push_partial(self, text: str) -> None:
        self._js(f"onPartial({json.dumps(text)})")

    def _push_typed(self, text: str) -> None:
        self._js(f"onTyped({json.dumps(text)})")

    def _push_error(self, message: str) -> None:
        self._js(f"onError({json.dumps(message)})")

    def _push_level(self, rms: float) -> None:
        now = time.monotonic()
        if now - self._last_level_t < 0.09:   # ~11 fps cap
            return
        self._last_level_t = now
        self._js(f"onLevel({rms:.4f})")

    def _handle_auto_stop(self) -> None:
        threading.Thread(target=self._do_auto_stop, daemon=True).start()

    def _do_auto_stop(self) -> None:
        result = self.stop_listening()
        self._js(f"onAutoStop({json.dumps(result)})")

    def _js(self, code: str) -> None:
        if self._window:
            try:
                self._window.evaluate_js(code)
            except Exception:
                pass

    # ── Helpers ───────────────────────────────────────────────────

    def _window_pos(self) -> dict:
        try:
            if self._window:
                return {"window_x": self._window.x, "window_y": self._window.y}
        except Exception:
            pass
        return {}

    def _set_tray_title(self, title: str) -> None:
        if self._tray:
            try:
                self._tray.title = title
            except Exception:
                pass

    # ── System tray ───────────────────────────────────────────────

    def setup_tray(self) -> None:
        if not _HAS_TRAY:
            return
        img = _make_tray_image()

        def on_show(icon, item):
            if self._window:
                self._window.show()

        def on_toggle(icon, item):
            self._js("toggleListen()")

        def on_quit(icon, item):
            self.close_app()

        menu = pystray.Menu(
            pystray.MenuItem("Show Kothon", on_show, default=True),
            pystray.MenuItem("Start / Stop  (Ctrl+Shift+V)", on_toggle),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", on_quit),
        )
        self._tray = pystray.Icon("Kothon", img, "Kothon", menu)
        self._tray.run_detached()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    saved = _settings.load()
    default_language = saved.get("language", "Banglish")
    win_x = saved.get("window_x")
    win_y = saved.get("window_y")

    model_path = resolve_model_path(default_language)
    app = VoiceTyperApp(model_path=model_path, language=default_language)
    api = Api(app)

    ui_path = Path(__file__).parent / "ui" / "index.html"

    create_kwargs: dict = dict(
        title="Kothon",
        url=ui_path.as_uri(),
        js_api=api,
        width=380,
        height=600,
        resizable=False,
        frameless=True,
        on_top=True,
        background_color="#0a0a0f",
        easy_drag=False,
    )
    if win_x is not None:
        create_kwargs["x"] = int(win_x)
    if win_y is not None:
        create_kwargs["y"] = int(win_y)

    window = webview.create_window(**create_kwargs)
    api.set_window(window)
    api.setup_tray()

    if _HAS_KEYBOARD:
        try:
            _keyboard.add_hotkey(
                "ctrl+shift+v",
                lambda: api._js("toggleListen()"),
                suppress=False,
            )
            print("Hotkey Ctrl+Shift+V registered.")
        except Exception as exc:
            print(f"Hotkey registration failed: {exc}")

    webview.start()


if __name__ == "__main__":
    main()
