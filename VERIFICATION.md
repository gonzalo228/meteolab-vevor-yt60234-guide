# Provenienza e verifiche

La documentazione è ricostruita dalla conversazione tecnica originale del laboratorio MeteoLab, riletta senza accedere ai sistemi di produzione. Non viene pubblicata la conversazione: contiene dati di rete e riferimenti di autenticazione.

## Verifiche storiche sul Raspberry

- Console VEVOR YT60234, firmware 1.0.1.
- NetworkManager 1.52.1; Wi-Fi AP con Ethernet per SSH e Internet.
- Firewall dedicato: servizi del Pi limitati dal Wi-Fi e accesso diretto alla LAN bloccato.
- PCAPNG acquisiti con dumpcap e permessi privati.
- 44 richieste HTTP WeatherCloud decodificate, nove misure per richiesta.
- Mediana degli intervalli circa 786,5 s; richieste ravvicinate circa 5,3 s mantenute come record distinti.
- Compilazione e 17 test passati sul Raspberry con Python 3.13.5.
- AP, route Ethernet e cattura live attivi all’ultimo controllo storico.

Il decoder qui incluso è recuperato dal codice e dalle correzioni registrati nella chat. La suite mantiene le verifiche originali; il campione copiato dalla cattura è stato sostituito con valori sintetici e le date dei test sono fittizie.

## Verifica locale della versione preparata per la pubblicazione

Su Windows con Python 3.10.3: 16 test passati e un test POSIX sui permessi saltato. Controllo automatico privacy senza segnalazioni. Questa verifica usa dati sintetici e simulazioni di TShark; non equivale a una nuova esecuzione del progetto sul Pi. Non sono stati installati servizi o modificati apparati remoti per preparare la guida.

## Verifiche ancora aperte

- Confronto puntuale con console e WeatherCloud allo stesso istante.
- Risposta di vento, pioggia e UV a eventi reali.
- Provenienza e compensazione della pressione.
- Funzionamento senza Internet e dopo un riavvio.
- Ricezione radio diretta, integrazione MQTT e Home Assistant.

Questa guida non promette indipendenza da WeatherCloud o frequenza superiore agli upload della console. Il proprietario ha approvato esplicitamente la pubblicazione della versione revisionata.
