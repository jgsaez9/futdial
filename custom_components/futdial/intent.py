"""Intent para Assist: «¿en qué canal echan el Atleti?»."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import intent

from . import get_entry, resultado_busqueda
from .const import INTENT_BUSCAR


async def async_setup_intents(hass: HomeAssistant) -> None:
    """Registra el intent de búsqueda."""
    intent.async_register(hass, BuscarPartidoIntent())


class BuscarPartidoIntent(intent.IntentHandler):
    """Responde con el canal y dial donde se emite un partido."""

    intent_type = INTENT_BUSCAR
    description = "Dice en qué canal y dial de Movistar Plus+ se emite un partido de fútbol"
    slot_schema = {"partido": intent.non_empty_string}

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        hass = intent_obj.hass
        slots = self.async_validate_slots(intent_obj.slots)
        consulta = slots["partido"]["value"]
        response = intent_obj.create_response()
        try:
            entry = get_entry(hass)
        except ServiceValidationError:
            response.async_set_speech("La integración FutDial no está cargada.")
            return response
        result = resultado_busqueda(hass, entry, consulta, max_resultados=3)
        response.async_set_speech(result["texto"])
        return response
