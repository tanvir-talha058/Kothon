# Kothon — Offline Voice Typer

[![CI](https://github.com/tanvir-talha058/Kothon/actions/workflows/ci.yml/badge.svg)](https://github.com/tanvir-talha058/Kothon/actions/workflows/ci.yml)

An offline voice-typing app for Windows. Speak in **Bangla, English, or Banglish**; Kothon converts your speech to text locally with [Vosk](https://alphacephei.com/vosk/), applies Banglish→Bangla normalization, and types the result into whatever application is focused.

No internet required — all processing happens on your machine.

## Features

- Fully offline speech-to-text (Vosk)
- Small always-on-top GUI with live transcript, waveform, and language switcher
- Three language modes: **Bangla**, **English**, **Banglish** (mixed speech with automatic Banglish→Bangla word conversion)
- Auto-types into the active window using native Windows `SendInput` (Unicode-safe, works with Bangla text)
- Global hotkey **Ctrl+Shift+V** to start/stop from anywhere
- Auto-stop after ~2.5 s of silence
- System tray icon (minimize to tray, quick start/stop, quit)
- Spoken punctuation in all modes: "comma", "full stop", "question mark", "new line", etc.
- Copy button to grab the whole transcript
- **Mini bar**: the minimize button collapses Kothon to a small always-on-top dock (waveform + mic + timer) so you can dictate anywhere without the full window
- **Custom dictionary**: add your own Banglish→Bangla words and phrases in `~/.kothon/custom_words.json` — user entries override the built-ins
- **Settings panel** (gear icon): microphone picker, auto-stop delay, silence threshold, hotkey, push-to-talk, typing mode, and recent takes
- **Undo**: erase the last typed segment with one click
- **Push-to-talk**: optionally hold the hotkey to talk, release to stop
- Bangla spoken punctuation: "দাঁড়ি", "কমা", "প্রশ্নবোধক", "নতুন লাইন"
- Optional aggressive Banglish mode: transliterates words the dictionary doesn't know (Avro-style)
- Day/night theme, custom hotkey, optional start-with-Windows (tray menu)
- Single-instance guard — launching Kothon twice just points you at the running copy
- Remembers language, theme, hotkey, and window position (`~/.kothon/settings.json`); activity log at `~/.kothon/kothon.log`
- **Optional online providers** (off by default): bring your own API key for OpenAI, Google Gemini, OpenRouter, or Anthropic Claude to get AI transcript cleanup, and cloud speech-to-text via OpenAI or Gemini (see below)

## Requirements

- Windows 10/11
- Python 3.10+
- A working microphone
- A Vosk model in the `models/` folder (see below)

## Installation

```bash
pip install -r requirements.txt
```

Dependencies: `vosk`, `sherpa-onnx`, `numpy`, `sounddevice`, `pywebview`, `keyboard`, `pystray`, `Pillow`, `keyring` (for storing optional cloud API keys in the Windows Credential Manager).
(`sherpa-onnx` powers Bangla recognition — without it, Bangla mode will not work.
`keyboard`, `pystray`, and `Pillow` are optional — without them you lose the global hotkey and tray icon, but the app still runs.)

### Download a model

```bash
python download_model.py bn   # Bangla (~94 MB)
python download_model.py en   # English (~40 MB)
```

Or manually: get a model from https://alphacephei.com/vosk/models and extract it into `models/`, e.g.:

```text
Kothon/
└── models/
    └── vosk-model-small-en-us-0.15/
```

The app auto-discovers models by folder name — no exact name is required. It picks the best match for the selected language:

- **English** — any folder containing `english` or `en` (e.g. `vosk-model-small-en-us-0.15`)
- **Bangla** — a folder containing `bangla` or `bn` (e.g. `vosk-model-small-bn-0.4`). **Without a Bangla model, Bangla mode falls back to the English model and recognition will be poor.**
- **Banglish** — a `banglish`/`multilingual` model if present, otherwise falls back to whatever is available

## Usage

```bash
python main.py
```

1. Pick a language mode with the pills at the bottom.
2. Click into the app where you want text typed (editor, browser, chat…).
3. Tap the mic button or press **Ctrl+Shift+V** and speak.
4. Recognized text is typed into the focused window as you go. Stop with the mic button, the hotkey, or just pause — it auto-stops after silence.

## Project Structure

```text
Kothon/
├── main.py           # App core, model resolution, pywebview API, tray, hotkey
├── recorder.py       # Microphone capture (sounddevice)
├── stt.py            # Vosk recognizer wrapper
├── banglish_fix.py   # Banglish→Bangla + spoken-punctuation rules
├── typer.py          # Unicode typing via Windows SendInput
├── settings.py       # Persisted settings (~/.kothon/settings.json)
├── applog.py         # Rotating file log (~/.kothon/kothon.log)
├── ui/index.html     # GUI (pywebview)
├── assets/           # Icon + logo (regenerate with assets/make_logo.py)
├── tests/            # Unit + integration tests (python -m pytest tests/)
└── models/           # STT models (you download these)
```

## Customization

**Custom words** — create `~/.kothon/custom_words.json`:

```json
{
  "words":   { "tanvir": "তানভীর" },
  "phrases": { "ki obostha": "কি অবস্থা" }
}
```

Entries apply in Bangla/Banglish modes and take priority over the built-in dictionary. Restart Kothon after editing.

**Hotkey** — add `"hotkey": "ctrl+alt+k"` (any [keyboard](https://github.com/boppreh/keyboard) combo) to `~/.kothon/settings.json`. Invalid combos fall back to Ctrl+Shift+V.

**Start with Windows** — right-click the tray icon → "Start with Windows".

## Troubleshooting

- **"No Vosk model found"** — put an extracted model folder inside `models/` (the folder containing `am/`, `conf/`, `graph/`…, not the zip).
- **Hotkey doesn't work** — the `keyboard` package may need the terminal run as Administrator; another app may own Ctrl+Shift+V.
- **Nothing is typed** — make sure the target window is focused and check the console for recognition output.
- **Bangla output is poor** — install a Bangla-capable Vosk model; the bundled English model cannot recognize Bangla speech. Banglish word conversion only fixes spelling of romanized words the recognizer got right.
- **Mic errors** — check Windows microphone privacy settings and that no app holds the mic exclusively.

## Optional online providers

Kothon is **fully offline by default** and that is the recommended way to use it.
If you want higher accuracy or grammar cleanup and are comfortable sending your
speech to a third party, open **Settings → AI & Cloud (online)**:

1. Turn on **Enable online features** (a one-time consent dialog explains what
   leaves your machine; an **online** badge then shows in the title bar).
2. Paste an API key for OpenAI, Google Gemini, OpenRouter, or Anthropic Claude
   and click **Save** / **Test**. Keys are stored in the **Windows Credential
   Manager** — never in `settings.json` and never displayed again.
3. Optionally pick a **Cloud speech-to-text** provider (OpenAI or Gemini), and/or
   enable **AI rewrite** to clean up grammar and punctuation before typing.

If a cloud call fails, AI rewrite falls back to the raw transcript (you never lose
your words) and cloud speech-to-text surfaces an error while offline stays usable.
Note that cloud speech-to-text is not live — text appears when you stop dictating,
not word-by-word.

## Privacy

By default, all recognition runs locally and no audio or text ever leaves your
machine. This changes **only** if you explicitly enable online features and add an
API key (see above); Kothon then sends audio and/or text to the provider you
choose. There are still no accounts, no telemetry, and no Kothon servers.

## License

MIT
