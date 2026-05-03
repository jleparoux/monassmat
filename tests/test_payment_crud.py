from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from monassmat.models import Base, Child, Contract, PaymentKind
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


def test_create_payment(db):
    session, contract_id = db
    payment = crud.create_payment(
        session,
        contract_id=contract_id,
        period_start=date(2025, 1, 1),
        period_end=date(2025, 1, 31),
        amount=1200.0,
        paid_at=date(2025, 2, 1),
        kind=PaymentKind.MONTHLY,
    )
    session.commit()
    assert payment.id is not None
    assert payment.amount == 1200.0


def test_list_payments_empty(db):
    session, contract_id = db
    assert crud.list_payments(session, contract_id) == []


def test_list_payments_ordered_desc(db):
    session, contract_id = db
    crud.create_payment(
        session,
        contract_id=contract_id,
        period_start=date(2025, 1, 1),
        period_end=date(2025, 1, 31),
        amount=1000.0,
        paid_at=date(2025, 2, 1),
        kind=PaymentKind.MONTHLY,
    )
    crud.create_payment(
        session,
        contract_id=contract_id,
        period_start=date(2025, 2, 1),
        period_end=date(2025, 2, 28),
        amount=1100.0,
        paid_at=date(2025, 3, 1),
        kind=PaymentKind.MONTHLY,
    )
    session.commit()
    payments = crud.list_payments(session, contract_id)
    assert payments[0].paid_at == date(2025, 3, 1)


def test_delete_payment(db):
    session, contract_id = db
    payment = crud.create_payment(
        session,
        contract_id=contract_id,
        period_start=date(2025, 1, 1),
        period_end=date(2025, 1, 31),
        amount=1000.0,
        paid_at=date(2025, 2, 1),
        kind=PaymentKind.MONTHLY,
    )
    session.commit()
    deleted = crud.delete_payment(session, payment.id)
    session.commit()
    assert deleted is True
    assert crud.list_payments(session, contract_id) == []


def test_delete_payment_not_found(db):
    session, _ = db
    assert crud.delete_payment(session, 999) is False
