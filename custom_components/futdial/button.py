"""Botones para poner en la tele el partido de un equipo."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from . import sintonizar_partido
from .const import CONF_EQUIPOS, DOMAIN, NAME
from .coordinator import FutDialConfigEntry
from .mando import mando_configurado
from .teams import resolver_equipo


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FutDialConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Crea un botón por equipo seguido y otro para la búsqueda (si hay mando)."""
    if not mando_configurado(entry.options):
        return
    botones: list[ButtonEntity] = [PonerBusquedaButton(entry)]
    for valor in dict.fromkeys(e.strip() for e in entry.options.get(CONF_EQUIPOS, [])):
        if valor:
            botones.append(PonerEquipoButton(entry, valor))
    async_add_entities(botones)


class _PonerButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:remote-tv"

    def __init__(self, entry: FutDialConfigEntry, key: str) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=NAME,
            entry_type=DeviceEntryType.SERVICE,
        )

    def _consulta(self) -> str:
        raise NotImplementedError

    async def async_press(self) -> None:
        await sintonizar_partido(self.hass, self._entry, self._consulta())


class PonerEquipoButton(_PonerButton):
    """Pone el canal del próximo partido de un equipo."""

    def __init__(self, entry: FutDialConfigEntry, valor: str) -> None:
        equipo = resolver_equipo(valor)
        super().__init__(entry, f"poner_{equipo.id if equipo else slugify(valor)}")
        self._valor = valor
        self._attr_name = f"Poner partido {equipo.nombre if equipo else valor}"

    def _consulta(self) -> str:
        return self._valor


class PonerBusquedaButton(_PonerButton):
    """Pone el canal del partido escrito en «Buscar partido»."""

    _attr_name = "Poner resultado búsqueda"

    def __init__(self, entry: FutDialConfigEntry) -> None:
        super().__init__(entry, "poner_busqueda")

    def _consulta(self) -> str:
        return self._entry.runtime_data.consulta
