# Isolamento del laboratorio

Nel laboratorio originale era presente una protezione nftables dedicata, oltre al NAT gestito da NetworkManager. Il modello seguente deve essere adattato alle proprie reti, senza sostituire regole preesistenti. Non usare `nft flush ruleset`.

Prima di accendere l’AP, salvare **fuori dal repository** un file `meteolab-guard.nft` con questo contenuto. Sostituire `<RETI_LOCALI_CIDR>` con l’elenco, separato da virgole, di tutte le sottoreti locali raggiungibili (LAN, VLAN, VPN, reti container). Non includere la sottorete dell’AP nell’elenco delle reti da inoltrare: i servizi DHCP e DNS sul Pi sono gestiti dalla catena input.

```nft
table inet meteolab_guard {
    chain input_guard {
        type filter hook input priority -10; policy accept;
        iifname "wlan0" ct state established,related accept
        iifname "wlan0" udp dport { 53, 67 } accept
        iifname "wlan0" tcp dport 53 accept
        iifname "wlan0" ip protocol icmp accept
        iifname "wlan0" counter reject with icmpx type admin-prohibited
    }
    chain forward_guard {
        type filter hook forward priority -10; policy accept;
        iifname "wlan0" ip daddr { <RETI_LOCALI_CIDR> } counter drop
        iifname "wlan0" meta nfproto ipv6 counter drop
    }
}
```

Con AP ancora spento, controllare che la tabella dedicata non esista già. Se esiste, ispezionarla prima di procedere; non cancellarla automaticamente. Validare e applicare il file locale:

```bash
sudo nft -c -f meteolab-guard.nft
sudo nft -f meteolab-guard.nft
sudo nft list table inet meteolab_guard
```

Eseguire il secondo comando solo se il primo termina con successo. Un `accept` in questa tabella non annulla eventuali blocchi di altre catene; verificare la compatibilità con il firewall del sistema. La configurazione presume IPv6 disabilitato sul profilo AP e impedisce l’inoltro IPv6 dalla WLAN.

Dopo l’avvio verificare che la route predefinita del Pi usi ancora Ethernet, che un client di test riceva DHCP/DNS e raggiunga Internet, e che non possa raggiungere SSH del Pi o servizi delle reti locali elencate. Usare un client amministrativo di test prima di collegare la console. Il test negativo di isolamento è necessario: NAT da solo non isola la LAN.

Nel laboratorio furono impiegati timer temporanei per fermare l’AP durante il collaudo. Un timer che spegne l’AP interrompe anche l’accesso Internet della console: usare questa tecnica solo per prove sorvegliate, poi riconnettere la console al Wi-Fi originario prima della scadenza. Non predisporre un arresto automatico del gateway durante l’uso ordinario di WeatherCloud.

Per il rollback seguire prima la sequenza del README e rimuovere solo la tabella dedicata dopo lo spegnimento dell’AP:

```bash
sudo nft delete table inet meteolab_guard
```

La procedura non configura un firewall persistente. Dopo un riavvio ripetere i controlli e caricare la protezione prima di riaccendere l’AP.
