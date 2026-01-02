from __future__ import annotations

from datetime import date, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Contract, ContractSettingsSnapshot, Workday, WorkdayKind


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
    hourly_rate: float,
    days_per_week: int | None,
    majoration_threshold: float | None,
    majoration_rate: float | None,
    fee_meal_amount: float | None,
    fee_maintenance_amount: float | None,
    salary_net_ceiling: float | None,
) -> ContractSettingsSnapshot:
    stmt = select(ContractSettingsSnapshot).where(
        ContractSettingsSnapshot.contract_id == contract_id,
        ContractSettingsSnapshot.valid_from == valid_from,
    )
    existing = db.scalar(stmt)
    if existing:
        existing.hours_per_week = hours_per_week
        existing.weeks_per_year = weeks_per_year
        existing.hourly_rate = hourly_rate
        existing.days_per_week = days_per_week
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
        hourly_rate=hourly_rate,
        days_per_week=days_per_week,
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
