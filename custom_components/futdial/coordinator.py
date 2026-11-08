"""Coordinador que descarga la guía de Movistar Plus+."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_DIAS,
    CONF_INTERVALO,
    CONF_REPETICIONES,
    DEFAULT_DIAS,
    DEFAULT_INTERVALO,
    DEFAULT_REPETICIONES,
    DOMAIN,
    FAR_DAYS_MAX_AGE,
)
from .epg import Emision, EpgError, Partido, buscar, fetch_day, parse_epg

_LOGGER = logging.getLogger(__name__)


@dataclass
class _DayCache:
    fetched: datetime
    emisiones: list[Emision]


@dataclass
class RuntimeData:
    """Datos en memoria de la entrada de configuración."""

    coordinator: FutDialCoordinator
    consulta: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


type FutDialConfigEntry = ConfigEntry[RuntimeData]


class FutDialCoordinator(DataUpdateCoordinator[list[Emision]]):
    """Descarga la EPG de varios días y se queda sólo con el fútbol."""

    config_entry: FutDialConfigEntry

    def __init__(self, hass: HomeAssistant, entry: FutDialConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                minutes=int(entry.options.get(CONF_INTERVALO, DEFAULT_INTERVALO))
            ),
        )
        self.dias = int(entry.options.get(CONF_DIAS, DEFAULT_DIAS))
        self.incluir_repeticiones = bool(
            entry.options.get(CONF_REPETICIONES, DEFAULT_REPETICIONES)
        )
        self._cache: dict[date, _DayCache] = {}
        self._session = async_get_clientsession(hass)

    async def _async_update_data(self) -> list[Emision]:
        now = dt_util.now()
        today = now.date()
        days = [today + timedelta(days=i) for i in range(self.dias)]
        errors: list[str] = []

        for i, day in enumerate(days):
            cached = self._cache.get(day)
            # Hoy y mañana siempre; los siguientes, cada FAR_DAYS_MAX_AGE
            if cached and i >= 2 and now - cached.fetched < FAR_DAYS_MAX_AGE:
                continue
            try:
                raw = await fetch_day(self._session, day)
                emisiones = await self.hass.async_add_executor_job(parse_epg, raw)
                del raw
            except EpgError as err:
                errors.append(str(err))
                _LOGGER.warning("%s", err)
                continue
            self._cache[day] = _DayCache(now, emisiones)

        # Descarta días pasados (salvo ayer, por partidos que cruzan medianoche)
        for day in list(self._cache):
            if day < today - timedelta(days=1) or day > days[-1]:
                del self._cache[day]

        if not self._cache:
            raise UpdateFailed("; ".join(errors) or "No se pudo descargar la EPG")

        seen: set[int] = set()
        result: list[Emision] = []
        for day in sorted(self._cache):
            for em in self._cache[day].emisiones:
                key = em.id or hash((em.dial, em.inicio, em.partido))
                if key not in seen:
                    seen.add(key)
                    result.append(em)
        result.sort(key=lambda e: (e.inicio, e.dial))
        _LOGGER.debug("EPG actualizada: %d emisiones de fútbol", len(result))
        return result

    def buscar(self, consulta: str, incluir_repeticiones: bool | None = None) -> list[Partido]:
        """Busca un partido en los datos ya descargados."""
        if incluir_repeticiones is None:
            incluir_repeticiones = self.incluir_repeticiones
        return buscar(self.data or [], consulta, dt_util.utcnow(), incluir_repeticiones)
