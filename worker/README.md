# Worker — sincronización con Jira y revisión de herramientas

Servicio aparte del backend. No expone HTTP. Tiene dos tareas:

1. **Sincronización con Jira** (proyecto MDA, tablero IA-SEC).
2. **Revisión de herramientas de pentesting** cada 15 días, en un hilo aparte (ver más abajo).

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
```

## Correr en local

Usa el entorno y el `.env` del backend:

```bash
cd backend
PYTHONPATH=../worker .venv/bin/python -m aisec_worker            # worker
PYTHONPATH=../worker .venv/bin/python -m aisec_worker --una-vez  # una vuelta y sale
PYTHONPATH=../worker .venv/bin/python -m aisec_worker.discover   # ver tablero, columnas y campos
PYTHONPATH=../worker .venv/bin/python -m aisec_worker --herramientas  # una revisión de herramientas ya
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
