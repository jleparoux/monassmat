from alembic import op
import sqlalchemy as sa

revision = "7b3f9c8a2e1b"
down_revision = "5e7d2c9a4f21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("contract", sa.Column("days_per_week", sa.Integer(), nullable=True))
    op.add_column("contract", sa.Column("majoration_threshold", sa.Float(), nullable=True))
    op.add_column("contract", sa.Column("majoration_rate", sa.Float(), nullable=True))
    op.add_column("contract", sa.Column("fee_meal_amount", sa.Float(), nullable=True))
    op.add_column("contract", sa.Column("fee_maintenance_amount", sa.Float(), nullable=True))
    op.add_column("contract", sa.Column("salary_net_ceiling", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("contract", "salary_net_ceiling")
    op.drop_column("contract", "fee_maintenance_amount")
    op.drop_column("contract", "fee_meal_amount")
    op.drop_column("contract", "majoration_rate")
    op.drop_column("contract", "majoration_threshold")
    op.drop_column("contract", "days_per_week")
