"""Interruptor para activar o pausar el «poner partidos automáticamente»."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .auto import auto_configurado
from .const import DOMAIN, NAME
from .coordinator import FutDialConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FutDialConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Crea el interruptor si hay equipos para poner automáticamente."""
    if auto_configurado(entry.options):
        async_add_entities([AutoSwitch(entry)])


class AutoSwitch(SwitchEntity, RestoreEntity):
    """Activa o pausa el cambio de canal automático (sin tocar la configuración)."""

    _attr_has_entity_name = True
    _attr_name = "Poner partidos automáticamente"
    _attr_icon = "mdi:television-play"

    def __init__(self, entry: FutDialConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_auto"
        self._attr_is_on = True
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=NAME,
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) and last.state == STATE_OFF:
            self._attr_is_on = False
        self._aplicar()

    def _aplicar(self) -> None:
        if (auto := self._entry.runtime_data.auto) is not None:
            auto.activar(bool(self._attr_is_on))

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._attr_is_on = True
        self._aplicar()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._attr_is_on = False
        self._aplicar()
        self.async_write_ha_state()
