from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from monassmat import crud
from monassmat.models import (
    Base,
    Child,
    Contract,
    PaidLeaveBasisMode,
    PaidLeaveMethod,
    PaidLeaveTreatment,
)


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


def test_upsert_paid_leave_period_settings_updates_factual_basis(db):
    session, contract_id = db
    settings = crud.upsert_paid_leave_period_settings(
        session,
        contract_id=contract_id,
        period_start=date(2024, 6, 1),
        basis_mode=PaidLeaveBasisMode.MONTHS,
        worked_months=9,
        worked_weeks=None,
        worked_days=0,
        scheduled_days_per_week=None,
        dependent_children=2,
        employee_under_21=False,
        history_confirmed=False,
        additional_days=0,
        additional_days_reason=None,
        note="Décompte vérifié",
    )
    session.commit()

    assert settings.id is not None
    assert settings.worked_months == 9
    assert settings.dependent_children == 2

    updated = crud.upsert_paid_leave_period_settings(
        session,
        contract_id=contract_id,
        period_start=date(2024, 6, 1),
        basis_mode=PaidLeaveBasisMode.WEEKS,
        worked_months=None,
        worked_weeks=36,
        worked_days=2,
        scheduled_days_per_week=5,
        dependent_children=2,
        employee_under_21=False,
        history_confirmed=False,
        additional_days=1,
        additional_days_reason="Fractionnement validé",
        note=None,
    )
    session.commit()

    assert updated.id == settings.id
    assert updated.basis_mode == PaidLeaveBasisMode.WEEKS
    assert updated.worked_weeks == 36
    assert updated.additional_days_reason == "Fractionnement validé"


def test_create_list_and_delete_paid_leave_absence(db):
    session, contract_id = db
    absence = crud.create_paid_leave_absence(
        session,
        contract_id=contract_id,
        reference_period_start=date(2024, 6, 1),
        absence_start=date(2025, 5, 30),
        absence_end=date(2025, 5, 30),
        treatment=PaidLeaveTreatment.ADVANCE,
        regularized_days=2,
        note="Régularisé en mai",
    )
    session.commit()

    assert absence.id is not None
    assert crud.list_paid_leave_absences(session, contract_id) == [absence]
    assert crud.delete_paid_leave_absence(
        session,
        contract_id=contract_id,
        absence_id=absence.id,
    )
    session.commit()
    assert crud.list_paid_leave_absences(session, contract_id) == []
