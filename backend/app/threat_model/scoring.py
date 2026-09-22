"""Pure replication of the per-question formulas in the source Excel
(columns I/J/K/L/O of each domain sheet — see docs/SPEC.md "Motor de
scoring" and docs/excel-formula-mapping.md for the original cell formulas
this was transcribed from). No ORM/DB/HTTP here on purpose: every function
takes and returns primitives so it can be golden-tested in isolation
(tests/unit/test_scoring.py) against values read straight from the
workbook.
"""

from decimal import Decimal

from app.catalog.models import Polaridad
from app.threat_model.enums import Estado, RespuestaValor

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
