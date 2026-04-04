from __future__ import annotations

import re

_PHRASE_REPLACEMENTS: dict[str, str] = {
    "assalamu alaikum": "আসসালামু আলাইকুম",
}

_WORD_REPLACEMENTS: dict[str, str] = {
    "ami": "আমি",
    "tumi": "তুমি",
    "apni": "আপনি",
    "bhalo": "ভালো",
    "valo": "ভালো",
    "kemon": "কেমন",
    "na": "না",
    "ki": "কি",
}


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


def normalize_text(text: str) -> str:
    normalized = _normalize_whitespace(text)
    if not normalized:
        return ""

    for source, target in _PHRASE_REPLACEMENTS.items():
        pattern = re.compile(rf"\b{re.escape(source)}\b", flags=re.IGNORECASE)
        normalized = pattern.sub(target, normalized)

    words = normalized.split(" ")
    converted_words: list[str] = []

    for word in words:
        converted_words.append(_WORD_REPLACEMENTS.get(word.lower(), word))

    return " ".join(converted_words)