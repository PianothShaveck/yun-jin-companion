# Yun Jin Companion

Una piccola Yun Jin sul desktop, con appunti, promemoria vocali e strumenti per lo studio musicale. **Versione 1.2.1** per Windows, macOS e Linux.

[Scarica l'app](https://github.com/PianothShaveck/yun-jin-companion/releases/latest) · [Guida illustrata](Guida.pdf)

## Funzioni

- Appunti con ricerca, immagini e allegati.
- Promemoria con notifiche, suoni e lettura vocale.
- Metronomo con accenti e scalata personalizzabile, cronometro con parziali e timer focus.
- Voce tramite Edge TTS o Google Translate, con fumetti durante il parlato.
- Animazioni, passeggiate, inseguimento del cursore e sonnellini.
- Saluti nella lingua scelta e reazioni all'ora del giorno e al meteo.
- Backup dei dati e aggiornamenti con note di rilascio, rinvio o salto della versione.

## Installazione

Scarica **Yun-Jin-Companion-1.2.1.zip** dalla release ed estrai tutta la cartella.

| Sistema | Avvio dell'installazione |
| --- | --- |
| Windows 10/11, 64 bit | Apri `Windows.cmd`. |
| macOS 13+, Intel o Apple Silicon | Apri `Mac.command`. |
| Linux desktop | Esegui `bash Linux.sh`; servono Python e venv. |

Segui le istruzioni dell'installer, poi usa il collegamento creato. Su macOS, se l'apertura viene bloccata, autorizza il pacchetto in **Impostazioni di Sistema → Privacy e Sicurezza → Apri comunque**.

Fai doppio clic su Yun Jin per aprire il pannello; il clic destro apre il menu. La [guida PDF](Guida.pdf) è disponibile anche nell'app.

## Dati e connessione

Appunti, allegati e impostazioni sono conservati localmente. La sintesi vocale invia il testo al servizio selezionato. Il meteo usa [Open-Meteo](https://open-meteo.com/) e una posizione approssimativa ricavata dall'IP tramite [ipwho.is](https://ipwhois.io/). Saluti, reazioni meteo e ricerca automatica degli aggiornamenti sono disattivabili nelle impostazioni.

## Crediti e licenza

Progetto fan indipendente, non affiliato a HoYoverse. Yun Jin e Genshin Impact appartengono ai rispettivi titolari.

Codice sotto [GNU GPL v3 o successiva](app/licenses/GPL-3.0.txt); illustrazioni, personaggio e marchi sono esclusi dalla licenza del codice. Dati meteo Open-Meteo sotto [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
