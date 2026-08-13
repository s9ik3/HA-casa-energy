"""Integrazione Casa Energy: storico consumi + potenza istantanea."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_ENERGY_SENSORS,
    CONF_EXTRA_CHARGES_PER_KWH,
    CONF_FIXED_MONTHLY_COST,
    CONF_PRICE_PER_KWH,
    CONF_VAT_RATE,
    DOMAIN,
    UPDATE_INTERVAL_MINUTES,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Chiamato quando l'utente completa il config_flow (o al riavvio, per
    ogni istanza già configurata). Crea il coordinator che calcola
    periodicamente lo storico consumi mensile dalle statistiche HA."""

    coordinator = MonthlyEnergyCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Richiamato quando l'utente salva le Opzioni: ricarica l'integrazione
    così i nuovi valori (tariffa, soglie, sensori) vengono applicati subito."""
    await hass.config_entries.async_reload(entry.entry_id)


class MonthlyEnergyCoordinator(DataUpdateCoordinator):
    """Calcola periodicamente lo storico mensile dei consumi (kWh + costo
    stimato) leggendo le statistiche a lungo termine già registrate da
    Home Assistant per i sensori energy configurati.

    Sostituisce la query SQL raw dell'esempio YAML con l'API statistics
    di Home Assistant: più portabile (funziona identicamente su SQLite,
    MariaDB, PostgreSQL) e non richiede l'integrazione SQL separata.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(minutes=UPDATE_INTERVAL_MINUTES),
        )
        self.entry = entry

    async def _async_update_data(self) -> dict:
        from homeassistant.components.recorder import get_instance
        from homeassistant.components.recorder.statistics import (
            statistics_during_period,
        )

        data = self.entry.data
        energy_sensors: list[str] = data.get(CONF_ENERGY_SENSORS, [])
        if not energy_sensors:
            return {"mesi": []}

        price = float(data.get(CONF_PRICE_PER_KWH, 0.0))
        fixed_cost = float(data.get(CONF_FIXED_MONTHLY_COST, 0.0))
        extra = float(data.get(CONF_EXTRA_CHARGES_PER_KWH, 0.0))
        vat = float(data.get(CONF_VAT_RATE, 0.0))

        # Vai indietro fino a 13 mesi fa per avere storico + mese corrente
        start = (datetime.now() - timedelta(days=400)).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )

        recorder_instance = get_instance(self.hass)
        stats = await recorder_instance.async_add_executor_job(
            statistics_during_period,
            self.hass,
            start,
            None,
            set(energy_sensors),
            "month",
            None,
            {"sum"},
        )

        # Aggrega per mese sommando i delta di tutti i sensori configurati
        monthly_kwh: dict[str, float] = {}
        for sensor_id, entries in stats.items():
            prev_sum: float | None = None
            for entry_stat in entries:
                start_ts = entry_stat.get("start")
                total = entry_stat.get("sum")
                if total is None or start_ts is None:
                    continue
                month_key = datetime.fromtimestamp(start_ts).strftime("%Y-%m")
                if prev_sum is not None:
                    delta = max(0.0, total - prev_sum)
                    monthly_kwh[month_key] = monthly_kwh.get(month_key, 0.0) + delta
                prev_sum = total

        months = []
        for month_key in sorted(monthly_kwh.keys()):
            kwh = round(monthly_kwh[month_key], 2)
            cost = round((kwh * price) + (kwh * extra) + fixed_cost, 2)
            cost_with_vat = round(cost * (1 + vat / 100), 2)
            months.append({"mese": month_key, "kwh": kwh, "costo": cost_with_vat})

        return {"mesi": months}
