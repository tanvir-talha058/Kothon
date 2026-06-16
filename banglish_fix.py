from __future__ import annotations

import re

# ── Multi-word phrase → Bangla ────────────────────────────────────────────────
_PHRASE_REPLACEMENTS: dict[str, str] = {
    "assalamu alaikum": "আসসালামু আলাইকুম",
    "walaikum assalam": "ওয়ালাইকুম আসসালাম",
    "walaikum salam": "ওয়ালাইকুম আসসালাম",
    "in sha allah": "ইনশাআল্লাহ",
    "inshallah": "ইনশাআল্লাহ",
    "alhamdulillah": "আলহামদুলিল্লাহ",
    "allahu akbar": "আল্লাহু আকবার",
    "subhanallah": "সুবহানআল্লাহ",
    "mashallah": "মাশাআল্লাহ",
    "bismillah": "বিসমিল্লাহ",
    "khuda hafez": "খোদা হাফেজ",
    "khoda hafez": "খোদা হাফেজ",
    "thik ache": "ঠিক আছে",
    "thik achi": "ঠিক আছি",
    "thik acho": "ঠিক আছো",
    "ki holo": "কি হলো",
    "ki korcho": "কি করছো",
    "ki korben": "কি করবেন",
    "ki korbe": "কি করবে",
    "ki korbi": "কি করবি",
    "bhalo achi": "ভালো আছি",
    "bhalo acho": "ভালো আছো",
    "bhalo achen": "ভালো আছেন",
    "valo achi": "ভালো আছি",
    "kemon acho": "কেমন আছো",
    "kemon achen": "কেমন আছেন",
    "kemon achi": "কেমন আছি",
    "apni kemon achen": "আপনি কেমন আছেন",
    "ami bhalo achi": "আমি ভালো আছি",
}

# ── Spoken punctuation → symbol ───────────────────────────────────────────────
_PUNCTUATION_COMMANDS: dict[str, str] = {
    "full stop": ".",
    "period": ".",
    "comma": ",",
    "question mark": "?",
    "exclamation mark": "!",
    "exclamation point": "!",
    "new line": "\n",
    "new paragraph": "\n\n",
    "semicolon": ";",
    "colon": ":",
    "open bracket": "(",
    "close bracket": ")",
    "open parenthesis": "(",
    "close parenthesis": ")",
    "dash": " — ",
    "hyphen": "-",
    "ellipsis": "...",
    "dot dot dot": "...",
}

# ── Single Banglish word → Bangla ─────────────────────────────────────────────
_WORD_REPLACEMENTS: dict[str, str] = {
    # — Pronouns —
    "ami": "আমি",
    "amra": "আমরা",
    "tumi": "তুমি",
    "apni": "আপনি",
    "se": "সে",
    "tini": "তিনি",
    "ora": "ওরা",
    "tara": "তারা",
    "amar": "আমার",
    "tomar": "তোমার",
    "apnar": "আপনার",
    "tar": "তার",
    "tader": "তাদের",
    "amader": "আমাদের",
    "tomader": "তোমাদের",
    "apnader": "আপনাদের",

    # — To be / existence —
    "achi": "আছি",
    "acho": "আছো",
    "achen": "আছেন",
    "ache": "আছে",
    "chilo": "ছিলো",
    "chilam": "ছিলাম",
    "chilen": "ছিলেন",

    # — Common verbs —
    "asi": "আসি",
    "aschi": "আসছি",
    "asbo": "আসবো",
    "elo": "এলো",
    "elam": "এলাম",
    "jabo": "যাবো",
    "jachhi": "যাচ্ছি",
    "jacchi": "যাচ্ছি",
    "gelam": "গেলাম",
    "gelo": "গেলো",
    "chai": "চাই",
    "chao": "চাও",
    "lagbe": "লাগবে",
    "lagche": "লাগছে",
    "hobe": "হবে",
    "hoyeche": "হয়েছে",
    "hoye": "হয়ে",
    "holo": "হলো",
    "holam": "হলাম",
    "korchi": "করছি",
    "korcho": "করছো",
    "korben": "করবেন",
    "korbo": "করবো",
    "korechi": "করেছি",
    "korecho": "করেছো",
    "kori": "করি",
    "koro": "করো",
    "bolo": "বলো",
    "bolchi": "বলছি",
    "bolbo": "বলবো",
    "bolechi": "বলেছি",
    "dekho": "দেখো",
    "dekchi": "দেখছি",
    "dekhbo": "দেখবো",
    "shono": "শোনো",
    "shunchi": "শুনছি",
    "jano": "জানো",
    "jani": "জানি",
    "janbo": "জানবো",
    "bujhchi": "বুঝছি",
    "bujhi": "বুঝি",
    "bujhbo": "বুঝবো",
    "khao": "খাও",
    "khacchi": "খাচ্ছি",
    "khabo": "খাবো",
    "khechi": "খেয়েছি",
    "paro": "পারো",
    "pari": "পারি",
    "parbo": "পারবো",
    "dao": "দাও",
    "debo": "দেবো",
    "dechi": "দিয়েছি",
    "nao": "নাও",
    "nebo": "নেবো",
    "rao": "রাখো",
    "rakho": "রাখো",
    "rekho": "রেখো",
    "thako": "থাকো",
    "thaki": "থাকি",
    "thakbo": "থাকবো",
    "patro": "পাত্র",
    "pao": "পাও",
    "pai": "পাই",
    "pabo": "পাবো",

    # — Adjectives / adverbs —
    "bhalo": "ভালো",
    "valo": "ভালো",
    "manda": "মন্দ",
    "kharap": "খারাপ",
    "boro": "বড়",
    "choto": "ছোট",
    "lamba": "লম্বা",
    "shundor": "সুন্দর",
    "sundor": "সুন্দর",
    "onek": "অনেক",
    "ektu": "একটু",
    "shob": "সব",
    "sob": "সব",
    "aro": "আরো",
    "khub": "খুব",
    "beshi": "বেশি",
    "kom": "কম",
    "thik": "ঠিক",
    "daroon": "দারুণ",
    "oshhadharon": "অসাধারণ",
    "shoja": "সহজ",
    "kothin": "কঠিন",
    "duto": "দুটো",
    "tinta": "তিনটা",
    "ekta": "একটা",

    # — Nouns / people —
    "bhai": "ভাই",
    "apa": "আপা",
    "apu": "আপু",
    "chacha": "চাচা",
    "mama": "মামা",
    "maa": "মা",
    "baba": "বাবা",
    "dada": "দাদা",
    "dadi": "দাদি",
    "nana": "নানা",
    "nani": "নানি",
    "dost": "দোস্ত",
    "bondhu": "বন্ধু",
    "manush": "মানুষ",
    "chelে": "ছেলে",
    "chele": "ছেলে",
    "meye": "মেয়ে",
    "baccha": "বাচ্চা",
    "shontan": "সন্তান",

    # — Food / drink —
    "khabar": "খাবার",
    "pani": "পানি",
    "jol": "জল",
    "ruti": "রুটি",
    "bhat": "ভাত",
    "daal": "ডাল",
    "dal": "ডাল",
    "tarkari": "তরকারি",
    "mach": "মাছ",
    "mangsho": "মাংস",
    "dim": "ডিম",
    "dudh": "দুধ",
    "cha": "চা",
    "mishti": "মিষ্টি",
    "fol": "ফল",

    # — Time —
    "kal": "কাল",
    "aaj": "আজ",
    "aj": "আজ",
    "raat": "রাত",
    "din": "দিন",
    "shokaal": "সকাল",
    "shokal": "সকাল",
    "bikal": "বিকেল",
    "dupurer": "দুপুরের",
    "dupure": "দুপুরে",
    "shondha": "সন্ধ্যা",
    "ekhon": "এখন",
    "pore": "পরে",
    "age": "আগে",
    "shomoy": "সময়",

    # — Questions / connectors —
    "ki": "কি",
    "keno": "কেনো",
    "kothay": "কোথায়",
    "kothai": "কোথায়",
    "kokhon": "কখন",
    "kemon": "কেমন",
    "koto": "কতো",
    "ke": "কে",
    "kintu": "কিন্তু",
    "tahole": "তাহলে",
    "ebong": "এবং",
    "othoba": "অথবা",
    "ba": "বা",
    "na": "না",
    "haa": "হ্যাঁ",
    "ha": "হ্যাঁ",
    "ji": "জি",
    "tobe": "তবে",
    "jodi": "যদি",
    "tobuo": "তবুও",
    "tai": "তাই",
    "karon": "কারণ",

    # — Demonstratives / location —
    "eta": "এটা",
    "eita": "এইটা",
    "ota": "ওটা",
    "oita": "ওইটা",
    "ei": "এই",
    "oi": "ওই",
    "ekhane": "এখানে",
    "okhane": "ওখানে",
    "shekhane": "সেখানে",
    "upore": "উপরে",
    "niche": "নিচে",
    "shামনে": "সামনে",
    "shamne": "সামনে",
    "pechone": "পেছনে",

    # — Greetings / expressions —
    "dhonnobad": "ধন্যবাদ",
    "shukriya": "শুকরিয়া",
    "maaf": "মাফ",
    "shala": "শালা",
    "arre": "আরে",
    "uff": "উফ",
    "oho": "ওহো",
    "hm": "হুম",
    "hmm": "হুম",
    "plz": "প্লিজ",
    "pls": "প্লিজ",
    "ok": "ওকে",
    "okay": "ওকে",
}

_TOKEN_RE = re.compile(r"[A-Za-z']+|[^A-Za-z']+")


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


def normalize_text(text: str, is_partial: bool = False) -> str:
    normalized = _normalize_whitespace(text)
    if not normalized:
        return ""

    if not is_partial:
        # Punctuation commands — only on complete segments
        for cmd, symbol in _PUNCTUATION_COMMANDS.items():
            pattern = re.compile(rf"\b{re.escape(cmd)}\b", flags=re.IGNORECASE)
            normalized = pattern.sub(symbol, normalized)

        # Multi-word phrase replacements — only on complete segments
        for source, target in _PHRASE_REPLACEMENTS.items():
            pattern = re.compile(rf"\b{re.escape(source)}\b", flags=re.IGNORECASE)
            normalized = pattern.sub(target, normalized)

    # Single-word replacements — always apply
    tokens = _TOKEN_RE.findall(normalized)
    result: list[str] = []
    for token in tokens:
        if not re.fullmatch(r"[A-Za-z']+", token):
            result.append(token)
            continue
        replacement = _WORD_REPLACEMENTS.get(token.lower())
        result.append(replacement if replacement is not None else token)

    return "".join(result).strip()
