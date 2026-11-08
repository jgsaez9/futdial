"""Sensores de FutDial."""

from __future__ import annotations

from datetime import timedelta
from enum import StrEnum
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
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
from .teams import resolver_equipo

MAX_LISTA = 40


class Tipo(StrEnum):
    """Qué muestra cada sensor de un partido."""

    CANAL = "canal"  # "M+ LALIGA - 54"
    DIAL = "dial"  # 54
    FECHA = "fecha"  # 2026-11-08T21:00:00+01:00 (timestamp)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FutDialConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Crea los sensores."""
    entities: list[SensorEntity] = [PartidosHoySensor(entry)]
    entities.extend(BusquedaSensor(entry, tipo) for tipo in Tipo)
    for valor in dict.fromkeys(e.strip() for e in entry.options.get(CONF_EQUIPOS, [])):
        if valor:
            entities.extend(EquipoSensor(entry, valor, tipo) for tipo in Tipo)
    async_add_entities(entities)


class _PartidoSensor(FutDialEntity, SensorEntity):
    """Sensor que muestra el canal, el dial o la fecha del próximo partido."""

    def __init__(self, entry: FutDialConfigEntry, key: str, tipo: Tipo) -> None:
        super().__init__(entry, key if tipo is Tipo.CANAL else f"{key}_{tipo}")
        self._tipo = tipo
        if tipo is Tipo.FECHA:
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
            self._attr_icon = "mdi:calendar-clock"
        elif tipo is Tipo.DIAL:
            self._attr_icon = "mdi:remote-tv"
        else:
            self._attr_icon = "mdi:soccer"

    def _consulta(self) -> str:
        raise NotImplementedError

    @callback
    def _recalcular(self) -> None:
        consulta = self._consulta()
        if self.coordinator.data is None or not consulta:
            # Guía aún no descargada o búsqueda vacía
            self._attr_native_value = None
            self._attr_extra_state_attributes = {"consulta": consulta}
            return

        r = resultado_busqueda(self.hass, self._entry, consulta, max_resultados=10)
        p: dict[str, Any] = r["partidos"][0] if r["partidos"] else {}

        if self._tipo is Tipo.CANAL:
            self._attr_native_value = r["resultado"] or SIN_EMISION
        elif self._tipo is Tipo.DIAL:
            self._attr_native_value = p.get("dial")
        else:
            self._attr_native_value = (
                dt_util.parse_datetime(p["inicio"]) if p.get("inicio") else None
            )

        attrs: dict[str, Any] = {
            "consulta": consulta,
            "equipo": r["equipo"],
            "partido": p.get("partido"),
            "competicion": p.get("competicion"),
            "canal": p.get("canal"),
            "dial": p.get("dial"),
            "canal_dial": p.get("canal_dial"),
            "fecha": p.get("fecha"),
            "hora": p.get("hora"),
            "fecha_hora": p.get("fecha_hora"),
            "cuando": p.get("cuando"),
            "en_juego": p.get("en_juego", False),
        }
        if self._tipo is Tipo.CANAL:
            attrs.update(
                {
                    "todos_los_canales": p.get("todos_los_canales"),
                    "inicio": p.get("inicio"),
                    "fin": p.get("fin"),
                    "texto": r["texto"],
                    "otros_partidos": r["partidos"][1:],
                }
            )
        self._attr_extra_state_attributes = attrs


_NOMBRES = {
    Tipo.CANAL: "Próximo partido {}",
    Tipo.DIAL: "Dial {}",
    Tipo.FECHA: "Fecha partido {}",
}


class EquipoSensor(_PartidoSensor):
    """Próximo partido de un equipo seguido."""

    def __init__(self, entry: FutDialConfigEntry, valor: str, tipo: Tipo) -> None:
        equipo = resolver_equipo(valor)
        key = equipo.id if equipo else slugify(valor)
        super().__init__(entry, f"equipo_{key}", tipo)
        self._valor = valor
        self._attr_name = _NOMBRES[tipo].format(equipo.nombre if equipo else valor)

    def _consulta(self) -> str:
        return self._valor


class BusquedaSensor(_PartidoSensor):
    """Resultado de la búsqueda escrita en la entidad de texto o el servicio."""

    def __init__(self, entry: FutDialConfigEntry, tipo: Tipo) -> None:
        super().__init__(entry, "resultado_busqueda", tipo)
        self._attr_name = {
            Tipo.CANAL: "Resultado búsqueda",
            Tipo.DIAL: "Resultado búsqueda dial",
            Tipo.FECHA: "Resultado búsqueda fecha",
        }[tipo]
        if tipo is Tipo.CANAL:
            self._attr_icon = "mdi:television-guide"

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
        if coordinator.data is None:
            self._attr_native_value = None
            self._attr_extra_state_attributes = {}
            return
        ahora = dt_util.utcnow()
        tz = dt_util.get_default_time_zone()
        fin_dia = dt_util.start_of_local_day(dt_util.now() + timedelta(days=1))
        emisiones = filtrar(
            coordinator.data, ahora, coordinator.incluir_repeticiones, hasta=fin_dia
        )
        partidos = agrupar(emisiones)
        partidos.sort(key=lambda p: (p.inicio, p.principal.dial))
        lista: list[dict[str, Any]] = [
            {
                "hora": p.inicio.astimezone(tz).strftime("%H:%M"),
                "partido": p.partido,
                "competicion": p.competicion,
                "canal_dial": p.canal_dial,
                "dial": p.principal.dial,
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
