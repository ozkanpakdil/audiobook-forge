#!/usr/bin/env python3
"""build_book.py — assembles the chapters into a single speech-ready text.

Reads the chapters from content/capitoli/NN-slug.md, checks that they respect the
style contract in content/PLAN.md, orders them, and joins them into out/anatomia.txt
with front matter and a spoken table of contents. Prints the word, character and
byte counts, the estimated audio duration, and the distance to the 1 MB target.

Examples:
    python3 scripts/build_book.py
    python3 scripts/build_book.py --stats
    python3 scripts/build_book.py --strict
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from textnorm import (  # noqa: E402
    WPM_DEFAULT,
    acronyms_found,
    clean_for_speech,
    count_words,
    estimate_seconds,
    ordinale,
)

OBIETTIVO_BYTE = 1_048_576  # 1 MB binary
PAROLE_MIN, PAROLE_MAX = 2800, 5600

FRONTESPIZIO = """# Anatomia umana — corso narrato

Questo corso narrato accompagna chi ascolta attraverso la forma e la funzione del corpo umano, dalle prime nozioni di orientamento fino agli organi di senso. Il percorso segue l'ordine con cui l'anatomia viene tradizionalmente studiata: prima le ossa e le articolazioni, poi i muscoli e il movimento, quindi il cuore e la circolazione, la respirazione, la digestione, l'escrezione, il sistema endocrino e riproduttivo, e infine il sistema nervoso.

Ogni capitolo e' stato scritto per essere ascoltato e non letto. Le descrizioni procedono per immagini e per rapporti topografici, i termini tecnici vengono spiegati alla loro prima comparsa, e la funzione di ogni struttura viene raccontata insieme alla struttura stessa, perche' in anatomia la forma ha senso solo quando si capisce a che cosa serve.

Il testo ha carattere divulgativo e non sostituisce un manuale illustrato: non contiene indicazioni di carattere medico, ne' diagnosi, ne' terapie. Serve a costruirsi un'idea ordinata e duratura di come e' fatto il corpo, e di come le sue parti lavorano insieme.
"""


def indice_parlato(capitoli):
    """Builds the table of contents to be read aloud, as prose."""
    righe = [
                 "# Indice dei capitoli",
                 "",
                 f"Il corso comprende {ordinale(len(capitoli))} capitoli. "
                 "Ecco l'elenco, nell'ordine di ascolto.",
                 "",
             ]
    blocchi = []
    for cap in capitoli:
        titolo = cap["titolo"]
        m = re.match(r"^Capitolo\s+\d+\s*[-—–]\s*(.+)$", titolo)
        testo = m.group(1) if m else titolo
        blocchi.append(f"Capitolo {ordinale(cap['n'])}. {testo}.")
    # One sentence every four chapters, so the list does not go on forever.
    for i in range(0, len(blocchi), 4):
        righe.append(" ".join(blocchi[i:i + 4]))
        righe.append("")
    return "\n".join(righe).strip() + "\n"


REGOLE = (
    (r"\*\*|__|`", "markdown residuo (grassetto o codice)"),
    (r"^\s{0,3}#{2,}", "sottotitolo di livello due o superiore"),
    (r"^\s{0,3}[-*+]\s+\S", "elenco puntato"),
    (r"^\s{0,3}\d+[.)]\s+\S", "elenco numerato"),
    (r"\|", "tabella"),
    (r"https?://|www\.", "indirizzo web"),
    (r"[%&=→←°©®™]", "simbolo non pronunciabile"),
    (r"\[\d+\]|\(\d{4}\)", "rimando a nota o citazione"),
    (r"\d+\s*(?:cm|mm|kg|ml|mg)\b", "unita' di misura non scritta per esteso"),
    (r"\bfig(?:ura)?\.?\s*\d+|\btab(?:ella)?\.?\s*\d+", "rimando a figura o tabella"),
    (r"\b(?:SNC|SNP|ATP|DNA|RNA|ECG|TC|RM|LCA)\b", "sigla non sciolta"),
)


def controlla(testo: str):
    problemi = []
    for riga_no, riga in enumerate(testo.splitlines(), start=1):
        for schema, descrizione in REGOLE:
            if re.search(schema, riga):
                problemi.append(f"riga {riga_no}: {descrizione}: {riga.strip()[:70]}")
    sigle = acronyms_found(testo)
    if sigle:
        problemi.append("sigle da controllare: " + ", ".join(sigle))
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
        n_titolo = re.search(r"Capitolo\s+(\d+)", titolo)
        numero = int(n_titolo.group(1)) if n_titolo else (
            int(n_file.group(1)) if n_file else 0)
        capitoli.append({"n": numero, "titolo": titolo, "testo": testo,
                         "percorso": percorso})
    capitoli.sort(key=lambda c: (c["n"] == 0, c["n"], c["percorso"].name))
    return capitoli


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Compone out/anatomia.txt dai capitoli.")
    ap.add_argument("--capitoli", default="content/capitoli", help="cartella dei capitoli")
    ap.add_argument("--out", default="out/anatomia.txt", help="file di uscita")
    ap.add_argument("--indice", default="out/indice.txt", help="indice leggibile")
    ap.add_argument("--no-frontespizio", action="store_true", help="omette il frontespizio")
    ap.add_argument("--no-indice", action="store_true", help="omette l'indice parlato")
    ap.add_argument("--strict", action="store_true", help="esce con errore se un capitolo viola lo stile")
    ap.add_argument("--stats", action="store_true", help="stampa solo le statistiche")
    args = ap.parse_args(argv)

    cartella = Path(args.capitoli)
    if not cartella.is_dir():
        sys.exit(f"Errore: {cartella} non esiste.")
    capitoli = carica_capitoli(cartella)
    if not capitoli:
        sys.exit(f"Errore: nessun capitolo in {cartella}.")

    errori = []
    print(f"{'CAP':>3}  {'PAROLE':>7}  {'BYTE':>8}  {'MIN':>5}  TITOLO")
    for cap in capitoli:
        parole = count_words(clean_for_speech(cap["testo"]))
        byte = len(clean_for_speech(cap["testo"]).encode("utf-8"))
        problemi = controlla(cap["testo"])
        stato = "ok"
        if not (PAROLE_MIN <= parole <= PAROLE_MAX):
            problemi.append(f"lunghezza fuori intervallo: {parole} parole "
                            f"(attese {PAROLE_MIN}-{PAROLE_MAX})")
        if problemi:
            stato = f"{len(problemi)} avvisi"
            errori.append((cap, problemi))
        print(f"{cap['n']:>3}  {parole:>7,}  {byte:>8,}  "
              f"{estimate_seconds(parole) / 60:>4.0f}m  {cap['titolo'][:46]}  [{stato}]")

    for cap, problemi in errori:
        print(f"\n--- {cap['percorso'].name} ---")
        for p in problemi[:12]:
            print(f"    {p}")
        if len(problemi) > 12:
            print(f"    ... e altri {len(problemi) - 12} avvisi")

    if args.strict and errori:
        print(f"\n--strict: interrotto per {len(errori)} capitoli con avvisi.", file=sys.stderr)
        return 1

    parti = []
    if not args.no_frontespizio:
        parti.append(FRONTESPIZIO.strip())
    if not args.no_indice:
        parti.append(indice_parlato(capitoli))
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
        righe = ["Anatomia umana - corso narrato", ""]
        for cap in capitoli:
            righe.append(f"{cap['n']:>3}. {cap['titolo']}")
        righe.append("")
        indice.write_text("\n".join(righe), encoding="utf-8")
        print(f"\nScritto {out} e {indice}")

    print(f"\nCapitoli:        {len(capitoli)}")
    print(f"Parole:          {parole:,}")
    print(f"Caratteri:       {len(pulito):,}")
    print(f"Byte (UTF-8):    {byte:,}  ({byte / 1e6:.2f} MB)")
    print(f"Durata stimata:  {durata / 3600:.2f} ore ({durata / 60:.0f} minuti) "
          f"a {WPM_DEFAULT:.0f} parole al minuto")
    delta = OBIETTIVO_BYTE - byte
    if delta > 0:
        per_capitolo = max(byte // max(len(capitoli), 1), 1)
        print(f"Obiettivo 1 MB:  mancano {delta:,} byte, "
              f"circa {delta / per_capitolo:.0f} capitoli "
              f"({estimate_seconds(int(delta / 6.4)) / 60:.0f} minuti di parlato)")
    else:
        print(f"Obiettivo 1 MB:  raggiunto (+{abs(delta):,} byte)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
