"""Tenable -> inventario de equipos y reglas de fuente Tenable.

1. sincronizar: exporta de Tenable el inventario de software (plugins 20811 y
   22869) y los escaneos de puertos, y reemplaza la tabla equipos_tenable con
   lo relevante para seguridad de IA: runtimes de modelos, Python/Anaconda y
   puertos de servicios de IA abiertos.
2. evaluar_reglas: con ese inventario genera las alertas de las reglas de
   fuente Tenable:
   - servicio de IA expuesto (un puerto de Ollama, LM Studio, Jupyter... abierto);
   - equipo con actividad de IA fuera de cobertura (Netskope ve actividad en un
     equipo que Tenable no inventaría).
"""

import datetime as dt
import logging
import re
from dataclasses import dataclass, field

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.alertas.models import (
    Alerta,
    EquipoTenable,
    EstadoAlerta,
    FuenteRegla,
    ModoRegla,
    ReglaAlerta,
    SincronizacionTenable,
    TipoReglaTenable,
)
from app.alertas.tenable import PLUGINS_PUERTOS, PLUGINS_SOFTWARE, TenableClient

logger = logging.getLogger(__name__)

# Software relevante en el inventario (nombre a mostrar -> patrón en la salida del plugin).
SOFTWARE_IA = {
    "Ollama": r"\bollama\b",
    "LM Studio": r"lm ?studio",
    "GPT4All": r"gpt4all",
    "AnythingLLM": r"anythingllm",
    "llama.cpp": r"llama\.cpp|llama-server",
    "Jupyter": r"\bjupyter",
    "Anaconda": r"\banaconda",
    "Miniconda": r"\bminiconda",
    "Python": r"\bpython 3\.\d+",
}
_PATRONES = {nombre: re.compile(patron, re.IGNORECASE) for nombre, patron in SOFTWARE_IA.items()}

PUERTOS_IA = {11434: "Ollama", 1234: "LM Studio", 8888: "Jupyter", 7860: "Gradio"}


def normalizar_host(nombre: str | None) -> str | None:
    """"BMN1234.macro.local" -> "bmn1234": la forma común entre Netskope y Tenable."""
    if not nombre:
        return None
    return nombre.strip().lower().split(".")[0] or None


@dataclass
class ResultadoTenable:
    equipos: int = 0
    con_inventario: int = 0
    con_software_ia: int = 0
    con_puertos_ia: int = 0
    nuevas: int = 0
    reincidentes: int = 0
    errores: list[str] = field(default_factory=list)


def _equipo(equipos: dict[str, dict], registro: dict, ahora: dt.datetime) -> dict:
    asset = registro.get("asset") or {}
    uuid = asset.get("uuid")
    if uuid not in equipos:
        sistema = asset.get("operating_system") or []
        equipos[uuid] = {
            "asset_uuid": uuid,
            "hostname": normalizar_host(asset.get("hostname") or asset.get("fqdn")),
            "netbios": (asset.get("netbios_name") or "").strip().lower() or None,
            "sistema_operativo": (sistema[0] if sistema else None),
            # agent_uuid viene completo en casi todos los equipos: lo que indica
            # agente es que algún registro lo haya informado un Nessus Agent.
            "tiene_agente": False,
            "con_inventario": False,
            "software_ia": set(),
            "puertos_ia": {},
            "visto_at": None,
            "actualizado_at": ahora,
        }
    equipo = equipos[uuid]
    if registro.get("source") == "AGENT":
        equipo["tiene_agente"] = True
    visto = registro.get("last_found")
    if visto and (equipo["visto_at"] is None or visto > equipo["visto_at"]):
        equipo["visto_at"] = visto
    return equipo


def sincronizar(db: Session, client: TenableClient, ahora: dt.datetime | None = None) -> ResultadoTenable:
    ahora = ahora or dt.datetime.now(dt.UTC)
    registro_sync = SincronizacionTenable(iniciada_at=ahora)
    db.add(registro_sync)
    db.commit()

    equipos: dict[str, dict] = {}
    for registro in client.exportar(PLUGINS_SOFTWARE):
        equipo = _equipo(equipos, registro, ahora)
        equipo["con_inventario"] = True
        salida = registro.get("output") or ""
        equipo["software_ia"].update(nombre for nombre, patron in _PATRONES.items() if patron.search(salida))
    for registro in client.exportar(PLUGINS_PUERTOS):
        equipo = _equipo(equipos, registro, ahora)
        puerto = (registro.get("port") or {}).get("port")
        if puerto in PUERTOS_IA:
            equipo["puertos_ia"][puerto] = PUERTOS_IA[puerto]

    # Reemplazo completo: el inventario es una foto del estado actual.
    db.execute(delete(EquipoTenable))
    for equipo in equipos.values():
        db.add(
            EquipoTenable(
                **{k: v for k, v in equipo.items() if k not in ("software_ia", "puertos_ia", "visto_at")},
                software_ia=sorted(equipo["software_ia"]),
                puertos_ia=[{"puerto": p, "servicio": s} for p, s in sorted(equipo["puertos_ia"].items())],
                visto_at=dt.datetime.fromisoformat(equipo["visto_at"].replace("Z", "+00:00")) if equipo["visto_at"] else None,
            )
        )
    registro_sync.finalizada_at = dt.datetime.now(dt.UTC)
    registro_sync.ok = True
    registro_sync.equipos = len(equipos)
    db.commit()

    return ResultadoTenable(
        equipos=len(equipos),
        con_inventario=sum(e["con_inventario"] for e in equipos.values()),
        con_software_ia=sum(bool(e["software_ia"]) for e in equipos.values()),
        con_puertos_ia=sum(bool(e["puertos_ia"]) for e in equipos.values()),
    )


def debe_sincronizar(db: Session, horas: int, ahora: dt.datetime | None = None) -> bool:
    ultima = db.scalar(
        select(SincronizacionTenable.finalizada_at)
        .where(SincronizacionTenable.ok.is_(True))
        .order_by(SincronizacionTenable.finalizada_at.desc())
    )
    ahora = ahora or dt.datetime.now(dt.UTC)
    return ultima is None or ahora - ultima >= dt.timedelta(hours=horas)


# --- reglas de fuente Tenable ---


def _registrar(
    db: Session, regla: ReglaAlerta, app: str, equipo: str, cantidad: int, actividades: dict[str, int],
    ahora: dt.datetime, resultado: ResultadoTenable,
) -> None:
    """Crea o actualiza la alerta (regla, app, equipo). Mismas reglas de
    reincidencia que las de Netskope: una resuelta vuelve a "nueva"."""
    alerta = db.scalar(select(Alerta).where(Alerta.regla_id == regla.id, Alerta.app == app, Alerta.usuario == equipo))
    if alerta is None:
        db.add(
            Alerta(
                regla_id=regla.id, app=app, usuario=equipo, estado=EstadoAlerta.NUEVA, severidad=regla.severidad,
                primera_vez=ahora, ultima_vez=ahora, cantidad_eventos=cantidad, actividades=actividades,
                equipos=[equipo], por_notificar=True,
            )
        )
        resultado.nuevas += 1
        return
    if alerta.estado == EstadoAlerta.RESUELTA:
        alerta.estado = EstadoAlerta.NUEVA
        alerta.por_notificar = True
        alerta.cerrada_at = None
        resultado.reincidentes += 1
    alerta.ultima_vez = ahora
    alerta.cantidad_eventos = cantidad
    alerta.actividades = actividades


def evaluar_reglas(db: Session, ahora: dt.datetime | None = None) -> ResultadoTenable:
    ahora = ahora or dt.datetime.now(dt.UTC)
    resultado = ResultadoTenable()
    reglas = db.scalars(
        select(ReglaAlerta).where(ReglaAlerta.fuente == FuenteRegla.TENABLE, ReglaAlerta.activa.is_(True))
    ).all()
    if not reglas or db.scalar(select(EquipoTenable.id).limit(1)) is None:
        return resultado  # sin inventario todavía no se puede evaluar nada
    equipos = db.scalars(select(EquipoTenable)).all()

    for regla in reglas:
        if regla.consulta == TipoReglaTenable.SERVICIO_IA_EXPUESTO.value:
            for equipo in equipos:
                nombre = equipo.hostname or equipo.netbios or equipo.asset_uuid
                for puerto in equipo.puertos_ia:
                    app = f"{puerto['servicio']} (puerto {puerto['puerto']})"
                    _registrar(db, regla, app, nombre, 1, {"Puerto abierto": 1}, ahora, resultado)

        elif regla.consulta == TipoReglaTenable.FUERA_DE_COBERTURA.value:
            cubiertos = {n for e in equipos if e.con_inventario for n in (e.hostname, e.netbios) if n}
            abiertas = db.scalars(
                select(Alerta)
                .join(ReglaAlerta, Alerta.regla_id == ReglaAlerta.id)
                .where(
                    ReglaAlerta.fuente == FuenteRegla.NETSKOPE,
                    ReglaAlerta.modo == ModoRegla.ALERTA,
                    Alerta.estado.in_([EstadoAlerta.NUEVA, EstadoAlerta.EN_REVISION]),
                )
            ).all()
            por_equipo: dict[str, dict[str, int]] = {}
            for alerta in abiertas:
                for equipo in alerta.equipos:
                    if equipo not in cubiertos:
                        reglas_equipo = por_equipo.setdefault(equipo, {})
                        reglas_equipo[alerta.regla.nombre] = reglas_equipo.get(alerta.regla.nombre, 0) + 1
            for equipo, por_regla in por_equipo.items():
                _registrar(
                    db, regla, "Sin inventario de Tenable", equipo, sum(por_regla.values()), por_regla, ahora, resultado
                )
    db.commit()
    return resultado
