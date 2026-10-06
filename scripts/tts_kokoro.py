#!/usr/bin/env python3
"""Synthesizes a text with Kokoro and writes a mono 16-bit WAV.

It is the bridge used by scripts/txt2mp3.py for the --engine kokoro engine. Kokoro
has no command line, so synthesis goes through here.

Two routes, in order of preference:

 1. `pip install kokoro-onnx` — lightweight: only onnxruntime, no torch,
    about 340 MB of models downloaded the first time into models/kokoro/.
    This is the recommended way.
 2. `pip install kokoro` — the original version with torch (heavy, a few
    gigabytes), used only if kokoro-onnx is not there.

Usage:
    python3 scripts/tts_kokoro.py --prepare
    python3 scripts/tts_kokoro.py --text-file blocco.txt --out blocco.wav \\
        --voice af_heart [--lang en-us] [--speed 1.0]

The WAV always comes out mono, 16-bit, at the model's sample rate (24000 Hz).
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
import wave
from pathlib import Path

URL_MODELLO = ("https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
               "model-files-v1.0/kokoro-v1.0.onnx")
URL_VOCI = ("https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
            "model-files-v1.0/voices-v1.0.bin")

# The first letter of a voice name tells the language: af_ and am_ are American
# English, bf_ and bm_ British English, if_ and im_ Italian, hf_ and hm_ Hindi.
PREFISSO_LINGUA = {
    "a": "en-us", "b": "en-gb", "e": "es", "f": "fr-fr",
    "h": "hi", "i": "it", "j": "ja", "p": "pt-br", "z": "cmn",
}

CARTELLA_PREDEFINITA = Path(__file__).resolve().parent.parent / "models" / "kokoro"


def scarica(url: str, destinazione: Path) -> Path:
    """Downloads a file once only, showing how far along it is."""
    if destinazione.exists() and destinazione.stat().st_size > 1_000_000:
        return destinazione
    destinazione.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {destinazione.name} from GitHub (once only) ...", flush=True)

    # Marks only whole megabytes: with \r, in a terminal, the line is
    # refreshed; in a file or a pipe thousands of lines do not pile up.
    stato = {"mb": -1}

    def avanzamento(blocchi, dimensione_blocco, totale):
        if totale <= 0:
            return
        fatto = min(blocchi * dimensione_blocco, totale)
        mb = int(fatto / 1e6)
        if mb != stato["mb"]:
            stato["mb"] = mb
            print(f"\r  {destinazione.name}: {mb}/{totale / 1e6:.0f} MB",
                  end="", flush=True)

    provvisorio = destinazione.with_suffix(destinazione.suffix + ".part")
    urllib.request.urlretrieve(url, provvisorio, avanzamento)
    print()
    provvisorio.replace(destinazione)
    return destinazione


def assicura_modelli(cartella: Path):
    """Downloads if needed and returns (model, voices)."""
    return (scarica(URL_MODELLO, cartella / "kokoro-v1.0.onnx"),
            scarica(URL_VOCI, cartella / "voices-v1.0.bin"))


def scrivi_wav(percorso: Path, campioni, frequenza: int) -> None:
    """Writes a mono 16-bit WAV from float samples in [-1, 1]."""
    import numpy as np

    dati = np.clip(np.asarray(campioni, dtype="float32"), -1.0, 1.0)
    pcm = (dati * 32767.0).astype("<i2").tobytes()
    percorso.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(percorso), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(frequenza)
        w.writeframes(pcm)


def sintetizza_onnx(testo, voce, lingua, velocita, cartella: Path):
    from kokoro_onnx import Kokoro

    modello, voci = assicura_modelli(cartella)
    kokoro = Kokoro(str(modello), str(voci))
    return kokoro.create(testo, voice=voce, speed=velocita, lang=lingua)


def sintetizza_torch(testo, voce, lingua, velocita):
    """Fallback for the original `kokoro` package, which uses torch."""
    import numpy as np
    import torch
    from kokoro import KPipeline

    codice = {"en-us": "a", "en-gb": "b", "es": "e", "fr-fr": "f",
              "hi": "h", "it": "i", "pt-br": "p", "ja": "j", "cmn": "z"}.get(lingua, "a")
    pipeline = KPipeline(lang_code=codice)
    pezzi = []
    for risultato in pipeline(testo, voice=voce, speed=velocita):
        audio = risultato[-1]
        if isinstance(audio, torch.Tensor):
            audio = audio.detach().cpu().numpy()
        pezzi.append(np.asarray(audio, dtype="float32"))
    if not pezzi:
        raise RuntimeError("Kokoro produced no audio")
    return np.concatenate(pezzi), 24000


def main() -> int:
    ap = argparse.ArgumentParser(description="Kokoro -> WAV, for txt2mp3.py")
    ap.add_argument("--text-file", help="text file to read")
    ap.add_argument("--out", help="WAV file to write")
    ap.add_argument("--voice", default="af_heart", help="name of the Kokoro voice")
    ap.add_argument("--lang", default=None,
                    help="language code for phonemization (default: derived from the voice)")
    ap.add_argument("--speed", type=float, default=1.0, help="speed, 1.0 is normal")
    ap.add_argument("--models-dir", default=None, help="where to keep the Kokoro models")
    ap.add_argument("--prepare", action="store_true",
                    help="only download the models, without synthesizing")
    args = ap.parse_args()

    cartella = Path(args.models_dir) if args.models_dir else CARTELLA_PREDEFINITA
    voce = args.voice or "af_heart"
    lingua = args.lang or PREFISSO_LINGUA.get(voce[0], "en-us")

    if args.prepare:
        try:
            modulo = "kokoro-onnx"
            import kokoro_onnx  # noqa: F401
        except ImportError:
            modulo = "kokoro (torch)"
        print(f"Kokoro: using {modulo}")
        if modulo.startswith("kokoro-onnx"):
            assicura_modelli(cartella)
        print("Models ready in " + str(cartella))
        return 0

    if not args.text_file or not args.out:
        ap.error("servono --text-file e --out (oppure --prepare)")

    testo = Path(args.text_file).read_text(encoding="utf-8").strip()
    if not testo:
        raise SystemExit("Error: the text block is empty")
    # kokoro-onnx accepts speeds between 0.5 and 2.0.
    velocita = max(0.5, min(2.0, args.speed))

    try:
        import kokoro_onnx  # noqa: F401
        campioni, frequenza = sintetizza_onnx(testo, voce, lingua, velocita, cartella)
    except ImportError:
        campioni, frequenza = sintetizza_torch(testo, voce, lingua, velocita)

    scrivi_wav(Path(args.out), campioni, frequenza)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
