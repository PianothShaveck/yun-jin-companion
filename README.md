# Yun Jin Companion

Una piccola compagna per il desktop: appunti, promemoria vocali, focus, cronometro e metronomo con scalata. Versione **1.0.1**.

## Avvio

Scarica ed estrai il pacchetto completo. Chiudi eventuali versioni precedenti.

| Sistema | Primo avvio | Avvii successivi |
| --- | --- | --- |
| Windows 10/11 x64 | Doppio clic su `Windows.cmd` | Collegamento **Yun Jin Companion** sul desktop |
| macOS 13+, Intel / Apple Silicon | Doppio clic su `Mac.command` | **Yun Jin Companion.app** in Scrivania o `/Applications` |
| Linux desktop x64 | `bash Linux.sh` con Python e venv installati | Menu applicazioni |

Gli avviatori Windows e macOS cercano Python; se manca, scaricano l'installer ufficiale e ne verificano SHA-256. Le dipendenze sono installate in un ambiente privato. Sul Mac completa l'installer di Python quando richiesto. Serve Internet per la prima installazione e per la sintesi vocale.

La guida unica e completa è [Guida.pdf](Guida.pdf), disponibile anche dal pulsante **Guida** nell'app. Include installazione, funzioni, comandi per ogni sistema, backup e aiuto.

## Novità della 1.0.1

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

Su macOS la presenza sopra le app a schermo intero resta limitata: questa
versione conserva l’icona nel Dock e non introduce una modalità overlay dedicata.

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

Su macOS l’app imposta anche l’icona del processo nel Dock tramite AppKit.
Per aggiornare, chiudi Yun Jin, estrai il pacchetto aggiornato e avvia
`Mac.command` (oppure `Windows.cmd` su Windows). I dati personali sono conservati.

## Interfaccia

La barra laterale apre Appunti, Promemoria, Focus, Metronomo e Cronometro.
Voce e Impostazioni sono separate. Le opzioni secondarie sono nei menu `⋯`;
i controlli di lettura e riproduzione seguono lo stato dello strumento.
Le animazioni manuali sono nel menu del pet, sotto **Animazioni**.
Il tema usa viola, prugna e azzurro, con icone vettoriali e gradienti leggeri.

## Revisione delle animazioni

Le dieci sequenze aggiuntive contengono 16 fotogrammi ciascuna. Le tavole sono
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

- Sprite originale, dieci animazioni aggiuntive da 16 fotogrammi, sguardo, passeggiate e reazioni.
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

`python tests/test_release.py` controlla pianificazione dei battiti, PCM, pause e parziali, comportamento del pannello, voce e animazioni. L'uscita audio fisica e i dialoghi nativi di installazione richiedono un dispositivo reale.

`python tools/render_guide_assets.py` rigenera le schermate con dati fittizi e gli estratti delle animazioni definitive.
`python docs/build_guide.py` rigenera il PDF su Linux con ReportLab, Pillow e i font DejaVu installati.

`python tools/package_release.py` crea lo ZIP di distribuzione in `dist/`; aggiungi `--source` per produrre anche lo ZIP del repository. Sono escluse cache, revisioni precedenti, archivi e dati personali. `Mac.command` e `Linux.sh` mantengono il permesso eseguibile.

## Pubblicazione 1.0.1

1. Estrai **Yun-Jin-Companion-1.0.1-Sorgenti.zip**. Carica nella radice del repository
   il contenuto della cartella estratta, comprese `.github` e `.gitignore`.
   `README.md`, `Windows.cmd` e `app/` devono trovarsi direttamente nella radice.
2. Attendi i controlli nella scheda **Actions**. Verifica su Windows l’installazione,
   il collegamento aggiornato e l’icona nella barra; verifica anche l’uscita audio.
3. Crea la release con tag **v1.0.1** e titolo **Yun Jin Companion 1.0.1**.
   Allega **Yun-Jin-Companion-1.0.1.zip**, il pacchetto da scaricare e installare.
   GitHub fornisce automaticamente anche l’archivio dei sorgenti.

Descrizione del repository: **Compagna desktop con appunti, promemoria vocali,
focus, cronometro e metronomo.**

Note per la release: vedi [docs/RELEASE-1.0.1.md](docs/RELEASE-1.0.1.md).

Gli ZIP contengono solo la versione definitiva 1.0.1. Il pacchetto di distribuzione
include app, risorse, avviatori e guida; i sorgenti aggiungono documentazione,
strumenti di sviluppo e test. Anteprime di controllo, revisioni precedenti,
ambienti Python e dati personali sono esclusi.

## Licenze e crediti

Codice: [GNU GPL v3 o successiva](app/licenses/GPL-3.0.txt). Le dipendenze mantengono le proprie licenze. Le illustrazioni del personaggio sono escluse dalla licenza del codice: non viene concesso alcun diritto ulteriore su personaggio o marchi.

Progetto fan non ufficiale. Yun Jin è un personaggio di Genshin Impact, dei rispettivi titolari. Lo sprite originale fornito dall'utente è conservato; le sequenze aggiuntive sono generate da riferimenti e integrate come animazioni. Nessuna affiliazione con HoYoverse, Microsoft, Google o OpenAI.
