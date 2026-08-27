"""Add explicit weekly schedule facts.

Revision ID: 6b4e2f8a1c3d
Revises: 3a7c1d5e9b2f
"""

import sqlalchemy as sa

from alembic import op

revision = "6b4e2f8a1c3d"
down_revision = "3a7c1d5e9b2f"
branch_labels = None
depends_on = None

DAY_COLUMNS = (
    "monday_hours",
    "tuesday_hours",
    "wednesday_hours",
    "thursday_hours",
    "friday_hours",
    "saturday_hours",
    "sunday_hours",
)


def upgrade() -> None:
    # Existing values stay NULL: hours_per_week and days_per_week are not enough
    # to infer which days are worked or whether daily durations are identical.
    for table_name in ("contract", "contract_settings_snapshot"):
        for column_name in DAY_COLUMNS:
            op.add_column(
                table_name,
                sa.Column(column_name, sa.Float(), nullable=True),
            )


def downgrade() -> None:
    for table_name in ("contract_settings_snapshot", "contract"):
        for column_name in reversed(DAY_COLUMNS):
            op.drop_column(table_name, column_name)
