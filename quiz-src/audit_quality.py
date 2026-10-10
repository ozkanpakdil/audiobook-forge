#!/usr/bin/env python3
"""Quality audit for the assembled quiz bank.

Reports the things a large generated bank gets wrong even when every batch
passes its own validator:

  * near-duplicate questions, including across decks, by token overlap
  * the "longest choice is the answer" giveaway, which lets a student score
    without knowing anything
  * the distribution of correct-answer positions
  * explanation length, and explanations too short to teach anything
  * absolute wording ("sempre", "mai", "tutti") concentrated in the correct
    answer, which is another way to guess without knowing
  * choice-count and structural drift

Exit code is 0 unless a hard threshold is breached, so it can gate a build.
"""
from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.abspath(os.path.join(ROOT, "..", "docs", "data"))

STOP = {
    "il", "lo", "la", "i", "gli", "le", "un", "uno", "una", "di", "a", "da", "in",
    "con", "su", "per", "tra", "fra", "e", "o", "che", "chi", "cui", "non", "si",
    "del", "dello", "della", "dei", "degli", "delle", "al", "allo", "alla", "ai",
    "agli", "alle", "dal", "dallo", "dalla", "dai", "dagli", "dalle", "nel", "nello",
    "nella", "nei", "negli", "nelle", "sul", "sullo", "sulla", "sui", "sugli",
    "sulle", "è", "sono", "essere", "viene", "vengono", "quale", "quali", "come",
    "quando", "dove", "più", "meno", "anche", "the", "of", "is", "a",
}
ABSOLUTE = ("sempre", "mai", "tutti", "tutte", "nessun", "nessuna", "solo", "soltanto")


def norm_tokens(s: str) -> list[str]:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return [w for w in s.split() if w and w not in STOP]


def jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def main() -> int:
    manifest = json.load(open(os.path.join(DATA, "manifest.json"), encoding="utf-8"))
    hard_fail: list[str] = []
    soft: list[str] = []
    total = 0

    all_q: list[dict] = []

    for entry in manifest["decks"]:
        deck = entry["deck"]
        payload = json.load(open(os.path.join(DATA, entry["file"]), encoding="utf-8"))
        qs = payload["questions"]
        total += len(qs)
        print(f"\n=== Lezione {deck} — {entry['title']}  ({len(qs)} domande) ===")

        pos = Counter(q["answer"] for q in qs)
        print("  posizioni corrette: " + "  ".join(f"{'ABCDE'[i]}={pos.get(i, 0)}" for i in range(5)))
        top = max(pos.values())
        if top > 0.35 * len(qs):
            soft.append(f"deck {deck}: position {pos.most_common(1)[0][0]} holds {top}/{len(qs)} answers")

        # The longest-choice giveaway. Report the same rule the per-batch
        # validator enforces (strictly longest and >25% beyond the median
        # distractor) as the headline number, and ties separately: a tie is far
        # less exploitable than a unique longest option.
        strict = 0
        tie = 0
        for q in qs:
            lens = [len(c) for c in q["choices"]]
            others = [lens[i] for i in range(5) if i != q["answer"]]
            median = sorted(others)[2]
            if lens[q["answer"]] == max(lens):
                if lens[q["answer"]] > 1.25 * median:
                    strict += 1
                elif lens.count(lens[q["answer"]]) > 1:
                    tie += 1
        srate = strict / len(qs)
        print(f"  corretta strettamente più lunga (>25% oltre la mediana): "
              f"{strict}/{len(qs)}  ({srate:.0%}, atteso ~20-25%)")
        print(f"  corretta a pari merito per lunghezza: {tie}/{len(qs)}  ({tie / len(qs):.0%})")
        if srate > 0.30:
            soft.append(f"deck {deck}: the correct answer is the strictly longest choice "
                        f"in {srate:.0%} of questions")

        exlens = [len(q["explain"]) for q in qs]
        print(f"  spiegazione: min {min(exlens)}, mediana {sorted(exlens)[len(exlens) // 2]}, max {max(exlens)}")
        if min(exlens) < 120:
            soft.append(f"deck {deck}: shortest explanation is only {min(exlens)} chars")

        absrate = sum(
            1 for q in qs
            if any(w in norm_tokens(q["choices"][q["answer"]]) for w in ABSOLUTE)
        ) / len(qs)
        print(f"  risposta corretta con parole assolute: {absrate:.0%}")
        if absrate > 0.15:
            soft.append(f"deck {deck}: {absrate:.0%} of correct answers contain absolute wording")

        # near-duplicates inside the deck
        toks = [norm_tokens(q["q"]) for q in qs]
        dupes = 0
        for i in range(len(qs)):
            for j in range(i + 1, len(qs)):
                if jaccard(toks[i], toks[j]) > 0.80:
                    dupes += 1
                    soft.append(f"deck {deck}: near-duplicate stems {qs[i]['id']} / {qs[j]['id']}")
        print(f"  coppie di domande quasi identiche: {dupes}")

        for q in qs:
            q["_tokens"] = norm_tokens(q["q"])
            q["_deck"] = deck
        all_q.extend(qs)

    print(f"\n=== Totale: {total} domande ===")

    # near-duplicates across the whole bank
    cross = 0
    by_first: dict[str, list[dict]] = defaultdict(list)
    for q in all_q:
        by_first[q["_tokens"][0] if q["_tokens"] else ""].append(q)
    for qs in by_first.values():
        if len(qs) < 2:
            continue
        for i in range(len(qs)):
            for j in range(i + 1, len(qs)):
                if qs[i]["_deck"] == qs[j]["_deck"]:
                    continue
                if jaccard(qs[i]["_tokens"], qs[j]["_tokens"]) > 0.80:
                    cross += 1
                    soft.append(f"cross-deck near-duplicate: {qs[i]['id']} / {qs[j]['id']}")
    print(f"coppie quasi identiche fra lezioni diverse: {cross}")

    if total != 2000:
        hard_fail.append(f"expected 2000 questions, found {total}")

    if hard_fail:
        print(f"\nFAIL: {len(hard_fail)} hard problem(s)")
        for f in hard_fail:
            print("  -", f)
        return 1

    if soft:
        print(f"\n{len(soft)} thing(s) worth a look:")
        for s in soft[:40]:
            print("  ~", s)
        if len(soft) > 40:
            print(f"  ... and {len(soft) - 40} more")
    else:
        print("\nNo quality concerns found.")
    print("\nOK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
