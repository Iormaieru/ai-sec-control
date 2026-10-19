"""Loop del worker: python -m aisec_worker

- Eventos de la plataforma: escucha el canal de jira_outbox (LISTEN). Cada
  NOTIFY lo despierta y envía los eventos pendientes a Jira en segundos.
- Cambios en Jira: cada AISEC_JIRA_SYNC_INTERVALO_SEGUNDOS trae los tickets
  del tablero que cambiaron (Jira no avisa). En esa vuelta también envía
  cualquier evento que haya quedado pendiente (aviso perdido, reintentos).
- Herramientas de pentesting (en un hilo aparte, para no frenar a Jira): cada
  AISEC_HERRAMIENTAS_REVISION_DIAS revisa el Catálogo, las distribuciones y
  descubre candidatas para el Radar; también cuando se pide "revisar ahora".
  Con Jira deshabilitado, el worker sigue corriendo sólo con esta tarea.
- Alertas de Netskope (otro hilo, si AISEC_NETSKOPE_ENABLED): cada
  AISEC_NETSKOPE_INTERVALO_SEGUNDOS ejecuta las reglas activas, agrupa los
  eventos en alertas y manda un email resumen con las nuevas.
- Inventario de Tenable (otro hilo, si AISEC_TENABLE_ENABLED): cada
  AISEC_TENABLE_INTERVALO_HORAS actualiza los equipos (software y puertos de
  IA) y evalúa las reglas de fuente Tenable. La brecha de cobertura también se
  reevalúa en cada vuelta de alertas.

Un error en una vuelta (Jira caído, timeout, base reiniciando) se loguea y
se reintenta en la siguiente. El proceso termina con SIGTERM (redeploy) o
Ctrl+C después de completar la vuelta en curso.

Opciones (una vuelta y sale; para pruebas o un planificador como Control-M):
--una-vez (Jira), --herramientas (revisión de herramientas), --alertas (Netskope),
--tenable (inventario de Tenable).
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

from app.alertas.netskope import NetskopeError
from app.alertas.tenable import TenableError
from app.alertas.tenable import crear_cliente as crear_cliente_tenable
from app.alertas.netskope import crear_cliente as crear_cliente_netskope
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal, engine
from app.integraciones.jira import sync
from app.integraciones.jira.outbox import CANAL
from app.llm.base import LLMProvider
from app.llm.factory import get_llm_provider
from app.pentesting.models import RevisionHerramientas

from aisec_worker.alertas.aviso import notificar
from aisec_worker.alertas.procesamiento import procesar
from aisec_worker.alertas.tenable_inventario import debe_sincronizar, evaluar_reglas, sincronizar
from aisec_worker.herramientas.fuentes import Distribuciones, GitHub, Registros
from aisec_worker.herramientas.revision import Fuentes, debe_revisar, revisar
from aisec_worker.pull import pull
from aisec_worker.push import push

logger = logging.getLogger("aisec_worker")

# pg advisory locks: una sola vuelta de cada tarea a la vez (durante un redeploy conviven dos workers).
_LOCK = 7_241_001
_LOCK_HERRAMIENTAS = 7_241_002
_LOCK_ALERTAS = 7_241_003
_LOCK_TENABLE = 7_241_004
_CHEQUEO_TENABLE = 3600  # cada cuánto se fija si toca actualizar el inventario
_CHEQUEO_HERRAMIENTAS = 300  # cada cuánto se fija si toca revisar herramientas (o si lo pidieron)
_INTERVALO_MINIMO = 30
_ESPERA_MAXIMA = 5  # cada cuánto se revisa si llegó la señal de apagado

_detener = threading.Event()


@contextmanager
def _lock(clave: int = _LOCK) -> Iterator[bool]:
    with engine.connect() as conn:
        obtenido = bool(conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": clave}).scalar())
        try:
            yield obtenido
        finally:
            if obtenido:
                conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": clave})
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


# --- herramientas de pentesting ---


def _proveedor_llm() -> LLMProvider | None:
    try:
        return get_llm_provider()
    except Exception:
        # Sin LLM las candidatas entran igual al Radar, sin vínculos sugeridos.
        logger.warning("Sin proveedor LLM: las candidatas no tendrán vínculos sugeridos", exc_info=True)
        return None


def revisar_herramientas(*, forzar: bool = False) -> RevisionHerramientas | None:
    """Corre la revisión si corresponde (o si `forzar`). None si no tocaba
    o si otra instancia la está corriendo."""
    settings = get_settings()
    with _lock(_LOCK_HERRAMIENTAS) as obtenido:
        if not obtenido:
            return None
        db = SessionLocal()
        fuentes = Fuentes(GitHub(settings.github_token), Registros(), Distribuciones())
        try:
            pendiente = debe_revisar(db, settings.herramientas_revision_dias)
            if not (pendiente or forzar):
                return None
            logger.info("Revisión de herramientas iniciada")
            revision = revisar(
                db,
                fuentes,
                _proveedor_llm(),
                revision=pendiente if isinstance(pendiente, RevisionHerramientas) else None,
                detener=_detener.is_set,
            )
            logger.info(
                "Revisión de herramientas",
                extra={"estado": revision.estado.value, **revision.resumen, "errores": len(revision.errores)},
            )
            for error in revision.errores:
                logger.warning("Error en la revisión de herramientas", extra={"detalle": error})
            return revision
        finally:
            for cliente in (fuentes.github, fuentes.registros, fuentes.distribuciones):
                cliente.close()
            db.close()


def _tarea_herramientas() -> None:
    while not _detener.is_set():
        try:
            revisar_herramientas()
        except Exception:
            logger.exception("Falló la revisión de herramientas; se reintenta más tarde")
        _detener.wait(_CHEQUEO_HERRAMIENTAS)


# --- alertas de Netskope ---


def vuelta_alertas() -> None:
    """Ejecuta las reglas activas contra Netskope y avisa las alertas nuevas."""
    settings = get_settings()
    with _lock(_LOCK_ALERTAS) as obtenido:
        if not obtenido:
            logger.info("Otra instancia está procesando alertas; se omite esta vuelta")
            return
        db = SessionLocal()
        try:
            with crear_cliente_netskope() as client:
                resultado = procesar(db, client, settings)
            # Barato (sólo base): una alerta nueva en un equipo sin inventario de
            # Tenable genera la de brecha de cobertura en esta misma vuelta.
            tenable = evaluar_reglas(db)
            avisadas = notificar(db, settings)
        finally:
            db.close()
    # Sólo cantidades: los eventos traen usuarios (datos personales).
    logger.info(
        "Alertas de Netskope",
        extra={
            "eventos": resultado.eventos,
            "nuevas": resultado.nuevas,
            "reincidentes": resultado.reincidentes,
            "actualizadas": resultado.actualizadas,
            "eventos_en_metricas": resultado.eventos_metricas,
            "nuevas_tenable": tenable.nuevas,
            "avisadas_por_email": avisadas,
            "errores": len(resultado.errores),
        },
    )
    for error in resultado.errores:
        logger.warning("Error en las alertas de Netskope", extra={"detalle": error})


def _tarea_alertas(intervalo: int) -> None:
    while not _detener.is_set():
        try:
            vuelta_alertas()
        except Exception:
            logger.exception("Falló la vuelta de alertas; se reintenta en la próxima")
        _detener.wait(intervalo)


# --- inventario de Tenable ---


def vuelta_tenable(*, forzar: bool = False) -> None:
    settings = get_settings()
    with _lock(_LOCK_TENABLE) as obtenido:
        if not obtenido:
            return
        db = SessionLocal()
        try:
            if not (forzar or debe_sincronizar(db, settings.tenable_intervalo_horas)):
                return
            logger.info("Inventario de Tenable: actualización iniciada")
            with crear_cliente_tenable() as client:
                inventario = sincronizar(db, client)
            reglas = evaluar_reglas(db)
            avisadas = notificar(db, settings)
        finally:
            db.close()
    logger.info(
        "Inventario de Tenable",
        extra={
            "equipos": inventario.equipos,
            "con_inventario": inventario.con_inventario,
            "con_software_ia": inventario.con_software_ia,
            "con_puertos_ia": inventario.con_puertos_ia,
            "alertas_nuevas": reglas.nuevas,
            "avisadas_por_email": avisadas,
        },
    )


def _tarea_tenable() -> None:
    while not _detener.is_set():
        try:
            vuelta_tenable()
        except Exception:
            logger.exception("Falló la actualización del inventario de Tenable; se reintenta más tarde")
        _detener.wait(_CHEQUEO_TENABLE)


# --- loop principal ---


def correr(intervalo: int) -> None:
    settings = get_settings()
    hilos = [threading.Thread(target=_tarea_herramientas, name="herramientas")]
    if settings.netskope_enabled:
        hilos.append(
            threading.Thread(target=_tarea_alertas, args=(settings.netskope_intervalo_segundos,), name="alertas")
        )
    else:
        logger.info("Integración con Netskope deshabilitada: no se procesan alertas")
    if settings.tenable_enabled:
        hilos.append(threading.Thread(target=_tarea_tenable, name="tenable"))
    for hilo in hilos:
        hilo.start()
    try:
        if get_settings().jira_enabled:
            _correr_jira(intervalo)
        else:
            logger.warning("Integración con Jira deshabilitada: el worker sólo revisa herramientas")
            _detener.wait()
    finally:
        _detener.set()
        for hilo in hilos:
            hilo.join()


def _correr_jira(intervalo: int) -> None:
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
    parser.add_argument("--una-vez", action="store_true", help="una sola vuelta de Jira (push + pull) y sale")
    parser.add_argument("--herramientas", action="store_true", help="una revisión de herramientas completa y sale")
    parser.add_argument("--alertas", action="store_true", help="una vuelta de alertas de Netskope y sale")
    parser.add_argument("--tenable", action="store_true", help="actualiza el inventario de Tenable ya y sale")
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(settings)
    if args.tenable:
        try:
            vuelta_tenable(forzar=True)
        except TenableError as exc:
            sys.exit(str(exc))
        return
    if args.alertas:
        try:
            vuelta_alertas()
        except NetskopeError as exc:
            sys.exit(str(exc))
        return
    if args.herramientas:
        revisar_herramientas(forzar=True)
        return
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
