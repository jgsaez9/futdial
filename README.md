<p align="center">
  <img src="logo.png" alt="FutDial" width="200">
</p>

# FutDial

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories)
[![release](https://img.shields.io/github/v/release/jgsaez9/futdial)](https://github.com/jgsaez9/futdial/releases)

Integración para Home Assistant que te dice **en qué canal y dial de Movistar Plus+ echan un partido** y, si quieres, **lo pone en la tele**.

> **Atleti** → `M+ LALIGA - 54` · domingo 08/11/2026 a las 21:00

## Instalación

1. HACS → ⋮ → **Repositorios personalizados** → añade `https://github.com/jgsaez9/futdial` como **Integración**.
2. Descarga **FutDial** y reinicia Home Assistant.
3. **Ajustes → Dispositivos y servicios → Añadir integración → FutDial**.

[![Abrir en HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jgsaez9&repository=futdial&category=integration)

## Configuración

En **FutDial → Configurar** hay tres apartados:

### General

- **Equipos a seguir**: elige de la lista (LALIGA EA SPORTS, HYPERMOTION, Selección y grandes de Europa) o escribe cualquier otro.
- **Actualizar la programación**: desde cada 30 min hasta una vez a la semana.
- **Días de programación**, **incluir repeticiones** y **buscar en todos los canales** (por defecto sólo los de deportes, generalistas y autonómicos).

### Mando (opcional, para poner el partido en la tele)

- Elige tu entidad `remote` (p. ej. un Broadlink).
- Modo **Descodificador Movistar+ (códigos incluidos)**: no hay que configurar nada más.
- También admite tus propios códigos IR por dígito o una plantilla de comando (p. ej. `KEYCODE_{digito}` para Android TV).

### Automático (poner los partidos solos)

- Elige los equipos **en orden de preferencia** y cuántos minutos antes del inicio se pone el canal (p. ej. 30).
- Si dos partidos coinciden, manda el del equipo con más preferencia: el otro no se pone, y si ya estaba puesto se cambia al preferido cuando le toque. Si ambos juegan el mismo partido, se pone una sola vez.
- Sólo directos y estrenos, nunca repeticiones.
- Para cambiar el orden, quita los equipos y vuelve a añadirlos en el orden que quieras.
- Cada vez que pone un partido lanza el evento `futdial_partido_puesto` (útil para notificaciones).

## Entidades

Por cada equipo que sigas:

| Entidad | Ejemplo |
| --- | --- |
| `sensor.futdial_proximo_partido_<equipo>` | `M+ LALIGA - 54` |
| `sensor.futdial_dial_<equipo>` | `54` (atributos `fecha`, `hora`, `partido`…) |
| `sensor.futdial_fecha_partido_<equipo>` | Fecha y hora de inicio |
| `button.futdial_poner_partido_<equipo>` | Pone el canal en la tele (con mando) |

Además:

| Entidad | Para qué sirve |
| --- | --- |
| `text.futdial_buscar_partido` | Escribe un equipo o partido (`Atleti Barça`, `Betis`…) |
| `sensor.futdial_resultado_busqueda` (+ `_dial`, `_fecha`) | Resultado de esa búsqueda |
| `button.futdial_poner_resultado_busqueda` | Pone en la tele lo buscado |
| `sensor.futdial_partidos_hoy` | Partidos que quedan hoy, con canal y dial |
| `switch.futdial_poner_partidos_automaticamente` | Activa o pausa el modo automático |
| `sensor.futdial_proximo_partido_automatico` | Cuándo y qué partido se pondrá solo (atributos `programados` y `descartados`) |

Sólo cuenta las emisiones en directo o de estreno. Si un partido va por varios canales, aparecen todos.

## Acciones

```yaml
# Buscar (devuelve canal, dial, fecha, hora y un texto listo para notificar)
action: futdial.buscar_partido
data:
  partido: Atleti
response_variable: r

# Poner en la tele un partido o un dial
action: futdial.sintonizar
data:
  partido: Atleti      # o bien  dial: 54
```

`futdial.actualizar` fuerza la descarga de la programación.

## Ejemplos

### Aviso 15 minutos antes

```yaml
triggers:
  - trigger: time
    at:
      entity_id: sensor.futdial_fecha_partido_atletico_de_madrid
      offset: "-00:15:00"
actions:
  - action: notify.mobile_app_mi_movil
    data:
      title: "Partido en el dial {{ states('sensor.futdial_dial_atletico_de_madrid') }}"
      message: "{{ state_attr('sensor.futdial_proximo_partido_atletico_de_madrid', 'texto') }}"
```

### Tarjeta con los partidos de hoy

```yaml
type: markdown
title: ⚽ Hoy en Movistar Plus+
content: |
  {% for p in state_attr('sensor.futdial_partidos_hoy', 'partidos') or [] %}
  {{ '🔴' if p.en_juego else '🕒' }} **{{ p.hora }}** {{ p.partido }} — `{{ p.todos_los_canales }}`
  {% else %}
  No quedan partidos hoy.
  {% endfor %}
```

## Voz (Assist)

Copia [`custom_sentences/es/futdial.yaml`](custom_sentences/es/futdial.yaml) en `/config/custom_sentences/es/` y reinicia:

- «¿En qué canal echan el Atleti?» → *Atlético de Madrid - FC Barcelona se emite hoy a las 21:00 en M+ LALIGA (dial 54).*
- «Pon el partido del Atleti» → *Pongo Atlético de Madrid - FC Barcelona en M+ LALIGA, dial 54.*

---

Proyecto no oficial, sin relación con Telefónica ni Movistar Plus+. Los datos salen de la guía pública de programación.
