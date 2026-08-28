"""Record monthly Pajemploi declaration confirmations.

Revision ID: 7d5a1c9e3b2f
Revises: 4f7a2c9e1b6d
"""

import sqlalchemy as sa

from alembic import op

revision = "7d5a1c9e3b2f"
down_revision = "4f7a2c9e1b6d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "monthly_declaration",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("contract_id", sa.Integer(), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("declared_on", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(["contract_id"], ["contract.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "contract_id",
            "month",
            name="uq_monthly_declaration_contract_month",
        ),
    )


def downgrade() -> None:
    op.drop_table("monthly_declaration")
