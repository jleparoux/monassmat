"""Add contract name

Revision ID: 4d2b1a7c3f8e
Revises: 9c2e4f7a1b6d
Create Date: 2025-01-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "4d2b1a7c3f8e"
down_revision = "9c2e4f7a1b6d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("contract", sa.Column("name", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("contract", "name")
