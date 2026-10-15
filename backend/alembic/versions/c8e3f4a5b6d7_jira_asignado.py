"""jira: persona asignada del ticket (id, nombre y avatar)

Revision ID: c8e3f4a5b6d7
Revises: b7d1e2f3a4c5
Create Date: 2026-10-16 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8e3f4a5b6d7'
down_revision: Union[str, Sequence[str], None] = 'b7d1e2f3a4c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('casos', sa.Column('jira_asignado_id', sa.String(length=128), nullable=True))
    op.add_column('casos', sa.Column('jira_asignado_nombre', sa.String(length=200), nullable=True))
    op.add_column('casos', sa.Column('jira_asignado_avatar_url', sa.String(length=500), nullable=True))
    # Los casos ya importados no tienen el asignado: la próxima sincronización
    # vuelve a leer todos los tickets del tablero.
    op.execute('UPDATE casos SET jira_updated_at = NULL WHERE jira_issue_id IS NOT NULL')
    op.execute('DELETE FROM jira_sync_cursor')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('casos', 'jira_asignado_avatar_url')
    op.drop_column('casos', 'jira_asignado_nombre')
    op.drop_column('casos', 'jira_asignado_id')
