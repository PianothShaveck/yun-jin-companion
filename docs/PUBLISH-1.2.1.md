# Pubblica la 1.2.1

Chiudi Yun Jin e scarica Patch.zip e lo ZIP di distribuzione in Downloads.
La patch cumulativa si applica alla 1.1.2, alla 1.2.0 o alle anteprime della 1.2.1.

```bash
cd "$HOME/Documents/yun-jin-companion"
git pull --ff-only
unzip -o "$HOME/Downloads/Yun-Jin-Companion-1.2.1-Patch.zip" -d .
python3 tools/prune_sprite_cache.py
git add -A
git diff --cached --stat
git commit -m "Release 1.2.1: animazioni e fumetti"
git push
```

Dopo i controlli verdi in Actions, con GitHub CLI già configurata:

```bash
gh release create v1.2.1 \
  "$HOME/Downloads/Yun-Jin-Companion-1.2.1.zip" \
  --target "$(git rev-parse HEAD)" \
  --title "Yun Jin Companion 1.2.1" \
  --notes-file docs/RELEASE-1.2.1.md \
  --latest
```

Oppure crea la release dal sito con tag v1.2.1, incolla le note e allega
Yun-Jin-Companion-1.2.1.zip. È questo lo ZIP usato dagli aggiornamenti automatici.
