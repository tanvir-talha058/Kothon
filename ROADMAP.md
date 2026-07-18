# Kothon — Product Roadmap

From working prototype to a professional product, in order of impact.

## Phase 1 — Make the core promise true (highest impact)

The app promises Bangla voice typing, but ships only an English model. This is the gap between demo and product.

1. **Real Bangla recognition.** The classic `vosk` engine has no Bangla model anywhere. Two options:
   - **sherpa-onnx** backend — the Vosk maintainers publish `alphacep/vosk-model-small-streaming-bn` (ONNX). Streaming, light, offline. Closest to current architecture.
   - **faster-whisper** backend — best Bangla/Banglish accuracy available offline, but not streaming (type-on-pause instead of live partials) and heavier (~1 GB model, benefits from GPU).
   - Recommended: define a small `SpeechEngine` interface in `stt.py`, implement sherpa-onnx first (keeps live partials), add whisper later as a "high accuracy" option.
2. **Smarter Banglish.** The fixed ~250-word dictionary can't scale. Replace with rule-based phonetic transliteration (Avro-style mapping), keep the dictionary as an override layer, and add a **user dictionary** (UI to add your own words — names, workplace terms).
3. **First-run model downloader.** Models can't live in git. On first launch: pick language → download model with progress bar → verify checksum. This is also what makes the installer small.

## Phase 2 — Distribution (what makes it "a product")

4. **Single-file installer.** PyInstaller build → Inno Setup installer (`KothonSetup.exe`). App icon, version number, Start-menu entry, optional "start with Windows".
5. **Code signing.** Unsigned apps that hook the keyboard *and* inject keystrokes will trip antivirus/SmartScreen. A signing cert (~$100–300/yr) is near-mandatory for distribution.
6. **Versioned releases.** Git tags + GitHub Releases with changelog. Later: in-app update check (a version-check ping is the one network call worth making — keep it opt-in to preserve the offline promise).
7. **License decision.** README says MIT — confirm and add the actual `LICENSE` file.

## Phase 3 — UX depth (what makes it feel professional)

8. **Settings panel** (gear icon → second view in the webview):
   - Microphone device picker + live input level check
   - VAD sensitivity and auto-stop delay sliders (hardcoded today)
   - Hotkey remapping
   - Toggle: auto-capitalization, spoken punctuation, sound feedback
9. **Push-to-talk mode.** Hold the hotkey to talk, release to stop — many users prefer it to toggle.
10. **Dictation history.** Last N utterances with per-item copy; "undo last" (send backspaces to erase the last typed segment).
11. **Onboarding.** First-run: mic permission check, mic test, 10-second tutorial ("focus any app, press Ctrl+Shift+V, speak").
12. **Bangla UI localization.** The app types Bangla but speaks English — offer the interface itself in বাংলা.
13. **Feedback sounds.** Subtle start/stop chirps (dictation apps need non-visual confirmation since you're focused on another window).

## Phase 4 — Engineering foundation (pays for everything above)

14. **Package structure.** Move to `kothon/` package + `pyproject.toml`, pin dependency versions.
15. **CI.** GitHub Actions: run the test suite (30 tests exist in `tests/`) + ruff lint on every push; build the exe on tag.
16. **Logging.** Replace `print()` with `logging` to `~/.kothon/kothon.log` — you'll need it for the first user bug report.
17. **More tests.** Integration test feeding a WAV fixture through recognizer → normalizer → cleanup; VAD unit tests.
18. **Performance.** numpy for RMS (currently pure-Python over 8000 samples, computed twice per chunk); measure end-to-end latency.

## Explicitly out (the product's identity)

- **No cloud STT, no telemetry, no accounts.** "Fully offline, your voice never leaves your machine" is the differentiator against Windows dictation and Google — protect it and say it loudly.

## Suggested order of attack

| Step | Effort | Why first |
|------|--------|-----------|
| sherpa-onnx Bangla backend (1) | ~2–4 sessions | The core promise |
| Model downloader (3) | ~1 session | Unblocks packaging |
| PyInstaller + installer (4) | ~1–2 sessions | Makes it shareable |
| Settings panel (8) | ~1–2 sessions | Most-requested UX |
| Package + CI (14, 15) | ~1 session | Cheap now, expensive later |

Everything else follows user feedback once real users have it.
