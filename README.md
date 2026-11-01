# MeteoLab — analisi locale VEVOR YT60234

Guida sperimentale e riproducibile per osservare **senza interrompere WeatherCloud** il traffico generato da una console meteo VEVOR YT60234, usando un Raspberry Pi 4 come access point Wi‑Fi con uscita Ethernet.

> Stato: proof of concept, console con firmware 1.0.1 nel laboratorio originale. Il lavoro documenta ciò che è stato osservato in un singolo impianto; non è una specifica ufficiale VEVOR o WeatherCloud. Eseguire solo su dispositivi e reti propri. La provenienza e lo stato delle verifiche sono in [VERIFICATION.md](VERIFICATION.md).

## Obiettivo e limiti di sicurezza

Il percorso studiato è:

```text
sensori esterni → console VEVOR → Wi‑Fi del Raspberry Pi
                                    ├─ copia locale PCAPNG
                                    └─ Ethernet → router → WeatherCloud
```

Il Raspberry inoltra normalmente il traffico: la console continua quindi a usare WeatherCloud. La guida non modifica firmware, non effettua MITM TLS e non richiede credenziali WeatherCloud.

Non pubblicare catture reali: una richiesta HTTP può contenere identificativi, chiavi, indirizzi e dettagli della rete. Gli esempi di questo repository sono interamente sintetici.

## Risultati osservati

- La console ha prodotto richieste HTTP osservabili nel punto di transito.
- Nella prova notturna sono state decodificate **44 richieste**, ciascuna con nove misure. L’intervallo mediano è stato circa **786,5 secondi (13 min 6,5 s)**; sono presenti richieste ravvicinate a circa 5,3 secondi, senza prova che siano ritrasmissioni.
- Nel traffico sono state riconosciute grandezze coerenti con temperatura, umidità, pressione, vento, pioggia, radiazione solare e indice UV.
- Un decoder offline può estrarre e confrontare i parametri senza contattare WeatherCloud.

Le conversioni seguono la [specifica WeatherCloud](https://weathercloud.net/en/api): umidità e direzione restano invariate; temperatura, velocità, pioggia, intensità della pioggia, radiazione, UV e pressione sono divise per 10. Il decoder conserva anche il valore grezzo. Le conversioni documentate non dimostrano la calibrazione fisica del sensore.

## Prerequisiti

- Raspberry Pi 4 con Raspberry Pi OS recente e porta Ethernet collegata al router.
- Adattatore Wi‑Fi integrato dedicato alla console.
- `NetworkManager`, `dnsmasq-base`, `nftables`, `dumpcap`, `tshark` e Python 3.10 o successivo. Nel laboratorio originale NetworkManager era 1.52.1 e Python 3.13.5.
- PC amministrativo per copiare e analizzare le catture offline.
- Accesso locale alla console per poter ripristinare il Wi‑Fi originario.

Prima di iniziare, annotare la connessione Ethernet attiva e la configurazione Wi‑Fi originaria della console. Non applicare la procedura da remoto se la perdita dell’accesso al Pi impedirebbe il rollback.

Verificare `nmcli device status`, `rfkill list`, `nmcli -f WIFI-PROPERTIES.AP device show wlan0` e `ip route`: Wi-Fi disponibile, modalità AP supportata e route predefinita su Ethernet. Se la radio è bloccata via software, controllare prima i profili Wi-Fi con autoconnect prima di sbloccarla. Configurare il paese radio effettivo con gli strumenti del sistema. In presenza di VPN, Docker o firewall preesistenti, far verificare le regole prima di proseguire.

## 1. Access point con uscita Ethernet

Questi comandi sono un modello, non uno script da eseguire alla cieca. Sostituire soltanto i segnaposto e verificare i nomi delle interfacce con `nmcli device status`.

```bash
sudo nmcli connection add type wifi ifname wlan0 con-name meteolab-ap \
  autoconnect no ssid '<SSID_DI_TEST>'
sudo nmcli connection modify meteolab-ap \
  802-11-wireless.mode ap 802-11-wireless.band bg \
  ipv4.method shared ipv4.never-default yes ipv6.method disabled \
  wifi-sec.key-mgmt wpa-psk wifi-sec.psk '<PASSWORD_FORTE_DI_TEST>'
```

`ipv4.method shared` abilita sul Pi una sottorete privata, DHCP/DNS e inoltro/NAT verso la connessione predefinita, normalmente Ethernet. Controllare che la sottorete scelta non si sovrapponga alle reti esistenti. **Prima di attivare l’AP**, applicare l’isolamento descritto in [NETWORK.md](NETWORK.md), poi eseguire `sudo nmcli connection up meteolab-ap`. Verificare Internet dal Pi e configurare la console sul nuovo SSID lasciando invariate le impostazioni WeatherCloud. Attendere almeno due cicli e confermare sul portale che gli aggiornamenti continuino.

Non inserire SSID o password reali in file versionati. La password nella cronologia della shell va rimossa secondo le procedure del proprio sistema; per un laboratorio dedicato è preferibile creare il profilo in modo interattivo.

## 2. Acquisizione PCAPNG

Nel laboratorio TShark non riusciva a scrivere nella directory utente dopo la riduzione dei privilegi. La procedura riuscita usa `dumpcap` e una directory privata di root. Sostituire `<MAC_CONSOLE>` solo sul proprio Pi, senza salvarlo nel repository:

```bash
sudo install -d -o root -g root -m 700 /var/lib/meteolab/captures
sudo systemd-run --unit=meteolab-capture-lab --property=UMask=0077 \
  /usr/bin/dumpcap -i wlan0 -f 'ether host <MAC_CONSOLE>' \
  -b filesize:10240 -b files:5 -a duration:28800 \
  -w /var/lib/meteolab/captures/lab.pcapng
```

Il ring buffer limita lo spazio a circa 50 MB e la cattura dura al massimo otto ore. Include anche DNS, DHCP e NTP della console, utili per l’inventario. Controllare servizio, crescita dei file e permessi `0600`. Un file contenente solo l’intestazione non prova un guasto: attendere un ciclo o generare un test di rete locale controllato. I file restano sensibili: tenerli fuori dal repository. Se la console usa HTTPS, il contenuto non sarà decodificabile con questa procedura; non disabilitare TLS.

Per una prima ispezione locale:

```bash
sudo tshark -r '<FILE_PCAPNG_COMPLETATO>' \
  -Y 'http.request' -T fields \
  -e frame.time_epoch -e http.request.method -e http.host
```

Non copiare questo output in issue, forum o repository prima della sanificazione.

## 3. Decoder offline

Lo script [decoder/decode_weathercloud.py](decoder/decode_weathercloud.py) accetta un PCAP/PCAPNG e usa `tshark` solo in locale:

```bash
python decoder/decode_weathercloud.py cattura.pcapng --output letture.sanitized.json
```

Per verificare il funzionamento senza dati reali:

```bash
python -m unittest discover -s tests -v
```

Il risultato è un documento JSON con riepilogo, record e problemi rilevati. Vengono esportati soltanto campi meteo numerici ammessi: ID, chiavi, campi sconosciuti, host, URI, IP e MAC sono esclusi. Sono riconosciuti sia parametri nei segmenti `/v01/set/...` sia query; i campi assenti restano assenti, gli zeri sono conservati e i duplicati conflittuali sono segnalati. Le richieste ravvicinate restano distinte. Il timestamp è quello del pacchetto, non della misurazione. L’output non viene sovrascritto e su Linux è creato con permessi `0600`.

Il JSON contiene comunque timestamp, misure e hash della cattura: resta materiale privato da rivedere prima di condividerlo. Su Windows impostare una cartella con accesso limitato tramite ACL: il modo POSIX `0600` non offre la stessa garanzia. Analizzare una cattura completata; il decoder verifica che il contenuto non cambi durante la lettura. Non pubblicare i risultati reali in questo repository.

## 4. Metodo di analisi

1. Conservare la cattura originale solo in locale.
2. Estrarre richieste HTTP con il decoder.
3. Ordinare le letture nel tempo e misurare l’intervallo fra invii.
4. Variare una grandezza alla volta quando possibile e confrontarla con la console/WeatherCloud.
5. Registrare per ogni campo: nome grezzo, valore grezzo, ipotesi, unità, numero di confronti e stato (`osservato`, `probabile`, `confermato`).
6. Non dichiarare confermata una scala basandosi su una sola lettura.

## Risultati e limiti

Questa soluzione migliora l’osservabilità e permette analisi offline, ma non rende la stazione indipendente dal cloud né aumenta la frequenza trasmessa dalla console. Dieci–tredici minuti possono essere sufficienti per temperatura o pressione, ma non descrivono bene raffiche e precipitazioni improvvise. La ricezione diretta del collegamento radio a 868 MHz, a monte della console, resta un filone separato e non è trattata qui.

Nei 44 upload erano presenti `temp`, `hum`, `wspd`, `wdir`, `rain`, `rainrate`, `solarrad`, `uvi`, `bar`. Mancavano `tempin`, `humin`, `wspdavg` e `wspdhi`; i lux non sono equivalenti alla radiazione solare. Vento, pioggia e UV erano sempre a zero, quindi la risposta a eventi non è verificata. L’origine fisica della pressione e la correzione al livello del mare restano da confermare. Sono state osservate 35 risposte HTTP 200; per nove richieste non risultava una risposta HTTP nella cattura: ciò non basta a classificarle come successi o fallimenti. Il decoder non valuta l’accettazione lato server.

L’eventuale integrazione MQTT/Home Assistant è volutamente esclusa dalla versione verificata: prima servono una mappatura stabile dei campi, test più lunghi e gestione esplicita dei dati obsoleti.

## Rollback

1. Riconfigurare la console sul Wi‑Fi originario del router.
2. Verificare sul portale WeatherCloud almeno un nuovo aggiornamento con orario successivo al cambio.
3. Arrestare la cattura con `sudo systemctl stop meteolab-capture-lab.service`. Disattivare, senza cancellarlo subito, il profilo del laboratorio:

   ```bash
   sudo nmcli connection down meteolab-ap
   ```

4. Verificare che il Pi sia ancora raggiungibile via Ethernet e che WeatherCloud continui ad aggiornarsi.
5. Solo dopo la verifica, eliminare il profilo se non serve più:

   ```bash
   sudo nmcli connection delete meteolab-ap
   ```

6. Rimuovere soltanto la tabella firewall dedicata, se creata, con `sudo nft delete table inet meteolab_guard`. Rimuovere privatamente i PCAPNG sensibili e revocare eventuali chiavi SSH temporanee aggiunte per il laboratorio.

Se WeatherCloud non aggiorna, riattivare l’AP con `sudo nmcli connection up meteolab-ap`, ricollegare la console al SSID di test e diagnosticare senza spegnere il Pi.

Prima di riattivarlo, ricaricare anche le protezioni di [NETWORK.md](NETWORK.md) eventualmente già rimosse. I servizi creati con `systemd-run` sono transitori e questa procedura non configura l’avvio automatico dopo un riavvio.

## Privacy e pubblicazione

Prima di ogni commit eseguire:

```bash
python tools/privacy_check.py .
```

La checklist completa è in [PRIVACY.md](PRIVACY.md). Il controllo automatico segnala pattern comuni ma non sostituisce una revisione umana. PCAP/PCAPNG, chiavi SSH, file `.env`, configurazioni Wi‑Fi e screenshot sono esclusi anche da [.gitignore](.gitignore).

## Licenza e responsabilità

Codice e documentazione sono rilasciati con licenza MIT. Marchi e servizi citati appartengono ai rispettivi proprietari. Usare la guida solo su infrastrutture proprie e nel rispetto delle condizioni dei servizi utilizzati.

