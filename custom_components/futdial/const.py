"""Constantes de FutDial."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "futdial"
NAME = "FutDial"

CONF_EQUIPOS = "equipos"
CONF_DIAS = "dias"
CONF_INTERVALO = "intervalo"
CONF_REPETICIONES = "incluir_repeticiones"
CONF_TODOS_CANALES = "todos_los_canales"

DEFAULT_DIAS = 3
DEFAULT_INTERVALO = "180"  # minutos
DEFAULT_REPETICIONES = False
DEFAULT_TODOS_CANALES = False
MAX_DIAS = 8

# Opciones del desplegable de intervalo: (minutos, etiqueta)
INTERVALOS: list[tuple[str, str]] = [
    ("30", "Cada 30 minutos"),
    ("60", "Cada hora"),
    ("120", "Cada 2 horas"),
    ("180", "Cada 3 horas"),
    ("360", "Cada 6 horas"),
    ("720", "Cada 12 horas"),
    ("1440", "Una vez al día"),
    ("2880", "Cada 2 días"),
    ("4320", "Cada 3 días"),
    ("10080", "Una vez a la semana"),
]

# Los días más allá de mañana cambian poco: se refrescan con menos frecuencia
FAR_DAYS_MAX_AGE = timedelta(hours=6)
# Si la descarga falla y no hay datos, se reintenta con esta frecuencia
RETRY_INTERVAL = timedelta(minutes=5)
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
