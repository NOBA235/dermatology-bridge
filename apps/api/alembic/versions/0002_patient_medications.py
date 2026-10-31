"""patient_medications

Revision ID: 0002_patient_medications
Revises: 0001_initial
Create Date: 2026-10-31 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0002_patient_medications'
down_revision: Union[str, Sequence[str], None] = '0001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create patient_medications table and indexes."""
    op.create_table(
        'patient_medications',
        sa.Column('id', sa.Uuid(), server_default=sa.text('(gen_random_uuid())'), nullable=False),
        sa.Column('patient_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('category', sa.Text(), nullable=False),
        sa.Column('dose', sa.Text(), nullable=True),
        sa.Column('rxnorm_code', sa.Text(), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('prescriber', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_patient_medications_patient', 'patient_medications', ['patient_id'], unique=False)
    op.create_index('idx_patient_medications_start', 'patient_medications', ['patient_id', 'start_date'], unique=False)


def downgrade() -> None:
    """Drop patient_medications table and indexes."""
    op.drop_index('idx_patient_medications_start', table_name='patient_medications')
    op.drop_index('idx_patient_medications_patient', table_name='patient_medications')
    op.drop_table('patient_medications')

