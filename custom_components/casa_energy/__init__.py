"""Integrazione Casa Energy: storico consumi + potenza istantanea."""
from __future__ import annotations

import asyncio
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
    CONF_LOAD_ENERGY_ENTITY,
    CONF_LOAD_ENTITY,
    CONF_LOAD_NAME,
    CONF_LOADS,
    CONF_PRICE_PER_KWH,
    CONF_VAT_RATE,
    DOMAIN,
    UPDATE_INTERVAL_MINUTES,
)
from .device_matching import resolve_power_sensors

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]

CARD_URL_PATH = "/casa_energy_static/casa-energy-card.js"
CARD_JS_FILENAME = "casa-energy-card.js"
_INSTANCES_KEY = "instance_count"
_RESOURCE_ID_KEY = "lovelace_resource_id"


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Chiamato automaticamente da Home Assistant quando trova una config
    entry con entry.version inferiore a CasaEnergyConfigFlow.VERSION.

    Serve come rete di sicurezza per istanze rimaste su una versione
    precedente dell'integrazione: senza questa migrazione, un'istanza
    configurata prima che il matching automatico energy→power esistesse
    (o comunque con CONF_LOADS mancante/vuoto) restava con un sensore di
    potenza permanentemente "Non disponibile" finché l'utente non
    reinstallava manualmente l'integrazione da zero.

    La migrazione qui è "best effort": se i sensori energy configurati
    sono ancora presenti, ritenta il matching automatico per ricostruire
    CONF_LOADS. Se qualcosa non torna, logga e lascia la entry invariata
    piuttosto che rischiare di corrompere una configurazione funzionante.
    """
    if entry.version >= 2:
        return True

    data = dict(entry.data)

    if not data.get(CONF_LOADS):
        energy_sensors = data.get(CONF_ENERGY_SENSORS, [])
        if energy_sensors:
            try:
                result = resolve_power_sensors(hass, energy_sensors)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning(
                    "Migrazione Casa Energy: impossibile ricostruire i carichi "
                    "automaticamente (%s). Riapri Configura sull'integrazione "
                    "per completare manualmente la configurazione.",
                    err,
                )
                result = None

            if result and result.matched:
                data[CONF_LOADS] = [
                    {
                        CONF_LOAD_NAME: info["name"],
                        CONF_LOAD_ENTITY: info["power_entity"],
                        CONF_LOAD_ENERGY_ENTITY: energy_entity,
                    }
                    for energy_entity, info in result.matched.items()
                ]
                _LOGGER.info(
                    "Migrazione Casa Energy: ricostruiti %d carichi automaticamente "
                    "per l'istanza '%s'.",
                    len(data[CONF_LOADS]),
                    data.get("instance_name", entry.entry_id),
                )
            else:
                _LOGGER.warning(
                    "Migrazione Casa Energy: nessun carico ricostruibile "
                    "automaticamente per l'istanza '%s' (device senza sensore "
                    "power abbinato, o sensori energy non più esistenti). "
                    "Riapri Configura sull'integrazione per completare la "
                    "configurazione manualmente.",
                    data.get("instance_name", entry.entry_id),
                )

    hass.config_entries.async_update_entry(entry, data=data, version=2)
    return True


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

    Nota tecnica: la chiave giusta in hass.data per l'oggetto Lovelace è
    "lovelace" (non "lovelace_resources", che non esiste e faceva
    fallire silenziosamente la registrazione in versioni precedenti).
    L'oggetto lovelace espone .resources (lo storage vero e proprio) e
    .mode (storage/yaml). Se il dashboard è in modalità YAML, la
    registrazione automatica non è supportata da Home Assistant: viene
    solo loggato un avviso, l'utente può sempre aggiungere la risorsa a
    mano se l'auto-registrazione non riesce.
    """
    www_path = Path(__file__).parent / "www" / CARD_JS_FILENAME
    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL_PATH, str(www_path), cache_headers=False)]
        )
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Impossibile registrare il file statico della card: %s", err)
        return

    lovelace = hass.data.get("lovelace")
    if lovelace is None:
        _LOGGER.info(
            "Componente Lovelace non ancora disponibile: aggiungi la "
            "risorsa %s manualmente da Impostazioni → Dashboard → Risorse.",
            CARD_URL_PATH,
        )
        return

    mode = getattr(lovelace, "mode", getattr(lovelace, "resource_mode", "yaml"))
    if mode != "storage":
        _LOGGER.info(
            "Dashboard Lovelace non in modalità storage: aggiungi la "
            "risorsa %s manualmente da Impostazioni → Dashboard → Risorse.",
            CARD_URL_PATH,
        )
        return

    # Le risorse Lovelace potrebbero non essere ancora caricate al momento
    # in cui l'integrazione viene impostata (specie all'avvio di HA):
    # ritentiamo con un breve backoff invece di arrenderci al primo giro.
    resources = lovelace.resources
    for attempt in range(10):
        if getattr(resources, "loaded", True):
            break
        await asyncio.sleep(1)
    else:
        _LOGGER.warning(
            "Le risorse Lovelace non risultano caricate dopo l'attesa: "
            "aggiungi la risorsa manualmente se non compare da sola. "
            "URL %s, tipo Modulo JavaScript.",
            CARD_URL_PATH,
        )
        return

    try:
        existing = [r for r in resources.async_items() if r["url"] == CARD_URL_PATH]
        if existing:
            hass.data[DOMAIN][_RESOURCE_ID_KEY] = existing[0]["id"]
            return

        item = await resources.async_create_item(
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
        lovelace = hass.data.get("lovelace")
        if lovelace is not None:
            await lovelace.resources.async_delete_item(resource_id)
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

        # Vai indietro fino a 24 mesi fa (+ margine di un mese per
        # includere per intero il primo mese della finestra) per avere
        # storico esteso + mese corrente.
        start = (datetime.now() - timedelta(days=760)).replace(
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
        # Per ogni mese, il consumo è: ultimo valore osservato nel mese meno
        # il valore osservato appena PRIMA dell'inizio del mese (o, se il
        # sensore non esisteva ancora, il primo valore disponibile in quel
        # mese). Se per un mese esiste UN SOLO punto storico in totale (nessun
        # secondo campione da cui calcolare una differenza), quel mese viene
        # marcato come "dati insufficienti" invece di mostrare 0 kWh, che
        # sembrerebbe un consumo reale invece di un'attesa fisiologica del
        # recorder (le statistiche giornaliere si consolidano nel tempo).
        monthly_kwh: dict[str, float] = {}
        monthly_insufficient: dict[str, bool] = {}
        for sensor_id, entries in stats.items():
            points: list[tuple[datetime, float]] = []
            for entry_stat in entries:
                start_ts = entry_stat.get("start")
                total = entry_stat.get("sum")
                if total is None or start_ts is None:
                    continue
                points.append((datetime.fromtimestamp(start_ts), total))

            if not points:
                continue

            points.sort(key=lambda p: p[0])

            # Raggruppa i punti per mese
            by_month: dict[str, list[tuple[datetime, float]]] = {}
            for ts, value in points:
                by_month.setdefault(ts.strftime("%Y-%m"), []).append((ts, value))

            for month_key, month_points in by_month.items():
                month_points.sort(key=lambda p: p[0])
                last_value = month_points[-1][1]

                # Valore di riferimento: l'ultimo punto CRONOLOGICAMENTE
                # precedente all'inizio di questo mese, se esiste tra tutti
                # i punti raccolti (anche di mesi precedenti).
                month_start_dt = month_points[0][0].replace(
                    day=1, hour=0, minute=0, second=0, microsecond=0
                )
                earlier = [v for ts, v in points if ts < month_start_dt]

                if earlier:
                    baseline = earlier[-1]
                elif len(month_points) > 1:
                    baseline = month_points[0][1]
                else:
                    # Nessun punto precedente al mese E un solo punto nel
                    # mese stesso: non c'è alcun secondo campione da cui
                    # calcolare una differenza. Segnala come "insufficiente"
                    # invece di produrre un 0 kWh fuorviante.
                    monthly_insufficient[month_key] = True
                    monthly_kwh.setdefault(month_key, 0.0)
                    continue

                delta = max(0.0, last_value - baseline)
                monthly_kwh[month_key] = monthly_kwh.get(month_key, 0.0) + delta

        months = []
        for month_key in sorted(monthly_kwh.keys()):
            insufficient = monthly_insufficient.get(month_key, False)
            kwh = round(monthly_kwh[month_key], 2)
            cost = round((kwh * price) + (kwh * extra) + fixed_cost, 2)
            cost_with_vat = round(cost * (1 + vat / 100), 2)
            months.append(
                {
                    "mese": month_key,
                    "kwh": kwh,
                    "costo": cost_with_vat,
                    "insufficient_data": insufficient,
                }
            )

        return {"mesi": months}
