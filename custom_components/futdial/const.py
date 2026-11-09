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

# Mando / descodificador
CONF_MANDO = "mando"
CONF_MODO_MANDO = "modo_mando"
CONF_PLANTILLA = "plantilla"
CONF_DISPOSITIVO = "dispositivo"
CONF_RETARDO = "retardo"
CONF_TECLA_FINAL = "tecla_final"
CONF_CODIGOS = [f"codigo_{d}" for d in range(10)]
MODO_MOVISTAR = "movistar"
MODO_CODIGOS = "codigos"
MODO_PLANTILLA = "plantilla"
DEFAULT_RETARDO = 0.9

# Poner partidos automáticamente (equipos en orden de preferencia)
CONF_AUTO_EQUIPOS = "auto_equipos"
CONF_AUTO_MINUTOS = "auto_minutos"
DEFAULT_AUTO_MINUTOS = 30
DEFAULT_PLANTILLA = "{digito}"

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
SIGNAL_AUTO_UPDATED = f"{DOMAIN}_auto_updated"
EVENT_AUTO = f"{DOMAIN}_partido_puesto"

SERVICE_BUSCAR = "buscar_partido"
SERVICE_ACTUALIZAR = "actualizar"
SERVICE_SINTONIZAR = "sintonizar"
ATTR_PARTIDO = "partido"
ATTR_DIAL = "dial"
ATTR_MAX_RESULTADOS = "max_resultados"

INTENT_BUSCAR = "FutDialBuscarPartido"
INTENT_SINTONIZAR = "FutDialSintonizar"
