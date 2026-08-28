"""Add recalculable paid leave facts.

Revision ID: 9e4b6a2c1d7f
Revises: 7d5a1c9e3b2f
"""

import sqlalchemy as sa

from alembic import op

revision = "9e4b6a2c1d7f"
down_revision = "7d5a1c9e3b2f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "paid_leave_period_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("contract_id", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column(
            "basis_mode",
            sa.Enum("auto", "months", "weeks", name="paidleavebasismode"),
            nullable=False,
        ),
        sa.Column("worked_months", sa.Integer(), nullable=True),
        sa.Column("worked_weeks", sa.Integer(), nullable=True),
        sa.Column("worked_days", sa.Integer(), nullable=False),
        sa.Column("scheduled_days_per_week", sa.Integer(), nullable=True),
        sa.Column("dependent_children", sa.Integer(), nullable=False),
        sa.Column("employee_under_21", sa.Boolean(), nullable=False),
        sa.Column("history_confirmed", sa.Boolean(), nullable=False),
        sa.Column("additional_days", sa.Integer(), nullable=False),
        sa.Column("additional_days_reason", sa.String(length=240), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.CheckConstraint(
            "additional_days >= 0",
            name="ck_paid_leave_additional_days",
        ),
        sa.CheckConstraint(
            "dependent_children >= 0",
            name="ck_paid_leave_children",
        ),
        sa.CheckConstraint(
            "scheduled_days_per_week IS NULL OR "
            "(scheduled_days_per_week >= 1 AND scheduled_days_per_week <= 7)",
            name="ck_paid_leave_scheduled_days",
        ),
        sa.CheckConstraint(
            "worked_days >= 0",
            name="ck_paid_leave_worked_days",
        ),
        sa.CheckConstraint(
            "worked_months IS NULL OR (worked_months >= 0 AND worked_months <= 12)",
            name="ck_paid_leave_worked_months",
        ),
        sa.CheckConstraint(
            "worked_weeks IS NULL OR worked_weeks >= 0",
            name="ck_paid_leave_worked_weeks",
        ),
        sa.ForeignKeyConstraint(["contract_id"], ["contract.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "contract_id",
            "period_start",
            name="uq_paid_leave_period_settings",
        ),
    )
    op.create_table(
        "paid_leave_absence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("contract_id", sa.Integer(), nullable=False),
        sa.Column("reference_period_start", sa.Date(), nullable=False),
        sa.Column("absence_start", sa.Date(), nullable=False),
        sa.Column("absence_end", sa.Date(), nullable=False),
        sa.Column(
            "treatment",
            sa.Enum("acquired", "advance", "unpaid", name="paidleavetreatment"),
            nullable=False,
        ),
        sa.Column("regularized_days", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.CheckConstraint(
            "absence_end >= absence_start",
            name="ck_paid_leave_absence_dates",
        ),
        sa.CheckConstraint(
            "regularized_days >= 0",
            name="ck_paid_leave_regularized_days",
        ),
        sa.ForeignKeyConstraint(["contract_id"], ["contract.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "contract_id",
            "absence_start",
            "absence_end",
            name="uq_paid_leave_absence_period",
        ),
    )


def downgrade() -> None:
    op.drop_table("paid_leave_absence")
    op.drop_table("paid_leave_period_settings")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(name="paidleavetreatment").drop(bind, checkfirst=True)
        sa.Enum(name="paidleavebasismode").drop(bind, checkfirst=True)
