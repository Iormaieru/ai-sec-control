# Worker — sincronización con Jira

Servicio aparte del backend. No expone HTTP. Es dueño de la sincronización periódica con Jira (proyecto MDA, tablero IA-SEC).

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

## Código

Reutiliza los modelos y la lógica de dominio del backend (`backend/app`), que la imagen copia como librería. Por eso **se construye desde la raíz del repo**:

```
aisec_worker/
  __main__.py   loop: LISTEN + pull periódico + lock (una vuelta a la vez)
  push.py       eventos de jira_outbox -> Jira
  pull.py       tickets del tablero -> casos
  discover.py   relevamiento de la configuración de Jira (sólo lectura)
```

## Correr en local

Usa el entorno y el `.env` del backend:

```bash
cd backend
PYTHONPATH=../worker .venv/bin/python -m aisec_worker            # worker
PYTHONPATH=../worker .venv/bin/python -m aisec_worker --una-vez  # una vuelta y sale
PYTHONPATH=../worker .venv/bin/python -m aisec_worker.discover   # ver tablero, columnas y campos
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

Las migraciones las corre el backend (*Pre-deploy Command*: `alembic upgrade head`). Si el worker arranca antes de que terminen, la primera vuelta falla y la siguiente ya funciona.

En los logs deberías ver:

```
Worker de sincronización con Jira iniciado
Sincronización con Jira {"push_enviados": 0, "pull_nuevos": 34, ...}
Escuchando eventos de la plataforma
```
