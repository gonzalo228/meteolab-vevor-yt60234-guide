# Checklist privacy prima della pubblicazione

La revisione va eseguita sull’intera cronologia Git, non solo sull’ultima versione dei file.

- [ ] Nessun PCAP/PCAPNG o estratto di pacchetti reali.
- [ ] Nessun SSID, password, cookie, token, chiave WeatherCloud o URI completo reale.
- [ ] Nessun indirizzo IP/MAC reale o hostname riconducibile all’impianto.
- [ ] Nessuna chiave SSH pubblica o privata, fingerprint o riga `authorized_keys`.
- [ ] Nessun indirizzo email, nome personale o percorso utente.
- [ ] Nessuno screenshot non ritagliato e nessun metadato immagine sensibile.
- [ ] Esempi e fixture dichiarati e verificati come sintetici.
- [ ] `python tools/privacy_check.py .` termina senza segnalazioni inattese.
- [ ] Ricerca manuale completata per `password`, `secret`, `token`, `key`, `ssid`, `http`, `192.168`, `10.`, `172.`, `ssh-`, `@`.
- [ ] Repository GitHub creata inizialmente privata e contenuti verificati dal proprietario.
- [ ] Visibilità pubblica abilitata soltanto dopo approvazione esplicita.

Se un segreto è mai entrato nella cronologia, rimuoverlo dal file non basta: revocarlo/ruotarlo e riscrivere la cronologia prima della pubblicazione.

