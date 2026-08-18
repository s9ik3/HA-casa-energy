"""Gestione delle tariffe "congelate" sui mesi già chiusi.

Quando l'utente modifica la tariffa dalle Opzioni, i mesi già passati non
devono ricalcolare il loro costo con i nuovi parametri: la bolletta di
gennaio non cambia se a marzo aggiorno il prezzo del kWh. Per ottenere
questo, ogni volta che la tariffa cambia "congeliamo" (salviamo) la
tariffa PRECEDENTE su tutti i mesi già chiusi che non hanno ancora una
tariffa congelata propria. Il mese in corso non viene mai congelato in
questo momento: lo sarà solo alla PROSSIMA modifica di tariffa, quando
sarà a sua volta un mese passato.

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
    CONF_LINE_ITEM_MONTH_FROM,
    CONF_LINE_ITEM_MONTH_TO,
    CONF_LINE_ITEM_TYPE,
    CONF_LINE_ITEM_VALUE,
    CONF_PRICE_PER_KWH,
    CONF_TARIFF_LINE_ITEMS,
    CONF_VAT_RATE,
    LINE_ITEM_TYPE_PER_KWH,
)

_STORAGE_VERSION = 1
_STORAGE_KEY_PREFIX = "casa_energy_frozen_tariffs"


class FrozenTariffStore:
    """Wrapper sopra homeassistant.helpers.storage.Store per le tariffe
    congelate di una singola config entry."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store = Store(
            hass, _STORAGE_VERSION, f"{_STORAGE_KEY_PREFIX}_{entry_id}"
        )
        self._data: dict[str, dict] | None = None

    async def async_load(self) -> dict[str, dict]:
        """Carica (con cache in memoria) le tariffe congelate: mappa
        mese ("YYYY-MM") -> {price_per_kwh, fixed_monthly_cost,
        extra_charges_per_kwh, vat_rate}."""
        if self._data is None:
            stored = await self._store.async_load()
            self._data = stored.get("months", {}) if stored else {}
        return self._data

    async def async_freeze_previous_tariff(
        self,
        closed_months: list[str],
        previous_tariff: dict,
    ) -> None:
        """Congela previous_tariff su tutti i mesi in closed_months che
        non hanno ancora una tariffa congelata propria. Chiamata quando
        l'utente cambia la tariffa: previous_tariff è quella appena
        sostituita (non quella nuova), perché è quella sotto cui i mesi
        passati sono realmente stati fatturati."""
        data = await self.async_load()
        changed = False
        for month_key in closed_months:
            if month_key not in data:
                data[month_key] = dict(previous_tariff)
                changed = True
        if changed:
            await self._store.async_save({"months": data})

    async def async_reset(self) -> None:
        """Rimuove tutte le tariffe congelate: i mesi passati torneranno
        a essere ricalcolati con la tariffa corrente, finché non si
        congela di nuovo qualcosa con una futura modifica di tariffa."""
        self._data = {}
        await self._store.async_save({"months": {}})

    def get_frozen_tariff(self, month_key: str) -> dict | None:
        """Versione sincrona per l'uso nel coordinator, dopo che
        async_load è già stato chiamato almeno una volta."""
        if self._data is None:
            return None
        return self._data.get(month_key)


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
    ciascuna secondo il proprio tipo (per kWh o fissa mensile), il
    proprio range di mesi applicabile, e la propria scelta se applicarci
    sopra l'IVA oppure no — necessario perché in bolletta capita di avere
    voci non soggette a IVA (es. un contributo una tantum) mescolate a
    voci che invece lo sono."""
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
        amount = value * kwh if item.get(CONF_LINE_ITEM_TYPE) == LINE_ITEM_TYPE_PER_KWH else value

        if item.get(CONF_LINE_ITEM_APPLY_VAT, True):
            vat_taxable_extra += amount
        else:
            vat_free_extra += amount

    taxable_total = base_subtotal + vat_taxable_extra
    cost_with_vat = taxable_total * (1 + vat / 100) + vat_free_extra
    return round(cost_with_vat, 2)
