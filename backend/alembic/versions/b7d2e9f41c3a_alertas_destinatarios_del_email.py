"""alertas: destinatarios del email

Casillas que reciben el email resumen de alertas, gestionadas desde la
plataforma (antes sólo AISEC_ALERTAS_EMAIL_DESTINO, que queda como respaldo).

Revision ID: b7d2e9f41c3a
Revises: 930a9c0d0c47
Create Date: 2026-10-19 20:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b7d2e9f41c3a'
down_revision: Union[str, Sequence[str], None] = '930a9c0d0c47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('destinatarios_alerta',
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('nombre', sa.String(length=200), nullable=True),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by_id', sa.UUID(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_by_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('destinatarios_alerta')
