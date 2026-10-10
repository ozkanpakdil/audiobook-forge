# Contratto per ribilanciare le alternative di un lotto

Un controllo automatico ha trovato un difetto sistematico in tutto il quiz: **in
molte domande la risposta corretta è l'alternativa più lunga**. Su 1.900 domande
già scritte succede nell'44 per cento dei casi, con punte del 76 per cento. Con
cinque alternative il caso ne darebbe circa il 20-25 per cento.

La conseguenza è grave: uno studente che non ha studiato può rispondere bene
scegliendo **sempre l'alternativa più lunga**. Un quiz così non misura nulla.

Il tuo compito è correggere questo difetto nel tuo lotto.

## Cosa non devi toccare

- Il testo della domanda (`q`): resta identico.
- **Quale** alternativa è corretta: resta la stessa, nello stesso indice `answer`.
- Il numero di alternative: sempre cinque.
- Il numero di domande e i loro `id`.
- Il campo `slide`.

## Cosa devi cambiare

Il **testo delle alternative**, in modo che tutte e cinque abbiano struttura,
specificità e lunghezza paragonabili.

### Come si fa

1. **Accorcia la risposta corretta.** Spesso è lunga perché porta dettagli
   ridondanti o cautele inutili. Tieni il nucleo che la rende corretta e togli il
   resto, senza renderla incompleta o ambigua.
2. **Arricchisci i distrattori allo stesso livello.** Se la risposta corretta dice
   un meccanismo, dai a ciascun distrattore un meccanismo alternativo ugualmente
   specifico ma sbagliato. Un distrattore lungo ma plausibile è ottimo; un
   distrattore lungo e assurdo è peggio di uno corto.
3. **Rendi le cinque alternative parallele.** Se tre iniziano con un verbo e due con
   un sostantivo, uniforma. Se una cita un compartimento cellulare, citalo in tutte.
4. **Non riempire con parole vuote.** Vietato allungare un distrattore con
   "in modo significativo", "generalmente", "come è noto", "soprattutto". Vietato
   anche accorciare la risposta corretta fino a farla sembrare una nota a piè di
   pagina mentre i distrattori restano discorsivi.

### Esempio

Prima — la corretta è lunga il doppio delle altre:

```
D: Dove avviene la beta-ossidazione?
   A) Nel citosol
   B) Nel reticolo endoplasmatico
 ✓ C) Nella matrice mitocondriale, dove gli enzimi della beta-ossidazione sono
      organizzati in quattro tappe successive che accorciano la catena di due atomi
      di carbonio a ogni passaggio
   D) Nel nucleo
   E) Nei lisosomi
```

Dopo — cinque alternative parallele, tutte specifiche, la corretta non è più la più
lunga:

```
D: Dove avviene la beta-ossidazione?
   A) Nel citosol, dove operano gli enzimi della sintesi degli acidi grassi
   B) Nel reticolo endoplasmatico, dove si assemblano le lipoproteine
 ✓ C) Nella matrice mitocondriale, con quattro tappe che accorciano la catena di
      due atomi di carbonio per ciclo
   D) Nel nucleo, dove si trascrivono i geni degli enzimi ossidativi
   E) Nei lisosomi, dove si degradano i glicolipidi di membrana
```

La risposta corretta resta la C, ma ora lo studente deve conoscerla.

## Correggi anche la spiegazione, se serve

Se cambi la formulazione di un distrattore che la spiegazione citava, aggiorna la
spiegazione di conseguenza. La spiegazione continua a dover dire perché la risposta
corretta è corretta e perché il distrattore più insidioso è sbagliato.

## Autocontrollo obbligatorio

```
cd /Users/ozkan/projects/audiobook-forge/quiz-src && python3 validate_batch.py batches/deck<N>/batch<M>.json --slides <from>-<to>
```

Il validatore ora rifiuta il lotto se più del 30 per cento delle domande ha la
risposta corretta come alternativa strettamente più lunga, oltre a controllare
tutto il resto. Deve terminare con exit code 0 e stampare `OK`. Itera finché non
passa.

Nel file `batches/deck<N>/batch<M>.rebalance.txt` trovi l'elenco delle domande
segnalate nel tuo lotto, con le lunghezze delle alternative, così sai da dove
cominciare. Non è un elenco esaustivo: alla fine conta solo la percentuale del
lotto intero.

## Come rispondere

Una sola riga, senza altro testo:
`batches/deck<N>/batch<M>.json — ribilanciato — PASS`
