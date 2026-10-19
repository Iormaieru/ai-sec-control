# Worker — Jira, herramientas y alertas

Servicio aparte del backend. No expone HTTP. Tiene cuatro tareas, cada una en su propio hilo:

1. **Sincronización con Jira** (proyecto MDA, tablero IA-SEC).
2. **Revisión de herramientas de pentesting** cada 15 días.
3. **Alertas de Netskope** cada 5 minutos, si `AISEC_NETSKOPE_ENABLED=true`.
4. **Inventario de Tenable** una vez por día, si `AISEC_TENABLE_ENABLED=true`.

Si Jira está deshabilitado, el worker sigue corriendo sólo con la segunda tarea.

## Sincronización con Jira

| Sentido | Cómo |
|---|---|
| Plataforma → Jira | El backend guarda cada cambio como evento en `jira_outbox`, en la misma transacción, y emite `NOTIFY jira_outbox`. El worker hace `LISTEN`, se despierta y envía los eventos en segundos. Si un aviso se pierde, el evento sale en la vuelta periódica. |
| Jira → plataforma | Jira no avisa (no hay webhook), así que cada `AISEC_JIRA_SYNC_INTERVALO_SEGUNDOS` (120 por defecto) el worker trae los tickets del tablero que cambiaron. La primera vez los trae todos. |

Errores:
- **Transitorios** (Jira caído, timeout, 429/5xx): se reintentan con backoff.
- **Rechazos de Jira** (4xx): dejan el caso en error hasta que alguien pulse "Reintentar" en la plataforma.
- **Errores en una vuelta:** el worker los registra y sigue con la siguiente.
- **SIGTERM:** termina la vuelta en curso y sale.

En el backend quedan sólo las acciones que el usuario hace en vivo: transiciones, asignación y el webhook opcional.

## Revisión de herramientas (Catálogo, Radar, Distribuciones)

Especificación en `tasks/herramientas-radar.md`. Cada `AISEC_HERRAMIENTAS_REVISION_DIAS` (15 por defecto), o cuando un admin pulsa "Revisar ahora" en la plataforma:

1. **Distribuciones:** lee los índices de paquetes de Kali, Parrot y BlackArch y actualiza sus fichas (versión, categorías, cantidad de herramientas).
2. **Catálogo:** actualiza cada herramienta con GitHub (actividad, estrellas, archivada, mudanzas), PyPI/npm (versión) y las distribuciones. Recalcula sus criterios; las que dejan de estar mantenidas pasan a **en observación**.
3. **Radar:** descubre herramientas de seguridad de IA por temas de GitHub y por el grupo `blackarch-ai`. Las que cumplen los criterios y no fueron descartadas entran como candidatas, hasta 25 por revisión. Para cada una, el proveedor LLM sugiere los pasos de los estándares donde sirve, y un analista los confirma al aprobarla.

Si una fuente falla, se anota el error y la revisión sigue con el resto. Una revisión real tarda ~1,5 minutos.

Necesita, además de las variables de Jira:

| Variable | Para qué |
|---|---|
| `AISEC_GITHUB_TOKEN` | Token **fine-grained** de sólo lectura de repos públicos, sin permisos extra. Sin token, GitHub limita a 60 consultas por hora |
| `AISEC_LLM_PROVIDER`, `AISEC_OPENAI_API_KEY` | Sugerencia de vínculos. Sin LLM, las candidatas entran sin pasos sugeridos |
| `AISEC_HERRAMIENTAS_REVISION_DIAS` | Opcional; 15 por defecto |

## Alertas de Netskope (sector Alertas)

Cada `AISEC_NETSKOPE_INTERVALO_SEGUNDOS` (300), para cada regla activa (una consulta de Skope IT, ej. `app like mcp`):

1. **Consulta:** `GET {tenant}/api/v2/events/data/application` con la consulta y la ventana `[consultada_hasta − 30 min, ahora − AISEC_NETSKOPE_DEMORA_MINUTOS]`. La demora cubre la ingesta de Netskope. En la primera consulta de una regla se mira hacia atrás `AISEC_NETSKOPE_RETROSPECTIVA_DIAS` (7).
2. **Agrupación:** los eventos se agrupan en una alerta por **regla + app + usuario**. Los eventos repetidos no cuentan dos veces.
3. **Estados:**
   - Una alerta **resuelta** que recibe eventos nuevos vuelve a "nueva".
   - Una **descartada** (falso positivo) sólo acumula eventos, sin volver a avisar.
4. **Email:** al final de cada vuelta se manda **un solo email resumen** con las alertas nuevas a los destinatarios cargados en la plataforma (Alertas → Avisos por email). Si no hay ninguno cargado, va a `AISEC_ALERTAS_EMAIL_DESTINO`. Si el envío falla, se reintenta en la próxima vuelta.

Si una regla falla (token, 429, red), su cursor no avanza y el error se ve en la pestaña Reglas. Los logs sólo llevan cantidades, nunca usuarios.

| Variable | Para qué |
|---|---|
| `AISEC_NETSKOPE_ENABLED` | `true` para activar el hilo de alertas |
| `AISEC_NETSKOPE_TENANT_URL` | `https://bancomacro.goskope.com` |
| `AISEC_NETSKOPE_API_TOKEN` | Token de la API v2, de sólo lectura sobre eventos de aplicación |
| `AISEC_ALERTAS_EMAIL_DESTINO` | Respaldo: casillas separadas por coma, que se usan sólo si no hay destinatarios cargados en la plataforma. El envío real requiere `AISEC_EMAIL_BACKEND=smtp` |

El backend también necesita `AISEC_NETSKOPE_*`, para el botón "Probar" de las reglas.

## Inventario de Tenable

Cada `AISEC_TENABLE_INTERVALO_HORAS` (24) el worker exporta de Tenable Vulnerability Management (`POST /vulns/export`, sólo lectura) el inventario de software (plugins 20811 y 22869) y los puertos abiertos. Reemplaza la tabla `equipos_tenable` con lo relevante para IA: Ollama, LM Studio, Python, Anaconda, Jupyter, y los puertos 11434, 1234, 8888 y 7860. La exportación de ~12 mil equipos tarda unos 3 minutos.

Después evalúa las reglas de fuente Tenable:
- **servicio de IA expuesto:** un puerto de servicio de IA abierto;
- **equipo con actividad de IA fuera de Tenable:** el equipo aparece en alertas abiertas de Netskope y Tenable no lo inventaría, ni por hostname ni por NetBIOS.

Para una actualización manual (por ejemplo, desde Control-M): `python -m aisec_worker --tenable`.

| Variable | Para qué |
|---|---|
| `AISEC_TENABLE_ENABLED` | `true` para activar el hilo de Tenable |
| `AISEC_TENABLE_BASE_URL` | `https://cloud.tenable.com` |
| `AISEC_TENABLE_ACCESS_KEY` / `AISEC_TENABLE_SECRET_KEY` | Claves de API con alcance sobre `/vulns/export` |
| `AISEC_TENABLE_INTERVALO_HORAS` | Horas entre actualizaciones (24) |

El backend no llama a Tenable: el tablero "Seguridad de IA" lee lo que dejó el worker.

## Código

Reutiliza los modelos y la lógica de dominio del backend (`backend/app`), que la imagen copia como librería. Por eso **se construye desde la raíz del repo**:

```
aisec_worker/
  __main__.py   loop: LISTEN + pull periódico + lock (una vuelta a la vez)
  push.py       eventos de jira_outbox -> Jira
  pull.py       tickets del tablero -> casos
  discover.py   relevamiento de la configuración de Jira (sólo lectura)
  herramientas/
    fuentes.py     GitHub, PyPI/npm e índices de Kali, Parrot y BlackArch
    evaluacion.py  criterios ("mantenida", "adoptada", ...) y cambios de estado
    vinculos.py    pasos sugeridos por el LLM
    revision.py    orquesta la revisión y la registra en revision_herramientas
  alertas/
    procesamiento.py  reglas -> eventos de Netskope -> alertas (agrupación, reincidencia)
    aviso.py          email resumen de las alertas nuevas
```

El cliente de Netskope está en `backend/app/alertas/netskope.py`, porque lo comparten el worker y el botón "Probar" del backend.

## Correr en local

Usa el entorno y el `.env` del backend:

```bash
cd backend
PYTHONPATH=../worker .venv/bin/python -m aisec_worker            # worker
PYTHONPATH=../worker .venv/bin/python -m aisec_worker --una-vez  # una vuelta y sale
PYTHONPATH=../worker .venv/bin/python -m aisec_worker.discover   # ver tablero, columnas y campos
PYTHONPATH=../worker .venv/bin/python -m aisec_worker --herramientas  # una revisión de herramientas ya
PYTHONPATH=../worker .venv/bin/python -m aisec_worker --alertas       # una vuelta de alertas de Netskope
```

Con Docker: `docker compose --profile jira up worker`. No arranca con un `up` común porque opera sobre el **Jira real**.

Tests (misma base de test que el backend):

```bash
cd worker && ../backend/.venv/bin/python -m pytest
```

## Despliegue en Railway

Servicio nuevo desde el mismo repo:

- **Root Directory:** vacío (`/`). La imagen necesita `backend/` y `worker/`.
- **Config file:** `/worker/railway.json`. Define el Dockerfile, los *watch paths* y la política de reinicio.
- **Networking:** sin dominio público.
- **Variables** (las mismas que el backend):

  | Variable | Nota |
  |---|---|
  | `AISEC_DATABASE_URL` | La misma base que el backend |
  | `AISEC_ENVIRONMENT` | |
  | `AISEC_JWT_SECRET` | La configuración lo exige fuera de development |
  | `AISEC_JIRA_ENABLED` | `true` |
  | `AISEC_JIRA_EMAIL` | |
  | `AISEC_JIRA_API_TOKEN` | |
  | `AISEC_JIRA_SYNC_INTERVALO_SEGUNDOS` | Opcional; 120 por defecto, mínimo 30 |
  | `AISEC_GITHUB_TOKEN` | Revisión de herramientas (ver arriba) |
  | `AISEC_LLM_PROVIDER`, `AISEC_OPENAI_API_KEY` | Vínculos sugeridos en el Radar |

Las migraciones las corre el backend (*Pre-deploy Command*: `alembic upgrade head`). Si el worker arranca antes de que terminen, la primera vuelta falla y la siguiente ya funciona.

En los logs deberías ver:

```
Worker de sincronización con Jira iniciado
Sincronización con Jira {"push_enviados": 0, "pull_nuevos": 34, ...}
Escuchando eventos de la plataforma
```
