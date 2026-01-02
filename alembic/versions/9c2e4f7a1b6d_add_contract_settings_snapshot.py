"""Add contract settings snapshot

Revision ID: 9c2e4f7a1b6d
Revises: 1a6c9d2f4e7b
Create Date: 2025-01-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9c2e4f7a1b6d"
down_revision = "1a6c9d2f4e7b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contract_settings_snapshot",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("contract_id", sa.Integer(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("hours_per_week", sa.Float(), nullable=False),
        sa.Column("weeks_per_year", sa.Float(), nullable=False),
        sa.Column("hourly_rate", sa.Float(), nullable=False),
        sa.Column("days_per_week", sa.Integer(), nullable=True),
        sa.Column("majoration_threshold", sa.Float(), nullable=True),
        sa.Column("majoration_rate", sa.Float(), nullable=True),
        sa.Column("fee_meal_amount", sa.Float(), nullable=True),
        sa.Column("fee_maintenance_amount", sa.Float(), nullable=True),
        sa.Column("salary_net_ceiling", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["contract_id"], ["contract.id"]),
        sa.UniqueConstraint(
            "contract_id",
            "valid_from",
            name="uq_contract_settings_snapshot",
        ),
    )


def downgrade() -> None:
    op.drop_table("contract_settings_snapshot")
