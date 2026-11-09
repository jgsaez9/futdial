"""Notificaciones push (app de Home Assistant) al poner un partido solo."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, TemplateError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.template import Template
from homeassistant.util import slugify

from .const import (
    CONF_AUTO_MENSAJE,
    CONF_AUTO_NOTIFICAR,
    CONF_AUTO_TITULO,
    DEFAULT_AUTO_MENSAJE,
    DEFAULT_AUTO_TITULO,
)

_LOGGER = logging.getLogger(__name__)

# Variables disponibles en las plantillas (se muestran en la configuración)
VARIABLES = (
    "partido, local, visitante, equipo, competicion, canal, dial, canal_dial, "
    "hora, fecha, fecha_hora, cuando, minutos"
)


def plantilla_valida(hass: HomeAssistant, texto: str) -> bool:
    """Comprueba que la plantilla Jinja se puede compilar."""
    try:
        Template(texto, hass).ensure_valid()
    except TemplateError:
        return False
    return True


def servicios_notify(hass: HomeAssistant, dispositivos: list[str]) -> list[str]:
    """Servicios `notify.mobile_app_*` de los dispositivos elegidos."""
    registro = dr.async_get(hass)
    servicios: list[str] = []
    for device_id in dispositivos:
        device = registro.async_get(device_id)
        if device is None:
            _LOGGER.warning("El dispositivo %s ya no existe; quítalo de FutDial", device_id)
            continue
        nombres = [
            entry.data.get("device_name")
            for entry_id in device.config_entries
            if (entry := hass.config_entries.async_get_entry(entry_id))
            and entry.domain == "mobile_app"
        ]
        nombres += [device.name, device.name_by_user]
        for nombre in filter(None, nombres):
            servicio = f"mobile_app_{slugify(nombre)}"
            if hass.services.has_service("notify", servicio):
                servicios.append(servicio)
                break
        else:
            _LOGGER.warning(
                "No encuentro el servicio de notificación de %s", device.name_by_user or device.name
            )
    return list(dict.fromkeys(servicios))


def _render(hass: HomeAssistant, texto: str, defecto: str, variables: dict[str, Any]) -> str:
    try:
        return str(Template(texto, hass).async_render(variables, parse_result=False))
    except TemplateError as err:
        _LOGGER.warning("Plantilla de notificación no válida (%s); se usa la de por defecto", err)
        return str(Template(defecto, hass).async_render(variables, parse_result=False))


async def async_notificar(
    hass: HomeAssistant,
    options: dict[str, Any],
    variables: dict[str, Any],
    error: str | None = None,
) -> int:
    """Envía la notificación a los dispositivos elegidos. Devuelve a cuántos."""
    servicios = servicios_notify(hass, options.get(CONF_AUTO_NOTIFICAR) or [])
    if not servicios:
        return 0
    titulo = _render(
        hass, options.get(CONF_AUTO_TITULO) or DEFAULT_AUTO_TITULO, DEFAULT_AUTO_TITULO, variables
    )
    if error:
        mensaje = (
            f"No he podido poner {variables['partido']} ({variables['canal_dial']}): {error}"
        )
    else:
        mensaje = _render(
            hass,
            options.get(CONF_AUTO_MENSAJE) or DEFAULT_AUTO_MENSAJE,
            DEFAULT_AUTO_MENSAJE,
            variables,
        )
    enviados = 0
    for servicio in servicios:
        try:
            await hass.services.async_call(
                "notify",
                servicio,
                {"title": titulo, "message": mensaje, "data": {"tag": "futdial"}},
                blocking=True,
            )
            enviados += 1
        except HomeAssistantError as err:
            _LOGGER.warning("No se pudo notificar a %s: %s", servicio, err)
    return enviados
