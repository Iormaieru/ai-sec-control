"""integracion jira: estados del tablero, vinculo con tickets, comentarios y outbox

Revision ID: b7d1e2f3a4c5
Revises: ece0f83e9af2
Create Date: 2026-10-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b7d1e2f3a4c5'
down_revision: Union[str, Sequence[str], None] = 'ece0f83e9af2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Estados viejos -> columnas del tablero IA-SEC. Cerrado/aprobado y
# rechazado quedan los dos en Hecho (en Jira son Finalizado/Cancelado).
_ESTADOS = {
    'ABIERTO': 'POR_HACER',
    'EN_ANALISIS': 'EN_CURSO',
    'ESPERANDO_PROVEEDOR': 'ESPERANDO_RESPUESTA',
    'CERRADO_APROBADO': 'HECHO',
    'RECHAZADO': 'HECHO',
}
_ESTADOS_INVERSO = {
    'POR_HACER': 'ABIERTO',
    'EN_CURSO': 'EN_ANALISIS',
    'ESPERANDO_RESPUESTA': 'ESPERANDO_PROVEEDOR',
    'HECHO': 'CERRADO_APROBADO',
}


def _cambiar_enum_estado(nuevos: list[str], mapeo: dict[str, str]) -> None:
    op.execute('ALTER TABLE casos ALTER COLUMN estado TYPE varchar(32) USING estado::text')
    op.execute('DROP TYPE caso_estado')
    for viejo, nuevo in mapeo.items():
        op.execute(sa.text('UPDATE casos SET estado = :nuevo WHERE estado = :viejo').bindparams(viejo=viejo, nuevo=nuevo))
    sa.Enum(*nuevos, name='caso_estado').create(op.get_bind())
    op.execute('ALTER TABLE casos ALTER COLUMN estado TYPE caso_estado USING estado::caso_estado')


def upgrade() -> None:
    """Upgrade schema."""
    _cambiar_enum_estado(['POR_HACER', 'EN_CURSO', 'ESPERANDO_RESPUESTA', 'HECHO'], _ESTADOS)

    op.alter_column('casos', 'empresa_responsable', existing_type=sa.String(length=200), nullable=True)
    op.alter_column('casos', 'tipo', existing_type=sa.Enum(name='caso_tipo'), nullable=True)
    # Los resúmenes de Jira admiten hasta 255 caracteres.
    op.alter_column('casos', 'nombre_proyecto', existing_type=sa.String(length=200), type_=sa.String(length=255))

    origen = sa.Enum('PLATAFORMA', 'JIRA', name='origen')
    origen.create(op.get_bind())
    sync_estado = sa.Enum('OK', 'PENDIENTE', 'ERROR', name='jira_sync_estado')
    sync_estado.create(op.get_bind())

    op.add_column('casos', sa.Column('origen', origen, server_default='PLATAFORMA', nullable=False))
    op.add_column('casos', sa.Column('jira_issue_id', sa.String(length=32), nullable=True))
    op.add_column('casos', sa.Column('jira_issue_key', sa.String(length=32), nullable=True))
    op.add_column('casos', sa.Column('jira_status_id', sa.String(length=32), nullable=True))
    op.add_column('casos', sa.Column('jira_status_nombre', sa.String(length=100), nullable=True))
    op.add_column('casos', sa.Column('jira_tipo_solicitud_id', sa.String(length=32), nullable=True))
    op.add_column('casos', sa.Column('jira_updated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('casos', sa.Column('jira_sync_estado', sync_estado, nullable=True))
    op.add_column('casos', sa.Column('jira_sync_error', sa.Text(), nullable=True))
    op.create_unique_constraint('uq_casos_jira_issue_id', 'casos', ['jira_issue_id'])
    op.create_unique_constraint('uq_casos_jira_issue_key', 'casos', ['jira_issue_key'])

    op.create_table('caso_comentarios',
    sa.Column('caso_id', sa.UUID(), nullable=False),
    sa.Column('cuerpo', sa.Text(), nullable=False),
    sa.Column('autor_nombre', sa.String(length=200), nullable=False),
    sa.Column('origen', postgresql.ENUM(name='origen', create_type=False), nullable=False),
    sa.Column('publico', sa.Boolean(), nullable=False),
    sa.Column('jira_comment_id', sa.String(length=32), nullable=True),
    sa.Column('fecha', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by_id', sa.UUID(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_by_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['caso_id'], ['casos.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('jira_comment_id')
    )
    op.create_index(op.f('ix_caso_comentarios_caso_id'), 'caso_comentarios', ['caso_id'], unique=False)

    op.create_table('jira_outbox',
    sa.Column('caso_id', sa.UUID(), nullable=False),
    sa.Column('comentario_id', sa.UUID(), nullable=True),
    sa.Column('operacion', sa.Enum('CREAR_ISSUE', 'ACTUALIZAR_ISSUE', 'CREAR_COMENTARIO', name='operacion_jira'), nullable=False),
    sa.Column('intentos', sa.Integer(), nullable=False),
    sa.Column('proximo_intento_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('ultimo_error', sa.Text(), nullable=True),
    sa.Column('descartada', sa.Boolean(), nullable=False),
    sa.Column('procesado_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['caso_id'], ['casos.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['comentario_id'], ['caso_comentarios.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_jira_outbox_caso_id'), 'jira_outbox', ['caso_id'], unique=False)

    op.create_table('jira_sync_cursor',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('ultimo_poll_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('jira_sync_cursor')
    op.drop_index(op.f('ix_jira_outbox_caso_id'), table_name='jira_outbox')
    op.drop_table('jira_outbox')
    op.drop_index(op.f('ix_caso_comentarios_caso_id'), table_name='caso_comentarios')
    op.drop_table('caso_comentarios')
    op.drop_constraint('uq_casos_jira_issue_key', 'casos', type_='unique')
    op.drop_constraint('uq_casos_jira_issue_id', 'casos', type_='unique')
    # Los casos importados de Jira no tienen tipo/empresa: se completan con
    # un valor genérico antes de volver a hacer las columnas obligatorias.
    op.execute("UPDATE casos SET tipo = 'CANDIDATO' WHERE tipo IS NULL")
    op.execute("UPDATE casos SET empresa_responsable = 'Sin definir' WHERE empresa_responsable IS NULL")
    op.execute("UPDATE casos SET nombre_proyecto = left(nombre_proyecto, 200)")
    for columna in ('jira_sync_error', 'jira_sync_estado', 'jira_updated_at', 'jira_tipo_solicitud_id',
                    'jira_status_nombre', 'jira_status_id', 'jira_issue_key', 'jira_issue_id', 'origen'):
        op.drop_column('casos', columna)
    op.execute('DROP TYPE IF EXISTS operacion_jira')
    op.execute('DROP TYPE IF EXISTS jira_sync_estado')
    op.execute('DROP TYPE IF EXISTS origen')
    op.alter_column('casos', 'nombre_proyecto', existing_type=sa.String(length=255), type_=sa.String(length=200))
    op.alter_column('casos', 'tipo', existing_type=sa.Enum(name='caso_tipo'), nullable=False)
    op.alter_column('casos', 'empresa_responsable', existing_type=sa.String(length=200), nullable=False)
    _cambiar_enum_estado(['ABIERTO', 'EN_ANALISIS', 'ESPERANDO_PROVEEDOR', 'CERRADO_APROBADO', 'RECHAZADO'], _ESTADOS_INVERSO)
