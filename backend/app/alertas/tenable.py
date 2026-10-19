"""Cliente mínimo de Tenable Vulnerability Management (cloud.tenable.com).

Usa sólo la exportación de vulnerabilidades (POST /vulns/export, estado y
chunks), que es lo que habilitan las claves del área: el inventario de
software y los escaneos de puertos son "vulnerabilidades" informativas de
plugins concretos. Autentica con el header X-ApiKeys; las claves nunca se
loguean.
"""

import time
from collections.abc import Iterator
from typing import Any

import httpx

from app.core.config import Settings, get_settings

# Plugins de Nessus que se exportan.
PLUGINS_SOFTWARE = [20811, 22869]  # software instalado: Windows / Linux (SSH)
PLUGINS_PUERTOS = [11219, 10335, 34220, 14272]  # SYN, TCP, netstat (WMI), netstat (SSH)

ESPERA_ENTRE_CONSULTAS = 5  # segundos entre consultas del estado de la exportación
ESPERA_MAXIMA = 30 * 60


class TenableError(Exception):
    pass


class TenableClient:
    def __init__(self, settings: Settings | None = None, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.tenable_access_key or not self.settings.tenable_secret_key:
            raise TenableError("Faltan AISEC_TENABLE_ACCESS_KEY / AISEC_TENABLE_SECRET_KEY")
        claves = f"accessKey={self.settings.tenable_access_key};secretKey={self.settings.tenable_secret_key}"
        self._http = httpx.Client(
            base_url=self.settings.tenable_base_url.rstrip("/"),
            headers={"X-ApiKeys": claves, "Accept": "application/json"},
            timeout=httpx.Timeout(120, connect=15),
            transport=transport,
        )
        self._esperar = time.sleep  # los tests lo reemplazan

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "TenableClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _request(self, metodo: str, ruta: str, **kwargs: Any) -> Any:
        try:
            resp = self._http.request(metodo, ruta, **kwargs)
        except httpx.HTTPError as exc:
            raise TenableError(f"{metodo} {ruta}: {type(exc).__name__}") from exc
        if resp.is_error:
            raise TenableError(f"{metodo} {ruta} -> {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    def exportar(self, plugin_ids: list[int]) -> Iterator[dict]:
        """Registros vigentes de esos plugins (estado actual: sin los "FIXED",
        que serían software ya desinstalado o puertos ya cerrados), de a un
        chunk por vez para no cargar todo en memoria."""
        exportacion = self._request(
            "POST",
            "/vulns/export",
            json={"num_assets": 500, "filters": {"plugin_id": plugin_ids, "state": ["OPEN", "REOPENED"]}},
        )
        uuid = exportacion["export_uuid"]
        esperado = 0
        while True:
            estado = self._request("GET", f"/vulns/export/{uuid}/status")
            if estado["status"] == "FINISHED":
                break
            if estado["status"] in ("ERROR", "CANCELLED") or esperado > ESPERA_MAXIMA:
                raise TenableError(f"Exportación {estado['status'].lower()} ({uuid})")
            self._esperar(ESPERA_ENTRE_CONSULTAS)
            esperado += ESPERA_ENTRE_CONSULTAS
        for chunk in estado.get("chunks_available", []):
            yield from self._request("GET", f"/vulns/export/{uuid}/chunks/{chunk}")


def crear_cliente() -> TenableClient:
    """Punto único de creación (los tests lo reemplazan)."""
    if not get_settings().tenable_enabled:
        raise TenableError("La integración con Tenable está deshabilitada (AISEC_TENABLE_ENABLED)")
    return TenableClient()
