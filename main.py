import ctypes
import ctypes.wintypes
import json
import logging
import os
import queue
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any

import webview

import applog
import providers
import secrets_store
import settings as _settings
from banglish_fix import apply_punctuation, normalize_text
from recorder import AudioRecorder, _rms
from stt import CloudRecognizer, create_recognizer
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


__version__ = "0.2.0"

_LOG = logging.getLogger("kothon.app")

# Frozen (PyInstaller): models live next to the exe, bundled assets in _MEIPASS
_IS_FROZEN = getattr(sys, "frozen", False)
_APP_DIR = Path(sys.executable).parent if _IS_FROZEN else Path(__file__).parent
_ASSETS_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))

MODELS_DIR = _APP_DIR / "models"
FULL_SIZE = (380, 600)
COMPACT_SIZE = (322, 64)
LANGUAGE_OPTIONS = ("Bangla", "English", "Banglish")
RECOGNIZER_CACHE: dict[Path, Any] = {}
LANGUAGE_HINTS = {
    "Bangla": "Best with a Bangla-capable Vosk model. Falls back to the best available local model.",
    "English": "Optimized for English dictation with the current local model.",
    "Banglish": "Works with mixed Bangla-English speech and also normalizes common Banglish words.",
}

# Auto-stop defaults (each audio chunk ≈ 0.5 s); user-tunable in Settings
_CHUNK_SECONDS = 0.5
_MIN_SPEECH_CHUNKS = 2         # need ≥ 1 s of speech before silence kicks in

DEFAULT_CONFIG: dict[str, Any] = {
    "silence_seconds": 2.5,        # pause length that auto-stops dictation
    "vad_threshold": 0.008,        # RMS below this counts as silence
    "auto_stop": True,             # stop by itself after silence
    "mic_device": None,            # sounddevice index; None = system default
    "typing_mode": "type",         # "type" (SendInput) | "paste" (clipboard+Ctrl+V)
    "char_delay_ms": 0,            # pacing for apps that drop bursty input
    "trailing_space": True,        # append a space after each typed segment
    "auto_capitalize": True,       # capitalize English sentences
    "punctuation_commands": True,  # spoken "comma"/"দাঁড়ি" become symbols
    "aggressive_banglish": False,  # transliterate unknown roman words too
    "push_to_talk": False,         # hold the hotkey to talk, release to stop
    "sounds": False,               # start/stop chirps
    "always_on_top": True,         # keep the window above other apps
    "minimize_to": "mini",         # minimize button: "mini" bar | "tray"
    # ── Optional cloud features (opt-in; off by default) ──────────────────
    "online_enabled": False,       # master switch — requires user consent
    "stt_provider": "offline",     # "offline" | "openai" | "gemini"
    "stt_model": "",               # blank → provider default
    "rewrite_enabled": False,      # LLM cleanup of the transcript before typing
    "rewrite_provider": "openai",  # "openai" | "gemini" | "openrouter" | "anthropic"
    "rewrite_model": "",           # blank → provider default
    "rewrite_prompt": "",          # blank → providers.DEFAULT_REWRITE_PROMPT
}


def config_from_settings(saved: dict) -> dict[str, Any]:
    cfg = dict(DEFAULT_CONFIG)
    for key in cfg:
        if key in saved:
            cfg[key] = saved[key]
    return cfg


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
        # Banglish is romanized speech: recognize as English, then transliterate
        "Banglish": (("banglish",), ("multilingual",), ("bangla", "english"), ("en",), ("vosk-model-small",)),
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


def get_recognizer(model_path: Path) -> Any:
    resolved = model_path.resolve()
    if resolved not in RECOGNIZER_CACHE:
        RECOGNIZER_CACHE[resolved] = create_recognizer(resolved)
    return RECOGNIZER_CACHE[resolved]


# ── Foreground-window tracker ────────────────────────────────────────────────
#
# Kothon is a clickable webview window: pressing the mic button focuses Kothon
# itself, so plain SendInput would type into Kothon instead of the field the
# user was dictating into. This tracks the last non-Kothon foreground window
# and restores focus to it immediately before typing.

class ForegroundTracker:
    def __init__(self, poll_interval: float = 0.15) -> None:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.GetForegroundWindow.restype = ctypes.wintypes.HWND
        user32.GetWindowThreadProcessId.argtypes = [
            ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.DWORD)
        ]
        user32.GetWindowThreadProcessId.restype = ctypes.wintypes.DWORD
        user32.SetForegroundWindow.argtypes = [ctypes.wintypes.HWND]
        user32.SetForegroundWindow.restype = ctypes.wintypes.BOOL
        user32.IsWindow.argtypes = [ctypes.wintypes.HWND]
        user32.IsWindow.restype = ctypes.wintypes.BOOL
        user32.AttachThreadInput.argtypes = [
            ctypes.wintypes.DWORD, ctypes.wintypes.DWORD, ctypes.wintypes.BOOL
        ]
        user32.AttachThreadInput.restype = ctypes.wintypes.BOOL
        self._user32 = user32
        self._kernel32 = kernel32
        self._own_pid = kernel32.GetCurrentProcessId()
        self._poll_interval = poll_interval
        self._last_external_hwnd: int | None = None
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        pid = ctypes.wintypes.DWORD()
        while self._running:
            hwnd = self._user32.GetForegroundWindow()
            if hwnd:
                self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value and pid.value != self._own_pid:
                    self._last_external_hwnd = hwnd
            time.sleep(self._poll_interval)

    def restore(self) -> None:
        """Bring the last external window back to the foreground before typing."""
        hwnd = self._last_external_hwnd
        if not hwnd or not self._user32.IsWindow(hwnd):
            self._last_external_hwnd = None
            return
        if self._user32.GetForegroundWindow() == hwnd:
            return
        cur_thread = self._kernel32.GetCurrentThreadId()
        target_thread = self._user32.GetWindowThreadProcessId(hwnd, None)
        # SetForegroundWindow alone is blocked by Windows' focus-steal guard;
        # attaching input queues briefly is the standard workaround.
        self._user32.AttachThreadInput(cur_thread, target_thread, True)
        try:
            self._user32.SetForegroundWindow(hwnd)
        finally:
            self._user32.AttachThreadInput(cur_thread, target_thread, False)
        time.sleep(0.03)


# ── Core app ──────────────────────────────────────────────────────────────────

class VoiceTyperApp:
    def __init__(
        self, model_path: Path, language: str, config: dict[str, Any] | None = None
    ) -> None:
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self.audio_queue: queue.Queue[bytes] = queue.Queue()
        self.recorder = AudioRecorder(self.audio_queue, device=self.config["mic_device"])
        self.typer = AutoTyper(char_delay=self.config["char_delay_ms"] / 1000.0)
        # Last few typed segments, newest last — powers undo and history
        self.history: list[str] = []
        self.is_listening = False
        self.worker_thread: threading.Thread | None = None
        # Serializes start/stop across UI, hotkey, tray, and auto-stop threads
        self._state_lock = threading.Lock()
        self.language = language
        self.model_path = model_path
        self.recognizer = self._select_recognizer()
        # Restores focus to the field the user was dictating into before typing
        self.focus_tracker: ForegroundTracker | None = None
        # Callbacks wired by Api
        self.on_partial = None
        self.on_typed = None
        self.on_error = None
        self.on_auto_stop = None
        self.on_level = None
        # VAD counters
        self._speech_chunks = 0
        self._silence_chunks = 0

    def _select_recognizer(self) -> Any:
        """Pick the STT engine from config: a cloud recognizer when online + a
        provider is chosen and a key is present, otherwise the offline engine."""
        if self.config.get("online_enabled") and self.config.get("stt_provider", "offline") != "offline":
            provider = self.config["stt_provider"]
            key = secrets_store.get_key(provider)
            if key:
                model = providers.stt_model_for(provider, self.config.get("stt_model", ""))
                return CloudRecognizer(provider, model, key, on_error=self._forward_error)
            _LOG.warning("Cloud STT selected (%s) but no API key set; using offline model", provider)
        return get_recognizer(self.model_path)

    def _forward_error(self, message: str) -> None:
        _LOG.error("%s", message)
        if self.on_error:
            self.on_error(message)

    def set_language(self, language: str) -> None:
        with self._state_lock:
            if self.is_listening:
                raise RuntimeError("Stop listening before switching language.")
            self.language = language
            self.model_path = resolve_model_path(language)
            self.recognizer = self._select_recognizer()
            self._flush_queue()

    def apply_config(self, updates: dict[str, Any]) -> None:
        """Apply settings-panel changes; audio settings need a stopped mic."""
        with self._state_lock:
            self.config.update({k: v for k, v in updates.items() if k in DEFAULT_CONFIG})
            self.recorder.device = self.config["mic_device"]
            self.typer.char_delay = float(self.config["char_delay_ms"]) / 1000.0
            # STT provider/model/online toggle may have changed — rebuild the engine
            self.recognizer = self._select_recognizer()

    # ── Normalization / typing helpers ────────────────────────────

    def _normalize(self, text: str, is_partial: bool = False) -> str:
        punctuation = bool(self.config["punctuation_commands"])
        if self.language in {"Bangla", "Banglish"}:
            return normalize_text(
                text, is_partial=is_partial,
                aggressive=bool(self.config["aggressive_banglish"]) and self.language == "Banglish",
                punctuation=punctuation,
            )
        return apply_punctuation(text) if punctuation else text

    def _rewrite(self, text: str) -> str:
        """Optionally clean up a finished segment with a cloud LLM.

        Off unless online + rewrite are enabled and a key is present. Any
        failure logs and returns the original text — the user never loses words.
        Runs on the audio worker thread, so network latency never blocks the UI.
        """
        if not text or not text.strip():
            return text
        if not (self.config.get("online_enabled") and self.config.get("rewrite_enabled")):
            return text
        provider = self.config.get("rewrite_provider", "openai")
        key = secrets_store.get_key(provider)
        if not key:
            return text
        try:
            result = providers.rewrite(
                provider, key, self.config.get("rewrite_model", ""),
                self.config.get("rewrite_prompt", ""), text, self.language,
            )
            return result or text
        except Exception as exc:
            _LOG.warning("Rewrite failed (%s); using original text: %s", provider, exc)
            return text

    def _emit(self, cleaned: str) -> None:
        """Type a finished segment into the focused app and record it."""
        _LOG.info("Typed (%s): %s", self.language, cleaned)
        self._restore_focus()
        out = cleaned + " " if self.config["trailing_space"] else cleaned
        if self.config["typing_mode"] == "paste":
            self.typer.paste_text(out)
        else:
            self.typer.type_text(out)
        self.history.append(cleaned)
        del self.history[:-8]

    def undo_last(self) -> str:
        """Erase the most recently typed segment with backspaces."""
        if not self.history:
            return ""
        last = self.history.pop()
        self._restore_focus()
        extra = 1 if self.config["trailing_space"] else 0
        self.typer.send_backspaces(len(last) + extra)
        _LOG.info("Undid last segment (%d chars)", len(last))
        return last

    def start_listening(self) -> None:
        with self._state_lock:
            if self.is_listening:
                return
            self._speech_chunks = 0
            self._silence_chunks = 0
            self.recorder.on_level = self.on_level
            self.recorder.on_error = self._on_recorder_error
            self.recorder.start()
            # Only mark listening once the mic is actually open
            self.is_listening = True
            self.worker_thread = threading.Thread(
                target=self._process_audio_loop, daemon=True
            )
            self.worker_thread.start()

    def stop_listening(self) -> str:
        # Hold the lock for the whole teardown: releasing it after only
        # flipping the flag lets a concurrent start_listening slip in and
        # have its freshly started recorder stopped by this call's tail.
        # The worker thread never takes this lock, so joining it here is safe.
        with self._state_lock:
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
            cleaned = self._rewrite(self._cleanup_text(self._normalize(final_text)))
            if cleaned:
                if self.on_typed:
                    self.on_typed(cleaned)
                self._emit(cleaned)
            self._flush_queue()
            return cleaned

    def _on_recorder_error(self, message: str) -> None:
        _LOG.error("Recorder error: %s", message)
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
                # VAD — silence detection (thresholds are user-tunable)
                silence_chunks_to_stop = max(
                    1, round(float(self.config["silence_seconds"]) / _CHUNK_SECONDS)
                )
                level = _rms(chunk)
                if level >= float(self.config["vad_threshold"]):
                    self._speech_chunks += 1
                    self._silence_chunks = 0
                elif self.config["auto_stop"] and self._speech_chunks >= _MIN_SPEECH_CHUNKS:
                    self._silence_chunks += 1
                    if self._silence_chunks >= silence_chunks_to_stop:
                        if self.is_listening and self.on_auto_stop:
                            self.on_auto_stop()
                        break

                # Speech recognition
                text = self.recognizer.accept_audio(chunk)
                if text:
                    cleaned = self._rewrite(self._cleanup_text(self._normalize(text)))
                    if cleaned:
                        if self.on_typed:
                            self.on_typed(cleaned)
                        self._emit(cleaned)
                else:
                    partial = self.recognizer.get_partial_text()
                    if partial and self.on_partial:
                        self.on_partial(self._normalize(partial, is_partial=True))

            except Exception as exc:
                _LOG.exception("Audio loop error: %s", exc)
                if self.on_error:
                    self.on_error(str(exc))

    def _restore_focus(self) -> None:
        if self.focus_tracker:
            try:
                self.focus_tracker.restore()
            except Exception:
                pass

    def _cleanup_text(self, text: str) -> str:
        # Collapse spaces/tabs but keep newlines from the "new line" command
        cleaned = re.sub(r"[ \t]+", " ", text)
        cleaned = re.sub(r" ?\n ?", "\n", cleaned).strip()
        if not cleaned:
            return ""
        if self.language in {"Bangla", "Banglish"}:
            return cleaned
        if not getattr(self, "config", DEFAULT_CONFIG)["auto_capitalize"]:
            return cleaned
        if cleaned.lower() == "i":
            return "I"
        return cleaned[0].upper() + cleaned[1:] if len(cleaned) > 1 else cleaned.upper()


# ── Windows integration helpers ───────────────────────────────────────────────

_MUTEX_NAME = "Kothon.SingleInstance.Mutex"
_ERROR_ALREADY_EXISTS = 183
_mutex_handle = None   # held for the process lifetime


def acquire_single_instance(name: str = _MUTEX_NAME) -> bool:
    """Return False if another Kothon instance already holds the mutex."""
    global _mutex_handle
    kernel32 = ctypes.windll.kernel32
    _mutex_handle = kernel32.CreateMutexW(None, False, name)
    return kernel32.GetLastError() != _ERROR_ALREADY_EXISTS


_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_VALUE = "Kothon"


def _autostart_command() -> str:
    if _IS_FROZEN:
        return f'"{sys.executable}"'
    return f'"{sys.executable}" "{Path(__file__).resolve()}"'


def is_autostart_enabled() -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, _RUN_VALUE)
        return True
    except OSError:
        return False


def set_autostart(enabled: bool) -> None:
    import winreg
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enabled:
                winreg.SetValueEx(key, _RUN_VALUE, 0, winreg.REG_SZ, _autostart_command())
            else:
                winreg.DeleteValue(key, _RUN_VALUE)
        _LOG.info("Start with Windows %s", "enabled" if enabled else "disabled")
    except OSError:
        _LOG.exception("Could not update the Start-with-Windows registry entry")


def hotkey_label(hotkey: str) -> str:
    """'ctrl+shift+v' → 'Ctrl+Shift+V' for UI display."""
    return "+".join(part.strip().capitalize() for part in hotkey.split("+"))


# ── Tray icon ─────────────────────────────────────────────────────────────────

def _make_tray_image() -> "Image.Image":
    """Kothon mark: waveform strokes hanging from a matra headstroke.

    Geometry mirrors assets/make_logo.py (the .ico/.png/.svg generator);
    drawn here so the tray icon needs no bundled asset. Rendered at 256
    and downscaled so the 16-32px tray sizes stay crisp.
    """
    ink, jade = (11, 16, 13, 255), (61, 214, 140, 255)
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, 256, 256], radius=58, fill=ink)
    for x, h, rise in ((74, 72, 0), (117, 104, 32), (160, 52, 0)):
        draw.rounded_rectangle([x, 88 - rise, x + 22, 88 + h], radius=11, fill=jade)
    draw.rounded_rectangle([52, 88, 204, 110], radius=11, fill=jade)
    return img.resize((64, 64), Image.LANCZOS)


# ── pywebview API ─────────────────────────────────────────────────────────────

class Api:
    def __init__(
        self,
        app: VoiceTyperApp,
        theme: str = "night",
        compact: bool = False,
        hotkey: str = "ctrl+shift+v",
    ) -> None:
        self._app = app
        self._theme = theme if theme in {"day", "night"} else "night"
        self._compact = bool(compact)
        self._hotkey = hotkey
        self._onboarded = False
        self._window: webview.Window | None = None
        self._tray: Any = None
        self._last_level_t: float = 0.0
        self._hk_handle: Any = None
        self._release_hook: Any = None

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
            "theme": self._theme,
            "compact": self._compact,
            "version": __version__,
            "hotkey": hotkey_label(self._hotkey),
            "onboarded": self._onboarded,
            "sounds": self._app.config["sounds"],
            "minimize_to": self._app.config["minimize_to"],
            "online_active": bool(
                self._app.config["online_enabled"]
                and (self._app.config["rewrite_enabled"]
                     or self._app.config["stt_provider"] != "offline")
            ),
        }

    def set_onboarded(self) -> dict:
        self._onboarded = True
        _settings.save({"onboarded": True})
        return {"success": True}

    # ── Settings panel ────────────────────────────────────────────

    def get_settings(self) -> dict:
        cfg = self._app.config
        return {
            "devices": AudioRecorder.list_input_devices(),
            "hotkey": self._hotkey,
            **{k: cfg[k] for k in DEFAULT_CONFIG},
            **self.get_ai_settings(),
        }

    def get_ai_settings(self) -> dict:
        """Provider metadata + which keys are stored (booleans only, never the
        keys themselves) + default prompt. Safe to send to the UI."""
        return {
            "providers": [
                {
                    "id": meta["id"],
                    "label": meta["label"],
                    "supports_rewrite": meta["supports_rewrite"],
                    "supports_stt": meta["supports_stt"],
                    "default_rewrite_model": meta["default_rewrite_model"],
                    "default_stt_model": meta["default_stt_model"],
                    "key_set": secrets_store.has_key(meta["id"]),
                }
                for meta in providers.PROVIDERS.values()
            ],
            "default_rewrite_prompt": providers.DEFAULT_REWRITE_PROMPT,
        }

    def set_api_key(self, provider: str, key: str) -> dict:
        if provider not in providers.PROVIDERS:
            return {"success": False, "error": "Unknown provider."}
        if secrets_store.set_key(provider, key):
            return {"success": True, "key_set": secrets_store.has_key(provider)}
        return {"success": False, "error": "Could not store the key (Credential Manager unavailable?)."}

    def clear_api_key(self, provider: str) -> dict:
        if provider not in providers.PROVIDERS:
            return {"success": False, "error": "Unknown provider."}
        secrets_store.delete_key(provider)
        return {"success": True, "key_set": secrets_store.has_key(provider)}

    def test_provider(self, provider: str, model: str = "") -> dict:
        if provider not in providers.PROVIDERS:
            return {"success": False, "error": "Unknown provider."}
        key = secrets_store.get_key(provider)
        if not key:
            return {"success": False, "error": "Save an API key first."}
        ok, message = providers.test_connection(provider, key, model)
        return {"success": ok, "message" if ok else "error": message}

    def set_online_enabled(self, enabled: bool) -> dict:
        """Record the consent toggle (the consent dialog lives in the UI)."""
        self._app.apply_config({"online_enabled": bool(enabled)})
        _settings.save({"online_enabled": bool(enabled)})
        return {"success": True, "online_enabled": bool(enabled)}

    def apply_settings(self, cfg: dict) -> dict:
        try:
            if self._app.is_listening:
                return {"success": False, "error": "Stop dictation before changing settings."}
            new_hotkey = str(cfg.get("hotkey", self._hotkey)).strip().lower() or self._hotkey
            stt_provider = cfg.get("stt_provider", "offline")
            if stt_provider not in ("offline", *providers.stt_providers()):
                stt_provider = "offline"
            rewrite_provider = cfg.get("rewrite_provider", "openai")
            if rewrite_provider not in providers.rewrite_providers():
                rewrite_provider = "openai"
            updates = {
                "mic_device": cfg.get("mic_device"),
                "silence_seconds": max(1.0, min(6.0, float(cfg.get("silence_seconds", 2.5)))),
                "vad_threshold": max(0.002, min(0.03, float(cfg.get("vad_threshold", 0.008)))),
                "auto_stop": bool(cfg.get("auto_stop", True)),
                "typing_mode": "paste" if cfg.get("typing_mode") == "paste" else "type",
                "char_delay_ms": max(0, min(30, int(cfg.get("char_delay_ms", 0)))),
                "trailing_space": bool(cfg.get("trailing_space", True)),
                "auto_capitalize": bool(cfg.get("auto_capitalize", True)),
                "punctuation_commands": bool(cfg.get("punctuation_commands", True)),
                "aggressive_banglish": bool(cfg.get("aggressive_banglish")),
                "push_to_talk": bool(cfg.get("push_to_talk")),
                "sounds": bool(cfg.get("sounds")),
                "always_on_top": bool(cfg.get("always_on_top", True)),
                "minimize_to": "tray" if cfg.get("minimize_to") == "tray" else "mini",
                "online_enabled": bool(cfg.get("online_enabled")),
                "stt_provider": stt_provider,
                "stt_model": str(cfg.get("stt_model", "")).strip(),
                "rewrite_enabled": bool(cfg.get("rewrite_enabled")),
                "rewrite_provider": rewrite_provider,
                "rewrite_model": str(cfg.get("rewrite_model", "")).strip(),
                "rewrite_prompt": str(cfg.get("rewrite_prompt", "")).strip(),
            }
            if updates["mic_device"] is not None:
                updates["mic_device"] = int(updates["mic_device"])
            # Rebinding validates the hotkey; failure keeps the old binding
            if not self.register_hotkey(new_hotkey, updates["push_to_talk"]):
                return {"success": False, "error": f'Hotkey "{new_hotkey}" could not be registered.'}
            self._hotkey = new_hotkey
            self._app.apply_config(updates)
            if self._window is not None:
                try:
                    self._window.on_top = updates["always_on_top"]
                except Exception:
                    pass   # older pywebview backends have no runtime setter
            _settings.save({**updates, "hotkey": new_hotkey})
            return {"success": True, "hotkey": hotkey_label(new_hotkey)}
        except Exception as exc:
            _LOG.exception("apply_settings failed")
            return {"success": False, "error": str(exc)}

    def open_config_folder(self) -> dict:
        try:
            folder = Path.home() / ".kothon"
            folder.mkdir(parents=True, exist_ok=True)
            os.startfile(str(folder))  # noqa: S606 — local folder, user-initiated
            return {"success": True}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    # ── Undo / history ────────────────────────────────────────────

    def undo_last(self) -> dict:
        try:
            if self._app.is_listening:
                return {"success": False, "error": "Stop dictation before undoing."}
            text = self._app.undo_last()
            if not text:
                return {"success": False, "error": "Nothing to undo."}
            return {"success": True, "text": text}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def get_history(self) -> list:
        return list(reversed(self._app.history))

    # ── Hotkey binding (toggle or push-to-talk) ──────────────────

    def register_hotkey(self, hotkey: str, push_to_talk: bool) -> bool:
        if not _HAS_KEYBOARD:
            return True   # nothing to bind against; settings still apply
        try:
            old_handle, old_hook = self._hk_handle, self._release_hook
            if push_to_talk:
                handle = _keyboard.add_hotkey(
                    hotkey, lambda: self._js("pttStart()"), suppress=False
                )
                release_key = hotkey.split("+")[-1].strip()
                hook = _keyboard.on_release_key(
                    release_key, lambda e: self._js("pttStop()")
                )
            else:
                handle = _keyboard.add_hotkey(
                    hotkey, lambda: self._js("toggleListen()"), suppress=False
                )
                hook = None
            # New binding succeeded — now drop the old one
            if old_handle is not None:
                try:
                    _keyboard.remove_hotkey(old_handle)
                except Exception:
                    pass
            if old_hook is not None:
                try:
                    _keyboard.unhook(old_hook)
                except Exception:
                    pass
            self._hk_handle, self._release_hook = handle, hook
            _LOG.info(
                "Hotkey %s registered (%s mode).",
                hotkey_label(hotkey), "push-to-talk" if push_to_talk else "toggle",
            )
            return True
        except Exception as exc:
            _LOG.error("Hotkey %r failed: %s", hotkey, exc)
            return False

    def set_theme(self, theme: str) -> dict:
        if theme not in {"day", "night"}:
            return {"success": False, "error": f"Unknown theme: {theme}"}
        self._theme = theme
        _settings.save({"theme": theme})
        return {"success": True}

    def set_compact(self, is_compact: bool) -> dict:
        try:
            self._compact = bool(is_compact)
            if self._window:
                width, height = COMPACT_SIZE if self._compact else FULL_SIZE
                self._window.resize(width, height)
            _settings.save({"compact": self._compact, **self._window_pos()})
            return {"success": True}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

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
        if not self._window:
            return
        # Without a tray icon there is no way to bring a hidden window back
        if self._tray:
            self._window.hide()
        else:
            self._window.minimize()

    def close_app(self) -> None:
        _settings.save({
            "language": self._app.language,
            "compact": self._compact,
            **self._window_pos(),
        })
        try:
            self._app.stop_listening()
        finally:
            if self._app.focus_tracker:
                self._app.focus_tracker.stop()
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
        # A manual stop may have won the race — don't override its result
        if not self._app.is_listening:
            return
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

        def on_autostart(icon, item):
            set_autostart(not is_autostart_enabled())

        menu = pystray.Menu(
            pystray.MenuItem("Show Kothon", on_show, default=True),
            pystray.MenuItem(f"Start / Stop  ({hotkey_label(self._hotkey)})", on_toggle),
            pystray.MenuItem(
                "Start with Windows", on_autostart,
                checked=lambda item: is_autostart_enabled(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", on_quit),
        )
        self._tray = pystray.Icon("Kothon", img, "Kothon", menu)
        self._tray.run_detached()


# ── Entry point ───────────────────────────────────────────────────────────────

def _fatal(message: str) -> None:
    _LOG.error("%s", message)
    try:
        ctypes.windll.user32.MessageBoxW(None, message, "Kothon", 0x10)  # MB_ICONERROR
    except Exception:
        pass
    sys.exit(1)


def main() -> None:
    applog.setup()
    _LOG.info("Kothon v%s starting (frozen=%s)", __version__, _IS_FROZEN)

    if not acquire_single_instance():
        _LOG.warning("Another Kothon instance is already running — exiting.")
        try:
            ctypes.windll.user32.MessageBoxW(
                None,
                "Kothon is already running.\nLook for it in the system tray.",
                "Kothon", 0x40,  # MB_ICONINFORMATION
            )
        except Exception:
            pass
        sys.exit(0)

    saved = _settings.load()
    default_language = saved.get("language", "Banglish")
    hotkey = str(saved.get("hotkey", "ctrl+shift+v"))
    win_x = saved.get("window_x")
    win_y = saved.get("window_y")

    try:
        model_path = resolve_model_path(default_language)
        app = VoiceTyperApp(
            model_path=model_path,
            language=default_language,
            config=config_from_settings(saved),
        )
    except FileNotFoundError as exc:
        _fatal(
            f"{exc}\n\nExpected location: {MODELS_DIR}\n"
            "Run  python download_model.py bn  (or en) to fetch one, "
            "then start Kothon again."
        )
        return
    is_compact = bool(saved.get("compact", False))
    api = Api(app, theme=saved.get("theme", "night"), compact=is_compact, hotkey=hotkey)
    api._onboarded = bool(saved.get("onboarded", False))

    ui_path = _ASSETS_DIR / "ui" / "index.html"
    start_width, start_height = COMPACT_SIZE if is_compact else FULL_SIZE

    create_kwargs: dict = dict(
        title="Kothon",
        url=ui_path.as_uri(),
        js_api=api,
        width=start_width,
        height=start_height,
        resizable=False,
        frameless=True,
        on_top=bool(app.config["always_on_top"]),
        background_color="#0b100d",   # matches the UI's --bg: no flash on launch
        easy_drag=False,
    )
    if win_x is not None:
        create_kwargs["x"] = int(win_x)
    if win_y is not None:
        create_kwargs["y"] = int(win_y)

    window = webview.create_window(**create_kwargs)
    api.set_window(window)
    api.setup_tray()

    focus_tracker = ForegroundTracker()
    focus_tracker.start()
    app.focus_tracker = focus_tracker

    if not api.register_hotkey(hotkey, bool(app.config["push_to_talk"])):
        _LOG.warning("Falling back to Ctrl+Shift+V.")
        api._hotkey = "ctrl+shift+v"
        api.register_hotkey("ctrl+shift+v", bool(app.config["push_to_talk"]))

    webview.start()


if __name__ == "__main__":
    main()
