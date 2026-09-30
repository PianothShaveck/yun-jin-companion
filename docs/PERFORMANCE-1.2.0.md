# Prestazioni della 1.2.0

Confronto locale del 30 settembre 2026, stesso interprete Python 3.12.14,
PyQt6 6.11.0 / Qt 6.11.2, Linux, backend Qt offscreen. Misure di processo,
non una promessa sul consumo di qualsiasi computer. Le API esterne non sono
chiamate durante il benchmark.

| Scenario | 1.1.2 | 1.2.0 |
| --- | ---: | ---: |
| Memoria residente dopo l’avvio | 151,8 MiB | 93,9 MiB |
| Memoria con pannello e cronometro aperti | 157,3 MiB | 109,7 MiB |
| CPU a riposo, millisecondi per secondo | 14,21 | 5,30 |
| CPU con cronometro nascosto, ms/s | 15,91 | 5,32 |
| CPU con cronometro visibile, ms/s | 65,09 | 14,26 |
| Ridisegni del personaggio a riposo, al secondo | 31,4 | 2,8 |
| Costruzione del personaggio e dei servizi, secondi | 0,969 | 0,096 |

5,30 ms di CPU per secondo corrispondono a circa **0,53% di un singolo core**.
La misura include i timer ordinari di movimento e promemoria. Ogni scenario
è osservato per sei secondi, con animazione idle attiva, sguardo e decisioni
casuali neutralizzati per rendere il confronto ripetibile. La costruzione
non comprende il caricamento iniziale dell’interprete o delle librerie.
Le prime misure indipendenti davano risultati simili; sono riportati i numeri
dell’ultimo confronto sequenziale, conservati in `performance-1.2.0.json`.

## Cosa è cambiato

- Gli originali restano intatti. Le clip già allineate sono incluse come PNG
  senza perdita: il processo di preparazione verifica l’identità esatta dei
  pixel. All’avvio vengono decodificati solo gli sprite originali; la cache
  mantiene al massimo due clip aggiuntive. Se manca un PNG preparato, resta
  disponibile il percorso di allineamento originale.
- Il timer del personaggio conserva i 33 ms e tutti i tempi delle animazioni.
  Il disegno viene richiesto solo quando cambia il fotogramma visibile,
  compresi sguardo e battito delle palpebre. Gli avvisi ridisegnano il badge
  solo quando cambia il numero dei promemoria.
- Il cronometro mantiene conteggio monotono e parziali. Il timer grafico
  funziona solo quando è in corso e la sua pagina è visibile. Le cifre non
  provocano più il ricalcolo dell’intero layout a ogni decimo di secondo.
- Orario: una verifica al minuto, senza nuove interrogazioni rapide. Meteo:
  un processo temporaneo circa ogni ora, massimo 12 secondi, risposta fino
  a 32 KiB, cache meteo di un’ora e posizione di 24 ore. Nessuna dipendenza
  aggiuntiva, thread permanente o attesa di rete sul thread dell’interfaccia.
- I testi fissi in mandarino riutilizzano la cache vocale esistente. La sintesi
  di un audio nuovo può avviare temporaneamente il generatore vocale, come
  già avviene per la lettura manuale.

## Ripetere la misura

```bash
python tools/benchmark_performance.py /percorso/alla/versione-1.1.2
python tools/benchmark_performance.py /percorso/alla/versione-1.2.0
```

Eseguire in sequenza sullo stesso computer. I dati includono RSS, CPU e numero
di eventi di disegno; il backend offscreen serve alla ripetibilità. Su macOS
verificare inoltre Monitoraggio Attività con overlay attivo e audio reale;
su Windows usare Gestione attività. Questi percorsi nativi non sono simulati
dal benchmark Linux. Il consumo durante audio, sintesi vocale, caricamento
iniziale di una clip o apertura delle finestre sarà temporaneamente maggiore.

I test automatici controllano limiti della cache, temporizzazione dei frame,
blink, badge e pausa/ripresa dell’aggiornamento grafico del cronometro. Non
impongono soglie di tempo o RAM dipendenti dall’hardware ai runner GitHub.
