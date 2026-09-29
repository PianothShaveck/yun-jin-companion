# Yun Jin Companion

Una piccola compagna per il desktop: appunti, promemoria vocali, focus, cronometro e metronomo con scalata. Versione **1.1.1**.

## Avvio

Scarica ed estrai il pacchetto completo. Chiudi eventuali versioni precedenti.

| Sistema | Primo avvio | Avvii successivi |
| --- | --- | --- |
| Windows 10/11 x64 | Doppio clic su `Windows.cmd` | Collegamento **Yun Jin Companion** sul desktop |
| macOS 13+, Intel / Apple Silicon | Apri `Mac.command`; autorizzalo se macOS lo blocca | **Yun Jin Companion.app** in Scrivania o `/Applications` |
| Linux desktop x64 | `bash Linux.sh` con Python e venv installati | Menu applicazioni |

Gli avviatori Windows e macOS cercano Python; se manca, scaricano l'installer ufficiale e ne verificano SHA-256. Le dipendenze sono installate in un ambiente privato. Sul Mac completa l'installer di Python quando richiesto. Serve Internet per la prima installazione e per la sintesi vocale.

**macOS: se Mac.command viene bloccato perché lo sviluppatore non è verificato**, dopo il tentativo di apertura vai in **Impostazioni di Sistema → Privacy e Sicurezza → Apri comunque**, poi conferma **Apri**. Fallo per il pacchetto scaricato dalla release ufficiale. Il semplice doppio clic può non bastare; una nuova copia scaricata può richiedere una nuova approvazione. Procedura Apple: https://support.apple.com/it-it/102445

La guida unica e completa è [Guida.pdf](Guida.pdf), disponibile anche dal pulsante **Guida** nell'app. Include installazione, funzioni, comandi per ogni sistema, backup e aiuto.

## Correzioni della 1.1.1

- Gli avvisi di **Controlla ora** su macOS compaiono sopra il pannello Impostazioni. La chiusura dell’avviso restituisce il controllo al pannello.
- Corretto il tipo di finestra usato dai messaggi modali con overlay; la stessa gestione copre gli errori e le conferme degli aggiornamenti.
- **Guida indipendente dalla versione dell’app:** nessun numero in copertina, intestazioni o piè di pagina. La data di revisione nei crediti cambia solo quando cambiano i contenuti.

## Novità della 1.1.0

- Menu a tendina visibili anche nei pannelli macOS sopra le app a schermo intero.
- **Seguimi** interrompe l’animazione in corso e mantiene la richiesta durante
  i due secondi di attesa. Funziona anche dopo una pausa; se il cursore esce dal
  monitor, Yun Jin attende il suo ritorno durante i nove secondi dell’inseguimento.
- Il campanello dei promemoria suona anche con il metronomo attivo, senza
  interromperlo. Restano rispettati volume, Suoni e Silenzio per un’ora.
  La lettura automatica dei promemoria rimane sospesa durante il metronomo.
- **Aggiornamenti**: controllo automatico dopo circa 30 secondi e ogni 2 ore,
  note di rilascio leggibili, **Aggiorna e riavvia**, **Più tardi** e
  **Salta questa versione**. Controllo disattivabile e ricerca manuale nelle impostazioni.
- **Sonno**: addormentamento (8 frame), respiro lento (6 frame di riproduzione)
  e risveglio (8 frame). **Addormentata** precede **Tranquilla** nel menu Carattere.
  **Sonnellino** esegue un breve episodio. Gli episodi spontanei sono occasionali.
- Guida illustrata aggiornata, con pagine dedicate ad aggiornamenti e sonno.

### Come funzionano gli aggiornamenti

Le versioni 1.0.x vanno aggiornate manualmente alla 1.1.0. Dalla 1.1.0,
la ricerca delle release stabili è attiva di default. L’avviso automatico
attende la fine di voce, metronomo, cronometro o focus; non forza il riavvio.
Le note vengono dal testo della release GitHub e si leggono nell’app.
**Più tardi** rimanda di circa due ore. **Salta questa versione** memorizza
solo la versione esclusa; le successive vengono ancora proposte.
**Controlla ora** permette di rivedere anche quella saltata.

Il download e l’installazione partono dopo **Aggiorna e riavvia**. L’app verifica
la provenienza dello ZIP, SHA-256 fornito da GitHub, percorsi e hash dei file.
Salva gli appunti, si chiude e aggiorna la **cartella dei moduli effettivamente
in uso**, compresi percorsi spostati e cartelle con spazi. Preserva dati personali
e file estranei al programma. Una copia di ripristino consente di annullare
errori durante la sostituzione e un avvio fallito; un diario permette il recupero
anche dopo un’interruzione. Il programma di aggiornamento aspetta la chiusura
dell’istanza prima di sostituire i file. La cartella deve essere scrivibile.

Gli aggiornamenti integrati non avviano `Mac.command`: il riavvio usa lo stesso Python già installato. Il blocco iniziale di Gatekeeper sul file `.command` non è quindi un passaggio del normale aggiornamento integrato. Il comportamento completo va verificato su macOS reale.

Se cambia il requisito Python o una dipendenza installata, viene richiesto
l’installer della nuova release: l’aggiornamento automatico non modifica un
ambiente Python incompatibile. Non sono necessari account o token GitHub.

### Sonno e proporzioni

Un episodio spontaneo non può iniziare nei primi 10 minuti; dopo il risveglio
c’è una pausa minima di 15 minuti. Il sonno dura 5-10 respiri, circa 30-55 secondi.
**Addormentata** mantiene il sonno finché si sceglie un altro carattere o
**Riprendi**. Un comando di movimento attende il risveglio.
I promemoria restano attivi; voce e metronomo possono risvegliarla per animarsi.

Le tre sequenze condividono scala uniforme e punto d’appoggio. Il risveglio
ripercorre le pose approvate della discesa, così testa, vestito e scarpe non
cambiano disegno al ritorno in piedi. Il ciclo di respiro usa quattro nuove pose
con gli stessi fotogrammi di raccordo. Nessuna deformazione orizzontale.
La correzione colore viene applicata dopo il controllo di anatomia e movimento;
parametri, misure e prompt sono in `docs/palette-calibration-sleep.json`,
`docs/sleep-animation-review.json` e `docs/sleep-animation-prompts.md`.

### Schermo intero su Mac (dalla 1.0.2)

**Mostra anche sopra le app a schermo intero** resta attiva di default.
L’icona nel Dock scompare in questa modalità: restano il personaggio e il menu
nella barra in alto. Puoi disattivarla in Impostazioni; la scelta viene salvata.
Menu, tendine, pannelli e dialoghi vengono disposti su livelli appropriati.

## Correzioni incluse dalla 1.0.1

- Su macOS l’app viene installata in `/Applications`. L’aggiornamento riconosce
  la precedente copia in `~/Applications`, aggiorna il collegamento sulla
  Scrivania e rimuove la vecchia copia solo dopo la verifica della nuova.
  macOS può richiedere l’autorizzazione di un amministratore per la copia.
- Aprire il pannello o un dialogo dal menu lascia riprendere le animazioni.
  La Pausa completa scelta dall’utente resta attiva finché non viene disattivata.
- Guida aggiornata, con una nuova copertina.

Per aggiornare dalla 1.0, chiudi Yun Jin e avvia `Mac.command` dal nuovo ZIP
(o l’avviatore del tuo sistema). Appunti, allegati e impostazioni sono conservati.
L’app in `/Applications` continua a usare l’ambiente Python e i dati del tuo
profilo; non è un’installazione condivisa fra utenti diversi del Mac.

La modalità overlay è basata sulle API pubbliche AppKit e richiede macOS 13 o successivo.
I test di logica possono essere eseguiti senza desktop; la presenza sopra app a schermo
intero e la gestione del focus vanno provate in una sessione macOS reale.

## Icona nella barra delle applicazioni Windows

L’installer assegna ai collegamenti Desktop e Start lo stesso AppUserModelID
usato dall’app e verifica che sia stato salvato. Il processo imposta e rilegge
l’identità prima di importare Qt; ogni finestra riceve anche le icone native
Windows piccola e grande, ricavate dal file ICO a più risoluzioni. Chiudi Yun Jin e avvia il nuovo
`Windows.cmd` per aggiornare anche i collegamenti. Se avevi fissato alla barra
il vecchio collegamento con l’icona Python, rimuovilo e fissa quello aggiornato
**Yun Jin Companion** dal menu Start.

## Menu compatto e icona macOS

Il clic destro e il menu dell’area di notifica condividono nove voci principali.
**Strumenti** raccoglie appunti, promemoria, focus, metronomo e cronometro;
**Voce** raccoglie lettura e silenzio; **Comportamento**, **Animazioni** e
**Aspetto** raccolgono i controlli del pet. Pannello, preferenze, guida e chiusura
restano direttamente accessibili.

Su macOS l’app imposta anche l’icona del processo tramite AppKit; nel Dock
è visibile quando la modalità sopra le app a schermo intero è disattivata.
Per aggiornare, chiudi Yun Jin, estrai il pacchetto aggiornato e avvia
`Mac.command` (oppure `Windows.cmd` su Windows). I dati personali sono conservati.

## Interfaccia

La barra laterale apre Appunti, Promemoria, Focus, Metronomo e Cronometro.
Voce e Impostazioni sono separate. Le opzioni secondarie sono nei menu `⋯`;
i controlli di lettura e riproduzione seguono lo stato dello strumento.
Le animazioni manuali sono nel menu del pet, sotto **Animazioni**.
Il tema usa viola, prugna e azzurro, con icone vettoriali e gradienti leggeri.

## Revisione delle animazioni

Le dieci sequenze aggiuntive della 1.0 contengono 16 fotogrammi ciascuna;
la 1.1.0 aggiunge le tre sequenze del sonno. Le tavole sono
state rigenerate usando un modello ricavato dallo sprite originale:
trecce sottili e separate, scarpe contenute, occhi bordeaux e palette più sobria.
L’estrazione usa regioni esplicite per ogni figura oppure celle già ripulite,
conserva l’antialiasing ed esclude frammenti vicini e residui quasi trasparenti.
Una sola scala uniforme per
sequenza mantiene le proporzioni durante il movimento: larghezza e altezza
usano lo stesso fattore, senza compressione orizzontale.

`tools/prepare_animation_manifest.py` ricostruisce i ritagli e verifica l’assenza
di pixel appartenenti alle figure vicine; nelle tavole già impaginate conserva
gli ancoraggi, il sollevamento del salto e le pause revisionate (Pillow, numpy e
scipy, solo sviluppo).
`tools/render_animation_review.py` produce anteprime usando il caricatore reale
Qt. I risultati tecnici sono in `docs/animation-qa.json`, i prompt in
`docs/animation-prompts.json`. La fedeltà artistica richiede anche confronto visivo.
`docs/animation-review.json` registra la revisione finale, le misure dei frame
effettivamente caricati e i controlli eseguiti. Danza ora combina passi incrociati,
spostamenti di peso, gesti delle braccia e un piccolo inchino. Il giro completo
precedente è conservato con il nome Piroetta, selezionabile separatamente.
Entrambe possono comparire spontaneamente nei caratteri Normale e Vivace; il
comando **Comportamento → Esibizione** le esegue dopo un saluto e prima del
saluto finale. L'opzione Animazioni aggiuntive disattiva questi inserimenti
automatici; l'esibizione torna alla sequenza originale.
Cronometro è stato rifatto partendo dalla sagoma originale: testa e abito più
stretti, orologio alzato accanto al viso. Le altre otto sequenze conservano
immagini e tempi della revisione precedente. Promemoria e Piroetta usano 16 intervalli di riproduzione
con 15 disegni distinti: una breve posa mantenuta sostituisce un gesto isolato
scartato durante la revisione.

Un filtro CIELAB continuo comune alle due nuove sequenze armonizza i colori con
lo sprite originale senza ridurre il numero di colori né cambiare la trasparenza.
La correzione cromatica viene applicata dopo la revisione di disegno e movimento.
L’altezza di riferimento usa la sagoma opaca originale, senza includere
le ombre quasi trasparenti. La tavola originale rimane invariata.
Parametri e criterio numerico sono in `docs/palette-calibration.json`; il filtro
delle revisioni precedenti è documentato nei file `palette-calibration-initial.json`
e `palette-calibration-dynamic.json` della stessa cartella.
`tools/color_match_animations.py --source-assets PERCORSO` riproduce il filtro
a partire dalle tavole non corrette; gli hash impediscono una doppia applicazione.
Per calibrare future tavole, `tools/calibrate_animation_palette.py --review
CARTELLA_ANTEPRIME --source-assets CARTELLA_TAVOLE --names dance16 stopwatch16` usa le anteprime non corrette
del caricatore Qt (numpy, Pillow, scipy e scikit-learn, solo sviluppo).

## Funzioni

- Sprite originale, dieci animazioni da 16 fotogrammi, tre fasi del sonno, sguardo, passeggiate e reazioni.
- Taccuino con ricerca, immagini incollate e riferimenti ai file; preparazione di richieste da incollare in ChatGPT.
- Promemoria persistenti, notifiche visive, suoni e lettura vocale.
- Edge TTS: Elsa, italiano, velocità +20%, intonazione +15 Hz, volume 70%. Alternativa gTTS con controlli dedicati.
- Focus da 1 a 180 minuti, cronometro con parziali ed esportazione CSV.
- Metronomo PCM 20–400 BPM, Tap tempo, accento opzionale ogni 1–32 battiti, scalata ascendente o discendente per battiti o secondi.
- Dati personali locali, backup ZIP e comandi Windows mostrati solo su Windows.

Il metronomo e il cronometro funzionano senza Internet. Edge/gTTS inviano il testo al servizio scelto e sono accessi non ufficiali: nessuna quota o disponibilità garantita. iOS e Android non sono inclusi. Su Wayland il posizionamento del pet dipende dal compositor; è consigliata una sessione X11.

## Sviluppo

Python 3.10–3.14 a 64 bit. Installa `installer/requirements.txt` in un ambiente virtuale, quindi esegui `python app/yun_jin_pet.py`.

`python tests/test_windows_identity.py` controlla ordine di avvio e identità,
e su Windows verifica le icone native di finestre e dialoghi.

`python tests/test_macos_overlay.py` verifica preferenze, ripristino e livelli delle finestre.
Su un Mac, `QT_QPA_PLATFORM=cocoa python tests/test_macos_overlay.py` esegue anche
il controllo nativo di creazione del pannello e attivazione/disattivazione.

`python tests/test_release.py` controlla pianificazione dei battiti, PCM, pause e parziali, comportamento del pannello, voce e animazioni. L'uscita audio fisica e i dialoghi nativi di installazione richiedono un dispositivo reale.

`python tests/test_behavior_updates.py` verifica Seguimi, sonno, proporzioni, suoni e interfaccia aggiornamenti.
`python tests/test_updater.py` verifica ZIP, hash, percorsi spostati, conservazione dati, rollback e riavvio in processi separati.

`python tools/render_guide_assets.py` rigenera le schermate con dati fittizi e gli estratti delle animazioni definitive.
`python docs/build_guide.py` rigenera il PDF su Linux con ReportLab, Pillow e i font DejaVu installati. Eseguilo solo quando cambiano i contenuti della guida; le release con sole correzioni riutilizzano lo stesso PDF. Aggiorna la data di revisione nei crediti quando modifichi il manuale.

`python tools/package_release.py` crea lo ZIP di distribuzione in `dist/`; aggiungi `--source` per produrre anche lo ZIP del repository. Sono escluse cache, revisioni precedenti, archivi e dati personali. `Mac.command` e `Linux.sh` mantengono il permesso eseguibile.

## Pubblicazione 1.1.1

1. Estrai **Yun-Jin-Companion-1.1.1-Sorgenti.zip**. Carica nella radice del repository
   il contenuto della cartella estratta, comprese `.github` e `.gitignore`.
   `README.md`, `Windows.cmd` e `app/` devono trovarsi direttamente nella radice.
2. Attendi i controlli nella scheda **Actions**. Verifica su Windows l’installazione,
   il collegamento aggiornato e l’icona nella barra; verifica anche l’uscita audio.
3. Crea la release con tag **v1.1.1** e titolo **Yun Jin Companion 1.1.1**.
   Allega **Yun-Jin-Companion-1.1.1.zip**, il pacchetto da scaricare e installare.
   GitHub fornisce automaticamente anche l’archivio dei sorgenti.
4. Pubblica una release stabile, non una prerelease, e contrassegnala come **Latest**.
   Scrivi le note nel corpo della release: sono quelle che l’app mostrerà.
   Mantieni il nome **Yun-Jin-Companion-X.Y.Z.zip** e il tag **vX.Y.Z**.
   Lo ZIP deve essere quello prodotto da `tools/package_release.py`: contiene
   `app/release-manifest.json`, indispensabile per la verifica automatica.
   Non usare lo ZIP Sorgenti come allegato di aggiornamento.

I dettagli per preparare le release future sono in [docs/UPDATES.md](docs/UPDATES.md).

Descrizione del repository: **Compagna desktop con appunti, promemoria vocali,
focus, cronometro e metronomo.**

Note per la release: vedi [docs/RELEASE-1.1.1.md](docs/RELEASE-1.1.1.md).

Gli ZIP contengono solo la versione definitiva 1.1.1. Il pacchetto di distribuzione
include app, risorse, avviatori e guida; i sorgenti aggiungono documentazione,
strumenti di sviluppo e test. Anteprime di controllo, revisioni precedenti,
ambienti Python e dati personali sono esclusi.

## Licenze e crediti

Codice: [GNU GPL v3 o successiva](app/licenses/GPL-3.0.txt). Le dipendenze mantengono le proprie licenze. Le illustrazioni del personaggio sono escluse dalla licenza del codice: non viene concesso alcun diritto ulteriore su personaggio o marchi.

Progetto fan non ufficiale. Yun Jin è un personaggio di Genshin Impact, dei rispettivi titolari. Lo sprite originale fornito dall'utente è conservato; le sequenze aggiuntive sono generate da riferimenti e integrate come animazioni. Nessuna affiliazione con HoYoverse, Microsoft, Google o OpenAI.
