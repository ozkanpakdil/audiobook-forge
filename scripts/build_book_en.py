#!/usr/bin/env python3
"""build_book_en.py — assembles an English course into one speech-ready text.

Reads the sections from a book's content/capitoli/*.md, checks each against the style
contract in that book's content/PLAN.md, orders them, and joins them into
out/<slug>.txt with front matter and a spoken table of contents. Prints word,
character and byte counts, the estimated audio duration, and the distance to the
1 MB target.

Every book lives in books/<slug>/ with the same shape, and the launchers read
books/books.tsv to find it, so in practice this script is called with explicit
--capitoli/--out/--indice paths. The defaults below build the tropical medicine
book, the one this script started life on.

Examples:
    python3 scripts/build_book_en.py
    python3 scripts/build_book_en.py --stats
    python3 scripts/build_book_en.py --strict --acronyms-ok CT,MRI,ECG
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from textnorm_en import (  # noqa: E402
    WPM_DEFAULT,
    acronyms_found,
    cardinale,
    clean_for_speech,
    count_words,
    estimate_seconds,
)

OBIETTIVO_BYTE = 1_048_576  # 1 MB (binary)
PAROLE_MIN_CAPITOLO, PAROLE_MAX = 3200, 7500
PAROLE_MIN_APPENDICE = 1800  # appendices are briefed shorter than chapters

FRONT_MATTER = """# Tropical Medicine for the Advanced Practice Nurse — A Narrated Course

This course accompanies the listener through the diseases of the tropics and the practice of medicine where resources are few: how the diseases are transmitted, how they present at the bedside, how they are diagnosed and treated, and how the advanced practice nurse works with them far from a referral hospital. It is written to be listened to rather than read, and every chapter builds on the ones before it.

The sixty-five chapters move from the foundations of the field to the clinical approach, through the vector-borne diseases, the worms and protozoa, the bacterial, viral and fungal infections, and the special populations they strike; then through prevention, public health, and professional practice; and on into the skills that remote practice demands, from emergency obstetrics to point-of-care ultrasound, the decisions a clinician must make without diagnostics, the logistics of drugs, power and communication, and finally the nurse's own safety, health and limits. Four appendices follow: a drug formulary, the incubation periods, a set of case studies, and a glossary with the key guidelines.

A word about the doses you will hear. The regimens spoken in this course reflect the guidance of the World Health Organization, the Centers for Disease Control and Prevention, and the European Centre for Disease Prevention and Control as it stood when the course was written. That guidance is revised, it differs between countries, and a synthesized voice is a poor place to look up a dose. Before you prescribe anything you hear here, verify the current guideline and your local protocol. This course teaches the reasoning; the guideline holds the number.

This course is educational. It does not replace clinical judgment, local protocols, or the advice of a supervising physician, and it is not a formulary. What it offers is the working knowledge that lets an advanced practice nurse recognize, stabilize, and care for patients whose diseases are most at home in the tropics, and to keep doing it safely at the end of a bad road.
"""


def indice_parlato(capitoli, sostantivo: str = "course"):
    """Builds the table of contents to be read aloud, as prose."""
    n_capitoli = sum(1 for c in capitoli if c["tipo"] == "chapter")
    n_appendici = sum(1 for c in capitoli if c["tipo"] == "appendix")
    # A book still being written may have no appendices: the sentence must not
    # end up saying "and zero appendices".
    if n_appendici:
        frase = (f"The {sostantivo} comprises {cardinale(n_capitoli)} chapters and "
                 f"{cardinale(n_appendici)} appendices. Here they are, in listening order.")
    else:
        frase = (f"The {sostantivo} comprises {cardinale(n_capitoli)} chapters. "
                 "Here they are, in listening order.")
    lines = [
        "# Table of Contents",
        "",
        frase,
        "",
    ]
    blocchi = []
    for cap in capitoli:
        titolo = cap["titolo"]
        if cap["tipo"] == "chapter":
            m = re.match(r"^Chapter\s+\d+\s*[-—–]\s*(.+)$", titolo)
            testo = m.group(1) if m else titolo
            blocchi.append(f"Chapter {cardinale(cap['n'])}. {testo}.")
        else:
            m = re.match(r"^Appendix\s+([A-Z])\s*[-—–]\s*(.+)$", titolo)
            testo = m.group(2) if m else titolo
            blocchi.append(f"Appendix {cap['lettera']}. {testo}.")
    # One sentence per four entries, so the list stays listenable.
    for i in range(0, len(blocchi), 4):
        lines.append(" ".join(blocchi[i:i + 4]))
        lines.append("")
    return "\n".join(lines).strip() + "\n"


REGOLE = (
    (r"\*\*|__|`", "residual markdown (bold or code)"),
    (r"^\s{0,3}#{2,}", "level two or deeper heading"),
    (r"^\s{0,3}[-*+]\s+\S", "bullet list"),
    (r"^\s{0,3}\d+[.)]\s+\S", "numbered list"),
    (r"\|", "table"),
    (r"https?://|www\.", "web address"),
    (r"[%&=\u2192\u2190\u00b0\u00a9\u00ae\u2122\u2265\u2264\u00b1\u00d7]",
     "unpronounceable symbol"),
    (r"\[\d+\]|\(\d{4}\)", "note or citation marker"),
    (r"\d+\s*(?:cm|mm|kg|km|ml|mg|mcg|\u00b5g|g|IU)\b", "unit not spelled out"),
    (r"\bmg/kg\b|\bmcg/kg\b|\bmL/kg\b|\bmg/kg/day\b", "unit ratio not spelled out"),
    (r"\bfig(?:ure)?\.?\s*\d+|\btab(?:le)?\.?\s*\d+", "figure or table reference"),
    (r"\bq\d+h\b|\bb\.i\.d\.\b|\bt\.i\.d\.\b|\bq\.i\.d\.\b",
     "abbreviated dose frequency"),
    (r"\b(?:IV|IM|PO)\b", "abbreviated route of administration"),
)

# Short forms a voice mangles into ordinary words. A book may exempt some of
# them with --acronyms-ok when they are the normal spoken name of the thing.
_ACRONIMI_TRAPPOLA = (
    "WHO", "WASH", "DALY", "IRIS", "TB", "PPE", "ORS", "LLIN", "ITN", "IRS",
    "RDT", "ACT", "MDA", "ART", "VHF", "ICU", "NTD",
)


def regola_trappole(consentiti):
    """Builds the trap rule, leaving out the short forms this book allows."""
    restanti = [a for a in _ACRONIMI_TRAPPOLA if a not in consentiti]
    if not restanti:
        return None
    return r"\b(?:" + "|".join(f"{a}s?" for a in restanti) + r")\b"


def controlla(testo: str, trappole=None, consentiti: tuple = ()):
    """Checks one section against the contract. Returns a list of problems."""
    problemi = []
    righe = testo.splitlines()
    intestazioni = [r for r in righe if re.match(r"^\s{0,3}#\s", r)]
    if len(intestazioni) != 1:
        problemi.append(f"expected exactly one heading, found {len(intestazioni)}")
    regole = list(REGOLE)
    if trappole:
        regole.append((trappole, "acronym the voice mangles"))
    for riga_no, riga in enumerate(righe, start=1):
        for schema, descrizione in regole:
            if re.search(schema, riga):
                problemi.append(f"line {riga_no}: {descrizione}: {riga.strip()[:70]}")
    sigle = acronyms_found(testo, consentiti)
    if sigle:
        problemi.append("acronyms to review: " + ", ".join(sigle))
    # The final paragraph must open with "To summarize, ".
    paragrafi = [p.strip() for p in re.split(r"\n\s*\n", testo.strip()) if p.strip()]
    if paragrafi and not paragrafi[-1].startswith("To summarize,"):
        problemi.append("final paragraph does not start with 'To summarize, '")
    return problemi


def carica_capitoli(cartella: Path):
    capitoli = []
    for percorso in sorted(cartella.glob("*.md")):
        testo = percorso.read_text(encoding="utf-8").strip()
        if not testo:
            continue
        m = re.match(r"^#\s+(.*\S)\s*$", testo, flags=re.M)
        titolo = m.group(1) if m else percorso.stem
        n_file = re.match(r"^(\d{1,3})", percorso.stem)
        n_titolo = re.search(r"Chapter\s+(\d+)", titolo)
        appendice = re.search(r"Appendix\s+([A-Z])\b", titolo)
        capitoli.append({
            "n": int(n_titolo.group(1)) if n_titolo else (
                int(n_file.group(1)) if n_file else 0),
            "lettera": appendice.group(1) if appendice else None,
            "tipo": "chapter" if n_titolo else ("appendix" if appendice else "altro"),
            "titolo": titolo,
            "testo": testo,
            "percorso": percorso,
        })
    capitoli.sort(key=lambda c: (c["n"] == 0, c["n"], c["percorso"].name))
    return capitoli


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Assembles books/tropical-medicine/out/tropical-medicine.txt from the sections.")
    ap.add_argument("--capitoli", default="books/tropical-medicine/content/capitoli",
                    help="sections folder (default: books/tropical-medicine/content/capitoli)")
    ap.add_argument("--out", default="books/tropical-medicine/out/tropical-medicine.txt",
                    help="output file")
    ap.add_argument("--indice", default="books/tropical-medicine/out/index.txt",
                    help="readable index file")
    ap.add_argument("--no-frontespizio", action="store_true", help="omit front matter")
    ap.add_argument("--front-matter", default=None,
                    help="file with front matter to use instead of the built-in one")
    ap.add_argument("--acronyms-ok", default="",
                    help="short forms this book tolerates, comma separated "
                         "(e.g. CT,MRI,ECG,ICU)")
    ap.add_argument("--toc-noun", default="course",
                    help="word used in the spoken table of contents: course or guide")
    ap.add_argument("--no-indice", action="store_true", help="omit spoken index")
    ap.add_argument("--strict", action="store_true",
                    help="exit with an error if any section violates the contract")
    ap.add_argument("--stats", action="store_true", help="print statistics only")
    args = ap.parse_args(argv)

    consentiti = tuple(a.strip().upper() for a in args.acronyms_ok.split(",") if a.strip())
    trappole = regola_trappole(consentiti)
    frontespizio = FRONT_MATTER
    if args.front_matter:
        frontespizio = Path(args.front_matter).read_text(encoding="utf-8")

    cartella = Path(args.capitoli)
    if not cartella.is_dir():
        sys.exit(f"Error: {cartella} does not exist.")
    capitoli = carica_capitoli(cartella)
    if not capitoli:
        sys.exit(f"Error: no sections in {cartella}.")

    errori = []
    print(f"{'SEC':>4}  {'WORDS':>7}  {'BYTES':>8}  {'MIN':>5}  TITLE")
    for cap in capitoli:
        parole = count_words(clean_for_speech(cap["testo"]))
        byte = len(clean_for_speech(cap["testo"]).encode("utf-8"))
        problemi = controlla(cap["testo"], trappole, consentiti)
        stato = "ok"
        parole_min = (PAROLE_MIN_CAPITOLO if cap["tipo"] == "chapter"
                      else PAROLE_MIN_APPENDICE)
        if not (parole_min <= parole <= PAROLE_MAX):
            problemi.append(f"length out of range: {parole} words "
                            f"(expected {parole_min}-{PAROLE_MAX})")
        if problemi:
            stato = f"{len(problemi)} warnings"
            errori.append((cap, problemi))
        etichetta = f"ch {cap['n']:02d}" if cap["tipo"] == "chapter" else (
            f"app {cap['lettera']}" if cap["tipo"] == "appendix" else "??")
        print(f"{etichetta:>4}  {parole:>7,}  {byte:>8,}  "
              f"{estimate_seconds(parole) / 60:>4.0f}m  {cap['titolo'][:44]}  [{stato}]")

    for cap, problemi in errori:
        print(f"\n--- {cap['percorso'].name} ---")
        for p in problemi[:12]:
            print(f"    {p}")
        if len(problemi) > 12:
            print(f"    ... and {len(problemi) - 12} more warnings")

    if args.strict and errori:
        print(f"\n--strict: stopped for {len(errori)} sections with warnings.",
              file=sys.stderr)
        return 1

    parti = []
    if not args.no_frontespizio:
        parti.append(frontespizio.strip())
    if not args.no_indice:
        parti.append(indice_parlato(capitoli, args.toc_noun))
    for cap in capitoli:
        parti.append(cap["testo"].strip())
    libro = "\n\n".join(parti).strip() + "\n"

    pulito = clean_for_speech(libro)
    parole = count_words(pulito)
    byte = len(pulito.encode("utf-8"))
    durata = estimate_seconds(parole, WPM_DEFAULT)

    if not args.stats:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(libro, encoding="utf-8")
        indice = Path(args.indice)
        indice.parent.mkdir(parents=True, exist_ok=True)
        righe = ["# " + next(
            (r.lstrip("#").strip() for r in frontespizio.splitlines()
             if r.startswith("# ")), "A Narrated Book"), ""]
        for cap in capitoli:
            righe.append(f"{cap['n']:>3}. {cap['titolo']}")
        righe.append("")
        indice.write_text("\n".join(righe), encoding="utf-8")
        print(f"\nWrote {out} and {indice}")

    print(f"\nSections:        {len(capitoli)}")
    print(f"Words:           {parole:,}")
    print(f"Characters:      {len(pulito):,}")
    print(f"Bytes (UTF-8):   {byte:,}  ({byte / 1e6:.2f} MB)")
    print(f"Estimated audio: {durata / 3600:.2f} hours ({durata / 60:.0f} minutes) "
          f"at {WPM_DEFAULT:.0f} words per minute")
    delta = OBIETTIVO_BYTE - byte
    if delta > 0:
        per_sezione = max(byte // max(len(capitoli), 1), 1)
        print(f"Target 1 MB:     {delta:,} bytes short, "
              f"about {delta / per_sezione:.0f} more sections needed")
    else:
        print(f"Target 1 MB:     reached (+{abs(delta):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())