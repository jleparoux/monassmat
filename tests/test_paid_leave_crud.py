from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from monassmat.models import Base, Child, Contract, PaidLeaveMethod
from monassmat import crud


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        child = Child(name="Emma", birth_date=date(2020, 1, 1))
        session.add(child)
        session.flush()
        contract = Contract(
            child_id=child.id,
            start_date=date(2024, 9, 1),
            end_date=None,
            hours_per_week=40.0,
            weeks_per_year=47.0,
            hourly_rate=5.0,
        )
        session.add(contract)
        session.commit()
        session.refresh(contract)
        yield session, contract.id
    Base.metadata.drop_all(engine)


def test_upsert_paid_leave_creates(db):
    session, contract_id = db
    pl = crud.upsert_paid_leave(
        session,
        contract_id=contract_id,
        period_start=date(2024, 6, 1),
        period_end=date(2025, 5, 31),
        days_acquired=30,
        days_taken=5,
        method=PaidLeaveMethod.MAINTIEN,
        amount_paid=None,
    )
    session.commit()
    assert pl.id is not None
    assert pl.days_acquired == 30


def test_upsert_paid_leave_updates(db):
    session, contract_id = db
    crud.upsert_paid_leave(
        session,
        contract_id=contract_id,
        period_start=date(2024, 6, 1),
        period_end=date(2025, 5, 31),
        days_acquired=30,
        days_taken=5,
        method=PaidLeaveMethod.MAINTIEN,
        amount_paid=None,
    )
    session.commit()
    pl = crud.upsert_paid_leave(
        session,
        contract_id=contract_id,
        period_start=date(2024, 6, 1),
        period_end=date(2025, 5, 31),
        days_acquired=30,
        days_taken=10,
        method=PaidLeaveMethod.MAINTIEN,
        amount_paid=500.0,
    )
    session.commit()
    assert pl.days_taken == 10
    assert pl.amount_paid == 500.0


def test_list_paid_leaves(db):
    session, contract_id = db
    crud.upsert_paid_leave(
        session,
        contract_id=contract_id,
        period_start=date(2024, 6, 1),
        period_end=date(2025, 5, 31),
        days_acquired=30,
        days_taken=0,
        method=PaidLeaveMethod.MAINTIEN,
        amount_paid=None,
    )
    session.commit()
    leaves = crud.list_paid_leaves(session, contract_id)
    assert len(leaves) == 1
