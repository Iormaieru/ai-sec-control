"""Golden test for domain_aggregate/global_score: the 7 questions of the
'Transparency & Accessibility' sheet, transcribed verbatim (respuesta,
polaridad, tier) together with that domain's own already-computed row in
'⚙️ Cálculos' (C8..N8) from the real workbook — cross-checked by hand in
the commit that introduced this file.
"""

from decimal import Decimal

import pytest

from app.catalog.models import Polaridad
from app.threat_model.enums import RespuestaValor
from app.threat_model.scoring import (
    RespuestaInput,
    domain_aggregate,
    global_score,
    semaforo_for,
)

POS = Polaridad.POSITIVA
NEG = Polaridad.NEGATIVA
SI = RespuestaValor.SI
NO = RespuestaValor.NO
PEND = RespuestaValor.PENDIENTE

# Transparency & Accessibility, filas 4-10 del Excel real.
TAC_RESPUESTAS = [
    RespuestaInput(SI, POS, 3),  # #1 Crítico, correcta
    RespuestaInput(NO, POS, 2),  # #2 Alto, incorrecta (Brecha)
    RespuestaInput(PEND, POS, 3),  # #3 Crítico, pendiente
    RespuestaInput(PEND, NEG, 2),  # #4 Alto, pendiente
    RespuestaInput(SI, POS, 1),  # #5 Estándar, correcta
    RespuestaInput(PEND, POS, 3),  # #6 Crítico, pendiente
    RespuestaInput(PEND, POS, 2),  # #7 Alto, pendiente
]
TAC_PESO = Decimal("0.06")


def test_domain_aggregate_matches_excel_calculos_sheet() -> None:
    score = domain_aggregate(TAC_RESPUESTAS, TAC_PESO)

    assert score.total_preguntas == 7
    assert score.respondidas == 3
    assert score.na_total == 0
    assert score.pendientes == 4
    assert score.cumple == 2
    assert score.brechas_criticas == 0  # la única brecha es Alto (mult=2), no Crítico

    assert float(score.compliance_pct) == pytest.approx(0.75, abs=1e-9)
    assert float(score.residual_pct) == pytest.approx(0.59375, abs=1e-9)
    assert float(score.contrib_cumplimiento) == pytest.approx(0.045, abs=1e-9)
    assert float(score.contrib_residual) == pytest.approx(0.035625, abs=1e-9)
    assert float(score.gap_ponderado) == pytest.approx(0.015, abs=1e-9)
    assert score.semaforo == "moderado"  # 75% cae en 60-79%


def test_subset_with_zero_denominator_returns_zero_not_exception() -> None:
    todas_pendientes = [RespuestaInput(PEND, POS, 3), RespuestaInput(PEND, POS, 2)]

    score = domain_aggregate(todas_pendientes, Decimal("0.10"))

    assert score.compliance_pct == Decimal(0)
    # respondidas=0 (todo Pendiente) -> "sin_evaluar", no "critico": todavía
    # no se respondió nada, 0% acá no significa que esté mal evaluado.
    assert score.semaforo == "sin_evaluar"


def test_empty_subset_returns_zero_not_exception() -> None:
    score = domain_aggregate([], Decimal("0.10"))

    assert score.total_preguntas == 0
    assert score.compliance_pct == Decimal(0)
    assert score.residual_pct == Decimal(0)
    assert score.semaforo == "sin_evaluar"  # 0 preguntas seleccionadas, no "critico"


def test_all_na_domain_returns_zero_compliance_not_exception() -> None:
    todas_na = [
        RespuestaInput(RespuestaValor.NA_ARQ, POS, 3),
        RespuestaInput(RespuestaValor.NA_FASE, POS, 2),
    ]

    score = domain_aggregate(todas_na, Decimal("0.10"))

    assert score.na_total == 2
    assert score.compliance_pct == Decimal(0)
    assert score.residual_pct == Decimal(0)
    assert score.semaforo == "sin_evaluar"  # todo NA -> nada respondido de verdad


def test_partial_subset_only_counts_selected_questions() -> None:
    # Sólo 2 de las 37 preguntas de Cybersecurity seleccionadas para un caso:
    # el cálculo debe usar exclusivamente esas 2 como denominador.
    subset = [RespuestaInput(SI, POS, 3), RespuestaInput(NO, POS, 3)]

    score = domain_aggregate(subset, Decimal("0.22"))

    assert score.total_preguntas == 2
    assert float(score.compliance_pct) == pytest.approx(3 / 6, abs=1e-9)  # 3 + 0 (crítico incorrecta)


@pytest.mark.parametrize(
    "pct,expected",
    [
        (Decimal("1.0"), "solido"),
        (Decimal("0.80"), "solido"),
        (Decimal("0.79"), "moderado"),
        (Decimal("0.60"), "moderado"),
        (Decimal("0.59"), "vulnerable"),
        (Decimal("0.40"), "vulnerable"),
        (Decimal("0.39"), "critico"),
        (Decimal("0.0"), "critico"),
    ],
)
def test_semaforo_thresholds(pct: Decimal, expected: str) -> None:
    assert semaforo_for(pct, respondidas=1) == expected


@pytest.mark.parametrize("pct", [Decimal("0.0"), Decimal("1.0"), Decimal("0.5")])
def test_semaforo_sin_evaluar_gana_a_cualquier_umbral_si_no_hay_respondidas(pct: Decimal) -> None:
    assert semaforo_for(pct, respondidas=0) == "sin_evaluar"


def test_global_score_sums_domain_contributions() -> None:
    tac_score = domain_aggregate(TAC_RESPUESTAS, TAC_PESO)
    # Segundo dominio sintético con valores fáciles de verificar a mano:
    # 100% de cumplimiento, peso 0.94 (resto del total ponderado hasta 1.00).
    otro_score = domain_aggregate(
        [RespuestaInput(SI, POS, 3), RespuestaInput(SI, POS, 2)], Decimal("0.94")
    )

    result = global_score([tac_score, otro_score])

    # Global = Σ(Compliance%_i * Peso_i) = 0.75*0.06 + 1.0*0.94 = 0.985
    assert float(result.compliance_pct) == pytest.approx(0.045 + 0.94, abs=1e-9)
    assert result.brechas_criticas == 0
    assert result.semaforo == "solido"
    # completitud = respondidas totales / preguntas totales = (3+2)/(7+2)
    assert float(result.completitud_pct) == pytest.approx(5 / 9, abs=1e-9)
