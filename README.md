# Five free books, read aloud — and the pipeline that reads them

This repository holds the complete text of five educational books written for
listening rather than reading, together with the cross-platform pipeline that
turns any of them into MP3 audiobooks on your own machine.

**No audio is stored here, on purpose.** Every listener generates it locally, which
keeps the repository at about 18 MB and lets you pick the voice and the accent you
like instead of accepting mine.

## The books

| Book | Language | Sections | Words | Audio |
|---|---|---|---|---|
| Anatomia umana — corso narrato | Italian | 55 chapters | 207,486 | ~20.3 h |
| Tropical Medicine: A Practical Manual | English | 65 chapters, 4 appendices | 339,348 | ~33.3 h |
| Hospital Equipment: A Practical Guide | English | 78 chapters, 5 appendices | 371,384 | ~36.4 h |
| Clinical Diagnosis: A Practical Manual | English | 77 chapters, 5 appendices | 349,131 | ~34.2 h |
| Emergency Wound and Trauma Care | English | 49 chapters, appendices in progress | 221,822 | ~21.7 h |
| **Total** | | | **1,489,171** | **~146 h** |

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
`--force`, `--prune-cache`, `--list-voices`, `--preview-voices`, `--dry-run`, `--yes`,
and `--help` for the rest. On a terminal with no options it asks everything; with
`--yes`, or without a terminal, it asks nothing and just runs.

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

Every book has a contract in its `content/` folder, named `PLAN.md`, and a list of
one brief per section named `OUTLINE.md`:

- `content/` — the Italian anatomy course
- `tropical/content/`, `equipment/content/`, `diagnosis/content/`, `trauma/content/`

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
scripts/            the pipeline: launchers, text normalisation, book assembly, MP3 conversion
content/            the Italian anatomy course: contract, briefs, chapters
out/anatomia.txt    the assembled book
tropical/           Tropical Medicine: content/ and out/
equipment/          Hospital Equipment: content/ and out/
diagnosis/          Clinical Diagnosis: content/ and out/
trauma/             Emergency Wound and Trauma Care: content/ and out/
requirements.txt    explains that the pipeline needs no third-party packages
```

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
