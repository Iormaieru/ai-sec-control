"""H5: vínculos sugeridos por IA entre herramientas y pasos de estándares."""

from sqlalchemy.orm import Session

from aisec_worker.herramientas.vinculos import sugerir_vinculos
from app.llm.providers.mock_provider import MockProvider
from app.llm.schemas import StepSummary, SuggestedStep, ToolSummary
from app.pentesting.models import EstadoVinculo, HerramientaPentest, OrigenVinculo, TipoHerramienta


class _Fijo(MockProvider):
    """Devuelve sugerencias fijas, incluidas algunas inválidas."""

    def __init__(self, codigos: list[str]) -> None:
        self.codigos = codigos
        self.pasos_recibidos: list[StepSummary] = []

    def suggest_tool_steps(self, tool: ToolSummary, steps: list[StepSummary]) -> list[SuggestedStep]:
        self.pasos_recibidos = steps
        return [SuggestedStep(codigo=c, justificacion=f"porque {c}") for c in self.codigos]


def _candidata(db: Session, **kwargs) -> HerramientaPentest:
    herramienta = HerramientaPentest(nombre="nemo-guardrails", tipo=TipoHerramienta.IA, **kwargs)
    db.add(herramienta)
    db.flush()
    return herramienta


def test_sugerencias_quedan_como_sugeridas(db: Session) -> None:
    herramienta = _candidata(db, descripcion="Guardrails for LLM apps", temas=["prompt-injection", "jailbreak"])

    nuevos = sugerir_vinculos(db, herramienta, MockProvider(), readme=None)
    db.commit()

    codigos = sorted(v.paso.codigo for v in herramienta.pasos)
    assert nuevos == len(codigos) and codigos == ["LLM01", "RT04", "RT05"]
    assert {(v.origen, v.estado) for v in herramienta.pasos} == {(OrigenVinculo.SUGERIDO_IA, EstadoVinculo.SUGERIDO)}


def test_codigos_inventados_o_repetidos_se_descartan(db: Session) -> None:
    herramienta = _candidata(db)
    provider = _Fijo(["llm01", "XX99", "LLM01", " AML.TA0005 "])

    assert sugerir_vinculos(db, herramienta, provider, readme="# README") == 2
    assert sorted(v.paso.codigo for v in herramienta.pasos) == ["AML.TA0005", "LLM01"]
    # El LLM recibe todos los pasos con código de los estándares sembrados.
    assert len(provider.pasos_recibidos) == 63
    # Una segunda pasada no duplica.
    assert sugerir_vinculos(db, herramienta, provider, readme=None) == 0


def test_herramienta_que_no_es_de_pentesting_queda_sin_vinculos(db: Session) -> None:
    herramienta = _candidata(db, descripcion="Awesome list of links", temas=["awesome-list"])

    assert sugerir_vinculos(db, herramienta, MockProvider(), readme=None) == 0
