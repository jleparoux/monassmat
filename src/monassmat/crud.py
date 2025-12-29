from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Contract, Workday, WorkdayKind


def get_contract(db: Session, contract_id: int) -> Contract | None:
    return db.get(Contract, contract_id)


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
) -> Workday:
    stmt = select(Workday).where(Workday.contract_id == contract_id, Workday.date == day)
    existing = db.scalar(stmt)

    if existing:
        existing.hours = hours
        existing.kind = kind
        return existing

    wd = Workday(contract_id=contract_id, date=day, hours=hours, kind=kind)
    db.add(wd)
    return wd


def delete_workday(db: Session, *, contract_id: int, day: date) -> bool:
    stmt = select(Workday).where(Workday.contract_id == contract_id, Workday.date == day)
    existing = db.scalar(stmt)
    if not existing:
        return False

    db.delete(existing)
    return True
