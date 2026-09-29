# Pubblicare Yun Jin Companion 1.1.2

Scarica `Yun-Jin-Companion-1.1.2-Patch.zip` e `Yun-Jin-Companion-1.1.2.zip` in Download. La patch aggiorna la repository locale dalla 1.1.1; il pacchetto completo serve per l’installazione e come allegato della release.

## Aggiornare la repository

Dopo la prova dell’app, adatta il percorso della prima riga se necessario:

```bash
cd "$HOME/Documents/yun-jin-companion"
git pull --ff-only
unzip -o "$HOME/Downloads/Yun-Jin-Companion-1.1.2-Patch.zip" -d .
git add -A
git diff --cached --stat
git commit -m "Release 1.1.2: finestre e impostazioni più chiare"
git push
```

Attendi che i controlli Windows, macOS e Ubuntu siano verdi. Il nuovo test delle finestre e delle impostazioni è incluso nel workflow.

## Pubblicare la release

Dalla stessa cartella, con GitHub CLI configurata:

```bash
gh release create v1.1.2 \
  "$HOME/Downloads/Yun-Jin-Companion-1.1.2.zip" \
  --target "$(git rev-parse HEAD)" \
  --title "Yun Jin Companion 1.1.2" \
  --notes-file docs/RELEASE-1.1.2.md \
  --latest
```

Mantieni il nome del pacchetto completo: è quello riconosciuto dagli aggiornamenti automatici. Le note vengono inserite dal comando; la patch non va allegata alla release.

## Prova rapida sul Mac

- Apri Scorciatoie dalle Impostazioni: deve comparire davanti; dopo OK il pannello deve rispondere.
- Crea un promemoria con data passata: l’avviso deve essere davanti anche all’editor. Prova inoltre Importa file, Backup e l’esportazione CSV del cronometro.
- Ripeti un avviso con “Mostra anche sopra le app a schermo intero” disattivata.
- In Voce disattiva la lettura automatica e prova “Ascolta” o “Leggi testo copiato”: la lettura manuale resta disponibile.
- Disattiva gli effetti sonori: volume e suoni di saluto/conferma diventano inattivi; riattivandoli ritrovi le tue scelte.

La guida è già compresa nella patch e nello ZIP completo. Per le future correzioni che non cambiano funzioni o istruzioni puoi riutilizzare lo stesso PDF.
