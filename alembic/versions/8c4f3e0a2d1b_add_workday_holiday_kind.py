"""add workday holiday kind

Revision ID: 8c4f3e0a2d1b
Revises: 7b3f9c8a2e1b
Create Date: 2025-12-30 00:15:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "8c4f3e0a2d1b"
down_revision: Union[str, Sequence[str], None] = "7b3f9c8a2e1b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE workdaykind ADD VALUE IF NOT EXISTS 'HOLIDAY'")


def downgrade() -> None:
    pass
