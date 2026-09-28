Le tavole Danza e Cronometro sono gli input non corretti della calibrazione corrente. Le altre immagini conservano gli input della revisione precedente.

Dal progetto, `python tools/color_match_animations.py --source-assets docs/source-art` riproduce solamente Danza e Cronometro in `app/assets`. Gli hash in `docs/palette-calibration.json` impediscono la doppia applicazione del filtro. Le otto altre sequenze non vengono elaborate. I file di calibrazione precedenti documentano la storia delle revisioni.
