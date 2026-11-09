"""Coordinador que descarga la guía de Movistar Plus+."""

from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_DIAS,
    CONF_INTERVALO,
    CONF_REPETICIONES,
    CONF_TODOS_CANALES,
    DEFAULT_DIAS,
    DEFAULT_INTERVALO,
    DEFAULT_REPETICIONES,
    DOMAIN,
    FAR_DAYS_MAX_AGE,
    MAX_DIAS,
    RETRY_INTERVAL,
)
from .epg import (
    CANALES_FUTBOL,
    MIN_CANALES_FILTRO,
    Emision,
    EpgError,
    Partido,
    buscar,
    fetch_day,
    marcar_repeticiones,
    parse_epg,
)
from .teams import buscar_equipo, resolver_equipo

if TYPE_CHECKING:
    from .auto import AutoSintonizador

_LOGGER = logging.getLogger(__name__)

# Descargas simultáneas (cada una es un día de guía)
_PARALLEL = 3
STORAGE_VERSION = 1


@dataclass
class _DayCache:
    fetched: datetime
    emisiones: list[Emision]


@dataclass
class RuntimeData:
    """Datos en memoria de la entrada de configuración."""

    coordinator: FutDialCoordinator
    consulta: str = ""
    auto: AutoSintonizador | None = None


type FutDialConfigEntry = ConfigEntry[RuntimeData]


def intervalo_minutos(options: dict) -> int:
    """Intervalo configurado en minutos (acepta valores antiguos numéricos)."""
    try:
        return max(30, int(float(options.get(CONF_INTERVALO, DEFAULT_INTERVALO))))
    except (TypeError, ValueError):
        return int(DEFAULT_INTERVALO)


class FutDialCoordinator(DataUpdateCoordinator[list[Emision]]):
    """Descarga la EPG de varios días y se queda sólo con el fútbol."""

    config_entry: FutDialConfigEntry

    def __init__(self, hass: HomeAssistant, entry: FutDialConfigEntry) -> None:
        minutos = intervalo_minutos(entry.options)
        self._intervalo = timedelta(minutes=minutos)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=self._intervalo,
        )
        dias = int(entry.options.get(CONF_DIAS, DEFAULT_DIAS))
        # Si se actualiza cada X días, hay que descargar al menos X+1 días
        # para que no se quede sin programación entre actualizaciones
        self.dias = min(MAX_DIAS, max(dias, math.ceil(minutos / 1440) + 1))
        self.incluir_repeticiones = bool(
            entry.options.get(CONF_REPETICIONES, DEFAULT_REPETICIONES)
        )
        self.canales: tuple[str, ...] | None = (
            None if entry.options.get(CONF_TODOS_CANALES) else CANALES_FUTBOL
        )
        self._cache: dict[date, _DayCache] = {}
        self._session = async_get_clientsession(hass)
        self._sem = asyncio.Semaphore(_PARALLEL)
        # La programación se guarda en disco para tenerla al reiniciar HA
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}", private=False
        )

    @property
    def intervalo(self) -> timedelta:
        """Intervalo configurado entre descargas."""
        return self._intervalo

    def _firma(self) -> dict[str, Any]:
        """Opciones que cambian qué se descarga (si cambian, la caché no vale)."""
        return {"todos_los_canales": self.canales is None, "dias": self.dias}

    async def async_cargar_cache(self) -> datetime | None:
        """Carga la programación guardada. Devuelve cuándo se descargó.

        Devuelve None si no hay nada útil guardado o si se guardó con otras
        opciones (en ese caso hay que descargar).
        """
        try:
            guardado = await self._store.async_load()
        except Exception:  # noqa: BLE001 - un fichero corrupto no debe impedir arrancar
            _LOGGER.warning("No se pudo leer la programación guardada; se descargará de nuevo")
            return None
        if not guardado:
            return None
        ayer = dt_util.now().date() - timedelta(days=1)
        try:
            for dia_txt, info in guardado.get("dias", {}).items():
                dia = date.fromisoformat(dia_txt)
                if dia < ayer:
                    continue
                self._cache[dia] = _DayCache(
                    datetime.fromisoformat(info["fetched"]),
                    [Emision.from_dict(e) for e in info["emisiones"]],
                )
        except (KeyError, TypeError, ValueError) as err:
            _LOGGER.warning("Programación guardada no válida (%s); se descargará de nuevo", err)
            self._cache.clear()
            return None
        if not self._cache:
            return None
        self.async_set_updated_data(self._combinar())
        hoy = dt_util.now().date()
        if guardado.get("firma") != self._firma() or hoy not in self._cache:
            return None
        return min(
            c.fetched for d, c in self._cache.items() if d in (hoy, hoy + timedelta(days=1))
        )

    def _datos_a_guardar(self) -> dict[str, Any]:
        return {
            "firma": self._firma(),
            "dias": {
                dia.isoformat(): {
                    "fetched": c.fetched.isoformat(),
                    "emisiones": [e.to_dict() for e in c.emisiones],
                }
                for dia, c in self._cache.items()
            },
        }

    def _combinar(self) -> list[Emision]:
        """Une los días en caché, sin duplicados y con repeticiones marcadas."""
        seen: set[int] = set()
        result: list[Emision] = []
        for day in sorted(self._cache):
            for em in self._cache[day].emisiones:
                key = em.id or hash((em.dial, em.inicio, em.partido))
                if key not in seen:
                    seen.add(key)
                    result.append(em)
        result = marcar_repeticiones(result)
        result.sort(key=lambda e: (e.inicio, e.dial))
        return result

    async def _fetch_parse(self, day: date) -> list[Emision]:
        async with self._sem:
            raw = await fetch_day(self._session, day, self.canales)
            emisiones, n_canales = await self.hass.async_add_executor_job(parse_epg, raw)
            del raw
            # Pocos canales => Movistar ha cambiado los códigos: guía completa.
            # Cero canales en días futuros => simplemente aún no hay guía.
            if (
                self.canales
                and n_canales < MIN_CANALES_FILTRO
                and (n_canales > 0 or day <= dt_util.now().date())
            ):
                _LOGGER.warning(
                    "La guía filtrada de %s sólo trae %d canales; "
                    "se descarga la guía completa", day, n_canales
                )
                raw = await fetch_day(self._session, day, None)
                emisiones, _ = await self.hass.async_add_executor_job(parse_epg, raw)
                del raw
            return emisiones

    async def _async_update_data(self) -> list[Emision]:
        now = dt_util.now()
        today = now.date()
        days = [today + timedelta(days=i) for i in range(self.dias)]

        # Hoy y mañana siempre; los siguientes, como mucho cada FAR_DAYS_MAX_AGE
        pendientes = [
            day
            for i, day in enumerate(days)
            if not (
                (cached := self._cache.get(day))
                and i >= 2
                and now - cached.fetched < FAR_DAYS_MAX_AGE
            )
        ]
        resultados = await asyncio.gather(
            *(self._fetch_parse(day) for day in pendientes), return_exceptions=True
        )
        errores: list[str] = []
        for day, res in zip(pendientes, resultados, strict=True):
            if isinstance(res, EpgError):
                errores.append(str(res))
                _LOGGER.warning("%s", res)
            elif isinstance(res, BaseException):
                errores.append(f"{day}: {res!r}")
                _LOGGER.exception("Error inesperado procesando la guía de %s", day, exc_info=res)
            else:
                self._cache[day] = _DayCache(now, res)

        # Descarta días pasados (salvo ayer, por partidos que cruzan medianoche)
        for day in list(self._cache):
            if day < today - timedelta(days=1) or day > days[-1]:
                del self._cache[day]

        # Si algo falló, reintenta pronto en lugar de esperar al intervalo
        # (que puede ser de días); mientras, se sigue usando lo que hay
        self.update_interval = RETRY_INTERVAL if errores else self._intervalo
        if not self._cache:
            raise UpdateFailed("; ".join(errores) or "No se pudo descargar la guía")

        result = self._combinar()
        self._store.async_delay_save(self._datos_a_guardar, 5)
        _LOGGER.debug(
            "Guía actualizada: %d emisiones de fútbol en %d días", len(result), len(self._cache)
        )
        return result

    def partidos(self, consulta: str, incluir_repeticiones: bool | None = None) -> list[Partido]:
        """Partidos para un equipo del catálogo o un texto libre."""
        if incluir_repeticiones is None:
            incluir_repeticiones = self.incluir_repeticiones
        ahora = dt_util.utcnow()
        datos = self.data or []
        if equipo := resolver_equipo(consulta):
            return buscar_equipo(datos, equipo, ahora, incluir_repeticiones)
        return buscar(datos, consulta, ahora, incluir_repeticiones)
