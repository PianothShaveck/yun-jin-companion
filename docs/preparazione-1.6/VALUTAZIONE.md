# Preparazione della 1.6 — 24 ottobre 2026

Base verificata: commit pubblico `5a84318db22747f6fe40adbc2e6f5c09704ce1f7`, tag `v1.5.7`.
Ramo di lavoro locale: `preparazione-1.6`. Nessuna release, pubblicazione,
connessione a Google Calendar o generazione di immagini eseguita in questa fase.
La versione installabile resta 1.5.7. Agosto e settembre restano da completare.

## Aggiornamento: conversione completa del catalogo

Completati 635 originali e 635 anteprime in una cartella separata: risparmio
globale misurato 11,088% e 30,619%, rispettivamente. Dettagli, comando e limiti
in [CATALOGO-CODEC.md](CATALOGO-CODEC.md); selezione per file in
`catalog-selection.json`. Gli asset distribuiti restano invariati.

## Risultato di questa fase

- README principale tradotto in inglese, senza presentare come disponibili le
  future lingue dell'interfaccia o la sincronizzazione. Per l'ultima indicazione
  dell'utente, note di rilascio in inglese da ora in poi, anche durante la
  preparazione della localizzazione. Descrizione GitHub proposta per la fase
  di pubblicazione: “A Yun Jin desktop companion with spaced repetition,
  an illustrated calendar, alarms, notes and music tools for Windows, macOS and Linux.”
- Esperimento JPEG XL riproducibile, confronto dei pixel, tempi di decodifica
  e tempo CPU; nessun asset convertito nel progetto. Seconda fase: verifica
  del caricamento reale dell'app, ampliamento della copertura dei mesi e confronto
  con altri codec. Totale: 138 confronti RGBA esatti, 58 file di input invariati.
- Inventario automatico delle superfici di traduzione, con limiti espliciti.
- Analisi del calendario reale e progetto tecnico della sincronizzazione;
  il motore di sincronizzazione e OAuth non sono ancora implementati.
- Prima modifica funzionale: conferma persistente dell'originale nel visualizzatore
  del calendario, con provenienza locale/cache/download e anteprima esplicita in
  caso di errore. Implementata nel ramo di preparazione, non ancora distribuita.
- Seconda modifica funzionale: decodifica dell'originale verificato fuori dal
  thread dell'interfaccia, con una sola decodifica attiva e annullamento dei
  risultati obsoleti. Nessuna conversione del catalogo o dipendenza aggiunta.

Nella prima fase il contatore non era disponibile negli strumenti esposti e il
browser non era autenticato. Nella seconda è stato trovato il metodo ufficiale
Codex app-server `account/rateLimits/read` e il binario locale 0.159.2. La richiesta
in sola lettura, ripetuta durante il lavoro, ha restituito HTTP 401 (autenticazione non riconosciuta): nessun
valore di utilizzo recuperato, nessun login modificato e nessun turno di modello
avviato tramite CLI. Il residuo più recente comunicato dall'utente è 8%, non una
misura autonoma. Non è quindi possibile garantire lo stop automatico al 3%.
L'ultimo incremento è circoscritto alla decodifica asincrona. Anche il controllo
durante questo incremento ha restituito HTTP 401; nessun residuo misurato.

## Incremento implementato: conferma dell'immagine visualizzata

Il visualizzatore prima cancellava il testo dopo il caricamento dell'originale;
ora mostra una conferma permanente e utile:

- «Anteprima · Caricamento originale…» durante il tentativo;
- «Originale · File locale» per un originale locale verificato, incluso il
  percorso dei sorgenti registrato dall'installer;
- «Originale · Cache» per un originale recuperato dalla cache sul dispositivo;
- «Originale · Scaricato» per un download appena concluso;
- «Anteprima · Originale non disponibile.» e «Riprova» se l'originale non è
  disponibile o non può essere decodificato.

La conferma richiede il controllo di dimensione/hash del catalogo e una
decodifica riuscita; non dipende dal sistema operativo, dalla risoluzione apparente
o dalla semplice esistenza di un file. Le dimensioni in pixel dell'immagine
visualizzata sono nel tooltip della conferma. Un file arbitrario fuori catalogo
resta apribile come «Immagine locale», senza essere dichiarato originale.
La provenienza non aggiunge nuovi download, timer periodici o cache. Nessun
percorso del disco o dettaglio del codec è esposto nell'interfaccia.

Verifica: 12 test del caricatore/dialogo superati, più 23 test del calendario UI.
Non eseguito in questa selezione il test di calendario su tutte le date reali,
perché il checkout contiene soltanto una parte delle illustrazioni. Ispezione
visiva offscreen del dialogo originale a 540 px e del fallback a 300 px:
stato leggibile, pulsanti separati, immagine proporzionata. Prove native Mac/Windows
ancora da fare. Note inglesi delle sole modifiche realizzate in `RELEASE-NOTES.en.md`.

## Incremento implementato: decodifica asincrona degli originali

Il passaggio dall'anteprima all'originale usa ora `OriginalDecoder`, che legge
il file con QImageReader su un worker Qt e consegna un QImage al thread GUI.
Soltanto il thread GUI crea la QPixmap e aggiorna il visualizzatore. L'anteprima
e «Caricamento originale…» restano visibili anche durante la decodifica;
«Originale» appare soltanto dopo il completamento riuscito.

La coda è condivisa dall'applicazione e ha un solo worker. Le richieste in attesa
conservano percorsi, non immagini decodificate; chiudere la finestra o sostituire
la richiesta le rimuove dalla coda. Un codec già in esecuzione viene lasciato
terminare senza bloccare la chiusura, ma il suo risultato viene scartato. Il
buffer visualizzato viene rilasciato subito alla chiusura; quello temporaneo del
codec può restare fino al termine del lavoro. Il thread inattivo scade dopo un
secondo; nessun timer periodico o cache in RAM aggiuntiva.

Verifica complessiva di questo incremento: **41 test superati** (5 coda/worker,
13 caricatore/dialogo, 23 calendario UI). Le prove usano anche una decodifica
artificialmente sospesa: un evento GUI e la chiusura vengono gestiti prima di
sbloccarla. Verificati: consegna sul thread principale, una sola decodifica,
eliminazione delle richieste in attesa alla distruzione del destinatario,
sostituzione di una richiesta senza pixel obsoleti, errori/ritentativo e arresto
della coda. Rimane escluso il test su tutte le illustrazioni reali nel checkout
parziale. Nessuna prova nativa Windows/macOS ancora eseguita.

Limiti: questo modifica la decodifica dell'originale caricato dal visualizzatore,
non il decoder Qt disponibile. **JPEG XL non è ancora abilitato.** Verifica hash,
anteprima iniziale, conversione finale QImage→QPixmap e caricamento di eventuali
file locali aperti direttamente restano sul thread GUI. Non è una promessa di
zero latenza complessiva, minore CPU o minor consumo energetico. Il calendario
e il suo sfondo continuano a usare le anteprime esistenti.

Riferimenti tecnici: [QImage e thread Qt](https://doc.qt.io/qt-6/threads-modules.html),
[QThreadPool](https://doc.qt.io/qt-6/qthreadpool.html).

## 1. JPEG XL: candidato valido, migrazione ancora da verificare

Il catalogo della 1.5.7 contiene 635 originali registrati nell'indice, per
957.213.682 byte. L'app carica le immagini tramite Qt; il supporto di un browser
non determina quello del runtime Python/Qt installato. Il runtime Linux di prova
usa PyQt 6.11.0 e Qt 6.11.2, esattamente le versioni dichiarate dall'installer:
`QImageReader.supportedImageFormats()` include WebP ma non JPEG XL.

Campione esplicito: YJ-085, 150, 250, 363, 410, 444, 468 e m10-a,
ciascuno originale e anteprima. Non è un campione casuale dell'intero catalogo.
Encoder/decoder: libjxl 0.12.0 tramite imagecodecs 2026.10.10. Pixel RGBA derivati
dal decoder Qt WebP; codifica JPEG XL lossless; tutti i 42 confronti RGBA sono
identici. Nessun filtro, ridimensionamento o modifica dell'anatomia.

Con effort 7 e un thread, sui sette file YJ il risparmio aggregato è **11,73% sugli
originali** e **9,84% sulle anteprime**. La vecchia m10-a, molto compatta in WebP,
aumenta invece del 250,46% (la sua anteprima usa gli stessi byte dell'originale).
Non è corretto applicare il 12% all'intero progetto o riconvertire tutto alla cieca.

Per verificare il compromesso velocità/spazio, YJ-444 è stata provata anche con
quattro thread e livelli di velocità di decodifica differenti, tutti lossless:

| Configurazione JXL, effort 7 | Risparmio originale | Decodifica originale: WebP → JXL | Risparmio anteprima | Decodifica anteprima: WebP → JXL |
| --- | ---: | ---: | ---: | ---: |
| 1 thread, velocità 0 | 11,24% | 26,1 → 353,5 ms | 9,26% | 9,5 → 123,8 ms |
| 4 thread, velocità 1 | 6,53% | 29,2 → 66,2 ms | 3,82% | 10,5 → 26,3 ms |
| 4 thread, velocità 2 | 4,62% | 27,8 → 45,5 ms | 2,23% | 10,1 → 17,4 ms |
| 4 thread, velocità 3 | −4,43% | 28,8 → 18,3 ms | −5,75% | 9,8 → 6,7 ms |
| 4 thread, velocità 4 | −6,30% | 32,8 → 16,3 ms | −7,98% | 10,0 → 6,1 ms |

Percentuale negativa = file più grande. Mediane di 9–11 decodifiche a caldo in
memoria; JXL include la copia in un QImage proprietario. Non sono tempi di avvio,
accesso al disco, download CDN o prove su un Mac/Windows reale. Non sono prove di
un plugin Qt nativo: un altro decoder potrebbe dare risultati diversi. Nessun
round-trip dei profili ICC/EXIF è stato certificato. Animazioni escluse.

La prima valutazione richiedeva un miglioramento simultaneo di spazio e velocità.
L'utente ha poi chiarito che un costo occasionale trascurabile è accettabile per
un risparmio globale del 10–12%. Il criterio corretto diventa quindi la fluidità
percepita e il costo complessivo, non l'assenza assoluta di rallentamento del codec.

### Approfondimento: stessa compressione con quattro thread

Il confronto mancante era effort 7, velocità di decodifica 0 e **quattro thread**.
Sui medesimi sette YJ recenti il risparmio aggregato rimane 11,73% negli originali
e 9,84% nelle anteprime. I tempi seguenti sono mediane delle mediane degli 11
caricamenti a caldo per ciascun file, non la durata di un singolo caricamento
reale da rete o disco:

| Immagini | WebP | JPEG XL | Attesa aggiuntiva | Intervallo JXL fra file |
| --- | ---: | ---: | ---: | ---: |
| Originali 1536×1024 | 29,0 ms | 111,9 ms | 82,8 ms | 98,1–123,4 ms |
| Anteprime 900×600 | 10,1 ms | 36,8 ms | 26,6 ms | 33,4–39,2 ms |

Il lavoro CPU totale, sommato sui thread, è diverso dall'attesa: mediana di
29,0 → 417,9 ms per originale e 10,1 → 138,9 ms per anteprima. È un breve picco
su più core, non un miglioramento energetico dimostrato. Non sono state misurate
potenza, batteria, picco di memoria o costi di primo caricamento delle librerie.
Su un dispositivo con pochi core non vanno promessi i tempi a quattro thread;
la prova precedente a un thread rimane il riferimento lento disponibile.

### Conseguenze nel calendario attuale

- `CalendarHero.set_month()` decodifica solo quando cambia l'immagine e non la
  trova nella cache di due elementi. La riduzione a calendario e lo sfondo
  condividono la stessa QPixmap; `paintEvent()` e il ridimensionamento non
  decodificano nuovamente. I due test esistenti dedicati a cache e resize passano.
- `IllustrationDialog` mostra prima l'anteprima e poi l'originale, se disponibile.
  Nella 1.5.7 il download è asincrono, ma anche l'originale viene decodificato sul
  thread GUI. Nel ramo 1.6 la decodifica dell'originale verificato è ora asincrona;
  le anteprime di `CalendarHero` e quella iniziale del dialogo restano sul thread
  GUI. Lo stesso originale riaperto dalla cache su disco deve comunque essere
  decodificato, ora attraverso il worker.
- Una volta visualizzata l'immagine, il codec non aggiunge lavoro continuativo.
  Non cambia il costo di animazione del companion: queste prove riguardano
  soltanto le illustrazioni statiche del calendario.
- A parità di pixel un buffer RGBA vale circa 2,06 MiB a 900×600 e 6 MiB a
  1536×1024, indipendentemente dal formato su disco. Due anteprime valgono circa
  4,12 MiB di soli pixel. Decoder, copie temporanee e QPixmap nativa possono
  aggiungere memoria: non confondere questi numeri con il picco dell'app.
- La cache degli originali su disco ha un limite di 64 MiB, distinto dalla cache
  di due anteprime decodificate. File più compatti possono farci stare più immagini;
  non riducono necessariamente una cache che è già piena al suo limite.

Il worker descritto sopra è ora implementato e provato con richieste lente,
chiusura e sostituzione. La migrazione a JXL richiede ancora decoder e prove
sulle piattaforme native; spostare il lavoro fuori dalla GUI non riduce da solo
né tempo CPU né attesa dell'immagine.

Per YJ-444 l'originale risparmia 196.454 byte. A 10 Mbit/s di trasferimento
effettivo questo equivale teoricamente a circa 157 ms; nella stessa prova la
decodifica aggiunge circa 71 ms. Il download può quindi compensare il costo,
ma su disco locale o rete rapida quel vantaggio si riduce. È un esempio aritmetico,
non una misura CDN; non include latenza, cache di rete o apertura connessione.

### Copertura ampliata: 29 illustrazioni, ciascuna originale e anteprima

Il campione ora include 17 scene YJ dei dieci mesi già popolati e una scena
storica per ciascuno dei dodici mesi, per 58 file distinti. I due JSON
`codec-benchmark-compact-4threads.json` e `codec-benchmark-month-coverage.json`
registrano le misure; tutti i pixel RGBA sono identici e gli hash dei 58 input
sono rimasti invariati.

Con JXL compatto, sui 17 YJ il risparmio aggregato è **11,31% per gli originali**
e **9,42% per le anteprime**. Tutti e dodici i file storici crescono invece,
del 262,69% aggregato. I loro byte originali e anteprima coincidono già: il
generatore di anteprime conserva il file più piccolo invece di ricodificarlo.
L'ispezione dei contenitori chiarisce la distinzione: i 34 file YJ hanno payload
WebP VP8L lossless, i 24 storici payload VP8 lossy. Passare questi ultimi a un
formato lossless conserva i pixel decodificati, ma non recupera dettagli già
persi e in queste prove ingrandisce molto il file. Non ricomprimerli di nuovo
con perdita per far apparire conveniente un risultato che non è a parità di pixel.

Nel campione intero, selezionare JXL soltanto quando più piccolo darebbe 9,96%
sugli originali e 6,99% sulle anteprime. Queste **non sono percentuali globali**:
i file storici sono sovrarappresentati nel campione (12/29, contro 84/635 nel
catalogo). Nell'indice completo i 551 YJ originali occupano 928.782.780 byte e
gli 84 storici 28.430.902 byte. Serve ancora un conteggio su tutti i file per
una decisione di migrazione e un risparmio netto delle dipendenze aggiunte.

### Compromesso intermedio e formati alternativi

Su YJ-444, originale e anteprima, sono stati provati sette candidati: WebP
lossless ricompresso con Pillow (`quality=100`, `method=6`, `exact=True`), JXL
effort 7/velocità 1 e 2/quattro thread, PNG ottimizzato, AVIF lossless RGB 4:4:4
con matrice identità, JPEG-LS senza errore e QOI. Tutti e 14 i risultati hanno
pixel RGBA identici; le configurazioni complete sono nel JSON del pilota.

Su questo solo soggetto PNG cresce del 28–30%, AVIF del 19–21%, JPEG-LS del
12–13%, senza migliorare la velocità rispetto a WebP. QOI è molto rapido
(circa 12 ms originale, 4 ms anteprima) ma cresce del 69–72%. Sono esiti di una
prova preliminare con queste impostazioni, non una classifica universale dei
formati. AVIF è stato decodificato tramite libavif/imagecodecs, non dal Qt di
produzione. Non è stato usato il comune AVIF con sottocampionamento/perdita
spacciandolo per equivalente.

WebP ottimizzato e le due configurazioni JXL intermedie sono stati poi provati
anche su YJ-112, YJ-280, YJ-716 e m10-a, originali e anteprime: altri 24 confronti
esatti. Il confronto seguente riguarda i quattro YJ complessivi (quattro
originali e quattro anteprime); la scena storica è esclusa dalla tabella perché
ricodificarla lossless ingrandisce il file con tutti i candidati.

| Formato/configurazione | Risparmio originali | Lettura originali | Risparmio anteprime | Lettura anteprime |
| --- | ---: | ---: | ---: | ---: |
| WebP attuale | — | 30,4 ms | — | 10,4 ms |
| WebP lossless ottimizzato | 1,14% | 28,6 ms | 2,16% | 10,4 ms |
| JXL effort 7, velocità 1, 4 thread | 6,36% | 64,2 ms | 3,39% | 24,3 ms |
| JXL effort 7, velocità 2, 4 thread | 4,38% | 48,0 ms | 2,01% | 18,6 ms |

Risparmi aggregati sui byte; tempi mediane delle mediane per file. La differenza
fra 28,6 e 30,4 ms non basta a dimostrare un miglioramento stabile di velocità:
WebP resta sostanzialmente equivalente. Nel campione JXL velocità 2 per le
anteprime perde sia in spazio sia in velocità rispetto al WebP ottimizzato.
JXL velocità 1 per gli originali è invece un compromesso concreto: circa 34 ms
aggiuntivi e 6,36% in meno sui byte. Il tempo CPU mediano di questa opzione è
circa 241 ms, contro 30 ms del WebP; l'attesa più breve usa più core, non annulla
il costo di elaborazione. Le prove non sono misure energetiche.

Questi benchmark sono riproducibili con `tools/benchmark_calendar_alternatives.py`;
i JSON `codec-alternatives-pilot.json` e `codec-alternatives-coverage.json`
conservano versioni, opzioni, hash e campioni temporali. Il parametro `quality=100`
con WebP lossless indica sforzo di compressione; non è una nuova ricodifica lossy.
Nessun asset, indice o pacchetto della release è stato modificato.

### Altre riduzioni di spazio, senza cambiare i pixel

- **Ricompressione WebP offline e selettiva:** mantenere un candidato soltanto
  se più piccolo e se Qt restituisce gli stessi pixel e metadati necessari.
  Il lavoro di codifica avviene nella preparazione, non sul dispositivo dell'utente;
  nessuna dipendenza aggiuntiva nel runtime. Da misurare su tutto il catalogo
  prima di promettere il 2% globale. Il generatore corrente usa l'encoder Qt e
  già evita alcune anteprime lossless più grandi del file originale.
- **Anteprime dei mesi su richiesta:** distribuire un insieme iniziale ridotto
  e scaricare le altre anteprime identiche dal CDN quando servono, con cache
  limitata. Potrebbe ridurre molto più del 10% il pacchetto, ma cambia la
  disponibilità offline: un mese mai scaricato richiede rete e la prima apertura
  può attendere il download. Precaricamento limitato dei giorni vicini solo quando
  il calendario è usato; nessun servizio o trasferimento periodico permanente.
  È una proposta, non una modifica realizzata, e non va confusa con la cache
  degli originali già presente. Chi vuole tutto offline dovrebbe poterlo conservare.
- Non aspettarsi un grande guadagno dalla sola compressione ZIP: il packaging
  usa già DEFLATE livello 9, e le immagini sono già compresse. Anche eliminare
  gli originali dal runtime è un intervento già fatto nella 1.5.7, non un nuovo
  risparmio da sommare.

### Nuovo requisito: anteprime percettivamente fedeli, originali lossless

L'utente ha autorizzato una compressione non strettamente lossless delle sole
anteprime, purché si vedano molto bene. Gli originali restano rigorosamente
lossless. Questo aggiorna il criterio precedente di pixel identici anche per le
anteprime e rende rilevante la proposta near-lossless di WebP.

Prova con **cwebp 1.6.0 ufficiale**, `-z 9 -near_lossless LIVELLO`, quattro
anteprime opache a 900×600 (YJ-085, 410, 444, 716). Controllo lossless al livello
100, misure Qt a caldo ripetute 11 volte per file. Nessun cambiamento di
risoluzione; alpha identico; file di partenza invariati. Risparmi aggregati rispetto
alle anteprime attuali, tempi mediane delle mediane per file:

| Opzione | Risparmio | Decodifica Qt | Errore RGB massimo nel campione |
| --- | ---: | ---: | ---: |
| WebP attuale | — | 10,1 ms | — |
| Lossless ottimizzato, livello 100 | 2,27% | 10,4 ms | 0 |
| Near-lossless 90 / 80 | 19,74% | 9,8 / 10,2 ms | 1 su 255 |
| Near-lossless 60 | 33,28% | 8,0 ms | 2 su 255 |

80 e 90 producono gli stessi pixel e byte su questi file; non sono una scala
continua di percentuale qualitativa. PSNR minimo 51,68 dB per 80/90 e 47,26 dB
per 60, ma questi valori non certificano da soli la qualità percepita. Ispezione
visiva delle quattro coppie ridotte a 450×300 e del volto/capelli/occhi di YJ-444
ingrandito al 200%: nessun deterioramento evidente nel confronto effettuato.
Non è un'approvazione di tutti i 635 file né una promessa su ogni display.

**Correzione del protocollo:** alla prima prova era stato aggiunto `-exact` anche
ai livelli near-lossless per preservare eventuali RGB trasparenti. Il controllo
dei pixel ha mostrato che tutti i livelli erano rimasti identici. Il sorgente
libwebp 1.6.0, `src/enc/predictor_enc.c`, conferma che `GetResidual()` con `exact`
salta la quantizzazione near-lossless. Rimosso questo flag dai livelli inferiori
a 100 e ripetute tutte le misure. Il controllo iniziale è conservato nel JSON
`codec-preview-exact-control.json`; i risultati validi nel JSON
`codec-preview-near-lossless.json`. Non confondere i due esperimenti.

Lo strumento `tools/benchmark_calendar_previews.py` accetta solo percorsi
`calendar-preview`, scrive in una cartella separata, rifiuta per ora anteprime
non opache nei test near-lossless e verifica dimensioni/alpha e il controllo
lossless. Non modifica originali, anteprime del progetto, indice o packaging.
Prima di adottare la compressione: verifica su tutto il catalogo e controllo dei
volti, sfumature, bordi e colori; mantenere il file precedente quando più piccolo
o qualitativamente preferibile, aggiornare manifest e test del generatore.
Il test esistente di uguaglianza esatta delle anteprime non è stato indebolito:
gli asset distribuiti non sono ancora cambiati.

Valutazione delle proposte ricevute:

1. **Near-lossless 60:** tecnicamente sensato e qui confermato intorno al 33%,
   ma «30–50%», «impercettibile» e «10 ms» non sono garanzie generali. Restare
   nel decoder VP8L evita una nuova dipendenza, non rende costante il tempo di lettura.
2. **WebP `-z 9`:** equivale nel sorgente 1.6.0 a metodo 6 e qualità 100.
   Era già sostanzialmente incluso nel confronto Pillow lossless. Da solo non
   dà i risparmi del near-lossless. Il 6,4% citato per JXL era la configurazione
   intermedia; la più compatta aveva raggiunto 11,31% sui 17 originali YJ testati.
3. **JXL effort 9, group size e pixel invisibili:** parametri reali e candidati
   per un esperimento successivo, non risultati acquisiti. `faster_decoding=2/3`
   scambia densità per velocità; il group size predefinito è scelto dall'encoder,
   non sempre 256×256. Non è garantito un altro 1–2%. I quattro file di questa
   prova sono opachi, quindi eliminare RGB sotto alpha zero non dà alcun risparmio.
   Sugli originali non sacrificare quei valori senza ridefinire esplicitamente
   il criterio di uguaglianza dei pixel.
4. **JXL distanza 0,1/0,2:** è con perdita, anche se può apparire fedele; escluso
   per gli originali in base al requisito espresso. Nessuna promessa di
   indistinguibilità al 400% o risparmio 40–60% senza misure e confronto visivo.

Ulteriori precisazioni sulla seconda proposta ricevuta: 8,0 contro 10,1 ms è
circa il 20% in meno per la sola decodifica misurata, non per l'apertura completa
del calendario. Una minore entropia può aiutare, ma non abbiamo profilato i singoli
passaggi Huffman/LZ77. Due livelli su 255 nei canali sRGB non equivalgono a una
soglia universale di impercettibilità né a una percentuale di luminanza percepita.
Il risparmio del 33,28% riguarda quattro anteprime, non l'intero installer.
Il vantaggio di 60 su 80 è 13,54 punti percentuali rispetto al file iniziale,
circa il 16,9% rispetto al peso ottenuto a 80. I conteggi 551 YJ/84 storici
provengono dall'indice: non certificano il tipo VP8L/VP8 di ogni singolo file.
Una conversione dovrà verificare il codec di ciascun input e mantenere il file
precedente se il risultato non è più piccolo o non supera il controllo visivo.

Fonti: [cwebp](https://developers.google.com/speed/webp/docs/cwebp),
[predittore libwebp 1.6.0](https://github.com/webmproject/libwebp/blob/v1.6.0/src/enc/predictor_enc.c),
[preset libwebp 1.6.0](https://github.com/webmproject/libwebp/blob/v1.6.0/src/enc/config_enc.c),
[parametri cjxl](https://github.com/libjxl/libjxl/blob/main/tools/cjxl_main.cc).

**Decisione aggiornata dopo il chiarimento dell'utente:** per gli originali del
calendario aperti in grande, privilegiare JXL lossless più compatto (nel benchmark:
effort 7, velocità di decodifica 0), non necessariamente la configurazione
intermedia. Il risultato disponibile è 11,31% sui 17 originali YJ del campione.
Un'attesa occasionale nell'ordine di mezzo secondo è accettata; non è una promessa
sul tempo totale, che dipende anche dalla rete e dal dispositivo. La GUI deve
rimanere utilizzabile durante download e decodifica, con lavoro e memoria limitati.
Valutare pochi thread nel worker, senza impegnare automaticamente tutti i core
solo per abbreviare un'attesa già accettabile. Conservare WebP dove più piccolo.

La parola **originali** in questa analisi indica esclusivamente le illustrazioni
del calendario aperte a piena risoluzione. Non include meteo, sprite, animazioni
o altre immagini dell'interfaccia, che non sono state confrontate in questi test.
Per anteprime e sfondi del calendario, meteo e animazioni, priorità alla velocità
e alla percezione invariata dell'app: niente JXL più lento applicato per estensione.
WebP ottimizzato senza perdita resta il primo candidato per le anteprime; eventuali
ottimizzazioni di meteo e animazioni richiedono misure separate di caricamento,
trasparenza, memoria e, per le sequenze, tutti i frame e la riproduzione effettiva.

Il prototipo JXL richiede ancora un decoder minimo distribuibile su
Windows/macOS/Linux e caricamento che non blocchi la GUI. Poiché gli originali
sono già esterni al runtime, questa scelta riduce soprattutto progetto/CDN/cache,
non automaticamente il pacchetto dell'app. Non distribuire l'intero ambiente di
analisi imagecodecs/numpy soltanto per JXL. Il 10–12% non è ancora certificato
globalmente; la dimensione del decoder va sottratta al risparmio effettivo.

Prima di migrare: prove native, colori/metadati conservati, test separati delle
animazioni se mai incluse, dimensione netta del decoder e compatibilità degli
aggiornamenti. Occorre aggiornare insieme indice, hash, CDN, cache e packaging,
conservando i file precedenti durante la transizione. Nessun cambiamento della
UI è necessario per mostrare all'utente quale codec sia stato scelto.

Riproduzione in un ambiente di sviluppo separato (non sono nuove dipendenze dell'app):

```bash
python tools/benchmark_calendar_codecs.py app/assets/calendar/YJ-444.webp app/assets/calendar-preview/YJ-444.webp --output prova-codec.json --effort 7 --threads 4 --decoding-speed 2
```

I JSON allegati riportano hash degli input, versioni, parametri e tutte le misure.

Fonti: [Qt Image Formats](https://doc.qt.io/qt-6/qtimageformats-index.html),
[implementazione ufficiale libjxl](https://github.com/libjxl/libjxl),
[contenitore WebP](https://developers.google.com/speed/webp/docs/riff_container),
[opzioni Pillow](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html),
[matrici colore AVIF](https://github.com/AOMediaCodec/libavif/wiki/CICP).

## 2. Localizzazione completa: lavoro significativo, da fare senza lingue parziali

L'audit AST trova **856 argomenti testuali candidati, 659 distinti**, in chiamate
note a controlli, errori e guida. Sono candidati da esaminare, non 659 messaggi già
validati: alcune stringhe sono tecniche, altre passano attraverso variabili e non
sono incluse. La guida sorgente ha 19 sezioni oltre alla copertina. I saluti e le
frasi meteo hanno già versioni nelle tre lingue, ma non l'interfaccia generale.

Superfici da completare prima di rendere selezionabili English e 简体中文:

1. Pannello, menu, finestre separate, calendario, sveglie, studio, musica, meteo,
   note, scorciatoie, import/export, backup e aggiornamenti.
2. Validazioni, errori di rete e database, avvisi di permesso del sistema operativo,
   messaggi dell'installer e problemi che avvengono prima dell'avvio della GUI.
3. Mesi, giorni, plurali, durate, date, numeri e controlli nativi Qt; nomi
   accessibili e suggerimenti. Evitare concatenazioni di frammenti tradotti.
4. Guida nelle tre lingue, comprese didascalie e schermate. Per il cinese serve
   anche un font CJK incorporabile nel PDF: DejaVu Sans attuale non basta.
5. Prompt predefiniti e testi generati dall'app; non tradurre il contenuto personale
   di appunti, carte o eventi. Tenere separata la lingua della voce da quella della UI.

Architettura proposta: cataloghi Qt Linguist con contesti stabili, marcatura
esplicita delle stringhe e `QTranslator` caricato prima di costruire le finestre.
Usare anche le traduzioni dei controlli Qt e `QLocale`, eliminando i mesi italiani
hardcoded e i locale italiani forzati. Condividere i cataloghi anche con gli
errori dei moduli di dominio, invece di cercare/sostituire il testo dei widget.

Primo avvio: un'unica scelta con i nomi nativi **Italiano / English / 简体中文**,
preselezione dalla lingua del sistema e una breve frase, nella lingua selezionata,
che indica la possibilità di cambiarla nelle Impostazioni. Per chi aggiorna,
conservare l'italiano come lingua dell'interfaccia finché non la cambia: la scelta
attuale della voce non dimostra una preferenza per l'interfaccia. Non aggiungere
banner, badge tecnici o spiegazioni permanenti nel calendario.

Per il cambio successivo, preservare bozze ed editor aperti. Prima di abilitare una
lingua: controllo cataloghi mancanti/placeholder/plurali, verifica visiva con testi
lunghi e caratteri CJK, tutti i percorsi di errore, UI nativa Windows/macOS e guide
rigenerate. L'inventario automatico da solo non certifica che sia tradotto tutto.

Stato: README inglese pronto nel ramo locale; cataloghi, selettore e guide tradotte
ancora da realizzare. Descrizione pubblica GitHub non modificata in questa fase.

### README e note della 1.6: parità editoriale fra lingue

Quando interfaccia e guida nelle tre lingue saranno complete e verificate, il
README destinato alla 1.6 dovrà eliminare la frase provvisoria che descrive UI e
guida come attualmente italiane, e l'etichetta «Italian» dal collegamento alla
guida. Il README oggi presente descrive ancora la 1.5.7: questa nota non va
trascinata nella documentazione della nuova versione. Inglese come lingua
predefinita del README pubblico; scelta della lingua fra le funzionalità, con
collegamenti alle guide effettivamente prodotte.

Testo della funzionalità, da utilizzare solo al completamento della localizzazione:

- IT: «Interfaccia e guida illustrata in italiano, inglese e cinese semplificato;
  scegli la lingua al primo avvio o cambiala in qualsiasi momento nelle impostazioni.»
- EN: “Interface and illustrated guide in Italian, English and Simplified Chinese;
  choose your language at first launch or change it at any time in settings.”
- 简体中文：「界面和图文指南支持意大利语、英语和简体中文；首次启动时选择语言，也可随时在设置中更改。」

Per UI, guida, README e note di rilascio mantenere la stessa impostazione,
struttura, ordine, tono conciso e quantità di informazioni in tutte le lingue.
Niente spiegazioni extra, omissioni, testi promozionali o istruzioni semplificate
solo in una delle versioni. La lunghezza in caratteri può cambiare naturalmente,
specialmente in cinese: la parità riguarda contenuti e livello di dettaglio,
non un numero identico di caratteri. Conservare placeholder, link, scorciatoie,
esempi e condizioni; adattare solo le convenzioni linguistiche e locali necessarie.
Le note della 1.6 descriveranno la scelta fra tre lingue come novità realizzata,
senza avvisi storici sull'italiano della versione precedente. L'ultima istruzione
dell'utente stabilisce note di rilascio in inglese da ora in poi, anche prima della
localizzazione completa, e sostituisce la precedente preferenza per l'italiano.

Riferimento: [internazionalizzazione in Qt](https://doc.qt.io/qt-6/internationalization.html).

## 3. Google Calendar: sincronizzazione bidirezionale, senza server obbligatorio

Proposta per la 1.6: collegamento Google opzionale, calendari selezionabili,
calendario predefinito per i nuovi eventi e copia locale utilizzabile offline.
Nelle impostazioni bastano account, calendari, stato utile con ultima
sincronizzazione/errore, “Sincronizza ora” e “Scollega”. Le informazioni tecniche
restano nei log, senza token o contenuti privati. Le sveglie personali restano locali.

Il telefono legge lo stesso calendario Google. Yun Jin carica gli eventi mentre
è aperta e connessa, dopo ogni modifica; scarica le modifiche all'avvio, alla
riattivazione e periodicamente con intervallo moderato e backoff. Le modifiche
offline attendono il ritorno della connessione. Non promettere sincronizzazione
con il computer spento. Le notifiche push Google richiedono un endpoint HTTPS:
per questa app desktop preferisco inizialmente sincronizzazione incrementale
periodica, evitando un server personale da mantenere.

### Cosa manca al modello attuale

- `AgendaStore.delete()` elimina subito le righe: servono tombstone e una coda
  persistente per notificare anche le cancellazioni effettuate offline.
- Associare ogni evento a account/calendario/ID remoto; conservare `etag`, ultima
  versione comune, revisione locale e stato della coda. Nessuna associazione per
  titolo/data: due appuntamenti uguali possono essere distinti.
- `_wall()` oggi rifiuta gli offset e le ore ripetute autunnali scelgono il primo
  istante. Prima dell'import serve rappresentare senza ambiguità gli istanti
  remoti e il fuso IANA, preservando le ricorrenze in ora locale.
- Il formato delle ricorrenze è un sottoinsieme esplicito: occorre gestire serie,
  eccezioni spostate e cancellate. Le regole non rappresentabili vanno conservate
  integralmente e mostrate con modifica limitata, non convertite con perdita.
- Il limite attuale di 2.000 elementi non può causare importazioni parziali
  silenziose o cancellazioni dedotte dall'assenza di righe. Mirror remoto,
  paginazione, limiti e notifiche locali devono essere progettati insieme.
- Le transazioni locali attuali non includono una coda di sincronizzazione;
  il salvataggio dell'evento e dell'operazione in uscita deve diventare atomico.

### Regole per evitare perdita di dati

- Confronto a tre vie fra ultima versione comune, copia locale e remota. Modifiche
  indipendenti possono unirsi; due modifiche incompatibili o modifica contro
  cancellazione vanno conservate e proposte all'utente, senza scegliere in base
  all'orologio del computer.
- Aggiornamenti e cancellazioni condizionati all'ETag (`If-Match`). Risposta 412:
  rileggere e riconciliare. Creazioni con ID stabile e recupero del risultato dopo
  un timeout, evitando un secondo evento al nuovo tentativo.
- Applicare tutte le pagine di un aggiornamento prima di salvare `nextSyncToken`.
  Su 410 rifare il mirror remoto, conservando coda locale e conflitti. Un errore
  di rete o una lista parziale non equivale a un evento cancellato.
- Usare patch dei campi gestiti e preservare invitati, conferenze, allegati e
  metadati Google non supportati. Non inviare inviti o notifiche agli ospiti come
  effetto involontario della sincronizzazione.
- Disconnessione e revoca non devono cancellare calendari remoti. Backup e log
  non devono contenere token OAuth; credenziali nel portachiavi del sistema.

### Autenticazione e verifica

Servirà un progetto Google Cloud dell'app, API Calendar abilitata, client OAuth
desktop e schermata del consenso. Accesso nel browser di sistema con PKCE,
`state` e callback loopback temporanea; niente password raccolte nell'app.
Il collegamento Google di questa chat non abilita automaticamente gli utenti
di Yun Jin. Configurazione e consenso saranno necessari per le prove reali,
ma non per scrivere e testare offline il motore.

Scegliere gli scope in base alla prima funzionalità: un calendario creato dall'app
consente accesso più ristretto; per calendari personali esistenti serve accesso
agli eventi dei calendari posseduti e lettura dell'elenco. La scrittura sui
calendari condivisi richiede una valutazione separata dello scope più ampio.
La lista selezionata nell'app non restringe da sola il permesso OAuth concesso.
Prima della distribuzione pubblica verificare i requisiti Google di verifica
dell'app e di pubblicazione; niente credenziali di prova distribuite agli utenti.

Test necessari: creazione/modifica/cancellazione da entrambi i lati; riavvio a metà
operazione; retry e duplicati; 401/403/410/412/429; più pagine e interruzione tra
pagine; conflitti e ripristino backup; revoca e cambio account; tutto il giorno
con fine esclusiva; fusi diversi, ora legale, ricorrenze ed eccezioni; notifiche
locali senza avvisi arretrati duplicati. Poi prove su un calendario di test e su
Windows/macOS, prima di proporre una release.

Fonti ufficiali:
[OAuth desktop](https://developers.google.com/identity/protocols/oauth2/native-app),
[scope Calendar](https://developers.google.com/workspace/calendar/api/auth),
[sincronizzazione incrementale](https://developers.google.com/workspace/calendar/api/guides/sync),
[ETag e scritture condizionali](https://developers.google.com/workspace/calendar/api/guides/version-resources),
[ricorrenze](https://developers.google.com/workspace/calendar/api/guides/recurringevents),
[push](https://developers.google.com/workspace/calendar/api/guides/push),
[risorsa evento](https://developers.google.com/workspace/calendar/api/v3/reference/events).

## Ripresa del lavoro

Ordine consigliato: modello locale/outbox e test di sincronizzazione; adapter
Google e OAuth; localizzazione completa comprensiva della nuova UI; guide e prove
native; immagini rimanenti; infine packaging e pubblicazione 1.6. Sono fasi da
completare, non funzionalità già disponibili. I nuovi script e i rapporti sono
strumenti di sviluppo e non vanno aggiunti al runtime dell'app.
