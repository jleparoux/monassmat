from datetime import date, datetime, time
from enum import Enum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class WorkdayKind(str, Enum):
    NORMAL = "normal"
    ABSENCE = "absence"
    UNPAID_LEAVE = "unpaid_leave"
    HOLIDAY = "holiday"
    ASSMAT_LEAVE = "assmat_leave"


class PaymentKind(str, Enum):
    MONTHLY = "monthly"
    REGULARIZATION = "regularization"
    PAID_LEAVE = "paid_leave"
    CORRECTION = "correction"


class PaidLeaveMethod(str, Enum):
    MAINTIEN = "maintien"
    DIXIEME = "dixieme"


class PaidLeaveBasisMode(str, Enum):
    AUTO = "auto"
    MONTHS = "months"
    WEEKS = "weeks"


class PaidLeaveTreatment(str, Enum):
    ACQUIRED = "acquired"
    ADVANCE = "advance"
    UNPAID = "unpaid"


class ContractYearMode(str, Enum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Child(Base):
    __tablename__ = "child"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    birth_date: Mapped[date] = mapped_column(Date, nullable=False)

    contracts: Mapped[list["Contract"]] = relationship(
        back_populates="child",
        cascade="all, delete-orphan",
    )


class Contract(Base):
    __tablename__ = "contract"

    id: Mapped[int] = mapped_column(primary_key=True)
    child_id: Mapped[int] = mapped_column(ForeignKey("child.id"), nullable=False)
    name: Mapped[str | None] = mapped_column(String(120))

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)

    hours_per_week: Mapped[float] = mapped_column(Float, nullable=False)
    weeks_per_year: Mapped[float] = mapped_column(Float, nullable=False)
    year_mode: Mapped[ContractYearMode] = mapped_column(
        SQLEnum(
            ContractYearMode,
            name="contract_year_mode",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=ContractYearMode.COMPLETE,
    )
    hourly_rate: Mapped[float] = mapped_column(Float, nullable=False)
    complementary_hourly_rate: Mapped[float | None] = mapped_column(Float)
    days_per_week: Mapped[int | None] = mapped_column(Integer)
    monday_hours: Mapped[float | None] = mapped_column(Float)
    tuesday_hours: Mapped[float | None] = mapped_column(Float)
    wednesday_hours: Mapped[float | None] = mapped_column(Float)
    thursday_hours: Mapped[float | None] = mapped_column(Float)
    friday_hours: Mapped[float | None] = mapped_column(Float)
    saturday_hours: Mapped[float | None] = mapped_column(Float)
    sunday_hours: Mapped[float | None] = mapped_column(Float)
    majoration_threshold: Mapped[float | None] = mapped_column(Float)
    majoration_rate: Mapped[float | None] = mapped_column(Float)
    fee_meal_amount: Mapped[float | None] = mapped_column(Float)
    fee_maintenance_amount: Mapped[float | None] = mapped_column(Float)
    salary_net_ceiling: Mapped[float | None] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    child: Mapped["Child"] = relationship(back_populates="contracts")

    workdays: Mapped[list["Workday"]] = relationship(
        back_populates="contract",
        cascade="all, delete-orphan",
    )

    payments: Mapped[list["Payment"]] = relationship(
        back_populates="contract",
        cascade="all, delete-orphan",
    )

    monthly_declarations: Mapped[list["MonthlyDeclaration"]] = relationship(
        back_populates="contract",
        cascade="all, delete-orphan",
    )

    paid_leaves: Mapped[list["PaidLeave"]] = relationship(
        back_populates="contract",
        cascade="all, delete-orphan",
    )

    paid_leave_period_settings: Mapped[list["PaidLeavePeriodSettings"]] = relationship(
        back_populates="contract",
        cascade="all, delete-orphan",
    )

    paid_leave_absences: Mapped[list["PaidLeaveAbsence"]] = relationship(
        back_populates="contract",
        cascade="all, delete-orphan",
    )

    rate_snapshots: Mapped[list["RateSnapshot"]] = relationship(
        back_populates="contract",
        cascade="all, delete-orphan",
    )

    settings_snapshots: Mapped[list["ContractSettingsSnapshot"]] = relationship(
        back_populates="contract",
        cascade="all, delete-orphan",
    )

    week_schedules: Mapped[list["ContractWeekSchedule"]] = relationship(
        back_populates="contract",
        cascade="all, delete-orphan",
    )


class Workday(Base):
    __tablename__ = "workday"
    __table_args__ = (
        UniqueConstraint("contract_id", "date", name="uq_workday_contract_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(
        ForeignKey("contract.id"), nullable=False
    )

    date: Mapped[date] = mapped_column(Date, nullable=False)
    hours: Mapped[float] = mapped_column(Float, nullable=False)

    start_time: Mapped[time | None] = mapped_column(Time)
    end_time: Mapped[time | None] = mapped_column(Time)

    fee_meal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fee_maintenance: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    kind: Mapped[WorkdayKind] = mapped_column(
        SQLEnum(WorkdayKind), nullable=False
    )

    contract: Mapped["Contract"] = relationship(back_populates="workdays")


class RateSnapshot(Base):
    __tablename__ = "rate_snapshot"

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(
        ForeignKey("contract.id"), nullable=False
    )

    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    hourly_rate: Mapped[float] = mapped_column(Float, nullable=False)

    contract: Mapped["Contract"] = relationship(back_populates="rate_snapshots")


class ContractSettingsSnapshot(Base):
    __tablename__ = "contract_settings_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "contract_id",
            "valid_from",
            name="uq_contract_settings_snapshot",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(
        ForeignKey("contract.id"), nullable=False
    )

    valid_from: Mapped[date] = mapped_column(Date, nullable=False)

    hours_per_week: Mapped[float] = mapped_column(Float, nullable=False)
    weeks_per_year: Mapped[float] = mapped_column(Float, nullable=False)
    year_mode: Mapped[ContractYearMode] = mapped_column(
        SQLEnum(
            ContractYearMode,
            name="contract_year_mode",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=ContractYearMode.COMPLETE,
    )
    hourly_rate: Mapped[float] = mapped_column(Float, nullable=False)
    complementary_hourly_rate: Mapped[float | None] = mapped_column(Float)
    days_per_week: Mapped[int | None] = mapped_column(Integer)
    monday_hours: Mapped[float | None] = mapped_column(Float)
    tuesday_hours: Mapped[float | None] = mapped_column(Float)
    wednesday_hours: Mapped[float | None] = mapped_column(Float)
    thursday_hours: Mapped[float | None] = mapped_column(Float)
    friday_hours: Mapped[float | None] = mapped_column(Float)
    saturday_hours: Mapped[float | None] = mapped_column(Float)
    sunday_hours: Mapped[float | None] = mapped_column(Float)
    majoration_threshold: Mapped[float | None] = mapped_column(Float)
    majoration_rate: Mapped[float | None] = mapped_column(Float)
    fee_meal_amount: Mapped[float | None] = mapped_column(Float)
    fee_maintenance_amount: Mapped[float | None] = mapped_column(Float)
    salary_net_ceiling: Mapped[float | None] = mapped_column(Float)

    contract: Mapped["Contract"] = relationship(back_populates="settings_snapshots")


class ContractWeekSchedule(Base):
    __tablename__ = "contract_week_schedule"
    __table_args__ = (
        UniqueConstraint(
            "contract_id",
            "week_start",
            name="uq_contract_week_schedule",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(
        ForeignKey("contract.id"),
        nullable=False,
    )
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    planned: Mapped[bool] = mapped_column(Boolean, nullable=False)

    contract: Mapped["Contract"] = relationship(back_populates="week_schedules")


class PaidLeave(Base):
    __tablename__ = "paid_leave"
    __table_args__ = (
        UniqueConstraint(
            "contract_id",
            "period_start",
            "period_end",
            name="uq_paid_leave_period",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(
        ForeignKey("contract.id"), nullable=False
    )

    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)

    days_acquired: Mapped[float] = mapped_column(Float, nullable=False)
    days_taken: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    method: Mapped[PaidLeaveMethod] = mapped_column(
        SQLEnum(PaidLeaveMethod), nullable=False
    )

    amount_paid: Mapped[float | None] = mapped_column(Float)

    contract: Mapped["Contract"] = relationship(back_populates="paid_leaves")


class PaidLeavePeriodSettings(Base):
    __tablename__ = "paid_leave_period_settings"
    __table_args__ = (
        UniqueConstraint(
            "contract_id",
            "period_start",
            name="uq_paid_leave_period_settings",
        ),
        CheckConstraint("dependent_children >= 0", name="ck_paid_leave_children"),
        CheckConstraint("additional_days >= 0", name="ck_paid_leave_additional_days"),
        CheckConstraint(
            "worked_months IS NULL OR (worked_months >= 0 AND worked_months <= 12)",
            name="ck_paid_leave_worked_months",
        ),
        CheckConstraint(
            "worked_weeks IS NULL OR worked_weeks >= 0",
            name="ck_paid_leave_worked_weeks",
        ),
        CheckConstraint("worked_days >= 0", name="ck_paid_leave_worked_days"),
        CheckConstraint(
            "scheduled_days_per_week IS NULL OR "
            "(scheduled_days_per_week >= 1 AND scheduled_days_per_week <= 7)",
            name="ck_paid_leave_scheduled_days",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(
        ForeignKey("contract.id"), nullable=False
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    basis_mode: Mapped[PaidLeaveBasisMode] = mapped_column(
        SQLEnum(
            PaidLeaveBasisMode,
            name="paidleavebasismode",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=PaidLeaveBasisMode.AUTO,
    )
    worked_months: Mapped[int | None] = mapped_column(Integer)
    worked_weeks: Mapped[int | None] = mapped_column(Integer)
    worked_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scheduled_days_per_week: Mapped[int | None] = mapped_column(Integer)
    dependent_children: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    employee_under_21: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    history_confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    additional_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    additional_days_reason: Mapped[str | None] = mapped_column(String(240))
    note: Mapped[str | None] = mapped_column(String(500))

    contract: Mapped["Contract"] = relationship(
        back_populates="paid_leave_period_settings"
    )


class PaidLeaveAbsence(Base):
    __tablename__ = "paid_leave_absence"
    __table_args__ = (
        UniqueConstraint(
            "contract_id",
            "absence_start",
            "absence_end",
            name="uq_paid_leave_absence_period",
        ),
        CheckConstraint(
            "absence_end >= absence_start",
            name="ck_paid_leave_absence_dates",
        ),
        CheckConstraint(
            "regularized_days >= 0",
            name="ck_paid_leave_regularized_days",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(
        ForeignKey("contract.id"), nullable=False
    )
    reference_period_start: Mapped[date] = mapped_column(Date, nullable=False)
    absence_start: Mapped[date] = mapped_column(Date, nullable=False)
    absence_end: Mapped[date] = mapped_column(Date, nullable=False)
    treatment: Mapped[PaidLeaveTreatment] = mapped_column(
        SQLEnum(
            PaidLeaveTreatment,
            name="paidleavetreatment",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    regularized_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    note: Mapped[str | None] = mapped_column(String(500))

    contract: Mapped["Contract"] = relationship(
        back_populates="paid_leave_absences"
    )


class Payment(Base):
    __tablename__ = "payment"

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(
        ForeignKey("contract.id"), nullable=False
    )

    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)

    amount: Mapped[float] = mapped_column(Float, nullable=False)
    paid_at: Mapped[date] = mapped_column(Date, nullable=False)

    kind: Mapped[PaymentKind] = mapped_column(
        SQLEnum(PaymentKind), nullable=False
    )

    contract: Mapped["Contract"] = relationship(back_populates="payments")


class MonthlyDeclaration(Base):
    __tablename__ = "monthly_declaration"
    __table_args__ = (
        UniqueConstraint(
            "contract_id",
            "month",
            name="uq_monthly_declaration_contract_month",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(
        ForeignKey("contract.id"), nullable=False
    )
    month: Mapped[date] = mapped_column(Date, nullable=False)
    declared_on: Mapped[date] = mapped_column(Date, nullable=False)

    contract: Mapped["Contract"] = relationship(
        back_populates="monthly_declarations"
    )
