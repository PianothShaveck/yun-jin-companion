# Pubblicare Yun Jin Companion 1.1.1 dal Mac

Salva in Download `Yun-Jin-Companion-1.1.1-Patch.zip` e `Yun-Jin-Companion-1.1.1.zip`, conservando i nomi originali. La patch serve alla copia locale della repository; lo ZIP completo serve agli utenti e agli aggiornamenti integrati.

## Aggiornare la repository

Con Git e GitHub CLI già configurati:

```bash
cd "$HOME/Documents/yun-jin-companion"
git pull --ff-only
unzip -o "$HOME/Downloads/Yun-Jin-Companion-1.1.1-Patch.zip" -d .
git add -A
git diff --cached --stat
```

La patch comprende anche le due correzioni precedenti ai controlli Windows. Verifica l’elenco, poi:

```bash
git commit -m "Release 1.1.1: avvisi macOS e guida senza versione"
git push
```

Attendi i controlli di Windows, macOS e Ubuntu nella scheda Actions:
https://github.com/PianothShaveck/yun-jin-companion/actions

## Pubblicare la release

Quando i controlli sono passati, dalla stessa cartella:

```bash
gh release create v1.1.1 \
  "$HOME/Downloads/Yun-Jin-Companion-1.1.1.zip" \
  --target "$(git rev-parse HEAD)" \
  --title "Yun Jin Companion 1.1.1" \
  --notes-file docs/RELEASE-1.1.1.md \
  --latest
```

Il comando pubblica la release, allega il pacchetto completo e inserisce le note. Mantieni il nome dello ZIP: l’app lo cerca esattamente così. Il tag v1.1.1 deve essere nuovo; non sostituire la release 1.1.0 già pubblicata.

## Verificare sul Mac

Dalla 1.1.0 puoi ricevere la release con Controlla ora. Dopo l’aggiornamento alla 1.1.1, ripeti il controllo con il pannello Impostazioni aperto: l’avviso deve essere davanti, e OK deve restituire il controllo al pannello. Prova con Mostra anche sopra le app a schermo intero attiva e disattiva.

## Guida nelle prossime release

Riutilizza `Guida.pdf` quando cambiano soltanto correzioni interne. Ricostruiscila con `python docs/build_guide.py` solo quando aggiorni funzioni, procedure o contenuti e modifica la data di revisione nei crediti. Le note di rilascio descrivono ogni singolo aggiornamento dell’app.
