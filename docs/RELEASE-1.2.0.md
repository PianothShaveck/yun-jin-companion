# Yun Jin Companion 1.2.0

Yun Jin diventa più attenta all’ora e al tempo fuori, con un’interfaccia più essenziale e un consumo di risorse ridotto.

- **Saluti in mandarino:** un saluto contestuale all’apertura, diverso fra mattina, pomeriggio, sera e notte. Non viene ripetuto aprendo il pannello.
- **Animazioni secondo l’ora:** una sola reazione al passaggio a una nuova fascia oraria, senza recuperi in sequenza dopo la sospensione del computer.
- **Meteo locale:** controllo ogni ora in background e reazioni a sole, pioggia, nuvole, neve, nebbia e temporali. Posizione approssimativa dall’IP; nessun GPS o account da configurare.
- **Reazioni discrete:** rispettano comandi manuali, pausa, sonno, focus, metronomo e promemoria. I commenti meteo non si ripetono a ogni controllo; almeno due ore separano due reazioni. In assenza di dati o connessione, nessun avviso di errore.
- **Interfaccia più pulita:** rimossi i testi superflui, semplificate le etichette e riordinata la pagina Voce. Saluto, animazioni orarie e meteo sono disattivabili separatamente.
- **Meno CPU e memoria:** caricamento delle animazioni su richiesta, cache limitata, ridisegni solo quando cambia il fotogramma e cronometro senza aggiornamenti grafici quando nascosto. Immagini, proporzioni e tempi delle animazioni restano invariati.
- **Guida aggiornata**, sempre senza numero di versione in copertina.

## Aggiornamento

Chi usa la 1.1.x può aggiornare da **Impostazioni → Controlla ora** dopo la pubblicazione di questa release. In alternativa, scarica lo ZIP completo, estrailo e avvia `Windows.cmd`, `Mac.command` o `Linux.sh`. Appunti, allegati e preferenze vengono conservati.

Il meteo usa [Open-Meteo](https://open-meteo.com/) (dati CC BY 4.0) e la posizione approssimativa di [ipwho.is](https://ipwhois.io/). Una VPN può indicare un’altra zona. Le frasi spontanee usano il servizio vocale e il volume scelti in Voce, in mandarino, senza modificare la lingua delle letture manuali.
