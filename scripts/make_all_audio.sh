#!/usr/bin/env bash
#
# make_all_audio.sh — build every book's text and turn it into MP3 files.
#
# One command to go from a fresh clone to five audiobooks. It checks (and, if you
# let it, installs) everything the pipeline needs, rebuilds each book's text from
# its chapters, and converts it to MP3 with a speech engine found on the machine.
#
# Works on macOS, Linux, and Windows under Git Bash / MSYS2 / Cygwin. On Windows
# the native alternative is make_all_audio.ps1.
#
# The books are not listed here: books/books.tsv is the single registry that both
# this launcher and make_all_audio.ps1 read. Every book lives in books/<slug>/ with
# the same shape (content/, out/, audio/), so nothing here needs to know the
# particular paths of a particular book.
#
#   ./scripts/make_all_audio.sh                  # every book in the registry
#   ./scripts/make_all_audio.sh --book equipment # just one (slug or alias)
#   ./scripts/make_all_audio.sh --dry-run        # plan, durations, sizes only
#   ./scripts/make_all_audio.sh --engine espeak  # pick the speech engine
#   ./scripts/make_all_audio.sh --prune-cache    # free the WAV cache when done
#
# Speech engines (the converter picks the best available; --engine overrides):
#   say     macOS system voice            nothing to install
#   sapi    Windows System.Speech         nothing to install (PowerShell)
#   espeak  espeak-ng, everywhere         apt/dnf/pacman install espeak-ng
#   piper   neural voices, best quality   pip install piper-tts + --piper-model
#
# There are NO third-party Python packages required by the pipeline itself: it is
# standard library only, and this script verifies that rather than installing
# anything. See requirements.txt.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# ----------------------------------------------------------------- platform
case "$(uname -s)" in
    Darwin)               PLATFORM=macos ;;
    Linux)                PLATFORM=linux ;;
    MINGW*|MSYS*|CYGWIN*) PLATFORM=windows ;;
    *)                    PLATFORM=other ;;
esac

# ----------------------------------------------------------------- defaults
BOOKS=""
JOBS=""
VOICE=""
RATE=""
BITRATE=""
OUT=""
ONLY=""
ENGINE=""
PIPER_MODEL=""
PIPER_DIR=""
PREVIEW=0
NO_PROMPT=0
RESET_VOICE=0
FORCE=0
SINGLE=1
DRY=0
DO_BUILD=1
SKIP_INSTALL=0
INSTALL_BREW=0
ASSUME_YES=0
WITH_PIP=0
PRUNE_CACHE=0
LIST_VOICES=0
LIST_BOOKS=0

# The acronyms each book tolerates as spoken short forms used to be hardcoded
# here. They now live, per book, in books/books.tsv — see the registry section.

# ----------------------------------------------------------------- messages
info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m  ok\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m  !!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

confirm() {
    [[ $ASSUME_YES -eq 1 ]] && return 0
    if [[ ! -t 0 ]]; then
        warn "not running interactively; re-run with --yes to allow installs"
        return 1
    fi
    local ans=""
    read -r -p "$1 [y/N] " ans || true
    [[ "$ans" == "y" || "$ans" == "Y" ]]
}

usage() {
    cat <<'EOF'
make_all_audio.sh — build the texts and generate all MP3s.

Usage:
  ./scripts/make_all_audio.sh [options]

Books:
  --book NAME        the slug of a book under books/, the slug of its folder,
                     one of its aliases, or 'all'. The list lives in
                     books/books.tsv, which is also what the PowerShell
                     launcher reads; run --list-books to print it.
                       anatomia-umana         (aliases: it, italiano, anatomia)
                       tropical-medicine      (alias:   tropical)
                       hospital-equipment     (alias:   equipment)
                       clinical-diagnosis     (alias:   diagnosis)
                       emergency-trauma-care  (aliases: trauma, emergency)
                     With no --book on a terminal, it asks which one; then
                     it asks which engine, and which voice and accent (with
                     a list to listen to, and the Indian English voices
                     explained); then it shows how much audio there is and
                     how long it should take, and starts only on a yes.
                     (default: all)
                     May be repeated, or comma separated.

Speech engine:
  --engine NAME      piper | kokoro | melotts | say | sapi | espeak
                     Default: piper, the best voice that needs no setup; then
                     say, sapi, espeak. kokoro and melotts are opt-in extras.
  --piper-model NAME .onnx file, or a voice name such as it_IT-paola-medium,
                     which is downloaded automatically (default: best for --lang)
  --piper-dir DIR    where piper keeps its downloaded models (default: models)

Choosing a voice:
  --voice NAME       use this voice for every book
                     piper: it_IT-paola-medium, en_US-lessac-medium, ...
                     kokoro: af_heart, am_michael, if_sara, ...
                     say: Alice, Samantha, ...     melotts: EN-US, EN-INDIA, ...
  --preview-voices   list the voices and play the sample phrase for the one you
                     pick (number); nothing is downloaded until you ask
                     (on a terminal the launcher offers this as a step, and the
                     voice it picks is the one the conversion then uses)
  --no-prompt        never ask which voice to use; take the default
  --reset-voice      forget the voice chosen in a previous run

Common options:
  --jobs N           parallel synthesis processes (default: min(8, cpu cores))
  --voice NAME       override the voice for every book
                     (macOS: Alice / Samantha; espeak: it, en-us; Windows: the
                     installed System.Speech voice name)
  --rate WPM         speaking rate in words per minute (default: 170)
  --bitrate K        MP3 bitrate (default: 64k)
  --out DIR          output directory; only valid with a single --book
  --only LIST        convert only these chapters, e.g. --only 1,24,50
                     (only valid with a single --book)
  --force            re-encode MP3s that already exist (reuses the chunk cache)
  --no-single        do not build the single whole-book MP3
  --no-build         skip rebuilding the .txt from the chapter files
  --dry-run          print the plan, durations and sizes; synthesize nothing
  --prune-cache      delete each book's .cache/ WAV directory after success
  --list-voices      list the engines and voices available, then exit
  --list-books       list the books in the registry and their folders, then exit

Installation:
  --skip-install     never try to install anything; fail if something is missing
  --install-brew     on macOS, allow installing Homebrew itself if missing
  --with-pip         also run `pip install -r requirements.txt` (a no-op: the
                     pipeline has no third-party dependencies)
  --yes              assume yes for install prompts (non-interactive)

Examples:
  ./scripts/make_all_audio.sh
  ./scripts/make_all_audio.sh --book tropical --jobs 4
  ./scripts/make_all_audio.sh --engine espeak --book it
  ./scripts/make_all_audio.sh --engine piper --piper-model en_US-lessac-medium.onnx
  ./scripts/make_all_audio.sh --book it --out /Volumes/Audio/anatomia --prune-cache
EOF
}

# ----------------------------------------------------------------- arguments
need_value() { [[ $# -ge 2 && -n "${2:-}" ]] || die "option $1 needs a value"; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --book)         need_value "$@"; BOOKS="${BOOKS:+$BOOKS,}${2}"; shift 2 ;;
        --jobs)         need_value "$@"; JOBS="$2"; shift 2 ;;
        --voice)        need_value "$@"; VOICE="$2"; shift 2 ;;
        --rate)         need_value "$@"; RATE="$2"; shift 2 ;;
        --bitrate)      need_value "$@"; BITRATE="$2"; shift 2 ;;
        --out)          need_value "$@"; OUT="$2"; shift 2 ;;
        --only)         need_value "$@"; ONLY="$2"; shift 2 ;;
        --engine)       need_value "$@"; ENGINE="$2"; shift 2 ;;
        --piper-model)  need_value "$@"; PIPER_MODEL="$2"; shift 2 ;;
        --piper-dir)    need_value "$@"; PIPER_DIR="$2"; shift 2 ;;
        --preview-voices) PREVIEW=1; shift ;;
        --no-prompt)    NO_PROMPT=1; shift ;;
        --reset-voice)  RESET_VOICE=1; shift ;;
        --force)        FORCE=1; shift ;;
        --no-single)    SINGLE=0; shift ;;
        --no-build)     DO_BUILD=0; shift ;;
        --dry-run)      DRY=1; shift ;;
        --prune-cache)  PRUNE_CACHE=1; shift ;;
        --list-voices)  LIST_VOICES=1; shift ;;
        --list-books)   LIST_BOOKS=1; shift ;;
        --skip-install) SKIP_INSTALL=1; shift ;;
        --install-brew) INSTALL_BREW=1; shift ;;
        --with-pip)     WITH_PIP=1; shift ;;
        --yes|-y)       ASSUME_YES=1; shift ;;
        -h|--help)      usage; exit 0 ;;
        *)              die "unknown option: $1  (try --help)" ;;
    esac
done


# ----------------------------------------------------------------- book registry
# books/books.tsv is the only place a book is declared. This launcher and
# make_all_audio.ps1 both read it, so the two can never disagree about which books
# exist, where they live, or how each one is built. Every book folder has the same
# shape, which is why nothing below hardcodes a book:
#
#   books/<slug>/content/PLAN.md          the style contract
#   books/<slug>/content/OUTLINE.md       the briefs, one per section
#   books/<slug>/content/capitoli/*.md    the sections themselves
#   books/<slug>/content/FRONT_MATTER.md  front matter, when the book has its own
#   books/<slug>/out/<slug>.txt           the assembled book
#   books/<slug>/out/index.txt            the readable index
#   books/<slug>/audio/                   generated MP3s, never committed
#
# Registry columns: slug, lang, toc, acronyms, title, aliases.
REGISTRY="books/books.tsv"

# One validated row per book: header, comments and blank lines removed. awk keeps
# $0 intact so the tabs survive.
registry_rows() {
    [[ -f "$REGISTRY" ]] || die "book registry not found: $REGISTRY"
    awk -F'\t' 'NR > 1 && $1 != "" && $1 !~ /^[[:space:]]*#/ { print }' "$REGISTRY"
}

# book_field <slug> <lang|toc|acr|title|aliases> — one column of a book's row.
# The "-" placeholder means "not set" and prints nothing.
book_field() {
    local want="$1" col="$2" slug lang toc acr title aliases
    while IFS=$'\t' read -r slug lang toc acr title aliases; do
        [[ "$slug" == "$want" ]] || continue
        case "$col" in
            lang)    printf '%s' "$lang" ;;
            toc)     [[ "$toc" == "-" ]] || printf '%s' "$toc" ;;
            acr)     [[ "$acr" == "-" ]] || printf '%s' "$acr" ;;
            title)   printf '%s' "$title" ;;
            aliases) printf '%s' "$aliases" ;;
            *)       printf '%s' "$slug" ;;
        esac
        return 0
    done < <(registry_rows)
    return 1
}

# All canonical slugs, in registry order.
book_slugs() {
    local slug rest
    while IFS=$'\t' read -r slug rest; do printf '%s\n' "$slug"; done < <(registry_rows)
}

# Resolves a name typed on the command line — canonical slug or alias, any case —
# to the canonical slug. Prints nothing and fails when the name is unknown.
book_canon() {
    local want slug lang toc acr title aliases a alias_parts
    want="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
    while IFS=$'\t' read -r slug lang toc acr title aliases; do
        [[ "$slug" == "$want" ]] && { printf '%s' "$slug"; return 0; }
        IFS=',' read -r -a alias_parts <<<"$aliases"
        for a in "${alias_parts[@]}"; do
            a="$(printf '%s' "$a" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
            [[ -n "$a" && "$a" == "$want" ]] && { printf '%s' "$slug"; return 0; }
        done
    done < <(registry_rows)
    return 1
}

# Every path of a book, derived from that folder shape. One line, pipe separated:
#   text | source | lang | title | builder | front | indice | acronyms | toc
book_paths() {
    # Note: these must not share a `local` line. On bash 3.2 (the /bin/bash that
    # macOS still ships) `local a="$1" b="x/$a"` expands $a from the *outer* scope,
    # so dir would silently pick up a stale value.
    local slug="$1"
    local dir; dir="books/$slug"
    local front=""
    local builder
    local lang title toc acr
    lang="$(book_field "$slug" lang)" || return 1
    title="$(book_field "$slug" title)"
    toc="$(book_field "$slug" toc)"
    acr="$(book_field "$slug" acr)"
    [[ -f "$dir/content/FRONT_MATTER.md" ]] && front="$dir/content/FRONT_MATTER.md"
    if [[ "$lang" == "it" ]]; then
        builder="scripts/build_book.py"
    else
        builder="scripts/build_book_en.py"
    fi
    printf '%s|%s|%s|%s|%s|%s|%s|%s|%s\n' \
        "$dir/out/$slug.txt" "$dir/content/capitoli" "$lang" "$title" "$builder" \
        "$front" "$dir/out/index.txt" "$acr" "$toc"
}

# Words in a book: the assembled text if it is there, otherwise its chapters.
book_words() {
    local text src
    IFS='|' read -r text src _ _ <<<"$(book_paths "$1")"
    if [[ -f "$text" ]]; then
        wc -w <"$text" | tr -d ' '
    elif [[ -d "$src" ]]; then
        cat "$src"/*.md 2>/dev/null | wc -w | tr -d ' '
    else
        printf '0'
    fi
}

# 349708 -> 349.708
migliaia() {
    awk -v n="${1:-0}" 'BEGIN {
        s = sprintf("%d", n); r = ""
        while (length(s) > 3) { r = "." substr(s, length(s) - 2) r; s = substr(s, 1, length(s) - 3) }
        print s r
    }'
}

# seconds -> "3 hours 40 minutes"
human_time() {
    awk -v s="${1:-0}" 'BEGIN {
        s = int(s + 0.5)
        h = int(s / 3600); m = int((s % 3600) / 60)
        if (s < 60) printf "%d seconds", s
        else if (h == 0) printf "%d minutes", m
        else if (m == 0) printf "%d hours", h
        else printf "%d hours %d minutes", h, m
    }'
}

# Interactive: asks which book, and prints how much audio there is and how long it will take.
menu_books() {
    local slugs=() slug i=1 w h titolo risposta=""
    while IFS= read -r slug; do slugs+=("$slug"); done < <(book_slugs)
    (( ${#slugs[@]} > 0 )) || die "the registry $REGISTRY lists no books"
    printf '\n'
    info "which book do you want to convert?"
    for slug in "${slugs[@]}"; do
        IFS='|' read -r _ _ _ titolo _ _ _ _ _ <<<"$(book_paths "$slug")"
        w="$(book_words "$slug")"
        h="$(awk -v w="$w" 'BEGIN{printf "%.1f", w/170/60}')"
        printf '  %2d) %-24s %-40s %8s words, about %s hours of audio\n' \
               "$i" "$slug" "$titolo" "$(migliaia "$w")" "$h"
        i=$((i+1))
    done
    printf '  %2d) %-24s %s\n' "$i" all "all ${#slugs[@]} of them, one after another"
    read -r -p "  number [Enter = all]: " risposta || true
    case "$risposta" in
        "") BOOKS="all" ;;
        *[!0-9]*) warn "not a choice I know: taking all of them"; BOOKS="all" ;;
        *)
            if [[ "$risposta" -ge 1 && "$risposta" -le "${#slugs[@]}" ]]; then
                BOOKS="${slugs[$((risposta - 1))]}"
            elif [[ "$risposta" -eq $(( ${#slugs[@]} + 1 )) ]]; then
                BOOKS="all"
            else
                warn "not a choice I know: taking all of them"; BOOKS="all"
            fi
            ;;
    esac
    ok "book: $BOOKS"
}

# Prints the registry: what exists, where it lives, and under which names.
menu_list_books() {
    local slug text src lang title builder front indice acr toc
    info "books in $REGISTRY"
    printf '\n  %-24s %-4s %10s  %s\n' SLUG LANG WORDS TITLE
    while IFS= read -r slug; do
        IFS='|' read -r text src lang title builder front indice acr toc <<<"$(book_paths "$slug")"
        printf '  %-24s %-4s %10s  %s\n' \
               "$slug" "$lang" "$(migliaia "$(book_words "$slug")")" "$title"
        printf '  %-24s %-4s %10s  %s\n' "" "" "" "$(dirname "$text")/  ->  $(basename "$text")"
    done < <(book_slugs)
    printf '\n  aliases: '
    while IFS= read -r slug; do
        printf '%s [%s]  ' "$slug" "$(book_field "$slug" aliases)"
    done < <(book_slugs)
    printf '\n'
}

if [[ $LIST_BOOKS -eq 1 ]]; then
    menu_list_books
    exit 0
fi

# Normalise the book selection.
if [[ -z "$BOOKS" ]]; then
    if [[ -t 0 && $ASSUME_YES -eq 0 && $DRY -eq 0 ]]; then
        menu_books
    else
        BOOKS="all"
    fi
fi
SELECTED=""
add_book() {
    # Keeps the selection in registry order and free of duplicates.
    case " $SELECTED " in *" $1 "*) ;; *) SELECTED="$SELECTED $1" ;; esac
}
OLD_IFS="$IFS"; IFS=','
for b in $BOOKS; do
    if [[ "$b" == "all" || -z "$b" ]]; then
        while IFS= read -r slug; do add_book "$slug"; done < <(book_slugs)
    elif slug="$(book_canon "$b")"; then
        add_book "$slug"
    else
        IFS="$OLD_IFS"
        die "unknown book: $b
       books in $REGISTRY: $(book_slugs | tr '\n' ' ')
       or 'all'
       (each book also answers to its aliases: --list-books shows them)"
    fi
done
IFS="$OLD_IFS"
SELECTED="${SELECTED# }"

(( ${#SELECTED} > 0 )) || die "no book selected (is $REGISTRY empty?)"

n_books=$(wc -w <<<"$SELECTED" | tr -d ' ')
if [[ -n "$OUT" && $n_books -ne 1 ]]; then
    die "--out needs exactly one --book (the books have different output folders)"
fi
if [[ -n "$ONLY" && $n_books -ne 1 ]]; then
    die "--only needs exactly one --book"
fi

# ----------------------------------------------------------------- helpers
python_bin() {
    # Windows often has only "python" or the "py" launcher; elsewhere python3.
    if command -v python3 >/dev/null 2>&1; then echo python3
    elif command -v python  >/dev/null 2>&1; then echo python
    elif command -v py      >/dev/null 2>&1; then echo "py -3"
    else echo ""; fi
}

# Prints the install command for a component, or nothing if no installer is known.
install_cmd_for() {
    local componente="$1"
    # These are Python packages: the installation is the same on every system.
    case "$componente" in
        piper)   echo "$PY -m pip install --user piper-tts"; return ;;
        kokoro)  echo "$PY -m pip install --user kokoro-onnx"; return ;;
        melotts) echo "$PY -m pip install --user git+https://github.com/myshell-ai/MeloTTS.git && $PY -m unidic download"; return ;;
    esac
    if [[ "$PLATFORM" == macos ]]; then
        command -v brew >/dev/null 2>&1 || return 0
        case "$componente" in
            ffmpeg) echo "brew install ffmpeg" ;;
        esac
    elif [[ "$PLATFORM" == linux ]]; then
        local pm=""
        if   command -v apt-get >/dev/null 2>&1; then pm="sudo apt-get install -y"
        elif command -v dnf     >/dev/null 2>&1; then pm="sudo dnf install -y"
        elif command -v pacman  >/dev/null 2>&1; then pm="sudo pacman -S --noconfirm"
        elif command -v zypper  >/dev/null 2>&1; then pm="sudo zypper install -y"
        fi
        [[ -n "$pm" ]] || return 0
        case "$componente" in
            ffmpeg) echo "$pm ffmpeg" ;;
            espeak) echo "$pm espeak-ng" ;;
        esac
    elif [[ "$PLATFORM" == windows ]]; then
        case "$componente" in
            ffmpeg)
                if   command -v winget >/dev/null 2>&1; then echo "winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements"
                elif command -v choco  >/dev/null 2>&1; then echo "choco install ffmpeg -y"
                elif command -v scoop  >/dev/null 2>&1; then echo "scoop install ffmpeg"
                fi
                ;;
        esac
    fi
}

# True if a Python module is importable from this interpreter.
modulo_presente() {
    $PY -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('$1') else 1)" 2>/dev/null
}

# Installs a component, asking first unless --yes.
installa() {
    local componente="$1" motivo="$2"
    if [[ $SKIP_INSTALL -eq 1 ]]; then
        die "$motivo (--skip-install was given, so nothing was installed)"
    fi
    local cmd
    cmd="$(install_cmd_for "$componente")"
    if [[ -z "$cmd" ]]; then
        die "$motivo, and no installer was found for this system.
       macOS:   brew install $componente
       Linux:   sudo apt-get install -y ffmpeg espeak-ng
       Windows: winget install --id Gyan.FFmpeg -e"
    fi
    info "missing: $motivo"
    if confirm "Run this now?  $cmd"; then
        eval "$cmd"
    else
        die "$motivo"
    fi
}

# ----------------------------------------------------------------- environment
PY="$(python_bin)"
[[ -n "$PY" ]] || die "python3 not found. Install Python 3.8 or newer first:
       macOS:   brew install python
       Linux:   sudo apt-get install -y python3
       Windows: winget install --id Python.Python.3.12 -e"

$PY - <<'PY' || die "Python is too old: version 3.8 or newer is required"
import sys
sys.exit(0 if sys.version_info >= (3, 8) else 1)
PY
ok "Python $($PY -c 'import platform; print(platform.python_version())')  ($PY)"

# The pipeline must run with no third-party packages at all. Running each entry
# point with --help proves every import resolves; that is the whole check.
for script in scripts/txt2mp3.py scripts/build_book.py scripts/build_book_en.py; do
    PYTHONDONTWRITEBYTECODE=1 $PY "$script" --help >/dev/null 2>&1 \
        || die "$script does not run: fix the Python environment before continuing"
done
ok "pipeline scripts run (standard library only, no pip packages needed)"

# Kokoro needs Python 3.10 or newer, because onnxruntime >= 1.20 does not
# exist for 3.9: if the dedicated venv is there the pipeline runs inside it, while
# everything else stays on the system interpreter.
if [[ "$ENGINE" == "kokoro" && -x "$ROOT/.tools/venv-kokoro/bin/python3" ]]; then
    PY="$ROOT/.tools/venv-kokoro/bin/python3"
    info "kokoro: uso $PY"
fi

if [[ $WITH_PIP -eq 1 ]]; then
    if [[ -f requirements.txt ]]; then
        info "pip install -r requirements.txt (documented no-op)"
        $PY -m pip install -r requirements.txt || warn "pip step failed, but it is not required"
    else
        warn "requirements.txt not found; skipping --with-pip"
    fi
fi

# ----------------------------------------------------------------- engine menu and estimate
menu_engine() {
    local scelte=(auto piper say sapi espeak kokoro melotts)
    local descr=("choose the best one available (piper, then say, sapi, espeak)"
                 "neural voices, the best quality: pip install piper-tts"
                 "the macOS system voices"
                 "the Windows System.Speech voices"
                 "very fast, very robotic, good for checking a text"
                 "opt-in extra: needs its own environment"
                 "opt-in extra: needs torch and a large download")
    local tabella n disp i=1 risposta=""
    tabella="$($PY scripts/txt2mp3.py --list-engines 2>/dev/null || true)"
    printf '\n'
    info "which speech engine?"
    for n in "${scelte[@]}"; do
        disp=""
        if [[ "$n" != auto ]]; then
            if grep -qE "^${n}[[:space:]].*[[:space:]]available$" <<<"$tabella"; then
                disp="ready"
            else
                disp="not installed here"
            fi
        fi
        printf '  %2d) %-8s %-58s %s\n' "$i" "$n" "${descr[$((i-1))]}" "$disp"
        i=$((i+1))
    done
    read -r -p "  number [Enter = 1, automatic]: " risposta || true
    case "$risposta" in
        ""|1) ENGINE="" ;;
        2) ENGINE="piper" ;;
        3) ENGINE="say" ;;
        4) ENGINE="sapi" ;;
        5) ENGINE="espeak" ;;
        6) ENGINE="kokoro" ;;
        7) ENGINE="melotts" ;;
        *) warn "not a choice I know: choosing automatically"; ENGINE="" ;;
    esac
    [[ -n "$ENGINE" ]] && ok "engine: $ENGINE" || true
}

# ----------------------------------------------------------------- voice and accent
nome_lingua() {
    case "$1" in
        it) printf 'Italian' ;;
        en) printf 'English' ;;
        *)  printf '%s' "$1" ;;
    esac
}

# The language of the selection, if there is only one: with more languages the voice cannot
# be a single one, and the converter asks for it book by book.
lingua_unica() {
    local b l lingue="" quante
    for b in $SELECTED; do
        IFS='|' read -r _ _ l _ <<<"$(book_paths "$b")"
        case " $lingue " in *" $l "*) ;; *) lingue="$lingue $l" ;; esac
    done
    # shellcheck disable=SC2086
    set -- $lingue
    [[ $# -eq 1 ]] && printf '%s' "$1"
    return 0
}

# The engine the converter would choose on its own, in the same order.
motore_auto() {
    local tabella e
    tabella="$($PY scripts/txt2mp3.py --list-engines 2>/dev/null || true)"
    for e in piper say sapi espeak; do
        if grep -qE "^${e}[[:space:]].*[[:space:]]available$" <<<"$tabella"; then
            printf '%s' "$e"; return 0
        fi
    done
}

# The accents the engine has for this language: en_US, en_GB, en_IN, ...
accenti_motore() {
    local lang="$1" eng="$2"
    { $PY scripts/txt2mp3.py --list-voices --lang "$lang" --engine "$eng" 2>/dev/null || true; } \
        | grep -oE '[a-z]{2}_[A-Z]{2}' | sort -u | tr '\n' ' ' | sed 's/ *$//'
}

# Indian English: what really exists, engine by engine.
indiano() {
    local lang="$1" risposta=""
    if [[ "$lang" != en ]]; then
        warn "the Indian English voices speak English; this book is $(nome_lingua "$lang")"
        return 0
    fi
    printf '\n'
    printf '  piper     no Indian English voice: its catalogue for English is %s\n' "$(accenti_motore en piper)"
    printf '  kokoro    no Indian English either: it has Hindi voices (hf_alpha, hf_beta)\n'
    printf '  melotts   has EN-INDIA, but it needs torch installed, a large download\n'
    if command -v say >/dev/null 2>&1 \
       && $PY scripts/txt2mp3.py --list-voices --lang en --engine say 2>/dev/null | grep -qE "^Tara( |$)"; then
        printf '  say       yes: Tara, female Indian English, and Aman and Rishi, male\n'
        read -r -p "  use Tara, with the say engine? [y/N] " risposta || true
        case "$risposta" in
            y|Y|yes|YES) VOICE="Tara"; ENGINE="say"; ok "voice: Tara  (say, en_IN, female)" ;;
            *) info "kept the current choice" ;;
        esac
    else
        printf '  say       not available on this system\n'
    fi
}

# Asks for the voice and its engine: choosing Tara uses say, not piper.
menu_voice() {
    local lang="$1" eng risposta="" nome="" accenti
    eng="${ENGINE:-$(motore_auto)}"
    [[ -n "$eng" ]] || eng="piper"
    accenti="$(accenti_motore "$lang" "$eng")"
    printf '\n'
    info "which voice?   language: $(nome_lingua "$lang")   engine: $eng"
    printf '  accents in this catalogue: %s\n' "${accenti:-none}"
    printf '  1) hear the voices and pick one   (lists them all; downloads only what you ask to hear)\n'
    printf '  2) use the default voice for this engine\n'
    printf '  3) Indian English, female\n'
    printf '  4) type the name of a voice\n'
    read -r -p "  number [Enter = 2]: " risposta || true
    case "$risposta" in
        1)
            $PY scripts/txt2mp3.py --preview-voices --lang "$lang" --engine "$eng" || true
            read -r -p "  name of the voice you liked (Enter = default): " nome || true
            if [[ -n "$nome" ]]; then VOICE="$nome"; ENGINE="$eng"; fi
            ;;
        3) indiano "$lang" ;;
        4)
            printf '  piper: en_GB-alan-medium, en_US-lessac-medium   say: Tara, Samantha   kokoro: af_heart\n'
            read -r -p "  voice name: " nome || true
            if [[ -n "$nome" ]]; then VOICE="$nome"; ENGINE="$eng"; fi
            ;;
        *) : ;;
    esac
    [[ -n "$VOICE" ]] && ok "voice: $VOICE  (engine $ENGINE)" || ok "voice: the default one for $eng"
    return 0
}

# Synthesises one short sample and times it: how many seconds of audio the
# engine produces per second of wall time, with a single job.
misura_velocita() {
    local lang="$1" tmp t0 t1 elapsed mp3 dur voicearg=""
    [[ -n "$VOICE" ]] && voicearg="--voice $VOICE"
    tmp="$(mktemp -d 2>/dev/null)" || return 1
    cat >"$tmp/prova.txt" <<'PROBA'
Make the scene safe before you touch the patient. Traffic, fire, electricity, water and violence are the hazards that hurt rescuers, and a responder who is hurt cannot help anyone. Once the scene is safe, look at the patient as a whole, and ask what the mechanism of injury tells you about what may be broken inside. Control catastrophic bleeding before anything else, because a patient can die from a wound in minutes. Then assess the airway, the breathing, the circulation and the level of consciousness, expose the patient to find every injury, and keep the patient warm throughout. Write down what you did and when you did it.
PROBA
    t0="$($PY -c 'import time; print(time.time())' 2>/dev/null)" || { rm -rf "$tmp"; return 1; }
    PYTHONDONTWRITEBYTECODE=1 $PY scripts/txt2mp3.py "$tmp/prova.txt" --lang "$lang" \
        -o "$tmp/out" --no-prompt --jobs 1 $engine_args $voicearg >/dev/null 2>&1 || { rm -rf "$tmp"; return 1; }
    t1="$($PY -c 'import time; print(time.time())' 2>/dev/null)" || { rm -rf "$tmp"; return 1; }
    mp3="$(find "$tmp/out" -maxdepth 1 -name '*.mp3' 2>/dev/null | head -1)"
    dur="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$mp3" 2>/dev/null | head -1)"
    rm -rf "$tmp"
    [[ -n "$dur" ]] || return 1
    elapsed="$(awk -v a="$t0" -v b="$t1" 'BEGIN{printf "%.2f", b - a}')"
    awk -v au="$dur" -v el="$elapsed" 'BEGIN{ if (el > 0.2) printf "%.1f", au / el; else exit 1 }'
}

# Tells the user how much audio there is, how long it should take, and asks.
stima_e_conferma() {
    local tot_w=0 b w lang="" h audio_s ratio pareti risposta=""
    for b in $SELECTED; do
        w="$(book_words "$b")"
        tot_w=$(( tot_w + w ))
        IFS='|' read -r _ _ lang _ <<<"$(book_paths "$b")"
    done
    if [[ "$tot_w" -le 0 ]]; then
        warn "could not count the words of the selection; skipping the estimate"
        return 0
    fi
    h="$(awk -v w="$tot_w" 'BEGIN{printf "%.1f", w/170/60}')"
    audio_s="$(awk -v w="$tot_w" 'BEGIN{printf "%.0f", w/170*60}')"
    printf '\n'
    info "what this run is going to cost you"
    printf '  text            %8s words, about %s hours of audio\n' "$(migliaia "$tot_w")" "$h"
    printf '  disk            about %s GB of intermediate WAV cache\n' "$needed_gb"
    printf '  parallel jobs   %s\n' "$JOBS"
    info "measuring the engine on one short sample, this takes a few seconds ..."
    if ratio="$(misura_velocita "$lang")" && [[ -n "$ratio" ]]; then
        pareti="$(awk -v a="$audio_s" -v r="$ratio" -v j="$JOBS" 'BEGIN{ printf "%.0f", a / (r * j) }')"
        printf '  measured speed  about %s times real time, with one job\n' "$ratio"
        printf '  so, roughly     %s of synthesizing, plus the joining of the MP3s\n' "$(human_time "$pareti")"
        printf '  first run only  adds the download of the voice, about 60 MB each\n'
        printf '\n'
        warn "that is an average measured here, on this machine, on a short sample:"
        warn "allow a wide margin, and remember that --jobs speeds it up until the cpu is full."
    else
        warn "could not measure the engine now: it may be missing, or no voice has been chosen yet"
        warn "the run itself prints progress with its own estimate as it goes"
    fi
    if [[ $ASSUME_YES -eq 1 || ! -t 0 ]]; then
        info "starting without asking (--yes, or not interactive)"
        return 0
    fi
    printf '\n'
    read -r -p "  start now? [y/N] " risposta || true
    case "$risposta" in
        y|Y|yes|YES) return 0 ;;
        *) info "nothing was synthesized. Run it again when you are ready."; exit 0 ;;
    esac
}

if [[ -z "$ENGINE" && -t 0 && $ASSUME_YES -eq 0 && $DRY -eq 0 && $PREVIEW -eq 0 && $LIST_VOICES -eq 0 ]]; then
    menu_engine
fi
if [[ -z "$VOICE" && -t 0 && $ASSUME_YES -eq 0 && $DRY -eq 0 && $PREVIEW -eq 0 && $LIST_VOICES -eq 0 ]]; then
    _lingua="$(lingua_unica)"
    if [[ -n "$_lingua" ]]; then
        menu_voice "$_lingua"
    else
        info "the selection mixes Italian and English: the voice is chosen by the converter, book by book"
    fi
fi

engine_args=""
[[ -n "$ENGINE" ]] && engine_args="$engine_args --engine $ENGINE"
[[ -n "$PIPER_MODEL" ]] && engine_args="$engine_args --piper-model $PIPER_MODEL"
[[ -n "$PIPER_DIR" ]] && engine_args="$engine_args --piper-dir $PIPER_DIR"

# Speech engine.
if [[ $LIST_VOICES -eq 1 ]]; then
    info "speech engines on this machine"
    PYTHONDONTWRITEBYTECODE=1 $PY scripts/txt2mp3.py --list-engines || true
    printf '\n'
    info "Italian voices"
    # shellcheck disable=SC2086
    PYTHONDONTWRITEBYTECODE=1 $PY scripts/txt2mp3.py --list-voices --lang it $engine_args || true
    printf '\n'
    info "English voices"
    # shellcheck disable=SC2086
    PYTHONDONTWRITEBYTECODE=1 $PY scripts/txt2mp3.py --list-voices --lang en $engine_args || true
    exit 0
fi

if [[ $DRY -eq 0 ]]; then
    case "$ENGINE" in
        say)
            command -v say >/dev/null 2>&1 || die "'say' not found: it only exists on macOS"
            ;;
        sapi)
            [[ "$PLATFORM" == windows ]] || warn "--engine sapi only works on Windows"
            ;;
        espeak)
            command -v espeak-ng >/dev/null 2>&1 || command -v espeak >/dev/null 2>&1 \
                || installa espeak "espeak-ng is missing"
            ;;
        piper)
            # piper is the default engine. There is no need to specify the model: if
            # it is missing, the converter downloads the right one for the language.
            command -v piper >/dev/null 2>&1 || modulo_presente piper \
                || installa piper "piper is missing"
            ;;
        kokoro)
            modulo_presente kokoro_onnx || modulo_presente kokoro || die "Kokoro is not installed, and it needs Python 3.10 or newer:
onnxruntime >= 1.20 has no wheel for Python 3.9. Give it its own environment:

       python3.12 -m venv .tools/venv-kokoro
       .tools/venv-kokoro/bin/pip install kokoro-onnx

This launcher picks .tools/venv-kokoro up by itself for --engine kokoro."
            ;;
        melotts)
            modulo_presente melo || die "MeloTTS is missing. It must come from GitHub, not PyPI:
       python3 -m pip install git+https://github.com/myshell-ai/MeloTTS.git
       python3 -m unidic download
       It pulls in torch, several gigabytes. It is also the only engine with an
       Indian English accent: --engine melotts --voice EN-INDIA"
            ;;
        "")
            info "speech engines found on this machine:"
            PYTHONDONTWRITEBYTECODE=1 $PY scripts/txt2mp3.py --list-engines || true
            ;;
    esac
fi

# Preview: lists the voices and plays only the one you choose, without downloading
# anything in advance. It converts nothing.
if [[ $PREVIEW -eq 1 ]]; then
    info "voices: pick one to hear the sample phrase (it / en switch language)"
    PYTHONDONTWRITEBYTECODE=1 $PY scripts/txt2mp3.py --preview-voices $engine_args \
        || warn "anteprima non riuscita"
    exit 0
fi

# ffmpeg and ffprobe.
missing_ffmpeg=0
command -v ffmpeg  >/dev/null 2>&1 || missing_ffmpeg=1
command -v ffprobe >/dev/null 2>&1 || missing_ffmpeg=1
if [[ $missing_ffmpeg -eq 1 ]]; then
    if [[ $DRY -eq 1 ]]; then
        warn "ffmpeg/ffprobe missing, but --dry-run needs neither"
    else
        installa ffmpeg "ffmpeg or ffprobe is missing"
        command -v ffmpeg >/dev/null 2>&1 || die "ffmpeg still not on PATH; open a new shell and re-run"
        ok "ffmpeg installed"
    fi
else
    ok "ffmpeg ready"
fi

# Parallel jobs.
if [[ -z "$JOBS" ]]; then
    cores=""
    if [[ "$PLATFORM" == macos ]]; then
        cores="$(sysctl -n hw.ncpu 2>/dev/null || true)"
    elif [[ "$PLATFORM" == windows ]]; then
        cores="${NUMBER_OF_PROCESSORS:-}"
    fi
    [[ -z "$cores" ]] && cores="$(nproc 2>/dev/null || true)"
    [[ -z "$cores" ]] && cores=4
    JOBS=$(( cores < 8 ? cores : 8 ))
fi
[[ "$JOBS" =~ ^[0-9]+$ && "$JOBS" -ge 1 ]] || die "--jobs must be a positive integer"

# Free space: the chunk cache is the big consumer (several GB per book). The
# estimate is derived from the length of each book instead of a hardcoded table,
# so a book added to the registry is measured like the others: about 44 kB of
# 16-bit mono WAV per second of speech, plus about 8 kB per second of MP3.
free_gb="$(df -Pk "$ROOT" 2>/dev/null | awk 'NR==2 {printf "%d", $4/1024/1024}')"
needed_gb=0
for book in $SELECTED; do
    gb="$(awk -v w="$(book_words "$book")" 'BEGIN{ printf "%d", (w / 170 * 60 * 52000) / 1e9 + 0.5 }')"
    [[ "$gb" =~ ^[0-9]+$ && "$gb" -ge 1 ]] || gb=1
    needed_gb=$(( needed_gb + gb ))
done
if [[ "$free_gb" =~ ^[0-9]+$ ]]; then
    info "disk: ${free_gb} GB free, about ${needed_gb} GB needed for the synthesis cache"
    if [[ "$free_gb" -lt "$needed_gb" ]]; then
        if [[ $ASSUME_YES -eq 1 ]]; then
            warn "proceeding anyway because --yes was given; a full disk will abort the run"
        else
            die "not enough free space. Free some, or re-run with --prune-cache,
       or pass --yes to try anyway. The cache can be deleted afterwards with:
         rm -rf books/*/audio/.cache"
        fi
    fi
else
    warn "could not read the free space of $ROOT; skipping the disk check"
    warn "the synthesis cache needs about ${needed_gb} GB; --prune-cache frees it afterwards"
fi

# ----------------------------------------------------------------- per book
run_book() {
    local book="$1"
    local text src lang_code title builder front indice acr toc
    local audio_dir build_cmd conv_cmd args

    # Everything about this book comes from books/books.tsv and its folder shape.
    IFS='|' read -r text src lang_code title builder front indice acr toc \
        <<<"$(book_paths "$book")"
    [[ -n "$text" && -n "$src" && -n "$lang_code" && -n "$builder" ]] \
        || die "internal error: could not resolve the paths of '$book' from $REGISTRY"
    audio_dir="books/$book/audio"

    build_cmd="$PY $builder --capitoli '$src' --out '$text' --indice '$indice' --strict"
    [[ -n "$front" ]] && build_cmd="$build_cmd --front-matter '$front'"
    [[ -n "$acr"   ]] && build_cmd="$build_cmd --acronyms-ok $acr"
    [[ -n "$toc"   ]] && build_cmd="$build_cmd --toc-noun $toc"
    conv_cmd="$PY scripts/txt2mp3.py '$text' --lang $lang_code"

    [[ -n "$OUT" ]] && audio_dir="$OUT"

    printf '\n'
    info "book: $book  ($lang_code)  ->  $audio_dir"

    if [[ $DO_BUILD -eq 1 && $DRY -eq 1 && -f "$text" ]]; then
        # A dry run is meant to be fast: reuse the text that is already there.
        info "keeping the existing $text (--dry-run does not rebuild it)"
    elif [[ $DO_BUILD -eq 1 ]]; then
        info "building $text"
        PYTHONDONTWRITEBYTECODE=1 eval "$build_cmd"
        ok "text rebuilt"
    else
        info "skipping the rebuild (--no-build)"
        [[ -f "$text" ]] || die "$text does not exist; drop --no-build"
    fi

    local manifest="$audio_dir/.manifest.json"
    if [[ -f "$manifest" && "$text" -nt "$manifest" && $FORCE -eq 0 && $DRY -eq 0 ]]; then
        warn "the text is newer than the audio manifest: existing MP3s may be stale"
        warn "add --force to re-encode everything from the cached chunks"
    fi

    local args="--jobs $JOBS"
    [[ $SINGLE -eq 1 ]] && args="$args --single"
    [[ $FORCE  -eq 1 ]] && args="$args --force"
    [[ $DRY    -eq 1 ]] && args="$args --dry-run"
    [[ -n "$RATE"    ]] && args="$args --rate $RATE"
    [[ -n "$BITRATE" ]] && args="$args --bitrate $BITRATE"
    [[ -n "$VOICE"   ]] && args="$args --voice $VOICE"
    [[ -n "$ONLY"    ]] && args="$args --only $ONLY"
    [[ $NO_PROMPT  -eq 1 ]] && args="$args --no-prompt"
    [[ $RESET_VOICE -eq 1 ]] && args="$args --reset-voice"

    info "converting: $conv_cmd -o $audio_dir $args$engine_args"
    # shellcheck disable=SC2086
    PYTHONDONTWRITEBYTECODE=1 eval "$conv_cmd -o '$audio_dir' $args$engine_args"

    if [[ $PRUNE_CACHE -eq 1 && $DRY -eq 0 ]]; then
        if [[ -d "$audio_dir/.cache" ]]; then
            rm -rf "$audio_dir/.cache"
            ok "pruned $audio_dir/.cache"
        fi
    fi

    if [[ $DRY -eq 0 && -d "$audio_dir" ]]; then
        local n size integral
        n="$(find "$audio_dir" -maxdepth 1 -name '*.mp3' | wc -l | tr -d ' ')"
        size="$(du -sh "$audio_dir" 2>/dev/null | awk '{print $1}')"
        ok "$n MP3 files, $size total in $audio_dir"
        integral="$(find "$audio_dir" -maxdepth 1 -name '*-integrale.mp3' | head -1)"
        if [[ -n "$integral" ]]; then
            ok "single file: $(basename "$integral") ($(du -h "$integral" | awk '{print $1}'))"
        fi
    fi
}

if [[ $DRY -eq 0 ]]; then
    stima_e_conferma
fi

for book in $SELECTED; do
    run_book "$book"
done

printf '\n'
info "done. Playlists (.m3u) and .manifest.json sit next to the MP3s."
if [[ $DRY -eq 0 && $PRUNE_CACHE -eq 0 ]]; then
    info "the .cache/ directories hold intermediate WAVs and can be deleted at any time."
fi
