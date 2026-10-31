# Catalogo ottimizzato — preparazione 1.6

Convertito e verificato l'intero catalogo attuale: 635 originali e 635 anteprime.
Nessun asset di produzione sostituito, nessuna release pubblicata.

| File | Prima | Selezione ottimizzata | Risparmio |
| --- | ---: | ---: | ---: |
| Originali | 957.213.682 B | 851.075.712 B | 106.137.970 B (11,088%) |
| Anteprime | 389.517.758 B | 270.250.452 B | 119.267.306 B (30,619%) |
| Totale | 1.346.731.440 B | 1.121.326.164 B | 225.405.276 B |

MB decimali: circa 106,1 MB risparmiati negli originali e 119,3 MB nelle anteprime.
Non è una misura della riduzione dell'intero installer: gli originali sono esterni
al runtime e gli altri asset dell'app non sono stati convertiti.

## Selezione eseguita

- Originali: 551 JXL lossless (effort 7, decoding speed 0) e 84 WebP esistenti.
  Ogni candidato JXL è stato decodificato e confrontato in RGBA con il WebP
  sorgente. Selezionato solo se più piccolo. Nessuna ulteriore perdita sui file
  storici già lossy; naturalmente non vengono ricostruiti dettagli già persi.
- Anteprime: 551 WebP near-lossless 60 con `cwebp -z 9`; 84 WebP lossy conservati
  byte per byte. Dimensioni e alpha invariati; errore massimo osservato e accettato
  2/255 per canale RGB. PSNR minimo 46,587 dB. Non usato `-exact` nel near-lossless.
- Il tipo di codifica è ora verificato su tutti i 635 sorgenti: 551 VP8L, 84 VP8.
  Nessun input contiene chunk ICC/EXIF/XMP o altri metadati da migrare.
- Hash dei 1.270 input confrontati con l'indice e ricontrollati; selezione e hash
  di ogni output registrati in `catalog-selection.json`. Zero errori.
- Eseguita anche la ripresa dell'intero comando: riusa solo risultati con input,
  configurazione e hash degli output corrispondenti. Un risultato mancante viene
  ricostruito. I valori aggregati sono rimasti identici.

Confronto visivo affiancato a 450×300 di YJ-586, YJ-087, YJ-590 e YJ-444;
le prime tre erano le anteprime con PSNR più basso fra quelle già elaborate.
YJ-586 è risultato il minimo anche sull'intero catalogo: controllati volto,
capelli, occhi, abiti e dettagli circostanti al 200%. Nessun deterioramento
visibile nei confronti eseguiti; non è una verifica visiva individuale di 635 file.

## Comando ripetibile

Dall'ambiente di sviluppo con PyQt6, numpy, imagecodecs e Pillow:

```sh
python tools/optimize_calendar_catalog.py --output /percorso/separato/catalogo-ottimizzato --cwebp /percorso/cwebp --workers 8 --threads 2
```

Il comando converte, verifica e sceglie il file più piccolo in una sola esecuzione.
I file sono scritti in una cartella separata, con checkpoint per immagine. Non
modifica il progetto e non installa dipendenze nell'app. Per gli originali il
confronto è fra il WebP esistente e JXL; la ricompressione massima WebP, già provata
nel benchmark precedente, non è ripetuta in questa passata.

Versioni: cwebp 1.6.0, libjxl 0.12.0, Qt 6.11.2. Parallelismo limitato a 8 processi
con 2 thread JXL ciascuno; le anteprime usano il normale cwebp. Non sono misure di
consumi o di velocità del runtime. Il costo di conversione è offline.

## Verifiche e prossimi passi

Sei controlli sintetici superati: identità RGBA degli originali, selezione più
piccola/limite d'errore delle anteprime, byte storici invariati, conservazione
metadati, conservazione alpha nelle anteprime e RGB/alpha negli originali.
Passato anche il test UI sulle illustrazioni giornaliere di tutte le date campione,
prima escluso per checkout parziale. Le 41 verifiche precedenti restano valide;
questo incremento non modifica il runtime.

Resta da integrare la generazione delle anteprime nella pipeline di produzione e
aggiornare i relativi test. Per usare gli originali JXL nell'app servono decoder
Windows/macOS/Linux, indice/download con formati misti e verifica nativa. La
conversione numericamente lossless è completata; il supporto runtime JXL resta
separato. Meteo, sprite e animazioni invariati. Agosto e settembre da generare.
