"""seed catalogo inicial de herramientas, distribuciones y vinculos con pasos

Carga desde alembic/data/herramientas_v1.json (tasks/herramientas-radar.md, H4):
7 herramientas de seguridad de IA, 4 especializadas (Burp Suite, sqlmap, ZAP,
nuclei), las distribuciones Kali, Parrot y BlackArch, y los vínculos curados
(confirmados) entre cada herramienta y los pasos de los estándares.

Mismo criterio que el seed de estándares: tablas mínimas definidas acá,
idempotente y el JSON es un snapshot congelado (lo mantiene al día el worker).
Si una herramienta ya existe con el mismo nombre (ej. cargada a mano), no se
duplica: se completan sólo sus datos vacíos y se agregan los vínculos.

Revision ID: a1c2d3e4f5a6
Revises: 0692c18a7b52
Create Date: 2026-10-16 12:00:00.000000

"""

import json
import uuid
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "0692c18a7b52"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "herramientas_v1.json"
ORIGEN = "curado"

herramientas = sa.table(
    "herramientas_pentest",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("nombre", sa.String),
    sa.column("descripcion", sa.Text),
    sa.column("url_referencia", sa.String),
    sa.column("tipo", postgresql.ENUM("IA", "ESPECIALIZADA", name="herramienta_tipo", create_type=False)),
    sa.column("estado", postgresql.ENUM(
        "CANDIDATA", "ACTIVA", "EN_OBSERVACION", "RETIRADA", "DESCARTADA", name="herramienta_estado", create_type=False
    )),
    sa.column("motivo_estado", sa.Text),
    sa.column("origen", sa.String),
    sa.column("repo_github", sa.String),
    sa.column("paquete", sa.String),
    sa.column("documentacion_url", sa.String),
    sa.column("notas_version_url", sa.String),
    sa.column("licencia", sa.String),
)
distribuciones = sa.table(
    "distribuciones",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("codigo", sa.String),
    sa.column("nombre", sa.String),
    sa.column("descripcion", sa.Text),
    sa.column("sitio_url", sa.String),
    sa.column("documentacion_url", sa.String),
)
pasos = sa.table(
    "pentest_estandar_pasos",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("codigo", sa.String),
)
vinculos = sa.table(
    "herramienta_pasos",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("herramienta_id", postgresql.UUID(as_uuid=True)),
    sa.column("paso_id", postgresql.UUID(as_uuid=True)),
    sa.column("origen", postgresql.ENUM("CURADO", "SUGERIDO_IA", "ANALISTA", name="vinculo_origen", create_type=False)),
    sa.column("estado", postgresql.ENUM("SUGERIDO", "CONFIRMADO", name="vinculo_estado", create_type=False)),
    sa.column("justificacion", sa.Text),
)

_CAMPOS = ("descripcion", "url_referencia", "repo_github", "paquete", "documentacion_url", "notas_version_url", "licencia")


def _payload() -> dict:
    return json.loads(SEED_PATH.read_text(encoding="utf-8"))


def seed(connection: sa.Connection) -> None:
    datos = _payload()
    paso_por_codigo = {codigo: id_ for id_, codigo in connection.execute(sa.select(pasos.c.id, pasos.c.codigo)) if codigo}

    for h in datos["herramientas"]:
        existente = connection.execute(
            sa.select(herramientas).where(sa.func.lower(herramientas.c.nombre) == h["nombre"].lower())
        ).mappings().first()
        if existente is None:
            herramienta_id = uuid.uuid4()
            connection.execute(
                herramientas.insert().values(
                    id=herramienta_id,
                    nombre=h["nombre"],
                    tipo=h["tipo"].upper(),
                    estado=h["estado"].upper(),
                    motivo_estado=h.get("motivo_estado"),
                    origen=ORIGEN,
                    **{campo: h.get(campo) for campo in _CAMPOS},
                )
            )
        else:
            herramienta_id = existente["id"]
            vacios = {campo: h[campo] for campo in _CAMPOS if h.get(campo) and not existente[campo]}
            connection.execute(
                herramientas.update().where(herramientas.c.id == herramienta_id).values(tipo=h["tipo"].upper(), **vacios)
            )

        ya_vinculados = set(
            connection.scalars(sa.select(vinculos.c.paso_id).where(vinculos.c.herramienta_id == herramienta_id))
        )
        for v in h["pasos"]:
            paso_id = paso_por_codigo.get(v["paso"])
            if paso_id is None or paso_id in ya_vinculados:
                continue  # el paso se borró o renombró desde la plataforma, o el vínculo ya existe
            connection.execute(
                vinculos.insert().values(
                    id=uuid.uuid4(),
                    herramienta_id=herramienta_id,
                    paso_id=paso_id,
                    origen="CURADO",
                    estado="CONFIRMADO",
                    justificacion=v.get("nota"),
                )
            )

    existentes = set(connection.scalars(sa.select(distribuciones.c.codigo)))
    for d in datos["distribuciones"]:
        if d["codigo"] not in existentes:
            connection.execute(distribuciones.insert().values(id=uuid.uuid4(), **d))


def upgrade() -> None:
    seed(op.get_bind())


def downgrade() -> None:
    """Quita lo sembrado. Falla por la FK si alguna herramienta curada ya se
    usó en un ataque (no se borra información de pentests)."""
    datos = _payload()
    conn = op.get_bind()
    conn.execute(sa.delete(vinculos).where(vinculos.c.origen == "CURADO"))
    conn.execute(sa.delete(herramientas).where(herramientas.c.origen == ORIGEN))
    conn.execute(sa.delete(distribuciones).where(distribuciones.c.codigo.in_([d["codigo"] for d in datos["distribuciones"]])))
