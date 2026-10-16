"""Vínculos sugeridos por IA entre una herramienta del Radar y los pasos de
los estándares (tasks/herramientas-radar.md, sección 6).

El LLM sólo sugiere: los vínculos quedan en estado "sugerido" y un analista
los confirma (o quita) al aprobar la herramienta.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm.base import LLMProvider
from app.llm.schemas import StepSummary, ToolSummary
from app.pentesting.models import (
    EstadoVinculo,
    HerramientaPaso,
    HerramientaPentest,
    OrigenVinculo,
    PentestEstandar,
    PentestEstandarPaso,
)


def _pasos(db: Session) -> dict[str, tuple[PentestEstandarPaso, StepSummary]]:
    filas = db.execute(
        select(PentestEstandarPaso, PentestEstandar.nombre)
        .join(PentestEstandar, PentestEstandarPaso.estandar_id == PentestEstandar.id)
        .where(PentestEstandarPaso.codigo.is_not(None))
        .order_by(PentestEstandar.codigo, PentestEstandarPaso.orden)
    ).all()
    return {
        paso.codigo.upper(): (
            paso,
            StepSummary(codigo=paso.codigo, estandar=estandar, titulo=paso.titulo, descripcion=paso.descripcion),
        )
        for paso, estandar in filas
    }


def sugerir_vinculos(db: Session, herramienta: HerramientaPentest, provider: LLMProvider, readme: str | None) -> int:
    """Agrega a la herramienta los pasos que sugiere el LLM. Devuelve cuántos
    vínculos nuevos quedaron. No hace commit."""
    pasos = _pasos(db)
    if not pasos:
        return 0
    sugerencias = provider.suggest_tool_steps(
        ToolSummary(nombre=herramienta.nombre, descripcion=herramienta.descripcion, temas=herramienta.temas, readme=readme),
        [resumen for _, resumen in pasos.values()],
    )
    # paso_id puede no estar cargado todavía (vínculo agregado sin flush): se toma del objeto.
    ya_vinculados = {v.paso_id or v.paso.id for v in herramienta.pasos}
    nuevos = 0
    for sugerencia in sugerencias:
        encontrado = pasos.get(sugerencia.codigo.strip().upper())
        if encontrado is None or encontrado[0].id in ya_vinculados:
            continue  # código inventado por el modelo, o ya vinculado
        paso = encontrado[0]
        herramienta.pasos.append(
            HerramientaPaso(
                paso=paso,
                origen=OrigenVinculo.SUGERIDO_IA,
                estado=EstadoVinculo.SUGERIDO,
                justificacion=sugerencia.justificacion[:1000],
            )
        )
        ya_vinculados.add(paso.id)
        nuevos += 1
    return nuevos
