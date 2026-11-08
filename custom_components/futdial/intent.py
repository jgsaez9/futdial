"""Intents para Assist.

- «¿En qué canal echan el Atleti?»  → dice canal, dial y hora.
- «Pon el partido del Atleti»        → además lo pone en la tele.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import intent

from . import get_entry, resultado_busqueda, sintonizar_partido
from .const import INTENT_BUSCAR, INTENT_SINTONIZAR


async def async_setup_intents(hass: HomeAssistant) -> None:
    """Registra los intents."""
    intent.async_register(hass, BuscarPartidoIntent())
    intent.async_register(hass, SintonizarIntent())


class BuscarPartidoIntent(intent.IntentHandler):
    """Responde con el canal y dial donde se emite un partido."""

    intent_type = INTENT_BUSCAR
    description = "Dice en qué canal y dial de Movistar Plus+ se emite un partido de fútbol"
    slot_schema = {"partido": intent.non_empty_string}

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        hass = intent_obj.hass
        consulta = self.async_validate_slots(intent_obj.slots)["partido"]["value"]
        response = intent_obj.create_response()
        try:
            entry = get_entry(hass)
        except HomeAssistantError:
            response.async_set_speech("La integración FutDial no está cargada.")
            return response
        result = resultado_busqueda(hass, entry, consulta, max_resultados=3)
        response.async_set_speech(result["texto"])
        return response


class SintonizarIntent(intent.IntentHandler):
    """Pone en la tele el canal del partido pedido."""

    intent_type = INTENT_SINTONIZAR
    description = (
        "Pone en el descodificador de Movistar Plus+ el canal donde se emite "
        "el partido de fútbol de un equipo"
    )
    slot_schema = {"partido": intent.non_empty_string}

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        hass = intent_obj.hass
        consulta = self.async_validate_slots(intent_obj.slots)["partido"]["value"]
        response = intent_obj.create_response()
        try:
            result = await sintonizar_partido(hass, get_entry(hass), consulta)
        except HomeAssistantError as err:
            # Sin partido, sin mando, falta un código...: se explica en voz
            response.async_set_speech(str(err))
            return response
        response.async_set_speech(result["texto"])
        return response
