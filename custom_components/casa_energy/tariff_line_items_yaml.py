"""Parsing e validazione delle voci di tariffa avanzate, inserite
dall'utente come un unico blocco YAML invece che una alla volta.

Il flusso precedente (un form per voce, con più passaggi di
aggiungi/rimuovi/reinvia) si è rivelato troppo fragile in pratica: con
bollette a 10+ componenti, il rischio di un campo dimenticato, un valore
non registrato dal form, o un nome sbagliato per riga cresce con ogni
singolo invio. Con un blocco YAML unico, l'utente (o un assistente IA a
cui ha dato la bolletta) prepara l'intera lista in un colpo solo, e la
validazione qui segnala con precisione riga per riga cosa non va, invece
di fallire silenziosamente su un singolo campo del form.
"""
from __future__ import annotations

import yaml

from .const import (
    CONF_LINE_ITEM_APPLY_VAT,
    CONF_LINE_ITEM_ENGAGED_POWER_KW,
    CONF_LINE_ITEM_MONTH_FROM,
    CONF_LINE_ITEM_MONTH_TO,
    CONF_LINE_ITEM_NAME,
    CONF_LINE_ITEM_TYPE,
    CONF_LINE_ITEM_VALUE,
    LINE_ITEM_TYPE_FIXED,
    LINE_ITEM_TYPE_PER_KW_POWER,
    LINE_ITEM_TYPE_PER_KWH,
)

_VALID_TYPES = {LINE_ITEM_TYPE_PER_KWH, LINE_ITEM_TYPE_FIXED, LINE_ITEM_TYPE_PER_KW_POWER}

# Esempio mostrato nella descrizione dello step, così l'utente (o un
# prompt IA) ha subito la sintassi esatta sotto mano senza dover
# indovinare i nomi dei campi o il formato.
EXAMPLE_YAML = """- name: Consumo energia
  type: per_kwh
  value: 0.1122
- name: Quota fissa
  type: fixed
  value: 9.10
- name: Quota potenza trasporto
  type: per_kw_power
  value: 1.96
  engaged_power_kw: 3.0
- name: Arrotondamenti
  type: fixed
  value: -0.43
  apply_vat: false
- name: Costo stagionale
  type: fixed
  value: 9.00
  apply_vat: false
  month_from: 1
  month_to: 10"""


class LineItemsParseError(Exception):
    """Sollevata quando il blocco YAML non è valido: il messaggio è
    pensato per essere mostrato direttamente all'utente nel form,
    indicando la riga o la voce responsabile."""


def parse_line_items_yaml(raw_text: str) -> list[dict]:
    """Converte il testo YAML incollato dall'utente in una lista di voci
    nel formato interno (le stesse chiavi usate finora in
    CONF_TARIFF_LINE_ITEMS), validando ogni campo. Solleva
    LineItemsParseError con un messaggio specifico al primo problema
    trovato, così l'utente sa esattamente cosa correggere senza dover
    indovinare quale delle N voci ha causato l'errore.

    Testo vuoto (o solo spazi) è valido e produce una lista vuota: è il
    modo per svuotare tutte le voci avanzate senza doverle rimuovere
    manualmente una a una."""
    raw_text = (raw_text or "").strip()
    if not raw_text:
        return []

    try:
        parsed = yaml.safe_load(raw_text)
    except yaml.YAMLError as err:
        raise LineItemsParseError(
            f"YAML non valido: {err}"
        ) from err

    if parsed is None:
        return []
    if not isinstance(parsed, list):
        raise LineItemsParseError(
            "Il testo deve essere un elenco di voci (ogni voce inizia con '- name: ...')."
        )

    items: list[dict] = []
    seen_names: set[str] = set()

    for index, entry in enumerate(parsed, start=1):
        if not isinstance(entry, dict):
            raise LineItemsParseError(
                f"Voce #{index}: ogni voce deve essere un blocco con almeno 'name', "
                "'type' e 'value' (hai scritto qualcosa che non è nel formato atteso)."
            )

        name = str(entry.get(CONF_LINE_ITEM_NAME, "")).strip()
        if not name:
            raise LineItemsParseError(f"Voce #{index}: manca 'name' (il nome della voce).")
        if name in seen_names:
            raise LineItemsParseError(
                f"Voce #{index} ('{name}'): questo nome è già usato da un'altra voce. "
                "Ogni voce deve avere un nome diverso."
            )
        seen_names.add(name)

        item_type = entry.get(CONF_LINE_ITEM_TYPE)
        if item_type not in _VALID_TYPES:
            raise LineItemsParseError(
                f"Voce #{index} ('{name}'): 'type' deve essere uno tra "
                f"{', '.join(sorted(_VALID_TYPES))} (hai scritto '{item_type}')."
            )

        if CONF_LINE_ITEM_VALUE not in entry:
            raise LineItemsParseError(f"Voce #{index} ('{name}'): manca 'value'.")
        try:
            value = float(entry[CONF_LINE_ITEM_VALUE])
        except (TypeError, ValueError) as err:
            raise LineItemsParseError(
                f"Voce #{index} ('{name}'): 'value' deve essere un numero "
                f"(hai scritto '{entry[CONF_LINE_ITEM_VALUE]}')."
            ) from err

        item: dict = {
            CONF_LINE_ITEM_NAME: name,
            CONF_LINE_ITEM_TYPE: item_type,
            CONF_LINE_ITEM_VALUE: value,
            CONF_LINE_ITEM_APPLY_VAT: bool(entry.get(CONF_LINE_ITEM_APPLY_VAT, True)),
        }

        if item_type == LINE_ITEM_TYPE_PER_KW_POWER:
            if CONF_LINE_ITEM_ENGAGED_POWER_KW not in entry:
                raise LineItemsParseError(
                    f"Voce #{index} ('{name}'): il tipo 'per_kw_power' richiede anche "
                    "'engaged_power_kw' (la potenza impegnata in kW)."
                )
            try:
                item[CONF_LINE_ITEM_ENGAGED_POWER_KW] = float(
                    entry[CONF_LINE_ITEM_ENGAGED_POWER_KW]
                )
            except (TypeError, ValueError) as err:
                raise LineItemsParseError(
                    f"Voce #{index} ('{name}'): 'engaged_power_kw' deve essere un numero."
                ) from err

        for month_key in (CONF_LINE_ITEM_MONTH_FROM, CONF_LINE_ITEM_MONTH_TO):
            if month_key in entry and entry[month_key] is not None:
                try:
                    month_value = int(entry[month_key])
                except (TypeError, ValueError) as err:
                    raise LineItemsParseError(
                        f"Voce #{index} ('{name}'): '{month_key}' deve essere un numero "
                        "da 1 a 12."
                    ) from err
                if not 1 <= month_value <= 12:
                    raise LineItemsParseError(
                        f"Voce #{index} ('{name}'): '{month_key}' deve essere tra 1 e 12 "
                        f"(hai scritto {month_value})."
                    )
                item[month_key] = month_value

        items.append(item)

    return items


def line_items_to_yaml(items: list[dict]) -> str:
    """Converte la lista di voci già salvate nel formato interno in YAML,
    per precompilare il campo quando l'utente riapre lo step (così vede e
    può modificare quello che ha già, invece di ripartire da un campo
    vuoto e doverlo riscrivere tutto)."""
    if not items:
        return ""
    clean_items = []
    for item in items:
        clean = {
            "name": item[CONF_LINE_ITEM_NAME],
            "type": item[CONF_LINE_ITEM_TYPE],
            "value": item[CONF_LINE_ITEM_VALUE],
        }
        if item[CONF_LINE_ITEM_TYPE] == LINE_ITEM_TYPE_PER_KW_POWER:
            clean["engaged_power_kw"] = item.get(CONF_LINE_ITEM_ENGAGED_POWER_KW, 0.0)
        if not item.get(CONF_LINE_ITEM_APPLY_VAT, True):
            clean["apply_vat"] = False
        if item.get(CONF_LINE_ITEM_MONTH_FROM):
            clean["month_from"] = item[CONF_LINE_ITEM_MONTH_FROM]
        if item.get(CONF_LINE_ITEM_MONTH_TO):
            clean["month_to"] = item[CONF_LINE_ITEM_MONTH_TO]
        clean_items.append(clean)
    return yaml.safe_dump(clean_items, allow_unicode=True, sort_keys=False)
