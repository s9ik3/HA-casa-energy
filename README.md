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
2. Segui gli step guidati:
   - **Nome istanza**: un'etichetta per questa configurazione (utile se in futuro vuoi tracciare più contatori/case separatamente)
   - **Sensori energy**: seleziona uno o più sensori con `device_class: energy` di cui vuoi lo storico. Questi sono i dispositivi che concorrono al calcolo del totale della potenza istantanea. Il sensore di potenza (Watt) dello stesso dispositivo viene individuato **automaticamente** (stesso device Home Assistant): non serve selezionarlo di nuovo. Se un dispositivo ha più sensori di potenza, ti verrà chiesto quale usare; se non ne ha nessuno, un avviso bloccante te lo segnala (con possibilità di procedere comunque accettando che quel dispositivo non venga conteggiato)
   - **Tariffa**: prezzo energia (€/kWh), costi fissi mensili, eventuali oneri aggiuntivi, aliquota IVA — verifica sempre questi valori con la tua bolletta reale
   - **Potenza istantanea**: potenza massima del tuo contatore/impianto, soglie di allerta (in percentuale)

Se vuoi mostrare in card anche dispositivi che **non** devono contare nel totale (es. un dispositivo già incluso in un carico aggregato, o semplicemente qualcosa che vuoi solo monitorare a colpo d'occhio), si aggiungono direttamente dall'editor della card — vedi sotto.

### Separatore decimale nei campi tariffa

I campi della tariffa (prezzo/kWh, costi fissi, oneri, IVA) sono validati internamente con il punto come separatore decimale (es. `0.1122`). Nella pratica, la maggior parte dei browser con lingua italiana converte automaticamente la virgola in punto quando digiti in questi campi numerici, quindi scrivere `0,1122` funziona comunque nella maggior parte dei casi. Se dopo aver salvato la stima del costo mensile in card ti sembra sballata (troppo alta, troppo bassa, o pari a zero), è il segnale che nel tuo caso la conversione non è avvenuta: riprova scrivendo il valore con il punto (`0.1122`) e verifica che la stima torni sensata.

### Estrarre i valori della tariffa da una bolletta con l'IA

Se hai una bolletta PDF o una foto e vuoi ricavare rapidamente i valori da inserire, puoi incollare questo prompt (insieme al documento) in un assistente IA capace di leggere documenti/immagini (es. Claude, ChatGPT):

```
Analizza questa bolletta elettrica ed estrai i valori della tariffa.

Prima i quattro campi base (numeri con il PUNTO come separatore decimale,
mai la virgola):

price_per_kwh: 0
fixed_monthly_cost: 0
extra_charges_per_kwh: 0
vat_rate: (aliquota IVA principale in percentuale, es. 10 oppure 22)

Lascia i primi tre a 0: ogni componente della bolletta va invece elencata
come voce avanzata qui sotto, per non perdere precisione comprimendo più
voci in un solo numero.

Poi elenca OGNI voce della bolletta (quota energia, quota fissa, quota
potenza, ogni onere di sistema, accise, sconti, arrotondamenti, ecc.)
come blocco YAML, in questo formato ESATTO, pronto da incollare così
com'è:

- name: "<nome della voce, es. Consumo energia>"
  type: per_kwh
  value: <numero, anche negativo per sconti/detrazioni>
- name: "<altra voce>"
  type: fixed
  value: <numero>

Regole per 'type':
- per_kwh: se la voce in bolletta è moltiplicata per i kWh consumati nel
  periodo
- fixed: se la voce è un importo fisso mensile, indipendente dal consumo
- per_kw_power: se la voce è calcolata sulla potenza impegnata in kW (non
  sui kWh) — in questo caso aggiungi anche 'engaged_power_kw: <numero>'
  con la potenza impegnata indicata in bolletta

Per ogni voce, aggiungi 'apply_vat: false' SOLO se in bolletta risulta
esplicitamente non soggetta a IVA (es. un arrotondamento con codice IVA
"fuori campo" o simile); altrimenti ometti il campo (l'IVA si applica di
default). Se una voce è stagionale (attiva solo in alcuni mesi), aggiungi
'month_from: <1-12>' e 'month_to: <1-12>'.

Se un valore non è chiaramente deducibile dal documento, ometti quella
voce e segnalalo a parte, invece di inventare un numero.
```

I tre campi base vanno lasciati a 0 nello step "Tariffa" (solo l'IVA va compilata), e il blocco YAML restituito dall'IA va incollato per intero nel campo "Voci di tariffa (YAML)" dello step successivo (vedi sotto). Ricontrolla sempre i valori estratti confrontandoli con la bolletta: l'IA può interpretare male voci non standard o bollette con più fasce orarie.

### Voci di tariffa avanzate (bollette con più componenti)

Se la tua bolletta ha una struttura più complessa dei quattro campi semplici (più oneri distinti, componenti stagionali, importi non soggetti a IVA, ecc.), dallo step "Tariffa" delle Opzioni spunta "Gestisci voci di tariffa avanzate": si apre un campo di testo dove incolli **tutte le voci in un colpo solo**, come YAML — una lista con un blocco per voce:

```yaml
- name: Consumo energia
  type: per_kwh
  value: 0.1122
- name: Quota fissa
  type: fixed
  value: 9.10
- name: Quota potenza trasporto
  type: per_kw_power
  value: 1.96
  engaged_power_kw: 3.0
- name: Arrotondamenti
  type: fixed
  value: -0.43
  apply_vat: false
- name: Costo stagionale
  type: fixed
  value: 9.00
  apply_vat: false
  month_from: 1
  month_to: 10
```

Campi per voce:
- **name**: nome libero, deve essere diverso per ogni voce
- **type**: `per_kwh` (moltiplicato per i kWh del mese), `fixed` (importo fisso mensile), oppure `per_kw_power` (moltiplicato per la potenza impegnata — utile per componenti come la quota potenza del trasporto, calcolate sui kW e non sui kWh)
- **value**: può essere negativo, per rappresentare una detrazione/credito
- **engaged_power_kw**: richiesto solo per il tipo `per_kw_power`
- **apply_vat**: `false` per escludere quella voce dall'IVA configurata sopra; se omesso, l'IVA si applica (default `true`)
- **month_from** / **month_to**: opzionali, 1-12, per voci stagionali attive solo in certi mesi; se omessi la voce si applica tutto l'anno

Se il testo incollato non è YAML valido o manca un campo obbligatorio, lo step segnala l'errore specifico (quale voce e quale campo) invece di far sparire silenziosamente una voce. Lascia il campo vuoto per non avere voci avanzate — riapri lo step in qualsiasi momento per vedere e modificare quelle già salvate, precompilate automaticamente. Le voci extra si sommano ai quattro campi semplici, non li sostituiscono. Come per la tariffa semplice, anche le voci extra vengono congelate sui mesi già chiusi quando le modifichi (vedi sotto).

## Modificare la configurazione dopo l'installazione

Impostazioni → Dispositivi e servizi → Casa Energy → **Configura**. Puoi modificare sensori energy, tariffa, soglie e rinominare i carichi in qualsiasi momento, senza reinstallare nulla. Se la selezione dei sensori energy non cambia, i carichi già risolti (incluse eventuali rinomine) restano invariati.

## Card Lovelace inclusa

L'integrazione include una card dedicata (`Casa Energy Card`), servita e **registrata automaticamente** all'installazione — non serve copiare nessun file né aggiungere risorse a mano. Dopo aver configurato l'integrazione, cercala nel picker "Aggiungi card" del tuo dashboard.

La card legge direttamente le due entità generate: seleziona `sensor.<nome>_potenza_istantanea` e `sensor.<nome>_storico_consumi_mensili` dall'editor visuale della card (o scrivi il YAML a mano, se preferisci):

```yaml
type: custom:casa-energy-card
power_entity: sensor.casa_potenza_istantanea
history_entity: sensor.casa_storico_consumi_mensili
```

### Dispositivi solo visualizzazione

Dall'editor della card puoi aggiungere dispositivi extra (nome + sensore di potenza) da mostrare come chip separate, **esclusi dal totale**: utili per dispositivi già inclusi in un carico aggregato, o semplicemente per tenerli d'occhio senza farli contribuire alla somma. A differenza dei carichi principali, questi non passano dall'integrazione: si gestiscono interamente qui, con un editor visuale (nome + selettore entità, aggiungi/rimuovi). In YAML:

```yaml
type: custom:casa-energy-card
power_entity: sensor.casa_potenza_istantanea
history_entity: sensor.casa_storico_consumi_mensili
extra_devices:
  - name: "Server"
    entity: sensor.server_power
  - name: "Lavastoviglie"
    entity: sensor.lavastoviglie_power
```

### Ordine e rinomina delle chip

Dall'editor della card puoi trascinare (maniglia "☰") sia i carichi principali sia i dispositivi solo-visualizzazione per cambiare l'ordine con cui compaiono. Su ogni riga, il pulsante "✎" apre una schermata dedicata: per i carichi principali permette di rinominare la chip senza toccare il nome configurato nell'integrazione (l'etichetta personalizzata viene salvata in `load_labels`); per i dispositivi solo-visualizzazione permette di modificare sia il nome sia il sensore di potenza abbinato, salvando direttamente in `extra_devices`. Il pulsante "✕" per rimuovere un dispositivo resta invece visibile direttamente sulla riga.

**Nota**: la registrazione automatica della risorsa Lovelace richiede che il tuo dashboard sia in modalità "storage" (quella di default per la maggior parte delle installazioni). Se usi un dashboard configurato interamente via YAML, l'auto-registrazione potrebbe non riuscire — in quel caso un messaggio nei log ti dice di aggiungere la risorsa manualmente (Impostazioni → Dashboard → Risorse → URL `/casa_energy_static/casa-energy-card.js`, tipo Modulo JavaScript). L'integrazione resta comunque pienamente funzionante in ogni caso: solo il passaggio automatico della card potrebbe richiedere un piccolo intervento manuale su questo tipo di setup.

Se configuri più istanze (es. Casa e Ufficio), la card viene registrata una sola volta e rimane disponibile per tutte; viene rimossa solo quando **l'ultima** istanza viene disinstallata.

## Entità create

Per ogni istanza configurata, l'integrazione crea:

| Entità | Descrizione |
|---|---|
| `sensor.<nome>_storico_consumi_mensili` | Stato: numero di mesi disponibili nello storico. Attributo `mesi`: array `{mese, kwh, costo}` per ogni mese |
| `sensor.<nome>_potenza_istantanea` | Stato: potenza attuale in W, somma dei carichi configurati nell'integrazione. Attributi: `status` (`ok`/`warning`/`critical`), `percent_of_max`, `max_power`, `warning_threshold_pct`, `critical_threshold_pct`, `loads` (array `{name, value}`) |

## Card YAML alternativa (opzionale)

Se preferisci non usare la card auto-registrata sopra, il repository include comunque, nella cartella [`examples_virtual_sensors/`](examples_virtual_sensors/), il file `energy_summary_card_integration.yaml`: una card più elaborata (con carichi in griglia, storico mesi precedenti espandibile) da incollare a mano, richiede `button-card` e `card_mod` via HACS.

## Icona dell'integrazione

L'integrazione include un'icona dedicata (`custom_components/casa_energy/brand/`), mostrata automaticamente nella pagina "Dispositivi e servizi" e nel picker di aggiunta integrazione. Richiede **Home Assistant 2026.3 o successivo**: su versioni precedenti l'icona non compare (nessun errore, solo l'icona generica), il resto dell'integrazione funziona comunque normalmente.

## Note tecniche

- Lo storico mensile viene ricalcolato ogni 15 minuti tramite l'API statistics nativa di Home Assistant (non query SQL dirette), quindi funziona in modo identico su installazioni con SQLite, MariaDB o PostgreSQL come database recorder.
- La potenza istantanea si aggiorna in tempo reale (basata su eventi di cambio stato del sensore sorgente), non sull'intervallo di 15 minuti.
- Le soglie e la tariffa sono per singola istanza: se configuri più istanze (es. Casa e Ufficio), ognuna ha i propri valori indipendenti.
- **Tariffe congelate sui mesi chiusi**: quando modifichi prezzo, costi fissi, oneri, IVA o le voci di tariffa avanzate dalle Opzioni, la nuova tariffa si applica dal 1° del mese corrente in poi; i mesi già chiusi restano fissi alla tariffa (comprese le eventuali voci avanzate) con cui erano stati calcolati e non cambiano più, anche a fronte di modifiche future. Per resettare questo comportamento e far ricalcolare tutti i mesi passati con la tariffa attuale, spunta "Reset tariffe congelate" nello step Tariffa delle Opzioni.
