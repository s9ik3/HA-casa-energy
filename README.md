# Casa Energy

*[Read this in English](README.en.md)*

Integrazione Home Assistant, installabile da HACS, che calcola e monitora:

- **Storico consumi mensili** (kWh) e stima del costo in bolletta, a partire dalle statistiche a lungo termine già registrate da Home Assistant per uno o più sensori "energy"
- **Potenza istantanea** con stato di soglia automatico (`ok` / `warning` / `critical`), percentuale rispetto alla potenza massima del tuo contatore, ed elenco dei carichi principali monitorati

Tutta la configurazione avviene da interfaccia grafica — nessun YAML da scrivere, nessuna query SQL da editare.

## Installazione

### Tramite HACS (repository personalizzato)

1. HACS → Integrazioni → menu (⋮) in alto a destra → **Repository personalizzati**
2. Aggiungi l'URL di questo repository, categoria **Integrazione**
3. Cerca "Casa Energy" nella lista HACS → Scarica
4. Riavvia Home Assistant

### Manuale

1. Copia la cartella `custom_components/casa_energy/` in `/config/custom_components/`
2. Riavvia Home Assistant

## Configurazione

Dopo l'installazione e il riavvio:

1. Impostazioni → Dispositivi e servizi → Aggiungi integrazione → cerca **Casa Energy**
2. Segui i 4 step guidati:
   - **Nome istanza**: un'etichetta per questa configurazione (utile se in futuro vuoi tracciare più contatori/case separatamente)
   - **Sensori energy**: seleziona uno o più sensori con `device_class: energy` di cui vuoi lo storico
   - **Tariffa**: prezzo energia (€/kWh), costi fissi mensili, eventuali oneri aggiuntivi, aliquota IVA — verifica sempre questi valori con la tua bolletta reale
   - **Potenza istantanea**: sensore di potenza totale, potenza massima del tuo contatore/impianto, soglie di allerta (in percentuale)
3. Facoltativo: aggiungi uno o più "carichi" da monitorare singolarmente (nome + sensore di potenza)

## Modificare la configurazione dopo l'installazione

Impostazioni → Dispositivi e servizi → Casa Energy → **Configura**. Puoi modificare sensori, tariffa, soglie e gestire (aggiungere/rimuovere) i carichi monitorati in qualsiasi momento, senza reinstallare nulla.

## Card Lovelace inclusa

L'integrazione include una card dedicata (`Casa Energy Card`), servita e **registrata automaticamente** all'installazione — non serve copiare nessun file né aggiungere risorse a mano. Dopo aver configurato l'integrazione, cercala nel picker "Aggiungi card" del tuo dashboard.

La card legge direttamente le due entità generate: seleziona `sensor.<nome>_potenza_istantanea` e `sensor.<nome>_storico_consumi_mensili` dall'editor visuale della card (o scrivi il YAML a mano, se preferisci):

```yaml
type: custom:casa-energy-card
power_entity: sensor.casa_potenza_istantanea
history_entity: sensor.casa_storico_consumi_mensili
```

**Nota**: la registrazione automatica della risorsa Lovelace richiede che il tuo dashboard sia in modalità "storage" (quella di default per la maggior parte delle installazioni). Se usi un dashboard configurato interamente via YAML, l'auto-registrazione potrebbe non riuscire — in quel caso un messaggio nei log ti dice di aggiungere la risorsa manualmente (Impostazioni → Dashboard → Risorse → URL `/casa_energy_static/casa-energy-card.js`, tipo Modulo JavaScript). L'integrazione resta comunque pienamente funzionante in ogni caso: solo il passaggio automatico della card potrebbe richiedere un piccolo intervento manuale su questo tipo di setup.

Se configuri più istanze (es. Casa e Ufficio), la card viene registrata una sola volta e rimane disponibile per tutte; viene rimossa solo quando **l'ultima** istanza viene disinstallata.

## Entità create

Per ogni istanza configurata, l'integrazione crea:

| Entità | Descrizione |
|---|---|
| `sensor.<nome>_storico_consumi_mensili` | Stato: numero di mesi disponibili nello storico. Attributo `mesi`: array `{mese, kwh, costo}` per ogni mese |
| `sensor.<nome>_potenza_istantanea` | Stato: potenza attuale in W. Attributi: `status` (`ok`/`warning`/`critical`), `percent_of_max`, `max_power`, `warning_threshold_pct`, `critical_threshold_pct`, `loads` (array `{name, value}`) |

## Card YAML alternativa (opzionale)

Se preferisci non usare la card auto-registrata sopra, il repository include comunque, nella cartella [`examples_virtual_sensors/`](examples_virtual_sensors/), il file `energy_summary_card_integration.yaml`: una card più elaborata (con carichi in griglia, storico mesi precedenti espandibile) da incollare a mano, richiede `button-card` e `card_mod` via HACS.

## Note tecniche

- Lo storico mensile viene ricalcolato ogni 15 minuti tramite l'API statistics nativa di Home Assistant (non query SQL dirette), quindi funziona in modo identico su installazioni con SQLite, MariaDB o PostgreSQL come database recorder.
- La potenza istantanea si aggiorna in tempo reale (basata su eventi di cambio stato del sensore sorgente), non sull'intervallo di 15 minuti.
- Le soglie e la tariffa sono per singola istanza: se configuri più istanze (es. Casa e Ufficio), ognuna ha i propri valori indipendenti.
