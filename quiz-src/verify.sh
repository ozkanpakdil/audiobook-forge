#!/usr/bin/env bash
# Full verification of the biochemistry quiz. Run from anywhere.
set -u

cd "$(dirname "$0")" || exit 1
fails=0

echo "== 1. every batch validates on its own =="
python3 - <<'PY' > /tmp/bioq_batches.txt
import json
m = json.load(open("batches/manifest.json", encoding="utf-8"))
for s in m:
    print(s["deck"], s["batch"], s["slide_from"], s["slide_to"], s["out"])
PY
while read -r deck batch lo hi out; do
  if [ ! -f "$out" ]; then
    echo "  MISSING $out"
    fails=$((fails + 1))
    continue
  fi
  if ! out_msg=$(python3 validate_batch.py "$out" --slides "$lo-$hi" 2>&1); then
    echo "  FAIL deck$deck batch$batch"
    echo "$out_msg" | sed 's/^/      /'
    fails=$((fails + 1))
  fi
done < /tmp/bioq_batches.txt
echo "  batches checked: $(wc -l < /tmp/bioq_batches.txt | tr -d ' ')"

echo
echo "== 2. assemble the site data =="
if python3 build_site.py; then :; else fails=$((fails + 1)); fi

echo
echo "== 3. quality audit of the assembled bank =="
if python3 audit_quality.py; then :; else fails=$((fails + 1)); fi

echo
echo "== 4. browser self-test page is current =="
if python3 test/make_selftest.py > /dev/null; then
  echo "  regenerated quiz-src/test/selftest.html"
else
  fails=$((fails + 1))
fi

echo
if [ "$fails" -eq 0 ]; then
  echo "ALL CHECKS PASSED"
  exit 0
fi
echo "$fails check(s) FAILED"
exit 1
