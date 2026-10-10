#!/usr/bin/env python3
"""Validate one question batch produced for the Biochimica quiz.

Usage:
    python3 validate_batch.py batches/deck1/batch1.json --slides 19-35

Exits 0 and prints OK when the batch is valid, otherwise prints the problems
and exits 1.
"""
import argparse
import json
import re
import sys
import unicodedata

REQUIRED = {"id", "q", "choices", "answer", "explain", "slide"}
# A choice is banned when it *is* a compound answer or a blanket "all of the
# above", not merely when such a substring appears somewhere inside it — Italian
# "uova e burro" must not be mistaken for the option "A e B".
COMPOUND_RE = re.compile(r"^[a-e](\s*(?:,|e)\s*[a-e])+$")
BLANKET_RE = re.compile(r"^(?:tutte|tutti|nessuna|nessuno|nessun)\b")
BANNED_META = (
    "secondo la slide", "come visto a lezione", "nel lucido", "in questa slide",
    "nella slide", "secondo il lucido", "come da slide",
)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    # keep digits, signs and the decimal comma so that "+4" and "-4", or
    # "7,3" and "73", do not collapse into the same string.
    return re.sub(r"[^a-z0-9 +,.\-]+", " ", s).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--slides", required=True, help="allowed slide range, e.g. 19-35")
    ap.add_argument("--expect", type=int, default=50)
    args = ap.parse_args()

    lo, hi = (int(x) for x in args.slides.split("-"))
    problems: list[str] = []

    try:
        with open(args.path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        print(f"FAIL: file not found: {args.path}")
        return 1
    except json.JSONDecodeError as exc:
        print(f"FAIL: invalid JSON: {exc}")
        return 1

    if not isinstance(data, dict):
        print("FAIL: top level must be an object")
        return 1
    for key in ("deck", "batch", "topic", "questions"):
        if key not in data:
            problems.append(f"missing top-level key {key!r}")
    qs = data.get("questions")
    if not isinstance(qs, list):
        print("FAIL: 'questions' must be an array")
        return 1
    if len(qs) != args.expect:
        problems.append(f"expected {args.expect} questions, found {len(qs)}")

    seen_ids: set[str] = set()
    seen_stems: dict[str, str] = {}
    answer_hist = [0, 0, 0, 0, 0]

    for i, q in enumerate(qs):
        where = f"questions[{i}]"
        if not isinstance(q, dict):
            problems.append(f"{where}: not an object")
            continue
        missing = REQUIRED - q.keys()
        if missing:
            problems.append(f"{where}: missing keys {sorted(missing)}")
            continue
        extra = q.keys() - REQUIRED
        if extra:
            problems.append(f"{where}: unexpected keys {sorted(extra)}")

        qid = q["id"]
        m = re.fullmatch(r"d(\d{2})-b(\d{2})-q(\d{3})", qid) if isinstance(qid, str) else None
        if not m:
            problems.append(f"{where}: bad id {qid!r}")
        elif qid in seen_ids:
            problems.append(f"{where}: duplicate id {qid!r}")
        else:
            seen_ids.add(qid)
            if int(m.group(1)) != data.get("deck") or int(m.group(2)) != data.get("batch"):
                problems.append(f"{where}: id {qid!r} does not match deck/batch")

        stem = q["q"]
        if not isinstance(stem, str) or len(stem.strip()) < 15:
            problems.append(f"{where}: question text too short")
        else:
            key = norm(stem)
            if key in seen_stems:
                problems.append(f"{where}: duplicate of {seen_stems[key]}")
            else:
                seen_stems[key] = qid
            low = stem.lower()
            for bad in BANNED_META:
                if bad in low:
                    problems.append(f"{where}: meta reference {bad!r}")

        ch = q["choices"]
        if not isinstance(ch, list) or len(ch) != 5:
            problems.append(f"{where}: must have exactly 5 choices")
        else:
            for c in ch:
                if not isinstance(c, str) or not c.strip():
                    problems.append(f"{where}: empty choice")
            if all(isinstance(c, str) for c in ch):
                if len({norm(c) for c in ch}) != 5:
                    problems.append(f"{where}: duplicate choices")
                for c in ch:
                    n = norm(c)
                    if COMPOUND_RE.match(n):
                        problems.append(f"{where}: banned compound choice {c!r}")
                    if BLANKET_RE.match(n) and "precedent" in n:
                        problems.append(f"{where}: banned blanket choice {c!r}")

        ans = q["answer"]
        if not isinstance(ans, int) or isinstance(ans, bool) or not 0 <= ans <= 4:
            problems.append(f"{where}: answer must be an integer 0-4, got {ans!r}")
        else:
            answer_hist[ans] += 1

        ex = q["explain"]
        if not isinstance(ex, str) or len(ex.strip()) < 60:
            problems.append(f"{where}: explanation too short ({len(str(ex))} chars)")

        sl = q["slide"]
        if not isinstance(sl, int) or isinstance(sl, bool) or not lo <= sl <= hi:
            problems.append(f"{where}: slide {sl!r} outside {lo}-{hi}")

    if len(qs) >= 10:
        top = max(answer_hist)
        if top > 0.40 * len(qs):
            problems.append(
                f"answer position {answer_hist.index(top)} holds {top}/{len(qs)} "
                f"correct answers (max 40%): spread them out"
            )

    # The longest-choice-is-the-answer giveaway. If the correct option is
    # consistently the wordiest, a student scores without knowing anything.
    scored = [
        q for q in qs
        if isinstance(q, dict)
        and isinstance(q.get("choices"), list) and len(q["choices"]) == 5
        and isinstance(q.get("answer"), int) and not isinstance(q["answer"], bool)
        and 0 <= q["answer"] <= 4
        and all(isinstance(c, str) for c in q["choices"])
    ]
    if len(scored) >= 10:
        flagged = 0
        for q in scored:
            lens = [len(c) for c in q["choices"]]
            others = [lens[i] for i in range(5) if i != q["answer"]]
            median = sorted(others)[2]
            if lens[q["answer"]] == max(lens) and lens[q["answer"]] > 1.25 * median:
                flagged += 1
        rate = flagged / len(scored)
        if rate > 0.30:
            problems.append(
                f"{flagged}/{len(scored)} questions ({rate:.0%}) have the correct answer as the "
                f"strictly longest choice; keep all five choices comparable in length and "
                f"specificity (target under 30%)"
            )

    if problems:
        print(f"FAIL: {len(problems)} problem(s) in {args.path}")
        for p in problems[:40]:
            print("  -", p)
        if len(problems) > 40:
            print(f"  ... and {len(problems) - 40} more")
        return 1

    print(f"OK  {args.path}  {len(qs)} domande  posizioni={answer_hist}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
