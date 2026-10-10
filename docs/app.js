/* Biochimica — Quiz di autovalutazione
   App statica, senza dipendenze. I dati stanno in data/*.json. */
(function () {
  "use strict";

  var $ = function (sel) { return document.querySelector(sel); };
  var LS_SETTINGS = "bioq.settings.v1";
  var LS_SESSION = "bioq.session.v1";
  var LS_THEME = "bioq.theme.v1";

  var state = {
    manifest: null,
    decks: {},          // numero -> dati completi del deck
    selected: null,     // numero del deck, oppure "all"
    session: null
  };

  /* ---------------------------------------------------------------- utils */

  function shuffle(arr) {
    var a = arr.slice();
    for (var i = a.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1));
      var t = a[i]; a[i] = a[j]; a[j] = t;
    }
    return a;
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function fmtDate(iso) {
    if (!iso) return "";
    var p = String(iso).split("-");
    if (p.length !== 3) return iso;
    return p[2] + "/" + p[1] + "/" + p[0];
  }

  function store(key, val) {
    try { localStorage.setItem(key, JSON.stringify(val)); } catch (e) { /* ignore */ }
  }
  function read(key) {
    try { return JSON.parse(localStorage.getItem(key)); } catch (e) { return null; }
  }
  function drop(key) {
    try { localStorage.removeItem(key); } catch (e) { /* ignore */ }
  }

  /* --------------------------------------------------------------- theme */

  function applyTheme(t) {
    if (t) { document.documentElement.setAttribute("data-theme", t); }
    else { document.documentElement.removeAttribute("data-theme"); }
  }

  function initTheme() {
    var saved = read(LS_THEME);
    applyTheme(saved && saved.theme ? saved.theme : null);
    $("#btn-theme").addEventListener("click", function () {
      var cur = document.documentElement.getAttribute("data-theme");
      var isDark = cur ? cur === "dark"
        : window.matchMedia("(prefers-color-scheme: dark)").matches;
      var next = isDark ? "light" : "dark";
      applyTheme(next);
      store(LS_THEME, { theme: next });
    });
  }

  /* -------------------------------------------------------------- settings */

  function readSettings() {
    var s = read(LS_SETTINGS) || {};
    return {
      count: typeof s.count === "number" ? s.count : 31,
      shuffleQ: s.shuffleQ !== false,
      shuffleA: s.shuffleA !== false,
      instant: s.instant !== false
    };
  }

  function applySettingsToForm(s) {
    $("#opt-count").value = String(s.count);
    $("#opt-shuffle-q").checked = s.shuffleQ;
    $("#opt-shuffle-a").checked = s.shuffleA;
    $("#opt-instant").checked = s.instant;
  }

  function settingsFromForm() {
    return {
      count: parseInt($("#opt-count").value, 10) || 0,
      shuffleQ: $("#opt-shuffle-q").checked,
      shuffleA: $("#opt-shuffle-a").checked,
      instant: $("#opt-instant").checked
    };
  }

  /* ----------------------------------------------------------------- data */

  function loadJSON(url) {
    return fetch(url, { cache: "no-cache" }).then(function (r) {
      if (!r.ok) throw new Error(url + " → HTTP " + r.status);
      return r.json();
    });
  }

  function loadDecks() {
    var list = state.manifest.decks.map(function (d) {
      return loadJSON("data/" + d.file).then(function (full) {
        state.decks[d.deck] = full;
        return full;
      });
    });
    return Promise.all(list);
  }

  /* ------------------------------------------------------------ rendering */

  function renderDecks() {
    var box = $("#deck-list");
    var decks = state.manifest.decks;
    var html = "";

    html += '<button class="deck all" type="button" data-deck="all" aria-pressed="false">' +
      '<span class="deck-top"><span class="deck-num">Tutte</span>' +
      '<span class="deck-count">' + state.manifest.total + " domande</span></span>" +
      '<span class="deck-title">Tutte le lezioni insieme</span>' +
      '<span class="deck-date">Cinque lezioni, dalla chimica generale al metabolismo</span>' +
      "</button>";

    decks.forEach(function (d) {
      html += '<button class="deck" type="button" data-deck="' + d.deck + '" aria-pressed="false">' +
        '<span class="deck-top"><span class="deck-num">Lezione ' + d.deck + "</span>" +
        '<span class="deck-count">' + d.count + " domande</span></span>" +
        '<span class="deck-title">' + esc(d.title) + "</span>" +
        '<span class="deck-date">' + fmtDate(d.date) + "</span>" +
        "</button>";
    });

    box.innerHTML = html;

    box.addEventListener("click", function (ev) {
      var btn = ev.target.closest(".deck");
      if (!btn) return;
      state.selected = btn.dataset.deck === "all" ? "all" : parseInt(btn.dataset.deck, 10);
      Array.prototype.forEach.call(box.querySelectorAll(".deck"), function (b) {
        b.setAttribute("aria-pressed", String(b === btn));
      });
      $("#btn-start").disabled = false;
      updateCountOptions();
    });

    // preseleziona "tutte"
    var first = box.querySelector('.deck[data-deck="all"]');
    if (first) { first.click(); }
  }

  function selectedPool() {
    if (state.selected === "all") {
      var all = [];
      state.manifest.decks.forEach(function (d) {
        all = all.concat(state.decks[d.deck].questions);
      });
      return all;
    }
    var dk = state.decks[state.selected];
    return dk ? dk.questions.slice() : [];
  }

  function updateCountOptions() {
    var n = selectedPool().length;
    var sel = $("#opt-count");
    Array.prototype.forEach.call(sel.options, function (o) {
      if (o.value === "0") { o.textContent = "tutte (" + n + ")"; return; }
      o.disabled = parseInt(o.value, 10) > n;
    });
    // Never leave the select on a value that is no longer selectable: that would
    // silently fall back to "all questions" instead of the chosen size.
    var cur = sel.value;
    if (cur === "" || (cur !== "0" && parseInt(cur, 10) > n)) {
      var best = null;
      Array.prototype.forEach.call(sel.options, function (o) {
        if (o.value !== "0" && !o.disabled) { best = o.value; }
      });
      sel.value = best !== null ? best : "0";
    }
  }

  /* --------------------------------------------------------------- session */

  function buildSession(settings) {
    var pool = selectedPool();
    if (settings.shuffleQ) pool = shuffle(pool);

    var limit = settings.count === 0 ? pool.length : settings.count;
    pool = pool.slice(0, limit);

    var questions = pool.map(function (q) {
      var idx = [0, 1, 2, 3, 4];
      if (settings.shuffleA) idx = shuffle(idx);
      return {
        deck: q.deck,
        id: q.id,
        q: q.q,
        explain: q.explain,
        slide: q.slide,
        order: idx,                                   // posizione mostrata -> indice originale
        correct: idx.indexOf(q.answer),                // posizione mostrata della risposta corretta
        choices: idx.map(function (i) { return q.choices[i]; })
      };
    });

    return {
      settings: settings,
      deck: state.selected,
      questions: questions,
      index: 0,
      answers: new Array(questions.length).fill(null),
      startedAt: Date.now()
    };
  }

  function startSession() {
    var s = settingsFromForm();
    store(LS_SETTINGS, s);
    state.session = buildSession(s);

    if (!state.session.questions.length) {
      showError("Non ci sono domande disponibili per questa selezione.");
      return;
    }
    store(LS_SESSION, state.session);
    goto("quiz");
    renderQuestion();
  }

  function saveSession() { if (state.session) store(LS_SESSION, state.session); }

  function renderQuestion() {
    var s = state.session;
    var q = s.questions[s.index];
    var n = s.questions.length;

    $("#q-position").textContent = "Domanda " + (s.index + 1) + " di " + n;
    var dk = state.manifest.decks.filter(function (d) { return d.deck === q.deck; })[0];
    $("#q-deck").textContent = dk ? dk.title : "";

    var answered = s.answers.filter(function (a) { return a !== null; }).length;
    var correct = s.answers.filter(function (a) { return a === true; }).length;
    $("#score-ok").textContent = correct;
    $("#score-done").textContent = answered;

    var pct = n ? Math.round((s.index / n) * 100) : 0;
    $("#progress-bar").style.width = pct + "%";
    var bar = $(".progress");
    if (bar) bar.setAttribute("aria-valuenow", String(pct));

    $("#q-text").textContent = q.q;

    var ul = $("#choices");
    ul.innerHTML = q.choices.map(function (c, i) {
      return '<li><button class="choice" type="button" data-i="' + i + '">' +
        '<span class="choice-key">' + "ABCDE"[i] + "</span>" +
        '<span class="choice-text">' + esc(c) + "</span>" +
        "</button></li>";
    }).join("");

    var fb = $("#feedback");
    fb.hidden = true;
    fb.className = "feedback";
    $("#btn-next").disabled = true;
    $("#btn-next").textContent = (s.index === n - 1) ? "Vedi il risultato" : "Avanti";
    $("#btn-skip").disabled = false;

    // se già risposto (sessione ripresa) mostra lo stato
    var prev = s.answers[s.index];
    if (prev !== null) { revealAnswer(s.answersRaw ? s.answersRaw[s.index] : null, true); }
  }

  function revealAnswer(chosenIndex, silent) {
    var s = state.session;
    var q = s.questions[s.index];
    var instant = s.settings.instant;

    var buttons = $("#choices").querySelectorAll(".choice");
    Array.prototype.forEach.call(buttons, function (b) {
      b.disabled = true;
      var i = parseInt(b.dataset.i, 10);
      if (i === q.correct) b.classList.add("correct");
      else if (chosenIndex !== null && i === chosenIndex) b.classList.add("wrong");
      else b.classList.add("dim");
    });

    if (instant || !silent) {
      var ok = chosenIndex === q.correct;
      var fb = $("#feedback");
      fb.hidden = false;
      fb.className = "feedback " + (ok ? "ok" : "no");
      $("#feedback-head").textContent = chosenIndex === null
        ? "Nessuna risposta"
        : (ok ? "Risposta corretta" : "Risposta errata");
      $("#feedback-body").textContent = q.explain;
      var src = $("#feedback-src");
      var dk = state.manifest.decks.filter(function (d) { return d.deck === q.deck; })[0];
      src.textContent = "Lezione " + q.deck + (dk ? " — " + dk.title : "") + " · slide " + q.slide;
    }
    $("#btn-next").disabled = false;
  }

  function choose(i) {
    var s = state.session;
    if (s.answers[s.index] !== null) return;      // già risposto
    var q = s.questions[s.index];

    if (!s.answersRaw) s.answersRaw = new Array(s.questions.length).fill(null);
    s.answersRaw[s.index] = i;
    s.answers[s.index] = (i === q.correct);
    saveSession();

    if (s.settings.instant) {
      revealAnswer(i, false);
    } else {
      var buttons = $("#choices").querySelectorAll(".choice");
      Array.prototype.forEach.call(buttons, function (b) {
        b.classList.remove("correct", "wrong", "dim");
        b.classList.toggle("selected", parseInt(b.dataset.i, 10) === i);
      });
      $("#btn-next").disabled = false;
    }
    var answered = s.answers.filter(function (a) { return a !== null; }).length;
    var correct = s.answers.filter(function (a) { return a === true; }).length;
    $("#score-ok").textContent = correct;
    $("#score-done").textContent = answered;
  }

  function next() {
    var s = state.session;
    if (s.index >= s.questions.length - 1) { finish(); return; }
    s.index++;
    saveSession();
    renderQuestion();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function skip() {
    var s = state.session;
    if (!s.answersRaw) s.answersRaw = new Array(s.questions.length).fill(null);
    if (s.answers[s.index] === null) { s.answers[s.index] = false; s.answersRaw[s.index] = null; }
    saveSession();
    next();
  }

  /* --------------------------------------------------------------- results */

  function finish() {
    var s = state.session;
    var raw = s.answersRaw || [];
    var total = s.questions.length;
    var correct = s.answers.filter(function (a) { return a === true; }).length;
    // A skipped question is recorded as answered-false with no choice kept, so it
    // still counts against the score; a question never reached stays null.
    var skipped = 0, notReached = 0;
    s.answers.forEach(function (a, i) {
      if (a === null) { notReached++; }
      else if (raw[i] === null || raw[i] === undefined) { skipped++; }
    });
    var unanswered = skipped + notReached;
    var pct = total ? Math.round((correct / total) * 100) : 0;

    $("#result-percent").textContent = pct + "%";
    $("#result-detail").textContent = correct + " corrette su " + total +
      (unanswered ? " · " + unanswered + " non risposte" : "");

    var verdict;
    if (pct >= 90) verdict = "Ottimo: la materia è solida. Ripassa solo i dettagli sbagliati.";
    else if (pct >= 75) verdict = "Buon livello. Rivedi gli argomenti degli errori e ripeti la sessione.";
    else if (pct >= 60) verdict = "Sufficiente. Conviene rileggere le slide delle lezioni in cui hai sbagliato di più.";
    else if (pct >= 40) verdict = "Da consolidare. Riprendi le lezioni dall'inizio e torna su questo quiz dopo lo studio.";
    else verdict = "Serve uno studio sistematico: parti dalle slide della lezione e usa il quiz come verifica.";
    $("#result-verdict").textContent = verdict;

    renderReview();
    $("#review").hidden = true;
    $("#btn-review").textContent = "Rivedi gli errori";
    drop(LS_SESSION);
    goto("result");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function renderReview() {
    var s = state.session;
    var raw = s.answersRaw || [];
    var items = [];
    s.questions.forEach(function (q, i) {
      var ok = s.answers[i] === true;
      if (ok) return;
      var chosen = raw[i];
      var dk = state.manifest.decks.filter(function (d) { return d.deck === q.deck; })[0];
      items.push(
        '<article class="review-item">' +
        '<p class="rq">' + (i + 1) + ". " + esc(q.q) + "</p>" +
        '<p class="ra"><span class="lbl">La tua risposta:</span> ' +
          (chosen === null || chosen === undefined
            ? '<em>nessuna</em>'
            : '<span class="bad">' + esc(q.choices[chosen]) + "</span>") + "</p>" +
        '<p class="ra good"><span class="lbl">Risposta corretta:</span> ' +
          esc(q.choices[q.correct]) + "</p>" +
        '<p class="rex">' + esc(q.explain) + "</p>" +
        '<p class="rex muted">Lezione ' + q.deck + (dk ? " — " + esc(dk.title) : "") +
          " · slide " + q.slide + "</p>" +
        "</article>"
      );
    });
    $("#review").innerHTML = items.length
      ? '<h2>Domande da rivedere (' + items.length + ")</h2>" + items.join("")
      : '<h2>Nessun errore da rivedere</h2><p class="muted">Hai risposto correttamente a tutte le domande.</p>';
  }

  /* ------------------------------------------------------------------ view */

  function goto(name) {
    ["home", "quiz", "result"].forEach(function (v) {
      $("#view-" + v).hidden = (v !== name);
    });
    $("#btn-home").hidden = (name === "home");
  }

  function showError(msg) {
    var b = $("#load-error");
    b.textContent = msg;
    b.hidden = false;
  }

  /* ------------------------------------------------------------------ init */

  function wire() {
    $("#btn-start").addEventListener("click", startSession);
    $("#btn-home").addEventListener("click", function () { goto("home"); });
    $("#brand").addEventListener("click", function (e) { e.preventDefault(); goto("home"); });

    $("#choices").addEventListener("click", function (ev) {
      var b = ev.target.closest(".choice");
      if (!b) return;
      choose(parseInt(b.dataset.i, 10));
    });
    $("#btn-next").addEventListener("click", next);
    $("#btn-skip").addEventListener("click", skip);
    $("#btn-quit").addEventListener("click", finish);

    $("#btn-again").addEventListener("click", function () { goto("home"); });
    $("#btn-review").addEventListener("click", function () {
      var r = $("#review");
      r.hidden = !r.hidden;
      $("#btn-review").textContent = r.hidden ? "Rivedi gli errori" : "Nascondi la revisione";
    });
    $("#btn-print").addEventListener("click", function () { window.print(); });

    $("#btn-resume").addEventListener("click", function () {
      var s = read(LS_SESSION);
      if (!s || !s.questions || !s.questions.length) return;
      state.session = s;
      if (!state.session.answersRaw) {
        state.session.answersRaw = new Array(s.questions.length).fill(null);
      }
      goto("quiz");
      renderQuestion();
    });

    document.addEventListener("keydown", function (ev) {
      if ($("#view-quiz").hidden) return;
      if (ev.target.tagName === "SELECT" || ev.target.tagName === "INPUT") return;
      var k = ev.key;
      if (ev.metaKey || ev.ctrlKey || ev.altKey) return;

      var idx = -1;
      if (/^[1-5]$/.test(k)) idx = parseInt(k, 10) - 1;
      else if (/^[a-eA-E]$/.test(k)) idx = k.toLowerCase().charCodeAt(0) - 97;

      if (idx >= 0) {
        ev.preventDefault();
        if (!$("#btn-next").disabled && state.session.answers[state.session.index] !== null) return;
        choose(idx);
        return;
      }
      if (k === "Enter" || k === " ") {
        var nb = $("#btn-next");
        if (!nb.disabled) { ev.preventDefault(); next(); }
        return;
      }
      if (k === "Escape") { finish(); }
    });
  }

  function boot() {
    initTheme();
    wire();
    applySettingsToForm(readSettings());

    // Optional inline dataset: lets the page run from file:// and from a single
    // self-contained HTML file, where fetch() on data/*.json would be blocked.
    var inline = window.__BIOQ_DATA__;
    if (inline && inline.manifest && inline.decks) {
      state.manifest = inline.manifest;
      Object.keys(inline.decks).forEach(function (k) {
        state.decks[parseInt(k, 10)] = inline.decks[k];
      });
      afterLoad();
      return;
    }

    loadJSON("data/manifest.json")
      .then(function (m) {
        if (!m || !m.decks || !m.decks.length) throw new Error("manifest vuoto");
        state.manifest = m;
        return loadDecks();
      })
      .then(afterLoad)
      .catch(function (err) {
        $("#deck-list").innerHTML = '<p class="muted">Dati non disponibili.</p>';
        showError("Impossibile caricare le domande: " + err.message +
          ". Se stai aprendo il file direttamente dal disco, avvia un piccolo server locale " +
          "(per esempio: python3 -m http.server) perché il browser blocca fetch() su file://.");
      });
  }

  function afterLoad() {
    renderDecks();
    var saved = read(LS_SESSION);
    if (saved && saved.questions && saved.index < saved.questions.length) {
      $("#btn-resume").hidden = false;
      $("#btn-resume").textContent =
        "Riprendi la sessione interrotta (domanda " + (saved.index + 1) + " di " + saved.questions.length + ")";
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
