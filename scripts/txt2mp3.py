#!/usr/bin/env python3
"""txt2mp3 — turn a text book into an MP3 audiobook.

Uses a speech synthesis engine available on the machine and `ffmpeg`, with no
external Python dependencies. It does not depend on macOS: it picks the right
engine by itself, and --engine forces it.

  say     macOS, system voice, nothing to install
  sapi    Windows, System.Speech via PowerShell, nothing to install
  espeak  Linux and anywhere (espeak-ng or espeak): robotic voice but always there
  piper   anywhere, neural network, the best rendering: requires --piper-model

What it does:
  * splits the book into chapters on the heading lines "# Title";
  * splits each chapter into blocks that end at the end of a sentence;
  * synthesizes the blocks in parallel and caches them: a second
    run resumes exactly where it was interrupted;
  * inserts pauses between paragraphs and after the title of each chapter;
  * encodes one MP3 per chapter with the ID3 tags, plus the M3U playlist and,
    on request, a single MP3 with the whole book;
  * with --lang en it uses the English normalizer (units, doses, acronyms) and an
    English voice; it recognizes "Chapter N" and "Appendix A" besides "Capitolo N".

Examples:
    python3 scripts/txt2mp3.py books/anatomia-umana/out/anatomia-umana.txt --dry-run
    python3 scripts/txt2mp3.py books/anatomia-umana/out/anatomia-umana.txt -v Alice -r 170 --jobs 6
    python3 scripts/txt2mp3.py books/anatomia-umana/out/anatomia-umana.txt --only 1,24 --single
    python3 scripts/txt2mp3.py books/tropical-medicine/out/tropical-medicine.txt --lang en \\
        -o books/tropical-medicine/audio
    python3 scripts/txt2mp3.py libro.txt --engine espeak --list-voices
    python3 scripts/txt2mp3.py libro.txt --engine piper --piper-model en_US-lessac-medium.onnx

In this repository every book lives in books/<slug>/out/<slug>.txt and its audio
goes to books/<slug>/audio/. Normally you do not call this script directly: the
launchers in scripts/ read books/books.tsv and call it with the right paths.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _lingua_da_argv() -> str:
    """Read --lang from sys.argv before importing the right normalizer."""
    for i, a in enumerate(sys.argv):
        if a == "--lang" and i + 1 < len(sys.argv):
            return sys.argv[i + 1].lower()
        if a.startswith("--lang="):
            return a.split("=", 1)[1].lower()
    return "it"


LANG = _lingua_da_argv()

if LANG == "en":  # noqa: E402
    from textnorm_en import (  # noqa: E402
        WPM_DEFAULT,
        clean_for_speech,
        count_words,
        estimate_seconds,
        iter_chunks,
        slugify,
    )
else:
    from textnorm import (  # noqa: E402
        WPM_DEFAULT,
        clean_for_speech,
        count_words,
        estimate_seconds,
        iter_chunks,
        slugify,
    )

# Synthesis engines and preferred voices per language. The pipeline no longer
# depends on macOS: it uses whatever it finds, or whatever --engine forces.
_VOCI_PREFERITE = {
    "say": {"it": ("Alice",), "en": ("Samantha", "Daniel", "Karen")},
    "espeak": {"it": ("it",), "en": ("en-us", "en-gb")},
    "sapi": {"it": ("Microsoft Elsa", "Microsoft Cosimo", "Italian"),
             "en": ("Microsoft Zira", "Microsoft David", "Microsoft Mark", "English")},
    # Piper voices, downloadable with piper.download_voices: the first name of each
    # language is the default. The "high" ones are heavier and slower.
    "piper": {"it": ("it_IT-paola-medium", "it_IT-serena-medium", "it_IT-serena-high",
                     "it_IT-riccardo-x_low"),
              "en": ("en_US-lessac-medium", "en_GB-alba-medium", "en_US-ryan-high")},
    # Kokoro: 54 voices, the language is the first letter of the name (af_ and am_ are
    # American English, bf_ and bm_ British, if_ and im_ Italian, hf_ and hm_ Hindi).
    "kokoro": {"it": ("if_sara", "im_nicola"),
               "en": ("af_heart", "af_bella", "af_nicole", "am_michael", "am_onyx",
                      "am_adam", "bf_emma", "bf_alice", "bm_george", "bm_lewis")},
    # MeloTTS: EN-INDIA is English with an Indian accent, and the only way to
    # have it without depending on macOS. MeloTTS has no Italian.
    "melotts": {"it": (),
                "en": ("EN-US", "EN-Default", "EN-INDIA", "EN-BR", "EN-AU")},
}
_NOMI_MOTORE = {
    "say": "macOS say",
    "sapi": "Windows System.Speech",
    "espeak": "espeak-ng",
    "piper": "piper",
    "kokoro": "Kokoro",
    "melotts": "MeloTTS",
}
_NOMI_LINGUA = {"it": "Italian", "en": "English"}

SAMPLE_RATE = 22050
DATA_FORMAT = "LEI16@22050"
DEFAULT_BITRATE = "64k"
PAUSE_PARAGRAFO = 0.35
PAUSA_TITOLO = 0.90
WPM_NEUTRO = 170.0        # speed at which piper speaks with length_scale 1.0
SAPI_WPM_NEUTRO = 180     # approximate speed of SAPI with Rate 0

MOTORE = None        # resolved by risolvi_motore()
MODELLO_PIPER = None  # path of the .onnx model when piper is used
CARTELLA_PIPER = "models"  # where the downloaded piper models end up
ESPEAK_BIN = None    # "espeak-ng" or "espeak"
PWSH = None          # "powershell" or "pwsh"

# ---------------------------------------------------------------------------
# System utilities
# ---------------------------------------------------------------------------


def _run(cmd, **kw):
    kw.setdefault("capture_output", True)
    kw.setdefault("text", True)
    # On Windows the system encoding is not UTF-8: without this, the output of
    # ffmpeg or of PowerShell can make decoding fail.
    kw.setdefault("encoding", "utf-8")
    kw.setdefault("errors", "replace")
    return subprocess.run(cmd, **kw)


def _presente(binary: str) -> bool:
    return shutil.which(binary) is not None


def _require(binary: str, suggerimento: str = "") -> None:
    if not _presente(binary):
        messaggio = f"Error: '{binary}' not found in PATH."
        if suggerimento:
            messaggio += f"\n  {suggerimento}"
        sys.exit(messaggio)


def _piper_argv():
    """How to invoke piper: the script on the PATH, or the Python module.

    `pip install --user piper-tts` puts the executable in a directory that often
    is not on the PATH (for example ~/Library/Python/3.9/bin on macOS): in that case
    piper stays usable as a module of the same interpreter that is running us.
    """
    if _presente("piper"):
        return ["piper"]
    if importlib.util.find_spec("piper") is not None:
        return [sys.executable, "-m", "piper"]
    return None


def _piper_disponibile() -> bool:
    return _piper_argv() is not None


def _modulo_disponibile(nome: str) -> bool:
    """True if a Python module can be imported by this interpreter."""
    try:
        return importlib.util.find_spec(nome) is not None
    except (ImportError, ValueError):
        return False


def motori_disponibili():
    """Engines usable on this machine, in order of preference."""
    trovati = []
    if _piper_disponibile():
        trovati.append("piper")
    if _presente("say"):
        trovati.append("say")
    if os.name == "nt" and (_presente("powershell") or _presente("pwsh")):
        trovati.append("sapi")
    if _presente("espeak-ng") or _presente("espeak"):
        trovati.append("espeak")
    if _modulo_disponibile("kokoro_onnx") or _modulo_disponibile("kokoro"):
        trovati.append("kokoro")
    if _modulo_disponibile("melo"):
        trovati.append("melotts")
    return trovati


def risolvi_motore(richiesto=None, modello_piper=None) -> str:
    """Choose the synthesis engine: the requested one, or the best available."""
    global ESPEAK_BIN, PWSH, MODELLO_PIPER
    disponibili = motori_disponibili()
    MODELLO_PIPER = modello_piper

    if richiesto:
        motore = richiesto.strip().lower()
        if motore in ("espeak-ng", "espeak_ng"):
            motore = "espeak"
        if motore not in disponibili:
            elenco = ", ".join(disponibili) if disponibili else "nessuno"
            sys.exit(f"Error: engine '{richiesto}' not available here. "
                     f"Available: {elenco}.")
    elif not disponibili:
        sys.exit(
            "Error: no speech engine found.\n"
            "  macOS:   'say' ships with the system and should always be there.\n"
            "  Windows: PowerShell ships with Windows and is needed for System.Speech.\n"
            "  Linux:   install espeak-ng:  sudo apt install espeak-ng   "
            "(or dnf, pacman, zypper).\n"
            "  Anywhere: piper has the best voices:  python3 -m pip install piper-tts")
    elif "piper" in disponibili:
        # piper is the best voice among the ready-to-use engines, so it is the
        # default; kokoro and melotts still have to be requested with --engine.
        motore = "piper"
    elif "say" in disponibili:
        motore = "say"
    elif "sapi" in disponibili:
        motore = "sapi"
    elif "espeak" in disponibili:
        motore = "espeak"
    else:
        motore = disponibili[0]

    if motore == "melotts" and LANG == "it":
        sys.exit("Error: MeloTTS has no Italian voice.\n"
                 "  For Italian use piper (it_IT-paola-medium), kokoro (if_sara) "
                 "or say (Alice).")

    if motore == "espeak":
        ESPEAK_BIN = "espeak-ng" if _presente("espeak-ng") else "espeak"
    if motore == "sapi":
        PWSH = "powershell" if _presente("powershell") else "pwsh"
    return motore


def _cerca_modello(nome: str, cartella: str):
    """Find a piper model: a direct path, or <folder>/<name>.onnx."""
    percorso = Path(nome)
    if percorso.exists():
        return percorso
    for candidato in (Path(cartella) / f"{nome}.onnx", Path(f"{nome}.onnx")):
        if candidato.exists():
            return candidato
    return None


def risolvi_modello_piper(richiesto, lang: str, cartella: str):
    """Path of the .onnx model, downloading it if it is not there yet.

    Accepts both an existing .onnx file and the name of a piper voice, for
    example it_IT-paola-medium: in that case it downloads it into <folder>/.
    """
    voce = richiesto or _VOCI_PREFERITE["piper"][lang][0]
    trovato = _cerca_modello(voce, cartella)
    if trovato:
        return trovato

    if not re.match(r"^[a-z]{2}_[A-Z]{2}-[A-Za-z0-9_]+-(x_low|low|medium|high)$", voce):
        sys.exit(f"Error: piper model not found: {voce}\n"
                 "  Pass a .onnx file, or the name of a voice to download,\n"
                 "  for example it_IT-paola-medium (Italian) or en_US-lessac-medium (English).\n"
                 "  The full list is at https://huggingface.co/rhasspy/piper-voices")

    Path(cartella).mkdir(parents=True, exist_ok=True)
    print(f"piper voice '{voce}' is missing: downloading it into {cartella}/ "
          f"(once, a few tens of MB) ...", flush=True)
    p = subprocess.run([sys.executable, "-m", "piper.download_voices", voce,
                        "--download-dir", str(cartella)])
    if p.returncode != 0:
        sys.exit(f"Error: could not download the piper voice '{voce}'.\n"
                 f"  Download it by hand from https://huggingface.co/rhasspy/piper-voices\n"
                 f"  and pass the .onnx file path with --piper-model.")

    trovato = Path(cartella) / f"{voce}.onnx"
    if not trovato.exists():
        sys.exit(f"Error: voice '{voce}' looks downloaded but is not in {trovato}")
    return trovato


# How piper voices are named per language: "it_IT-...", "en_US-...", "en_GB-...".
_PREFISSI_PIPER = {"it": ("it_IT",), "en": ("en_US", "en_GB")}


def _catalogo_piper():
    """All the voice names piper can download (177 at the moment).

    The official catalogue is read instead of keeping a hand-written list, which
    ages; if the network does not answer the piper command is tried, and if that
    fails too an empty list is returned, and the caller falls back.
    """
    try:
        from piper.download_voices import VOICES_JSON, urlopen
        with urlopen(VOICES_JSON, timeout=20) as risposta:
            catalogo = sorted(json.load(risposta).keys())
        if catalogo:
            return catalogo
    except Exception:
        pass
    try:
        p = _run([sys.executable, "-m", "piper.download_voices"])
        return [r.strip() for r in (p.stdout or "").splitlines()
                if re.match(r"^[a-z]{2}_[A-Z]{2}-", r.strip())]
    except Exception:
        return []


def list_voices(lang: str = "it", motore: str = None):
    """[(name, locale)] of the voices available for the requested language."""
    motore = motore or MOTORE

    if motore == "say":
        p = _run(["say", "-v", "?"])
        voci = []
        viste = set()
        for line in p.stdout.splitlines():
            m = re.match(r"^(.*?)\s+([a-z]{2}_[A-Z]{2})\s+#", line)
            if not m or not m.group(2).lower().startswith(lang):
                continue
            nome, codice = m.group(1).strip(), m.group(2)
            # On macOS it happens that the same voice is listed twice: without
            # this check it would also be tried and chosen twice.
            if nome in viste:
                continue
            viste.add(nome)
            voci.append((nome, codice))
        return voci

    if motore == "espeak":
        p = _run([ESPEAK_BIN or "espeak-ng", "--voices"])
        voci = []
        for line in p.stdout.splitlines():
            m = re.match(r"^\s*\d+\s+(\S+)\s+(.*\S)\s*$", line)
            if not m:
                continue
            codice, resto = m.group(1), m.group(2)
            if not codice.lower().startswith(lang):
                continue
            # Columns separated by two or more spaces: gender, descriptive name,
            # file of the voice ("it/it", "en/en-us"), other languages. The code
            # that -v accepts is the part after the slash.
            pezzi = [x.strip() for x in re.split(r"\s{2,}", resto.strip()) if x.strip()]
            voce, descrizione = codice, ""
            for pezzo in pezzi:
                if re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+$", pezzo):
                    voce = pezzo.split("/")[-1]
                    break
            for pezzo in pezzi:
                if pezzo == voce or re.match(r"^[MFA][0-9]?$", pezzo) or "/" in pezzo:
                    continue
                descrizione = pezzo
                break
            voci.append((descrizione or voce, voce))
        if not voci:
            predefinita = _VOCI_PREFERITE["espeak"].get(lang, (lang,))[0]
            voci = [(predefinita, predefinita)]
        return voci

    if motore == "sapi":
        script = (
            "Add-Type -AssemblyName System.Speech\n"
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer\n"
            "$s.GetInstalledVoices() | ForEach-Object { "
            "\"$($_.VoiceInfo.Name)|$($_.VoiceInfo.Culture.Name)\" }\n")
        p = _run([PWSH or "powershell", "-NoProfile", "-NonInteractive",
                  "-ExecutionPolicy", "Bypass", "-Command", script])
        voci = []
        for line in p.stdout.splitlines():
            if "|" not in line:
                continue
            nome, cultura = line.strip().split("|", 1)
            if cultura.lower().startswith(lang):
                voci.append((nome, cultura))
        return voci

    if motore == "piper":
        # Not just the short hand-written list: piper can download 177 voices, and
        # whoever wants a different one must be able to see it. First the recommended
        # ones, then all the others in alphabetical order.
        catalogo = _catalogo_piper()
        prefissi = _PREFISSI_PIPER.get(lang, ())
        disponibili = [v for v in catalogo if v.startswith(prefissi)]
        ordinate = [v for v in _VOCI_PREFERITE["piper"].get(lang, ()) if v in disponibili]
        ordinate += [v for v in sorted(disponibili) if v not in ordinate]
        if not ordinate:
            # Without a catalogue (no network) it falls back to the short list.
            ordinate = list(_VOCI_PREFERITE["piper"].get(lang, ()))
        voci = []
        for voce in ordinate:
            percorso = _cerca_modello(voce, CARTELLA_PIPER)
            voci.append((voce, str(percorso) if percorso else "to download"))
        return voci

    if motore == "kokoro":
        return [(voce, "models in " + str(Path(CARTELLA_PIPER) / "kokoro"))
                for voce in _VOCI_PREFERITE["kokoro"].get(lang, ())]

    if motore == "melotts":
        return [(voce, "English accent" if lang == "en" else "language not available")
                for voce in _VOCI_PREFERITE["melotts"].get(lang, ())]

    return []


def _combacia(richiesto: str, nome: str) -> bool:
    """Compare the requested name with the one shown by `say -v ?`.

    Higher-quality voices are listed as "Name (English (US))",
    so the comparison by prefix is needed, not just by equality.
    """
    return nome == richiesto or nome.startswith(richiesto + " (")


def pick_voice(requested=None, lang: str = "it", motore: str = None):
    """Choose the voice. Returns None when the engine uses its own default."""
    motore = motore or MOTORE

    if motore == "piper":
        # Without a request the already resolved model is used; with a request it can
        # be another voice, which is downloaded on the fly.
        if not requested:
            return str(MODELLO_PIPER)
        return str(risolvi_modello_piper(requested, lang, CARTELLA_PIPER))

    if motore in ("kokoro", "melotts"):
        # Here the voice is a name (kokoro) or an accent (melotts): it is passed to the
        # library, which knows the full list and fails with a clear message.
        if requested:
            return requested
        voci = [nome for nome, _ in list_voices(lang, motore)]
        if not voci:
            sys.exit(f"Error: {_NOMI_MOTORE[motore]} has no voices for "
                     f"{_NOMI_LINGUA.get(lang, lang)}.")
        return voci[0]

    if motore == "espeak":
        # In espeak the voice is a language identifier, with possible
        # variants ("en-us+f3"): it is passed as is, without interpreting it.
        if requested:
            return requested
        preferite = _VOCI_PREFERITE["espeak"].get(lang, (lang,))
        codici = [codice for _, codice in list_voices(lang, "espeak")]
        for preferita in preferite:
            if preferita in codici:
                return preferita
        return preferite[0]

    if motore == "sapi":
        voci = [nome for nome, _ in list_voices(lang, "sapi")]
        if requested:
            for nome in voci:
                if nome == requested:
                    return nome
            for nome in voci:
                if requested.lower() in nome.lower():
                    return nome
            disponibili = ", ".join(voci) if voci else "nessuna"
            sys.exit(f"Error: voice '{requested}' not found. Available: {disponibili}")
        for preferita in _VOCI_PREFERITE["sapi"].get(lang, ()):
            for nome in voci:
                if nome.lower().startswith(preferita.lower()):
                    return nome
        return None  # Windows uses the system default voice

    voices = list_voices(lang, "say")
    if not voices:
        sys.exit(f"Error: no {_NOMI_LINGUA.get(lang, lang)} voice installed. "
                 "Add one in System Settings, Accessibility, Spoken Content.")
    if requested:
        for name, _ in voices:
            if _combacia(requested, name):
                return name
        for name, _ in voices:
            if requested.lower() in name.lower():
                return name
        disponibili = ", ".join(n for n, _ in voices)
        sys.exit(f"Error: voice '{requested}' not found. Available: {disponibili}")
    for preferita in _VOCI_PREFERITE.get(lang, ()):
        for name, _ in voices:
            if _combacia(preferita, name):
                return name
    for name, _ in voices:
        if "Enhanced" in name or "Premium" in name:
            return name
    return voices[0][0]


def ffprobe_duration(path: Path) -> float:
    p = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
              "-of", "csv=p=0", str(path)])
    try:
        return float(p.stdout.strip())
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------
# Book analysis
# ---------------------------------------------------------------------------


def parse_book(path: Path):
    """Split the book into chapters on the '# Title' headings."""
    raw = path.read_text(encoding="utf-8")
    grezzi = []
    titolo, righe = None, []
    for line in raw.splitlines():
        m = re.match(r"^#\s+(.*\S)\s*$", line)
        if m:
            if titolo is not None or any(r.strip() for r in righe):
                grezzi.append((titolo, "\n".join(righe)))
            titolo, righe = m.group(1), []
        else:
            righe.append(line)
    if titolo is not None or any(r.strip() for r in righe):
        grezzi.append((titolo, "\n".join(righe)))

    capitoli = []
    # A file with no heading at all is a single chapter: it is given the name
    # of the file, so `txt2mp3.py appunti.txt` immediately makes a sensible MP3.
    titolo_unico = None
    if len(grezzi) == 1 and grezzi[0][0] is None:
        titolo_unico = path.stem.replace("-", " ").replace("_", " ").strip()
    for titolo, corpo in grezzi:
        corpo = corpo.strip()
        if titolo is None and not corpo:
            continue
        m = re.search(r"Capitolo\s+(\d+)", titolo or "")
        if not m:
            m = re.search(r"Chapter\s+(\d+)", titolo or "")
        ma = re.search(r"Appendix\s+([A-Z])\b", titolo or "")
        capitoli.append({
            "titolo": titolo or titolo_unico or "Introduzione",
            "intestazione": titolo is not None,
            "numero": int(m.group(1)) if m else None,
            "appendice": ma.group(1) if ma else None,
            "corpo": corpo,
        })
    return capitoli


def chiave_capitolo(cap) -> int:
    """Chapter number if declared, otherwise its position in the book."""
    return cap["num"] if cap.get("num") is not None else cap["pos"]


def nome_file_capitolo(cap) -> str:
    """MP3 file name: chapter number, a letter for appendices, 00 for the introduction."""
    if cap.get("num") is not None:
        prefisso = f"{cap['num']:02d}"
    elif cap.get("appendice"):
        prefisso = cap["appendice"]
    else:
        prefisso = "00"
    return f"{prefisso}-{slugify(cap['titolo'])}.mp3"


def piano_capitolo(cap, max_chars: int):
    """Prepare the blocks to synthesize for one chapter."""
    blocchi = []
    titolo = clean_for_speech(cap["titolo"]).strip()
    if titolo:
        blocchi.append({"text": titolo, "pause": PAUSA_TITOLO})
    corpo = clean_for_speech(cap["corpo"])
    for blocco in iter_chunks(corpo, max_chars=max_chars):
        blocchi.append({
            "text": blocco["text"],
            "pause": PAUSE_PARAGRAFO if blocco["para_end"] else 0.0,
        })
    return blocchi


# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------


class Contatore:
    def __init__(self, totale: int):
        self.totale = totale
        self.fatti = 0
        self.inizio = time.time()
        self._lock = threading.Lock()

    def avanti(self, etichetta: str, secondi: float) -> None:
        with self._lock:
            self.fatti += 1
            trascorso = time.time() - self.inizio
            media = trascorso / self.fatti
            resta = media * (self.totale - self.fatti)
            print(
                f"  [{self.fatti:>4}/{self.totale}] {etichetta}  "
                f"+{secondi:4.1f}s audio   elapsed {self._mmss(trascorso)}   "
                f"left {self._mmss(resta)}",
                flush=True,
            )

    @staticmethod
    def _mmss(sec: float) -> str:
        sec = int(max(sec, 0))
        return f"{sec // 60:02d}:{sec % 60:02d}"


def frequenza_wav(percorso: Path) -> int:
    """Sampling rate of a WAV, to align the silences with the blocks."""
    with wave.open(str(percorso), "rb") as w:
        return w.getframerate()


def silence_file(cache: Path, seconds: float, frequenza: int = SAMPLE_RATE) -> Path:
    """Create (only once) a WAV file of silence of the requested duration."""
    percorso = cache / f"silenzio-{int(round(seconds * 1000))}ms-{frequenza}.wav"
    if not percorso.exists():
        with wave.open(str(percorso), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(frequenza)
            w.writeframes(b"\x00\x00" * int(frequenza * seconds))
    return percorso


def chiave_blocco(motore: str, voce, rate: int, indice: int, testo: str) -> str:
    """Cache key: it depends on engine, voice, speed and text."""
    h = hashlib.sha1()
    h.update(f"{motore}|{voce}|{rate}|{testo}".encode("utf-8"))
    return f"{indice:05d}-{h.hexdigest()[:16]}"


def _ps_quote(valore) -> str:
    """PowerShell string in single quotes, with the inner quotes doubled."""
    return "'" + str(valore).replace("'", "''") + "'"


_SAPI_SCRIPT = """\
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$sintesi = New-Object System.Speech.Synthesis.SpeechSynthesizer
$richiesta = {voce_q}
if ($richiesta -ne '') {{
    $nomi = $sintesi.GetInstalledVoices() | ForEach-Object {{ $_.VoiceInfo.Name }}
    $scelta = $nomi | Where-Object {{ $_ -eq $richiesta }} | Select-Object -First 1
    if (-not $scelta) {{ $scelta = $nomi | Where-Object {{ $_ -like "*$richiesta*" }} | Select-Object -First 1 }}
    if (-not $scelta) {{ throw "voce non trovata: $richiesta" }}
    $sintesi.SelectVoice($scelta)
}}
$sintesi.Rate = {rate}
$formato = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo({freq}, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$sintesi.SetOutputToWaveFile({wav_q}, $formato)
$sintesi.Speak([System.IO.File]::ReadAllText({testo_q}, [System.Text.Encoding]::UTF8))
$sintesi.Dispose()
"""


def _rate_sapi(rate: int) -> int:
    """Convert words per minute to the SAPI scale, from minus ten to ten."""
    return max(-10, min(10, int(round((rate - SAPI_WPM_NEUTRO) / 20.0))))


def _script_ponte(nome: str) -> str:
    """Path of a bridge script that sits next to this file."""
    return str(Path(__file__).resolve().with_name(nome))


def _sintetizza_una_volta(motore, voce, rate, testo, testo_file, wav, cache, chiave):
    """A single call to the engine. Raises RuntimeError if it produces no audio."""
    if motore == "say":
        cmd = ["say", "-r", str(rate), "-o", str(wav),
               "--data-format", DATA_FORMAT, "-f", str(testo_file)]
        if voce:
            cmd[1:1] = ["-v", voce]
        p = _run(cmd)
    elif motore == "espeak":
        voce = voce or _VOCI_PREFERITE["espeak"]["en"][0]
        p = _run([ESPEAK_BIN, "-v", voce, "-s", str(rate), "-w", str(wav),
                  "-f", str(testo_file)])
    elif motore == "piper":
        base = _piper_argv()
        if not base:
            raise RuntimeError("piper is no longer available: was it uninstalled?")
        # piper reads the text from stdin and writes the WAV; length_scale above one is slower.
        p = _run(base + ["--model", str(voce), "--output_file", str(wav),
                         "--length_scale", f"{WPM_NEUTRO / max(rate, 1):.3f}"], input=testo)
    elif motore == "kokoro":
        # Kokoro has no command line: it goes through the bridge, which chooses
        # kokoro-onnx (lightweight) or the kokoro package with torch.
        p = _run([sys.executable, _script_ponte("tts_kokoro.py"),
                  "--text-file", str(testo_file), "--out", str(wav),
                  "--voice", str(voce),
                  "--speed", f"{rate / WPM_NEUTRO:.3f}"])
    elif motore == "melotts":
        p = _run([sys.executable, _script_ponte("tts_melotts.py"),
                  "--text-file", str(testo_file), "--out", str(wav),
                  "--lang", LANG.upper(), "--speaker", str(voce),
                  "--speed", f"{rate / WPM_NEUTRO:.3f}"])
    elif motore == "sapi":
        script = cache / f"{chiave}.ps1"
        script.write_text(
            _SAPI_SCRIPT.format(voce_q=_ps_quote(voce or ""), rate=_rate_sapi(rate),
                                freq=SAMPLE_RATE, wav_q=_ps_quote(wav),
                                testo_q=_ps_quote(testo_file)),
            # With BOM: PowerShell 5.1 reads .ps1 files without a BOM as ANSI and
            # would ruin accents and non-ASCII characters.
            encoding="utf-8-sig")
        p = _run([PWSH, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                  "-File", str(script)])
    else:
        raise RuntimeError(f"unknown speech engine: {motore}")

    if p.returncode != 0 or not wav.exists() or wav.stat().st_size <= 512:
        dettaglio = (p.stderr or p.stdout or "").strip()
        righe = [r for r in dettaglio.splitlines() if r.strip()]
        # In a traceback the tail is what matters: that is where the real error is.
        coda = "\n".join(righe[-6:]) if righe else ""
        raise RuntimeError(coda[:500] or f"exit {p.returncode} with no message")


def sintetizza_blocco(motore: str, voce, rate: int, testo: str, cache: Path,
                      chiave: str) -> Path:
    """Synthesize one block into WAV, reusing the cache when possible."""
    wav = cache / f"{chiave}.wav"
    if wav.exists() and wav.stat().st_size > 512:
        return wav
    testo_file = cache / f"{chiave}.txt"
    testo_file.write_text(testo, encoding="utf-8")
    ultimo_errore = ""
    for tentativo in range(3):
        try:
            _sintetizza_una_volta(motore, voce, rate, testo, testo_file, wav, cache, chiave)
            if wav.exists() and wav.stat().st_size > 512:
                return wav
        except Exception as errore:  # noqa: BLE001
            ultimo_errore = str(errore)
        time.sleep(0.6 * (tentativo + 1))
    raise RuntimeError(f"synthesis failed for block {chiave}: {ultimo_errore}")


def _escape_concat(path: Path) -> str:
    """Path for the concat demuxer: forward slashes, valid on Windows too."""
    return "file '" + path.resolve().as_posix().replace("'", "'\\''") + "'"


def codifica_mp3(lista_wav, uscita: Path, bitrate: str, tags: dict, cache: Path) -> None:
    """Concatenate the WAVs with the concat demuxer and encode an MP3 with ID3 tags."""
    lista = cache / f"concat-{uscita.stem}.txt"
    lista.write_text("\n".join(_escape_concat(p) for p in lista_wav) + "\n",
                     encoding="utf-8")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-f", "concat", "-safe", "0", "-i", str(lista),
           "-c:a", "libmp3lame", "-b:a", bitrate, "-ar", str(SAMPLE_RATE), "-ac", "1",
           "-id3v2_version", "3"]
    for chiave, valore in tags.items():
        cmd += ["-metadata", f"{chiave}={valore}"]
    cmd.append(str(uscita))
    p = _run(cmd)
    if p.returncode != 0 or not uscita.exists():
        raise RuntimeError(f"ffmpeg ha fallito su {uscita.name}: {p.stderr.strip()}")


def unisci_mp3(percorsi, uscita: Path, cache: Path, bitrate: str, tags: dict) -> None:
    lista = cache / "concat-libro.txt"
    lista.write_text("\n".join(_escape_concat(p) for p in percorsi) + "\n",
                     encoding="utf-8")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy"]
    for chiave, valore in tags.items():
        cmd += ["-metadata", f"{chiave}={valore}"]
    cmd.append(str(uscita))
    p = _run(cmd)
    if p.returncode != 0 or not uscita.exists():
        raise RuntimeError(f"unione fallita: {p.stderr.strip()}")


# ---------------------------------------------------------------------------
# Main program
# ---------------------------------------------------------------------------


FRASE_PROVA = {
    "it": "Ciao, questa e' anatomia e medicina.",
    "en": "Hello, this is anatomy and medicine.",
}
FILE_SCELTE = ".voci-scelte.json"


def _nome_puro(nome: str) -> str:
    """The usable name of a voice.

    `say -v ?` lists "Rishi (English (India))": for -v only "Rishi" is needed.
    """
    return re.sub(r"\s*\(.*\)\s*$", "", nome).strip()


def _chiedi(domanda: str):
    """Read a line from the keyboard; None if the user closes it or interrupts."""
    try:
        return input(domanda).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None


def _leggi_scelte() -> dict:
    """The voices chosen in the past, per engine and language."""
    percorso = Path(FILE_SCELTE)
    if not percorso.exists():
        return {}
    try:
        return json.loads(percorso.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _salva_scelta(motore: str, lang: str, voce) -> None:
    """Remember the chosen voice, so that next time nothing is asked."""
    scelte = _leggi_scelte()
    scelte[f"{motore}|{lang}"] = str(voce)
    try:
        Path(FILE_SCELTE).write_text(json.dumps(scelte, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
    except OSError:
        pass  # if the folder is not writable the voice will simply be asked again


def riproduci(percorso: Path) -> bool:
    """Play a WAV with whatever is on the machine. False if it cannot."""
    percorso = percorso.resolve()
    comandi = []
    if sys.platform == "darwin":
        comandi.append(["afplay", str(percorso)])
    if os.name == "nt":
        ps = "(New-Object Media.SoundPlayer '" + str(percorso).replace("'", "''") + "').PlaySync()"
        comandi.append([PWSH or "powershell", "-NoProfile", "-Command", ps])
    comandi += [["paplay", str(percorso)],
                ["aplay", "-q", str(percorso)],
                ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", str(percorso)]]
    for cmd in comandi:
        if _presente(cmd[0]):
            _run(cmd)
            return True
    return False


def prova_voce(motore, voce, lang, rate, cache: Path, frase: str) -> bool:
    """Synthesize the sample phrase with a voice and play it back.

    It raises no exceptions: if a voice does not work it says so and moves on, because
    this is a listening test and must not make the conversion fail.
    """
    # The voice from the list is a name; for piper it must be turned into the .onnx
    # file (downloading it if needed), for SAPI into the full installed name.
    try:
        voce = pick_voice(voce, lang, motore) or voce
    except SystemExit:
        print(f"     !! voice {voce} not available for this engine", flush=True)
        return False
    chiave = chiave_blocco(motore, voce, rate, 0, "prova|" + frase)
    try:
        wav = sintetizza_blocco(motore, voce, rate, frase, cache, chiave)
    except RuntimeError as errore:
        print(f"     !! cannot use {voce}: {errore}", flush=True)
        return False
    if riproduci(wav):
        return True
    print(f"     (no audio player: listen to {wav})", flush=True)
    return True


def scegli_voce_interattiva(voci, lang: str, motore: str, rate: int, cache: Path,
                            frase: str, predefinita):
    """Show the list, play the chosen voice, and confirm it with Enter.

    A number downloads (if needed) that voice and immediately plays the sample
    phrase; then Enter confirms, another number tries again. `p` plays them all.
    """
    print(f"\n{_NOMI_LINGUA.get(lang, lang)} voices for {_NOMI_MOTORE[motore]}:")
    for i, (nome, nota) in enumerate(voci, 1):
        print(f"  {i:>3}. {_nome_puro(nome)}  ({nota})")
    print(f"\nSample phrase: \"{frase}\"")
    print("  number = download (if needed), hear that voice, then Enter to confirm")
    print(f"  Enter  = hear nothing and use {predefinita or 'the default'}")
    print("  p      = hear every voice             q = quit")

    candidata = None
    while True:
        if candidata:
            risposta = _chiedi(f"  Enter = confirm {_nome_puro(candidata)}, "
                               "number = try again, q = quit > ")
        else:
            risposta = _chiedi("Voice? ")
        if risposta is None or risposta == "":
            return candidata  # with no candidate, None means "default"
        if risposta.lower() in ("q", "quit", "esci"):
            sys.exit("Interrupted.")
        if risposta.lower() == "p":
            for nome, _ in voci:
                print(f"  {_nome_puro(nome)} ...", flush=True)
                prova_voce(motore, nome, lang, rate, cache, frase)
            continue
        m = re.match(r"^p\s+(\d+)$", risposta, re.I)
        if m:
            indice = int(m.group(1))
        elif risposta.isdigit():
            indice = int(risposta)
        else:
            indice = None
        if indice is not None:
            if 1 <= indice <= len(voci):
                scelta = voci[indice - 1][0]
                print(f"  {_nome_puro(scelta)} ...", flush=True)
                if prova_voce(motore, scelta, lang, rate, cache, frase):
                    candidata = scelta
            else:
                print("  number out of range")
            continue
        trovata = next((n for n, _ in voci if _nome_puro(n).lower() == risposta.lower()
                        or _combacia(risposta, n)), None)
        if trovata:
            print(f"  {_nome_puro(trovata)} ...", flush=True)
            if prova_voce(motore, trovata, lang, rate, cache, frase):
                candidata = trovata
            continue
        print("  did not understand: type a number, p, p N or q")


def menu_prova(motore: str, lang: str, rate: int, cache: Path, frase: str):
    """List the voices and play only the ones asked for, one at a time.

    It downloads nothing in advance: the voice is downloaded when it is asked for, and
    right afterwards the sample phrase is heard. `it` and `en` switch language.
    """
    while True:
        voci = list_voices(lang, motore)
        print(f"\n{_NOMI_LINGUA.get(lang, lang)} voices for {_NOMI_MOTORE[motore]}"
              f"   (phrase: \"{frase}\")")
        if not voci:
            print("  no voices for this language")
            return
        for i, (nome, nota) in enumerate(voci, 1):
            print(f"  {i:>3}. {_nome_puro(nome)}  ({nota})")
        print("  number = download (if needed) and hear that voice     p = all")
        print("  it / en = switch language                Enter or q = quit")

        risposta = _chiedi("Voice? ")
        if risposta is None or risposta == "" or risposta.lower() in ("q", "quit", "esci"):
            return
        if risposta.lower() in ("it", "en"):
            lang = risposta.lower()
            continue
        if risposta.lower() == "p":
            for nome, _ in voci:
                print(f"  {_nome_puro(nome)} ...", flush=True)
                prova_voce(motore, nome, lang, rate, cache, frase)
            continue
        if risposta.isdigit():
            indice = int(risposta)
            if 1 <= indice <= len(voci):
                scelta = voci[indice - 1][0]
                print(f"  {_nome_puro(scelta)} ...", flush=True)
                prova_voce(motore, scelta, lang, rate, cache, frase)
            else:
                print("  number out of range")
            continue
        trovata = next((n for n, _ in voci if _nome_puro(n).lower() == risposta.lower()
                        or _combacia(risposta, n)), None)
        if trovata:
            print(f"  {_nome_puro(trovata)} ...", flush=True)
            prova_voce(motore, trovata, lang, rate, cache, frase)
            continue
        print("  did not understand: type a number, p, it, en or q")


def main(argv=None) -> int:
    global MOTORE, CARTELLA_PIPER, MODELLO_PIPER
    ap = argparse.ArgumentParser(
        description="Convert a text book into an MP3 audiobook. It picks the speech "
                    "engine available: piper, say on macOS, System.Speech on Windows, "
                    "espeak-ng on Linux.")
    ap.add_argument("input", nargs="?", help=".txt file of the book (with '# Title' headings)")
    ap.add_argument("--lang", default="it", choices=["it", "en"],
                    help="text language: normalizer and default voice (default: it)")
    ap.add_argument("-o", "--outdir", default="audio", help="output directory (default: audio)")
    ap.add_argument("-v", "--voice", default=None,
                    help="voice to use (defaults: Alice for Italian on macOS, "
                         "Samantha for English; espeak uses language codes such as it, en-us)")
    ap.add_argument("--engine", default=None,
                    choices=["piper", "kokoro", "melotts", "say", "sapi", "espeak", "espeak-ng"],
                    help="speech engine (default: piper, the best voice that needs "
                         "no setup; then say, sapi, espeak)")
    ap.add_argument("--piper-model", default=None,
                    help=".onnx file, or the name of a piper voice such as it_IT-paola-medium "
                         "or en_US-lessac-medium, which is downloaded (default: the best "
                         "voice for --lang)")
    ap.add_argument("--piper-dir", default=CARTELLA_PIPER,
                    help="directory of the piper models (default: models)")
    ap.add_argument("--list-engines", action="store_true",
                    help="show the available speech engines and exit")
    ap.add_argument("-r", "--rate", type=int, default=170,
                    help="speed in words per minute (default: 170)")
    ap.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 4),
                    help="parallel synthesis jobs (default: min(8, cpu))")
    ap.add_argument("--max-chars", type=int, default=700,
                    help="maximum size of one synthesis block (default: 700)")
    ap.add_argument("--bitrate", default=DEFAULT_BITRATE, help="bitrate MP3 (default: 64k)")
    ap.add_argument("--album", default=None, help="album tag (default: depends on --lang)")
    ap.add_argument("--artist", default="Sintesi vocale", help="artist tag")
    ap.add_argument("--only", default=None,
                    help="synthesize only certain chapters, by number (e.g. 1,24,50)")
    ap.add_argument("--single", action="store_true",
                    help="also build a single MP3 with the whole book")
    ap.add_argument("--force", action="store_true",
                    help="re-encode the MP3s already there (reuses the audio cache)")
    ap.add_argument("--dry-run", action="store_true",
                    help="show the plan, duration and estimated size, without synthesizing")
    ap.add_argument("--list-voices", action="store_true",
                    help="list the voices installed for --lang and the chosen engine, and exit")
    ap.add_argument("--preview-voices", nargs="*", default=None,
                    help="play the sample phrase with the voices given by number "
                         "(or list them all, if you name none) and exit")
    ap.add_argument("--sample-text", default=None,
                    help="sample phrase instead of \"Hello, this is anatomy and medicine\"")
    ap.add_argument("--no-prompt", action="store_true",
                    help="do not ask which voice to use, take the default")
    ap.add_argument("--reset-voice", action="store_true",
                    help="forget the voice chosen before for this engine and language")
    args = ap.parse_args(argv)

    if args.album is None:
        # The "album" is the repo book if the file is one of those, otherwise
        # it is the file itself: so even an appunti.txt has sensible tags.
        nome_file = Path(args.input).name if args.input else ""
        album_noti = {
            "anatomia.txt": "Anatomia umana: corso narrato",
            "tropical-medicine.txt": "Tropical Medicine: A Narrated Course",
            "hospital-equipment.txt": "Hospital Equipment: A Complete Guide",
        }
        if nome_file in album_noti:
            args.album = album_noti[nome_file]
        elif args.input:
            args.album = Path(args.input).stem.replace("-", " ").replace("_", " ").strip()
        else:
            args.album = ("Anatomia umana: corso narrato" if args.lang == "it"
                          else "Tropical Medicine: A Narrated Course")

    if args.list_engines:
        disponibili = motori_disponibili()
        if not disponibili:
            print("No speech engine found on this machine.")
            print("  macOS:   say, ships with the system")
            print("  Windows: PowerShell with System.Speech, ships with the system")
            print("  Linux:   sudo apt install espeak-ng   (or dnf, pacman, zypper)")
            print("  Anywhere: python3 -m pip install piper-tts   (with --piper-model)")
            return 1
        for nome in ("piper", "kokoro", "melotts", "say", "sapi", "espeak"):
            if nome in disponibili:
                print(f"{nome:<8} {_NOMI_MOTORE[nome]:<26} available")
            else:
                print(f"{nome:<8} {_NOMI_MOTORE[nome]:<26} not installed")
        return 0

    CARTELLA_PIPER = args.piper_dir
    MOTORE = risolvi_motore(args.engine, args.piper_model)

    # The engines that need a model or an executable get it now: only once, and
    # outside the parallel processes, otherwise two blocks would download the
    # same model at the same time.
    if MOTORE == "espeak":
        _require(ESPEAK_BIN, "Installa espeak-ng: sudo apt install espeak-ng   "
                             "(oppure dnf, pacman, zypper)")
    elif MOTORE == "piper":
        if not _piper_disponibile():
            sys.exit("Error: piper is not installed.\n"
                     "  python3 -m pip install piper-tts")
        MODELLO_PIPER = risolvi_modello_piper(args.piper_model, args.lang, CARTELLA_PIPER)
    elif MOTORE == "sapi" and not PWSH:
        sys.exit("Error: PowerShell not found: System.Speech needs it on Windows.")
    elif MOTORE == "kokoro":
        prepara = _run([sys.executable, _script_ponte("tts_kokoro.py"), "--prepare",
                        "--models-dir", str(Path(CARTELLA_PIPER) / "kokoro")])
        if prepara.returncode != 0:
            sys.exit("Error: could not prepare Kokoro:\n  "
                     + (prepara.stderr or prepara.stdout or "").strip()[:400])
        print((prepara.stdout or "").strip())
    elif MOTORE == "melotts" and not _modulo_disponibile("melo"):
        sys.exit("Error: MeloTTS is not installed. It must come from GitHub, not PyPI:\n"
                 "  python3 -m pip install git+https://github.com/myshell-ai/MeloTTS.git\n"
                 "  python3 -m unidic download")

    voci_disponibili = list_voices(args.lang, MOTORE)

    if args.list_voices:
        print(f"Engine: {MOTORE}  ({_NOMI_MOTORE[MOTORE]})")
        viste = set()
        for nome, nota in voci_disponibili:
            # `say -v ?` lists "Alice (Italian (Italy))": for -v only "Alice" is needed.
            pulito = _nome_puro(nome)
            if pulito in viste:
                continue
            viste.add(pulito)
            print(f"{pulito}  ({nota})")
        print()
        if MOTORE == "piper":
            print("Use it like this:  --piper-model <name>     (missing voices are downloaded)")
        elif MOTORE == "melotts":
            print("Use it like this:  --engine melotts --voice EN-INDIA")
        else:
            print('Use it like this:  --voice "<name>"      (omit it and one is chosen for you)')
        print("Hear them first:  --preview-voices     (or --preview-voices 1 3 5)")
        print("Other engine:  --engine piper|kokoro|melotts|say|sapi|espeak")
        return 0

    frase_prova = args.sample_text or FRASE_PROVA.get(args.lang, FRASE_PROVA["en"])

    if args.preview_voices is not None:
        richieste = [x for x in args.preview_voices if x]
        cache_prove = Path(args.outdir) / ".cache" / "prove"
        cache_prove.mkdir(parents=True, exist_ok=True)

        if not richieste:
            # With no names nothing is downloaded in advance: it lists them, and
            # only the voice that is asked for is heard.
            print(f"Engine: {MOTORE}  ({_NOMI_MOTORE[MOTORE]})")
            menu_prova(MOTORE, args.lang, args.rate, cache_prove, frase_prova)
            return 0

        numeri = [int(x) for x in richieste if x.isdigit()]
        if numeri:
            scelte = [v for i, v in enumerate(voci_disponibili, 1) if i in numeri]
        else:
            scelte = [v for v in voci_disponibili
                      if any(_combacia(x, v[0]) or _nome_puro(v[0]).lower() == x.lower()
                             for x in richieste)]
        if not scelte:
            elenco = ", ".join(_nome_puro(n) for n, _ in voci_disponibili) or "nessuna"
            sys.exit(f"Error: no voice matches {' '.join(richieste)}.\n"
                     f"  Available: {elenco}")
        print(f"Engine: {MOTORE}   sample phrase: \"{frase_prova}\"")
        for nome, nota in scelte:
            print(f"\n{_nome_puro(nome)}  ({nota})", flush=True)
            prova_voce(MOTORE, nome, args.lang, args.rate, cache_prove, frase_prova)
        return 0

    if not args.input:
        ap.error("an input file is required (or use --list-voices, --preview-voices "
                 "or --list-engines)")

    _require("ffmpeg")
    _require("ffprobe")

    sorgente = Path(args.input)
    if not sorgente.exists():
        sys.exit(f"Error: {sorgente} does not exist.")
    outdir = Path(args.outdir)
    cache = outdir / ".cache"
    cache.mkdir(parents=True, exist_ok=True)
    manifest_path = outdir / ".manifest.json"
    manifest = {"engine": None, "voice": None, "rate": args.rate, "capitoli": {}}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
        manifest.setdefault("capitoli", {})

    rate = args.rate

    if args.reset_voice:
        scelte = _leggi_scelte()
        scelte.pop(f"{MOTORE}|{args.lang}", None)
        try:
            Path(FILE_SCELTE).write_text(json.dumps(scelte, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
        except OSError:
            pass
        print(f"Forgotten the voice for {MOTORE}/{args.lang}.")

    scelta = args.voice
    if not scelta:
        scelta = _leggi_scelte().get(f"{MOTORE}|{args.lang}")
        if scelta:
            print(f"Voice chosen before for {MOTORE}/{args.lang}: {scelta}  "
                  "(change it with --voice, forget it with --reset-voice)")

    # If nobody has chosen, and there is someone at the keyboard, the voices are
    # shown and the sample phrase is played before deciding.
    scelta_dall_utente = False
    if not scelta and not args.no_prompt and len(voci_disponibili) > 1 and sys.stdin.isatty():
        predefinita = voci_disponibili[0][0] if voci_disponibili else None
        scelta = scegli_voce_interattiva(voci_disponibili, args.lang, MOTORE, rate,
                                         cache / "prove", frase_prova, predefinita)
        scelta_dall_utente = bool(scelta)

    voice = pick_voice(scelta, args.lang, MOTORE)
    if scelta_dall_utente:
        _salva_scelta(MOTORE, args.lang, scelta)

    # Changing engine or voice does not redo the MP3s already produced: those
    # stay as they were until --force is requested.
    if (manifest.get("capitoli") and manifest.get("engine")
            and manifest.get("engine") != MOTORE and not args.force):
        print(f"\nNote: the MP3s already there were made with {manifest['engine']} "
              f"(voice {manifest.get('voice')}),")
        print(f"      while now {MOTORE} (voice {voice}) is used. Chapters already "
              "converted stay as they were:")
        print("      add --force to redo them all with the new voice.")
    solo = None
    if args.only:
        solo = {int(x) for x in re.findall(r"\d+", args.only)}

    capitoli = parse_book(sorgente)
    if not capitoli:
        sys.exit("Error: no content found in the input file.")

    # Preparing the plan.
    piano = []
    for pos, cap in enumerate(capitoli, start=1):
        blocchi = piano_capitolo(cap, args.max_chars)
        if not blocchi:
            continue
        parole = sum(count_words(b["text"]) for b in blocchi)
        durata = estimate_seconds(parole, WPM_DEFAULT)
        piano.append({"num": cap["numero"], "pos": pos, "titolo": cap["titolo"],
                      "appendice": cap["appendice"],
                      "blocchi": blocchi, "parole": parole, "durata": durata})

    print(f"Engine: {MOTORE} ({_NOMI_MOTORE[MOTORE]})   "
          f"Voice: {voice or 'default'}   speed: {rate} words per minute   "
          f"chapters: {len(piano)}   blocks: {sum(len(c['blocchi']) for c in piano)}")
    print(f"Estimate: {sum(c['parole'] for c in piano):,} words, "
          f"duration {sum(c['durata'] for c in piano) / 3600:.1f} hours, "
          f"about {sum(c['durata'] for c in piano) * int(args.bitrate.rstrip('k')) * 125 / 1e9:.2f} GB "
          f"at {args.bitrate}")

    if args.dry_run:
        print(f"\n{'CH':>3}  {'WORDS':>7}  {'BLOCKS':>7}  {'LENGTH':>8}  {'MP3':>8}  TITLE")
        for cap in piano:
            mb = cap["durata"] * int(args.bitrate.rstrip("k")) * 125 / 1e6
            print(f"{chiave_capitolo(cap):>3}  {cap['parole']:>7,}  {len(cap['blocchi']):>7}  "
                  f"{cap['durata'] / 60:>6.1f}m  {mb:>6.1f}MB  {cap['titolo'][:52]}")
        return 0

    da_fare = [c for c in piano if solo is None or chiave_capitolo(c) in solo]
    if args.force:
        # Re-encode also what already exists. The audio blocks stay in the cache,
        # so nothing is re-synthesized: only the assembly and the encoding are redone.
        mancanti = list(da_fare)
    else:
        mancanti = [c for c in da_fare if not (outdir / nome_file_capitolo(c)).exists()]
    if solo is not None and not mancanti:
        print("All the requested chapters are already converted. Use --force to redo them.")
        return 0
    if solo is None and not mancanti:
        print("All the chapters are already converted. Use --force to redo them.")
        return 0

    totale_blocchi = sum(len(c["blocchi"]) for c in mancanti)
    contatore = Contatore(totale_blocchi)
    prodotti = []
    avvio = time.time()

    try:
        for cap in mancanti:
            etichetta_cap = f"cap {chiave_capitolo(cap):02d}"
            uscita = outdir / nome_file_capitolo(cap)
            print(f"\n=== Chapter {chiave_capitolo(cap):02d}: {cap['titolo']} "
                  f"({cap['parole']:,} words, {len(cap['blocchi'])} blocks) ===", flush=True)

            wavs = [None] * len(cap["blocchi"])

            def lavora(i, blocco):
                chiave = chiave_blocco(MOTORE, voice, rate, i, blocco["text"])
                percorso = sintetizza_blocco(MOTORE, voice, rate, blocco["text"],
                                             cache, chiave)
                durata = ffprobe_duration(percorso)
                contatore.avanti(f"{etichetta_cap} blocco {i + 1:>2}/{len(cap['blocchi'])}",
                                 durata)
                return i, percorso

            with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
                for i, percorso in pool.map(lambda iv: lavora(*iv),
                                            list(enumerate(cap["blocchi"]))):
                    wavs[i] = percorso

            # The silence must have the same rate as the blocks: piper uses
            # 16 kHz for the "x_low" voices and 22.05 kHz for the others, and the
            # concat demuxer of ffmpeg refuses inputs with different formats.
            frequenza = SAMPLE_RATE
            if wavs and wavs[0] is not None:
                try:
                    frequenza = frequenza_wav(wavs[0])
                except (wave.Error, OSError):
                    pass
            sequenza = []
            for blocco, wav in zip(cap["blocchi"], wavs):
                sequenza.append(wav)
                if blocco["pause"] > 0:
                    sequenza.append(silence_file(cache, blocco["pause"], frequenza))

            tags = {
                "title": cap["titolo"],
                "album": args.album,
                "artist": args.artist,
                "track": f"{cap['pos']}/{len(piano)}",
                "genre": "Speech",
                "comment": (f"Sintesi vocale {_NOMI_MOTORE[MOTORE]}, testo italiano"
                            if args.lang == "it" else
                            f"{_NOMI_MOTORE[MOTORE]} speech synthesis, English text"),
            }
            codifica_mp3(sequenza, uscita, args.bitrate, tags, cache)
            durata_reale = ffprobe_duration(uscita)
            manifest["engine"] = MOTORE
            manifest["voice"] = voice
            manifest["rate"] = rate
            manifest["capitoli"][uscita.name] = {
                "file": uscita.name,
                "titolo": cap["titolo"],
                "parole": cap["parole"],
                "durata": round(durata_reale, 1),
                "caratteri": sum(len(b["text"]) for b in cap["blocchi"]),
            }
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
            prodotti.append(uscita)
            print(f"  -> {uscita}  ({durata_reale / 60:.1f} minutes, "
                  f"{uscita.stat().st_size / 1e6:.1f} MB)", flush=True)
    except KeyboardInterrupt:
        print("\nInterrupted. The block cache is intact: running the same "
              "command again resumes where it stopped.", file=sys.stderr)
        return 130

    # Playlist, in chapter order, including the ones already there.
    tutti = []
    for cap in piano:
        f = outdir / nome_file_capitolo(cap)
        if f.exists():
            tutti.append(f)
    if tutti:
        m3u = outdir / f"{sorgente.stem}.m3u"
        m3u.write_text("#EXTM3U\n" + "\n".join(f"#EXTINF:-1,{p.stem}\n{p.name}"
                                              for p in tutti) + "\n",
                       encoding="utf-8")
        print(f"\nPlaylist: {m3u}  ({len(tutti)} chapters)")

    if args.single and tutti:
        unico = outdir / f"{sorgente.stem}-integrale.mp3"
        print(f"Joining {len(tutti)} chapters into {unico} ...", flush=True)
        unisci_mp3(tutti, unico, cache, args.bitrate,
                   {"title": args.album, "album": args.album, "artist": args.artist,
                    "genre": "Speech"})
        print(f"  -> {unico}  ({ffprobe_duration(unico) / 3600:.2f} hours, "
              f"{unico.stat().st_size / 1e6:.1f} MB)")

    print(f"\nDone in {Contatore._mmss(time.time() - avvio)}. "
          f"Total audio length: "
          f"{sum(c.get('durata', 0) for c in manifest['capitoli'].values()) / 3600:.2f} hours.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
