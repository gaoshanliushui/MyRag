"""Add api_key_hash column to tenants table

Revision ID: 002_add_api_key_hash
Revises: 001_initial
Create Date: 2025-06-17 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '002_add_api_key_hash'
down_revision: Union[str, None] = '001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Add api_key_hash column
    op.add_column('tenants', sa.Column('api_key_hash', sa.String(length=64), nullable=True))

    # Create index for faster lookup
    op.create_index(op.f('ix_tenants_api_key_hash'), 'tenants', ['api_key_hash'], unique=True)

    # Fill existing tenants with hashed api_key
    from app.utils.security import hash_api_key
    connection = op.get_bind()
    tenants = connection.execute(sa.text("SELECT id, api_key FROM tenants"))
    for tenant in tenants:
        if tenant.api_key:
            hashed = hash_api_key(tenant.api_key)
            connection.execute(
                sa.text("UPDATE tenants SET api_key_hash = :hash WHERE id = :id"),
                hash=hashed, id=tenant.id
            )

    # Make api_key_hash required
    op.alter_column('tenants', 'api_key_hash', nullable=False)


def downgrade() -> None:
    # Remove index
    op.drop_index(op.f('ix_tenants_api_key_hash'), table_name='tenants')
    # Drop column
    op.drop_column('tenants', 'api_key_hash')