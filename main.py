import queue
import threading
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

from banglish_fix import normalize_text
from recorder import AudioRecorder
from stt import OfflineSpeechRecognizer
from typer import AutoTyper


MODELS_DIR = Path("models")
LANGUAGE_OPTIONS = ("Bangla", "English", "Banglish")
RECOGNIZER_CACHE: dict[Path, OfflineSpeechRecognizer] = {}
LANGUAGE_HINTS = {
    "Bangla": "Best with a Bangla-capable Vosk model. Falls back to the best available local model.",
    "English": "Optimized for English dictation with the current local model.",
    "Banglish": "Works with mixed Bangla-English speech and also normalizes common Banglish words.",
}


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
        "Bangla": (("bangla",), ("bn",), ("vosk-model-small",)),
        "English": (("english",), ("en",), ("vosk-model-small-en",), ("vosk-model-small",)),
        "Banglish": (("banglish",), ("multilingual",), ("bangla", "english"), ("vosk-model-small",)),
    }

    for keywords in preferred_map.get(language, ()):
        match = _find_matching_model(*keywords)
        if match is not None:
            return match

    if MODELS_DIR.exists():
        candidate_dirs = sorted(path for path in MODELS_DIR.iterdir() if path.is_dir())
        if candidate_dirs:
            return candidate_dirs[0]

    raise FileNotFoundError(
        "No Vosk model was found in the 'models' directory. Add a model folder such as "
        "'models/vosk-model-small' and run the app again."
    )


def has_dedicated_model(language: str) -> bool:
    checks: dict[str, tuple[tuple[str, ...], ...]] = {
        "Bangla": (("bangla",), ("bn",)),
        "English": (("english",), ("en",), ("vosk-model-small-en",)),
        "Banglish": (("banglish",), ("multilingual",), ("bangla", "english")),
    }
    return any(_find_matching_model(*keywords) is not None for keywords in checks.get(language, ()))


def get_recognizer(model_path: Path) -> OfflineSpeechRecognizer:
    resolved_path = model_path.resolve()
    recognizer = RECOGNIZER_CACHE.get(resolved_path)
    if recognizer is None:
        recognizer = OfflineSpeechRecognizer(model_path=resolved_path)
        RECOGNIZER_CACHE[resolved_path] = recognizer
    return recognizer


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

    def set_language(self, language: str) -> None:
        if self.is_listening:
            raise RuntimeError("Stop listening before switching language.")

        model_path = resolve_model_path(language)
        self.language = language
        self.model_path = model_path
        self.recognizer = get_recognizer(model_path)
        self._flush_queue()

    def start_listening(self) -> None:
        if self.is_listening:
            return

        self.is_listening = True
        self.recorder.start()
        self.worker_thread = threading.Thread(target=self._process_audio_loop, daemon=True)
        self.worker_thread.start()

    def stop_listening(self) -> str:
        if not self.is_listening:
            return ""

        self.is_listening = False
        self.recorder.stop()

        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=1.0)

        final_text = self.recognizer.finalize_text()
        if self.language in {"Bangla", "Banglish"}:
            final_text = normalize_text(final_text)

        cleaned_text = self._cleanup_text(final_text)
        if cleaned_text:
            print(f"Typed ({self.language}): {cleaned_text}")
            self.typer.type_text(cleaned_text + " ")

        self._flush_queue()
        return cleaned_text

    def _flush_queue(self) -> None:
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break

    def _process_audio_loop(self) -> None:
        while self.is_listening:
            try:
                audio_chunk = self.audio_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            text = self.recognizer.accept_audio(audio_chunk)
            if not text:
                continue

            if self.language in {"Bangla", "Banglish"}:
                text = normalize_text(text)

            cleaned_text = self._cleanup_text(text)
            if cleaned_text:
                print(f"Typed ({self.language}): {cleaned_text}")
                self.typer.type_text(cleaned_text + " ")

    def _cleanup_text(self, text: str) -> str:
        cleaned = " ".join(text.split()).strip()
        if not cleaned:
            return ""

        if self.language in {"Bangla", "Banglish"}:
            return cleaned

        if cleaned.lower() == "i":
            return "I"

        return cleaned[0].upper() + cleaned[1:] if len(cleaned) > 1 else cleaned.upper()


class VoiceTyperUI:
    BG = "#f5f7fb"
    CARD = "#ffffff"
    TEXT = "#111827"
    MUTED = "#6b7280"
    BORDER = "#e5e7eb"
    ACCENT = "#111827"
    ACCENT_ACTIVE = "#000000"
    ACTIVE_PILL = "#111827"
    ACTIVE_PILL_TEXT = "#ffffff"
    IDLE_PILL = "#f3f4f6"
    IDLE_PILL_TEXT = "#4b5563"
    SUCCESS_BG = "#ecfdf3"
    SUCCESS_TEXT = "#166534"
    READY_BG = "#eff6ff"
    READY_TEXT = "#1d4ed8"
    ERROR_BG = "#fef2f2"
    ERROR_TEXT = "#b91c1c"
    MIC_IDLE = "#cbd5e1"
    MIC_ACTIVE = ("#f87171", "#ef4444", "#dc2626", "#ef4444")
    BUTTON_ON = "#dc2626"
    BUTTON_ON_ACTIVE = "#b91c1c"

    def __init__(self, root: tk.Tk, app: VoiceTyperApp) -> None:
        self.root = root
        self.app = app
        self.language_var = tk.StringVar(value=app.language)
        self.status_var = tk.StringVar(value="Ready")
        self.helper_var = tk.StringVar(value="Choose a language and press start.")
        self.button_var = tk.StringVar(value="Start")
        self.model_var = tk.StringVar(value=f"Model: {app.model_path.name}")
        self.language_buttons: dict[str, tk.Button] = {}
        self.available_languages = {language: has_dedicated_model(language) for language in LANGUAGE_OPTIONS}
        self._pulse_index = 0
        self._pulse_job: str | None = None

        self.root.title("Kothon")
        self.root.geometry("340x292")
        self.root.minsize(320, 280)
        self.root.configure(bg=self.BG)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.wm_attributes("-topmost", True)

        self._build_ui()
        self._set_idle_state()

    def _build_ui(self) -> None:
        outer = tk.Frame(self.root, bg=self.BG, padx=12, pady=12)
        outer.pack(fill="both", expand=True)

        card = tk.Frame(
            outer,
            bg=self.CARD,
            highlightbackground=self.BORDER,
            highlightthickness=1,
            padx=14,
            pady=14,
        )
        card.pack(fill="both", expand=True)

        top_row = tk.Frame(card, bg=self.CARD)
        top_row.pack(fill="x")

        tk.Label(
            top_row,
            text="Kothon",
            font=("Segoe UI Semibold", 16),
            fg=self.TEXT,
            bg=self.CARD,
        ).pack(side="left")

        pin_badge = tk.Label(
            top_row,
            text="Compact",
            font=("Segoe UI", 8),
            fg=self.MUTED,
            bg="#f8fafc",
            padx=8,
            pady=4,
        )
        pin_badge.pack(side="right")

        subtitle_row = tk.Frame(card, bg=self.CARD)
        subtitle_row.pack(fill="x", pady=(4, 10))

        tk.Label(
            subtitle_row,
            text="Offline voice typing",
            font=("Segoe UI", 9),
            fg=self.MUTED,
            bg=self.CARD,
        ).pack(side="left")

        self.status_badge = tk.Label(
            subtitle_row,
            textvariable=self.status_var,
            font=("Segoe UI Semibold", 9),
            padx=8,
            pady=3,
            bd=0,
        )
        self.status_badge.pack(side="right")

        lang_row = tk.Frame(card, bg=self.CARD)
        lang_row.pack(fill="x", pady=(0, 10))

        for index, language in enumerate(LANGUAGE_OPTIONS):
            button = tk.Button(
                lang_row,
                text=language,
                command=lambda value=language: self.select_language(value),
                font=("Segoe UI", 9),
                relief="flat",
                bd=0,
                padx=8,
                pady=7,
                cursor="hand2",
            )
            button.grid(row=0, column=index, sticky="ew", padx=(0, 6 if index < len(LANGUAGE_OPTIONS) - 1 else 0))
            lang_row.grid_columnconfigure(index, weight=1)
            self.language_buttons[language] = button

        self.mic_canvas = tk.Canvas(
            card,
            width=64,
            height=64,
            bg=self.CARD,
            highlightthickness=0,
            bd=0,
        )
        self.mic_canvas.pack(pady=(0, 10))
        self._build_mic_icon()

        tk.Label(
            card,
            textvariable=self.helper_var,
            font=("Segoe UI", 9),
            fg=self.MUTED,
            bg=self.CARD,
            wraplength=270,
            justify="center",
        ).pack(anchor="center")

        self.toggle_button = tk.Button(
            card,
            textvariable=self.button_var,
            command=self.toggle_listening,
            font=("Segoe UI Semibold", 10),
            bg=self.ACCENT,
            fg="white",
            activebackground=self.ACCENT_ACTIVE,
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=14,
            pady=9,
            cursor="hand2",
        )
        self.toggle_button.pack(fill="x", pady=(12, 8))

        footer = tk.Frame(card, bg=self.CARD)
        footer.pack(fill="x")

        tk.Label(
            footer,
            textvariable=self.model_var,
            font=("Segoe UI", 8),
            fg=self.MUTED,
            bg=self.CARD,
        ).pack(anchor="w")

        tk.Label(
            footer,
            text="Keep the target field focused.",
            font=("Segoe UI", 8),
            fg=self.MUTED,
            bg=self.CARD,
        ).pack(anchor="w", pady=(4, 0))

        self._refresh_language_buttons()

    def _build_mic_icon(self) -> None:
        self.mic_canvas.delete("all")
        self.mic_canvas.create_oval(4, 4, 60, 60, fill="#f8fafc", outline="")
        self.mic_glow = self.mic_canvas.create_oval(12, 12, 52, 52, fill="#fee2e2", outline="")
        self.mic_body = self.mic_canvas.create_oval(23, 12, 41, 36, fill=self.MIC_IDLE, outline="")
        self.mic_stem = self.mic_canvas.create_rectangle(29, 36, 35, 45, fill=self.MIC_IDLE, outline="")
        self.mic_base = self.mic_canvas.create_arc(18, 28, 46, 50, start=200, extent=140, style="arc", width=3, outline=self.MIC_IDLE)
        self.mic_canvas.create_rectangle(23, 50, 41, 53, fill="#d1d5db", outline="")
        self._set_mic_idle()

    def _set_mic_idle(self) -> None:
        self.mic_canvas.itemconfigure(self.mic_glow, fill="#eef2f7")
        self.mic_canvas.itemconfigure(self.mic_body, fill=self.MIC_IDLE)
        self.mic_canvas.itemconfigure(self.mic_stem, fill=self.MIC_IDLE)
        self.mic_canvas.itemconfigure(self.mic_base, outline=self.MIC_IDLE)

    def _animate_mic(self) -> None:
        if not self.app.is_listening:
            self._pulse_job = None
            self._set_mic_idle()
            return

        color = self.MIC_ACTIVE[self._pulse_index % len(self.MIC_ACTIVE)]
        glow_colors = ("#fee2e2", "#fecaca", "#fca5a5", "#fecaca")
        glow = glow_colors[self._pulse_index % len(glow_colors)]

        self.mic_canvas.itemconfigure(self.mic_glow, fill=glow)
        self.mic_canvas.itemconfigure(self.mic_body, fill=color)
        self.mic_canvas.itemconfigure(self.mic_stem, fill=color)
        self.mic_canvas.itemconfigure(self.mic_base, outline=color)

        self._pulse_index += 1
        self._pulse_job = self.root.after(260, self._animate_mic)

    def _start_mic_animation(self) -> None:
        if self._pulse_job is None:
            self._pulse_index = 0
            self._animate_mic()

    def _stop_mic_animation(self) -> None:
        if self._pulse_job is not None:
            self.root.after_cancel(self._pulse_job)
            self._pulse_job = None
        self._set_mic_idle()

    def _refresh_language_buttons(self) -> None:
        active_language = self.language_var.get()
        for language, button in self.language_buttons.items():
            if language == active_language:
                button.configure(
                    bg=self.ACTIVE_PILL,
                    fg=self.ACTIVE_PILL_TEXT,
                    activebackground=self.ACTIVE_PILL,
                    activeforeground=self.ACTIVE_PILL_TEXT,
                )
            else:
                button.configure(
                    bg=self.IDLE_PILL,
                    fg=self.IDLE_PILL_TEXT,
                    activebackground=self.IDLE_PILL,
                    activeforeground=self.IDLE_PILL_TEXT,
                )

    def _set_idle_state(self) -> None:
        self.status_var.set("Ready")
        selected_language = self.language_var.get()
        self.helper_var.set(f"{selected_language} mode selected. {LANGUAGE_HINTS[selected_language]}")
        self.button_var.set("Start")
        self.status_badge.configure(bg=self.READY_BG, fg=self.READY_TEXT)
        self.toggle_button.configure(bg=self.ACCENT, activebackground=self.ACCENT_ACTIVE)
        self._stop_mic_animation()

    def _set_listening_state(self) -> None:
        self.status_var.set("Listening")
        self.helper_var.set(f"Listening in {self.language_var.get()} mode. Speak clearly, then press stop.")
        self.button_var.set("Stop")
        self.status_badge.configure(bg=self.SUCCESS_BG, fg=self.SUCCESS_TEXT)
        self.toggle_button.configure(bg=self.BUTTON_ON, activebackground=self.BUTTON_ON_ACTIVE)
        self._start_mic_animation()

    def _set_error_state(self, message: str) -> None:
        self.status_var.set("Error")
        self.helper_var.set(message)
        self.button_var.set("Start")
        self.status_badge.configure(bg=self.ERROR_BG, fg=self.ERROR_TEXT)
        self.toggle_button.configure(bg=self.ACCENT, activebackground=self.ACCENT_ACTIVE)
        self._stop_mic_animation()

    def select_language(self, language: str) -> None:
        try:
            self.app.set_language(language)
            self.language_var.set(language)
            self.model_var.set(f"Model: {self.app.model_path.name}")
            self._refresh_language_buttons()
            self._set_idle_state()
            if not self.available_languages.get(language, False):
                self.helper_var.set(
                    f"{language} mode selected. Dedicated model not found, so Kothon is using {self.app.model_path.name}."
                )
        except Exception as exc:
            self._set_error_state(str(exc))
            self._refresh_language_buttons()
            messagebox.showerror("Kothon", str(exc))

    def toggle_listening(self) -> None:
        try:
            if self.app.is_listening:
                typed_text = self.app.stop_listening()
                self._set_idle_state()
                if typed_text:
                    self.helper_var.set(f"Typed: {typed_text}")
                else:
                    self.helper_var.set("No final speech was detected. Try speaking clearly, then press stop.")
            else:
                self.app.start_listening()
                self._set_listening_state()
        except Exception as exc:
            self.app.stop_listening()
            self._set_error_state(str(exc))
            messagebox.showerror("Kothon", str(exc))

    def on_close(self) -> None:
        self._stop_mic_animation()
        try:
            self.app.stop_listening()
        finally:
            self.root.destroy()


def main() -> None:
    default_language = "Banglish"
    model_path = resolve_model_path(default_language)
    app = VoiceTyperApp(model_path=model_path, language=default_language)
    root = tk.Tk()
    VoiceTyperUI(root, app)
    root.mainloop()


if __name__ == "__main__":
    main()
