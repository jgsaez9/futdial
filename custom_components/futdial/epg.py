"""Cliente de la guía (EPG) de Movistar Plus+ y búsqueda de partidos.

Este módulo no depende de Home Assistant para poder probarse de forma aislada.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp

try:  # Home Assistant incluye orjson, mucho más rápido para 11 MB de JSON
    import orjson

    def _json_loads(raw: bytes) -> Any:
        return orjson.loads(raw)

except ImportError:  # pragma: no cover
    import json

    def _json_loads(raw: bytes) -> Any:
        return json.loads(raw)


EPG_URL = "https://ottcache.dof6.com/movistarplus/webplayer/OTT/epg"
EPG_PARAMS = {
    "span": "1",
    "channel": "",
    "version": "8",
    "mdrm": "true",
    "tlsstream": "true",
    "demarcation": "1",
}
USER_AGENT = "Mozilla/5.0 (compatible; HomeAssistant futdial)"
TIMEOUT = aiohttp.ClientTimeout(total=120)

# Canales donde se emite fútbol: generalistas, deportes de Movistar Plus+/DAZN
# y autonómicas. Pedir sólo estos reduce la guía de ~11 MB a ~3 MB por día y
# el tiempo de respuesta de ~12 s a ~3 s. Los códigos desconocidos se ignoran.
CANALES_FUTBOL: tuple[str, ...] = (
    # Generalistas
    "TVE", "LA2", "A3", "C4", "T5", "SEXTA", "SEPTIM", "MPLUS", "TV3CAT", "13TV",
    # Movistar Plus+ / DAZN / LALIGA
    "VAMOSD", "VAM2SD", "MELLAV", "MCOPA", "MLIGA", "DAZNLI", "MLIGS", "MLIG1",
    "DAZNL2", "MLIGS2", "MLIG2", "MLIG3", "MLIGS3", "CPDEP", "ARTHUR", "USOP2",
    "USOP3", "USOP11", "MULTI8", "M1SD", "M2SD", "DAZN3", "DAZN4", "UCL",
    "CHAPIO", "CHAP1", "CHAP2", "CHAP3", "CHAP4", "CHAP5", "CHAP6", "CHAP7",
    "CHAP8", "CHAP9", "CHAP10", "CHAP11", "CHAP12", "CHAP13", "CHAP14", "CHAP15",
    "CHAP16", "CHAP18", "CHAP19",
    # Otros deportes
    "ESP", "ESP2", "GOL", "TDEP", "REALM",
    # Autonómicas
    "RED", "ANTV", "TVG", "EXTREM", "TVC", "ARAGON", "TELMIN", "ETB3", "ETB",
)
# Canales de reposiciones: sólo cuentan si la emisión es en directo
CANALES_DIFERIDOS = frozenset({"REALM", "GOL"})
_TZ_ES = ZoneInfo("Europe/Madrid")
_REPEAT_GAP = timedelta(hours=3)
_MADRUGADA = (3.0, 10.5)

# Si con el filtro llegan menos canales que esto, los códigos han cambiado:
# se vuelve a pedir la guía completa
MIN_CANALES_FILTRO = 15

# Margen para agrupar la misma emisión en varios canales
_GROUP_WINDOW = timedelta(minutes=20)

_STOPWORDS = {
    "de", "del", "la", "el", "los", "las", "y", "e", "vs", "v", "contra",
    "fc", "cf", "cd", "ud", "sd", "rcd", "rc", "club", "partido", "futbol",
    "que", "en", "canal", "dial", "echan", "emiten", "juega", "juegan", "hoy",
    "manana", "al",
}

# Apodos habituales -> palabras que aparecen en la guía
_ALIASES: dict[str, list[str]] = {
    "barca": ["barcelona"],
    "atleti": ["atletico"],
    "atm": ["atletico", "madrid"],
    "depor": ["deportivo"],
    "psg": ["paris"],
    "united": ["manchester", "utd"],
    "manu": ["manchester", "utd"],
    "city": ["manchester", "city"],
    "spurs": ["tottenham"],
    "juve": ["juventus"],
    "sevillista": ["sevilla"],
    "colchonero": ["atletico"],
    "cule": ["barcelona"],
    "merengue": ["real", "madrid"],
    "madridista": ["real", "madrid"],
    "espanol": ["espanyol"],
    "seleccion": ["espana"],
}

# Palabras que indican partido "secundario" (femenino, filial, juvenil...)
_SECONDARY_WORDS = {
    "femenino", "fem", "women", "woman", "castilla", "b", "juvenil", "sub",
    "u19", "u21", "u23", "cadete",
}
_SECONDARY_COMPETITIONS = ("liga f", "uwcl", "women", "femenin", "youth", "juvenil")

_QUOTED = re.compile(r'"([^"]+)"')
_WEEKDAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


class EpgError(Exception):
    """Error obteniendo la guía de Movistar Plus+."""


def normalize(text: str) -> list[str]:
    """Quita acentos, pasa a minúsculas y separa en palabras."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]+", text.lower())


@dataclass(frozen=True, slots=True)
class Emision:
    """Una emisión de un partido en un canal concreto."""

    id: int
    partido: str
    competicion: str
    canal: str
    codigo_canal: str
    dial: int
    inicio: datetime
    fin: datetime
    directo: bool
    estreno: bool
    repeticion: bool = False

    @property
    def canal_dial(self) -> str:
        """Texto tipo 'M+ LALIGA - 54'."""
        return f"{self.canal} - {self.dial}"

    @property
    def original(self) -> bool:
        """True si es la emisión en directo/estreno (no una repetición)."""
        return (self.directo or self.estreno) and not self.repeticion

    @property
    def es_resumen(self) -> bool:
        comp = self.competicion.lower()
        return comp.startswith("resumen") or comp.startswith("resúmenes")

    @property
    def palabras(self) -> list[str]:
        return normalize(f"{self.partido} {self.competicion}")

    @property
    def secundario(self) -> bool:
        if set(normalize(self.partido)) & _SECONDARY_WORDS:
            return True
        comp = " ".join(normalize(self.competicion))
        return any(c in comp for c in _SECONDARY_COMPETITIONS)


@dataclass(slots=True)
class Partido:
    """Un partido, con todas las emisiones simultáneas que lo retransmiten."""

    partido: str
    competicion: str
    inicio: datetime
    fin: datetime
    emisiones: list[Emision] = field(default_factory=list)

    @property
    def principal(self) -> Emision:
        return self.emisiones[0]

    @property
    def canal_dial(self) -> str:
        """Canal principal, p. ej. 'M+ LALIGA - 54'."""
        return self.principal.canal_dial

    @property
    def todos_los_canales(self) -> str:
        return ", ".join(e.canal_dial for e in self.emisiones)

    @property
    def secundario(self) -> bool:
        return self.principal.secundario

    def en_juego(self, ahora: datetime) -> bool:
        return self.inicio <= ahora < self.fin

    def as_dict(self, ahora: datetime, tz: Any = None) -> dict[str, Any]:
        inicio = self.inicio.astimezone(tz) if tz else self.inicio
        fin = self.fin.astimezone(tz) if tz else self.fin
        ahora_local = ahora.astimezone(tz) if tz else ahora
        return {
            "partido": self.partido,
            "competicion": self.competicion,
            "canal": self.principal.canal,
            "dial": self.principal.dial,
            "canal_dial": self.canal_dial,
            "todos_los_canales": self.todos_los_canales,
            "canales": [
                {"canal": e.canal, "dial": e.dial, "canal_dial": e.canal_dial}
                for e in self.emisiones
            ],
            "inicio": inicio.isoformat(),
            "fin": fin.isoformat(),
            "fecha": inicio.strftime("%d/%m/%Y"),
            "hora": inicio.strftime("%H:%M"),
            "fecha_hora": (
                f"{_WEEKDAYS[inicio.weekday()]} {inicio.strftime('%d/%m/%Y')} "
                f"a las {inicio.strftime('%H:%M')}"
            ),
            "cuando": describir_fecha(inicio, ahora_local),
            "en_juego": self.en_juego(ahora),
            "directo": any(e.original for e in self.emisiones),
            "texto": describir_partido(self, ahora, tz),
        }


def _clean_title(event: dict[str, Any]) -> str:
    for key in ("TituloEpisodio", "TituloHorLinea2"):
        value = event.get(key) or ""
        match = _QUOTED.search(value)
        if match:
            return match.group(1).strip()
    return (event.get("TituloEpisodio") or event.get("Titulo") or "").strip().strip('"')


def _is_football(event: dict[str, Any]) -> bool:
    genre = " ".join(normalize(event.get("GeneroComAntena") or ""))
    return genre.startswith("futbol") and "americano" not in genre and "australiano" not in genre


def parse_epg(raw: bytes) -> tuple[list[Emision], int]:
    """Convierte la respuesta cruda de la EPG en emisiones de fútbol.

    La respuesta es una lista de canales (cada uno una lista de eventos) o,
    si se filtra por canal, una lista plana de eventos. Devuelve también el
    número de canales distintos recibidos.
    """
    data = _json_loads(raw)
    if not isinstance(data, list):
        raise EpgError("Formato de EPG inesperado")

    events: list[dict[str, Any]] = []
    for item in data:
        if isinstance(item, list):
            events.extend(e for e in item if isinstance(e, dict))
        elif isinstance(item, dict):
            events.append(item)

    result: list[Emision] = []
    canales: set[str] = set()
    for event in events:
        canal = event.get("Canal") or {}
        canales.add(str(canal.get("CodCadenaTv")))
        if not _is_football(event):
            continue
        try:
            dial = int(canal.get("ServiceId"))
            inicio = datetime.fromtimestamp(int(event["FechaHoraInicio"]) / 1000, tz=timezone.utc)
            fin = datetime.fromtimestamp(int(event["FechaHoraFin"]) / 1000, tz=timezone.utc)
        except (KeyError, TypeError, ValueError):
            continue
        result.append(
            Emision(
                id=int(event.get("CodEventoRejilla") or event.get("Id") or 0),
                partido=_clean_title(event),
                competicion=(event.get("TituloSerie") or event.get("Titulo") or "").strip(),
                canal=(canal.get("Nombre") or "").strip(),
                codigo_canal=canal.get("CodCadenaTv") or "",
                dial=dial,
                inicio=inicio,
                fin=fin,
                directo=bool(event.get("Directo")),
                estreno=bool(event.get("Estreno")),
            )
        )
    return result, len(canales)


async def fetch_day(
    session: aiohttp.ClientSession, day: date, canales: tuple[str, ...] | None = None
) -> bytes:
    """Descarga la guía de un día: completa (≈11 MB) o sólo de `canales`."""
    params = {"from": f"{day.isoformat()}T00:00:00", **EPG_PARAMS}
    if canales:
        params["channel"] = ",".join(canales)
    try:
        async with session.get(
            EPG_URL,
            params=params,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=TIMEOUT,
        ) as resp:
            if resp.status != 200:
                raise EpgError(f"HTTP {resp.status} al descargar la EPG de {day}")
            return await resp.read()
    except (aiohttp.ClientError, TimeoutError) as err:
        raise EpgError(f"Error de conexión al descargar la EPG de {day}: {err}") from err


def _query_tokens(consulta: str) -> list[str]:
    tokens: list[str] = []
    for word in normalize(consulta):
        if word in _ALIASES:
            tokens.extend(_ALIASES[word])
        elif word not in _STOPWORDS:
            tokens.append(word)
    return list(dict.fromkeys(tokens))


def _matches(tokens: list[str], palabras: list[str]) -> bool:
    return all(any(p.startswith(t) for p in palabras) for t in tokens)


def agrupar(emisiones: list[Emision]) -> list[Partido]:
    """Agrupa emisiones simultáneas del mismo partido en distintos canales."""
    def _key(title: str) -> set[str]:
        return {w for w in normalize(title) if w not in _STOPWORDS}

    def _same(a: set[str], b: set[str]) -> bool:
        if not a or not b:
            return a == b
        return len(a & b) / len(a | b) >= 0.5

    partidos: list[Partido] = []
    for em in sorted(emisiones, key=lambda e: (e.inicio, e.dial)):
        key = _key(em.partido)
        for p in partidos:
            if abs(p.inicio - em.inicio) <= _GROUP_WINDOW and _same(_key(p.partido), key):
                if all(e.dial != em.dial for e in p.emisiones):
                    p.emisiones.append(em)
                    p.fin = max(p.fin, em.fin)
                break
        else:
            partidos.append(Partido(em.partido, em.competicion, em.inicio, em.fin, [em]))
    for p in partidos:
        p.emisiones.sort(key=lambda e: (not e.original, e.dial))
    return partidos


def _clave_partido(em: Emision) -> tuple[frozenset[str], str]:
    titulo = frozenset(w for w in normalize(em.partido) if w not in _STOPWORDS)
    return titulo, " ".join(normalize(em.competicion))


def marcar_repeticiones(emisiones: list[Emision]) -> list[Emision]:
    """Marca como repetición los falsos "estrenos" de la guía.

    Movistar marca como estreno el primer pase de un partido en cada canal,
    aunque sea un diferido. Se considera repetición (salvo si es en directo):
    - si el mismo partido de la misma competición ya se emitió >3 h antes,
    - si empieza entre las 03:00 y las 10:30 (hora peninsular),
    - si es de un canal de reposiciones (Real Madrid TV, Replay).
    """
    primera: dict[tuple[frozenset[str], str], datetime] = {}
    for em in sorted(emisiones, key=lambda e: e.inicio):
        primera.setdefault(_clave_partido(em), em.inicio)

    resultado: list[Emision] = []
    for em in emisiones:
        repeticion = False
        if not em.directo:
            local = em.inicio.astimezone(_TZ_ES)
            hora = local.hour + local.minute / 60
            if em.inicio - primera[_clave_partido(em)] > _REPEAT_GAP:
                repeticion = True
            elif em.codigo_canal in CANALES_DIFERIDOS:
                repeticion = True
            elif _MADRUGADA[0] <= hora < _MADRUGADA[1]:
                repeticion = True
        resultado.append(replace(em, repeticion=True) if repeticion else em)
    return resultado


def filtrar(
    emisiones: list[Emision],
    ahora: datetime,
    incluir_repeticiones: bool = False,
    hasta: datetime | None = None,
) -> list[Emision]:
    """Emisiones que aún no han terminado (y, por defecto, sin repeticiones)."""
    out = []
    for e in emisiones:
        if e.fin <= ahora or (hasta and e.inicio >= hasta):
            continue
        if not incluir_repeticiones and (not e.original or e.es_resumen):
            continue
        out.append(e)
    return out


def buscar(
    emisiones: list[Emision],
    consulta: str,
    ahora: datetime,
    incluir_repeticiones: bool = False,
) -> list[Partido]:
    """Busca partidos por equipo(s) o competición.

    Orden: partidos "principales" antes que femenino/filial (salvo que se
    pidan explícitamente), después en juego primero y luego por hora.
    """
    tokens = _query_tokens(consulta)
    if not tokens:
        return []
    candidatas = [
        e for e in filtrar(emisiones, ahora, incluir_repeticiones) if _matches(tokens, e.palabras)
    ]
    # Si sólo hay repeticiones, mejor eso que nada (el texto lo indica)
    if not candidatas and not incluir_repeticiones:
        candidatas = [
            e for e in filtrar(emisiones, ahora, True) if _matches(tokens, e.palabras)
        ]
    pide_secundario = bool(set(tokens) & _SECONDARY_WORDS) or any(
        t in _SECONDARY_COMPETITIONS for t in tokens
    )
    partidos = agrupar(candidatas)
    partidos.sort(
        key=lambda p: (
            p.secundario and not pide_secundario,
            not p.en_juego(ahora),
            p.inicio,
        )
    )
    return partidos


def describir_fecha(inicio: datetime, ahora: datetime) -> str:
    """'hoy a las 21:00', 'mañana a las 18:30', 'el viernes 13 a las 20:50'."""
    hora = inicio.strftime("%H:%M")
    dias = (inicio.date() - ahora.date()).days
    if dias == 0:
        return f"hoy a las {hora}"
    if dias == 1:
        return f"mañana a las {hora}"
    if dias == -1:
        return f"ayer a las {hora}"
    return f"el {_WEEKDAYS[inicio.weekday()]} {inicio.day} a las {hora}"


def describir_partido(partido: Partido, ahora: datetime, tz: Any = None) -> str:
    """Frase lista para notificaciones o el asistente de voz."""
    inicio = partido.inicio.astimezone(tz) if tz else partido.inicio
    ahora_local = ahora.astimezone(tz) if tz else ahora
    canales = " y ".join(
        f"{e.canal} (dial {e.dial})" for e in partido.emisiones[:3]
    )
    if partido.en_juego(ahora):
        cuando = "se está emitiendo ahora"
    else:
        cuando = f"se emite {describir_fecha(inicio, ahora_local)}"
    if not any(e.original for e in partido.emisiones):
        cuando += " (repetición)"
    return f"{partido.partido} ({partido.competicion}) {cuando} en {canales}."
