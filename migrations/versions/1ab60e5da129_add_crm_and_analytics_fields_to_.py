"""Add CRM and Analytics fields to Conversation

Revision ID: 1ab60e5da129
Revises: d6568eedfd3d
Create Date: 2026-02-20 17:59:49.245482

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1ab60e5da129'
down_revision: Union[str, Sequence[str], None] = 'd6568eedfd3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('conversations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('analytics', sa.JSON(), nullable=False, server_default='{}'))
        batch_op.add_column(sa.Column('action_items', sa.JSON(), nullable=False, server_default='[]'))
        batch_op.add_column(sa.Column('risk_flags', sa.JSON(), nullable=False, server_default='[]'))
        batch_op.add_column(sa.Column('tags', sa.JSON(), nullable=False, server_default='[]'))
        batch_op.add_column(sa.Column('revenue_tracking', sa.JSON(), nullable=False, server_default='{}'))

def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('conversations', schema=None) as batch_op:
        batch_op.drop_column('revenue_tracking')
        batch_op.drop_column('tags')
        batch_op.drop_column('risk_flags')
        batch_op.drop_column('action_items')
        batch_op.drop_column('analytics')
