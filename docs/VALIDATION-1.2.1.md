# Verifica della revisione 1.2.1

Inchino è stato ridisegnato; Buon pomeriggio e Buona sera hanno sequenze proprie.
Al sole, Nuvoloso e Pioggia conservano disegni, alpha e tempi, con una correzione
mirata dei colori. Le altre 17 sequenze aggiuntive e lo spritesheet originale
restano identici nei byte rispetto alla revisione precedente.

## Animazioni

- 160 frame delle dieci nuove animazioni verificati alla risoluzione del runtime.
- Confronto alla stessa scala con l'originale: altezza, testa, gonna e scarpe.
  Le misure per fasce sono indicatori geometrici, non una segmentazione anatomica
  né una garanzia di identità stilistica. Dati: `docs/proportions-1.2.1.json`.
- Nessun frame tocca i bordi della cella. Primo e ultimo frame coincidono.
  Scarpe controllate in ogni posa; scostamento della superficie delle punte entro
  il 10% dall'originale. Nessun ridimensionamento separato di larghezza e altezza.
- Inchino usa una posa di tenuta, escludendo due disegni con scarpe ingrandite.
  Pomeriggio saluta con la mano; sera porta la mano al cuore e accenna il capo.
- Ogni clip usa una scala isotropa costante. Correzioni uniformi della camera:
  Pioggia -4%, Inchino -2,5%, Buona sera -1%.

## Colori e riproducibilità

Generazione tramite `image_gen` integrato. Sorgenti e prompt selezionati sono in
`docs/context-art/selected-sources.json`, `time-revision-prompts.json` e
`time-refinement-prompts.json`. I disegni scartati non vengono distribuiti.

`tools/prepare_context_animations.py` separa i personaggi completi e li impacchetta
con margini trasparenti. `tools/match_context_materials.py` applica un solo
trasferimento CIELAB continuo per clip, senza quantizzazione o modifiche all'alpha.
La calibrazione parte direttamente dall'atlante non corretto, renderizzato con
il caricatore del runtime e senza cache.

Configurazioni attive:

- `palette-calibration-materials.json`: Inchino, Buon pomeriggio e Buona sera.
- `palette-calibration-weather.json`: rifinitura della luminosità per colore su
  Al sole, Nuvoloso e Pioggia, conservando tonalità e saturazione della correzione
  precedente. Include i parametri di base, applicati una sola volta.
- `palette-calibration-proportions.json`: precedente correzione, ancora usata
  senza modifiche da Buongiorno, Sbadiglio, Neve e Applauso.

Le distanze di palette descrivono differenze numeriche; il giudizio sul disegno
richiede anche il confronto visivo. L'anteprima contiene i frame effettivi dell'app.
`tools/build_sprite_cache.py` verifica l'identità dei pixel degli atlanti ottimizzati.
`tools/prune_sprite_cache.py` elimina solo cache generate obsolete dopo una patch.

## Regressioni

Suite `test_animation_menu`, `test_context`, `test_release`, `test_resource_usage`:
55 test, 53 superati e 2 esclusi perché richiedono macOS o Windows nativi.
Verificati saluti distinti all'avvio, lingua della voce, un solo evento per cambio
fascia, accesso dai menu, integrità dei frame e limite di memoria della cache.
Esecuzione locale Linux, Qt offscreen. Nessuna nuova dipendenza del runtime.

Guida di 13 pagine: aggiornata e controllata visivamente la tabella delle fasce
orarie. ZIP verificati tramite CRC, manifest e installazione della patch su una
copia della 1.1.2.
