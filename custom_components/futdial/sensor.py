"""Sensores de FutDial."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from . import resultado_busqueda
from .const import CONF_EQUIPOS, SIGNAL_QUERY_UPDATED, SIN_EMISION
from .coordinator import FutDialConfigEntry
from .entity import FutDialEntity
from .epg import agrupar, filtrar

MAX_LISTA = 40


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FutDialConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Crea los sensores."""
    entities: list[SensorEntity] = [
        PartidosHoySensor(entry),
        ResultadoBusquedaSensor(entry),
    ]
    equipos = [e.strip() for e in entry.options.get(CONF_EQUIPOS, []) if e.strip()]
    entities.extend(EquipoSensor(entry, equipo) for equipo in dict.fromkeys(equipos))
    async_add_entities(entities)


class _BusquedaBase(FutDialEntity, SensorEntity):
    """Sensor cuyo estado es 'CANAL - DIAL' del partido encontrado."""

    _attr_icon = "mdi:soccer"

    def _consulta(self) -> str:
        raise NotImplementedError

    @callback
    def _recalcular(self) -> None:
        consulta = self._consulta()
        if not consulta:
            self._attr_native_value = None
            self._attr_extra_state_attributes = {"consulta": ""}
            return
        r = resultado_busqueda(self.hass, self._entry, consulta, max_resultados=10)
        primero = r["partidos"][0] if r["partidos"] else {}
        self._attr_native_value = r["resultado"] or SIN_EMISION
        self._attr_extra_state_attributes = {
            "consulta": consulta,
            "partido": primero.get("partido"),
            "competicion": primero.get("competicion"),
            "canal": primero.get("canal"),
            "dial": primero.get("dial"),
            "todos_los_canales": primero.get("todos_los_canales"),
            "inicio": primero.get("inicio"),
            "cuando": primero.get("cuando"),
            "en_juego": primero.get("en_juego", False),
            "texto": r["texto"],
            "otros_partidos": r["partidos"][1:],
        }


class EquipoSensor(_BusquedaBase):
    """Próximo partido de un equipo seguido."""

    def __init__(self, entry: FutDialConfigEntry, equipo: str) -> None:
        super().__init__(entry, f"equipo_{slugify(equipo)}")
        self._equipo = equipo
        self._attr_name = f"Próximo partido {equipo}"

    def _consulta(self) -> str:
        return self._equipo


class ResultadoBusquedaSensor(_BusquedaBase):
    """Resultado de la búsqueda escrita en la entidad de texto o el servicio."""

    _attr_name = "Resultado búsqueda"
    _attr_icon = "mdi:television-guide"

    def __init__(self, entry: FutDialConfigEntry) -> None:
        super().__init__(entry, "resultado_busqueda")

    def _consulta(self) -> str:
        return self._entry.runtime_data.consulta

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_QUERY_UPDATED}_{self._entry.entry_id}",
                self._on_query,
            )
        )

    @callback
    def _on_query(self) -> None:
        self._recalcular()
        self.async_write_ha_state()


class PartidosHoySensor(FutDialEntity, SensorEntity):
    """Número de partidos de hoy (pendientes o en juego) y su lista."""

    _attr_name = "Partidos hoy"
    _attr_icon = "mdi:scoreboard"
    _attr_native_unit_of_measurement = "partidos"

    def __init__(self, entry: FutDialConfigEntry) -> None:
        super().__init__(entry, "partidos_hoy")

    @callback
    def _recalcular(self) -> None:
        coordinator = self.coordinator
        ahora = dt_util.utcnow()
        tz = dt_util.get_default_time_zone()
        local = dt_util.now()
        fin_dia = dt_util.start_of_local_day(local + timedelta(days=1))
        emisiones = filtrar(
            coordinator.data or [], ahora, coordinator.incluir_repeticiones, hasta=fin_dia
        )
        partidos = agrupar(emisiones)
        partidos.sort(key=lambda p: (p.inicio, p.principal.dial))
        lista: list[dict[str, Any]] = [
            {
                "hora": p.inicio.astimezone(tz).strftime("%H:%M"),
                "partido": p.partido,
                "competicion": p.competicion,
                "canal_dial": p.canal_dial,
                "todos_los_canales": p.todos_los_canales,
                "en_juego": p.en_juego(ahora),
            }
            for p in partidos
        ]
        self._attr_native_value = len(lista)
        self._attr_extra_state_attributes = {
            "en_juego": [p for p in lista if p["en_juego"]],
            "partidos": lista[:MAX_LISTA],
        }
