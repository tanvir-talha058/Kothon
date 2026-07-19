"""App-wide logging: rotating file at ~/.kothon/kothon.log plus console.

Import and call setup() once at startup, then use logging.getLogger("kothon")
(or a child like "kothon.stt") everywhere instead of print().
"""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

LOG_PATH = Path.home() / ".kothon" / "kothon.log"


def setup(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("kothon")
    if logger.handlers:          # already configured (tests, re-entry)
        return logger
    logger.setLevel(level)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"
    )

    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            LOG_PATH, maxBytes=512_000, backupCount=2, encoding="utf-8"
        )
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except Exception:
        pass                     # logging must never break the app

    # Windows consoles are often cp1252 — Bangla text must not crash logging
    try:
        import sys
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except Exception:
        pass

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)
    return logger
