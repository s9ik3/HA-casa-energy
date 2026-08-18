"""Entità sensor create dall'integrazione Casa Energy."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_CRITICAL_THRESHOLD_PCT,
    CONF_EXTRA_CHARGES_PER_KWH,
    CONF_FIXED_MONTHLY_COST,
    CONF_INSTANCE_NAME,
    CONF_LOAD_ENTITY,
    CONF_LOAD_NAME,
    CONF_LOADS,
    CONF_MAX_POWER,
    CONF_PRICE_PER_KWH,
    CONF_TARIFF_LINE_ITEMS,
    CONF_VAT_RATE,
    CONF_WARNING_THRESHOLD_PCT,
    DOMAIN,
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [MonthlyEnergyHistorySensor(coordinator, entry)]
    if entry.data.get(CONF_LOADS):
        entities.append(PowerStatusSensor(hass, entry))
    async_add_entities(entities)


class MonthlyEnergyHistorySensor(CoordinatorEntity, SensorEntity):
    """Espone lo storico mensile consumi come attributo 'mesi', nello
    stesso formato JSON che la energy_summary_card.yaml già si aspetta
    (compatibilità con la card esistente, zero modifiche alla card
    richieste oltre al cambio di entity_id)."""

    _attr_icon = "mdi:transmission-tower"
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        instance_name = entry.data.get(CONF_INSTANCE_NAME, "Casa")
        self._attr_unique_id = f"{entry.entry_id}_monthly_energy_history"
        self._attr_name = "Storico consumi mensili"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=instance_name,
            manufacturer="Casa Energy",
            model="Virtual sensor",
        )

    @property
    def native_value(self):
        mesi = self.coordinator.data.get("mesi", [])
        return len(mesi)

    @property
    def extra_state_attributes(self):
        data = self._entry.data
        return {
            "mesi": self.coordinator.data.get("mesi", []),
            "max_power": data.get(CONF_MAX_POWER),
            "warning_threshold_pct": data.get(CONF_WARNING_THRESHOLD_PCT),
            "critical_threshold_pct": data.get(CONF_CRITICAL_THRESHOLD_PCT),
            # Tariffa attualmente configurata (viva, non quella congelata
            # sui mesi passati): comoda per verificare dall'interfaccia
            # cosa è stato effettivamente salvato, senza dover ispezionare
            # core.config_entries via terminale.
            "tariffa": {
                "price_per_kwh": data.get(CONF_PRICE_PER_KWH),
                "fixed_monthly_cost": data.get(CONF_FIXED_MONTHLY_COST),
                "extra_charges_per_kwh": data.get(CONF_EXTRA_CHARGES_PER_KWH),
                "vat_rate": data.get(CONF_VAT_RATE),
                "voci_avanzate": data.get(CONF_TARIFF_LINE_ITEMS, []),
            },
        }


class PowerStatusSensor(SensorEntity):
    """Somma la potenza dei carichi configurati (stessa logica del
    template originale dell'utente: [carico1, carico2, ...] | sum),
    e aggiunge lo stato di soglia (ok/warning/critical) e l'elenco dei
    singoli carichi come attributi pronti per la card.

    Si aggiorna in tempo reale (state_change su ciascun carico), non
    tramite il coordinator a 15 minuti usato per lo storico mensile,
    perché la potenza istantanea deve riflettere il valore attuale
    senza ritardo.
    """

    _attr_icon = "mdi:flash"
    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "W"
    _attr_device_class = "power"
    _attr_state_class = "measurement"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self._entry = entry
        instance_name = entry.data.get(CONF_INSTANCE_NAME, "Casa")
        self._attr_unique_id = f"{entry.entry_id}_power_status"
        self._attr_name = "Potenza istantanea"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=instance_name,
            manufacturer="Casa Energy",
            model="Virtual sensor",
        )
        self._unsub = None

    def _load_entities(self) -> list[str]:
        """Entità che entrano nel calcolo del totale."""
        return [
            load[CONF_LOAD_ENTITY]
            for load in self._entry.data.get(CONF_LOADS, [])
            if load.get(CONF_LOAD_ENTITY)
        ]

    async def async_added_to_hass(self) -> None:
        entities = self._load_entities()
        if entities:
            self._unsub = async_track_state_change_event(
                self.hass, entities, self._handle_source_change
            )
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()

    @callback
    def _handle_source_change(self, event) -> None:
        self.async_write_ha_state()

    def _read_entity_value(self, entity_id: str) -> float | None:
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return None
        try:
            return float(str(state.state).replace(",", "."))
        except (ValueError, TypeError):
            return None

    def _total_power(self) -> float | None:
        """Somma tutti i carichi configurati, come il template originale
        [states(carico1)|float(0), states(carico2)|float(0)] | sum.
        Un carico senza valore leggibile conta come 0, così un singolo
        sensore offline non azzera l'intero totale."""
        loads = self._load_entities()
        if not loads:
            return None
        return round(sum(self._read_entity_value(e) or 0.0 for e in loads), 2)

    @property
    def native_value(self):
        value = self._total_power()
        return round(value) if value is not None else None

    @property
    def extra_state_attributes(self):
        data = self._entry.data
        value = self._total_power()
        max_power = float(data.get(CONF_MAX_POWER) or 0) or None
        warning_pct = data.get(CONF_WARNING_THRESHOLD_PCT)
        critical_pct = data.get(CONF_CRITICAL_THRESHOLD_PCT)

        status = "unknown"
        percent = None
        if value is not None and max_power:
            percent = round((value / max_power) * 100)
            if critical_pct is not None and percent >= critical_pct:
                status = "critical"
            elif warning_pct is not None and percent >= warning_pct:
                status = "warning"
            else:
                status = "ok"

        loads = []
        for load in data.get(CONF_LOADS, []):
            load_value = self._read_entity_value(load[CONF_LOAD_ENTITY])
            loads.append(
                {
                    "name": load[CONF_LOAD_NAME],
                    "value": load_value,
                }
            )

        return {
            "status": status,
            "percent_of_max": percent,
            "max_power": max_power,
            "warning_threshold_pct": warning_pct,
            "critical_threshold_pct": critical_pct,
            "loads": loads,
        }
