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
          .cec-load-chip {
            padding: 8px 10px;
            border-radius: 12px;
            background: rgba(127,127,127,0.08);
            display: flex;
            justify-content: space-between;
            font-size: 12px;
          }
          .cec-month-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 12px;
            padding-top: 10px;
            border-top: 1px solid rgba(127,127,127,0.15);
          }
          .cec-month-kwh {
            font-weight: 800;
            font-size: 15px;
          }
          .cec-month-cost {
            font-size: 11px;
            opacity: 0.65;
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
        <div class="cec-month-row">
          <span style="font-size:12px;opacity:0.7;">Mese corrente</span>
          <div style="text-align:right;">
            <div class="cec-month-kwh" id="cec-month-kwh">-- kWh</div>
            <div class="cec-month-cost" id="cec-month-cost"></div>
          </div>
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
  }

  _statusColor(status) {
    if (status === "critical") return "#e53935";
    if (status === "warning") return "#fb8c00";
    if (status === "ok") return "#43a047";
    return "var(--disabled-text-color, #888)";
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
      this._loadsEl.innerHTML = loads
        .map(
          (l) => `
          <div class="cec-load-chip">
            <span>${l.name}</span>
            <span style="font-weight:700;color:${color};">${
              l.value == null ? "N/A" : Math.round(l.value) + " W"
            }</span>
          </div>
        `
        )
        .join("");
    }

    const historyState = this._hass.states[this._config.history_entity];
    if (historyState) {
      const mesi = historyState.attributes?.mesi || [];
      const now = new Date();
      const ymCorr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
      const corr = mesi.find((m) => m.mese === ymCorr);
      this._monthKwhEl.textContent = corr ? `${corr.kwh.toFixed(1)} kWh` : "-- kWh";
      this._monthCostEl.textContent =
        corr && corr.costo != null ? `~ € ${corr.costo.toFixed(2)}` : "";
    }
  }
}

customElements.define("casa-energy-card", CasaEnergyCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "casa-energy-card",
  name: "Casa Energy Card",
  description:
    "Potenza istantanea, soglie di allerta, carichi monitorati e storico consumo mensile, letti dalle entità dell'integrazione Casa Energy.",
  preview: false,
});

class CasaEnergyCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this.querySelectorAll("ha-entity-picker").forEach((el) => {
      el.hass = hass;
    });
  }

  _fireChanged() {
    this._suppressNextRender = true;
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config: this._config },
        bubbles: true,
        composed: true,
      })
    );
  }

  _render() {
    this.innerHTML = "";
    const container = document.createElement("div");
    container.style.padding = "8px";

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
    this.appendChild(container);
  }
}

customElements.define("casa-energy-card-editor", CasaEnergyCardEditor);
