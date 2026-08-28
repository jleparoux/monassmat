from __future__ import annotations

from datetime import date, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    Child,
    Contract,
    ContractSettingsSnapshot,
    ContractWeekSchedule,
    ContractYearMode,
    MonthlyDeclaration,
    PaidLeave,
    PaidLeaveAbsence,
    PaidLeaveBasisMode,
    PaidLeaveMethod,
    PaidLeavePeriodSettings,
    PaidLeaveTreatment,
    Payment,
    PaymentKind,
    Workday,
    WorkdayKind,
)


def get_contract(db: Session, contract_id: int) -> Contract | None:
    return db.get(Contract, contract_id)


def list_contracts(db: Session) -> list[Contract]:
    stmt = select(Contract).order_by(Contract.id.asc())
    return list(db.scalars(stmt).all())


def list_settings_snapshots(
    db: Session, contract_id: int
) -> list[ContractSettingsSnapshot]:
    stmt = (
        select(ContractSettingsSnapshot)
        .where(ContractSettingsSnapshot.contract_id == contract_id)
        .order_by(ContractSettingsSnapshot.valid_from.asc())
    )
    return list(db.scalars(stmt).all())


def upsert_settings_snapshot(
    db: Session,
    *,
    contract_id: int,
    valid_from: date,
    hours_per_week: float,
    weeks_per_year: float,
    year_mode: ContractYearMode,
    hourly_rate: float,
    days_per_week: int | None,
    monday_hours: float | None,
    tuesday_hours: float | None,
    wednesday_hours: float | None,
    thursday_hours: float | None,
    friday_hours: float | None,
    saturday_hours: float | None,
    sunday_hours: float | None,
    majoration_threshold: float | None,
    majoration_rate: float | None,
    fee_meal_amount: float | None,
    fee_maintenance_amount: float | None,
    salary_net_ceiling: float | None,
    complementary_hourly_rate: float | None = None,
) -> ContractSettingsSnapshot:
    stmt = select(ContractSettingsSnapshot).where(
        ContractSettingsSnapshot.contract_id == contract_id,
        ContractSettingsSnapshot.valid_from == valid_from,
    )
    existing = db.scalar(stmt)
    if existing:
        existing.hours_per_week = hours_per_week
        existing.weeks_per_year = weeks_per_year
        existing.year_mode = year_mode
        existing.hourly_rate = hourly_rate
        existing.complementary_hourly_rate = complementary_hourly_rate
        existing.days_per_week = days_per_week
        existing.monday_hours = monday_hours
        existing.tuesday_hours = tuesday_hours
        existing.wednesday_hours = wednesday_hours
        existing.thursday_hours = thursday_hours
        existing.friday_hours = friday_hours
        existing.saturday_hours = saturday_hours
        existing.sunday_hours = sunday_hours
        existing.majoration_threshold = majoration_threshold
        existing.majoration_rate = majoration_rate
        existing.fee_meal_amount = fee_meal_amount
        existing.fee_maintenance_amount = fee_maintenance_amount
        existing.salary_net_ceiling = salary_net_ceiling
        return existing

    snapshot = ContractSettingsSnapshot(
        contract_id=contract_id,
        valid_from=valid_from,
        hours_per_week=hours_per_week,
        weeks_per_year=weeks_per_year,
        year_mode=year_mode,
        hourly_rate=hourly_rate,
        complementary_hourly_rate=complementary_hourly_rate,
        days_per_week=days_per_week,
        monday_hours=monday_hours,
        tuesday_hours=tuesday_hours,
        wednesday_hours=wednesday_hours,
        thursday_hours=thursday_hours,
        friday_hours=friday_hours,
        saturday_hours=saturday_hours,
        sunday_hours=sunday_hours,
        majoration_threshold=majoration_threshold,
        majoration_rate=majoration_rate,
        fee_meal_amount=fee_meal_amount,
        fee_maintenance_amount=fee_maintenance_amount,
        salary_net_ceiling=salary_net_ceiling,
    )
    db.add(snapshot)
    return snapshot


def get_settings_snapshot(
    db: Session, *, contract_id: int, valid_from: date
) -> ContractSettingsSnapshot | None:
    stmt = select(ContractSettingsSnapshot).where(
        ContractSettingsSnapshot.contract_id == contract_id,
        ContractSettingsSnapshot.valid_from == valid_from,
    )
    return db.scalar(stmt)


def delete_settings_snapshot(
    db: Session, *, contract_id: int, valid_from: date
) -> bool:
    snapshot = get_settings_snapshot(
        db, contract_id=contract_id, valid_from=valid_from
    )
    if not snapshot:
        return False
    db.delete(snapshot)
    return True


def list_week_schedules(
    db: Session,
    contract_id: int,
    start: date,
    end: date,
) -> list[ContractWeekSchedule]:
    stmt = (
        select(ContractWeekSchedule)
        .where(ContractWeekSchedule.contract_id == contract_id)
        .where(ContractWeekSchedule.week_start >= start)
        .where(ContractWeekSchedule.week_start <= end)
        .order_by(ContractWeekSchedule.week_start.asc())
    )
    return list(db.scalars(stmt).all())


def set_week_schedules(
    db: Session,
    *,
    contract_id: int,
    statuses: dict[date, bool],
) -> list[ContractWeekSchedule]:
    if not statuses:
        return []
    existing = {
        item.week_start: item
        for item in list_week_schedules(
            db,
            contract_id,
            min(statuses),
            max(statuses),
        )
    }
    result = []
    for week_start, planned in sorted(statuses.items()):
        item = existing.get(week_start)
        if item:
            item.planned = planned
        else:
            item = ContractWeekSchedule(
                contract_id=contract_id,
                week_start=week_start,
                planned=planned,
            )
            db.add(item)
        result.append(item)
    return result


def list_workdays(db: Session, contract_id: int, start: date, end: date) -> list[Workday]:
    stmt = (
        select(Workday)
        .where(Workday.contract_id == contract_id)
        .where(Workday.date >= start)
        .where(Workday.date <= end)
        .order_by(Workday.date.asc())
    )
    return list(db.scalars(stmt).all())


def upsert_workday(
    db: Session,
    *,
    contract_id: int,
    day: date,
    hours: float,
    kind: WorkdayKind,
    start_time: time | None = None,
    end_time: time | None = None,
    fee_meal: bool = False,
    fee_maintenance: bool = False,
) -> Workday:
    stmt = select(Workday).where(Workday.contract_id == contract_id, Workday.date == day)
    existing = db.scalar(stmt)

    if existing:
        existing.hours = hours
        existing.kind = kind
        existing.start_time = start_time
        existing.end_time = end_time
        existing.fee_meal = fee_meal
        existing.fee_maintenance = fee_maintenance
        return existing

    wd = Workday(
        contract_id=contract_id,
        date=day,
        hours=hours,
        kind=kind,
        start_time=start_time,
        end_time=end_time,
        fee_meal=fee_meal,
        fee_maintenance=fee_maintenance,
    )
    db.add(wd)
    return wd


def delete_workday(db: Session, *, contract_id: int, day: date) -> bool:
    stmt = select(Workday).where(Workday.contract_id == contract_id, Workday.date == day)
    existing = db.scalar(stmt)
    if not existing:
        return False

    db.delete(existing)
    return True


def list_children(db: Session) -> list[Child]:
    stmt = select(Child).order_by(Child.name.asc())
    return list(db.scalars(stmt).all())


def get_child(db: Session, child_id: int) -> Child | None:
    return db.get(Child, child_id)


def create_child(db: Session, *, name: str, birth_date: date) -> Child:
    child = Child(name=name, birth_date=birth_date)
    db.add(child)
    return child


def update_child(
    db: Session, *, child_id: int, name: str, birth_date: date
) -> Child | None:
    child = get_child(db, child_id)
    if not child:
        return None
    child.name = name
    child.birth_date = birth_date
    return child


def list_paid_leaves(db: Session, contract_id: int) -> list[PaidLeave]:
    stmt = (
        select(PaidLeave)
        .where(PaidLeave.contract_id == contract_id)
        .order_by(PaidLeave.period_start.desc())
    )
    return list(db.scalars(stmt).all())


def get_paid_leave(
    db: Session, *, contract_id: int, period_start: date, period_end: date
) -> PaidLeave | None:
    stmt = select(PaidLeave).where(
        PaidLeave.contract_id == contract_id,
        PaidLeave.period_start == period_start,
        PaidLeave.period_end == period_end,
    )
    return db.scalar(stmt)


def upsert_paid_leave(
    db: Session,
    *,
    contract_id: int,
    period_start: date,
    period_end: date,
    days_acquired: float,
    days_taken: float,
    method: PaidLeaveMethod,
    amount_paid: float | None,
) -> PaidLeave:
    existing = get_paid_leave(
        db, contract_id=contract_id, period_start=period_start, period_end=period_end
    )
    if existing:
        existing.days_acquired = days_acquired
        existing.days_taken = days_taken
        existing.method = method
        existing.amount_paid = amount_paid
        return existing
    pl = PaidLeave(
        contract_id=contract_id,
        period_start=period_start,
        period_end=period_end,
        days_acquired=days_acquired,
        days_taken=days_taken,
        method=method,
        amount_paid=amount_paid,
    )
    db.add(pl)
    return pl


def get_paid_leave_period_settings(
    db: Session,
    *,
    contract_id: int,
    period_start: date,
) -> PaidLeavePeriodSettings | None:
    stmt = select(PaidLeavePeriodSettings).where(
        PaidLeavePeriodSettings.contract_id == contract_id,
        PaidLeavePeriodSettings.period_start == period_start,
    )
    return db.scalar(stmt)


def upsert_paid_leave_period_settings(
    db: Session,
    *,
    contract_id: int,
    period_start: date,
    basis_mode: PaidLeaveBasisMode,
    worked_months: int | None,
    worked_weeks: int | None,
    worked_days: int,
    scheduled_days_per_week: int | None,
    dependent_children: int,
    employee_under_21: bool,
    history_confirmed: bool,
    additional_days: int,
    additional_days_reason: str | None,
    note: str | None,
) -> PaidLeavePeriodSettings:
    settings = get_paid_leave_period_settings(
        db,
        contract_id=contract_id,
        period_start=period_start,
    )
    if settings is None:
        settings = PaidLeavePeriodSettings(
            contract_id=contract_id,
            period_start=period_start,
        )
        db.add(settings)

    settings.basis_mode = basis_mode
    settings.worked_months = worked_months
    settings.worked_weeks = worked_weeks
    settings.worked_days = worked_days
    settings.scheduled_days_per_week = scheduled_days_per_week
    settings.dependent_children = dependent_children
    settings.employee_under_21 = employee_under_21
    settings.history_confirmed = history_confirmed
    settings.additional_days = additional_days
    settings.additional_days_reason = additional_days_reason
    settings.note = note
    return settings


def list_paid_leave_absences(
    db: Session,
    contract_id: int,
) -> list[PaidLeaveAbsence]:
    stmt = (
        select(PaidLeaveAbsence)
        .where(PaidLeaveAbsence.contract_id == contract_id)
        .order_by(PaidLeaveAbsence.absence_start.asc())
    )
    return list(db.scalars(stmt).all())


def create_paid_leave_absence(
    db: Session,
    *,
    contract_id: int,
    reference_period_start: date,
    absence_start: date,
    absence_end: date,
    treatment: PaidLeaveTreatment,
    regularized_days: int,
    note: str | None,
) -> PaidLeaveAbsence:
    absence = PaidLeaveAbsence(
        contract_id=contract_id,
        reference_period_start=reference_period_start,
        absence_start=absence_start,
        absence_end=absence_end,
        treatment=treatment,
        regularized_days=regularized_days,
        note=note,
    )
    db.add(absence)
    return absence


def delete_paid_leave_absence(
    db: Session,
    *,
    contract_id: int,
    absence_id: int,
) -> bool:
    absence = db.get(PaidLeaveAbsence, absence_id)
    if absence is None or absence.contract_id != contract_id:
        return False
    db.delete(absence)
    return True


def list_payments(db: Session, contract_id: int) -> list[Payment]:
    stmt = (
        select(Payment)
        .where(Payment.contract_id == contract_id)
        .order_by(Payment.paid_at.desc())
    )
    return list(db.scalars(stmt).all())


def create_payment(
    db: Session,
    *,
    contract_id: int,
    period_start: date,
    period_end: date,
    amount: float,
    paid_at: date,
    kind: PaymentKind,
) -> Payment:
    payment = Payment(
        contract_id=contract_id,
        period_start=period_start,
        period_end=period_end,
        amount=amount,
        paid_at=paid_at,
        kind=kind,
    )
    db.add(payment)
    return payment


def delete_payment(db: Session, payment_id: int) -> bool:
    payment = db.get(Payment, payment_id)
    if not payment:
        return False
    db.delete(payment)
    return True


def get_monthly_declaration(
    db: Session,
    *,
    contract_id: int,
    month: date,
) -> MonthlyDeclaration | None:
    stmt = select(MonthlyDeclaration).where(
        MonthlyDeclaration.contract_id == contract_id,
        MonthlyDeclaration.month == month.replace(day=1),
    )
    return db.scalar(stmt)


def upsert_monthly_declaration(
    db: Session,
    *,
    contract_id: int,
    month: date,
    declared_on: date,
) -> MonthlyDeclaration:
    normalized_month = month.replace(day=1)
    existing = get_monthly_declaration(
        db,
        contract_id=contract_id,
        month=normalized_month,
    )
    if existing:
        existing.declared_on = declared_on
        return existing

    declaration = MonthlyDeclaration(
        contract_id=contract_id,
        month=normalized_month,
        declared_on=declared_on,
    )
    db.add(declaration)
    return declaration


def delete_monthly_declaration(
    db: Session,
    *,
    contract_id: int,
    month: date,
) -> bool:
    declaration = get_monthly_declaration(
        db,
        contract_id=contract_id,
        month=month,
    )
    if not declaration:
        return False
    db.delete(declaration)
    return True
