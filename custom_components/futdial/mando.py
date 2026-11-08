"""Enviar el dial al descodificador a través de una entidad `remote`.

Funciona con cualquier integración que implemente `remote.send_command`:
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
    MODO_PLANTILLA,
)

_B64 = re.compile(r"^[A-Za-z0-9+/=\s]+$")


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
    if modo == MODO_PLANTILLA:
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
    if final := (options.get(CONF_TECLA_FINAL) or "").strip():
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
