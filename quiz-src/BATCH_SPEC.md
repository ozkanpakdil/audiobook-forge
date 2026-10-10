# Contratto per la scrittura di un lotto di domande — Quiz di Biochimica

Stai scrivendo **50 domande a risposta multipla in italiano** per un quiz di
autovalutazione del corso di Biochimica (Corso di Laurea in Infermieristica,
Università della Valle d'Aosta, A.A. 2025/26).

## Cosa leggi

- Il file `batches/deck<N>/batch<M>.txt` contiene le slide del tuo intervallo,
  numerate (`### Slide 12`) e con il titolo dell'argomento in testa.
- Le slide sono poche e sintetiche: sono appunti visivi. Il testo di una slide è
  la fonte primaria, ma **non basta** a produrre 50 domande distinte.

## Cosa scrivi

Un solo file JSON, esattamente al percorso indicato nella richiesta, con questa forma:

```json
{
  "deck": 1,
  "batch": 1,
  "topic": "L'atomo, la tavola periodica e i legami chimici",
  "questions": [
    {
      "id": "d01-b01-q001",
      "q": "Quale tipo di legame si forma quando un atomo cede elettroni a un altro?",
      "choices": [
        "Legame ionico",
        "Legame covalente puro",
        "Legame a idrogeno",
        "Legame peptidico",
        "Interazione idrofobica"
      ],
      "answer": 0,
      "explain": "Il legame ionico nasce dal trasferimento completo di uno o piu elettroni da un atomo a un altro, che diventano cosi ioni di carica opposta e si attraggono. Il legame covalente, invece, mette in comune gli elettroni, e il legame a idrogeno e un'interazione debole che non comporta cessione di elettroni.",
      "slide": 21
    }
  ]
}
```

### Regole vincolanti

1. **Lingua**: italiano corretto e professionale. Terminologia biochimica e medica
   appropriata al corso di Infermieristica.
2. **Numero**: esattamente **50** domande nell'array `questions`.
3. **Id**: progressivo, formato `d<NN>-b<NN>-q<NNN>`, per esempio `d03-b07-q042`.
   Gli id devono essere unici.
4. **`q`**: una sola domanda, chiara, autonoma, comprensibile senza vedere la slide.
   Non usare "secondo la slide", "come visto a lezione", "nel lucido".
5. **`choices`**: esattamente **5** alternative, tutte diverse fra loro, tutte
   plausibili. Mai "tutte le precedenti", "nessuna delle precedenti", "A e B".
   I distrattori devono essere sbagliati *per un motivo*, non assurdi.
6. **`answer`**: indice **0-based** (0–4) dell'unica risposta corretta.
   Distribuisci le risposte corrette fra tutte e cinque le posizioni: nessuna
   posizione deve raccogliere più di circa un terzo delle domande.
7. **`explain`**: 2–4 frasi che spiegano **perché la risposta corretta è corretta**
   e, dove è utile, **perché il distrattore più insidioso è sbagliato**. Non
   ripetere semplicemente la domanda.
8. **`slide`**: il numero della slide su cui la domanda si fonda. Deve stare
   nell'intervallo del tuo lotto.
9. **Nessun duplicato**: nessuna domanda deve chiedere la stessa cosa di un'altra
   con parole diverse. Meglio 50 domande su 50 fatti distinti.
10. **Copertura**: distribuisci le domande su **tutte** le slide del tuo intervallo,
    in proporzione al loro contenuto. Non concentrarti su una sola slide.
11. **Profondità**: quando le slide sono povere, puoi integrarle con nozioni
    standard di biochimica (livello del testo consigliato: Nelson/Cox,
    *Introduzione alla biochimica di Lehninger*, Zanichelli). Non contraddire mai
    la slide, e non inventare valori numerici, dosi o riferimenti clinici che la
    slide non contiene e che non siano nozioni consolidate.
12. **Nessun riferimento bibliografico, figura o numero di pagina** dentro il testo
    delle domande.
13. **Niente domande su**: date del corso, nomi dei docenti, orari, aule,
    modalità d'esame, o qualunque cosa riguardi l'organizzazione didattica e non
    la biochimica.
14. **Varietà**: alterna domande di definizione, di riconoscimento, di
    ragionamento, di applicazione clinica e di calcolo semplice (per esempio il
    bilancio dell'ATP). Evita 50 domande tutte dello stesso tipo.
15. **Accenti**: usa le lettere accentate italiane corrette (perché, è, così,
    più, β-ossidazione va bene con il carattere greco).

### Difficoltà

Distribuisci all'incirca così: 15 domande di base (definizioni e riconoscimento),
20 di livello intermedio (comprensione e collegamenti), 15 avanzate (applicazione,
ragionamento, integrazione fra argomenti).

## Autocontrollo obbligatorio

Prima di considerare finito il lavoro, esegui:

```
cd /Users/ozkan/projects/audiobook-forge/quiz-src && python3 validate_batch.py batches/deck<N>/batch<M>.json --slides <from>-<to>
```

Deve terminare con exit code 0 e stampare `OK`. Correggi e ripeti finché non passa
senza errori. Il validatore controlla il numero di domande, le 5 alternative,
l'unicità, l'indice della risposta, la lunghezza della spiegazione e i duplicati.

## Come rispondere

Una sola riga, senza altro testo:
`batches/deck<N>/batch<M>.json — 50 domande — PASS`
