"""Config flow per l'integrazione Casa Energy."""
from __future__ import annotations

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
    CONF_INSTANCE_NAME,
    CONF_LOAD_ENTITY,
    CONF_LOAD_NAME,
    CONF_LOADS,
    CONF_MAX_POWER,
    CONF_PRICE_PER_KWH,
    CONF_TOTAL_POWER_SENSOR,
    CONF_VAT_RATE,
    CONF_WARNING_THRESHOLD_PCT,
    DEFAULT_CRITICAL_THRESHOLD_PCT,
    DEFAULT_MAX_POWER,
    DEFAULT_VAT_RATE,
    DEFAULT_WARNING_THRESHOLD_PCT,
    DOMAIN,
)

ENERGY_SENSOR_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", device_class="energy", multiple=True)
)
POWER_SENSOR_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", device_class="power")
)
ANY_SENSOR_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor")
)


class CasaEnergyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Gestisce il flow di configurazione iniziale (aggiunta integrazione)."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

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

    # ---------- STEP 1: sensori energy per lo storico ----------
    async def async_step_energy_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get(CONF_ENERGY_SENSORS):
                errors["base"] = "no_energy_sensors"
            else:
                self._data[CONF_ENERGY_SENSORS] = user_input[CONF_ENERGY_SENSORS]
                return await self.async_step_tariff()

        schema = vol.Schema(
            {
                vol.Required(CONF_ENERGY_SENSORS): ENERGY_SENSOR_SELECTOR,
            }
        )
        return self.async_show_form(
            step_id="energy_sensors", data_schema=schema, errors=errors
        )

    # ---------- STEP 2: tariffa ----------
    async def async_step_tariff(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_power()

        schema = vol.Schema(
            {
                vol.Required(CONF_PRICE_PER_KWH, default=0.10): vol.Coerce(float),
                vol.Required(CONF_FIXED_MONTHLY_COST, default=0.0): vol.Coerce(float),
                vol.Optional(CONF_EXTRA_CHARGES_PER_KWH, default=0.0): vol.Coerce(float),
                vol.Required(CONF_VAT_RATE, default=DEFAULT_VAT_RATE): vol.Coerce(float),
            }
        )
        return self.async_show_form(step_id="tariff", data_schema=schema, errors=errors)

    # ---------- STEP 3: potenza istantanea + soglie ----------
    async def async_step_power(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._data.update(user_input)
            self._data[CONF_LOADS] = []
            return await self.async_step_add_load()

        schema = vol.Schema(
            {
                vol.Required(CONF_TOTAL_POWER_SENSOR): ANY_SENSOR_SELECTOR,
                vol.Required(CONF_MAX_POWER, default=DEFAULT_MAX_POWER): vol.Coerce(int),
                vol.Required(
                    CONF_WARNING_THRESHOLD_PCT, default=DEFAULT_WARNING_THRESHOLD_PCT
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
                vol.Required(
                    CONF_CRITICAL_THRESHOLD_PCT, default=DEFAULT_CRITICAL_THRESHOLD_PCT
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
            }
        )
        return self.async_show_form(step_id="power", data_schema=schema, errors=errors)

    # ---------- STEP 4: carichi monitorati (dinamico, ripetibile) ----------
    async def async_step_add_load(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input.get(CONF_LOAD_NAME) and user_input.get(CONF_LOAD_ENTITY):
                self._data[CONF_LOADS].append(
                    {
                        CONF_LOAD_NAME: user_input[CONF_LOAD_NAME],
                        CONF_LOAD_ENTITY: user_input[CONF_LOAD_ENTITY],
                    }
                )
            if user_input.get("add_another"):
                return await self.async_step_add_load()
            return self.async_create_entry(
                title=self._data[CONF_INSTANCE_NAME], data=self._data
            )

        schema = vol.Schema(
            {
                vol.Optional(CONF_LOAD_NAME): str,
                vol.Optional(CONF_LOAD_ENTITY): POWER_SENSOR_SELECTOR,
                vol.Optional("add_another", default=False): bool,
            }
        )
        return self.async_show_form(
            step_id="add_load",
            data_schema=schema,
            errors=errors,
            description_placeholders={"count": str(len(self._data[CONF_LOADS]))},
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> CasaEnergyOptionsFlow:
        return CasaEnergyOptionsFlow(config_entry)


class CasaEnergyOptionsFlow(config_entries.OptionsFlow):
    """Permette di modificare la configurazione dopo l'installazione,
    dal pannello Impostazioni → Dispositivi e servizi → Casa Energy → Opzioni.
    Stessa logica del config_flow iniziale, ma parte dai valori già salvati."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry
        self._data: dict[str, Any] = dict(config_entry.data)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        return await self.async_step_energy_sensors()

    async def async_step_energy_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get(CONF_ENERGY_SENSORS):
                errors["base"] = "no_energy_sensors"
            else:
                self._data[CONF_ENERGY_SENSORS] = user_input[CONF_ENERGY_SENSORS]
                return await self.async_step_tariff()

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

    async def async_step_tariff(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._data.update(user_input)
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
            }
        )
        return self.async_show_form(step_id="tariff", data_schema=schema, errors=errors)

    async def async_step_power(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_manage_loads()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_TOTAL_POWER_SENSOR,
                    default=self._data.get(CONF_TOTAL_POWER_SENSOR),
                ): ANY_SENSOR_SELECTOR,
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

    async def async_step_manage_loads(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Mostra i carichi già configurati con opzione di rimozione, e
        permette di continuare verso l'aggiunta di nuovi carichi."""
        current_loads: list[dict] = list(self._data.get(CONF_LOADS, []))

        if user_input is not None:
            remove_names = set(user_input.get("remove_loads", []))
            self._data[CONF_LOADS] = [
                load for load in current_loads if load[CONF_LOAD_NAME] not in remove_names
            ]
            if user_input.get("add_more"):
                return await self.async_step_add_load_option()
            return self.async_create_entry(title="", data=self._data)

        if not current_loads:
            # Nessun carico esistente: salta direttamente all'aggiunta
            return await self.async_step_add_load_option()

        options = [load[CONF_LOAD_NAME] for load in current_loads]
        schema = vol.Schema(
            {
                vol.Optional("remove_loads", default=[]): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options, multiple=True, mode="list"
                    )
                ),
                vol.Optional("add_more", default=False): bool,
            }
        )
        return self.async_show_form(step_id="manage_loads", data_schema=schema)

    async def async_step_add_load_option(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Aggiunge nuovi carichi, uno alla volta, dalle Opzioni."""
        if CONF_LOADS not in self._data:
            self._data[CONF_LOADS] = []

        if user_input is not None:
            if user_input.get(CONF_LOAD_NAME) and user_input.get(CONF_LOAD_ENTITY):
                self._data[CONF_LOADS].append(
                    {
                        CONF_LOAD_NAME: user_input[CONF_LOAD_NAME],
                        CONF_LOAD_ENTITY: user_input[CONF_LOAD_ENTITY],
                    }
                )
            if user_input.get("add_another"):
                return await self.async_step_add_load_option()
            return self.async_create_entry(title="", data=self._data)

        schema = vol.Schema(
            {
                vol.Optional(CONF_LOAD_NAME): str,
                vol.Optional(CONF_LOAD_ENTITY): POWER_SENSOR_SELECTOR,
                vol.Optional("add_another", default=False): bool,
            }
        )
        return self.async_show_form(
            step_id="add_load_option",
            data_schema=schema,
            description_placeholders={"count": str(len(self._data[CONF_LOADS]))},
        )
