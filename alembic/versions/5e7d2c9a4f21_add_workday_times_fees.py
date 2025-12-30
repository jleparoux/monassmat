from alembic import op
import sqlalchemy as sa

revision = "5e7d2c9a4f21"
down_revision = "266d8bc76cfe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workday", sa.Column("start_time", sa.Time(), nullable=True))
    op.add_column("workday", sa.Column("end_time", sa.Time(), nullable=True))
    op.add_column(
        "workday",
        sa.Column(
            "fee_meal",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "workday",
        sa.Column(
            "fee_maintenance",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("workday", "fee_maintenance")
    op.drop_column("workday", "fee_meal")
    op.drop_column("workday", "end_time")
    op.drop_column("workday", "start_time")
