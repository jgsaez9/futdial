"""Constantes de FutDial."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "futdial"
NAME = "FutDial"

CONF_EQUIPOS = "equipos"
CONF_DIAS = "dias"
CONF_INTERVALO = "intervalo"
CONF_REPETICIONES = "incluir_repeticiones"

DEFAULT_DIAS = 3
DEFAULT_INTERVALO = 120  # minutos
DEFAULT_REPETICIONES = False

# Los días más allá de mañana cambian poco: se refrescan con menos frecuencia
FAR_DAYS_MAX_AGE = timedelta(hours=6)
# Cada cuánto recalculan las entidades (sin descargar nada) para que
# "en juego" / "próximo partido" avance con el reloj
TICK_INTERVAL = timedelta(minutes=2)

SIN_EMISION = "Sin emisión"

SIGNAL_QUERY_UPDATED = f"{DOMAIN}_query_updated"

SERVICE_BUSCAR = "buscar_partido"
SERVICE_ACTUALIZAR = "actualizar"
ATTR_PARTIDO = "partido"
ATTR_MAX_RESULTADOS = "max_resultados"

INTENT_BUSCAR = "FutDialBuscarPartido"
