"""Gestione dello storico delle tariffe per periodo.

Le componenti della tariffa elettrica italiana (Cdispd, oneri di sistema
ARIM/ASOS, ecc.) cambiano periodicamente, non solo quando l'utente decide
di aggiornarle: ogni bolletta può avere coefficienti diversi da quella
precedente. Per questo la tariffa attiva in configurazione (quella
"corrente") NON deve mai retroagire sui mesi già chiusi — ma un singolo
blob "congelato" per tutto il passato non basta, perché ogni mese chiuso
può aver avuto una tariffa diversa dagli altri (es. giugno con una
tariffa, luglio con un'altra, entrambi già chiusi rispetto ad agosto).

Lo storico è quindi una lista di PERIODI, ciascuno con un mese iniziale,
un mese finale, e la tariffa in vigore in quel periodo. Quando l'utente
salva una tariffa diversa da quella attualmente attiva, gli si chiede
esplicitamente a quale periodo appartenesse la tariffa appena sostituita
(es. "giugno 2026 - giugno 2026"), e quel periodo viene aggiunto allo
storico. Il coordinator, per ogni mese, cerca nello storico il periodo
che lo contiene; se non lo trova in nessun periodo, usa la tariffa
corrente (comportamento per il mese in corso e per mesi non ancora
coperti da nessun periodo storico).

I dati sono persistiti tramite lo Store di Home Assistant (non dentro
ConfigEntry.data, che è pensato per configurazione utente, non per dati
derivati che crescono nel tempo), uno store per ogni config entry.
"""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    CONF_EXTRA_CHARGES_PER_KWH,
    CONF_FIXED_MONTHLY_COST,
    CONF_LINE_ITEM_APPLY_VAT,
    CONF_LINE_ITEM_ENGAGED_POWER_KW,
    CONF_LINE_ITEM_MONTH_FROM,
    CONF_LINE_ITEM_MONTH_TO,
    CONF_LINE_ITEM_TYPE,
    CONF_LINE_ITEM_VALUE,
    CONF_PRICE_PER_KWH,
    CONF_TARIFF_LINE_ITEMS,
    CONF_VAT_RATE,
    LINE_ITEM_TYPE_PER_KW_POWER,
    LINE_ITEM_TYPE_PER_KWH,
)

_STORAGE_VERSION = 2
_STORAGE_KEY_PREFIX = "casa_energy_frozen_tariffs"


def _month_key_to_ordinal(month_key: str) -> int:
    """Converte 'YYYY-MM' in un intero ordinabile (anno*12+mese), per
    confrontare facilmente se un mese cade dentro un range."""
    year, month = month_key.split("-")
    return int(year) * 12 + int(month)


class FrozenTariffStore:
    """Wrapper sopra homeassistant.helpers.storage.Store per lo storico
    delle tariffe per periodo di una singola config entry."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store = Store(
            hass, _STORAGE_VERSION, f"{_STORAGE_KEY_PREFIX}_{entry_id}"
        )
        self._periods: list[dict] | None = None

    async def async_load(self) -> list[dict]:
        """Carica (con cache in memoria) lo storico dei periodi: ciascuno
        con month_from, month_to, tariff."""
        if self._periods is None:
            stored = await self._store.async_load()
            self._periods = stored.get("periods", []) if stored else []
        return self._periods

    async def async_add_period(
        self, month_from: str, month_to: str, tariff: dict
    ) -> None:
        """Aggiunge un nuovo periodo storico con la tariffa indicata,
        esplicitamente delimitato da month_from a month_to (entrambi
        'YYYY-MM'). Non deduplica né unisce automaticamente con periodi
        esistenti: la responsabilità di indicare il periodo corretto è
        dell'utente, tramite lo step apposito nel config_flow."""
        periods = await self.async_load()
        periods.append(
            {
                "month_from": month_from,
                "month_to": month_to,
                "tariff": tariff,
            }
        )
        await self._store.async_save({"periods": periods})

    async def async_reset(self) -> None:
        """Rimuove tutto lo storico dei periodi: ogni mese passato
        tornerà a essere ricalcolato con la tariffa corrente, finché non
        si aggiungono di nuovo periodi storici con future modifiche di
        tariffa."""
        self._periods = []
        await self._store.async_save({"periods": []})

    def get_frozen_tariff(self, month_key: str) -> dict | None:
        """Versione sincrona per l'uso nel coordinator, dopo che
        async_load è già stato chiamato almeno una volta. Cerca il primo
        periodo storico che contiene month_key; se più periodi si
        sovrappongono (non dovrebbe succedere se l'utente li inserisce
        correttamente, ma non lo impediamo), vince il più recentemente
        aggiunto (l'ultimo della lista)."""
        if self._periods is None:
            return None
        month_ord = _month_key_to_ordinal(month_key)
        for period in reversed(self._periods):
            from_ord = _month_key_to_ordinal(period["month_from"])
            to_ord = _month_key_to_ordinal(period["month_to"])
            if from_ord <= month_ord <= to_ord:
                return period["tariff"]
        return None


def tariff_from_entry_data(data: dict) -> dict:
    """Estrae i parametri di tariffa da ConfigEntry.data in un
    dizionario compatto, comodo da confrontare e da salvare come
    "congelato": i quattro campi semplici più le voci extra (se
    presenti), copiate per intero così ogni mese congelato ricorda
    esattamente quali voci erano attive quando è stato calcolato."""
    return {
        CONF_PRICE_PER_KWH: float(data.get(CONF_PRICE_PER_KWH, 0.0)),
        CONF_FIXED_MONTHLY_COST: float(data.get(CONF_FIXED_MONTHLY_COST, 0.0)),
        CONF_EXTRA_CHARGES_PER_KWH: float(data.get(CONF_EXTRA_CHARGES_PER_KWH, 0.0)),
        CONF_VAT_RATE: float(data.get(CONF_VAT_RATE, 0.0)),
        CONF_TARIFF_LINE_ITEMS: list(data.get(CONF_TARIFF_LINE_ITEMS, [])),
    }


def tariffs_differ(a: dict, b: dict) -> bool:
    """Confronto tollerante sui quattro campi numerici semplici (evita
    falsi positivi per errori di arrotondamento float), più un confronto
    diretto sulla lista delle voci extra: qualunque differenza lì
    (aggiunta, rimozione, modifica di una voce) conta come cambio
    tariffa a tutti gli effetti."""
    keys = (
        CONF_PRICE_PER_KWH,
        CONF_FIXED_MONTHLY_COST,
        CONF_EXTRA_CHARGES_PER_KWH,
        CONF_VAT_RATE,
    )
    if any(abs(float(a.get(k, 0.0)) - float(b.get(k, 0.0))) > 1e-9 for k in keys):
        return True
    return a.get(CONF_TARIFF_LINE_ITEMS, []) != b.get(CONF_TARIFF_LINE_ITEMS, [])


def calculate_cost(kwh: float, month_key: str, tariff: dict) -> float:
    """Calcola il costo di un mese a partire da kWh consumati, il mese
    (per filtrare le voci extra stagionali) e un dizionario tariffa nel
    formato prodotto da tariff_from_entry_data.

    Replica la struttura di una bolletta reale a più voci: i quattro
    campi semplici (prezzo energia, costi fissi, oneri, IVA) restano il
    calcolo di base, sempre soggetti a IVA — esattamente come prima
    dell'introduzione delle voci extra, per compatibilità con chi non le
    usa. Le voci extra (tariff_line_items) si sommano al subtotale
    ciascuna secondo il proprio tipo (per kWh, fissa mensile, o per kW di
    potenza impegnata — quest'ultima per componenti calcolate sulla
    potenza del contratto anziché sul consumo, come la quota potenza del
    trasporto), il proprio range di mesi applicabile, e la propria scelta
    se applicarci sopra l'IVA oppure no — necessario perché in bolletta
    capita di avere voci non soggette a IVA (es. un contributo una
    tantum) mescolate a voci che invece lo sono."""
    price = tariff.get(CONF_PRICE_PER_KWH, 0.0)
    fixed_cost = tariff.get(CONF_FIXED_MONTHLY_COST, 0.0)
    extra = tariff.get(CONF_EXTRA_CHARGES_PER_KWH, 0.0)
    vat = tariff.get(CONF_VAT_RATE, 0.0)

    base_subtotal = (kwh * price) + (kwh * extra) + fixed_cost

    vat_taxable_extra = 0.0
    vat_free_extra = 0.0
    month_num = int(month_key.split("-")[1]) if "-" in month_key else None

    for item in tariff.get(CONF_TARIFF_LINE_ITEMS, []):
        month_from = item.get(CONF_LINE_ITEM_MONTH_FROM)
        month_to = item.get(CONF_LINE_ITEM_MONTH_TO)
        if month_from and month_to and month_num is not None:
            in_range = (
                month_from <= month_num <= month_to
                if month_from <= month_to
                # Range che attraversa il cambio d'anno, es. da novembre (11)
                # a febbraio (2): l'intervallo "avvolge" dicembre/gennaio.
                else month_num >= month_from or month_num <= month_to
            )
            if not in_range:
                continue

        value = float(item.get(CONF_LINE_ITEM_VALUE, 0.0))
        item_type = item.get(CONF_LINE_ITEM_TYPE)
        if item_type == LINE_ITEM_TYPE_PER_KWH:
            amount = value * kwh
        elif item_type == LINE_ITEM_TYPE_PER_KW_POWER:
            engaged_power = float(item.get(CONF_LINE_ITEM_ENGAGED_POWER_KW, 0.0))
            amount = value * engaged_power
        else:
            amount = value

        if item.get(CONF_LINE_ITEM_APPLY_VAT, True):
            vat_taxable_extra += amount
        else:
            vat_free_extra += amount

    taxable_total = base_subtotal + vat_taxable_extra
    cost_with_vat = taxable_total * (1 + vat / 100) + vat_free_extra
    return round(cost_with_vat, 2)
