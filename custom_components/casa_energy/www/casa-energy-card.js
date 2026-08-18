class CasaEnergyCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
  }

  setConfig(config) {
    if (!config.power_entity || !config.history_entity) {
      throw new Error(
        "Servono 'power_entity' e 'history_entity' (le due entità create dall'integrazione Casa Energy)"
      );
    }
    this._config = config;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config) return;
    this._update();
  }

  getCardSize() {
    return 3;
  }

  static getStubConfig(hass) {
    // Prova a precompilare automaticamente cercando le entità
    // dell'integrazione già presenti in questa istanza HA.
    const entities = Object.keys(hass.states || {});
    const power = entities.find((e) => e.includes("potenza_istantanea"));
    const history = entities.find((e) => e.includes("storico_consumi_mensili"));
    return {
      power_entity: power || "sensor.casa_potenza_istantanea",
      history_entity: history || "sensor.casa_storico_consumi_mensili",
    };
  }

  static getConfigElement() {
    return document.createElement("casa-energy-card-editor");
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <ha-card>
        <style>
          ha-card {
            padding: 14px 18px;
            border-radius: 16px;
          }
          .cec-top {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 10px;
          }
          .cec-title-row {
            display: flex;
            align-items: center;
            gap: 8px;
          }
          .cec-title {
            font-weight: 800;
            font-size: 14px;
          }
          .cec-badge {
            font-size: 10px;
            font-weight: 800;
            padding: 2px 8px;
            border-radius: 999px;
            display: none;
          }
          .cec-power {
            font-size: 22px;
            font-weight: 900;
            text-align: right;
            line-height: 1;
          }
          .cec-percent {
            font-size: 11px;
            text-align: right;
            opacity: 0.7;
            margin-top: 3px;
          }
          .cec-bar-track {
            height: 10px;
            border-radius: 999px;
            background: rgba(127,127,127,0.15);
            overflow: hidden;
            margin-top: 10px;
          }
          .cec-bar-fill {
            height: 100%;
            border-radius: 999px;
            transition: width 0.3s ease;
          }
          .cec-loads {
            display: grid;
            gap: 8px;
            margin-top: 10px;
          }
          .cec-loads-full {
            display: grid;
            grid-template-columns: 1fr;
            gap: 8px;
          }
          .cec-loads-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
            margin-top: 8px;
          }
          .cec-load-chip {
            padding: 8px 10px;
            border-radius: 12px;
            background: rgba(127,127,127,0.08);
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 12px;
          }
          .cec-chip-name {
            flex: 1;
            min-width: 0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
          }
          .cec-month-section {
            margin-top: 12px;
            padding-top: 10px;
            border-top: 1px solid rgba(127,127,127,0.15);
          }
          .cec-month-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
          }
          .cec-month-title {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 13px;
            font-weight: 700;
          }
          .cec-month-kwh {
            font-weight: 800;
            font-size: 18px;
            text-align: right;
          }
          .cec-month-cost {
            font-size: 11px;
            opacity: 0.65;
            text-align: right;
          }
          .cec-month-bar-track {
            height: 6px;
            border-radius: 999px;
            background: rgba(127,127,127,0.12);
            overflow: hidden;
            margin-top: 8px;
          }
          .cec-month-bar-fill {
            height: 100%;
            border-radius: 999px;
            background: #42a5f5;
            transition: width 0.3s ease;
          }
          .cec-history-toggle {
            display: flex;
            align-items: center;
            gap: 4px;
            font-size: 12px;
            opacity: 0.7;
            margin-top: 10px;
            cursor: pointer;
          }
          .cec-history {
            margin-top: 4px;
          }
          .cec-history-row {
            padding: 6px 0;
            border-top: 1px solid rgba(127,127,127,0.1);
          }
          .cec-history-line {
            display: flex;
            justify-content: space-between;
            font-size: 11px;
          }
          .cec-history-month {
            opacity: 0.65;
          }
          .cec-history-kwh {
            font-weight: 700;
          }
          .cec-history-cost {
            opacity: 0.6;
            font-weight: 600;
            margin-left: 6px;
          }
          .cec-history-bar-track {
            height: 5px;
            border-radius: 999px;
            background: rgba(127,127,127,0.1);
            overflow: hidden;
            margin-top: 4px;
          }
          .cec-history-bar-fill {
            height: 100%;
            border-radius: 999px;
            background: #42a5f5;
          }
          .cec-history-empty {
            font-size: 11px;
            opacity: 0.5;
          }
        </style>
        <div class="cec-top">
          <div class="cec-title-row">
            <ha-icon icon="mdi:flash"></ha-icon>
            <span class="cec-title">Energia</span>
            <span class="cec-badge" id="cec-badge">ATTENZIONE</span>
          </div>
          <div>
            <div class="cec-power" id="cec-power">-- W</div>
            <div class="cec-percent" id="cec-percent">-- % soglia</div>
          </div>
        </div>
        <div class="cec-bar-track">
          <div class="cec-bar-fill" id="cec-bar-fill" style="width:0%;"></div>
        </div>
        <div class="cec-loads" id="cec-loads"></div>
        <div class="cec-month-section">
          <div class="cec-month-header">
            <div class="cec-month-title">
              <ha-icon icon="mdi:calendar-month" style="--mdc-icon-size:16px;"></ha-icon>
              Mese corrente
            </div>
            <div>
              <div class="cec-month-kwh" id="cec-month-kwh">-- kWh</div>
              <div class="cec-month-cost" id="cec-month-cost"></div>
            </div>
          </div>
          <div class="cec-month-bar-track">
            <div class="cec-month-bar-fill" id="cec-month-bar-fill" style="width:0%;"></div>
          </div>
          <div class="cec-history-toggle" id="cec-history-toggle">
            <span id="cec-toggle-arrow" style="font-size:9px;transition:transform 0.2s;">▸</span>
            <span id="cec-history-toggle-label">Mostra mesi precedenti</span>
          </div>
          <div class="cec-history" id="cec-history" style="display:none;"></div>
        </div>
      </ha-card>
    `;
    this._powerEl = this.shadowRoot.querySelector("#cec-power");
    this._percentEl = this.shadowRoot.querySelector("#cec-percent");
    this._barFill = this.shadowRoot.querySelector("#cec-bar-fill");
    this._badge = this.shadowRoot.querySelector("#cec-badge");
    this._loadsEl = this.shadowRoot.querySelector("#cec-loads");
    this._monthKwhEl = this.shadowRoot.querySelector("#cec-month-kwh");
    this._monthCostEl = this.shadowRoot.querySelector("#cec-month-cost");
    this._monthBarFill = this.shadowRoot.querySelector("#cec-month-bar-fill");
    this._historyEl = this.shadowRoot.querySelector("#cec-history");
    this._historyToggleLabel = this.shadowRoot.querySelector("#cec-history-toggle-label");
    this._toggleArrow = this.shadowRoot.querySelector("#cec-toggle-arrow");
    this._historyOpen = false;

    this.shadowRoot.querySelector("#cec-history-toggle").addEventListener("click", () => {
      this._historyOpen = !this._historyOpen;
      this._historyEl.style.display = this._historyOpen ? "block" : "none";
      this._toggleArrow.style.transform = this._historyOpen ? "rotate(90deg)" : "rotate(0deg)";
      const passatiCount = (this._mesi || []).filter((m) => {
        const now = new Date();
        const ymCorr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
        return m.mese !== ymCorr;
      }).length;
      this._historyToggleLabel.textContent = this._historyOpen
        ? "Nascondi mesi precedenti"
        : `Mostra mesi precedenti (${passatiCount})`;
      this._renderHistory();
    });
  }

  _statusColor(status) {
    if (status === "critical") return "#e53935";
    if (status === "warning") return "#fb8c00";
    if (status === "ok") return "#43a047";
    return "var(--disabled-text-color, #888)";
  }

  _readPowerValue(entityId) {
    if (!entityId || !this._hass) return null;
    const state = this._hass.states[entityId];
    if (!state || state.state === "unknown" || state.state === "unavailable") return null;
    const value = parseFloat(String(state.state).replace(",", "."));
    return isNaN(value) ? null : value;
  }

  // Applica un'etichetta personalizzata (scelta dall'editor) sopra il
  // nome originale del carico, senza modificarlo: l'ordine (_applyOrder)
  // e il collegamento coi dati del sensore restano chiavi sul nome
  // originale, così rinominare un carico non rompe l'ordine salvato né
  // il matching coi valori letti dal sensore.
  _withLabel(item, labelsKey) {
    const labels = (this._config && this._config[labelsKey]) || {};
    const label = labels[item.name];
    return label ? { ...item, name: label } : item;
  }

  _applyOrder(list, group) {
    const orderKey = group === "total" ? "load_order" : "display_load_order";
    const order = (this._config && this._config[orderKey]) || [];
    if (!order.length) return list;
    const byName = new Map(list.map((l) => [l.name, l]));
    const ordered = [];
    for (const name of order) {
      if (byName.has(name)) {
        ordered.push(byName.get(name));
        byName.delete(name);
      }
    }
    // Eventuali elementi nuovi non ancora presenti nell'ordine salvato
    // (es. appena aggiunti dal config_flow) vengono accodati in fondo.
    for (const remaining of byName.values()) ordered.push(remaining);
    return ordered;
  }

  _update() {
    if (!this._hass || !this._config) return;

    const powerState = this._hass.states[this._config.power_entity];
    if (powerState) {
      const value = parseFloat(powerState.state);
      const attrs = powerState.attributes || {};
      const status = attrs.status || "unknown";
      const percent = attrs.percent_of_max;
      const color = this._statusColor(status);

      this._powerEl.textContent = isNaN(value) ? "-- W" : `${Math.round(value)} W`;
      this._powerEl.style.color = color;
      this._percentEl.textContent = percent == null ? "-- % soglia" : `${percent}% soglia`;
      this._barFill.style.width = `${Math.max(0, Math.min(100, percent || 0))}%`;
      this._barFill.style.background = color;

      if (status === "critical") {
        this._badge.style.display = "inline-block";
        this._badge.style.background = "#e5393522";
        this._badge.style.color = "#e53935";
      } else {
        this._badge.style.display = "none";
      }

      const loads = attrs.loads || [];
      const chip = (l) => `
        <div class="cec-load-chip">
          <span class="cec-chip-name">${l.name}</span>
          <span class="cec-chip-value" style="font-weight:700;color:${color};">${
            l.value == null ? "N/A" : Math.round(l.value) + " W"
          }</span>
        </div>
      `;
      const totalLoads = this._applyOrder(loads, "total").map((l) =>
        this._withLabel(l, "load_labels")
      );
      // I dispositivi "solo visualizzazione" non fanno più parte
      // dell'integrazione: vivono nella config della card
      // (extra_devices), e il loro valore si legge direttamente dallo
      // stato dell'entità scelta nell'editor, non dall'attributo 'loads'
      // del sensore (che ora contiene solo i carichi che sommano).
      const extraDevices = (this._config.extra_devices || []).map((d) => ({
        name: d.name,
        value: this._readPowerValue(d.entity),
      }));
      const displayLoads = this._applyOrder(extraDevices, "display");

      // L'ordine delle chip si decide esclusivamente dall'editor della
      // card (drag & drop lì, non più qui): sulla card le chip sono
      // statiche, quindi possiamo sempre rigenerare l'HTML senza doverci
      // preoccupare di interrompere un trascinamento in corso.
      this._loadsEl.innerHTML = `
        ${
          totalLoads.length
            ? `<div class="cec-loads-full" id="cec-loads-full">${totalLoads
                .map((l) => chip(l))
                .join("")}</div>`
            : ""
        }
        ${
          displayLoads.length
            ? `<div class="cec-loads-grid" id="cec-loads-grid">${displayLoads
                .map((l) => chip(l))
                .join("")}</div>`
            : ""
        }
      `;
    }

    const historyState = this._hass.states[this._config.history_entity];
    if (historyState) {
      const mesi = historyState.attributes?.mesi || [];
      this._mesi = mesi;
      const now = new Date();
      const ymCorr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
      const corr = mesi.find((m) => m.mese === ymCorr);
      if (corr && corr.insufficient_data) {
        this._monthKwhEl.textContent = "In attesa dati";
        this._monthKwhEl.style.fontSize = "12px";
        this._monthCostEl.textContent = "Riprova tra un paio di giorni";
      } else {
        this._monthKwhEl.style.fontSize = "";
        this._monthKwhEl.textContent = corr ? `${corr.kwh.toFixed(1)} kWh` : "-- kWh";
        this._monthCostEl.textContent =
          corr && corr.costo != null ? `~ € ${corr.costo.toFixed(2)}` : "";
      }

      // La barra mostra quanti giorni del mese sono già trascorsi: dà
      // un riferimento visivo di "a che punto siamo" nel ciclo di
      // fatturazione corrente, coerente con lo stile a barra già usato
      // altrove nella card.
      const daysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
      const dayProgress = Math.round((now.getDate() / daysInMonth) * 100);
      this._monthBarFill.style.width = `${Math.max(0, Math.min(100, dayProgress))}%`;

      const passatiCount = mesi.filter((m) => m.mese !== ymCorr).length;
      this._historyToggleLabel.textContent = this._historyOpen
        ? "Nascondi mesi precedenti"
        : `Mostra mesi precedenti (${passatiCount})`;

      if (this._historyOpen) this._renderHistory();
    }
  }

  _monthLabel(ym) {
    const nomi = [
      "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
      "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre",
    ];
    const [y, m] = ym.split("-");
    return `${nomi[parseInt(m, 10) - 1]} ${y}`;
  }

  _renderHistory() {
    if (!this._historyEl) return;
    const mesi = this._mesi || [];
    const now = new Date();
    const ymCorr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;

    const passati = mesi
      .filter((m) => m.mese !== ymCorr)
      .sort((a, b) => b.mese.localeCompare(a.mese));

    if (!passati.length) {
      this._historyEl.innerHTML = `<div class="cec-history-empty">Nessun mese precedente disponibile</div>`;
      return;
    }

    const maxKwh = Math.max(...passati.map((m) => Number(m.kwh) || 0), 0.001);

    this._historyEl.innerHTML = passati
      .map((m) => {
        const w = Math.max(0, Math.min(100, (Number(m.kwh) / maxKwh) * 100));
        return `
          <div class="cec-history-row">
            <div class="cec-history-line">
              <span class="cec-history-month">${this._monthLabel(m.mese)}</span>
              <span>
                <span class="cec-history-kwh">${Number(m.kwh).toFixed(1)} kWh</span>
                ${
                  m.costo != null
                    ? `<span class="cec-history-cost">~ € ${Number(m.costo).toFixed(2)}</span>`
                    : ""
                }
              </span>
            </div>
            <div class="cec-history-bar-track">
              <div class="cec-history-bar-fill" style="width:${w}%;"></div>
            </div>
          </div>
        `;
      })
      .join("");
  }
}

customElements.define("casa-energy-card", CasaEnergyCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "casa-energy-card",
  name: "Casa Energy Card",
  description:
    "Potenza istantanea, soglie di allerta, carichi monitorati e storico consumo mensile, letti dalle entità dell'integrazione Casa Energy. Permette anche di aggiungere dispositivi extra solo per visualizzazione, esclusi dal totale.",
  preview: false,
});

class CasaEnergyCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { ...config };
    if (this._suppressNextRender) {
      // Il round-trip config-changed → setConfig è innescato da noi
      // stessi (utente sta digitando in un campo di testo, es. il nome
      // di un dispositivo extra): saltare il rebuild del DOM evita di
      // far perdere il focus/cursore mentre si scrive.
      this._suppressNextRender = false;
      return;
    }
    this._render();
  }

  set hass(hass) {
    const hadHass = !!this._hass;
    this._hass = hass;
    this.querySelectorAll("ha-entity-picker").forEach((el) => {
      el.hass = hass;
    });
    // Se hass arriva dopo setConfig (o il primo render è avvenuto senza
    // hass ancora disponibile), la sezione "Ordine carichi principali"
    // dipende dallo stato di power_entity: serve un render completo la
    // prima volta che hass diventa disponibile, altrimenti quella
    // sezione resterebbe assente finché l'utente non tocca altro.
    if (!hadHass && this._config) {
      this._render();
    }
  }

  _fireChanged(preserveFocus = false) {
    this._suppressNextRender = preserveFocus;
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config: this._config },
        bubbles: true,
        composed: true,
      })
    );
  }

  _applyOrder(list, group) {
    const orderKey = group === "total" ? "load_order" : "display_load_order";
    const order = (this._config && this._config[orderKey]) || [];
    if (!order.length) return list;
    const byName = new Map(list.map((l) => [l.name, l]));
    const ordered = [];
    for (const name of order) {
      if (byName.has(name)) {
        ordered.push(byName.get(name));
        byName.delete(name);
      }
    }
    for (const remaining of byName.values()) ordered.push(remaining);
    return ordered;
  }

  _saveOrder(group, names) {
    const orderKey = group === "total" ? "load_order" : "display_load_order";
    this._config = { ...this._config, [orderKey]: names };
    this._fireChanged();
  }

  // Apre la schermata dedicata di rinomina per un singolo elemento.
  // group: "total" (carico principale, salva in load_labels, chiave =
  // nome originale) o "display" (dispositivo extra, chiave = indice
  // nell'array extra_devices, perché lì il nome PUÒ ripetersi — es. due
  // dispositivi aggiunti di recente con nome ancora vuoto — quindi il
  // nome da solo non basta a identificare la riga in modo univoco).
  _openRename(group, key) {
    this._renameTarget = { group, key };
    this._render();
  }

  _closeRename() {
    this._renameTarget = null;
    this._render();
  }

  _currentLabel(group, key) {
    if (group === "total") {
      const labels = (this._config && this._config.load_labels) || {};
      return labels[key] || key;
    }
    const device = (this._config.extra_devices || [])[key];
    return device ? device.name || "" : "";
  }

  _saveRename(group, key, newLabel, newEntity) {
    const trimmed = (newLabel || "").trim();

    if (group === "total") {
      if (!trimmed) return;
      const labels = { ...((this._config && this._config.load_labels) || {}) };
      labels[key] = trimmed;
      this._config = { ...this._config, load_labels: labels };
    } else {
      const devices = [...(this._config.extra_devices || [])];
      if (devices[key]) {
        devices[key] = {
          ...devices[key],
          name: trimmed,
          ...(newEntity !== undefined ? { entity: newEntity } : {}),
        };
        this._config = { ...this._config, extra_devices: devices };
      }
    }
    this._fireChanged();
  }

  // Schermata dedicata: sostituisce l'intera lista con un solo campo di
  // testo per l'elemento scelto, più Indietro/Salva. Usata sia per i
  // carichi principali sia per i dispositivi extra (stessa logica,
  // cambia solo dove va salvato il risultato).
  _renderRenameScreen(container) {
    const { group, key } = this._renameTarget;
    const currentLabel = this._currentLabel(group, key);
    const currentEntity =
      group === "display" ? ((this._config.extra_devices || [])[key]?.entity || "") : null;

    const backRow = document.createElement("div");
    backRow.style.cssText = "display:flex;align-items:center;gap:8px;margin-bottom:16px;";
    const backBtn = document.createElement("button");
    backBtn.type = "button";
    backBtn.textContent = "← Indietro";
    backBtn.style.cssText =
      "padding:6px 12px;border-radius:4px;border:1px solid var(--divider-color, #ccc);background:transparent;color:var(--primary-text-color, #000);font-size:13px;cursor:pointer;";
    backBtn.addEventListener("click", () => this._closeRename());
    backRow.appendChild(backBtn);
    container.appendChild(backRow);

    const heading = document.createElement("div");
    heading.textContent =
      group === "total" ? "Rinomina carico principale" : "Modifica dispositivo";
    heading.style.cssText = "font-weight:600;margin-bottom:4px;font-size:14px;";
    container.appendChild(heading);

    const subheading = document.createElement("div");
    subheading.textContent =
      group === "total"
        ? `Nome attuale: ${currentLabel}`
        : "Nome e sensore di potenza abbinato.";
    subheading.style.cssText = "font-size:12px;opacity:0.65;margin-bottom:12px;";
    container.appendChild(subheading);

    const input = document.createElement("input");
    input.type = "text";
    input.placeholder = "Nome";
    input.value = currentLabel === "(senza nome)" ? "" : currentLabel;
    input.style.cssText =
      "width:100%;padding:10px 8px;border-radius:4px;border:1px solid var(--divider-color, #ccc);background:var(--card-background-color, #fff);color:var(--primary-text-color, #000);font-size:14px;box-sizing:border-box;margin-bottom:12px;";
    container.appendChild(input);
    // Porta subito il focus sul campo: nel caso più comune (solo
    // rinomina) è l'unica cosa da fare, ha senso risparmiare un click.
    setTimeout(() => input.focus(), 0);

    // Il sensore di potenza si modifica solo qui per i dispositivi
    // extra: nella lista la riga mostra solo nome + azioni, per lo
    // stesso layout minimale dei carichi principali.
    let entityPicker = null;
    if (group === "display") {
      entityPicker = document.createElement("ha-entity-picker");
      entityPicker.label = "Sensore potenza";
      entityPicker.value = currentEntity || "";
      entityPicker.includeDomains = ["sensor"];
      entityPicker.includeDeviceClasses = ["power"];
      if (this._hass) entityPicker.hass = this._hass;
      entityPicker.style.cssText = "width:100%;margin-bottom:16px;display:block;";
      container.appendChild(entityPicker);
    }

    const saveBtn = document.createElement("button");
    saveBtn.type = "button";
    saveBtn.textContent = "Salva";
    saveBtn.style.cssText =
      "padding:8px 18px;border-radius:4px;border:none;background:var(--primary-color, #03a9f4);color:#fff;font-size:14px;font-weight:500;cursor:pointer;";
    const commit = () => {
      const entityValue = entityPicker ? entityPicker.value : undefined;
      this._saveRename(group, key, input.value, entityValue);
      this._closeRename();
    };
    saveBtn.addEventListener("click", commit);
    input.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") commit();
    });
    container.appendChild(saveBtn);
  }

  // Righe riordinabili via drag, in stile HA nativo: maniglia "☰" a
  // sinistra, contenuto al centro, azioni opzionali a destra. Usata sia
  // per l'elenco dei carichi principali (sola lettura, solo riordino)
  // sia per i dispositivi extra (con campi editabili annessi via
  // extraContent). Il riordino avviene qui nell'editor, non più con
  // drag sulle chip della card.
  _makeSortableList(items, group, renderContent) {
    const list = document.createElement("div");
    list.style.cssText = "display:flex;flex-direction:column;gap:6px;";

    let draggedRow = null;

    items.forEach((item, index) => {
      const row = document.createElement("div");
      row.dataset.name = item.name;
      row.style.cssText =
        "display:flex;align-items:center;gap:8px;padding:6px;border-radius:8px;background:rgba(127,127,127,0.06);";

      const handle = document.createElement("span");
      handle.textContent = "☰";
      handle.draggable = true;
      handle.title = "Trascina per riordinare";
      handle.style.cssText =
        "cursor:grab;opacity:0.5;font-size:16px;flex-shrink:0;user-select:none;padding:4px;";

      handle.addEventListener("dragstart", (e) => {
        draggedRow = row;
        row.style.opacity = "0.4";
        e.dataTransfer.effectAllowed = "move";
      });
      row.addEventListener("dragend", () => {
        row.style.opacity = "";
        if (draggedRow !== row) return;
        draggedRow = null;
        const names = Array.from(list.children).map((r) => r.dataset.name);
        this._saveOrder(group, names);
      });
      row.addEventListener("dragover", (e) => {
        e.preventDefault();
        if (!draggedRow || draggedRow === row) return;
        const rect = row.getBoundingClientRect();
        const before = e.clientY < rect.top + rect.height / 2;
        list.insertBefore(draggedRow, before ? row : row.nextSibling);
      });

      row.appendChild(handle);
      renderContent(row, item, index);
      list.appendChild(row);
    });

    return list;
  }

  // Pulsante "✎" usato su ogni riga per aprire la schermata di rinomina
  // dedicata. Nativo (non ha-icon-button) per la stessa ragione di
  // affidabilità cross-versione già discussa per gli altri controlli.
  _makeRenameBtn(group, key) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = "✎";
    btn.title = "Rinomina";
    btn.style.cssText =
      "flex-shrink:0;width:32px;height:32px;border-radius:50%;border:none;background:rgba(127,127,127,0.15);color:var(--primary-text-color, #000);font-size:14px;cursor:pointer;";
    btn.addEventListener("click", () => this._openRename(group, key));
    return btn;
  }

  _render() {
    this.innerHTML = "";
    const container = document.createElement("div");
    container.style.padding = "8px";

    if (this._renameTarget) {
      this._renderRenameScreen(container);
      this.appendChild(container);
      return;
    }

    const makeRow = (label, key) => {
      const row = document.createElement("div");
      row.style.marginBottom = "12px";
      const picker = document.createElement("ha-entity-picker");
      picker.label = label;
      picker.value = this._config[key] || "";
      picker.includeDomains = ["sensor"];
      if (this._hass) picker.hass = this._hass;
      picker.style.width = "100%";
      picker.addEventListener("value-changed", (ev) => {
        ev.stopPropagation();
        this._config = { ...this._config, [key]: ev.detail.value };
        this._fireChanged();
      });
      row.appendChild(picker);
      return row;
    };

    container.appendChild(makeRow("Sensore potenza istantanea", "power_entity"));
    container.appendChild(makeRow("Sensore storico consumi mensili", "history_entity"));

    // --- Ordine carichi principali ---
    // Sola lettura qui: i carichi (nome + sensore) sono decisi
    // dall'integrazione (Configura → sensori energy), qui si può solo
    // scegliere in che ordine mostrarli in card.
    const powerState = this._hass && this._config.power_entity
      ? this._hass.states[this._config.power_entity]
      : null;
    const mainLoads = (powerState && powerState.attributes && powerState.attributes.loads) || [];

    if (mainLoads.length) {
      const loadsHeading = document.createElement("div");
      loadsHeading.textContent = "Ordine carichi principali";
      loadsHeading.style.cssText = "font-weight:600;margin:16px 0 4px;font-size:14px;";
      container.appendChild(loadsHeading);

      const loadsSubheading = document.createElement("div");
      loadsSubheading.textContent =
        "Trascina per cambiare l'ordine con cui compaiono in card. Per aggiungere o rimuovere un carico, usa Configura sull'integrazione.";
      loadsSubheading.style.cssText = "font-size:12px;opacity:0.65;margin-bottom:10px;";
      container.appendChild(loadsSubheading);

      // _applyOrder e la maniglia di drag lavorano sul nome ORIGINALE
      // (item.name), non sulla label rinominata: così l'ordine salvato
      // resta valido anche dopo una rinomina, e il pulsante ✎ passa
      // sempre la chiave corretta a _openRename/_saveRename.
      const orderedLoads = this._applyOrder(mainLoads, "total");
      const loadsList = this._makeSortableList(orderedLoads, "total", (row, item) => {
        const name = document.createElement("span");
        name.textContent = this._currentLabel("total", item.name);
        name.style.cssText = "flex:1;font-size:14px;";
        row.appendChild(name);
        row.appendChild(this._makeRenameBtn("total", item.name));
      });
      container.appendChild(loadsList);
    }

    // --- Dispositivi solo visualizzazione (extra_devices) ---
    // Non fanno parte dell'integrazione: vivono qui nella config della
    // card, non entrano mai nel calcolo del totale, servono solo per
    // essere mostrati come chip separati.
    const heading = document.createElement("div");
    heading.textContent = "Dispositivi solo visualizzazione";
    heading.style.cssText = "font-weight:600;margin:16px 0 4px;font-size:14px;";
    container.appendChild(heading);

    const subheading = document.createElement("div");
    subheading.textContent =
      "Mostrati come voce a parte in card, esclusi dal totale della potenza istantanea. Trascina per riordinare.";
    subheading.style.cssText = "font-size:12px;opacity:0.65;margin-bottom:10px;";
    container.appendChild(subheading);

    const extraDevices = this._applyOrder(this._config.extra_devices || [], "display");

    const devicesList = this._makeSortableList(extraDevices, "display", (row, device) => {
      // L'indice nell'array originale (non ordinato) serve per aggiornare
      // correttamente extra_devices quando l'utente modifica un campo;
      // l'ordine di visualizzazione è invece gestito da display_load_order.
      const findOriginalIndex = () =>
        (this._config.extra_devices || []).findIndex((d) => d === device);

      const nameLabel = document.createElement("span");
      nameLabel.textContent = device.name || "(senza nome)";
      nameLabel.style.cssText = "flex:1;font-size:14px;";
      row.appendChild(nameLabel);
      // La chiave di rinomina è l'indice nell'array extra_devices (non
      // il nome): due dispositivi appena aggiunti hanno entrambi nome
      // vuoto, quindi solo la posizione li distingue in modo univoco.
      // La schermata di rinomina gestisce anche il sensore abbinato, non
      // solo il nome: stesso pulsante ✎, stessa forma della lista, ma il
      // contenuto della schermata si adatta al gruppo "display".
      row.appendChild(this._makeRenameBtn("display", findOriginalIndex()));

      // Pulsante nativo invece di ha-icon-button, stessa motivazione di
      // affidabilità cross-versione già discussa altrove. Resta sulla
      // riga (non nella schermata di rinomina) perché rimuovere è
      // un'azione distruttiva e immediata, diversa dal modificare.
      const removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.textContent = "✕";
      removeBtn.title = "Rimuovi dispositivo";
      removeBtn.style.cssText =
        "flex-shrink:0;width:32px;height:32px;border-radius:50%;border:none;background:rgba(127,127,127,0.15);color:var(--primary-text-color, #000);font-size:14px;cursor:pointer;";
      removeBtn.addEventListener("click", () => {
        const idx = findOriginalIndex();
        if (idx < 0) return;
        const updated = (this._config.extra_devices || []).filter((_, i) => i !== idx);
        this._config = { ...this._config, extra_devices: updated };
        this._fireChanged();
      });

      row.appendChild(removeBtn);
    });

    container.appendChild(devicesList);

    // Pulsante nativo invece di mwc-button, stessa motivazione.
    const addBtn = document.createElement("button");
    addBtn.type = "button";
    addBtn.textContent = "+ Aggiungi dispositivo";
    addBtn.style.cssText =
      "margin-top:10px;padding:8px 14px;border-radius:4px;border:1px solid var(--primary-color, #03a9f4);background:transparent;color:var(--primary-color, #03a9f4);font-size:14px;font-weight:500;cursor:pointer;";
    addBtn.addEventListener("click", () => {
      const updated = [...(this._config.extra_devices || []), { name: "", entity: "" }];
      this._config = { ...this._config, extra_devices: updated };
      this._fireChanged();
    });
    container.appendChild(addBtn);

    this.appendChild(container);
  }
}

customElements.define("casa-energy-card-editor", CasaEnergyCardEditor);
