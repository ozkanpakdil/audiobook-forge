#!/usr/bin/env python3
"""Write the per-batch list of questions with the longest-choice giveaway.

For every batch that exists, writes `batches/deck<N>/batch<M>.rebalance.txt`
listing the questions whose correct answer is the strictly longest choice and
more than 25% longer than the median distractor — the list a writer works from
when rebalancing. These files are generated, not hand-written.
"""
from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
GATE = 1.25


def flagged(questions: list[dict]) -> list[tuple[int, dict, list[int], int]]:
    out = []
    for i, q in enumerate(questions):
        lens = [len(c) for c in q["choices"]]
        others = [lens[j] for j in range(5) if j != q["answer"]]
        median = sorted(others)[2]
        if lens[q["answer"]] == max(lens) and lens[q["answer"]] > GATE * median:
            out.append((i, q, lens, median))
    return out


def main() -> int:
    manifest = json.load(open(os.path.join(ROOT, "batches", "manifest.json"), encoding="utf-8"))
    written = 0
    for spec in manifest:
        path = os.path.join(ROOT, spec["out"])
        if not os.path.exists(path):
            continue
        data = json.load(open(path, encoding="utf-8"))
        questions = data["questions"]
        hits = flagged(questions)
        out = os.path.join(ROOT, spec["out"].replace(".json", ".rebalance.txt"))
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(f"# Lotto {spec['out']}\n")
            fh.write(f"# Argomento: {spec['topic']}\n")
            fh.write(f"# Slide {spec['slide_from']}-{spec['slide_to']}\n")
            fh.write(f"# Domande segnalate: {len(hits)}/{len(questions)} "
                     f"({len(hits) / len(questions):.0%})\n")
            fh.write("# La risposta corretta e l'alternativa piu lunga. "
                     "Ribilancia le cinque alternative.\n\n")
            for i, q, lens, median in hits:
                fh.write(f"## [{i}] {q['id']}  (indice corretto {q['answer']} = "
                         f"{'ABCDE'[q['answer']]}, lunghezza {lens[q['answer']]} "
                         f"contro mediana {median})\n")
                fh.write(f"Domanda: {q['q']}\n")
                for j, c in enumerate(q["choices"]):
                    mark = "CORRETTA" if j == q["answer"] else "         "
                    fh.write(f"  {mark} {'ABCDE'[j]}) [{len(c):3d}] {c}\n")
                fh.write("\n")
        written += 1
    print(f"wrote {written} rebalance lists")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
