# Voice Typer (Offline)

An offline voice typing tool for Windows that listens through your microphone, converts speech to text with Vosk, applies simple Banglish normalization, and types the result into the active application.

This project is intended for **Bangla, English, and Banglish** input. Bangla recognition quality depends heavily on the Vosk model you place in the project.

## Features

- Fully offline speech-to-text
- Hotkey-based start and stop control
- Automatic typing into the active window
- Simple Banglish-to-Bangla normalization rules
- Lightweight Python setup for Windows 10

## How It Works

1. `recorder.py` captures microphone audio.
2. `stt.py` sends audio chunks to Vosk for offline recognition.
3. `banglish_fix.py` normalizes common Banglish words and phrases.
4. `main.py` cleans the text and sends it to `typer.py`.
5. `typer.py` types the final text into the currently focused app.

## Requirements

- Windows 10
- Python 3.10+ recommended
- A working microphone
- A downloaded Vosk model placed in the correct folder

## Installation

### 1. Install Python dependencies

From the project folder:

```bash
pip install -r requirements.txt
```

`requirements.txt` contains only the needed packages:

- `vosk`
- `sounddevice`
- `pyautogui`
- `keyboard`

### 2. Download a Vosk model

Download a Vosk speech recognition model and place it at:

```text
models/vosk-model-small
```

The app expects that exact folder path by default.

Example structure:

```text
Kothon/
├── models/
│   └── vosk-model-small/
│       ├── am/
│       ├── conf/
│       ├── graph/
│       └── ...
```

Important notes:

- If you use an English-only model, Bangla recognition will not work well.
- For Bangla or mixed-language use, choose a Vosk model that supports the language you want.
- Banglish normalization only adjusts recognized text after speech recognition. It does not replace the need for a suitable Bangla-capable model.

## Running the App

```bash
python main.py
```

When the program starts, it waits for the hotkey and runs in the console.

## Hotkeys

- `Ctrl+Shift+V` - Start or stop voice typing
- `Esc` - Exit the application

## Usage

1. Open any application where you want text to be typed.
2. Run `python main.py`.
3. Press `Ctrl+Shift+V` to begin recording.
4. Speak clearly into your microphone.
5. Press `Ctrl+Shift+V` again to stop recording.
6. The recognized text is typed into the active window automatically.

## Project Structure

```text
Kothon/
├── main.py             # Application entry point and hotkey loop
├── recorder.py         # Microphone audio capture
├── stt.py              # Offline speech recognition with Vosk
├── banglish_fix.py     # Banglish normalization rules
├── typer.py            # Automatic typing with pyautogui
├── requirements.txt    # Python dependencies
├── README.md           # Project documentation
├── project plan.md     # Original project plan
└── models/
    └── vosk-model-small/
```

## File Responsibilities

- `main.py`
  - Creates the queue and app components
  - Registers the hotkey
  - Starts/stops recording
  - Cleans recognized text before typing

- `recorder.py`
  - Records raw microphone audio using `sounddevice`
  - Pushes audio chunks into a queue

- `stt.py`
  - Loads the Vosk model from `models/vosk-model-small`
  - Accepts audio chunks and returns finalized text

- `banglish_fix.py`
  - Replaces common Banglish words and phrases with Bangla text where possible

- `typer.py`
  - Types output text into the active application

## Limitations

- Bangla support depends on the Vosk model you install.
- Recognition accuracy depends on microphone quality, pronunciation, and background noise.
- Banglish normalization is simple and rule-based, so many words will remain unchanged.
- The app types into whichever window is currently focused, so make sure the correct target application is active.
- Global hotkeys and automatic typing may require appropriate permissions on some systems.

## Troubleshooting

### Model not found

If the app reports that the Vosk model is missing, verify that this folder exists:

```text
models/vosk-model-small
```

Do not leave the downloaded model under a different folder name unless you also change the code.

### Nothing is being typed

Check the following:

- The target application window is focused
- The microphone is connected and working
- Recording was started with `Ctrl+Shift+V`
- Speech recognition is producing text in the console output

### Hotkey does not respond

Possible causes:

- The `keyboard` package may need administrator privileges on some Windows systems
- Another application may already be using the same hotkey
- Security software may block global keyboard hooks

Try running the terminal as Administrator if needed.

### Microphone problems

If recording fails:

- Confirm the correct input device is available in Windows
- Close other software that may be exclusively using the microphone
- Check Windows microphone privacy settings

### Bangla output is poor or missing

This usually means the selected Vosk model does not support Bangla well enough. Use a Bangla-capable or multilingual model if you want better Bangla recognition.

### Typed text appears in the wrong place

`pyautogui` types into the active window. Click the destination field before starting dictation.

## Privacy

All speech processing is designed to run locally on your machine. No cloud service is required for recognition.

## Notes

This repository currently uses a simple root-level file layout rather than a package structure. All main modules are imported directly from the project root, matching the current implementation in `main.py`.