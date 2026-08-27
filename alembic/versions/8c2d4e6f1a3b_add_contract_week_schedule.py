"""Add explicit contract week schedules.

Revision ID: 8c2d4e6f1a3b
Revises: 6b4e2f8a1c3d
"""

import sqlalchemy as sa

from alembic import op

revision = "8c2d4e6f1a3b"
down_revision = "6b4e2f8a1c3d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contract_week_schedule",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("contract_id", sa.Integer(), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("planned", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["contract_id"], ["contract.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "contract_id",
            "week_start",
            name="uq_contract_week_schedule",
        ),
    )


def downgrade() -> None:
    op.drop_table("contract_week_schedule")
