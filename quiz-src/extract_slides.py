#!/usr/bin/env python3
"""Extract the lecture slides into the per-slide text the quiz is built on.

The five source PDFs are PowerPoint exports: the text layer is sparse and the
real content sits in images, so what matters here is getting every caption onto
the right numbered slide. Needs `pdftotext` (poppler) on PATH.

The PDFs are not stored in this repository. Pass them explicitly:

    python3 extract_slides.py lecture1.pdf lecture2.pdf lecture3.pdf \\
        lecture4.pdf lecture5.pdf

The running header that the PDF export stamps on every slide is detected by
frequency and dropped automatically. Any further text to take out — an author
line on a title slide, for instance — can be removed with one or more
`--redact` patterns; the committed export was produced that way.

Writes extract/deck<N>.slides.json (slide number + cleaned text) and
extract/deck<N>.md (the same, readable). The committed copies of those files are
the source of record for the questions; this script documents how they were
produced.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "extract")

# A line stamped on at least this share of the slides is the export's running
# header, not content.
HEADER_SHARE = 0.5

DECK_META = {
    1: {"date": "2025-10-15", "title": "Chimica generale e propedeutica biochimica"},
    2: {"date": "2025-10-22", "title": "Metabolismo energetico e metabolismo dei carboidrati"},
    3: {"date": "2025-10-30", "title": "Metabolismo dei lipidi"},
    4: {"date": "2025-11-05", "title": "Metabolismo del colesterolo e delle proteine"},
    5: {"date": "2025-11-11", "title": "Proteine plasmatiche, enzimi, vitamine ed elettroliti"},
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdfs", nargs=5, help="the five lecture PDFs, in course order")
    ap.add_argument("--redact", action="append", metavar="TEXT",
                    help="remove this text wherever it appears (repeatable)")
    args = ap.parse_args()

    if shutil.which("pdftotext") is None:
        print("FAIL: pdftotext not found on PATH (install poppler)", file=sys.stderr)
        return 1

    redact = [r.lower() for r in args.redact or []]

    def clean(line: str) -> str:
        s = re.sub(r"\s+", " ", line).strip()
        if any(pat in s.lower() for pat in redact):
            for pat in redact:
                s = re.sub(re.escape(pat), "", s, flags=re.I)
            s = re.sub(r"^[\s•\-–—:.,;()]+", "", s).strip()
        return s

    os.makedirs(OUT, exist_ok=True)
    manifest = []
    for deck, pdf in enumerate(args.pdfs, 1):
        raw = subprocess.run(
            ["pdftotext", "-layout", pdf, "-"],
            check=True, capture_output=True, text=True,
        ).stdout

        pages = [[s for s in (clean(line) for line in page.split("\n")) if s]
                 for page in raw.split("\f")]

        # the running header is whatever the export stamped on most slides
        seen: dict[str, int] = {}
        for lines in pages:
            for s in set(lines):
                seen[s] = seen.get(s, 0) + 1
        heads = {s for s, c in seen.items() if c >= HEADER_SHARE * len(pages)}

        slides = [{"n": n, "text": "\n".join(s for s in lines if s not in heads).strip()}
                  for n, lines in enumerate(pages, 1)]

        meta = DECK_META[deck]
        with open(os.path.join(OUT, f"deck{deck}.slides.json"), "w", encoding="utf-8") as fh:
            json.dump({"deck": deck, "date": meta["date"], "title": meta["title"],
                       "slides": slides}, fh, ensure_ascii=False, indent=1)
        with open(os.path.join(OUT, f"deck{deck}.md"), "w", encoding="utf-8") as fh:
            fh.write(f"# Deck {deck} — {meta['title']} ({meta['date']})\n\n")
            for s in slides:
                fh.write(f"### Slide {s['n']}\n{s['text']}\n\n")

        words = sum(len(s["text"].split()) for s in slides)
        empty = sum(1 for s in slides if not s["text"])
        manifest.append({"deck": deck, "date": meta["date"], "title": meta["title"],
                         "slides": len(slides), "empty_slides": empty, "words": words})
        print(f"deck {deck}: {len(slides):3d} slides, {empty:3d} without text, {words:5d} words")

    with open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
    print(f"wrote {len(manifest)} decks to {os.path.relpath(OUT, HERE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
