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
    CONF_CODIGOS,
    CONF_DIAS,
    CONF_DISPOSITIVO,
    CONF_MANDO,
    CONF_MODO_MANDO,
    CONF_PLANTILLA,
    CONF_RETARDO,
    CONF_TECLA_FINAL,
    CONF_EQUIPOS,
    CONF_INTERVALO,
    CONF_REPETICIONES,
    CONF_TODOS_CANALES,
    DEFAULT_DIAS,
    DEFAULT_INTERVALO,
    DEFAULT_PLANTILLA,
    DEFAULT_REPETICIONES,
    DEFAULT_RETARDO,
    DEFAULT_TODOS_CANALES,
    DOMAIN,
    INTERVALOS,
    MAX_DIAS,
    MODO_CODIGOS,
    MODO_MOVISTAR,
    MODO_PLANTILLA,
    NAME,
)
from .mando import codigo_valido, normalizar_codigo
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
    """Opciones: «General» (equipos, intervalo…) y «Mando» (poner el canal)."""

    def __init__(self) -> None:
        self._mando: dict[str, Any] = {}

    def _guardar(self, cambios: dict[str, Any]) -> ConfigFlowResult:
        return self.async_create_entry(data={**self.config_entry.options, **cambios})

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(step_id="init", menu_options=["general", "mando"])

    async def async_step_general(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self._guardar(_clean(user_input))
        return self.async_show_form(
            step_id="general", data_schema=_schema(dict(self.config_entry.options))
        )

    async def async_step_mando(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        opts = self.config_entry.options
        if user_input is not None:
            self._mando = {
                CONF_MANDO: user_input.get(CONF_MANDO) or "",
                CONF_MODO_MANDO: user_input[CONF_MODO_MANDO],
                CONF_RETARDO: float(user_input[CONF_RETARDO]),
            }
            if (
                not self._mando[CONF_MANDO]  # sin mando: se desactiva la función
                or self._mando[CONF_MODO_MANDO] == MODO_MOVISTAR  # códigos incluidos
            ):
                return self._guardar(self._mando)
            if self._mando[CONF_MODO_MANDO] == MODO_PLANTILLA:
                return await self.async_step_plantilla()
            return await self.async_step_codigos()

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_MANDO, description={"suggested_value": opts.get(CONF_MANDO)}
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="remote")),
                vol.Required(
                    CONF_MODO_MANDO, default=opts.get(CONF_MODO_MANDO, MODO_MOVISTAR)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=MODO_MOVISTAR,
                                label="Descodificador Movistar+ (códigos incluidos, Broadlink)",
                            ),
                            selector.SelectOptionDict(
                                value=MODO_CODIGOS, label="Mis propios códigos IR por dígito (Broadlink b64)"
                            ),
                            selector.SelectOptionDict(
                                value=MODO_PLANTILLA,
                                label="Plantilla de comando (comandos aprendidos, Android TV…)",
                            ),
                        ],
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
                vol.Required(
                    CONF_RETARDO, default=float(opts.get(CONF_RETARDO, DEFAULT_RETARDO))
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.1, max=3, step=0.1, unit_of_measurement="s",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="mando", data_schema=schema)

    async def async_step_codigos(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        opts = self.config_entry.options
        errors: dict[str, str] = {}
        if user_input is not None:
            for clave in [*CONF_CODIGOS, CONF_TECLA_FINAL]:
                if not codigo_valido(user_input.get(clave, "")):
                    errors[clave] = "codigo_invalido"
            if not errors:
                codigos = {
                    clave: normalizar_codigo(user_input.get(clave))
                    for clave in [*CONF_CODIGOS, CONF_TECLA_FINAL]
                }
                return self._guardar({**self._mando, **codigos})

        valores = user_input or opts
        texto = selector.TextSelector(selector.TextSelectorConfig(multiline=False))
        schema = vol.Schema(
            {
                vol.Optional(
                    clave, description={"suggested_value": valores.get(clave) or None}
                ): texto
                for clave in [*CONF_CODIGOS, CONF_TECLA_FINAL]
            }
        )
        return self.async_show_form(step_id="codigos", data_schema=schema, errors=errors)

    async def async_step_plantilla(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        opts = self.config_entry.options
        errors: dict[str, str] = {}
        if user_input is not None:
            plantilla = (user_input.get(CONF_PLANTILLA) or "").strip()
            if "{digito}" not in plantilla:
                errors[CONF_PLANTILLA] = "plantilla_invalida"
            else:
                return self._guardar(
                    {
                        **self._mando,
                        CONF_PLANTILLA: plantilla,
                        CONF_DISPOSITIVO: (user_input.get(CONF_DISPOSITIVO) or "").strip(),
                        CONF_TECLA_FINAL: (user_input.get(CONF_TECLA_FINAL) or "").strip(),
                    }
                )
        valores = user_input or opts
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_PLANTILLA,
                    default=valores.get(CONF_PLANTILLA) or DEFAULT_PLANTILLA,
                ): selector.TextSelector(),
                vol.Optional(
                    CONF_DISPOSITIVO,
                    description={"suggested_value": valores.get(CONF_DISPOSITIVO) or None},
                ): selector.TextSelector(),
                vol.Optional(
                    CONF_TECLA_FINAL,
                    description={"suggested_value": valores.get(CONF_TECLA_FINAL) or None},
                ): selector.TextSelector(),
            }
        )
        return self.async_show_form(
            step_id="plantilla",
            data_schema=schema,
            errors=errors,
            description_placeholders={"digito": "{digito}"},
        )
