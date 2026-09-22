"""Pure replication of the per-question formulas in the source Excel
(columns I/J/K/L/O of each domain sheet — see docs/SPEC.md "Motor de
scoring" and docs/excel-formula-mapping.md for the original cell formulas
this was transcribed from). No ORM/DB/HTTP here on purpose: every function
takes and returns primitives so it can be golden-tested in isolation
(tests/unit/test_scoring.py) against values read straight from the
workbook.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.catalog.models import Polaridad
from app.threat_model.enums import Estado, RespuestaValor

SEMAFORO_SOLIDO = "solido"
SEMAFORO_MODERADO = "moderado"
SEMAFORO_VULNERABLE = "vulnerable"
SEMAFORO_CRITICO = "critico"
SEMAFORO_SIN_EVALUAR = "sin_evaluar"

NA_RESPUESTAS = frozenset({RespuestaValor.NA_ARQ, RespuestaValor.NA_FASE})
PENDIENTE_RESPUESTAS = frozenset({None, RespuestaValor.PENDIENTE})


def is_correcta(respuesta: RespuestaValor, polaridad: Polaridad) -> bool:
    """correcta = (polaridad=+1 y respuesta=SI) o (polaridad=-1 y respuesta=NO)"""
    if polaridad == Polaridad.POSITIVA:
        return respuesta == RespuestaValor.SI
    return respuesta == RespuestaValor.NO


def compute_estado(respuesta: RespuestaValor | None, polaridad: Polaridad) -> Estado:
    if respuesta in PENDIENTE_RESPUESTAS:
        return Estado.PENDIENTE
    if respuesta == RespuestaValor.NA_ARQ:
        return Estado.NO_APLICA_ARQUITECTURA
    if respuesta == RespuestaValor.NA_FASE:
        return Estado.NO_APLICA_FASE
    return Estado.CUMPLE if is_correcta(respuesta, polaridad) else Estado.BRECHA


def compute_pts_obtenidos(
    respuesta: RespuestaValor | None, polaridad: Polaridad, multiplicador: int
) -> Decimal | None:
    """None represents the Excel's "-" (not applicable / excluded from aggregation)."""
    if respuesta in NA_RESPUESTAS or respuesta in PENDIENTE_RESPUESTAS:
        return None
    if is_correcta(respuesta, polaridad):
        return Decimal(multiplicador)
    if multiplicador == 3:  # Crítico: zero tolerance, sin crédito parcial
        return Decimal(0)
    return Decimal(multiplicador) * Decimal("0.25")  # Alto/Estándar: 25% crédito parcial


def compute_maximo_aplicable(respuesta: RespuestaValor | None, multiplicador: int) -> Decimal:
    if respuesta in NA_RESPUESTAS or respuesta in PENDIENTE_RESPUESTAS:
        return Decimal(0)
    return Decimal(multiplicador)


def compute_riesgo_residual(
    respuesta: RespuestaValor | None,
    polaridad: Polaridad,
    multiplicador: int,
    factor_mitigacion_pct: int | None = None,
) -> Decimal | None:
    """None represents the Excel's "-" (NA rows only; Pendiente still counts)."""
    if respuesta in NA_RESPUESTAS:
        return None
    if respuesta in PENDIENTE_RESPUESTAS:
        return Decimal(multiplicador) * Decimal("0.75")
    if is_correcta(respuesta, polaridad):
        return Decimal(0)
    mitigacion = Decimal(factor_mitigacion_pct or 0) / Decimal(100)
    return Decimal(multiplicador) * (Decimal(1) - mitigacion)


@dataclass(frozen=True)
class RespuestaInput:
    """Lo mínimo que domain_aggregate necesita de una CasoRespuesta+Pregunta."""

    respuesta: RespuestaValor | None
    polaridad: Polaridad
    multiplicador: int
    factor_mitigacion_pct: int | None = None


@dataclass(frozen=True)
class DomainScore:
    total_preguntas: int
    respondidas: int
    na_total: int
    pendientes: int
    cumple: int
    brechas_criticas: int
    compliance_pct: Decimal
    residual_pct: Decimal
    peso: Decimal
    contrib_cumplimiento: Decimal
    contrib_residual: Decimal
    gap_ponderado: Decimal
    semaforo: str


@dataclass(frozen=True)
class GlobalScore:
    compliance_pct: Decimal
    residual_pct: Decimal
    completitud_pct: Decimal
    brechas_criticas: int
    semaforo: str


def semaforo_for(compliance_pct: Decimal, respondidas: int = 1) -> str:
    """Umbrales de semáforo: ≥80% Sólido · 60-79% Moderado · 40-59% Vulnerable · <40% Crítico.

    respondidas=0 (nada seleccionado, o seleccionado pero todo Pendiente)
    devuelve "sin_evaluar" en vez de "critico": 0% de compliance por falta
    de evaluación no es lo mismo que 0% por haber respondido mal — visualmente
    no se debe confundir "no lo miramos todavía" con "lo miramos y está mal".
    El default respondidas=1 es sólo para no romper otras llamadas que no
    necesitan este matiz (ninguna en este módulo al día de hoy).
    """
    if respondidas == 0:
        return SEMAFORO_SIN_EVALUAR
    if compliance_pct >= Decimal("0.8"):
        return SEMAFORO_SOLIDO
    if compliance_pct >= Decimal("0.6"):
        return SEMAFORO_MODERADO
    if compliance_pct >= Decimal("0.4"):
        return SEMAFORO_VULNERABLE
    return SEMAFORO_CRITICO


def domain_aggregate(respuestas: list[RespuestaInput], peso: Decimal) -> DomainScore:
    """Replica la fila de un dominio en la hoja ⚙️ Cálculos.

    Compliance% excluye NA y Pendiente de numerador y denominador.
    Residual% excluye sólo NA (Pendiente sí cuenta, con riesgo mult*0.75).
    Ambos dan 0 si el subconjunto de preguntas no tiene denominador (todas
    NA, o ninguna pregunta seleccionada) — nunca división por cero.
    """
    na_total = 0
    pendientes = 0
    cumple = 0
    brechas_criticas = 0
    suma_pts = Decimal(0)
    suma_mult_respondidas = Decimal(0)
    suma_residual = Decimal(0)
    suma_mult_resp_o_pendiente = Decimal(0)

    for r in respuestas:
        estado = compute_estado(r.respuesta, r.polaridad)

        if estado in (Estado.NO_APLICA_ARQUITECTURA, Estado.NO_APLICA_FASE):
            na_total += 1
        elif estado == Estado.PENDIENTE:
            pendientes += 1
        else:
            pts = compute_pts_obtenidos(r.respuesta, r.polaridad, r.multiplicador)
            assert pts is not None  # respondida: nunca "-"
            suma_pts += pts
            suma_mult_respondidas += Decimal(r.multiplicador)
            if estado == Estado.CUMPLE:
                cumple += 1
            elif r.multiplicador == 3:
                brechas_criticas += 1

        residual = compute_riesgo_residual(r.respuesta, r.polaridad, r.multiplicador, r.factor_mitigacion_pct)
        if residual is not None:
            suma_residual += residual
            suma_mult_resp_o_pendiente += Decimal(r.multiplicador)

    total = len(respuestas)
    respondidas = total - na_total - pendientes
    compliance_pct = suma_pts / suma_mult_respondidas if suma_mult_respondidas else Decimal(0)
    residual_pct = suma_residual / suma_mult_resp_o_pendiente if suma_mult_resp_o_pendiente else Decimal(0)

    return DomainScore(
        total_preguntas=total,
        respondidas=respondidas,
        na_total=na_total,
        pendientes=pendientes,
        cumple=cumple,
        brechas_criticas=brechas_criticas,
        compliance_pct=compliance_pct,
        residual_pct=residual_pct,
        peso=peso,
        contrib_cumplimiento=compliance_pct * peso,
        contrib_residual=residual_pct * peso,
        gap_ponderado=(Decimal(1) - compliance_pct) * peso,
        semaforo=semaforo_for(compliance_pct, respondidas),
    )


def global_score(domain_scores: list[DomainScore]) -> GlobalScore:
    """Total Ponderado: ya es Σ(Compliance%_i * Peso_i), no se vuelve a dividir."""
    compliance_pct = sum((d.contrib_cumplimiento for d in domain_scores), Decimal(0))
    residual_pct = sum((d.contrib_residual for d in domain_scores), Decimal(0))
    total_preguntas = sum(d.total_preguntas for d in domain_scores)
    respondidas = sum(d.respondidas for d in domain_scores)
    completitud_pct = Decimal(respondidas) / Decimal(total_preguntas) if total_preguntas else Decimal(0)
    brechas_criticas = sum(d.brechas_criticas for d in domain_scores)

    return GlobalScore(
        compliance_pct=compliance_pct,
        residual_pct=residual_pct,
        completitud_pct=completitud_pct,
        brechas_criticas=brechas_criticas,
        semaforo=semaforo_for(compliance_pct, respondidas),
    )
