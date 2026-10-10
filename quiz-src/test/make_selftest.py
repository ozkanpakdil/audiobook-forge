#!/usr/bin/env python3
"""Build the browser self-test for the quiz app.

Reads   docs/index.html   (so the markup can never drift from the real page)
Writes  quiz-src/test/selftest.html

The page embeds a small synthetic dataset via window.__BIOQ_DATA__, loads the
real docs/app.js, drives a full session with synthetic clicks and keystrokes,
and paints a PASS/FAIL report at the top of the page. It needs no server and no
network: the dataset is inline, so fetch() is never used.

Render it and read the report, for example with headless Chrome:

    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
        --headless --disable-gpu --screenshot=/tmp/selftest.png \
        --window-size=1100,1100 quiz-src/test/selftest.html

or just open the file in a browser.
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
INDEX = os.path.join(ROOT, "docs", "index.html")
OUT = os.path.join(HERE, "selftest.html")


def synthetic_data() -> dict:
    """Five decks of four questions each, answers at positions 0,1,2,3."""
    def q(i: int, ans: int) -> dict:
        return {
            "q": f"Domanda sintetica numero {i} sulla biochimica di prova?",
            "choices": ["Alfa", "Beta", "Gamma", "Delta", "Epsilon"],
            "answer": ans,
            "explain": (f"Spiegazione sintetica numero {i}, scritta abbastanza lunga "
                        "da superare il controllo minimo di sessanta caratteri."),
            "slide": 10 + i,
        }

    template = [q(1, 0), q(2, 1), q(3, 2), q(4, 3)]
    decks = {}
    for d in range(1, 6):
        decks[d] = {
            "deck": d,
            "title": f"Lezione di prova {d}",
            "date": f"2025-10-0{d}",
            "questions": [dict(item, deck=d, batch=1,
                               id=f"d{d:02d}-b01-q{i + 1:03d}")
                          for i, item in enumerate(template)],
        }
    manifest = {
        "decks": [{"deck": d, "title": f"Lezione di prova {d}", "date": f"2025-10-0{d}",
                   "count": 4, "file": f"deck{d}.json"} for d in range(1, 6)],
        "total": 20,
    }
    return {"manifest": manifest, "decks": decks}


DRIVER = r"""
<pre id="report" style="position:fixed;inset:0;z-index:9999;background:#fff;color:#000;margin:0;padding:16px;font:13px/1.55 monospace;overflow:auto"></pre>
<script>
(function(){
  var R=[];
  function ok(n,c,x){R.push((c?"PASS  ":"FAIL  ")+n+(x!==undefined?"   ["+x+"]":""));}
  function $(s){return document.querySelector(s);}
  function click(s){var e=$(s); if(!e) throw new Error("missing "+s); e.click();}
  function settle(){return new Promise(function(r){setTimeout(r,20);});}
  function key(k){document.dispatchEvent(new KeyboardEvent("keydown",{key:k,bubbles:true}));}
  function pickAll(){var sel=$("#opt-count");for(var i=0;i<sel.options.length;i++){if(sel.options[i].value==="0"){sel.value="0";return;}}}
  function render(){
    var bad=R.filter(function(l){return l.indexOf("FAIL")===0;}).length;
    $("#report").textContent="SELFTEST "+(bad?"FAILED ("+bad+" failures)":"OK — all "+R.length+" checks passed")+"\n\n"+R.join("\n");
  }
  async function run(){
    try{
      ok("no load error banner", $("#load-error").hidden===true);
      ok("6 deck buttons rendered", document.querySelectorAll("#deck-list .deck").length===6,
         document.querySelectorAll("#deck-list .deck").length+" found");
      ok("'tutte' preselected by default", $('.deck[data-deck="all"]').getAttribute("aria-pressed")==="true");
      ok("start enabled after default selection", $("#btn-start").disabled===false);
      ok("count shows pool size for 'tutte'", $("#opt-count").options[4].textContent==="tutte (20)", $("#opt-count").options[4].textContent);

      /* ---------- part 1: instant feedback, deck 1 ---------- */
      click('.deck[data-deck="1"]');
      pickAll();
      $("#opt-shuffle-q").checked=false; $("#opt-shuffle-a").checked=false; $("#opt-instant").checked=true;
      click("#btn-start"); await settle();
      ok("quiz view shown", $("#view-quiz").hidden===false);
      ok("counter says 1 di 4", $("#q-position").textContent==="Domanda 1 di 4", $("#q-position").textContent);
      ok("5 choices offered", document.querySelectorAll("#choices .choice").length===5);
      ok("next disabled before answering", $("#btn-next").disabled===true);

      click('#choices .choice[data-i="0"]'); await settle();
      ok("correct choice marked correct", $('#choices .choice[data-i="0"]').classList.contains("correct"));
      ok("feedback shown green", $("#feedback").hidden===false && $("#feedback").className.indexOf("ok")>-1);
      ok("explanation displayed", $("#feedback-body").textContent.length>60);
      ok("slide cited", $("#feedback-src").textContent.indexOf("slide")>-1, $("#feedback-src").textContent);
      ok("score incremented to 1", $("#score-ok").textContent==="1");
      ok("all choices locked after answering", document.querySelectorAll("#choices .choice:disabled").length===5);

      click("#btn-next"); await settle();
      ok("advanced to 2 di 4", $("#q-position").textContent==="Domanda 2 di 4", $("#q-position").textContent);
      click('#choices .choice[data-i="3"]'); await settle();
      ok("wrong choice marked wrong", $('#choices .choice[data-i="3"]').classList.contains("wrong"));
      ok("correct one revealed too", $('#choices .choice[data-i="1"]').classList.contains("correct"));
      ok("feedback red", $("#feedback").className.indexOf("no")>-1);
      click("#btn-next"); await settle();
      click('#choices .choice[data-i="2"]'); await settle();
      click("#btn-next"); await settle();
      ok("last question offers the result", $("#btn-next").textContent.indexOf("risultato")>-1, $("#btn-next").textContent);
      click('#choices .choice[data-i="0"]'); await settle();
      click("#btn-next"); await settle();

      ok("result view shown", $("#view-result").hidden===false);
      ok("score is 50%", $("#result-percent").textContent==="50%", $("#result-percent").textContent);
      ok("detail says 2 corrette su 4", $("#result-detail").textContent.indexOf("2 corrette su 4")===0, $("#result-detail").textContent);
      click("#btn-review"); await settle();
      ok("review lists exactly the 2 wrong", document.querySelectorAll("#review .review-item").length===2,
         document.querySelectorAll("#review .review-item").length+" items");
      ok("review shows correct answers", $("#review").textContent.indexOf("Risposta corretta")>-1);

      /* ---------- part 2: exam mode, deck 2 ---------- */
      click("#btn-home"); await settle();
      click('.deck[data-deck="2"]');
      pickAll(); $("#opt-instant").checked=false;
      $("#opt-shuffle-q").checked=false; $("#opt-shuffle-a").checked=false;
      click("#btn-start"); await settle();
      ok("exam mode: 4 questions", $("#q-position").textContent==="Domanda 1 di 4", $("#q-position").textContent);
      click('#choices .choice[data-i="0"]'); await settle();
      ok("exam mode hides feedback", $("#feedback").hidden===true);
      ok("exam mode marks selection only", $('#choices .choice[data-i="0"]').classList.contains("selected"));
      ok("exam mode does not reveal correctness", $('#choices .choice[data-i="0"]').classList.contains("correct")===false);
      click("#btn-next"); await settle();
      click("#btn-skip"); await settle();
      ok("skip advanced to 3 di 4", $("#q-position").textContent==="Domanda 3 di 4", $("#q-position").textContent);
      click('#choices .choice[data-i="2"]'); await settle(); click("#btn-next"); await settle();
      click('#choices .choice[data-i="3"]'); await settle(); click("#btn-next"); await settle();
      ok("exam result 75%", $("#result-percent").textContent==="75%", $("#result-percent").textContent);
      ok("skipped reported", $("#result-detail").textContent.indexOf("1 non risposte")>-1, $("#result-detail").textContent);

      /* ---------- part 3: keyboard, deck 3 ---------- */
      click("#btn-home"); await settle();
      click('.deck[data-deck="3"]');
      pickAll(); $("#opt-instant").checked=true;
      $("#opt-shuffle-q").checked=false; $("#opt-shuffle-a").checked=false;
      click("#btn-start"); await settle();
      key("1"); await settle();
      ok("keyboard '1' picks the correct first choice", $('#choices .choice[data-i="0"]').classList.contains("correct"));
      key("Enter"); await settle();
      ok("keyboard Enter advances", $("#q-position").textContent==="Domanda 2 di 4", $("#q-position").textContent);
      key("b"); await settle();
      ok("keyboard 'b' selects the second choice", $('#choices .choice[data-i="1"]').classList.contains("correct"));
    }catch(e){ ok("driver crashed: "+e.message, false); }
    render();
  }
  if(document.readyState==="loading"){document.addEventListener("DOMContentLoaded",function(){setTimeout(run,40);});}
  else {setTimeout(run,40);}
})();
</script>
"""


def main() -> int:
    with open(INDEX, encoding="utf-8") as fh:
        html = fh.read()

    inline = ("<script>window.__BIOQ_DATA__="
              + json.dumps(synthetic_data(), ensure_ascii=False)
              + ";</script>\n")

    # the test page lives one level deeper than docs/, so rewrite asset paths
    html = html.replace('href="styles.css"', 'href="../../docs/styles.css"')
    html = html.replace('<script src="app.js"></script>',
                        inline + '<script src="../../docs/app.js"></script>' + DRIVER)
    html = html.replace("<title>", "<title>SELFTEST ")
    html = html.replace('<a href="https://github.com/ozkanpakdil/audiobook-forge">',
                        '<a href="#">')

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"wrote {os.path.relpath(OUT, ROOT)}  ({len(html)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
