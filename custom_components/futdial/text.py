"""Entidad de texto para escribir el partido a buscar."""

from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import set_query
from .const import DOMAIN, NAME, SIGNAL_QUERY_UPDATED
from .coordinator import FutDialConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FutDialConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Crea la entidad de búsqueda."""
    async_add_entities([BuscarPartidoText(entry)])


class BuscarPartidoText(TextEntity, RestoreEntity):
    """Escribe un equipo (p. ej. 'Atleti Barça') y mira el sensor de resultado."""

    _attr_has_entity_name = True
    _attr_name = "Buscar partido"
    _attr_icon = "mdi:magnify"
    _attr_native_max = 100
    _attr_native_value = ""

    def __init__(self, entry: FutDialConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_buscar_partido"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=NAME,
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state not in ("unknown", "unavailable"):
            self._attr_native_value = last.state
            set_query(self.hass, self._entry, last.state)
        # Si se busca desde el servicio, refleja la consulta aquí también
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, f"{SIGNAL_QUERY_UPDATED}_{self._entry.entry_id}", self._sync
            )
        )

    @callback
    def _sync(self) -> None:
        if self._entry.runtime_data.consulta != self._attr_native_value:
            self._attr_native_value = self._entry.runtime_data.consulta
            self.async_write_ha_state()

    async def async_set_value(self, value: str) -> None:
        self._attr_native_value = value.strip()
        self.async_write_ha_state()
        set_query(self.hass, self._entry, self._attr_native_value)
