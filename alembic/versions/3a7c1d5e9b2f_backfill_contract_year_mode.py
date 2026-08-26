"""Backfill the regular-care mode from unambiguous week counts.

Revision ID: 3a7c1d5e9b2f
Revises: 0f8d9e2b3c4d
"""

import sqlalchemy as sa

from alembic import op

revision = "3a7c1d5e9b2f"
down_revision = "0f8d9e2b3c4d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The previous migration assigned "complete" to every existing row. Under
    # article 97.1, 46 programmed weeks or fewer unambiguously means the
    # "46 weeks or less" mode. Values from 47 to 51 are left untouched because
    # they require a user decision rather than an inferred correction.
    op.execute(
        sa.text(
            """
            UPDATE contract
            SET year_mode = 'incomplete'
            WHERE weeks_per_year <= 46
              AND year_mode = 'complete'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE contract_settings_snapshot
            SET year_mode = 'incomplete'
            WHERE weeks_per_year <= 46
              AND year_mode = 'complete'
            """
        )
    )


def downgrade() -> None:
    # This is a factual data correction. The previous value cannot be restored
    # without also reverting legitimate user selections, so downgrade is a
    # deliberate no-op.
    pass
