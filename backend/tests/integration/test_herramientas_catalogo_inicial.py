"""H4: catálogo inicial de herramientas (migración a1c2d3e4f5a6 y su JSON)."""

import importlib.util
import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import engine
from app.pentesting.models import (
    Distribucion,
    EstadoHerramienta,
    EstadoVinculo,
    HerramientaPaso,
    HerramientaPentest,
    OrigenVinculo,
    TipoHerramienta,
)

ALEMBIC = Path(__file__).resolve().parents[2] / "alembic"
DATOS = json.loads((ALEMBIC / "data" / "herramientas_v1.json").read_text(encoding="utf-8"))
ESTANDARES = json.loads((ALEMBIC / "data" / "pentest_estandares_v1.json").read_text(encoding="utf-8"))


def _migracion():
    ruta = ALEMBIC / "versions" / "a1c2d3e4f5a6_seed_catalogo_herramientas.py"
    spec = importlib.util.spec_from_file_location("seed_herramientas", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _sembrar() -> None:
    with engine.begin() as conn:
        _migracion().seed(conn)


def test_json_integro() -> None:
    codigos_pasos = {p["codigo"] for e in ESTANDARES["estandares"] for p in e["pasos"]}
    herramientas = DATOS["herramientas"]

    assert len(herramientas) == 11
    assert sum(h["tipo"] == "ia" for h in herramientas) == 7
    assert {d["codigo"] for d in DATOS["distribuciones"]} == {"kali", "parrot", "blackarch"}
    assert len({h["nombre"].lower() for h in herramientas}) == len(herramientas)
    for h in herramientas:
        assert h["documentacion_url"].startswith("https://"), h["nombre"]
        assert h["pasos"], f"{h['nombre']} no está vinculada a ningún paso"
        for vinculo in h["pasos"]:
            assert vinculo["paso"] in codigos_pasos, f"{h['nombre']}: paso inexistente {vinculo['paso']}"


def test_siembra_catalogo_distribuciones_y_vinculos(db: Session) -> None:
    _sembrar()

    herramientas = {h.nombre: h for h in db.scalars(select(HerramientaPentest))}
    assert len(herramientas) == 11
    assert herramientas["garak"].tipo == TipoHerramienta.IA
    assert herramientas["garak"].repo_github == "NVIDIA/garak"
    assert herramientas["Burp Suite"].repo_github is None  # comercial: sin repo
    assert herramientas["LLM Guard"].estado == EstadoHerramienta.EN_OBSERVACION
    assert all(h.origen == "curado" for h in herramientas.values())

    total_vinculos = sum(len(h["pasos"]) for h in DATOS["herramientas"])
    vinculos = db.scalars(select(HerramientaPaso)).all()
    assert len(vinculos) == total_vinculos
    assert {(v.origen, v.estado) for v in vinculos} == {(OrigenVinculo.CURADO, EstadoVinculo.CONFIRMADO)}
    assert db.scalar(select(func.count()).select_from(Distribucion)) == 3


def test_siembra_idempotente_y_respeta_lo_cargado_a_mano(db: Session) -> None:
    db.add(HerramientaPentest(nombre="burp suite", descripcion="La que usamos en el área"))
    db.commit()

    _sembrar()
    _sembrar()

    db.expire_all()
    burps = db.scalars(select(HerramientaPentest).where(func.lower(HerramientaPentest.nombre) == "burp suite")).all()
    assert len(burps) == 1
    burp = burps[0]
    assert burp.descripcion == "La que usamos en el área"  # no se pisa lo cargado a mano
    assert burp.documentacion_url == "https://portswigger.net/burp/documentation"  # se completa lo vacío
    assert burp.origen == "manual"
    assert len(burp.pasos) == 6
    assert db.scalar(select(func.count()).select_from(HerramientaPentest)) == 11
