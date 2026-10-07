#!/usr/bin/env python3
"""English text normalization for speech synthesis (macOS `say`).

Mirror of `textnorm.py` for English prose: same exported names, English rules.
Used by `build_book_en.py` while composing the book and by `txt2mp3.py` (with
`--lang en`) as a last defensive pass before each synthesis.

The style contract asks writers to avoid these traps, so this module is the
safety net: the things a voice mangles are rewritten here even if a writer
lets one through.

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

# Reading speed used for estimates (words per minute, English voice).
WPM_DEFAULT = 170.0

# ---------------------------------------------------------------------------
# Symbols: anything a synthesizer would read badly or skip.
# ---------------------------------------------------------------------------
_SYMBOLS = (
    ("\u2192", " leads to "),
    ("\u2190", " comes from "),
    ("\u2194", " corresponds to "),
    ("\u21d2", " therefore "),
    ("\u2248", " approximately "),
    ("\u2245", " approximately "),
    ("\u00b1", " plus or minus "),
    ("\u2264", " at most "),
    ("\u2265", " at least "),
    ("\u2260", " is not equal to "),
    ("\u00b0", " degrees "),
    ("\u00a7", " section "),
    ("\u2191", " "),
    ("\u2193", " "),
    ("\u00b7", " "),
    ("\u2022", " "),
    ("\u25cf", " "),
    ("\u25aa", " "),
    ("&", " and "),
    ("@", " at "),
    ("+", " plus "),
    ("=", " equals "),
    ("<", " less than "),
    (">", " greater than "),
    ("~", " approximately "),
)

# Measurement units preceded by a number: spoken in full. Order matters,
# longest first.
_UNITS = (
    (r"(\d+(?:\.\d+)?)\s*mg/kg/day\b", r"\1 milligrams per kilogram per day"),
    (r"(\d+(?:\.\d+)?)\s*mg/kg\b", r"\1 milligrams per kilogram"),
    (r"(\d+(?:\.\d+)?)\s*mcg/kg\b", r"\1 micrograms per kilogram"),
    (r"(\d+(?:\.\d+)?)\s*mL/kg\b", r"\1 milliliters per kilogram"),
    (r"(\d+(?:\.\d+)?)\s*mg/dL\b", r"\1 milligrams per deciliter"),
    (r"(\d+(?:\.\d+)?)\s*g/dL\b", r"\1 grams per deciliter"),
    (r"(\d+(?:\.\d+)?)\s*mmol/L\b", r"\1 millimoles per liter"),
    (r"(\d+(?:\.\d+)?)\s*IU/mL\b", r"\1 international units per milliliter"),
    (r"(\d+(?:\.\d+)?)\s*mmHg\b", r"\1 millimeters of mercury"),
    (r"(\d+(?:\.\d+)?)\s*mmol\b", r"\1 millimoles"),
    (r"(\d+(?:\.\d+)?)\s*milligrams\b", r"\1 milligrams"),
    (r"(\d+(?:\.\d+)?)\s*mg\b", r"\1 milligrams"),
    (r"(\d+(?:\.\d+)?)\s*mcg\b", r"\1 micrograms"),
    (r"(\d+(?:\.\d+)?)\s*[\u00b5u]g\b", r"\1 micrograms"),
    (r"(\d+(?:\.\d+)?)\s*kg\b", r"\1 kilograms"),
    (r"(\d+(?:\.\d+)?)\s*mL\b", r"\1 milliliters"),
    (r"(\d+(?:\.\d+)?)\s*ml\b", r"\1 milliliters"),
    (r"(\d+(?:\.\d+)?)\s*dL\b", r"\1 deciliters"),
    (r"(\d+(?:\.\d+)?)\s*cm\b", r"\1 centimeters"),
    (r"(\d+(?:\.\d+)?)\s*mm\b", r"\1 millimeters"),
    (r"(\d+(?:\.\d+)?)\s*km\b", r"\1 kilometers"),
    (r"(\d+(?:\.\d+)?)\s*IU\b", r"\1 international units"),
    (r"(\d+(?:\.\d+)?)\s*[Ll]\b", r"\1 liters"),
    (r"(\d+(?:\.\d+)?)\s*[Gg]\b", r"\1 grams"),
    (r"(\d+(?:\.\d+)?)\s*%", r"\1 per cent"),
)

# Temperature notation kept together: "38.5 degrees Celsius".
_TEMPERATURE = (
    (r"(\d+(?:\.\d+)?)\s*degrees\s*C\b", r"\1 degrees Celsius"),
    (r"(\d+(?:\.\d+)?)\s*degrees\s*F\b", r"\1 degrees Fahrenheit"),
    (r"(\d+(?:\.\d+)?)\s*\u00b0C\b", r"\1 degrees Celsius"),
    (r"(\d+(?:\.\d+)?)\s*\u00b0F\b", r"\1 degrees Fahrenheit"),
)

# Abbreviations a writer should not use, expanded as a safety net.
_ABBREV = (
    (r"\be\.g\.", "for example"),
    (r"\bi\.e\.", "that is"),
    (r"\betc\.", "and so on"),
    (r"\bapprox\.", "approximately"),
    (r"\bvs\.", "versus"),
    (r"\bDr\.", "Doctor"),
    (r"\bProf\.", "Professor"),
    (r"\bSt\.", "Saint"),
    (r"\bFig\.", "figure"),
    (r"\bTab\.", "table"),
    (r"\bNo\.", "number"),
)

# Dose frequency shorthand that must never reach the voice.
_FREQ = (
    (r"\bq4h\b", "every four hours"),
    (r"\bq6h\b", "every six hours"),
    (r"\bq8h\b", "every eight hours"),
    (r"\bq12h\b", "every twelve hours"),
    (r"\bq24h\b", "every twenty-four hours"),
    (r"\bb\.i\.d\.", "twice a day"),
    (r"\bt\.i\.d\.", "three times a day"),
    (r"\bq\.i\.d\.", "four times a day"),
    (r"\bBID\b", "twice a day"),
    (r"\bTID\b", "three times a day"),
    (r"\bQID\b", "four times a day"),
    (r"\bPO\b", "by mouth"),
)

# Acronyms the voice mangles: WHO becomes "who", DALY becomes "Daly",
# IRIS becomes the name "Iris", and so on. Expanded before synthesis.
# "the the" is avoided by handling "the WHO" first.
_ACRONYM_TRAPS = (
    (r"\bthe WHO\b", "the World Health Organization"),
    (r"\bWHO\b", "the World Health Organization"),
    (r"\bWASH\b", "water, sanitation and hygiene"),
    (r"\bDALYs\b", "disability-adjusted life years"),
    (r"\bDALY\b", "disability-adjusted life year"),
    (r"\bIRIS\b", "immune reconstitution inflammatory syndrome"),
    (r"\bMDR-TB\b", "multidrug-resistant tuberculosis"),
    (r"\bXDR-TB\b", "extensively drug-resistant tuberculosis"),
    (r"\bTB\b", "tuberculosis"),
    (r"\bPPE\b", "personal protective equipment"),
    (r"\bORS\b", "oral rehydration salts"),
    (r"\bLLINs\b", "insecticide-treated bed nets"),
    (r"\bLLIN\b", "insecticide-treated bed net"),
    (r"\bITNs\b", "insecticide-treated bed nets"),
    (r"\bITN\b", "insecticide-treated bed net"),
    (r"\bIRS\b", "indoor residual spraying"),
    (r"\bRDTs\b", "rapid diagnostic tests"),
    (r"\bRDT\b", "rapid diagnostic test"),
    (r"\bACTs\b", "artemisinin-based combination therapies"),
    (r"\bACT\b", "artemisinin-based combination therapy"),
    (r"\bMDA\b", "mass drug administration"),
    (r"\bART\b", "antiretroviral therapy"),
    (r"\bVHFs\b", "viral hemorrhagic fevers"),
    (r"\bVHF\b", "viral hemorrhagic fever"),
    (r"\bICU\b", "intensive care unit"),
    (r"\bNTDs\b", "neglected tropical diseases"),
    (r"\bNTD\b", "neglected tropical disease"),
    (r"\bRTS,S\b", "R T S S"),
    (r"\bIM\b", "intramuscularly"),
    (r"\bIV\b", "intravenously"),
)

_ROMAN_ORDINALS = {
    "I": "first", "II": "second", "III": "third", "IV": "fourth",
    "V": "fifth", "VI": "sixth", "VII": "seventh", "VIII": "eighth",
    "IX": "ninth", "X": "tenth", "XI": "eleventh", "XII": "twelfth",
    "XIII": "thirteenth", "XIV": "fourteenth", "XV": "fifteenth",
    "XVI": "sixteenth", "XVII": "seventeenth", "XVIII": "eighteenth",
    "XIX": "nineteenth", "XX": "twentieth", "XXI": "twenty-first",
}

_ORDINALS = (
    "first", "second", "third", "fourth", "fifth", "sixth", "seventh",
    "eighth", "ninth", "tenth", "eleventh", "twelfth", "thirteenth",
    "fourteenth", "fifteenth", "sixteenth", "seventeenth", "eighteenth",
    "nineteenth", "twentieth",
)


def strip_markdown(text: str) -> str:
    """Remove markdown syntax, leaving heading text intact."""
    t = text
    t = re.sub(r"```.*?```", " ", t, flags=re.S)
    t = re.sub(r"~~~.*?~~~", " ", t, flags=re.S)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)          # images
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)        # links
    t = re.sub(r"</?[a-zA-Z][^>]*>", " ", t)              # html
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.M)   # headings
    t = re.sub(r"\*\*\*([^*]+)\*\*\*", r"\1", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"(?<!\w)\*([^*\n]+)\*(?!\w)", r"\1", t)
    t = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"\1", t)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"^\s{0,3}>\s?", "", t, flags=re.M)        # quotes
    t = re.sub(r"^\s{0,3}[-*+]\s+", "", t, flags=re.M)    # bullet lists
    t = re.sub(r"^\s{0,3}\d+[.)]\s+", "", t, flags=re.M)  # numbered lists
    t = re.sub(r"^\s*\|.*\|\s*$", "", t, flags=re.M)      # tables
    t = re.sub(r"^\s*[-=*_]{3,}\s*$", "", t, flags=re.M)  # rules
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

    # Thousands separator: 1,000 -> 1000 (the voice reads it correctly).
    t = re.sub(r"(?<=\d),(?=\d{3}\b)", "", t)

    # Number ranges written with a dash: 20-25 -> 20 to 25.
    t = re.sub(r"\b(\d+)-(\d+)\b", r"\1 to \2", t)

    # Abbreviations and dose shorthand.
    for pat, rep in _ABBREV:
        t = re.sub(pat, rep, t)
    for pat, rep in _FREQ:
        t = re.sub(pat, rep, t)

    # Acronyms the voice mangles.
    for pat, rep in _ACRONYM_TRAPS:
        t = re.sub(pat, rep, t)

    # Units of measurement.
    for pat, rep in _UNITS:
        t = re.sub(pat, rep, t)
    for pat, rep in _TEMPERATURE:
        t = re.sub(pat, rep, t)

    # "the nineteenth century" from roman numerals, just in case.
    def _century(m: "re.Match[str]") -> str:
        return "the " + _ROMAN_ORDINALS.get(m.group(1), m.group(1)) + " century"

    t = re.sub(r"\bthe\s+([IVX]{1,4})\s+century\b", _century, t)

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
    """Full pipeline: markdown out, then speech normalization."""
    return normalize_for_speech(strip_markdown(text))


# ---------------------------------------------------------------------------
# Segmentation
# ---------------------------------------------------------------------------
_SENT_SPLIT = re.compile(r'(?<=[.!?])\s+(?=[("\'?A-Z0-9])')


def split_sentences(text: str) -> list:
    """Split text into sentences, respecting paragraph boundaries."""
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
    """Group sentences into synthesis blocks of at most max_chars characters.

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


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
_WORD_RE = re.compile(r"[0-9A-Za-z\u00c0-\u00ff']+")


def count_words(text: str) -> int:
    return len(_WORD_RE.findall(text))


def estimate_seconds(words: int, wpm: float = WPM_DEFAULT) -> float:
    return words / wpm * 60.0


def slugify(text: str, maxlen: int = 48) -> str:
    t = unicodedata.normalize("NFKD", text)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:maxlen].strip("-") or "chapter"


_ACRONYM_RE = re.compile(r"\b([A-Z]{2,6})\b")

# Acronyms the style contract allows, because the voice reads them as
# letters and they are unambiguous in English.
_ALLOWED_ACRONYMS = {
    "HIV", "AIDS", "PCR", "BCG", "CDC", "ECDC", "DNA", "RNA", "RTS",
    "II", "III", "IV", "IX", "XI", "XXI",
}


def acronyms_found(text: str, extra: tuple = ()) -> list:
    """List residual uppercase acronyms, for quality control.

    `extra` names short forms that the book in question tolerates, on top of
    the ones the style contract allows everywhere.
    """
    allowed = _ALLOWED_ACRONYMS | {a.upper() for a in extra}
    found = []
    for m in _ACRONYM_RE.finditer(text):
        tok = m.group(1)
        if tok in allowed or tok in _ROMAN_ORDINALS:
            continue
        if tok not in found:
            found.append(tok)
    return found


# ---------------------------------------------------------------------------
# Numbers in words (for the spoken table of contents)
# ---------------------------------------------------------------------------
_CARD_U = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
           6: "six", 7: "seven", 8: "eight", 9: "nine"}
_CARD_T = {10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen",
           14: "fourteen", 15: "fifteen", 16: "sixteen",
           17: "seventeen", 18: "eighteen", 19: "nineteen"}
_CARD_D = {20: "twenty", 30: "thirty", 40: "forty", 50: "fifty",
           60: "sixty", 70: "seventy", 80: "eighty", 90: "ninety"}
_ORD_U = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth",
          6: "sixth", 7: "seventh", 8: "eighth", 9: "ninth", 10: "tenth",
          11: "eleventh", 12: "twelfth"}


def cardinale(n: int) -> str:
    """English cardinal in words, 0 to 999."""
    if n == 0:
        return "zero"
    if n >= 100:
        # Chapters of a long book pass 99: "one hundred nine", not a crash.
        centinaia, resto = divmod(n, 100)
        base = cardinale(centinaia) + " hundred"
        return base if resto == 0 else base + " " + cardinale(resto)
    if n in _CARD_U:
        return _CARD_U[n]
    if n in _CARD_T:
        return _CARD_T[n]
    tens, unit = divmod(n, 10)
    if unit == 0:
        return _CARD_D[tens * 10]
    return _CARD_D[tens * 10] + "-" + _CARD_U[unit]


def ordinale(n: int) -> str:
    """English ordinal in words (thirteenth, twentieth, twenty-first...)."""
    if n in _ORD_U:
        return _ORD_U[n]
    if 13 <= n <= 19:
        return cardinale(n) + "th"
    tens, unit = divmod(n, 10)
    if unit == 0:
        base = _CARD_D[tens * 10]          # twenty -> twentieth
        return base[:-1] + "ieth"
    unit_ord = {1: "first", 2: "second", 3: "third", 4: "fourth",
                5: "fifth", 6: "sixth", 7: "seventh", 8: "eighth",
                9: "ninth"}
    return _CARD_D[tens * 10] + "-" + unit_ord[unit]