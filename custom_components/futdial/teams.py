"""Catálogo de equipos seleccionables y cómo reconocerlos en la guía.

Cada equipo tiene uno o varios "patrones": conjuntos de palabras que deben
aparecer en el MISMO lado del partido ("Local - Visitante"). Así «Barcelona»
no coincide con «RCD Espanyol de Barcelona» ni «Racing» con «Racing Ferrol».

Los nombres se han sacado de la propia guía de Movistar Plus+ (temporada 26/27).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .epg import Emision, Partido, agrupar, filtrar, normalize


@dataclass(frozen=True)
class Equipo:
    """Equipo seleccionable en la configuración."""

    id: str
    nombre: str
    grupo: str
    patrones: tuple[frozenset[str], ...]
    excluir: frozenset[str] = frozenset()
    excluir_competicion: frozenset[str] = frozenset()
    alias: tuple[str, ...] = ()
    # Filiales (Celta B, Real Sociedad B): no se descartan por ser "secundarios"
    filial: bool = False
    claves: frozenset[str] = field(default=frozenset(), compare=False)


def _e(
    id_: str,
    nombre: str,
    grupo: str,
    *patrones: str,
    excluir: str = "",
    excluir_competicion: str = "",
    alias: tuple[str, ...] = (),
    filial: bool = False,
) -> Equipo:
    pats = tuple(frozenset(normalize(p)) for p in patrones)
    claves = {" ".join(normalize(nombre)), id_.replace("_", " ")}
    claves.update(" ".join(normalize(a)) for a in alias)
    claves.update(" ".join(normalize(p)) for p in patrones)
    return Equipo(
        id=id_,
        nombre=nombre,
        grupo=grupo,
        patrones=pats,
        excluir=frozenset(normalize(excluir)),
        excluir_competicion=frozenset(normalize(excluir_competicion)),
        alias=alias,
        filial=filial,
        claves=frozenset(claves),
    )


LALIGA = "LALIGA EA SPORTS"
HYPER = "LALIGA HYPERMOTION"
INTER = "Internacional"
_SELECCIONES = "mundial eurocopa nations amistoso clasificacion"

EQUIPOS_LISTA: list[Equipo] = [
    # --- LALIGA EA SPORTS ---
    _e("athletic", "Athletic Club", LALIGA, "athletic", excluir="bilbao"),
    _e("atletico_madrid", "Atlético de Madrid", LALIGA, "atletico madrid", "at madrid",
       excluir="b", alias=("atleti", "atletico", "atm", "colchonero")),
    _e("osasuna", "CA Osasuna", LALIGA, "osasuna", excluir="promesas"),
    _e("alaves", "Deportivo Alavés", LALIGA, "alaves"),
    _e("elche", "Elche CF", LALIGA, "elche"),
    _e("barcelona", "FC Barcelona", LALIGA, "barcelona",
       excluir="espanyol universitari b", alias=("barca", "barça", "cule")),
    _e("getafe", "Getafe CF", LALIGA, "getafe"),
    _e("levante", "Levante UD", LALIGA, "levante"),
    _e("malaga", "Málaga CF", LALIGA, "malaga"),
    _e("racing", "Racing de Santander", LALIGA, "racing",
       excluir="ferrol", excluir_competicion="argentina", alias=("racing santander",)),
    _e("celta", "RC Celta", LALIGA, "celta", excluir="b fortuna"),
    _e("deportivo", "RC Deportivo", LALIGA, "deportivo", "depor",
       excluir="alaves fabril abanca cali", alias=("deportivo coruna", "depor")),
    _e("espanyol", "RCD Espanyol", LALIGA, "espanyol", alias=("espanol",)),
    _e("rayo", "Rayo Vallecano", LALIGA, "rayo", excluir="majadahonda"),
    _e("betis", "Real Betis", LALIGA, "betis"),
    _e("real_madrid", "Real Madrid", LALIGA, "real madrid", "r madrid",
       excluir="castilla cff", alias=("madrid", "merengue", "madridista")),
    _e("real_sociedad", "Real Sociedad", LALIGA, "sociedad", excluir="b"),
    _e("sevilla", "Sevilla FC", LALIGA, "sevilla", excluir="atletico cajasol"),
    _e("valencia", "Valencia CF", LALIGA, "valencia", excluir="basket mestalla"),
    _e("villarreal", "Villarreal CF", LALIGA, "villarreal", excluir="b"),
    # --- LALIGA HYPERMOTION ---
    _e("albacete", "Albacete BP", HYPER, "albacete"),
    _e("burgos", "Burgos CF", HYPER, "burgos"),
    _e("cadiz", "Cádiz CF", HYPER, "cadiz"),
    _e("castellon", "CD Castellón", HYPER, "castellon"),
    _e("eldense", "CD Eldense", HYPER, "eldense"),
    _e("leganes", "CD Leganés", HYPER, "leganes"),
    _e("tenerife", "CD Tenerife", HYPER, "tenerife", excluir="costa adeje"),
    _e("sabadell", "CE Sabadell", HYPER, "sabadell"),
    _e("ceuta", "AD Ceuta FC", HYPER, "ceuta"),
    _e("cordoba", "Córdoba CF", HYPER, "cordoba"),
    _e("andorra", "FC Andorra", HYPER, "andorra", excluir_competicion=_SELECCIONES),
    _e("girona", "Girona FC", HYPER, "girona"),
    _e("granada", "Granada CF", HYPER, "granada"),
    _e("celta_b", "RC Celta B (Celta Fortuna)", HYPER, "celta b", "celta fortuna", filial=True),
    _e("mallorca", "RCD Mallorca", HYPER, "mallorca"),
    _e("oviedo", "Real Oviedo", HYPER, "oviedo"),
    _e("real_sociedad_b", "Real Sociedad B", HYPER, "sociedad b", filial=True),
    _e("sporting", "Real Sporting de Gijón", HYPER, "sporting",
       excluir="portugal lisboa cp braga kansas", alias=("sporting gijon",)),
    _e("valladolid", "Real Valladolid CF", HYPER, "valladolid"),
    _e("eibar", "SD Eibar", HYPER, "eibar"),
    _e("almeria", "UD Almería", HYPER, "almeria"),
    _e("las_palmas", "UD Las Palmas", HYPER, "las palmas", "palmas"),
    # --- Internacional ---
    _e("espana", "Selección Española", INTER, "espana", alias=("seleccion", "la roja")),
    _e("arsenal", "Arsenal", INTER, "arsenal"),
    _e("chelsea", "Chelsea", INTER, "chelsea"),
    _e("liverpool", "Liverpool", INTER, "liverpool"),
    _e("manchester_city", "Manchester City", INTER, "manchester city", alias=("city",)),
    _e("manchester_united", "Manchester United", INTER, "manchester united", "manchester utd",
       alias=("united", "man utd")),
    _e("tottenham", "Tottenham", INTER, "tottenham", alias=("spurs",)),
    _e("newcastle", "Newcastle", INTER, "newcastle"),
    _e("bayern", "Bayern Múnich", INTER, "bayern"),
    _e("dortmund", "Borussia Dortmund", INTER, "dortmund"),
    _e("leverkusen", "Bayer Leverkusen", INTER, "leverkusen"),
    _e("psg", "Paris Saint-Germain", INTER, "psg", "paris saint", alias=("paris sg",)),
    _e("inter", "Inter de Milán", INTER, "inter", excluir="miami"),
    _e("milan", "AC Milan", INTER, "milan", excluir="inter"),
    _e("juventus", "Juventus", INTER, "juventus", alias=("juve",)),
    _e("napoles", "Nápoles", INTER, "napoles", "napoli"),
    _e("roma", "AS Roma", INTER, "roma"),
    _e("benfica", "Benfica", INTER, "benfica"),
    _e("oporto", "Oporto", INTER, "oporto", "porto"),
    _e("ajax", "Ajax", INTER, "ajax"),
    _e("boca", "Boca Juniors", INTER, "boca"),
    _e("river", "River Plate", INTER, "river"),
]

EQUIPOS: dict[str, Equipo] = {e.id: e for e in EQUIPOS_LISTA}

_POR_CLAVE: dict[str, Equipo] = {}
for _eq in EQUIPOS_LISTA:
    for _k in _eq.claves:
        _POR_CLAVE.setdefault(_k, _eq)


def coincide(em: Emision, equipo: Equipo) -> bool:
    """True si el equipo juega en esta emisión (en uno de los dos lados)."""
    if equipo.excluir_competicion & em.palabras_competicion:
        return False
    if em.secundario and not equipo.filial:
        return False
    for lado in em.lados:
        if lado & equipo.excluir:
            continue
        if any(p <= lado for p in equipo.patrones):
            return True
    return False


def buscar_equipo(
    emisiones: list[Emision],
    equipo: Equipo,
    ahora: datetime,
    incluir_repeticiones: bool = False,
) -> list[Partido]:
    """Partidos pendientes o en juego de un equipo, el más próximo primero."""
    candidatas = [e for e in filtrar(emisiones, ahora, incluir_repeticiones) if coincide(e, equipo)]
    partidos = agrupar(candidatas)
    partidos.sort(key=lambda p: (not p.en_juego(ahora), p.inicio))
    return partidos


def resolver_equipo(texto: str) -> Equipo | None:
    """Devuelve el equipo si el texto es su id, nombre o un apodo conocido."""
    if texto in EQUIPOS:
        return EQUIPOS[texto]
    clave = " ".join(w for w in normalize(texto) if w not in {"el", "la", "los", "del", "de"})
    return _POR_CLAVE.get(clave) or _POR_CLAVE.get(" ".join(normalize(texto)))


def etiqueta(equipo: Equipo) -> str:
    """Texto que se muestra en el desplegable."""
    if equipo.grupo == LALIGA:
        return equipo.nombre
    if equipo.grupo == HYPER:
        return f"{equipo.nombre} · Hypermotion"
    return f"{equipo.nombre} · {equipo.grupo}"
