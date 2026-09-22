"""Golden-value tests for app/threat_model/scoring.py.

Cases marked "real" are transcribed verbatim from computed cells in
AISEC_PLOT4AI_Final -05-2026-Proveedor.xlsx (data_only=True read). The
reference workbook's sample answers happen to contain no incorrect
("⚠️ Brecha") or mitigation-factor rows, so those branches are covered by
cases marked "derived", hand-evaluated against the verified Excel formula
text for columns J and O (see docs/excel-formula-mapping.md), most notably:

J (Pts. Obtenidos) = IF(NA-or-Pendiente, "-",
                       IF(correcta, mult,
                          IF(mult=3, 0, mult*0.25)))
O (Riesgo Residual) = IF(NA, "-",
                        IF(Pendiente, mult*0.75,
                           IF(correcta, 0, mult*(1-mitigacion%/100))))
"""

from decimal import Decimal

import pytest

from app.catalog.models import Polaridad
from app.threat_model.enums import Estado, RespuestaValor
from app.threat_model.scoring import (
    compute_estado,
    compute_maximo_aplicable,
    compute_pts_obtenidos,
    compute_riesgo_residual,
    is_correcta,
)

POS = Polaridad.POSITIVA
NEG = Polaridad.NEGATIVA


# respuesta, polaridad, multiplicador, expected_estado, expected_pts, expected_maxapl, expected_residual
CASES = [
    # --- real: correct answers across tiers (Accountability/Ethics/Transparency sheets) ---
    pytest.param(RespuestaValor.SI, POS, 2, Estado.CUMPLE, Decimal(2), Decimal(2), Decimal(0), id="real-alto-si-correcta"),
    pytest.param(RespuestaValor.SI, POS, 3, Estado.CUMPLE, Decimal(3), Decimal(3), Decimal(0), id="real-critico-si-correcta"),
    pytest.param(RespuestaValor.NO, NEG, 2, Estado.CUMPLE, Decimal(2), Decimal(2), Decimal(0), id="real-alto-no-correcta"),
    pytest.param(RespuestaValor.NO, NEG, 3, Estado.CUMPLE, Decimal(3), Decimal(3), Decimal(0), id="real-critico-no-correcta"),
    pytest.param(RespuestaValor.NO, NEG, 1, Estado.CUMPLE, Decimal(1), Decimal(1), Decimal(0), id="real-estandar-no-correcta"),
    pytest.param(RespuestaValor.SI, POS, 1, Estado.CUMPLE, Decimal(1), Decimal(1), Decimal(0), id="real-estandar-si-correcta"),
    # --- real: NA / Pendiente (Cybersecurity/Data Governance sheets) ---
    pytest.param(RespuestaValor.PENDIENTE, NEG, 3, Estado.PENDIENTE, None, Decimal(0), Decimal("2.25"), id="real-critico-pendiente"),
    pytest.param(RespuestaValor.PENDIENTE, NEG, 2, Estado.PENDIENTE, None, Decimal(0), Decimal("1.5"), id="real-alto-pendiente"),
    pytest.param(RespuestaValor.NA_ARQ, POS, 1, Estado.NO_APLICA_ARQUITECTURA, None, Decimal(0), None, id="real-estandar-na-arq"),
    pytest.param(RespuestaValor.NA_ARQ, POS, 2, Estado.NO_APLICA_ARQUITECTURA, None, Decimal(0), None, id="real-alto-na-arq"),
    pytest.param(RespuestaValor.NA_ARQ, NEG, 3, Estado.NO_APLICA_ARQUITECTURA, None, Decimal(0), None, id="real-critico-na-arq"),
    pytest.param(RespuestaValor.NA_FASE, POS, 1, Estado.NO_APLICA_FASE, None, Decimal(0), None, id="real-estandar-na-fase"),
    # --- derived: incorrect answers, the critical zero-tolerance rule vs. 25% partial credit ---
    pytest.param(RespuestaValor.NO, POS, 3, Estado.BRECHA, Decimal(0), Decimal(3), Decimal(3), id="derived-critico-incorrecta-zero-tolerance"),
    pytest.param(RespuestaValor.SI, NEG, 3, Estado.BRECHA, Decimal(0), Decimal(3), Decimal(3), id="derived-critico-incorrecta-polaridad-negativa"),
    pytest.param(RespuestaValor.NO, POS, 2, Estado.BRECHA, Decimal("0.5"), Decimal(2), Decimal(2), id="derived-alto-incorrecta-25pct-credito"),
    pytest.param(RespuestaValor.NO, POS, 1, Estado.BRECHA, Decimal("0.25"), Decimal(1), Decimal(1), id="derived-estandar-incorrecta-25pct-credito"),
]


@pytest.mark.parametrize(
    "respuesta,polaridad,multiplicador,expected_estado,expected_pts,expected_maxapl,expected_residual",
    CASES,
)
def test_per_question_formulas(
    respuesta, polaridad, multiplicador, expected_estado, expected_pts, expected_maxapl, expected_residual
) -> None:
    assert compute_estado(respuesta, polaridad) == expected_estado
    assert compute_pts_obtenidos(respuesta, polaridad, multiplicador) == expected_pts
    assert compute_maximo_aplicable(respuesta, multiplicador) == expected_maxapl
    assert compute_riesgo_residual(respuesta, polaridad, multiplicador) == expected_residual


def test_blank_respuesta_behaves_like_pendiente() -> None:
    assert compute_estado(None, POS) == Estado.PENDIENTE
    assert compute_pts_obtenidos(None, POS, 3) is None
    assert compute_riesgo_residual(None, POS, 3) == Decimal("2.25")


def test_mitigation_factor_reduces_residual_risk_on_incorrect_answer() -> None:
    # derived: O4 = mult*(1 - mitigacion/100); mult=3 (Crítico), mitigacion=50% -> 1.5
    assert compute_riesgo_residual(RespuestaValor.NO, POS, 3, factor_mitigacion_pct=50) == Decimal("1.5")
    # mitigacion=100% -> residual completamente absorbido
    assert compute_riesgo_residual(RespuestaValor.NO, POS, 3, factor_mitigacion_pct=100) == Decimal(0)
    # sin mitigación (None ~ 0%) -> residual = multiplicador completo
    assert compute_riesgo_residual(RespuestaValor.NO, POS, 3, factor_mitigacion_pct=None) == Decimal(3)


def test_mitigation_factor_does_not_affect_pts_obtenidos() -> None:
    # el factor de mitigación sólo entra en la fórmula de O (Riesgo Residual),
    # nunca en J (Pts. Obtenidos) — confirmado en el texto de la fórmula fuente.
    without_mit = compute_pts_obtenidos(RespuestaValor.NO, POS, 2)
    assert without_mit == Decimal("0.5")


def test_correct_answer_has_zero_residual_risk_regardless_of_mitigation() -> None:
    assert compute_riesgo_residual(RespuestaValor.SI, POS, 3, factor_mitigacion_pct=0) == Decimal(0)
    assert compute_riesgo_residual(RespuestaValor.SI, POS, 3, factor_mitigacion_pct=80) == Decimal(0)


def test_is_correcta_matches_polarity_semantics() -> None:
    assert is_correcta(RespuestaValor.SI, POS) is True
    assert is_correcta(RespuestaValor.NO, POS) is False
    assert is_correcta(RespuestaValor.NO, NEG) is True
    assert is_correcta(RespuestaValor.SI, NEG) is False
