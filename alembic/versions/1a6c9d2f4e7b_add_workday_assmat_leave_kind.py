"""add workday assmat leave kind

Revision ID: 1a6c9d2f4e7b
Revises: 8c4f3e0a2d1b
Create Date: 2025-12-30 00:35:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "1a6c9d2f4e7b"
down_revision: Union[str, Sequence[str], None] = "8c4f3e0a2d1b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE workdaykind ADD VALUE IF NOT EXISTS 'ASSMAT_LEAVE'")


def downgrade() -> None:
    pass
