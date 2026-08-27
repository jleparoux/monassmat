"""Add the contractual net rate for complementary hours.

Revision ID: 4f7a2c9e1b6d
Revises: 8c2d4e6f1a3b
"""

import sqlalchemy as sa

from alembic import op

revision = "4f7a2c9e1b6d"
down_revision = "8c2d4e6f1a3b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing contracts remain NULL: the rate can equal the base rate or be
    # contractually increased, so no historical value can safely be inferred.
    for table_name in ("contract", "contract_settings_snapshot"):
        op.add_column(
            table_name,
            sa.Column("complementary_hourly_rate", sa.Float(), nullable=True),
        )


def downgrade() -> None:
    for table_name in ("contract_settings_snapshot", "contract"):
        op.drop_column(table_name, "complementary_hourly_rate")
