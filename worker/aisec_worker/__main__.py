"""Loop del worker: python -m aisec_worker

- Eventos de la plataforma: escucha el canal de jira_outbox (LISTEN). Cada
  NOTIFY lo despierta y envía los eventos pendientes a Jira en segundos.
- Cambios en Jira: cada AISEC_JIRA_SYNC_INTERVALO_SEGUNDOS trae los tickets
  del tablero que cambiaron (Jira no avisa). En esa vuelta también envía
  cualquier evento que haya quedado pendiente (aviso perdido, reintentos).

Un error en una vuelta (Jira caído, timeout, base reiniciando) se loguea y
se reintenta en la siguiente. El proceso termina con SIGTERM (redeploy) o
Ctrl+C después de completar la vuelta en curso.

Opciones: --una-vez (una sola vuelta completa y sale, para pruebas).
"""

import argparse
import logging
import signal
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal, engine
from app.integraciones.jira import sync
from app.integraciones.jira.outbox import CANAL

from aisec_worker.pull import pull
from aisec_worker.push import push

logger = logging.getLogger("aisec_worker")

_LOCK = 7_241_001  # pg advisory lock: una sola vuelta a la vez (durante un redeploy conviven dos workers)
_INTERVALO_MINIMO = 30
_ESPERA_MAXIMA = 5  # cada cuánto se revisa si llegó la señal de apagado

_detener = threading.Event()


@contextmanager
def _lock() -> Iterator[bool]:
    with engine.connect() as conn:
        obtenido = bool(conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _LOCK}).scalar())
        try:
            yield obtenido
        finally:
            if obtenido:
                conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _LOCK})
                conn.commit()


def vuelta(*, con_pull: bool) -> None:
    """Envía los eventos pendientes y, si corresponde, trae los cambios de Jira."""
    with _lock() as obtenido:
        if not obtenido:
            logger.info("Otra instancia está sincronizando; se omite esta vuelta")
            return
        db = SessionLocal()
        try:
            with sync.crear_cliente() as client:
                enviados = push(db, client)
                traidos = pull(db, client) if con_pull else None
        finally:
            db.close()

    for error in enviados.errores + (traidos.errores if traidos else []):
        logger.warning("Error de sincronización", extra={"detalle": error})
    if traidos is not None:
        logger.info(
            "Sincronización con Jira",
            extra={
                "push_enviados": enviados.enviados,
                "pull_nuevos": traidos.nuevos,
                "pull_actualizados": traidos.actualizados,
                "errores": len(enviados.errores) + len(traidos.errores),
            },
        )


class Escucha:
    """Conexión dedicada con LISTEN sobre el canal de la outbox. Si se cae,
    se reconecta en la próxima espera; mientras tanto el worker sigue con el
    pull periódico, que también envía los pendientes."""

    def __init__(self, database_url: str) -> None:
        # La URL de SQLAlchemy ("postgresql+psycopg://...") a una que entienda libpq.
        self._dsn = make_url(database_url).set(drivername="postgresql").render_as_string(hide_password=False)
        self._conn: psycopg.Connection | None = None

    def _conectar(self) -> psycopg.Connection:
        if self._conn is None or self._conn.closed:
            self._conn = psycopg.connect(self._dsn, autocommit=True)
            self._conn.execute(f"LISTEN {CANAL}")
            logger.info("Escuchando eventos de la plataforma", extra={"canal": CANAL})
        return self._conn

    def esperar(self, segundos: float) -> bool:
        """True si llegó al menos un evento antes de `segundos`."""
        try:
            conn = self._conectar()
            llego = any(True for _ in conn.notifies(timeout=segundos, stop_after=1))
            if llego:
                # Un cambio suele traer varios eventos seguidos: se juntan.
                for _ in conn.notifies(timeout=0.5):
                    pass
            return llego
        except psycopg.Error:
            logger.warning("Se perdió la conexión de LISTEN; se reintenta", exc_info=True)
            self.cerrar()
            _detener.wait(segundos)
            return False

    def cerrar(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None


def correr(intervalo: int) -> None:
    escucha = Escucha(get_settings().database_url)
    logger.info("Worker de sincronización con Jira iniciado", extra={"intervalo_segundos": intervalo})
    proximo_pull = 0.0
    con_pull = True
    try:
        while not _detener.is_set():
            try:
                vuelta(con_pull=con_pull)
            except sync.JiraDeshabilitada as exc:
                # Mal configurado: reintentar no sirve; terminar lo hace visible en el panel.
                sys.exit(str(exc))
            except Exception:
                logger.exception("Falló la sincronización con Jira; se reintenta en la próxima vuelta")
            if con_pull:
                proximo_pull = time.monotonic() + intervalo

            # Espera hasta el próximo pull o hasta que la plataforma avise de un evento.
            con_pull = True
            while not _detener.is_set() and (restante := proximo_pull - time.monotonic()) > 0:
                if escucha.esperar(min(restante, _ESPERA_MAXIMA)):
                    logger.debug("Aviso de la plataforma: se envían los eventos pendientes")
                    con_pull = False
                    break
    finally:
        escucha.cerrar()
    logger.info("Worker de sincronización con Jira detenido")


def _al_recibir_senal(signum: int, _frame: object) -> None:
    logger.info("Señal recibida: termina después de la vuelta en curso", extra={"signal": signum})
    _detener.set()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m aisec_worker", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--una-vez", action="store_true", help="una sola vuelta completa (push + pull) y sale")
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(settings)
    if args.una_vez:
        try:
            vuelta(con_pull=True)
        except sync.JiraDeshabilitada as exc:
            sys.exit(str(exc))
        return

    intervalo = settings.jira_sync_intervalo_segundos
    if intervalo < _INTERVALO_MINIMO:
        sys.exit(f"AISEC_JIRA_SYNC_INTERVALO_SEGUNDOS debe ser de al menos {_INTERVALO_MINIMO}")
    signal.signal(signal.SIGTERM, _al_recibir_senal)
    signal.signal(signal.SIGINT, _al_recibir_senal)
    correr(intervalo)


if __name__ == "__main__":
    main()
