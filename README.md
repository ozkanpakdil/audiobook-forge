# Five free books, read aloud — and the pipeline that reads them

This repository holds the complete text of five educational books written for
listening rather than reading, together with the cross-platform pipeline that
turns any of them into MP3 audiobooks on your own machine.

**No audio is stored here, on purpose.** Every listener generates it locally, which
keeps the repository at about 18 MB and lets you pick the voice and the accent you
like instead of accepting mine.

## The books

Every book lives in its own folder under `books/`, with the same shape:

| Book | Folder | Language | Sections | Words | Audio |
|---|---|---|---|---|---|
| Anatomia umana — corso narrato | `books/anatomia-umana/` | Italian | 55 chapters | 207,486 | ~20.3 h |
| Tropical Medicine: A Practical Manual | `books/tropical-medicine/` | English | 65 chapters, 4 appendices | 339,348 | ~33.3 h |
| Hospital Equipment: A Practical Guide | `books/hospital-equipment/` | English | 78 chapters, 5 appendices | 371,384 | ~36.4 h |
| Clinical Diagnosis: A Practical Manual | `books/clinical-diagnosis/` | English | 77 chapters, 5 appendices | 349,131 | ~34.2 h |
| Emergency Wound and Trauma Care | `books/emergency-trauma-care/` | English | 49 chapters, appendices in progress | 221,822 | ~21.7 h |
| **Total** | | | | **1,489,171** | **~146 h** |

The books are written to be understood by ear: chapters of 3,800 to 4,400 words, no
tables, no bullet points, no symbols, acronyms spelled out letter by letter, and a
plain summary at the end of every chapter. The writing contracts that enforce this
are in the repository, next to the chapters they govern.

## Quick start

You need Python 3 and ffmpeg. Nothing else is mandatory.

```bash
git clone <this repository> && cd <this repository>

./scripts/make_all_audio.sh              # asks, measures, then generates
./scripts/make_all_audio.sh --dry-run    # shows the plan and the durations only
./scripts/make_all_audio.sh --list-books # what there is, and where it lives
```

The launcher guides you through four steps before it spends any of your CPU:

1. **Which book** — it lists the five, with the words and the hours of audio in each.
2. **Which engine** — it lists them and marks the ones installed on your machine.
3. **Which voice and accent** — it lists the accents that engine has, can play the
   voices one by one so you can hear them, and takes a name you type. Choosing the
   Indian English voice switches to the engine that can actually pronounce it.
4. **How long it will take** — it synthesises one short sample, times it, measures the
   audio it produced, and extrapolates to the whole book, then waits for your yes.

Measured on an Apple laptop: piper produces about 12 times real time per process, so
the 34-hour Clinical Diagnosis book is roughly 40 minutes of work on 4 processes.

Options: `--book NAME`, `--engine NAME`, `--voice NAME`, `--jobs N`, `--only 1,24,50`,
`--force`, `--prune-cache`, `--list-voices`, `--list-books`, `--preview-voices`,
`--dry-run`, `--yes`, and `--help` for the rest. On a terminal with no options it asks
everything; with `--yes`, or without a terminal, it asks nothing and just runs.

`--book` takes a book's folder name or one of its short aliases, so
`--book anatomia-umana` and `--book it` are the same request, and `--book all` is the
default. The same launcher runs on Windows as `.\scripts\make_all_audio.ps1`, and takes
`-ListBooks` instead of `--list-books`.

## Engines

| Engine | Platform | Notes |
|---|---|---|
| `piper` | all | default, neural voices, 177 in the catalogue, downloaded on demand |
| `say` | macOS | system voices, no installation |
| `sapi` | Windows | System.Speech voices, no installation |
| `espeak` | Linux | very fast, robotic, good for checking a text |
| `kokoro` | all | opt-in, needs its own environment |
| `melotts` | all | opt-in, needs torch |

## Voices and accents

Voices are chosen per language: Italian for the anatomy course, English for the other
four. The pipeline knows the language of each book and offers what fits.

- **piper** — English voices are `en_GB` and `en_US`; Italian is `it_IT`. There is no
  Indian English voice in its catalogue.
- **say** on macOS adds `en_IN`, `en_AU`, `en_IE`, `en_ZA`. The female Indian English
  voice is **Tara**; Aman and Rishi are the male ones.
- **kokoro** — no Indian English; it has Hindi voices (`hf_alpha`, `hf_beta`).
- **melotts** — has `EN-INDIA`, but needs torch installed, which is a large download.

## How the books were written

Every book carries its own contract in its `content/` folder, named `PLAN.md`, and a
list of one brief per section named `OUTLINE.md`:

- `books/anatomia-umana/content/` — the Italian anatomy course
- `books/tropical-medicine/content/`, `books/hospital-equipment/content/`,
  `books/clinical-diagnosis/content/`, `books/emergency-trauma-care/content/`

The contracts fix the length of a section, the vocabulary, the numbers that must not
appear, the acronyms allowed as spoken short forms, and the rules each genre needs.
The medical contracts forbid doses, routes, and anything that would read as a
prescription: the books teach decisions, not drugs.

`build_book_en.py` and `build_book.py` assemble the chapters into one text and check
every rule, which is why the chapters look the way they do. Their checks are the
reason the books listen well, and the reason a book cannot be quietly edited into
something inconsistent.

### Where the texts come from

The books are original prose written for this repository. They are not copies,
translations or abridgements of any published work, and no copyrighted text was used
to produce them. The Italian anatomy course is laid out in the classical order of
descriptive anatomy — osteology, arthrology, myology, angiology, splanchnology,
neurology, the sense organs — the same order used by the 1918 edition of Gray's
*Anatomy of the Human Body*, which is in the public domain; it is neither a copy nor
a translation of that work. The four English books follow outlines and writing
contracts written for the project. Facts about anatomy, disease and equipment are not
copyrightable; the expression in these pages is ours, and is licensed as described
below.

## Repository layout

```
scripts/                     the pipeline: launchers, text normalisation, book
                             assembly, MP3 conversion
books/
  books.tsv                  the registry: the one place a book is declared
  anatomia-umana/            the Italian anatomy course
  tropical-medicine/         Tropical Medicine
  hospital-equipment/        Hospital Equipment
  clinical-diagnosis/        Clinical Diagnosis
  emergency-trauma-care/     Emergency Wound and Trauma Care
requirements.txt             explains that the pipeline needs no third-party packages
```

Every book folder has the same shape, which is why neither launcher names a single
path of any single book:

```
books/<slug>/content/PLAN.md          the style contract
books/<slug>/content/OUTLINE.md       the briefs, one per section
books/<slug>/content/capitoli/*.md    the sections themselves
books/<slug>/content/FRONT_MATTER.md  front matter, when the book has its own
books/<slug>/out/<slug>.txt           the assembled book
books/<slug>/out/index.txt            the readable index
books/<slug>/audio/                   the MP3s you generate (never committed)
```

`books/books.tsv` lists, one line per book, the slug, the language, the noun its
spoken table of contents uses, the short forms it allows, a title and its aliases.
Both `make_all_audio.sh` and `make_all_audio.ps1` read that file, so the two cannot
disagree about which books exist or where they are. To add a sixth book: copy a
book folder to `books/<new-slug>/`, add one line to `books/books.tsv`, and both
launchers pick it up, `--book all` included.

## Licence

The code in `scripts/` is MIT, see `LICENSE`. The texts — the books, their contracts
and their briefs — are Creative Commons Attribution 4.0, see `LICENSE-TEXT`. Copy
them, narrate them, translate them, sell them; the licence asks only that you say
where they came from.

## Disclaimer

Everything here — the books and most of the code — was generated by AI language
models, and **no clinician has reviewed it**. These are educational books, not
medical advice, and they do not replace training, certification, supervision, local
protocol or the law where you work. Read `DISCLAIMER.md` before using anything here
on a patient.
