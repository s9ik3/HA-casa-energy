"""Integrazione Casa Energy: storico consumi + potenza istantanea."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
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

CARD_URL_PATH = "/casa_energy_static/casa-energy-card.js"
CARD_JS_FILENAME = "casa-energy-card.js"
_INSTANCES_KEY = "instance_count"
_RESOURCE_ID_KEY = "lovelace_resource_id"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Chiamato quando l'utente completa il config_flow (o al riavvio, per
    ogni istanza già configurata). Crea il coordinator che calcola
    periodicamente lo storico consumi mensile dalle statistiche HA, e
    (solo alla prima istanza) registra la card frontend come risorsa
    Lovelace automatica."""

    coordinator = MonthlyEnergyCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator
    hass.data[DOMAIN].setdefault(_INSTANCES_KEY, 0)
    hass.data[DOMAIN][_INSTANCES_KEY] += 1

    if hass.data[DOMAIN][_INSTANCES_KEY] == 1:
        await _async_register_card_resource(hass)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
        hass.data[DOMAIN][_INSTANCES_KEY] -= 1

        # Rimuovi la risorsa Lovelace solo quando l'ULTIMA istanza viene
        # disinstallata: se l'utente ha configurato più contatori/case,
        # rimuoverne uno non deve rompere la card per gli altri.
        if hass.data[DOMAIN][_INSTANCES_KEY] <= 0:
            await _async_unregister_card_resource(hass)
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Chiamato quando l'utente elimina definitivamente l'istanza dal
    pannello (non solo disabilita/scarica, ma cancella). A questo punto
    async_unload_entry è già stato eseguito da Home Assistant; qui ci
    limitiamo a un controllo di sicurezza extra, nel caso in cui restasse
    comunque una risorsa orfana (es. se l'unload era fallito silenziosamente)."""
    remaining = [
        e for e in hass.config_entries.async_entries(DOMAIN) if e.entry_id != entry.entry_id
    ]
    if not remaining:
        await _async_unregister_card_resource(hass)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Richiamato quando l'utente salva le Opzioni: ricarica l'integrazione
    così i nuovi valori (tariffa, soglie, sensori) vengono applicati subito."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_register_card_resource(hass: HomeAssistant) -> None:
    """Serve casa-energy-card.js come file statico e la registra come
    risorsa Lovelace, così la card compare nel picker 'Aggiungi card'
    senza che l'utente debba configurare nulla manualmente.

    Se qualcosa fallisce (es. dashboard non ancora in modalità storage,
    lovelace non pronto), viene solo loggato un avviso: l'integrazione
    resta comunque pienamente funzionante, l'utente può sempre aggiungere
    la risorsa a mano se l'auto-registrazione non riesce.
    """
    www_path = Path(__file__).parent / "www" / CARD_JS_FILENAME
    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL_PATH, str(www_path), cache_headers=False)]
        )
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Impossibile registrare il file statico della card: %s", err)
        return

    try:
        resource_storage = hass.data.get("lovelace_resources")
        if resource_storage is None:
            _LOGGER.info(
                "Dashboard Lovelace non in modalità storage: aggiungi la "
                "risorsa %s manualmente da Impostazioni → Dashboard → Risorse.",
                CARD_URL_PATH,
            )
            return

        existing = [
            r for r in resource_storage.async_items() if r["url"] == CARD_URL_PATH
        ]
        if existing:
            hass.data[DOMAIN][_RESOURCE_ID_KEY] = existing[0]["id"]
            return

        item = await resource_storage.async_create_item(
            {"res_type": "module", "url": CARD_URL_PATH}
        )
        hass.data[DOMAIN][_RESOURCE_ID_KEY] = item["id"]
        _LOGGER.info("Casa Energy Card registrata automaticamente come risorsa Lovelace")
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning(
            "Impossibile registrare automaticamente la risorsa Lovelace (%s). "
            "Aggiungila manualmente: URL %s, tipo Modulo JavaScript.",
            err,
            CARD_URL_PATH,
        )


async def _async_unregister_card_resource(hass: HomeAssistant) -> None:
    """Rimuove la risorsa Lovelace registrata automaticamente, così
    disinstallare l'integrazione non lascia riferimenti orfani a un file
    JS che non esiste più (che causerebbe errori di caricamento nel
    dashboard finché non rimossi manualmente)."""
    resource_id = hass.data.get(DOMAIN, {}).pop(_RESOURCE_ID_KEY, None)
    if not resource_id:
        return
    try:
        resource_storage = hass.data.get("lovelace_resources")
        if resource_storage is not None:
            await resource_storage.async_delete_item(resource_id)
            _LOGGER.info("Casa Energy Card rimossa dalle risorse Lovelace")
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning(
            "Impossibile rimuovere automaticamente la risorsa Lovelace (%s). "
            "Rimuovila manualmente da Impostazioni → Dashboard → Risorse se necessario.",
            err,
        )


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
            "day",
            None,
            {"sum"},
        )

        # Aggrega per mese sommando i delta di tutti i sensori configurati.
        # Granularità giornaliera. Il riferimento (baseline) per calcolare
        # il delta di ogni giorno è il valore ASSOLUTO più basso mai
        # registrato per quel sensore in tutto il periodo raccolto (non solo
        # nel mese corrente): così anche il primissimo giorno disponibile
        # produce un consumo sensato ("quanto consumato da quando esiste
        # il sensore ad oggi"), invece di richiedere che sia già trascorso
        # un giorno intero di confronto dentro lo stesso mese.
        monthly_kwh: dict[str, float] = {}
        for sensor_id, entries in stats.items():
            daily_points: list[tuple[str, float]] = []
            for entry_stat in entries:
                start_ts = entry_stat.get("start")
                total = entry_stat.get("sum")
                if total is None or start_ts is None:
                    continue
                month_key = datetime.fromtimestamp(start_ts).strftime("%Y-%m")
                daily_points.append((month_key, total))

            if not daily_points:
                continue

            baseline = min(v for _, v in daily_points)
            prev_value = baseline
            for month_key, value in daily_points:
                delta = max(0.0, value - prev_value)
                monthly_kwh[month_key] = monthly_kwh.get(month_key, 0.0) + delta
                prev_value = value

        months = []
        for month_key in sorted(monthly_kwh.keys()):
            kwh = round(monthly_kwh[month_key], 2)
            cost = round((kwh * price) + (kwh * extra) + fixed_cost, 2)
            cost_with_vat = round(cost * (1 + vat / 100), 2)
            months.append({"mese": month_key, "kwh": kwh, "costo": cost_with_vat})

        return {"mesi": months}
