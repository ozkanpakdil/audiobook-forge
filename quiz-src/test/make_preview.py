#!/usr/bin/env python3
"""Build a preview of the quiz app with the REAL assembled dataset inlined.

Reads   docs/index.html and docs/data/*.json
Writes  quiz-src/test/preview.html

Unlike the self-test, this uses the actual 2,000 questions. It starts a session
on the first lecture with shuffling off, answers the first question correctly,
and leaves the app on screen — so a screenshot shows the real header, progress
bar, question text, five real choices, the green feedback and the real
explanation with its slide citation. Needs no server and no network.
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
DOCS = os.path.join(ROOT, "docs")
OUT = os.path.join(HERE, "preview.html")


def main() -> int:
    with open(os.path.join(DOCS, "index.html"), encoding="utf-8") as fh:
        html = fh.read()

    manifest = json.load(open(os.path.join(DOCS, "data", "manifest.json"), encoding="utf-8"))
    decks = {}
    for entry in manifest["decks"]:
        payload = json.load(open(os.path.join(DOCS, "data", entry["file"]), encoding="utf-8"))
        decks[entry["deck"]] = payload
    first = decks[manifest["decks"][0]["deck"]]["questions"][0]

    driver = """
<script>
(function(){
  function $(s){return document.querySelector(s);}
  function settle(){return new Promise(function(r){setTimeout(r,30);});}
  async function run(){
    // first lecture, natural order, no shuffling: the correct option index of the
    // first question is known, so the preview can answer it for real.
    $('.deck[data-deck="1"]').click();
    var sel=$("#opt-count");
    for(var i=0;i<sel.options.length;i++){ if(sel.options[i].value==="0"){sel.value="0";} }
    $("#opt-shuffle-q").checked=false;
    $("#opt-shuffle-a").checked=false;
    $("#opt-instant").checked=true;
    $("#btn-start").click();
    await settle();
    var b=$('#choices .choice[data-i="__ANSWER__"]');
    if(b) b.click();
  }
  if(document.readyState==="loading"){document.addEventListener("DOMContentLoaded",function(){setTimeout(run,50);});}
  else {setTimeout(run,50);}
})();
</script>
""".replace("__ANSWER__", str(first["answer"]))

    inline = ("<script>window.__BIOQ_DATA__="
              + json.dumps({"manifest": manifest, "decks": decks}, ensure_ascii=False)
              + ";</script>\n")
    html = html.replace('href="styles.css"', 'href="../../docs/styles.css"')
    html = html.replace('<script src="app.js"></script>',
                        inline + '<script src="../../docs/app.js"></script>' + driver)
    html = html.replace("<title>", "<title>PREVIEW ")
    html = html.replace('<a href="https://github.com/ozkanpakdil/audiobook-forge">', '<a href="#">')

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"wrote {os.path.relpath(OUT, ROOT)}  ({len(html)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
