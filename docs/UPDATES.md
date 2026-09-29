# Preparare le release per gli aggiornamenti integrati

Repository pubblico: https://github.com/PianothShaveck/yun-jin-companion

## Pubblicazione manuale su GitHub

1. Aggiorna i sorgenti del repository con il contenuto dello ZIP Sorgenti. I file `README.md`, `app/`, `installer/`, `tests/`, `tools/`, `docs/`, la guida e gli avviatori devono stare nella radice. Aggiorna anche `.github/workflows/check.yml`; dal Mac puoi aprire il file già presente nell’editor web di GitHub e sostituirne il contenuto, evitando il selettore che rifiuta cartelle nascoste.
2. Attendi i check di Windows, macOS e Ubuntu. Prova anche le tendine macOS con overlay attivo/disattivo, Seguimi durante un’animazione e un promemoria mentre suona il metronomo.
3. Crea una release stabile con tag `v1.1.0`, titolo `Yun Jin Companion 1.1.0`, e impostala come Latest.
4. Incolla il contenuto di `docs/RELEASE-1.1.0.md` nelle note. L’app legge proprio il corpo della release: puoi usare Markdown, elenchi e link HTTPS. Le immagini remote non vengono caricate nell’app.
5. Allega `Yun-Jin-Companion-1.1.0.zip`, senza rinominarlo. Lo ZIP Sorgenti serve a caricare il repository, non come pacchetto di aggiornamento. GitHub calcola il digest SHA-256 dell’allegato; se ancora assente, l’app attende e non installa uno ZIP non verificabile.

Le versioni 1.0.x non possono cercare aggiornamenti: gli utenti devono installare la 1.1.0 manualmente una volta. Poi ricevono le release successive.

## macOS: approvazione dell’installer e aggiornamenti

Il doppio clic su `Mac.command` può essere bloccato da Gatekeeper. Per il pacchetto scaricato dalla release ufficiale, dopo il tentativo di apertura usa **Impostazioni di Sistema → Privacy e Sicurezza → Apri comunque**, poi **Apri**. Una nuova copia scaricata può richiedere una nuova approvazione. Non è lo stesso permesso eventualmente richiesto per copiare l’app in `/Applications`.

L’aggiornamento integrato non usa Finder, `open Mac.command` o il nuovo installer: il processo di aggiornamento e il riavvio impiegano lo stesso Python già in uso. Il normale flusso non richiede quindi di approvare nuovamente `Mac.command`. Se cambiano Python o dipendenze, il passaggio all’installer manuale può comportare nuovamente l’approvazione.

La distribuzione futura con un’app o installer firmato Developer ID e autenticato (notarizzato) da Apple permette il normale percorso di apertura delle app riconosciute. Richiede la preparazione e firma del pacchetto macOS; lo script bloccato non può autorizzare la propria esecuzione prima di partire. Riferimenti Apple: https://support.apple.com/it-it/102445 e https://developer.apple.com/developer-id/

## Per la prossima versione X.Y.Z

- Aggiorna la versione in `app/yun_jin_platform.py`, `app/yun_jin_app.py`, `installer/install.py`, `tools/package_release.py`, README e guida.
- Aggiorna note e test. Ricostruisci la guida prima del pacchetto.
- Esegui `python tools/package_release.py --source`. Il comando genera `app/release-manifest.json` con versione, requisiti e hash, poi crea gli archivi. Non modificare app o guida dopo il packaging senza rigenerare gli ZIP.
- Pubblica tag `vX.Y.Z` e allegato esatto `Yun-Jin-Companion-X.Y.Z.zip`, marcando la release come stabile e Latest. Bozze, prerelease, sorgenti automatici GitHub e ZIP Sorgenti non vengono installati.
- Conserva il protocollo 1 compatibile. Il primo aggiornamento è gestito dal codice della versione già installata: cambi incompatibili al protocollo richiedono una release intermedia compatibile.

## Ambito e recupero

La destinazione è la cartella risolta dei moduli in esecuzione. Non usa un percorso predefinito per cercare altre installazioni. Aggiorna moduli, risorse e guida; se è una cartella completa estratta dallo ZIP, aggiorna anche installer e avviatori. Rimuove soltanto file precedentemente elencati nel manifest del programma, mantenendo i file aggiunti dall’utente. Non sposta cartelle dati, allegati, Python o collegamenti del sistema.

La verifica delle dipendenze confronta quelle richieste con quelle installate. Un cambiamento di Python o delle versioni delle librerie richiede l’installer completo; l’app lo spiega senza modificare il programma. Non installa pacchetti dentro un ambiente incompatibile.

Il processo di aggiornamento conserva un backup e un diario in `updates/` nella cartella dati. Aspetta il rilascio del lock dell’app prima di sostituire i file. Verifica il nuovo avvio attraverso un segnale emesso dal ciclo eventi Qt; in caso di errore ripristina i file e riapre la versione precedente. Un’interruzione durante la copia viene recuperata all’avvio successivo, prima di caricare l’interfaccia. Le copie di recupero rimangono disponibili nella cartella dati; dopo un aggiornamento riuscito si possono eliminare le vecchie cartelle `updates/update-*` ad app chiusa.

## API di riferimento

- https://docs.github.com/en/rest/releases/releases#get-the-latest-release
- https://docs.github.com/en/rest/releases/assets

I controlli usano richieste HTTPS pubbliche in sola lettura e non richiedono token. Nessuna funzione dell’app pubblica release o modifica il repository.
