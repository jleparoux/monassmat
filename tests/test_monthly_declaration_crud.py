from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from monassmat import crud
from monassmat.models import Base, Child, Contract


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
        yield session, contract.id
    Base.metadata.drop_all(engine)


def test_upsert_monthly_declaration_normalizes_month_and_updates_date(db):
    session, contract_id = db
    declaration = crud.upsert_monthly_declaration(
        session,
        contract_id=contract_id,
        month=date(2026, 8, 27),
        declared_on=date(2026, 8, 28),
    )
    session.commit()

    assert declaration.month == date(2026, 8, 1)
    assert (
        crud.get_monthly_declaration(
            session,
            contract_id=contract_id,
            month=date(2026, 8, 15),
        )
        == declaration
    )

    updated = crud.upsert_monthly_declaration(
        session,
        contract_id=contract_id,
        month=date(2026, 8, 1),
        declared_on=date(2026, 8, 29),
    )
    session.commit()

    assert updated.id == declaration.id
    assert updated.declared_on == date(2026, 8, 29)


def test_delete_monthly_declaration(db):
    session, contract_id = db
    crud.upsert_monthly_declaration(
        session,
        contract_id=contract_id,
        month=date(2026, 7, 1),
        declared_on=date(2026, 8, 1),
    )
    session.commit()

    assert crud.delete_monthly_declaration(
        session,
        contract_id=contract_id,
        month=date(2026, 7, 20),
    )
    session.commit()
    assert (
        crud.get_monthly_declaration(
            session,
            contract_id=contract_id,
            month=date(2026, 7, 1),
        )
        is None
    )
