from __future__ import annotations

import re

_PHRASE_REPLACEMENTS: dict[str, str] = {
    "assalamu alaikum": "আসসালামু আলাইকুম",
    "walaikum assalam": "ওয়ালাইকুম আসসালাম",
    "in sha allah": "ইনশাআল্লাহ",
    "alhamdulillah": "আলহামদুলিল্লাহ",
}

_WORD_REPLACEMENTS: dict[str, str] = {
    "ami": "আমি",
    "amra": "আমরা",
    "tumi": "তুমি",
    "apni": "আপনি",
    "amar": "আমার",
    "tomar": "তোমার",
    "apnar": "আপনার",
    "bhalo": "ভালো",
    "valo": "ভালো",
    "kemon": "কেমন",
    "na": "না",
    "ki": "কি",
    "kintu": "কিন্তু",
    "eta": "এটা",
    "eita": "এইটা",
    "ota": "ওটা",
    "oita": "ওইটা",
    "jabo": "যাবো",
    "jachhi": "যাচ্ছি",
    "asi": "আসি",
    "achi": "আছি",
    "chai": "চাই",
    "lagbe": "লাগবে",
    "hobe": "হবে",
    "dhonnobad": "ধন্যবাদ",
    "plz": "please",
    "pls": "please",
}

_TOKEN_RE = re.compile(r"[A-Za-z']+|[^A-Za-z']+")


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


def normalize_text(text: str) -> str:
    normalized = _normalize_whitespace(text)
    if not normalized:
        return ""

    for source, target in _PHRASE_REPLACEMENTS.items():
        pattern = re.compile(rf"\b{re.escape(source)}\b", flags=re.IGNORECASE)
        normalized = pattern.sub(target, normalized)

    tokens = _TOKEN_RE.findall(normalized)
    converted_tokens: list[str] = []

    for token in tokens:
        if not re.fullmatch(r"[A-Za-z']+", token):
            converted_tokens.append(token)
            continue

        replacement = _WORD_REPLACEMENTS.get(token.lower())
        converted_tokens.append(replacement if replacement is not None else token)

    return "".join(converted_tokens).strip()
