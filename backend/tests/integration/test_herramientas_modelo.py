"""H1: modelo de herramientas (Catálogo/Radar), distribuciones y vínculos con
pasos de estándares (ver tasks/herramientas-radar.md)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.pentesting.models import (
    Distribucion,
    EstadoHerramienta,
    EstadoVinculo,
    HerramientaPaso,
    HerramientaPentest,
    OrigenVinculo,
    PentestEstandarPaso,
    TipoHerramienta,
)


def _paso(db: Session, codigo: str = "LLM01") -> PentestEstandarPaso:
    # Los estándares y sus pasos los siembra la migración de datos.
    return db.scalar(select(PentestEstandarPaso).where(PentestEstandarPaso.codigo == codigo))


def test_herramienta_cargada_a_mano_va_al_catalogo(client: TestClient, auth_headers: dict[str, str], db: Session) -> None:
    response = client.post("/pentesting/herramientas", json={"nombre": "Burp Suite"}, headers=auth_headers)
    assert response.status_code == 201

    herramienta = db.get(HerramientaPentest, response.json()["id"])
    assert herramienta.tipo == TipoHerramienta.ESPECIALIZADA
    assert herramienta.estado == EstadoHerramienta.ACTIVA
    assert herramienta.origen == "manual"
    assert (herramienta.temas, herramienta.distribuciones, herramienta.senales) == ([], [], {})
    assert herramienta.archivada is False


def test_herramienta_de_ia_candidata_con_datos_de_mantenimiento(db: Session) -> None:
    herramienta = HerramientaPentest(
        nombre="garak",
        tipo=TipoHerramienta.IA,
        estado=EstadoHerramienta.CANDIDATA,
        origen="github:llm-security",
        repo_github="NVIDIA/garak",
        paquete="pypi:garak",
        estrellas=9584,
        temas=["llm-security", "red-teaming"],
        distribuciones=[{"distribucion": "blackarch", "paquete": "garak", "version": "0.17.0", "categorias": ["ai"]}],
        senales={"mantenida": "verde", "adoptada": "verde"},
    )
    db.add(herramienta)
    db.commit()
    db.expire_all()

    guardada = db.scalar(select(HerramientaPentest).where(HerramientaPentest.repo_github == "NVIDIA/garak"))
    assert guardada.estado == EstadoHerramienta.CANDIDATA
    assert guardada.distribuciones[0]["distribucion"] == "blackarch"
    assert guardada.senales["mantenida"] == "verde"


def test_repo_github_es_unico(db: Session) -> None:
    db.add_all([HerramientaPentest(nombre="a", repo_github="o/r"), HerramientaPentest(nombre="b", repo_github="o/r")])
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_vinculo_con_paso_unico_y_se_borra_con_la_herramienta(db: Session) -> None:
    paso = _paso(db)
    herramienta = HerramientaPentest(nombre="garak", tipo=TipoHerramienta.IA)
    herramienta.pasos.append(
        HerramientaPaso(paso_id=paso.id, origen=OrigenVinculo.CURADO, estado=EstadoVinculo.CONFIRMADO)
    )
    db.add(herramienta)
    db.commit()

    db.add(HerramientaPaso(herramienta_id=herramienta.id, paso_id=paso.id, origen=OrigenVinculo.ANALISTA,
                           estado=EstadoVinculo.SUGERIDO))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    db.delete(db.get(HerramientaPentest, herramienta.id))
    db.commit()
    assert db.scalar(select(HerramientaPaso).where(HerramientaPaso.paso_id == paso.id)) is None
    assert db.get(PentestEstandarPaso, paso.id) is not None  # el paso del estándar no se toca


def test_distribucion(db: Session) -> None:
    db.add(
        Distribucion(
            codigo="kali",
            nombre="Kali Linux",
            categorias=[{"codigo": "kali-tools-web", "nombre": "Web", "cantidad": 45, "destacadas": ["burpsuite"]}],
        )
    )
    db.commit()
    db.expire_all()

    kali = db.scalar(select(Distribucion).where(Distribucion.codigo == "kali"))
    assert kali.categorias[0]["destacadas"] == ["burpsuite"]
