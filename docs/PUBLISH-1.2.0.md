# Pubblicare Yun Jin Companion 1.2.0

Dopo la prova locale, scarica `Yun-Jin-Companion-1.2.0-Patch.zip` e
`Yun-Jin-Companion-1.2.0.zip` in Download. La patch aggiorna il repository
1.1.2 che ha appena superato tutti i check; lo ZIP completo è l’allegato
installabile della release. Guida e note sono già incluse nei file corretti.

## Aggiornare il repository dal Mac

```bash
cd "$HOME/Documents/yun-jin-companion"
git pull --ff-only
unzip -o "$HOME/Downloads/Yun-Jin-Companion-1.2.0-Patch.zip" -d .
git add -A
git diff --cached --stat
git commit -m "Release 1.2.0: orario, meteo e prestazioni"
git push
```

Se il repository è in un’altra cartella, cambia soltanto il primo percorso.
`git add -A` include tutti i file cambiati, anche il workflow aggiornato.
Prima del commit controlla l’elenco e verifica di non avere modifiche personali
non pertinenti da aggiungere.

Attendi i check di Windows, macOS e Ubuntu nella scheda Actions. Sono inclusi
anche i nuovi test di orario, meteo e limiti delle risorse. Non serve creare
nuovamente gli ZIP: quelli forniti sono già definitivi e contengono il manifest.

## Creare la release dopo i check verdi

Se GitHub CLI è già configurato:

```bash
cd "$HOME/Documents/yun-jin-companion"
gh release create v1.2.0 \
  "$HOME/Downloads/Yun-Jin-Companion-1.2.0.zip" \
  --target "$(git rev-parse HEAD)" \
  --title "Yun Jin Companion 1.2.0" \
  --notes-file docs/RELEASE-1.2.0.md \
  --latest
```

In alternativa, dal sito crea una release con tag `v1.2.0`, titolo
**Yun Jin Companion 1.2.0**, incolla `docs/RELEASE-1.2.0.md` e allega soltanto
lo ZIP completo, senza rinominarlo. Pubblicala come stabile e Latest.
La patch non va allegata come pacchetto di aggiornamento automatico.

Per provare la versione prima della pubblicazione, estrai lo ZIP completo e
usa l’avviatore del tuo sistema. Gli aggiornamenti integrati della 1.1.x
potranno trovarla dopo che la release sarà pubblicata.
