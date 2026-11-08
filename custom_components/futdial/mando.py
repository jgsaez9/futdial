"""Enviar el dial al descodificador a través de una entidad `remote`.

Funciona con cualquier integración que implemente `remote.send_command`:
- Broadlink con los códigos del descodificador Movistar+ ya incluidos.
- Broadlink (RM mini, RM4…) con códigos IR en base64 por dígito
  (`b64:…`) o con comandos aprendidos por nombre (dispositivo + "5").
- Android TV Remote, Sony, Philips…, con una plantilla como
  `KEYCODE_{digito}`.
"""

from __future__ import annotations

import base64
import binascii
import re
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .const import (
    CONF_CODIGOS,
    CONF_DISPOSITIVO,
    CONF_MANDO,
    CONF_MODO_MANDO,
    CONF_PLANTILLA,
    CONF_RETARDO,
    CONF_TECLA_FINAL,
    DEFAULT_PLANTILLA,
    DEFAULT_RETARDO,
    DOMAIN,
    MODO_CODIGOS,
    MODO_MOVISTAR,
    MODO_PLANTILLA,
)

_B64 = re.compile(r"^[A-Za-z0-9+/=\s]+$")

# Teclas 0-9 del mando del descodificador Movistar+ (Arris/UHD) en formato
# Broadlink. Publicadas en la comunidad de Home Assistant:
# https://community.home-assistant.io/t/movistar-plus-hd-set-top-box-arris-ir-codes-with-broadlink-r3-mini/151962
CODIGOS_MOVISTAR: dict[str, str] = {
    "0": "OABEAB8fFSgLFAseCx4LHgseCx4LHgsoCzILCgsUCx4LPAseCwAHAh8fFSgLFAseCx4LHgseCx4LHgsoCzILCgsUCx4LPAseCwAHAg==",
    "1": "OABEAB8fFSgLFAseCx4LHgseCx4LKAseCygLFAsUCx4LPAseCwAHAh8fFSgLFAseCx4LHgseCx4LKAseCygLFAsUCx4LPAseCwAHAg==",
    "2": "OABEAB8fFSgLFAseCx4LHgseCx4LKAsoCx4LFAsUCx4LHgseCwAHIB8fFSgLFAseCx4LHgseCx4LKAsoCx4LFAsUCx4LHgseCwAHIA==",
    "3": "OABEAB8fFSgLFAseCx4LHgseCx4LKAsyCxQLFAsUCx4LHgsoCwAHFh8fFSgLFAseCx4LHgseCx4LKAsyCxQLFAsUCx4LHgsoCwAHFg==",
    "4": "OABAAB8fFSgLFAseCx4LHgseCx4LHgsoCzIWHgseCzwLFAsABwwfHxUoCxQLHgseCx4LHgseCx4LKAsyFh4LHgs8CxQLAAcM",
    "5": "OABAAB8fFSgLFAseCx4LHgseCx4LHgsyCygWHgseCzwLHgsABwIfHxUoCxQLHgseCx4LHgseCx4LMgsoFh4LHgs8Cx4LAAcC",
    "6": "OABAAB8fFSgLFAseCx4LHgseCx4LHgs8Cx4WHgseCx4LHgsAByAfHxUoCxQLHgseCx4LHgseCx4LPAseFh4LHgseCx4LAAcg",
    "7": "OABAAB8fFSgLFAseCx4LHgseCx4LKAsUCzwWHgseCx4LKAsABxYfHxUoCxQLHgseCx4LHgseCygLFAs8Fh4LHgseCygLAAcW",
    "8": "OABAAB8fFSgLFAseCx4LHgseCx4LKAseCzIWHgseCx4LMgsABwwfHxUoCxQLHgseCx4LHgseCygLHgsyFh4LHgseCzILAAcM",
    "9": "OABAAB8fFSgLFAseCx4LHgseCx4LKAsoCygWHgseCx4LPAsABwIfHxUoCxQLHgseCx4LHgseCygLKAsoFh4LHgseCzwLAAcC",
}


def mando_configurado(options: dict[str, Any]) -> bool:
    """True si hay un mando elegido."""
    return bool(options.get(CONF_MANDO))


def normalizar_codigo(codigo: str | None) -> str:
    """Admite el código con o sin el prefijo `b64:` y sin espacios."""
    codigo = (codigo or "").strip()
    if not codigo:
        return ""
    if codigo.lower().startswith("b64:"):
        codigo = codigo[4:]
    return "b64:" + re.sub(r"\s+", "", codigo)


def codigo_valido(codigo: str) -> bool:
    """Comprueba que un código `b64:` decodifica (vacío también vale)."""
    if not codigo:
        return True
    cuerpo = codigo[4:] if codigo.lower().startswith("b64:") else codigo
    if not _B64.match(cuerpo):
        return False
    try:
        return len(base64.b64decode(re.sub(r"\s+", "", cuerpo), validate=True)) > 4
    except (binascii.Error, ValueError):
        return False


def comandos_para_dial(options: dict[str, Any], dial: int) -> list[str]:
    """Lista de comandos (uno por dígito, más la tecla final si la hay)."""
    digitos = str(int(dial))
    modo = options.get(CONF_MODO_MANDO, MODO_CODIGOS)
    comandos: list[str] = []
    if modo == MODO_MOVISTAR:
        comandos = [f"b64:{CODIGOS_MOVISTAR[d]}" for d in digitos]
    elif modo == MODO_PLANTILLA:
        plantilla = options.get(CONF_PLANTILLA) or DEFAULT_PLANTILLA
        comandos = [plantilla.replace("{digito}", d) for d in digitos]
    else:
        faltan = [d for d in dict.fromkeys(digitos) if not options.get(CONF_CODIGOS[int(d)])]
        if faltan:
            raise ServiceValidationError(
                f"Falta el código IR del dígito {', '.join(faltan)} para marcar el {dial}. "
                "Añádelo en Configurar → Mando",
                translation_domain=DOMAIN,
                translation_key="falta_codigo",
                translation_placeholders={"digitos": ", ".join(faltan), "dial": str(dial)},
            )
        comandos = [normalizar_codigo(options[CONF_CODIGOS[int(d)]]) for d in digitos]
    if modo != MODO_MOVISTAR and (final := (options.get(CONF_TECLA_FINAL) or "").strip()):
        comandos.append(normalizar_codigo(final) if modo == MODO_CODIGOS else final)
    return comandos


async def async_sintonizar(
    hass: HomeAssistant,
    options: dict[str, Any],
    dial: int,
    mando: str | None = None,
) -> dict[str, Any]:
    """Marca el dial en el descodificador."""
    entidad = mando or options.get(CONF_MANDO)
    if not entidad:
        raise ServiceValidationError(
            "No hay ningún mando configurado. Elígelo en FutDial → Configurar → Mando",
            translation_domain=DOMAIN,
            translation_key="sin_mando",
        )
    comandos = comandos_para_dial(options, dial)
    datos: dict[str, Any] = {
        "entity_id": entidad,
        "command": comandos,
        "delay_secs": float(options.get(CONF_RETARDO, DEFAULT_RETARDO)),
    }
    if options.get(CONF_MODO_MANDO) == MODO_PLANTILLA and (
        dispositivo := (options.get(CONF_DISPOSITIVO) or "").strip()
    ):
        datos["device"] = dispositivo
    try:
        await hass.services.async_call("remote", "send_command", datos, blocking=True)
    except HomeAssistantError as err:
        raise HomeAssistantError(f"No se pudo enviar el dial {dial} a {entidad}: {err}") from err
    return {"mando": entidad, "dial": dial, "pulsaciones": len(comandos)}
