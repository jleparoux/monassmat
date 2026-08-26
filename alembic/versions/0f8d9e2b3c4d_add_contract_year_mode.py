import sqlalchemy as sa

from alembic import op

revision = "0f8d9e2b3c4d"
down_revision = "4d2b1a7c3f8e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    year_mode_enum = sa.Enum("complete", "incomplete", name="contract_year_mode")
    year_mode_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "contract",
        sa.Column(
            "year_mode",
            year_mode_enum,
            nullable=False,
            server_default="complete",
        ),
    )
    op.add_column(
        "contract_settings_snapshot",
        sa.Column(
            "year_mode",
            year_mode_enum,
            nullable=False,
            server_default="complete",
        ),
    )
def downgrade() -> None:
    op.drop_column("contract_settings_snapshot", "year_mode")
    op.drop_column("contract", "year_mode")
    year_mode_enum = sa.Enum("complete", "incomplete", name="contract_year_mode")
    year_mode_enum.drop(op.get_bind(), checkfirst=True)
