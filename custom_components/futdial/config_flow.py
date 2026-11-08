"""Flujo de configuración de FutDial."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_DIAS,
    CONF_EQUIPOS,
    CONF_INTERVALO,
    CONF_REPETICIONES,
    DEFAULT_DIAS,
    DEFAULT_INTERVALO,
    DEFAULT_REPETICIONES,
    DOMAIN,
    NAME,
)


def _schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(
                CONF_EQUIPOS, default=defaults.get(CONF_EQUIPOS, [])
            ): selector.TextSelector(selector.TextSelectorConfig(multiple=True)),
            vol.Required(
                CONF_DIAS, default=defaults.get(CONF_DIAS, DEFAULT_DIAS)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1, max=7, step=1, mode=selector.NumberSelectorMode.SLIDER
                )
            ),
            vol.Required(
                CONF_INTERVALO, default=defaults.get(CONF_INTERVALO, DEFAULT_INTERVALO)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=30,
                    max=720,
                    step=10,
                    unit_of_measurement="min",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_REPETICIONES,
                default=defaults.get(CONF_REPETICIONES, DEFAULT_REPETICIONES),
            ): selector.BooleanSelector(),
        }
    )


def _clean(user_input: dict[str, Any]) -> dict[str, Any]:
    data = dict(user_input)
    data[CONF_EQUIPOS] = [e.strip() for e in data.get(CONF_EQUIPOS, []) if e and e.strip()]
    data[CONF_DIAS] = int(data[CONF_DIAS])
    data[CONF_INTERVALO] = int(data[CONF_INTERVALO])
    return data


class FutDialConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configuración inicial."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title=NAME, data={}, options=_clean(user_input))
        return self.async_show_form(step_id="user", data_schema=_schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return FutDialOptionsFlow()


class FutDialOptionsFlow(OptionsFlow):
    """Opciones: equipos seguidos, días, intervalo y repeticiones."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=_clean(user_input))
        return self.async_show_form(
            step_id="init", data_schema=_schema(dict(self.config_entry.options))
        )
