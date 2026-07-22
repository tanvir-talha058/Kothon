"""Download speech models for Kothon.

Usage:
    python download_model.py bn     # Bangla  (sherpa-onnx streaming, ~94 MB)
    python download_model.py en     # English (Vosk small, ~40 MB)

Models land in ./models/ next to this script. This is the only part of
Kothon that touches the network, and it runs only when you invoke it.
"""
from __future__ import annotations

import sys
import urllib.request
import zipfile
from pathlib import Path

MODELS_DIR = Path(__file__).parent / "models"

EN_ZIP_URL = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"

BN_BASE = "https://huggingface.co/alphacep/vosk-model-small-streaming-bn/resolve/main"
BN_DIR = "vosk-model-small-streaming-bn"
BN_FILES = [
    "am-onnx/encoder.onnx",
    "am-onnx/decoder.onnx",
    "am-onnx/joiner.onnx",
    "lang/tokens.txt",
    "lang/bpe.model",
]


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  {url}")

    def report(blocks: int, block_size: int, total: int) -> None:
        if total > 0:
            done = min(blocks * block_size / total, 1.0)
            bar = "#" * int(done * 30)
            sys.stdout.write(f"\r  [{bar:<30}] {done * 100:5.1f}%")
            sys.stdout.flush()

    urllib.request.urlretrieve(url, dest, reporthook=report)
    print()


def download_en() -> None:
    zip_path = MODELS_DIR / "vosk-model-small-en-us-0.15.zip"
    if (MODELS_DIR / "vosk-model-small-en-us-0.15").exists():
        print("English model already present.")
        return
    print("Downloading the English model (~40 MB)…")
    _download(EN_ZIP_URL, zip_path)
    print("Extracting…")
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(MODELS_DIR)
    zip_path.unlink(missing_ok=True)
    print(f"Done → {MODELS_DIR / 'vosk-model-small-en-us-0.15'}")


def download_bn() -> None:
    target = MODELS_DIR / BN_DIR
    if (target / "am-onnx" / "encoder.onnx").exists():
        print("Bangla model already present.")
        return
    print("Downloading the Bangla model (~94 MB, 5 files)…")
    for rel in BN_FILES:
        _download(f"{BN_BASE}/{rel}", target / rel)
    print(f"Done → {target}")


def main() -> None:
    lang = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    if lang not in {"bn", "en"}:
        print(__doc__)
        sys.exit(2)
    try:
        download_bn() if lang == "bn" else download_en()
    except Exception as exc:
        print(f"\nDownload failed: {exc}\nCheck your connection and try again.")
        sys.exit(1)


if __name__ == "__main__":
    main()
