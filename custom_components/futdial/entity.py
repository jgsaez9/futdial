"""Entidad base de FutDial."""

from __future__ import annotations

from datetime import datetime

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NAME, TICK_INTERVAL
from .coordinator import FutDialConfigEntry, FutDialCoordinator


class FutDialEntity(CoordinatorEntity[FutDialCoordinator]):
    """Base: dispositivo común y recálculo periódico con el reloj."""

    _attr_has_entity_name = True

    def __init__(self, entry: FutDialConfigEntry, key: str) -> None:
        super().__init__(entry.runtime_data.coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=NAME,
            manufacturer="Movistar Plus+ (guía de TV)",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://www.movistarplus.es/programacion-tv",
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_interval(self.hass, self._tick, TICK_INTERVAL)
        )
        self._recalcular()

    @callback
    def _tick(self, _now: datetime) -> None:
        self._recalcular()
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._recalcular()
        super()._handle_coordinator_update()

    @callback
    def _recalcular(self) -> None:
        """Recalcula estado y atributos a partir de los datos y la hora."""
