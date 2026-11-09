"""Poner los partidos en la tele automáticamente, X minutos antes.

Los equipos se eligen en orden de preferencia. Si dos partidos coinciden,
manda el del equipo con más preferencia:

- Un partido no se pone si a esa hora ya está puesto (o se va a poner a la
  vez) el de un equipo con más preferencia.
- Si mientras se ve el de un equipo con menos preferencia empieza el de uno
  con más, se cambia a ese.
- Si los dos equipos juegan el mismo partido, se pone una sola vez.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util import dt as dt_util

from .const import (
    CONF_AUTO_EQUIPOS,
    CONF_AUTO_MINUTOS,
    CONF_EQUIPOS,
    DEFAULT_AUTO_MINUTOS,
    DOMAIN,
    EVENT_AUTO,
    SIGNAL_AUTO_UPDATED,
)
from .epg import Partido
from .mando import async_sintonizar, mando_configurado
from .teams import resolver_equipo

_LOGGER = logging.getLogger(__name__)

# Si HA estaba ocupado y el temporizador llega algo tarde, aún se pone
_MARGEN = timedelta(minutes=2)


@dataclass(slots=True)
class Programado:
    """Un partido que se pondrá (o se ha descartado) automáticamente."""

    equipo: str
    prioridad: int  # 1 = el preferido
    partido: Partido
    momento: datetime  # cuándo se pone (inicio - X minutos)
    motivo: str | None = None  # por qué se descarta
    clave: str = field(init=False)

    def __post_init__(self) -> None:
        self.clave = f"{self.partido.inicio.isoformat()}|{self.partido.partido}"

    def as_dict(self, tz: Any) -> dict[str, Any]:
        p = self.partido
        datos = {
            "equipo": self.equipo,
            "preferencia": self.prioridad,
            "partido": p.partido,
            "canal_dial": p.canal_dial,
            "dial": p.principal.dial,
            "inicio": p.inicio.astimezone(tz).isoformat(),
            "se_pone": self.momento.astimezone(tz).isoformat(),
        }
        if self.motivo:
            datos["motivo"] = self.motivo
        return datos


def equipos_auto(options: dict[str, Any]) -> list[str]:
    """Equipos que se ponen solos, en orden de preferencia (sólo los seguidos)."""
    seguidos = {e.strip() for e in options.get(CONF_EQUIPOS, []) if e and e.strip()}
    return [e for e in dict.fromkeys(options.get(CONF_AUTO_EQUIPOS, [])) if e in seguidos]


def auto_configurado(options: dict[str, Any]) -> bool:
    """True si hay mando y al menos un equipo para poner solo."""
    return mando_configurado(options) and bool(equipos_auto(options))


def minutos_antes(options: dict[str, Any]) -> int:
    try:
        return max(0, int(float(options.get(CONF_AUTO_MINUTOS, DEFAULT_AUTO_MINUTOS))))
    except (TypeError, ValueError):
        return DEFAULT_AUTO_MINUTOS


def planificar(
    candidatos: list[tuple[str, list[Partido]]],
    minutos: int,
    ahora: datetime,
) -> tuple[list[Programado], list[Programado]]:
    """Decide qué partidos se ponen.

    `candidatos` va en orden de preferencia: [(equipo, partidos), ...].
    Devuelve (aceptados, descartados), ambos ordenados por momento. Los
    aceptados incluyen los que ya están en juego (bloquean a los de menos
    preferencia), aunque ya no haya que ponerlos.
    """
    antes = timedelta(minutes=minutos)
    aceptados: list[Programado] = []
    descartados: list[Programado] = []
    for prioridad, (equipo, partidos) in enumerate(candidatos, start=1):
        for p in partidos:
            if p.fin <= ahora:
                continue
            prog = Programado(equipo, prioridad, p, p.inicio - antes)
            for otro in aceptados:
                if otro.prioridad == prioridad:
                    continue
                if otro.clave == prog.clave:
                    prog.motivo = f"Es el mismo partido que el de {otro.equipo}"
                    break
                # El preferido ya está puesto (o se pone a la vez) a esa hora
                if otro.momento <= prog.momento < otro.partido.fin:
                    prog.motivo = (
                        f"Coincide con {otro.partido.partido} ({otro.equipo}, más preferencia)"
                    )
                    break
            (descartados if prog.motivo else aceptados).append(prog)
    aceptados.sort(key=lambda x: (x.momento, x.prioridad))
    descartados.sort(key=lambda x: (x.momento, x.prioridad))
    return aceptados, descartados


class AutoSintonizador:
    """Programa y lanza el cambio de canal automático."""

    def __init__(self, hass: HomeAssistant, entry: Any) -> None:
        self.hass = hass
        self._entry = entry
        self.activo = True
        self.proximo: Programado | None = None
        self.programados: list[Programado] = []
        self.descartados: list[Programado] = []
        self.ultimo: dict[str, Any] | None = None
        self._hechos: dict[str, datetime] = {}  # clave -> fin del partido
        self._cancelar: CALLBACK_TYPE | None = None
        self._quitar_listener: Callable[[], None] | None = None

    @property
    def minutos(self) -> int:
        return minutos_antes(self._entry.options)

    @callback
    def iniciar(self) -> None:
        coordinator = self._entry.runtime_data.coordinator
        self._quitar_listener = coordinator.async_add_listener(self.replanificar)
        self.replanificar()

    @callback
    def detener(self) -> None:
        if self._quitar_listener:
            self._quitar_listener()
            self._quitar_listener = None
        self._cancelar_temporizador()

    @callback
    def activar(self, activo: bool) -> None:
        self.activo = activo
        self.replanificar()

    @callback
    def _cancelar_temporizador(self) -> None:
        if self._cancelar:
            self._cancelar()
            self._cancelar = None

    def _calcular(self, ahora: datetime) -> tuple[list[Programado], list[Programado]]:
        coordinator = self._entry.runtime_data.coordinator
        candidatos: list[tuple[str, list[Partido]]] = []
        for valor in equipos_auto(self._entry.options):
            equipo = resolver_equipo(valor)
            # Nunca repeticiones: sólo directos y estrenos
            partidos = [
                p
                for p in coordinator.partidos(valor, False)
                if any(e.original for e in p.emisiones)
            ]
            candidatos.append((equipo.nombre if equipo else valor, partidos))
        return planificar(candidatos, self.minutos, ahora)

    @callback
    def replanificar(self, *_: Any) -> None:
        """Recalcula el plan y programa el siguiente cambio de canal."""
        self._cancelar_temporizador()
        ahora = dt_util.utcnow()
        if self._entry.runtime_data.coordinator.data is None:
            aceptados, descartados = [], []
        else:
            aceptados, descartados = self._calcular(ahora)
        self.programados = [
            p for p in aceptados if p.momento > ahora and p.clave not in self._hechos
        ]
        self.descartados = [d for d in descartados if d.momento > ahora]
        self.proximo = self.programados[0] if self.programados and self.activo else None
        if self.proximo:
            self._cancelar = async_track_point_in_utc_time(
                self.hass, self._lanzar, self.proximo.momento
            )
        async_dispatcher_send(self.hass, f"{SIGNAL_AUTO_UPDATED}_{self._entry.entry_id}")

    @callback
    def _lanzar(self, momento: datetime) -> None:
        self._cancelar = None
        # Con los datos más recientes: ¿sigue tocando poner algo ahora?
        aceptados, _ = self._calcular(momento - _MARGEN)
        toca = [
            p
            for p in aceptados
            if p.clave not in self._hechos and momento - _MARGEN <= p.momento <= momento
        ]
        if toca and self.activo:
            prog = toca[0]
            self._hechos[prog.clave] = prog.partido.fin
            self._entry.async_create_background_task(
                self.hass, self._poner(prog), f"{DOMAIN}_auto_{prog.clave}"
            )
        # Olvida partidos ya terminados
        ahora = dt_util.utcnow()
        self._hechos = {c: fin for c, fin in self._hechos.items() if fin > ahora}
        self.replanificar()

    async def _poner(self, prog: Programado) -> None:
        p = prog.partido
        dial = p.principal.dial
        tz = dt_util.get_default_time_zone()
        datos = prog.as_dict(tz)
        try:
            await async_sintonizar(self.hass, dict(self._entry.options), dial)
        except HomeAssistantError as err:
            _LOGGER.warning("No se pudo poner %s (dial %s): %s", p.partido, dial, err)
            datos["error"] = str(err)
        else:
            _LOGGER.info("Puesto automáticamente %s en %s", p.partido, p.canal_dial)
        datos["puesto"] = dt_util.now().isoformat()
        self.ultimo = datos
        self.hass.bus.async_fire(EVENT_AUTO, datos)
        async_dispatcher_send(self.hass, f"{SIGNAL_AUTO_UPDATED}_{self._entry.entry_id}")
