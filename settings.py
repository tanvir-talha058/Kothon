import json
import os
from pathlib import Path

_PATH = Path.home() / ".kothon" / "settings.json"


def load() -> dict:
    try:
        if _PATH.exists():
            return json.loads(_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def save(data: dict) -> None:
    try:
        # Merge so partial saves (e.g. a language switch) keep unrelated keys
        merged = {**load(), **data}
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        # Atomic replace so a crash mid-write can't corrupt the file
        tmp = _PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(merged, indent=2), encoding="utf-8")
        os.replace(tmp, _PATH)
    except Exception:
        pass
