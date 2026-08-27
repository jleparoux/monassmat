from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from monassmat import crud
from monassmat.models import Base, Child, Contract, ContractYearMode


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
            start_date=date(2025, 1, 1),
            end_date=None,
            hours_per_week=40.0,
            weeks_per_year=44.0,
            year_mode=ContractYearMode.INCOMPLETE,
            hourly_rate=5.0,
        )
        session.add(contract)
        session.commit()
        yield session, contract.id
    Base.metadata.drop_all(engine)


def test_set_week_schedules_creates_explicit_facts(db):
    session, contract_id = db
    crud.set_week_schedules(
        session,
        contract_id=contract_id,
        statuses={
            date(2025, 1, 6): True,
            date(2025, 1, 13): False,
        },
    )
    session.commit()

    items = crud.list_week_schedules(
        session,
        contract_id,
        date(2025, 1, 1),
        date(2025, 1, 31),
    )
    assert [(item.week_start, item.planned) for item in items] == [
        (date(2025, 1, 6), True),
        (date(2025, 1, 13), False),
    ]


def test_set_week_schedules_updates_existing_fact(db):
    session, contract_id = db
    statuses = {date(2025, 1, 6): True}
    crud.set_week_schedules(session, contract_id=contract_id, statuses=statuses)
    session.commit()

    crud.set_week_schedules(
        session,
        contract_id=contract_id,
        statuses={date(2025, 1, 6): False},
    )
    session.commit()

    items = crud.list_week_schedules(
        session,
        contract_id,
        date(2025, 1, 6),
        date(2025, 1, 6),
    )
    assert len(items) == 1
    assert items[0].planned is False
