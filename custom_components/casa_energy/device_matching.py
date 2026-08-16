"""Risoluzione automatica dei sensori power a partire dai sensori energy
selezionati dall'utente, tramite device registry.

Per ogni sensore energy scelto, cerchiamo il device a cui appartiene e, tra
le sue entità, quelle con device_class 'power'. Tre esiti possibili:

- 0 device_id sul sensore energy, oppure 0 sensori power sul device
  → "unmatched" (nessuna corrispondenza trovata)
- esattamente 1 sensore power sul device
  → "matched" (collegamento automatico)
- 2+ sensori power sullo stesso device
  → "ambiguous" (serve una scelta manuale dell'utente)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er


@dataclass
class MatchResult:
    """Esito della risoluzione automatica per tutti i sensori energy."""

    matched: dict[str, dict] = field(default_factory=dict)  # energy_entity -> {name, power_entity}
    ambiguous: dict[str, dict] = field(default_factory=dict)  # energy_entity -> {name, options: [power_entity,...]}
    unmatched: dict[str, str] = field(default_factory=dict)  # energy_entity -> display name (per il messaggio d'errore)


def _friendly_name(hass: HomeAssistant, entity_id: str) -> str:
    state = hass.states.get(entity_id)
    if state is not None and state.name:
        return state.name
    return entity_id


def resolve_power_sensors(hass: HomeAssistant, energy_entities: list[str]) -> MatchResult:
    """Per ciascun sensore energy, individua il device e i sensori power
    associati allo stesso device.

    Se più sensori energy selezionati appartengono allo STESSO device (es.
    'energia totale' + 'energia giornaliera' dello stesso dispositivo),
    il secondo e successivi vengono ignorati per il calcolo della potenza:
    altrimenti lo stesso sensore power finirebbe sommato più volte nel
    totale, gonfiando artificialmente la potenza istantanea."""
    result = MatchResult()
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    seen_device_ids: set[str] = set()

    for energy_entity_id in energy_entities:
        entry = ent_reg.async_get(energy_entity_id)
        device_id = entry.device_id if entry else None
        display_name = _friendly_name(hass, energy_entity_id)

        if not device_id:
            result.unmatched[energy_entity_id] = display_name
            continue

        if device_id in seen_device_ids:
            # Device già risolto tramite un altro sensore energy dello
            # stesso dispositivo: saltiamo per evitare di sommare due
            # volte lo stesso sensore power nel totale.
            continue
        seen_device_ids.add(device_id)

        device = dev_reg.async_get(device_id)
        device_name = (device.name_by_user or device.name) if device else None
        load_name = device_name or display_name

        # Tutte le entità sensor di quel device con device_class power
        power_candidates: list[str] = []
        for candidate in er.async_entries_for_device(ent_reg, device_id):
            if candidate.domain != "sensor":
                continue
            # device_class può essere sull'entity registry entry oppure
            # solo sullo state corrente; controlliamo entrambi.
            device_class = candidate.device_class or candidate.original_device_class
            if device_class is None:
                state = hass.states.get(candidate.entity_id)
                if state is not None:
                    device_class = state.attributes.get("device_class")
            if device_class == "power":
                power_candidates.append(candidate.entity_id)

        if not power_candidates:
            result.unmatched[energy_entity_id] = load_name
        elif len(power_candidates) == 1:
            result.matched[energy_entity_id] = {
                "name": load_name,
                "power_entity": power_candidates[0],
            }
        else:
            result.ambiguous[energy_entity_id] = {
                "name": load_name,
                "options": power_candidates,
            }

    return result
