<p align="center">
  <img src="logo.png" alt="FutDial" width="220">
</p>

# FutDial

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories)
[![Validate](https://github.com/jgsaez9/futdial/actions/workflows/validate.yml/badge.svg)](https://github.com/jgsaez9/futdial/actions/workflows/validate.yml)
[![release](https://img.shields.io/github/v/release/jgsaez9/futdial)](https://github.com/jgsaez9/futdial/releases)

Integración para **Home Assistant** que te dice **en qué canal y número de dial de Movistar Plus+** se emite un partido de fútbol:

> **Atleti Barça** → `M+ LALIGA - 54`

Usa la guía de programación oficial de Movistar Plus+ (la misma que la web/app), así que cubre todos los canales: M+ LALIGA, DAZN LALIGA, LALIGA TV HYPERMOTION, M+ Liga de Campeones, M+ Vamos, Primera Federación, Teledeporte, La 1, TV3…

## Qué incluye

| Entidad / servicio | Para qué sirve |
| --- | --- |
| `text.futdial_buscar_partido` | Escribe un equipo o partido (p. ej. `Atleti Barça`). |
| `sensor.futdial_resultado_busqueda` | Estado: `M+ LALIGA - 54`. Atributos: partido, competición, hora, todos los canales… |
| `sensor.futdial_proximo_partido_<equipo>` | Uno por cada equipo que sigas. Siempre muestra el canal y dial de su próximo partido. |
| `sensor.futdial_partidos_hoy` | Número de partidos que quedan hoy, con la lista completa (hora, partido, canal y dial). |
| `futdial.buscar_partido` | Servicio con respuesta, para scripts y automatizaciones. |
| `futdial.actualizar` | Fuerza la descarga de la guía. |
| Intent de Assist | «¿En qué canal echan el Atleti?» → «Atlético de Madrid - FC Barcelona (LALIGA EA SPORTS) se emite hoy a las 21:00 en M+ LALIGA (dial 54).» |

Por defecto sólo se tienen en cuenta las emisiones **en directo / estreno** (no repeticiones ni resúmenes). Si un partido se emite en varios canales a la vez, aparecen todos (`M+ Vamos - 11, M+ Liga de Campeones - 60`).

La búsqueda ignora mayúsculas y acentos y entiende apodos habituales: `Atleti`, `Barça`, `Depor`, `Juve`, `PSG`, `United`… Si buscas un club, el primer equipo tiene prioridad sobre el femenino o el filial salvo que lo pidas (`Barcelona femenino`, `Castilla`).

## Instalación (HACS)

1. En Home Assistant abre **HACS → ⋮ → Repositorios personalizados**.
2. Añade `https://github.com/jgsaez9/futdial` con el tipo **Integración**.
3. Busca **FutDial** en HACS, pulsa **Descargar** y reinicia Home Assistant.
4. Ve a **Ajustes → Dispositivos y servicios → Añadir integración → FutDial**.

[![Abrir en HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jgsaez9&repository=futdial&category=integration)

Cuando se publique una versión nueva, HACS la mostrará como actualización disponible.

### Instalación manual

Copia `custom_components/futdial` en la carpeta `config/custom_components/` de tu Home Assistant y reinicia.

## Configuración

Todo se configura desde la interfaz (y se puede cambiar después en **Configurar**):

- **Equipos a seguir**: crea un sensor «Próximo partido …» por equipo.
- **Días de programación** (1–7, por defecto 3).
- **Intervalo de actualización** (por defecto 120 min). La guía de cada día pesa unos 11 MB; los días a partir de pasado mañana se refrescan como mucho cada 6 h.
- **Incluir repeticiones y resúmenes**.

Requiere Home Assistant 2024.11 o posterior. El logo dentro de Home Assistant se muestra a partir de la 2026.3.

## Ejemplos

### Script que pregunta y notifica

```yaml
script:
  donde_echan_partido:
    fields:
      equipo:
        example: "Atleti"
    sequence:
      - action: futdial.buscar_partido
        data:
          partido: "{{ equipo }}"
        response_variable: r
      - action: notify.mobile_app_mi_movil
        data:
          title: "{{ r.resultado or 'Sin emisión' }}"
          message: "{{ r.texto }}"
```

Respuesta del servicio:

```yaml
consulta: Atleti Barça
encontrado: true
resultado: M+ LALIGA - 54
canal: M+ LALIGA
dial: 54
texto: Atlético de Madrid - FC Barcelona (LALIGA EA SPORTS) se emite hoy a las 21:00 en M+ LALIGA (dial 54).
partidos:
  - partido: Atlético de Madrid - FC Barcelona
    competicion: LALIGA EA SPORTS
    canal_dial: M+ LALIGA - 54
    todos_los_canales: M+ LALIGA - 54
    inicio: "2026-11-08T21:00:00+01:00"
    cuando: hoy a las 21:00
    en_juego: false
```

### Aviso 15 minutos antes del partido de tu equipo

```yaml
automation:
  - alias: Aviso partido Atleti
    triggers:
      - trigger: template
        value_template: >
          {% set i = state_attr('sensor.futdial_proximo_partido_atleti', 'inicio') %}
          {{ i is not none and (as_datetime(i) - now()).total_seconds() | int(0) in range(0, 900) }}
    actions:
      - action: notify.mobile_app_mi_movil
        data:
          title: "¡Empieza el partido!"
          message: "{{ state_attr('sensor.futdial_proximo_partido_atleti', 'texto') }}"
```

### Tarjeta Markdown con los partidos de hoy

```yaml
type: markdown
title: ⚽ Fútbol hoy en Movistar Plus+
content: |
  {% for p in state_attr('sensor.futdial_partidos_hoy', 'partidos') or [] %}
  {{ '🔴' if p.en_juego else '🕒' }} **{{ p.hora }}** {{ p.partido }} — `{{ p.todos_los_canales }}`
  {% else %}
  No quedan partidos hoy.
  {% endfor %}
```

### Buscador en el panel

```yaml
type: entities
entities:
  - entity: text.futdial_buscar_partido
  - entity: sensor.futdial_resultado_busqueda
    secondary_info: last-changed
```

## Asistente de voz (Assist)

Copia [`custom_sentences/es/futdial.yaml`](custom_sentences/es/futdial.yaml) a `/config/custom_sentences/es/futdial.yaml` y reinicia. Después podrás preguntar:

- «¿En qué canal echan el Atleti?»
- «¿Dónde ponen el Betis Sevilla?»
- «¿Qué dial es el partido del Barça?»

Si usas un agente de conversación con LLM, el intent `FutDialBuscarPartido` también queda disponible como herramienta.

## Publicar una versión nueva (para el mantenedor)

1. Sube `version` en `custom_components/futdial/manifest.json` (p. ej. `1.0.1`).
2. Haz commit y push a `main`.
3. Crea y sube el tag con la misma versión: `git tag v1.0.1 && git push origin v1.0.1`.

La acción *Release* crea la release de GitHub automáticamente y HACS la ofrecerá como actualización.

## Aviso

Proyecto no oficial, sin relación con Telefónica ni Movistar Plus+. Los datos proceden de la guía pública de programación y pueden cambiar sin aviso. Los diales son los de Movistar Plus+ por fibra/IPTV en España.
