# Yun Jin Companion

Una piccola Yun Jin sul desktop, con flashcard, appunti, promemoria e strumenti musicali. **Versione 1.4.0** per Windows, macOS e Linux.

[Scarica l'app](https://github.com/PianothShaveck/yun-jin-companion/releases/latest) · [Guida illustrata](Guida.pdf)

## Funzioni

- Studio con mazzi, carte fronte/retro e cloze, immagini e audio.
- FSRS 6 locale con ritenzione personalizzabile.
- Richiami sulle carte difficili, sospesi durante il focus; Anki locale collegabile in sola lettura.
- Scorciatoie personalizzabili, globali su Windows e macOS.
- Appunti con ricerca, immagini e allegati.
- Promemoria con notifiche, suoni e lettura vocale.
- Metronomo con accenti e scalata personalizzabile, cronometro con parziali e timer focus.
- Voce tramite Edge TTS o Google Translate, con fumetti durante il parlato.
- Animazioni, passeggiate, inseguimento del cursore e sonnellini.
- Saluti nella lingua scelta e reazioni all'ora del giorno e al meteo.
- Previsioni orarie e a sette giorni, con illustrazioni di Yun Jin.
- Backup dei dati e aggiornamenti con note di rilascio, rinvio o salto della versione.

## Installazione

Scarica **Yun-Jin-Companion-1.4.0.zip** dalla release ed estrai tutta la cartella.

| Sistema | Avvio dell'installazione |
| --- | --- |
| Windows 10/11, 64 bit | Apri `Windows.cmd`. |
| macOS 13+, Intel o Apple Silicon | Esegui `bash Mac.command` dal Terminale nella cartella estratta. |
| Linux desktop | Esegui `bash Linux.sh`; servono Python e venv. |

L’installer prepara i componenti necessari e conserva i dati. Poi usa il collegamento creato. Puoi aggiornare anche dall’app; se servono nuove dipendenze, verrà richiesto l’installer. Su macOS, se l'apertura viene bloccata, autorizza il pacchetto in **Impostazioni di Sistema → Privacy e Sicurezza → Apri comunque**.

Fai doppio clic su Yun Jin per aprire il pannello; il clic destro apre il menu. La [guida PDF](Guida.pdf) è disponibile anche nell'app.

Puoi nascondere il personaggio dal menu, dalle impostazioni o con una scorciatoia personalizzata: strumenti e richiami di studio restano attivi. Su Windows e macOS puoi scegliere se mostrarlo anche sopra le app a schermo intero.

## Dati e connessione

Mazzi, ripassi, allegati e impostazioni sono conservati localmente in SQLite. Lo studio funziona offline. Il collegamento opzionale propone carte Anki difficili dei mazzi studiati oggi, senza modificarne la collezione. I richiami variano tra le carte selezionate ed evitano quelle già proposte oggi o ieri. La sintesi vocale invia il testo al servizio selezionato. Il meteo usa [Open-Meteo](https://open-meteo.com/): scegli la città nelle impostazioni per attivarlo. La ricerca delle città usa dati [GeoNames](https://www.geonames.org/). Saluti, reazioni meteo e ricerca automatica degli aggiornamenti sono disattivabili nelle impostazioni.

## Crediti e licenza

Progetto fan indipendente, non affiliato a HoYoverse. Yun Jin e Genshin Impact appartengono ai rispettivi titolari.

Codice sotto [GNU GPL v3 o successiva](app/licenses/GPL-3.0.txt); illustrazioni, personaggio e marchi sono esclusi dalla licenza del codice. FSRS: [Open Spaced Repetition](https://github.com/open-spaced-repetition), licenze in `app/licenses`. Dati meteo Open-Meteo sotto [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
