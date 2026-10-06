#!/usr/bin/env python3
"""Synthesizes a text with MeloTTS and writes a WAV.

Bridge for scripts/txt2mp3.py, --engine melotts engine.

MeloTTS is not on PyPI in a usable way: the published package is a
source tree without requirements.txt and the installation fails. It must be taken from GitHub:

    python3 -m pip install git+https://github.com/myshell-ai/MeloTTS.git
    python3 -m unidic download          # required by the installation

It brings torch with it, so it takes up a few gigabytes. In exchange it is the only
engine that offers English with an Indian accent:

    --lang EN --speaker EN-INDIA

Languages: EN, ES, FR, ZH, JP, KR. Italian is not there.
English accents: EN-Default, EN-US, EN-BR, EN-INDIA, EN-AU.

Usage:
    python3 scripts/tts_melotts.py --text-file blocco.txt --out blocco.wav \\
        --lang EN --speaker EN-INDIA [--speed 1.0]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

LINGUE = ("EN", "ES", "FR", "ZH", "JP", "KR")
ACCENTI = ("EN-Default", "EN-US", "EN-BR", "EN-INDIA", "EN-AU")

ISTRUZIONI = """MeloTTS is not installed. It must be installed from GitHub, not PyPI:

    python3 -m pip install git+https://github.com/myshell-ai/MeloTTS.git
    python3 -m unidic download

It takes a few gigabytes because it uses torch. If you only need Indian-accented
English without torch, on macOS the say command already has the voices
Aman, Rishi and Tara (en_IN): --engine say --voice Tara
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="MeloTTS -> WAV, for txt2mp3.py")
    ap.add_argument("--text-file", required=True, help="text file to read")
    ap.add_argument("--out", required=True, help="WAV file to write")
    ap.add_argument("--lang", default="EN", help="language: " + ", ".join(LINGUE))
    ap.add_argument("--speaker", default=None,
                    help="accent for English: " + ", ".join(ACCENTI))
    ap.add_argument("--speed", type=float, default=1.0, help="speed, 1.0 is normal")
    ap.add_argument("--device", default="auto", help="auto, cpu or cuda")
    args = ap.parse_args()

    lingua = (args.lang or "EN").upper()
    if lingua not in LINGUE:
        raise SystemExit(f"Error: MeloTTS does not know the language '{lingua}'. "
                         f"Available languages: {', '.join(LINGUE)}.\n"
                         "  For Italian use --engine piper or --engine say.")

    testo = Path(args.text_file).read_text(encoding="utf-8").strip()
    if not testo:
        raise SystemExit("Error: the text block is empty")

    try:
        from melo.api import TTS
    except ImportError:
        sys.stderr.write(ISTRUZIONI)
        return 2

    modello = TTS(language=lingua, device=args.device)
    parlanti = modello.hps.data.spk2id

    # The speaker only matters for English: in the other languages MeloTTS has one.
    if lingua == "EN":
        accento = args.speaker or "EN-Default"
        if accento not in parlanti:
            raise SystemExit(f"Error: accent '{accento}' not available. "
                             f"Disponibili: {', '.join(sorted(parlanti))}")
        parlante = parlanti[accento]
    else:
        if args.speaker:
            sys.stderr.write("Note: --speaker only applies to English, ignoring it.\n")
        parlante = parlanti[list(parlanti.keys())[0]]

    uscita = Path(args.out)
    uscita.parent.mkdir(parents=True, exist_ok=True)
    modello.tts_to_file(testo, parlante, str(uscita), speed=args.speed)
    if not uscita.exists():
        raise SystemExit("Error: MeloTTS wrote no WAV file")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
