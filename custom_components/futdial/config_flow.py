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
    CONF_TODOS_CANALES,
    DEFAULT_DIAS,
    DEFAULT_INTERVALO,
    DEFAULT_REPETICIONES,
    DEFAULT_TODOS_CANALES,
    DOMAIN,
    INTERVALOS,
    MAX_DIAS,
    NAME,
)
from .teams import EQUIPOS_LISTA, etiqueta, resolver_equipo

_OPCIONES_EQUIPOS = [
    selector.SelectOptionDict(value=e.id, label=etiqueta(e)) for e in EQUIPOS_LISTA
]
_OPCIONES_INTERVALO = [
    selector.SelectOptionDict(value=v, label=label) for v, label in INTERVALOS
]
_VALORES_INTERVALO = {v for v, _ in INTERVALOS}


def _intervalo_default(value: Any) -> str:
    """Convierte valores antiguos (p. ej. 120 numérico) a una opción válida."""
    try:
        minutos = int(float(value))
    except (TypeError, ValueError):
        return DEFAULT_INTERVALO
    if str(minutos) in _VALORES_INTERVALO:
        return str(minutos)
    # El más cercano
    return min(_VALORES_INTERVALO, key=lambda v: abs(int(v) - minutos))


def _equipos_default(values: list[str]) -> list[str]:
    """Equipos guardados; los textos libres de versiones antiguas se migran."""
    out: list[str] = []
    for v in values or []:
        equipo = resolver_equipo(v)
        out.append(equipo.id if equipo else v)
    return list(dict.fromkeys(out))


def _schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(
                CONF_EQUIPOS, default=_equipos_default(defaults.get(CONF_EQUIPOS, []))
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=_OPCIONES_EQUIPOS,
                    multiple=True,
                    custom_value=True,
                    sort=False,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                CONF_INTERVALO,
                default=_intervalo_default(defaults.get(CONF_INTERVALO, DEFAULT_INTERVALO)),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=_OPCIONES_INTERVALO,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                CONF_DIAS, default=int(defaults.get(CONF_DIAS, DEFAULT_DIAS))
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1, max=MAX_DIAS - 1, step=1, mode=selector.NumberSelectorMode.SLIDER
                )
            ),
            vol.Required(
                CONF_REPETICIONES,
                default=defaults.get(CONF_REPETICIONES, DEFAULT_REPETICIONES),
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_TODOS_CANALES,
                default=defaults.get(CONF_TODOS_CANALES, DEFAULT_TODOS_CANALES),
            ): selector.BooleanSelector(),
        }
    )


def _clean(user_input: dict[str, Any]) -> dict[str, Any]:
    data = dict(user_input)
    data[CONF_EQUIPOS] = _equipos_default(
        [e.strip() for e in data.get(CONF_EQUIPOS, []) if e and e.strip()]
    )
    data[CONF_DIAS] = int(data[CONF_DIAS])
    data[CONF_INTERVALO] = _intervalo_default(data[CONF_INTERVALO])
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
    """Opciones: equipos seguidos, intervalo, días, repeticiones y canales."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=_clean(user_input))
        return self.async_show_form(
            step_id="init", data_schema=_schema(dict(self.config_entry.options))
        )
