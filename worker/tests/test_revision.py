"""H6: revisión periódica de herramientas con fuentes falsas (sin red)."""

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from aisec_worker.herramientas.fuentes import FuenteError, Paquete, RepoGitHub, VersionPublicada
from aisec_worker.herramientas.revision import Fuentes, debe_revisar, revisar
from app.llm.providers.mock_provider import MockProvider
from app.pentesting.models import (
    Distribucion,
    EstadoHerramienta,
    EstadoRevision,
    EstadoVinculo,
    HerramientaPentest,
    RevisionHerramientas,
    TipoHerramienta,
)

AHORA = dt.datetime(2026, 10, 16, 12, tzinfo=dt.UTC)
RECIENTE = AHORA - dt.timedelta(days=3)


def _repo(nombre: str, **cambios) -> RepoGitHub:
    base = dict(
        nombre=nombre,
        descripcion=f"Repo {nombre}",
        url=f"https://github.com/{nombre}",
        homepage=None,
        estrellas=1500,
        archivado=False,
        ultimo_push=RECIENTE,
        licencia="MIT",
        temas=["llm-security"],
    )
    return RepoGitHub(**{**base, **cambios})


class FakeGitHub:
    def __init__(self) -> None:
        self.repos = {
            "NVIDIA/garak": _repo("NVIDIA/garak", estrellas=9584, licencia="Apache-2.0"),
            "protectai/llm-guard": _repo("protectai/llm-guard", archivado=True),
            # GitHub redirige el repo renombrado: devuelve el nombre nuevo.
            "Giskard-AI/giskard": _repo("Giskard-AI/giskard-oss"),
            "NVIDIA/NeMo-Guardrails": _repo("NVIDIA/NeMo-Guardrails", temas=["prompt-injection", "guardrails"]),
        }
        self.por_tema = {
            "llm-security": [
                _repo("acme/llm-fuzzer", estrellas=800, temas=["prompt-injection", "jailbreak"]),
                _repo("tiny/apenas-conocida", estrellas=40),
                _repo("acme/descartada"),
            ]
        }
        self.caidos = {"QData/TextAttack"}

    def repo(self, nombre: str) -> RepoGitHub:
        if nombre in self.caidos or nombre not in self.repos:
            raise FuenteError(f"GET /repos/{nombre} -> 502")
        return self.repos[nombre]

    def buscar_por_tema(self, tema: str, *, min_estrellas: int, activos_desde: dt.date, limite: int = 50) -> list[RepoGitHub]:
        return self.por_tema.get(tema, [])

    def readme(self, nombre: str, max_caracteres: int = 6000) -> str:
        return f"# {nombre}"

    def close(self) -> None:
        pass


class FakeRegistros:
    def version(self, paquete: str) -> VersionPublicada:
        if paquete == "pypi:garak":
            return VersionPublicada(version="0.17.0", fecha=RECIENTE)
        raise FuenteError(f"{paquete} -> 404")

    def close(self) -> None:
        pass


class FakeDistribuciones:
    def kali(self) -> dict[str, Paquete]:
        return {
            "base-files": Paquete("base-files", "1:2026.3.1"),
            "kali-tools-web": Paquete("kali-tools-web", "2026.3.9", depende_de=["burpsuite", "sqlmap"]),
            "kali-tools-top10": Paquete("kali-tools-top10", "2026.3.9", depende_de=["burpsuite", "nmap"]),
            "burpsuite": Paquete("burpsuite", "2026.8-0kali1", url="https://portswigger.net"),
            "sqlmap": Paquete("sqlmap", "1.10.9-1"),
            "nmap": Paquete("nmap", "7.95"),
        }

    def parrot(self) -> dict[str, Paquete]:
        raise FuenteError("deb.parrot.sh -> 503")

    def blackarch(self) -> dict[str, Paquete]:
        return {
            "garak": Paquete("garak", "0.17.0.r8-1", url="https://github.com/NVIDIA/garak", grupos=["blackarch", "blackarch-ai"]),
            "nemo-guardrails": Paquete(
                "nemo-guardrails", "0.10-1", url="https://github.com/NVIDIA/NeMo-Guardrails", grupos=["blackarch", "blackarch-ai"]
            ),
        }

    def close(self) -> None:
        pass


def _fuentes() -> Fuentes:
    return Fuentes(github=FakeGitHub(), registros=FakeRegistros(), distribuciones=FakeDistribuciones())


def _sembrar(db: Session) -> None:
    db.add_all(
        [
            HerramientaPentest(nombre="garak", tipo=TipoHerramienta.IA, repo_github="NVIDIA/garak", paquete="pypi:garak", version="0.16.0"),
            HerramientaPentest(nombre="LLM Guard", tipo=TipoHerramienta.IA, repo_github="protectai/llm-guard"),
            HerramientaPentest(nombre="Giskard", tipo=TipoHerramienta.IA, repo_github="Giskard-AI/giskard"),
            HerramientaPentest(nombre="TextAttack", tipo=TipoHerramienta.IA, repo_github="QData/TextAttack", version="0.3.11"),
            HerramientaPentest(nombre="Burp Suite"),
            HerramientaPentest(
                nombre="descartada", repo_github="acme/descartada", estado=EstadoHerramienta.DESCARTADA,
                motivo_estado="Es una lista de enlaces",
            ),
            Distribucion(codigo="kali", nombre="Kali Linux"),
            Distribucion(codigo="parrot", nombre="Parrot Security"),
            Distribucion(codigo="blackarch", nombre="BlackArch"),
        ]
    )
    db.commit()


def _herramienta(db: Session, nombre: str) -> HerramientaPentest:
    db.expire_all()
    return db.scalar(select(HerramientaPentest).where(HerramientaPentest.nombre == nombre))


def test_revision_completa(db: Session) -> None:
    _sembrar(db)

    revision = revisar(db, _fuentes(), MockProvider(), ahora=AHORA)

    # Parrot no respondió y TextAttack no se pudo consultar: la revisión sigue con el resto.
    assert revision.estado == EstadoRevision.CON_ERRORES
    assert any("parrot" in e for e in revision.errores)
    assert any("TextAttack" in e for e in revision.errores)

    kali = db.scalar(select(Distribucion).where(Distribucion.codigo == "kali"))
    assert (kali.version, kali.cantidad_herramientas, kali.revisada_at) == ("2026.3", 3, AHORA)
    web = next(c for c in kali.categorias if c["codigo"] == "kali-tools-web")
    assert (web["nombre"], web["destacadas"]) == ("Web", ["burpsuite", "sqlmap"])
    assert db.scalar(select(Distribucion).where(Distribucion.codigo == "parrot")).revisada_at is None

    garak = _herramienta(db, "garak")
    assert garak.version == "0.17.0"
    assert garak.novedad == "Nueva versión 0.17.0 (antes 0.16.0)"
    assert [d["distribucion"] for d in garak.distribuciones] == ["blackarch"]
    assert garak.senales["mantenida"] == "verde" and garak.estrellas == 9584

    llm_guard = _herramienta(db, "LLM Guard")
    assert llm_guard.estado == EstadoHerramienta.EN_OBSERVACION
    assert llm_guard.motivo_estado == "El repositorio protectai/llm-guard está archivado en GitHub"

    giskard = _herramienta(db, "Giskard")
    assert giskard.repo_github == "Giskard-AI/giskard-oss"
    assert giskard.novedad == "El repositorio se mudó a Giskard-AI/giskard-oss"

    burp = _herramienta(db, "Burp Suite")
    assert burp.distribuciones[0] | {"categorias": sorted(burp.distribuciones[0]["categorias"])} == {
        "distribucion": "kali", "paquete": "burpsuite", "version": "2026.8-0kali1", "categorias": ["Top10", "Web"],
    }
    assert burp.senales["mantenida"] == "verde"
    assert burp.version == "2026.8"  # sin el sufijo de empaquetado de Kali

    assert _herramienta(db, "TextAttack").revisada_at is None  # sin datos nuevos: quedó como estaba

    # Radar: entran las que cumplen los criterios, con vínculos sugeridos.
    candidatas = {h.repo_github: h for h in db.scalars(select(HerramientaPentest).where(HerramientaPentest.estado == EstadoHerramienta.CANDIDATA))}
    assert set(candidatas) == {"acme/llm-fuzzer", "NVIDIA/NeMo-Guardrails"}
    fuzzer = candidatas["acme/llm-fuzzer"]
    assert (fuzzer.nombre, fuzzer.origen, fuzzer.tipo) == ("llm-fuzzer", "github:llm-security", TipoHerramienta.IA)
    assert candidatas["NVIDIA/NeMo-Guardrails"].origen == "blackarch-ai"
    assert {v.estado for v in fuzzer.pasos} == {EstadoVinculo.SUGERIDO}
    assert sorted(v.paso.codigo for v in fuzzer.pasos) == ["LLM01", "RT04", "RT05"]
    # La descartada no vuelve; la poco conocida no cumple "adoptada".
    assert _herramienta(db, "descartada").estado == EstadoHerramienta.DESCARTADA
    assert db.scalar(select(HerramientaPentest).where(HerramientaPentest.repo_github == "tiny/apenas-conocida")) is None

    assert revision.resumen["nuevas_candidatas"] == 2
    assert revision.resumen["a_observacion"] == 1


def test_segunda_revision_no_duplica_candidatas(db: Session) -> None:
    _sembrar(db)
    revisar(db, _fuentes(), MockProvider(), ahora=AHORA)

    segunda = revisar(db, _fuentes(), MockProvider(), ahora=AHORA + dt.timedelta(days=15))

    assert "nuevas_candidatas" not in segunda.resumen
    assert _herramienta(db, "garak").novedad is None  # nada cambió desde la anterior


def test_sin_llm_las_candidatas_entran_sin_vinculos(db: Session) -> None:
    _sembrar(db)

    revisar(db, _fuentes(), None, ahora=AHORA)

    fuzzer = db.scalar(select(HerramientaPentest).where(HerramientaPentest.repo_github == "acme/llm-fuzzer"))
    assert fuzzer.estado == EstadoHerramienta.CANDIDATA and fuzzer.pasos == []


def test_se_puede_interrumpir(db: Session) -> None:
    _sembrar(db)

    revision = revisar(db, _fuentes(), MockProvider(), ahora=AHORA, detener=lambda: True)

    assert _herramienta(db, "garak").version == "0.16.0"
    assert "nuevas_candidatas" not in revision.resumen


def test_cuando_toca_revisar(db: Session) -> None:
    assert debe_revisar(db, 15, AHORA) is True  # nunca se revisó

    db.add(RevisionHerramientas(estado=EstadoRevision.OK, finalizada_at=AHORA - dt.timedelta(days=3)))
    db.commit()
    assert debe_revisar(db, 15, AHORA) is False
    assert debe_revisar(db, 15, AHORA + dt.timedelta(days=13)) is True

    solicitada = RevisionHerramientas(estado=EstadoRevision.SOLICITADA)
    db.add(solicitada)
    db.commit()
    assert debe_revisar(db, 15, AHORA) == solicitada  # "revisar ahora" gana aunque no hayan pasado 15 días

    revision = revisar(db, _fuentes(), None, ahora=AHORA, revision=solicitada)
    assert revision.id == solicitada.id and revision.estado == EstadoRevision.CON_ERRORES
