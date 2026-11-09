"""FutDial: ¿en qué canal y dial de Movistar Plus+ echan un partido?"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_DIAL,
    ATTR_MAX_RESULTADOS,
    ATTR_PARTIDO,
    CONF_MANDO,
    CONF_REPETICIONES,
    DOMAIN,
    SERVICE_ACTUALIZAR,
    SERVICE_BUSCAR,
    SERVICE_SINTONIZAR,
    SIGNAL_QUERY_UPDATED,
)
from .auto import AutoSintonizador, auto_configurado
from .coordinator import FutDialConfigEntry, FutDialCoordinator, RuntimeData
from .mando import async_sintonizar
from .teams import resolver_equipo

PLATFORMS: list[Platform] = [Platform.BUTTON, Platform.SENSOR, Platform.SWITCH, Platform.TEXT]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

BUSCAR_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_PARTIDO): cv.string,
        vol.Optional(CONF_REPETICIONES): cv.boolean,
        vol.Optional(ATTR_MAX_RESULTADOS, default=5): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=50)
        ),
    }
)


SINTONIZAR_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Exclusive(ATTR_PARTIDO, "que"): cv.string,
            vol.Exclusive(ATTR_DIAL, "que"): vol.All(vol.Coerce(int), vol.Range(min=0, max=9999)),
            vol.Optional(CONF_MANDO): cv.entity_id,
        }
    ),
    cv.has_at_least_one_key(ATTR_PARTIDO, ATTR_DIAL),
)


def get_entry(hass: HomeAssistant) -> FutDialConfigEntry:
    """Devuelve la (única) entrada cargada de la integración."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED:
            return entry
    raise ServiceValidationError(
        "FutDial no está configurado o todavía se está cargando",
        translation_domain=DOMAIN,
        translation_key="not_loaded",
    )


def resultado_busqueda(
    hass: HomeAssistant,
    entry: FutDialConfigEntry,
    consulta: str,
    incluir_repeticiones: bool | None = None,
    max_resultados: int = 5,
) -> dict[str, Any]:
    """Resultado de búsqueda serializable (servicio, sensor e intent)."""
    coordinator = entry.runtime_data.coordinator
    partidos = coordinator.partidos(consulta, incluir_repeticiones)
    ahora = dt_util.utcnow()
    tz = dt_util.get_default_time_zone()
    items = [p.as_dict(ahora, tz) for p in partidos[:max_resultados]]
    primero = items[0] if items else {}
    equipo = resolver_equipo(consulta)
    nombre = equipo.nombre if equipo else consulta
    return {
        "consulta": consulta,
        "equipo": nombre,
        "encontrado": bool(primero),
        "resultado": primero.get("canal_dial"),
        "canal": primero.get("canal"),
        "dial": primero.get("dial"),
        "inicio": primero.get("inicio"),
        "fecha": primero.get("fecha"),
        "hora": primero.get("hora"),
        "fecha_hora": primero.get("fecha_hora"),
        "texto": primero.get("texto")
        or f"No he encontrado ningún partido de «{nombre}» en Movistar Plus+.",
        "partidos": items,
    }


async def sintonizar_partido(
    hass: HomeAssistant,
    entry: FutDialConfigEntry,
    consulta: str | None = None,
    dial: int | None = None,
    mando: str | None = None,
) -> dict[str, Any]:
    """Pone en la tele el partido buscado (o un dial concreto).

    Devuelve el resultado de la búsqueda más lo enviado al mando, con un
    `texto` listo para el asistente de voz.
    """
    if dial is not None:
        enviado = await async_sintonizar(hass, dict(entry.options), dial, mando)
        return {**enviado, "texto": f"Pongo el dial {dial}.", "encontrado": True}

    coordinator = entry.runtime_data.coordinator
    if coordinator.data is None:
        await coordinator.async_refresh()
    r = resultado_busqueda(hass, entry, consulta or "", max_resultados=1)
    if not r["encontrado"]:
        raise ServiceValidationError(
            r["texto"],
            translation_domain=DOMAIN,
            translation_key="sin_partido",
            translation_placeholders={"equipo": r["equipo"]},
        )
    p = r["partidos"][0]
    enviado = await async_sintonizar(hass, dict(entry.options), p["dial"], mando)
    cuando = "" if p["en_juego"] else f" (empieza {p['cuando']})"
    return {
        **r,
        **enviado,
        "texto": f"Pongo {p['partido']} en {p['canal']}, dial {p['dial']}{cuando}.",
    }


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Registra los servicios de la integración."""

    async def _buscar(call: ServiceCall) -> ServiceResponse:
        entry = get_entry(hass)
        consulta: str = call.data[ATTR_PARTIDO].strip()
        coordinator = entry.runtime_data.coordinator
        if coordinator.data is None:
            # Primera descarga aún en curso o fallida: se intenta ahora
            await coordinator.async_refresh()
            if coordinator.data is None:
                raise HomeAssistantError(
                    "La programación de Movistar Plus+ todavía no se ha podido descargar",
                    translation_domain=DOMAIN,
                    translation_key="no_data",
                )
        result = resultado_busqueda(
            hass,
            entry,
            consulta,
            call.data.get(CONF_REPETICIONES),
            call.data[ATTR_MAX_RESULTADOS],
        )
        # Actualiza también el sensor "Resultado búsqueda"
        set_query(hass, entry, consulta)
        if call.return_response:
            return result
        return None

    async def _actualizar(call: ServiceCall) -> None:
        await get_entry(hass).runtime_data.coordinator.async_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_BUSCAR,
        _buscar,
        schema=BUSCAR_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(DOMAIN, SERVICE_ACTUALIZAR, _actualizar)

    async def _sintonizar(call: ServiceCall) -> ServiceResponse:
        result = await sintonizar_partido(
            hass,
            get_entry(hass),
            call.data.get(ATTR_PARTIDO),
            call.data.get(ATTR_DIAL),
            call.data.get(CONF_MANDO),
        )
        return result if call.return_response else None

    hass.services.async_register(
        DOMAIN,
        SERVICE_SINTONIZAR,
        _sintonizar,
        schema=SINTONIZAR_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    return True


@callback
def set_query(hass: HomeAssistant, entry: FutDialConfigEntry, consulta: str) -> None:
    """Cambia la consulta de la entidad de búsqueda y avisa a las entidades."""
    entry.runtime_data.consulta = consulta
    async_dispatcher_send(hass, f"{SIGNAL_QUERY_UPDATED}_{entry.entry_id}")


async def async_setup_entry(hass: HomeAssistant, entry: FutDialConfigEntry) -> bool:
    """Configura la integración desde una entrada de configuración."""
    coordinator = FutDialCoordinator(hass, entry)
    # 1) Programación guardada en disco: los sensores tienen datos al instante
    descargada = await coordinator.async_cargar_cache()
    entry.runtime_data = RuntimeData(coordinator=coordinator)
    if auto_configurado(entry.options):
        entry.runtime_data.auto = AutoSintonizador(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Después de las plataformas: el interruptor ya ha recuperado su estado
    if (auto := entry.runtime_data.auto) is not None:
        auto.iniciar()
        entry.async_on_unload(auto.detener)

    @callback
    def _descargar(*_: Any) -> None:
        entry.async_create_background_task(
            hass, coordinator.async_refresh(), f"{DOMAIN}_descarga"
        )

    @callback
    def _ha_arrancado(_hass: HomeAssistant) -> None:
        # 2) Nada de red ni CPU mientras arranca Home Assistant: la descarga
        #    se hace después y sólo si la programación guardada ya toca
        #    actualizarla según el intervalo elegido.
        if descargada is None:
            _descargar()
            return
        edad = dt_util.utcnow() - descargada
        if edad >= coordinator.intervalo:
            _descargar()
        else:
            entry.async_on_unload(
                async_call_later(hass, coordinator.intervalo - edad, _descargar)
            )

    entry.async_on_unload(async_at_started(hass, _ha_arrancado))
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: FutDialConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: FutDialConfigEntry) -> bool:
    """Descarga la entrada."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
