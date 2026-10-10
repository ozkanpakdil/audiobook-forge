# Quiz di Biochimica — materiale sorgente

Questo folder costruisce il quiz pubblicato in `docs/`, che GitHub Pages serve come
sito statico. Non contiene audio e non interferisce con la pipeline dei libri.

## Cosa c'è qui

| Percorso | Contenuto |
|---|---|
| `extract/deck<N>.slides.json` | il testo di ogni slide, ripulito e numerato |
| `extract/deck<N>.md` | lo stesso testo in forma leggibile |
| `batches/manifest.json` | i 40 lotti: lezione, intervallo di slide, argomento, numero di domande |
| `batches/deck<N>/batch<M>.txt` | le slide di quel lotto, con numerazione |
| `batches/deck<N>/batch<M>.json` | le 50 domande prodotte per quel lotto |
| `BATCH_SPEC.md` | il contratto di scrittura: schema e regole vincolanti |
| `REBALANCE_SPEC.md` | il contratto per correggere lo squilibrio delle alternative |
| `validate_batch.py` | autocontrollo di un singolo lotto |
| `audit_quality.py` | controllo di qualità sull'intero archivio assemblato |
| `make_rebalance_lists.py` | genera gli elenchi delle domande da ribilanciare |
| `build_site.py` | validazione globale e assemblaggio dei dati per l'app |
| `verify.sh` | esegue tutti i controlli in sequenza |
| `test/make_selftest.py` | costruisce la pagina di test nel browser dell'app |

## Come si rigenera il sito

```
cd quiz-src
./verify.sh                                                          # tutto
python3 validate_batch.py batches/deck1/batch1.json --slides 1-18   # un lotto
python3 build_site.py                                                # tutti i lotti
```

`build_site.py` fallisce se un lotto non è completo, se un id è duplicato, se una
domanda non ha esattamente cinque alternative distinte, se l'indice della risposta
non è fra 0 e 4, se la spiegazione è troppo corta, se una domanda cita una slide
fuori dal proprio intervallo, o se due domande della stessa lezione chiedono la
stessa cosa. In uscita scrive `docs/data/deck1.json` … `deck5.json` e
`docs/data/manifest.json`.

## Controllo di qualità

Il primo giro di domande aveva un difetto grave che nessun controllo per lotto
aveva visto: **nel 44 per cento delle domande la risposta corretta era
l'alternativa più lunga**, con punte del 76 per cento. Con cinque alternative il
caso ne darebbe il 20-25 per cento. Uno studente che non avesse studiato avrebbe
potuto rispondere bene scegliendo sempre l'opzione più lunga.

Il difetto è stato misurato con `audit_quality.py`, le domande segnalate sono state
ribilanciate una per una secondo `REBALANCE_SPEC.md`, e la regola è stata resa
vincolante in `validate_batch.py`, che ora rifiuta un lotto se più del 30 per cento
delle sue domande ha quel difetto. `audit_quality.py` controlla inoltre:

- la distribuzione delle posizioni della risposta corretta;
- le domande quasi identiche, anche fra lezioni diverse, per sovrapposizione di
  parole;
- la lunghezza delle spiegazioni;
- la presenza di parole assolute ("sempre", "mai", "tutti") concentrate nella
  risposta corretta, che è un altro modo di indovinare senza sapere.

## Test dell'applicazione

`test/make_selftest.py` legge `docs/index.html`, vi innesta un piccolo archivio
sintetico e il vero `docs/app.js`, e produce `test/selftest.html`: una pagina che
simula una sessione completa — scelta della lezione, risposta corretta, risposta
sbagliata, salto, modalità esame, revisione degli errori, tastiera — e stampa un
rapporto PASS/FAIL. Non serve né un server né la rete.

```
python3 test/make_selftest.py
# poi apri test/selftest.html nel browser, oppure:
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
    --headless --disable-gpu --screenshot=/tmp/selftest.png \
    --window-size=1100,1100 test/selftest.html
```

## Provenienza dei contenuti

Le slide provengono dalle cinque lezioni del corso di Biochimica (A.A. 2025/26),
Corso di Laurea in Infermieristica, Università della Valle d'Aosta. Le slide sono
appunti visivi molto sintetici: il testo estratto è di
circa 12.900 parole in totale, contro le 2.000 domande richieste. Le domande sono
quindi ancorate alla slide indicata nel campo `slide`, ma integrate — dove le slide
non bastano — con nozioni standard di biochimica al livello del testo consigliato
dal corso (Nelson/Cox, *Introduzione alla biochimica di Lehninger*, Zanichelli).
Nessun valore numerico, dose o soglia clinica è stato inventato.

## Struttura di una domanda

```json
{
  "id": "d01-b01-q001",
  "q": "Quale tipo di legame si forma quando un atomo cede elettroni a un altro?",
  "choices": ["Legame ionico", "Legame covalente puro", "Legame a idrogeno", "Legame peptidico", "Interazione idrofobica"],
  "answer": 0,
  "explain": "Il legame ionico nasce dal trasferimento completo di uno o più elettroni…",
  "slide": 21,
  "deck": 1,
  "batch": 1
}
```

`answer` è l'indice 0-based dell'unica alternativa corretta. `slide` è la slide da
cui la domanda nasce; l'app la mostra sotto la spiegazione.

## Nota

Materiale di autovalutazione per lo studio. Non è un esame ufficiale e non ha alcun
valore di certificazione. Il corso dichiara una prova scritta di 31 domande a
risposta multipla in 40 minuti: la sessione predefinita dell'app ne propone 31,
proprio per simulare quella forma.
