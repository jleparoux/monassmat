from datetime import date, datetime, time
from enum import Enum

from sqlalchemy import Boolean, Date, DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import Float, ForeignKey, Integer, String, Time, UniqueConstraint
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

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)

    hours_per_week: Mapped[float] = mapped_column(Float, nullable=False)
    weeks_per_year: Mapped[float] = mapped_column(Float, nullable=False)
    hourly_rate: Mapped[float] = mapped_column(Float, nullable=False)
    days_per_week: Mapped[int | None] = mapped_column(Integer)
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

    paid_leaves: Mapped[list["PaidLeave"]] = relationship(
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
    hourly_rate: Mapped[float] = mapped_column(Float, nullable=False)
    days_per_week: Mapped[int | None] = mapped_column(Integer)
    majoration_threshold: Mapped[float | None] = mapped_column(Float)
    majoration_rate: Mapped[float | None] = mapped_column(Float)
    fee_meal_amount: Mapped[float | None] = mapped_column(Float)
    fee_maintenance_amount: Mapped[float | None] = mapped_column(Float)
    salary_net_ceiling: Mapped[float | None] = mapped_column(Float)

    contract: Mapped["Contract"] = relationship(back_populates="settings_snapshots")


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
