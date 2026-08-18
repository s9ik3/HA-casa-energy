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
    CONF_PRICE_PER_KWH,
    CONF_VAT_RATE,
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
    """Estrae i quattro parametri di tariffa da ConfigEntry.data in un
    dizionario compatto, comodo da confrontare e da salvare come
    "congelato"."""
    return {
        CONF_PRICE_PER_KWH: float(data.get(CONF_PRICE_PER_KWH, 0.0)),
        CONF_FIXED_MONTHLY_COST: float(data.get(CONF_FIXED_MONTHLY_COST, 0.0)),
        CONF_EXTRA_CHARGES_PER_KWH: float(data.get(CONF_EXTRA_CHARGES_PER_KWH, 0.0)),
        CONF_VAT_RATE: float(data.get(CONF_VAT_RATE, 0.0)),
    }


def tariffs_differ(a: dict, b: dict) -> bool:
    """Confronto numerico tollerante: evita falsi positivi per errori di
    arrotondamento float quando in realtà l'utente non ha cambiato nulla
    (es. riapre le Opzioni e le richiude senza toccare i valori)."""
    keys = (
        CONF_PRICE_PER_KWH,
        CONF_FIXED_MONTHLY_COST,
        CONF_EXTRA_CHARGES_PER_KWH,
        CONF_VAT_RATE,
    )
    return any(abs(float(a.get(k, 0.0)) - float(b.get(k, 0.0))) > 1e-9 for k in keys)
