"""seed catalogo maestro (138 preguntas PLOT4AI)

Carga los 8 dominios y las 138 preguntas del catálogo PLOT4AI desde el
snapshot congelado alembic/data/catalogo_maestro_v1.json (extraído del Excel
con scripts/extract_catalog_from_excel.py). Migración de datos: `alembic
upgrade head` deja una base nueva lista para usar, sin un paso manual aparte.

- Independiente de los modelos de la app (tablas mínimas definidas acá): si
  los modelos cambian más adelante, esta migración sigue haciendo lo mismo.
- Idempotente (ON CONFLICT DO NOTHING): en una base que ya tenía el catálogo
  (cargado a mano antes de que existiera esta migración) no duplica ni pisa.
- El JSON es un snapshot por versión: para cambiar el catálogo no se edita
  este archivo ni esta migración, se genera catalogo_maestro_v2.json y se
  agrega una migración nueva.

Revision ID: 8c55274c7ed7
Revises: 6b22b2fcfd06
Create Date: 2026-09-24 10:00:00.000000

"""

import json
import uuid
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "8c55274c7ed7"
down_revision: Union[str, Sequence[str], None] = "6b22b2fcfd06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "catalogo_maestro_v1.json"

dominios = sa.table(
    "dominios",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("codigo", sa.String),
    sa.column("nombre", sa.String),
    sa.column("peso", sa.Numeric),
    sa.column("total_preguntas", sa.SmallInteger),
)

preguntas = sa.table(
    "preguntas",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("dominio_id", postgresql.UUID(as_uuid=True)),
    sa.column("numero", sa.SmallInteger),
    sa.column("texto_es", sa.Text),
    sa.column("texto_en", sa.Text),
    sa.column("tipo", postgresql.ENUM(name="pregunta_tipo", create_type=False)),
    sa.column("polaridad", postgresql.ENUM(name="polaridad", create_type=False)),
    sa.column("tier", postgresql.ENUM(name="tier", create_type=False)),
    sa.column("multiplicador", sa.SmallInteger),
    sa.column("impacto_primario", sa.String),
    sa.column("referencias_regulatorias", sa.Text),
    sa.column("justificacion_tier", sa.Text),
    sa.column("explicacion_control_es", sa.Text),
    sa.column("explicacion_control_en", sa.Text),
)


def seed_catalog(connection: sa.Connection) -> None:
    payload = json.loads(SEED_PATH.read_text(encoding="utf-8"))

    connection.execute(
        postgresql.insert(dominios).on_conflict_do_nothing(),
        [
            {
                "id": uuid.uuid4(),
                "codigo": d["codigo"],
                "nombre": d["nombre"],
                "peso": d["peso"],
                "total_preguntas": d["total_preguntas"],
            }
            for d in payload["dominios"]
        ],
    )

    # Si el dominio ya existía se conserva su id original, por eso se lee de la base.
    dominio_id_by_codigo = dict(
        connection.execute(sa.select(dominios.c.codigo, dominios.c.id)).all()
    )

    connection.execute(
        postgresql.insert(preguntas).on_conflict_do_nothing(),
        [
            {
                "id": uuid.uuid4(),
                "dominio_id": dominio_id_by_codigo[p["dominio_codigo"]],
                "numero": p["numero"],
                "texto_es": p["texto_es"],
                "texto_en": p["texto_en"],
                "tipo": p["tipo"].upper(),
                "polaridad": p["polaridad"].upper(),
                "tier": p["tier"].upper(),
                "multiplicador": p["multiplicador"],
                "impacto_primario": p.get("impacto_primario"),
                "referencias_regulatorias": p.get("referencias_regulatorias"),
                "justificacion_tier": p.get("justificacion_tier"),
                "explicacion_control_es": p.get("explicacion_control_es"),
                "explicacion_control_en": p.get("explicacion_control_en"),
            }
            for p in payload["preguntas"]
        ],
    )


def upgrade() -> None:
    seed_catalog(op.get_bind())


def downgrade() -> None:
    """Quita el catálogo sembrado. Falla (por la FK) si algún caso ya usa
    alguna de esas preguntas: en ese caso hay que sacarlas de los casos antes."""
    payload = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    codigos = [d["codigo"] for d in payload["dominios"]]
    connection = op.get_bind()

    ids = sa.select(dominios.c.id).where(dominios.c.codigo.in_(codigos))
    connection.execute(sa.delete(preguntas).where(preguntas.c.dominio_id.in_(ids)))
    connection.execute(sa.delete(dominios).where(dominios.c.codigo.in_(codigos)))
