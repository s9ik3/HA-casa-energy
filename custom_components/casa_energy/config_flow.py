"""Config flow per l'integrazione Casa Energy."""
from __future__ import annotations

import copy
from datetime import datetime
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_CRITICAL_THRESHOLD_PCT,
    CONF_ENERGY_SENSORS,
    CONF_EXTRA_CHARGES_PER_KWH,
    CONF_FIXED_MONTHLY_COST,
    CONF_IGNORE_UNMATCHED,
    CONF_INSTANCE_NAME,
    CONF_LOAD_ENERGY_ENTITY,
    CONF_LOAD_ENTITY,
    CONF_LOAD_NAME,
    CONF_LOADS,
    CONF_MAX_POWER,
    CONF_PRICE_PER_KWH,
    CONF_RESET_FROZEN_TARIFFS,
    CONF_TARIFF_LINE_ITEMS,
    CONF_VAT_RATE,
    CONF_WARNING_THRESHOLD_PCT,
    DEFAULT_CRITICAL_THRESHOLD_PCT,
    DEFAULT_MAX_POWER,
    DEFAULT_VAT_RATE,
    DEFAULT_WARNING_THRESHOLD_PCT,
    DOMAIN,
)
from .device_matching import resolve_power_sensors
from .tariff_history import (
    FrozenTariffStore,
    calculate_cost,
    tariff_from_entry_data,
    tariffs_differ,
)
from .tariff_line_items_yaml import (
    EXAMPLE_YAML,
    LineItemsParseError,
    line_items_to_yaml,
    parse_line_items_yaml,
)

ENERGY_SENSOR_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", device_class="energy", multiple=True)
)


class _DeviceMatchingMixin:
    """Logica condivisa tra ConfigFlow e OptionsFlow per la risoluzione
    automatica dei sensori power a partire dai sensori energy scelti
    dall'utente. La classe che la usa deve esporre self._data, self.hass
    e il metodo async _continue_after_loads() (implementato sia in
    ConfigFlow che in OptionsFlow, prosegue verso lo step tariffa)."""

    async def _async_resolve_devices(self) -> config_entries.ConfigFlowResult:
        """Esegue il matching device-based e decide se proseguire, chiedere
        di risolvere le ambiguità, o mostrare l'errore bloccante per i
        sensori senza corrispondenza."""
        result = resolve_power_sensors(self.hass, self._data.get(CONF_ENERGY_SENSORS, []))

        self._match_matched = result.matched
        self._match_ambiguous = list(result.ambiguous.items())
        self._match_unmatched = result.unmatched
        self._confirm_queue = None

        return await self._async_continue_matching()

    async def _async_continue_matching(self) -> config_entries.ConfigFlowResult:
        """Prosegue la risoluzione dopo un eventuale step di
        disambiguazione: se restano ambiguità le chiede, altrimenti
        gestisce i non risolti, altrimenti passa alla conferma dei nomi."""
        if self._match_ambiguous:
            return await self.async_step_ambiguous_power()

        if self._match_unmatched and not self._data.get(CONF_IGNORE_UNMATCHED):
            return await self.async_step_unmatched_power()

        return await self.async_step_confirm_load_names()

    # ---------- Step: conferma/rinomina di tutti i carichi risolti ----------
    async def async_step_confirm_load_names(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Mostra, un carico alla volta, il nome proposto per ciascun
        dispositivo individuato automaticamente (o già disambiguato),
        permettendo di rinominarlo subito invece di dover passare dalle
        Opzioni in un secondo momento. Un carico per step (invece di un
        form con più campi insieme) perché le label di campi generati
        dinamicamente non sono traducibili singolarmente in HA."""
        if self._confirm_queue is None:
            self._confirm_queue = list(self._match_matched.keys())

        if user_input is not None and self._confirm_queue:
            energy_entity = self._confirm_queue.pop(0)
            new_name = user_input.get(CONF_LOAD_NAME, "").strip()
            if new_name:
                self._match_matched[energy_entity]["name"] = new_name

        if not self._confirm_queue:
            self._confirm_queue = None
            return await self._async_finalize_loads()

        energy_entity = self._confirm_queue[0]
        info = self._match_matched[energy_entity]
        schema = vol.Schema(
            {
                vol.Optional(CONF_LOAD_NAME, default=info["name"]): str,
            }
        )
        return self.async_show_form(
            step_id="confirm_load_names",
            data_schema=schema,
            description_placeholders={
                "energy_entity": energy_entity,
                "power_entity": info["power_entity"],
            },
        )

    async def _async_finalize_loads(self) -> config_entries.ConfigFlowResult:
        """Costruisce CONF_LOADS a partire dai match risolti (auto +
        disambiguati) e prosegue verso lo step successivo del flow."""
        loads = []
        for energy_entity, info in self._match_matched.items():
            loads.append(
                {
                    CONF_LOAD_NAME: info["name"],
                    CONF_LOAD_ENTITY: info["power_entity"],
                    CONF_LOAD_ENERGY_ENTITY: energy_entity,
                }
            )
        self._data[CONF_LOADS] = loads
        return await self._continue_after_loads()

    # ---------- Step: disambiguazione (device con più sensori power) ----------
    async def async_step_ambiguous_power(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            energy_entity, info = self._match_ambiguous.pop(0)
            chosen = user_input.get(CONF_LOAD_ENTITY)
            name = user_input.get(CONF_LOAD_NAME, "").strip() or info["name"]
            self._match_matched[energy_entity] = {
                "name": name,
                "power_entity": chosen,
            }
            return await self._async_continue_matching()

        energy_entity, info = self._match_ambiguous[0]
        schema = vol.Schema(
            {
                vol.Required(CONF_LOAD_NAME, default=info["name"]): str,
                vol.Required(CONF_LOAD_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(include_entities=info["options"])
                ),
            }
        )
        return self.async_show_form(
            step_id="ambiguous_power",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "energy_entity": energy_entity,
                "device_name": info["name"],
            },
        )

    # ---------- Step: errore bloccante per sensori senza corrispondenza ----------
    async def async_step_unmatched_power(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input.get(CONF_IGNORE_UNMATCHED):
                self._data[CONF_IGNORE_UNMATCHED] = True
                return await self._async_finalize_loads()
            errors["base"] = "unmatched_power_sensors"

        names = ", ".join(self._match_unmatched.values())
        schema = vol.Schema(
            {
                vol.Optional(CONF_IGNORE_UNMATCHED, default=False): bool,
            }
        )
        return self.async_show_form(
            step_id="unmatched_power",
            data_schema=schema,
            errors=errors,
            description_placeholders={"devices": names},
        )


class CasaEnergyConfigFlow(_DeviceMatchingMixin, config_entries.ConfigFlow, domain=DOMAIN):
    """Gestisce il flow di configurazione iniziale (aggiunta integrazione)."""

    VERSION = 2

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._match_matched: dict[str, dict] = {}
        self._match_ambiguous: list[tuple[str, dict]] = []
        self._match_unmatched: dict[str, str] = {}
        self._confirm_queue: list[str] | None = None

    # ---------- STEP 0: nome istanza ----------
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._data[CONF_INSTANCE_NAME] = user_input[CONF_INSTANCE_NAME]
            return await self.async_step_energy_sensors()

        schema = vol.Schema(
            {
                vol.Required(CONF_INSTANCE_NAME, default="Casa"): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    # ---------- STEP 1: sensori energy (da qui deriviamo anche i carichi power) ----------
    async def async_step_energy_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get(CONF_ENERGY_SENSORS):
                errors["base"] = "no_energy_sensors"
            else:
                self._data[CONF_ENERGY_SENSORS] = user_input[CONF_ENERGY_SENSORS]
                return await self._async_resolve_devices()

        schema = vol.Schema(
            {
                vol.Required(CONF_ENERGY_SENSORS): ENERGY_SENSOR_SELECTOR,
            }
        )
        return self.async_show_form(
            step_id="energy_sensors", data_schema=schema, errors=errors
        )

    async def _continue_after_loads(self) -> config_entries.ConfigFlowResult:
        return await self.async_step_tariff()

    # ---------- STEP 2: tariffa ----------
    # ---------- STEP 2: tariffa base + potenza istantanea (unite in un solo step
    # nel setup iniziale: entrambe sono semplici liste di campi numerici senza
    # logica condizionale tra loro, a differenza delle Opzioni dove la Tariffa
    # ha in più le checkbox di reset/voci avanzate) ----------
    async def async_step_tariff(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(
                title=self._data[CONF_INSTANCE_NAME], data=self._data
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_PRICE_PER_KWH, default=0.10): vol.Coerce(float),
                vol.Required(CONF_FIXED_MONTHLY_COST, default=0.0): vol.Coerce(float),
                vol.Optional(CONF_EXTRA_CHARGES_PER_KWH, default=0.0): vol.Coerce(float),
                vol.Required(CONF_VAT_RATE, default=DEFAULT_VAT_RATE): vol.Coerce(float),
                vol.Required(CONF_MAX_POWER, default=DEFAULT_MAX_POWER): vol.Coerce(int),
                vol.Required(
                    CONF_WARNING_THRESHOLD_PCT, default=DEFAULT_WARNING_THRESHOLD_PCT
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
                vol.Required(
                    CONF_CRITICAL_THRESHOLD_PCT, default=DEFAULT_CRITICAL_THRESHOLD_PCT
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
            }
        )
        return self.async_show_form(step_id="tariff", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> CasaEnergyOptionsFlow:
        return CasaEnergyOptionsFlow(config_entry)


class CasaEnergyOptionsFlow(_DeviceMatchingMixin, config_entries.OptionsFlow):
    """Permette di modificare la configurazione dopo l'installazione,
    dal pannello Impostazioni → Dispositivi e servizi → Casa Energy → Opzioni.
    Stessa logica del config_flow iniziale, ma parte dai valori già salvati."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry
        # Deep copy: gli step di rinomina mutano CONF_LOADS in-place. Con
        # una copia superficiale quei dict sarebbero condivisi con
        # config_entry.data e verrebbero modificati ancora prima che
        # l'utente confermi (o anche se annulla il flow a metà), violando
        # la regola di HA per cui una ConfigEntry non va mai mutata
        # direttamente.
        self._data: dict[str, Any] = copy.deepcopy(dict(config_entry.data))
        self._match_matched: dict[str, dict] = {}
        self._match_ambiguous: list[tuple[str, dict]] = []
        self._match_unmatched: dict[str, str] = {}
        self._confirm_queue: list[str] | None = None
        self._rename_loads_queue: list[int] | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        return await self.async_step_energy_sensors()

    async def _async_save_and_finish(self) -> config_entries.ConfigFlowResult:
        """Salva le modifiche in entry.data (dove sensor.py e __init__.py
        le leggono davvero) e chiude il flow. Fondamentale: chiamare
        self.async_create_entry(data=...) qui scriverebbe in entry.options
        anziché in entry.data — dato che l'integrazione legge sempre da
        entry.data, quel percorso lascerebbe la card silenziosamente con
        i valori vecchi nonostante il flow segnali un salvataggio riuscito.
        async_update_entry() aggiorna esplicitamente entry.data; il
        confronto con i dati precedenti fa scattare l'update_listener
        (già registrato in __init__.py) che ricarica l'integrazione.

        Prima del salvataggio, se la tariffa è cambiata rispetto a quella
        finora in vigore (self._config_entry.data contiene ancora i
        valori vecchi in questo momento), congela quella vecchia tariffa
        su tutti i mesi già chiusi: da qui in poi quei mesi non seguiranno
        più eventuali modifiche future, restando fissi a quanto erano
        stati fatturati davvero."""
        old_tariff = tariff_from_entry_data(self._config_entry.data)
        new_tariff = tariff_from_entry_data(self._data)

        # Usiamo la STESSA istanza di FrozenTariffStore già in mano al
        # coordinator (non una nuova temporanea): quella ha una cache in
        # memoria propria, e scrivere/resettare tramite un'istanza
        # diversa lascia la cache del coordinator disallineata dal
        # disco finché non arriva un riavvio completo — il coordinator
        # continuerebbe a leggere i vecchi dati fino ad allora.
        coordinator = self.hass.data.get(DOMAIN, {}).get(self._config_entry.entry_id)
        store = coordinator.frozen_tariffs if coordinator else FrozenTariffStore(
            self.hass, self._config_entry.entry_id
        )

        if self._data.pop(CONF_RESET_FROZEN_TARIFFS, False):
            await store.async_reset()
        elif tariffs_differ(old_tariff, new_tariff):
            mesi = (coordinator.data or {}).get("mesi", []) if coordinator else []
            now = datetime.now()
            current_month_key = f"{now.year}-{now.month:02d}"
            closed_months = [m["mese"] for m in mesi if m["mese"] != current_month_key]
            await store.async_freeze_previous_tariff(closed_months, old_tariff)

        self.hass.config_entries.async_update_entry(self._config_entry, data=self._data)
        return self.async_create_entry(title="", data={})

    async def async_step_energy_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get(CONF_ENERGY_SENSORS):
                errors["base"] = "no_energy_sensors"
            else:
                # Se la selezione di sensori energy non è cambiata,
                # manteniamo i carichi già risolti/rinominati in precedenza
                # invece di rifare da zero il matching (altrimenti ogni
                # apertura delle Opzioni perderebbe le rinomine manuali
                # fatte in passato su un carico ambiguo).
                previous_sensors = set(self._data.get(CONF_ENERGY_SENSORS, []))
                new_sensors = set(user_input[CONF_ENERGY_SENSORS])
                self._data[CONF_ENERGY_SENSORS] = user_input[CONF_ENERGY_SENSORS]
                if new_sensors == previous_sensors:
                    return await self.async_step_tariff()
                return await self._async_resolve_devices()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_ENERGY_SENSORS,
                    default=self._data.get(CONF_ENERGY_SENSORS, []),
                ): ENERGY_SENSOR_SELECTOR,
            }
        )
        return self.async_show_form(
            step_id="energy_sensors", data_schema=schema, errors=errors
        )

    async def _continue_after_loads(self) -> config_entries.ConfigFlowResult:
        return await self.async_step_tariff()

    async def async_step_tariff(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            manage_line_items = user_input.pop("manage_line_items", False)
            self._data.update(user_input)
            if manage_line_items:
                return await self.async_step_manage_line_items()
            return await self.async_step_power()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_PRICE_PER_KWH, default=self._data.get(CONF_PRICE_PER_KWH, 0.10)
                ): vol.Coerce(float),
                vol.Required(
                    CONF_FIXED_MONTHLY_COST,
                    default=self._data.get(CONF_FIXED_MONTHLY_COST, 0.0),
                ): vol.Coerce(float),
                vol.Optional(
                    CONF_EXTRA_CHARGES_PER_KWH,
                    default=self._data.get(CONF_EXTRA_CHARGES_PER_KWH, 0.0),
                ): vol.Coerce(float),
                vol.Required(
                    CONF_VAT_RATE, default=self._data.get(CONF_VAT_RATE, DEFAULT_VAT_RATE)
                ): vol.Coerce(float),
                vol.Optional(CONF_RESET_FROZEN_TARIFFS, default=False): bool,
                vol.Optional("manage_line_items", default=False): bool,
            }
        )
        return self.async_show_form(step_id="tariff", data_schema=schema, errors=errors)

    # ---------- Voci di tariffa avanzate: blocco YAML unico ----------
    async def async_step_manage_line_items(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Tutte le voci di tariffa avanzate si inseriscono qui in un
        colpo solo, come blocco YAML, invece che una alla volta in più
        passaggi separati: con bollette a 10+ componenti il flusso
        precedente (un form per voce) si è rivelato fragile in pratica —
        un valore poteva non registrarsi nel form senza un errore
        visibile, o una voce restare fuori senza che l'utente se ne
        accorgesse subito. Un blocco unico permette anche di preparare
        l'elenco con l'aiuto di un assistente IA a cui si è data la
        bolletta, e di vedere/correggere tutto in un solo posto."""
        errors: dict[str, str] = {}
        current_yaml = line_items_to_yaml(self._data.get(CONF_TARIFF_LINE_ITEMS, []))
        error_detail = ""

        if user_input is not None:
            raw_text = user_input.get("line_items_yaml", "")
            reference_cost = user_input.get("reference_cost")
            try:
                new_items = parse_line_items_yaml(raw_text)
            except LineItemsParseError as err:
                errors["base"] = "line_items_invalid"
                current_yaml = raw_text
                error_detail = str(err)
            else:
                # Se l'utente ha indicato un costo di riferimento (es. il
                # totale esatto della bolletta), verifichiamo che il
                # calcolo con le voci appena inserite ci si avvicini
                # abbastanza PRIMA di salvare: uno scarto ampio (oltre il
                # 5%) è quasi sempre segno di una voce con il coefficiente
                # sbagliato o mancante, non di un normale arrotondamento
                # — meglio segnalarlo subito che scoprirlo dopo aver
                # salvato, come già successo controllando a mano contro
                # la card. Il mese di riferimento è opzionale: se la
                # bolletta guardata per compilare le voci non è quella
                # del mese corrente (es. si sta configurando l'integrazione
                # usando una bolletta più vecchia come esempio), va
                # indicato esplicitamente — altrimenti il confronto
                # userebbe i kWh del mese sbagliato, dando un falso
                # allarme o un falso "va tutto bene".
                if reference_cost:
                    coordinator = self.hass.data.get(DOMAIN, {}).get(
                        self._config_entry.entry_id
                    )
                    mesi = (coordinator.data or {}).get("mesi", []) if coordinator else []
                    now = datetime.now()
                    reference_month_input = (user_input.get("reference_month") or "").strip()
                    target_month_key = reference_month_input or f"{now.year}-{now.month:02d}"
                    target_month = next(
                        (m for m in mesi if m["mese"] == target_month_key), None
                    )
                    if target_month is None:
                        errors["base"] = "reference_month_not_found"
                        current_yaml = raw_text
                        available = ", ".join(m["mese"] for m in mesi) or "nessuno"
                        error_detail = (
                            f"Nessuno storico trovato per il mese '{target_month_key}'. "
                            f"Mesi disponibili: {available}."
                        )
                    elif target_month.get("insufficient_data"):
                        errors["base"] = "reference_month_not_found"
                        current_yaml = raw_text
                        error_detail = (
                            f"Il mese '{target_month_key}' non ha ancora dati sufficienti "
                            "per un confronto affidabile. Scegli un altro mese, o lascia "
                            "vuoto il costo di riferimento."
                        )
                    else:
                        trial_tariff = tariff_from_entry_data(
                            {**self._data, CONF_TARIFF_LINE_ITEMS: new_items}
                        )
                        trial_cost = calculate_cost(
                            target_month["kwh"], target_month_key, trial_tariff
                        )
                        diff_pct = abs(trial_cost - reference_cost) / reference_cost * 100
                        if diff_pct > 5:
                            errors["base"] = "cost_mismatch"
                            current_yaml = raw_text
                            error_detail = (
                                f"Mese {target_month_key}: calcolato ~ € {trial_cost} "
                                f"({target_month['kwh']} kWh) contro un riferimento di "
                                f"€ {reference_cost} (scarto {round(diff_pct, 1)}%). "
                                "Controlla se manca una voce o se un valore è sbagliato. "
                                "Se lo scarto è voluto (es. il riferimento include servizi "
                                "extra come un canone), invia di nuovo lasciando vuoto il "
                                "campo 'Costo di riferimento' per salvare comunque."
                            )

                if not errors:
                    self._data[CONF_TARIFF_LINE_ITEMS] = new_items
                    return await self.async_step_power()

        # Anteprima: applica la tariffa (4 campi base + voci salvate finora)
        # al consumo del mese in corso già calcolato dal coordinator, così
        # si vede subito se il totale torna prima di modificare qualcosa,
        # invece di doverlo scoprire solo dopo aver salvato e controllato
        # la card. Calcolata sui dati SALVATI (non su un tentativo appena
        # fallito): un solo invio resta sufficiente per confermare, senza
        # aggiungere un passaggio extra di "conferma dopo anteprima".
        preview = ""
        coordinator = self.hass.data.get(DOMAIN, {}).get(self._config_entry.entry_id)
        if coordinator:
            mesi = (coordinator.data or {}).get("mesi", [])
            now = datetime.now()
            current_month_key = f"{now.year}-{now.month:02d}"
            current_month = next((m for m in mesi if m["mese"] == current_month_key), None)
            if current_month and not current_month.get("insufficient_data"):
                preview_tariff = tariff_from_entry_data(self._data)
                preview_cost = calculate_cost(
                    current_month["kwh"], current_month_key, preview_tariff
                )
                preview = (
                    f"Con la tariffa attualmente salvata: "
                    f"{current_month['kwh']} kWh del mese corrente → ~ € {preview_cost}"
                )

        schema = vol.Schema(
            {
                vol.Optional("line_items_yaml", default=current_yaml): selector.TextSelector(
                    selector.TextSelectorConfig(
                        multiline=True, type=selector.TextSelectorType.TEXT
                    )
                ),
                vol.Optional("reference_cost"): vol.Coerce(float),
                vol.Optional("reference_month"): str,
            }
        )
        return self.async_show_form(
            step_id="manage_line_items",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "example": EXAMPLE_YAML,
                "error_detail": error_detail,
                "preview": preview,
            },
        )

    async def async_step_power(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._data.update(user_input)
            self._rename_loads_queue = None
            return await self.async_step_rename_loads()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_MAX_POWER, default=self._data.get(CONF_MAX_POWER, DEFAULT_MAX_POWER)
                ): vol.Coerce(int),
                vol.Required(
                    CONF_WARNING_THRESHOLD_PCT,
                    default=self._data.get(
                        CONF_WARNING_THRESHOLD_PCT, DEFAULT_WARNING_THRESHOLD_PCT
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
                vol.Required(
                    CONF_CRITICAL_THRESHOLD_PCT,
                    default=self._data.get(
                        CONF_CRITICAL_THRESHOLD_PCT, DEFAULT_CRITICAL_THRESHOLD_PCT
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
            }
        )
        return self.async_show_form(step_id="power", data_schema=schema, errors=errors)

    # ---------- Rinomina dei carichi principali (quelli sommati nel totale) ----------
    async def async_step_rename_loads(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Permette di rinominare, un carico alla volta, i dispositivi che
        concorrono al calcolo della potenza totale (CONF_LOADS). In
        precedenza il nome si poteva scegliere solo durante il setup
        iniziale (o quando la selezione dei sensori energy cambiava); qui
        è possibile farlo in qualunque momento dalle Opzioni, senza dover
        toccare la selezione dei sensori."""
        current: list[dict] = self._data.get(CONF_LOADS, [])

        if self._rename_loads_queue is None:
            self._rename_loads_queue = list(range(len(current)))

        if user_input is not None and self._rename_loads_queue:
            idx = self._rename_loads_queue.pop(0)
            new_name = user_input.get(CONF_LOAD_NAME, "").strip()
            if new_name:
                current[idx][CONF_LOAD_NAME] = new_name

        if not self._rename_loads_queue:
            self._rename_loads_queue = None
            return await self._async_save_and_finish()

        idx = self._rename_loads_queue[0]
        d = current[idx]
        schema = vol.Schema(
            {
                vol.Optional(CONF_LOAD_NAME, default=d[CONF_LOAD_NAME]): str,
            }
        )
        return self.async_show_form(
            step_id="rename_loads",
            data_schema=schema,
            description_placeholders={"entity": d[CONF_LOAD_ENTITY]},
        )
