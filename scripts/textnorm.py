#!/usr/bin/env python3
"""Italian text normalization for speech synthesis (macOS `say`).

Shared module: `build_book.py` uses it while composing the book and
`txt2mp3.py` as a last defensive pass before each synthesis.

No external dependencies: standard library only.
"""
from __future__ import annotations

import re
import unicodedata

__all__ = [
    "WPM_DEFAULT",
    "strip_markdown",
    "normalize_for_speech",
    "clean_for_speech",
    "split_sentences",
    "iter_chunks",
    "count_words",
    "estimate_seconds",
    "slugify",
    "acronyms_found",
    "cardinale",
    "ordinale",
]

# Reading speed used for the estimates (words per minute, Italian voice).
WPM_DEFAULT = 170.0

# --------------------------------------------------------------------------
# Symbols: everything a synthesizer would read badly or skip.
# --------------------------------------------------------------------------
_SYMBOLS = (
    ("\u2192", " porta a "),
    ("\u2190", " deriva da "),
    ("\u2194", " corrisponde a "),
    ("\u21d2", " quindi "),
    ("\u2248", " circa "),
    ("\u2245", " circa "),
    ("\u00b1", " piu' o meno "),
    ("\u2264", " minore o uguale a "),
    ("\u2265", " maggiore o uguale a "),
    ("\u2260", " diverso da "),
    ("\u00b0", " gradi "),
    ("\u20ac", " euro "),
    ("\u00a7", " paragrafo "),
    ("\u2191", " "),
    ("\u2193", " "),
    ("\u00b7", " "),
    ("\u2022", " "),
    ("\u25cf", " "),
    ("\u25aa", " "),
    ("&", " e "),
    ("@", " chiocciola "),
    ("+", " piu' "),
    ("=", " uguale a "),
    ("<", " minore di "),
    (">", " maggiore di "),
    ("~", " circa "),
)

# Measurement units preceded by a number: they are read out in full.
_UNITS = (
    (r"(\d+(?:[.,]\d+)?)\s*mm\b", r"\1 millimetri"),
    (r"(\d+(?:[.,]\d+)?)\s*cm\b", r"\1 centimetri"),
    (r"(\d+(?:[.,]\d+)?)\s*km\b", r"\1 chilometri"),
    (r"(\d+(?:[.,]\d+)?)\s*mg\b", r"\1 milligrammi"),
    (r"(\d+(?:[.,]\d+)?)\s*kg\b", r"\1 chilogrammi"),
    (r"(\d+(?:[.,]\d+)?)\s*ml\b", r"\1 millilitri"),
    (r"(\d+(?:[.,]\d+)?)\s*cl\b", r"\1 centilitri"),
    (r"(\d+(?:[.,]\d+)?)\s*dl\b", r"\1 decilitri"),
    (r"(\d+(?:[.,]\d+)?)\s*[Ll]\b", r"\1 litri"),
    (r"(\d+(?:[.,]\d+)?)\s*[Gg]\b", r"\1 grammi"),
    (r"(\d+(?:[.,]\d+)?)\s*%", r"\1 per cento"),
)

# Frequent abbreviations. Order matters: longest forms first.
_ABBREV = (
    (r"\bp\.\s*es\.", "per esempio"),
    (r"\becc\.", "eccetera"),
    (r"\betc\.", "eccetera"),
    (r"\bes\.", "per esempio"),
    (r"\bcfr\.", "confronta"),
    (r"\bca\.", "circa"),
    (r"\bnn\.", "numeri"),
    (r"\bn\.", "numero"),
    (r"\bsec\.", "secolo"),
    (r"\bfigg\.", "figure"),
    (r"\bfig\.", "figura"),
    (r"\btab\.", "tabella"),
    (r"\bart\.", "articolo"),
    (r"\bDott\.", "dottor"),
    (r"\bProf\.", "professor"),
    (r"\bSigg\.", "signori"),
    (r"\bSig\.", "signor"),
)

_ROMAN_ORDINALS = {
    "I": "primo", "II": "secondo", "III": "terzo", "IV": "quarto",
    "V": "quinto", "VI": "sesto", "VII": "settimo", "VIII": "ottavo",
    "IX": "nono", "X": "decimo", "XI": "undicesimo", "XII": "dodicesimo",
    "XIII": "tredicesimo", "XIV": "quattordicesimo", "XV": "quindicesimo",
    "XVI": "sedicesimo", "XVII": "diciassettesimo", "XVIII": "diciottesimo",
    "XIX": "diciannovesimo", "XX": "ventesimo", "XXI": "ventunesimo",
}

_ORDINALS = (
    "primo", "secondo", "terzo", "quarto", "quinto", "sesto", "settimo",
    "ottavo", "nono", "decimo", "undicesimo", "dodicesimo", "tredicesimo",
    "quattordicesimo", "quindicesimo", "sedicesimo", "diciassettesimo",
    "diciottesimo", "diciannovesimo", "ventesimo",
)


def strip_markdown(text: str) -> str:
    """Remove markdown syntax, leaving the heading text intact."""
    t = text
    t = re.sub(r"```.*?```", " ", t, flags=re.S)
    t = re.sub(r"~~~.*?~~~", " ", t, flags=re.S)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)          # images
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)        # links
    t = re.sub(r"</?[a-zA-Z][^>]*>", " ", t)             # html
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.M)  # headings
    t = re.sub(r"\*\*\*([^*]+)\*\*\*", r"\1", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"(?<!\w)\*([^*\n]+)\*(?!\w)", r"\1", t)
    t = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"\1", t)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"^\s{0,3}>\s?", "", t, flags=re.M)       # quotes
    t = re.sub(r"^\s{0,3}[-*+]\s+", "", t, flags=re.M)   # lists
    t = re.sub(r"^\s{0,3}\d+[.)]\s+", "", t, flags=re.M) # numbered lists
    t = re.sub(r"^\s*\|.*\|\s*$", "", t, flags=re.M)     # tables
    t = re.sub(r"^\s*[-=*_]{3,}\s*$", "", t, flags=re.M) # horizontal rules
    t = re.sub(r"\*{2,}", " ", t)
    t = re.sub(r"\\([*_`#\[\]()])", r"\1", t)
    return t


def normalize_for_speech(text: str) -> str:
    """Make text pronounceable: symbols, units, abbreviations, punctuation."""
    t = unicodedata.normalize("NFC", text)

    # Spaces and typographic dashes.
    t = t.replace("\u00a0", " ").replace("\u202f", " ").replace("\u2009", " ")
    t = t.replace("\u2011", "-").replace("\u2012", "-").replace("\u2013", "-")
    t = t.replace("\u2014", "-").replace("\u2015", "-").replace("\u2212", "-")
    t = re.sub(r"\s+-\s+", ", ", t)

    # Typographic quotes and ellipsis.
    for q in ("\u201c", "\u201d", "\u201e", "\u201f", "\u00ab", "\u00bb", "\u2033"):
        t = t.replace(q, '"')
    for a in ("\u2018", "\u2019", "\u201a", "\u2032"):
        t = t.replace(a, "'")
    t = t.replace("\u2026", "...")

    # Symbols.
    for src, dst in _SYMBOLS:
        t = t.replace(src, dst)

    # Numbers with the Italian thousands separator: 1.000 -> 1000.
    t = re.sub(r"(?<=\d)\.(?=\d{3}\b)", "", t)

    # Abbreviations.
    for pat, rep in _ABBREV:
        t = re.sub(pat, rep, t)

    # Units of measurement.
    for pat, rep in _UNITS:
        t = re.sub(pat, rep, t)

    # "secolo XIV" -> "secolo quattordicesimo".
    def _secolo(m: "re.Match[str]") -> str:
        return "secolo " + _ROMAN_ORDINALS.get(m.group(1), m.group(1))

    t = re.sub(r"\bsecolo\s+([IVX]{1,4})\b", _secolo, t)
    # "nervo cranico VII" -> "nervo cranico settimo".
    t = re.sub(
        r"\b(cranico|cervicale|toracico|lombare|sacrale)\s+([IVX]{1,4})\b",
        lambda m: m.group(1) + " " + _ROMAN_ORDINALS.get(m.group(2), m.group(2)),
        t,
    )

    # "1." or "1)" left at the start of a line: nothing to do, already removed above.
    # "3." used as an ordinal mid-line -> "terzo" only if followed by a lowercase letter.
    def _ord(m: "re.Match[str]") -> str:
        n = int(m.group(1))
        if 1 <= n <= len(_ORDINALS):
            return _ORDINALS[n - 1] + " "
        return m.group(0)

    t = re.sub(r"\b(\d{1,2})\s*°\s*(?!C\b)", _ord, t)

    # Repeated punctuation.
    t = re.sub(r",{2,}", ",", t)
    t = re.sub(r";{2,}", ";", t)
    t = re.sub(r":{2,}", ":", t)
    t = re.sub(r"\.{4,}", "...", t)
    t = re.sub(r"([!?])\1{1,}", r"\1", t)

    # Spacing.
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r" +([,;:.!?])", r"\1", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = "\n".join(line.strip() for line in t.split("\n"))
    return t.strip()


def clean_for_speech(text: str) -> str:
    """Full pipeline: markdown out, then normalization for the voice."""
    return normalize_for_speech(strip_markdown(text))


# --------------------------------------------------------------------------
# Segmentation
# --------------------------------------------------------------------------
_SENT_SPLIT = re.compile(r'(?<=[.!?])\s+(?=[("\'\u00ab]?[A-ZÀ-ÖØ-Þ0-9])')


def split_sentences(text: str) -> list:
    """Split the text into sentences, respecting paragraph boundaries."""
    out = []
    for para in re.split(r"\n\s*\n", text.strip()):
        para = " ".join(para.split())
        if not para:
            continue
        pieces = _SENT_SPLIT.split(para)
        for i, piece in enumerate(pieces):
            piece = piece.strip()
            if not piece:
                continue
            out.append({"text": piece, "para_end": i == len(pieces) - 1})
    return out


def _split_hard(sentence: str, max_chars: int) -> list:
    """Break an overlong sentence on commas or, as a last resort, on words."""
    out, cur = [], ""
    for piece in re.split(r"(?<=[,;:])\s+", sentence):
        if cur and len(cur) + len(piece) + 1 > max_chars:
            out.append(cur.strip())
            cur = piece
        elif len(piece) > max_chars:
            words, buf = piece.split(), cur
            for w in words:
                if buf and len(buf) + len(w) + 1 > max_chars:
                    out.append(buf.strip())
                    buf = w
                else:
                    buf = (buf + " " + w).strip()
            cur = buf
        else:
            cur = (cur + " " + piece).strip() if cur else piece
    if cur.strip():
        out.append(cur.strip())
    return out


def iter_chunks(text: str, max_chars: int = 700) -> list:
    """Group sentences into blocks to synthesize, <= max_chars characters.

    Returns a list of dictionaries {"text", "para_end"}.
    """
    chunks = []
    cur = ""
    cur_end = False
    for sent in split_sentences(text):
        for piece in ([sent["text"]] if len(sent["text"]) <= max_chars
                      else _split_hard(sent["text"], max_chars)):
            if cur and len(cur) + len(piece) + 1 > max_chars:
                chunks.append({"text": cur, "para_end": cur_end})
                cur, cur_end = piece, sent["para_end"]
            else:
                cur = (cur + " " + piece).strip() if cur else piece
                cur_end = sent["para_end"]
    if cur:
        chunks.append({"text": cur, "para_end": cur_end})
    return chunks


# --------------------------------------------------------------------------
# Utilities
# --------------------------------------------------------------------------
_WORD_RE = re.compile(r"[0-9A-Za-zÀ-ÖØ-öø-ÿ']+")


def count_words(text: str) -> int:
    return len(_WORD_RE.findall(text))


def estimate_seconds(words: int, wpm: float = WPM_DEFAULT) -> float:
    return words / wpm * 60.0


def slugify(text: str, maxlen: int = 48) -> str:
    t = unicodedata.normalize("NFKD", text)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:maxlen].strip("-") or "capitolo"


_ACRONYM_RE = re.compile(r"\b([A-ZÀ-Ö]{2,6})\b")


# --------------------------------------------------------------------------
# Numbers in words (for the spoken table of contents)
# --------------------------------------------------------------------------
_CARD_U = {1: "uno", 2: "due", 3: "tre", 4: "quattro", 5: "cinque",
           6: "sei", 7: "sette", 8: "otto", 9: "nove"}
_CARD_T = {10: "dieci", 11: "undici", 12: "dodici", 13: "tredici",
           14: "quattordici", 15: "quindici", 16: "sedici",
           17: "diciassette", 18: "diciotto", 19: "diciannove"}
_CARD_D = {20: "venti", 30: "trenta", 40: "quaranta", 50: "cinquanta",
           60: "sessanta", 70: "settanta", 80: "ottanta", 90: "novanta"}
_ORD_U = {1: "primo", 2: "secondo", 3: "terzo", 4: "quarto", 5: "quinto",
          6: "sesto", 7: "settimo", 8: "ottavo", 9: "nono", 10: "decimo"}


def cardinale(n: int) -> str:
    """Italian cardinal in words, from 1 to 99."""
    if n in _CARD_U:
        return _CARD_U[n]
    if n in _CARD_T:
        return _CARD_T[n]
    if n in _CARD_D:
        return _CARD_D[n]
    decina, unita = divmod(n, 10)
    testa = _CARD_D[decina * 10]
    parola = _CARD_U[unita]
    if parola in ("uno", "otto"):
        return testa[:-1] + parola
    if parola == "tre":
        return testa + "tr\u00e9"
    return testa + parola


def ordinale(n: int) -> str:
    """Italian ordinal in words (ventunesimo, cinquantaquattresimo...)."""
    if n in _ORD_U:
        return _ORD_U[n]
    return cardinale(n)[:-1] + "esimo"


def acronyms_found(text: str) -> list:
    """List the residual uppercase acronyms, for quality control."""
    skip = {"RIASSUNZIONE", "NOTA", "ITALIA", "ROMA", "II", "III", "IV", "IX", "XI",
            "AB"}  # AB: blood group, read out letter by letter
    found = []
    for m in _ACRONYM_RE.finditer(text):
        tok = m.group(1)
        if tok in skip or tok in _ROMAN_ORDINALS:
            continue
        if tok not in found:
            found.append(tok)
    return found
