"""Cliente mínimo de la REST API v2 de Netskope: eventos de aplicación.

GET {tenant}/api/v2/events/data/application con la misma consulta que se usa
en Skope IT (ej. `app like mcp`) y una ventana de tiempo en epoch. Autentica
con el header Netskope-Api-Token; el token nunca se loguea.

La forma de cada evento (nombres de campos) se interpreta sólo en
`normalizar`: si el tenant devuelve otros nombres, se ajusta ahí.
"""

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import Settings, get_settings

RUTA_EVENTOS = "/api/v2/events/data/application"
TAMANIO_PAGINA = 1000
MAX_EVENTOS_POR_CONSULTA = 20000  # tope de seguridad por regla y vuelta


class NetskopeError(Exception):
    def __init__(self, mensaje: str, status_code: int | None = None) -> None:
        super().__init__(mensaje)
        self.status_code = status_code


class DemasiadosEventos(NetskopeError):
    """La ventana pedida tiene más eventos que el tope por consulta: hay que
    partirla. Nunca se devuelven resultados parciales en silencio (el cursor
    avanzaría y esos eventos se perderían)."""


@dataclass
class EventoNetskope:
    evento_id: str
    fecha: dt.datetime
    usuario: str
    app: str
    actividad: str | None
    sitio: str | None
    objeto: str | None
    datos: dict[str, Any] = field(default_factory=dict)  # campos útiles del evento original


# Campos del evento original que se guardan como evidencia (no todo el evento).
# Validados contra el tenant (2026-10-19). No se guardan los JWT_* (claims del
# token del usuario: sensibles y sin valor para la alerta).
_CAMPOS_EVIDENCIA = (
    "app", "category", "activity", "action", "policy", "site", "object", "url", "hostname",
    "access_method", "device", "os", "process_name", "parent_process_name", "src_location", "src_country",
    "cci", "ccl",
    # Específicos de agentes de IA / MCP
    "agentic_protocol", "mcp_activity", "mcp_client_name", "mcp_server_name", "mcp_protocol_version",
    "mcp_tool_name", "mcp_tool_list",  # qué herramienta se ejecutó y cuáles ofrece el servidor
)


def normalizar(evento: dict[str, Any]) -> EventoNetskope | None:
    """Evento crudo de Netskope -> EventoNetskope. None si le falta lo mínimo
    (id, fecha, app) para agruparlo."""
    evento_id = evento.get("_id") or evento.get("id")
    timestamp = evento.get("timestamp")
    app = evento.get("app")
    if not evento_id or timestamp is None or not app:
        return None
    usuario = evento.get("user") or evento.get("ur_normalized") or evento.get("userkey") or "(sin usuario)"
    return EventoNetskope(
        evento_id=str(evento_id),
        fecha=dt.datetime.fromtimestamp(int(timestamp), tz=dt.UTC),
        usuario=str(usuario)[:300],
        app=str(app)[:300],
        actividad=(str(evento["activity"])[:200] if evento.get("activity") else None),
        sitio=(str(evento["site"])[:300] if evento.get("site") else None),
        objeto=(str(evento["object"])[:500] if evento.get("object") else None),
        datos={k: evento[k] for k in _CAMPOS_EVIDENCIA if evento.get(k) not in (None, "")},
    )


class NetskopeClient:
    def __init__(self, settings: Settings | None = None, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.netskope_api_token:
            raise NetskopeError("Falta AISEC_NETSKOPE_API_TOKEN")
        self._http = httpx.Client(
            base_url=self.settings.netskope_tenant_url.rstrip("/"),
            headers={"Netskope-Api-Token": self.settings.netskope_api_token, "Accept": "application/json"},
            timeout=httpx.Timeout(60, connect=15),
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "NetskopeClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def eventos(self, consulta: str, desde: dt.datetime, hasta: dt.datetime) -> list[EventoNetskope]:
        """Eventos de aplicación que cumplen `consulta` en [desde, hasta)."""
        resultado: list[EventoNetskope] = []
        offset = 0
        while True:
            params = {
                "query": consulta,
                "starttime": int(desde.timestamp()),
                "endtime": int(hasta.timestamp()),
                "limit": TAMANIO_PAGINA,
                "offset": offset,
            }
            try:
                resp = self._http.get(RUTA_EVENTOS, params=params)
            except httpx.HTTPError as exc:
                raise NetskopeError(f"GET {RUTA_EVENTOS}: {type(exc).__name__}") from exc
            if resp.is_error:
                raise NetskopeError(f"GET {RUTA_EVENTOS} -> {resp.status_code}: {resp.text[:300]}", resp.status_code)
            cuerpo = resp.json()
            pagina = cuerpo.get("result") or cuerpo.get("data") or []
            resultado += [e for e in (normalizar(crudo) for crudo in pagina) if e is not None]
            offset += len(pagina)
            if len(pagina) < TAMANIO_PAGINA:
                return resultado
            if offset >= MAX_EVENTOS_POR_CONSULTA:
                raise DemasiadosEventos(f"Más de {MAX_EVENTOS_POR_CONSULTA} eventos entre {desde} y {hasta}")


def crear_cliente() -> NetskopeClient:
    """Punto único de creación (los tests lo reemplazan)."""
    if not get_settings().netskope_enabled:
        raise NetskopeError("La integración con Netskope está deshabilitada (AISEC_NETSKOPE_ENABLED)")
    return NetskopeClient()
