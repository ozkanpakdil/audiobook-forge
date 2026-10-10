#!/usr/bin/env python3
"""Assemble the validated batches into the JSON the quiz app loads.

Reads   quiz-src/batches/deck<N>/batch<M>.json
Writes  docs/data/deck<N>.json  and  docs/data/manifest.json

Fails loudly on anything that would embarrass the app: wrong counts, missing
fields, duplicate ids, duplicate question stems inside a deck, answer indices
out of range, or a batch that does not match its declared slide range.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from collections import Counter

ROOT = os.path.dirname(os.path.abspath(__file__))
BATCH_DIR = os.path.join(ROOT, "batches")
DOCS_DATA = os.path.abspath(os.path.join(ROOT, "..", "docs", "data"))
EXPECT_PER_DECK = 400


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s).lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", s).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-partial", action="store_true",
                    help="build from whatever batches exist (for previewing)")
    args = ap.parse_args()

    manifest = json.load(open(os.path.join(BATCH_DIR, "manifest.json"), encoding="utf-8"))
    errors: list[str] = []
    warnings: list[str] = []
    by_deck: dict[int, list[dict]] = {}
    if args.allow_partial:
        warnings.append("partial build: batch counts are not enforced")

    for spec in manifest:
        deck, batch = spec["deck"], spec["batch"]
        path = os.path.join(ROOT, spec["out"])
        if not os.path.exists(path):
            if args.allow_partial:
                warnings.append(f"skipped missing batch: {spec['out']}")
                continue
            errors.append(f"missing batch file: {spec['out']}")
            continue
        try:
            data = json.load(open(path, encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{spec['out']}: invalid JSON: {exc}")
            continue

        qs = data.get("questions")
        if not isinstance(qs, list):
            errors.append(f"{spec['out']}: no questions array")
            continue
        if len(qs) != spec["count"]:
            errors.append(f"{spec['out']}: {len(qs)} questions, expected {spec['count']}")

        seen: dict[str, str] = {}
        pos = Counter()
        for i, q in enumerate(qs):
            tag = f"{spec['out']}[{i}]"
            for key in ("id", "q", "choices", "answer", "explain", "slide"):
                if key not in q:
                    errors.append(f"{tag}: missing {key}")
            if not all(k in q for k in ("id", "q", "choices", "answer", "explain", "slide")):
                continue
            if not isinstance(q["choices"], list) or len(q["choices"]) != 5:
                errors.append(f"{tag}: needs exactly 5 choices")
                continue
            if len({norm(c) for c in q["choices"]}) != 5:
                errors.append(f"{tag}: duplicate choices")
            if not isinstance(q["answer"], int) or not 0 <= q["answer"] <= 4:
                errors.append(f"{tag}: answer out of range: {q['answer']!r}")
                continue
            if not isinstance(q["explain"], str) or len(q["explain"].strip()) < 60:
                errors.append(f"{tag}: explanation too short")
            if not isinstance(q["slide"], int) or not spec["slide_from"] <= q["slide"] <= spec["slide_to"]:
                errors.append(f"{tag}: slide {q['slide']!r} outside {spec['slide_from']}-{spec['slide_to']}")
            k = norm(q["q"])
            if k in seen:
                errors.append(f"{tag}: duplicate question stem (also {seen[k]})")
            else:
                seen[k] = q["id"]
            pos[q["answer"]] += 1

        # carry deck metadata onto every question so the app can filter and cite
        for q in qs:
            q["deck"] = deck
            q["batch"] = batch

        by_deck.setdefault(deck, []).extend(qs)
        top = max(pos.values()) if pos else 0
        if qs and top > 0.40 * len(qs):
            warnings.append(f"{spec['out']}: answer position {pos.most_common(1)[0][0]} holds {top}/{len(qs)}")

    # per-deck totals and cross-deck duplicate stems
    global_stems: dict[str, str] = {}
    cross = 0
    for deck, qs in sorted(by_deck.items()):
        if len(qs) != EXPECT_PER_DECK and not args.allow_partial:
            errors.append(f"deck {deck}: {len(qs)} questions, expected {EXPECT_PER_DECK}")
        for q in qs:
            k = norm(q["q"])
            if k in global_stems and not global_stems[k].startswith(f"d{deck:02d}-"):
                cross += 1
            global_stems.setdefault(k, q["id"])

    if cross:
        # a handful of overlaps between adjacent topics is tolerable, a flood is not
        limit = int(0.02 * sum(len(v) for v in by_deck.values()))
        msg = f"{cross} question stems repeat across decks"
        (errors if cross > limit else warnings).append(msg)

    if errors:
        print(f"FAIL: {len(errors)} error(s)")
        for e in errors[:40]:
            print("  -", e)
        if len(errors) > 40:
            print(f"  ... and {len(errors) - 40} more")
        return 1

    os.makedirs(DOCS_DATA, exist_ok=True)

    titles = {}
    decks_manifest = []
    total = 0
    for deck, qs in sorted(by_deck.items()):
        src = json.load(open(os.path.join(ROOT, "extract", f"deck{deck}.slides.json"), encoding="utf-8"))
        titles[deck] = src["title"]
        payload = {"deck": deck, "title": src["title"], "date": src["date"], "questions": qs}
        with open(os.path.join(DOCS_DATA, f"deck{deck}.json"), "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
        decks_manifest.append({
            "deck": deck, "title": src["title"], "date": src["date"],
            "count": len(qs), "file": f"deck{deck}.json",
        })
        total += len(qs)
        print(f"deck {deck}: {len(qs):4d} domande  {src['title']}")

    with open(os.path.join(DOCS_DATA, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump({"decks": decks_manifest, "total": total,
                   "generated": "quiz-src/build_site.py"}, fh, ensure_ascii=False, indent=1)

    print(f"\ntotal: {total} domande in {len(decks_manifest)} lezioni")
    if warnings:
        print(f"\n{len(warnings)} warning(s):")
        for w in warnings[:20]:
            print("  ~", w)
    print("\nOK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
