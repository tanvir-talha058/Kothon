# 🎤 Voice Typer (Offline) — Bangla, English & Banglish

A lightweight, fully offline voice typing tool for Windows that converts speech into text and automatically types it anywhere on your system.

---

## 🚀 Overview

Voice Typer is designed to make typing effortless. Speak in **Bangla, English, or Banglish**, and the app will:

* Convert speech to text (offline)
* Apply basic Banglish normalization
* Clean up simple grammar issues
* Automatically type into any active application

> ⚡ No internet required
> 🔒 Privacy-first (all processing happens locally)

---

## 🎯 Key Features

* 🎙️ Real-time voice-to-text (offline)
* 🌐 Supports Bangla + English + Banglish (basic)
* ✍️ Auto typing into any software (browser, Word, IDE, etc.)
* ⌨️ Hotkey-based activation
* 🧠 Lightweight and fast (no heavy AI dependency)

---

## 🧠 System Architecture

```
User Voice
   ↓
Audio Capture (Mic)
   ↓
Speech-to-Text (Vosk)
   ↓
Banglish Normalization (Rule-based)
   ↓
Text Cleanup (Basic grammar)
   ↓
Auto Typing (System Input)
```

---

## 🛠️ Tech Stack

| Component           | Technology Used |
| ------------------- | --------------- |
| Speech Recognition  | Vosk (offline)  |
| Audio Input         | sounddevice     |
| Auto Typing         | pyautogui       |
| Hotkeys             | keyboard        |
| Language Processing | Rule-based      |
| Language            | Python          |

---

## 📦 Installation

### 1. Clone Repository

```bash
git clone https://github.com/your-username/voice-typer.git
cd voice-typer
```

---

### 2. Install Dependencies

```bash
pip install vosk sounddevice pyautogui keyboard
```

---

### 3. Download Vosk Model

Download a small model (recommended):

* Example: `vosk-model-small-en-us` or Bangla-supported model

Then place it inside:

```
/models/vosk-model-small
```

---

## ▶️ Usage

### Run the App

```bash
python main.py
```

---

### Start Voice Typing

Press:

```
CTRL + SHIFT + V
```

Then:

* Speak clearly
* The app will type automatically into the active window

---

## 📁 Project Structure

```
voice-typer/
│
├── main.py              # Entry point
├── recorder.py          # Audio capture
├── stt.py               # Speech-to-text logic
├── banglish_fix.py      # Banglish normalization
├── typer.py             # Auto typing system
├── models/              # Vosk models
│   └── vosk-model-small
```

---

## 🔧 Core Modules

### 🎤 recorder.py

Handles microphone input and audio streaming.

---

### 🧠 stt.py

Uses Vosk to convert audio → text.

---

### 🔄 banglish_fix.py

Simple dictionary-based Banglish → Bangla conversion.

Example:

```python
"ami" → "আমি"
"tumi" → "তুমি"
```

---

### ⌨️ typer.py

Injects text into the active application using system-level typing.

---

## ⚠️ Limitations

* ❌ Banglish conversion is basic (rule-based)
* ❌ Grammar correction is limited (no AI model)
* ⚠️ Accuracy depends on microphone quality
* ⚠️ Background noise affects performance

---

## 🧪 Future Improvements

* ✅ Integrate Whisper (better accuracy)
* ✅ Add real-time streaming output
* ✅ Smart Banglish NLP engine
* ✅ Minimal GUI (system tray app)
* ✅ Offline grammar model integration
* ✅ Multi-language auto-detection

---

## 💡 Contribution Ideas

* Improve Banglish dictionary
* Add punctuation prediction
* Optimize latency
* Build UI (Electron / Flutter)

---

## 🔐 Privacy

This app runs entirely offline.
No voice data is sent to any server.

---

## 📜 License

MIT License — free to use and modify.

---

## 👤 Author

Developed by a passionate builder focused on practical AI tools.

---

## ⭐ Final Note

This is not meant to be a perfect AI assistant.
It is designed to be:

> **Fast. Offline. Useful.**

If it saves even a few minutes of typing every day — it’s already a success.
