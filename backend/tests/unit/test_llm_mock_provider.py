from app.llm.providers.mock_provider import MockProvider
from app.llm.schemas import CatalogQuestionSummary


def _question(pregunta_id: str, tier: str, dominio: str = "CYB", numero: int = 1) -> CatalogQuestionSummary:
    return CatalogQuestionSummary(
        pregunta_id=pregunta_id,
        dominio_codigo=dominio,
        numero=numero,
        texto_es="¿Pregunta de prueba?",
        tier=tier,
    )


def test_mock_provider_recommends_only_critical_questions() -> None:
    catalog = [
        _question("p1", "critico"),
        _question("p2", "alto"),
        _question("p3", "estandar"),
        _question("p4", "critico"),
    ]

    result = MockProvider().analyze_document("cualquier texto", catalog)

    assert {q.pregunta_id for q in result.preguntas_recomendadas} == {"p1", "p4"}


def test_mock_provider_gives_bilingual_instructions() -> None:
    catalog = [_question("p1", "critico")]

    result = MockProvider().analyze_document("texto", catalog)

    recomendada = result.preguntas_recomendadas[0]
    assert recomendada.instrucciones_es
    assert recomendada.instrucciones_en


def test_mock_provider_handles_empty_catalog() -> None:
    result = MockProvider().analyze_document("texto", [])

    assert result.preguntas_recomendadas == []
    assert result.clasificacion
