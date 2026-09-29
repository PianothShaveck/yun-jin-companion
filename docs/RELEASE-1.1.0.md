# Yun Jin Companion 1.1.0

Aggiornamenti integrati, un nuovo stato di sonno e correzioni per macOS, inseguimento del cursore e promemoria.

## Novità

- **Aggiornamenti dall’app:** controllo automatico ogni due ore, disattivabile nelle impostazioni, e pulsante **Controlla ora**.
- **Note di rilascio leggibili prima di aggiornare**, con le scelte **Aggiorna e riavvia**, **Più tardi** e **Salta questa versione**. Saltare una release non esclude quelle successive.
- Download verificato e aggiornamento nella cartella effettivamente in uso, anche se spostata. Appunti e dati personali vengono conservati; in caso di errore durante l’installazione o il nuovo avvio viene ripristinata la versione precedente.
- **Yun Jin dorme:** addormentamento, respiro lento e risveglio. Il carattere **Addormentata** è sopra **Tranquilla**; **Animazioni → Esegui → Sonnellino** propone un episodio breve. Il sonno può comparire anche occasionalmente come comportamento spontaneo.
- Guida illustrata aggiornata, con istruzioni per aggiornamenti e sonno.

## Correzioni

- Su **macOS** le tendine dei pannelli, comprese quelle per servizio, lingua e voce, vengono mantenute sopra le finestre anche con l’overlay a schermo intero.
- **Seguimi** non viene più cancellato dalle animazioni spontanee durante i due secondi di attesa. Il comando riprende anche dalla pausa.
- Il **campanello dei promemoria suona durante il metronomo**, senza interrompere il ritmo. La lettura vocale automatica resta sospesa durante il metronomo; volume e silenzio temporaneo restano rispettati.

## Come aggiornare

Dalla **1.0.x**, chiudi Yun Jin, estrai **Yun-Jin-Companion-1.1.0.zip** e avvia **Windows.cmd**, **Mac.command** o **Linux.sh**, secondo il sistema. I dati personali vengono conservati.

**Su macOS**, se Mac.command viene bloccato perché lo sviluppatore non è verificato, dopo il tentativo di apertura autorizza il pacchetto ufficiale in **Impostazioni di Sistema → Privacy e Sicurezza → Apri comunque**, poi **Apri**.

La 1.1.0 introduce il controllo per le release successive. Il riavvio avviene soltanto dopo aver scelto **Aggiorna e riavvia**. Se una release richiede una versione diversa di Python o nuove dipendenze, l’app rimanda all’installer della release.
