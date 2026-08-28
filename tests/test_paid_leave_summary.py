from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from monassmat import crud
from monassmat.app import (
    _automatic_paid_leave_acquisition,
    build_paid_leave_period_summary,
)
from monassmat.models import (
    Base,
    Child,
    Contract,
    ContractYearMode,
    PaidLeaveBasisMode,
    PaidLeaveTreatment,
    Workday,
    WorkdayKind,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


def create_contract(
    db: Session,
    *,
    start_date: date,
    end_date: date | None = None,
) -> Contract:
    child = Child(name="Emma", birth_date=date(2020, 1, 1))
    db.add(child)
    db.flush()
    contract = Contract(
        child_id=child.id,
        start_date=start_date,
        end_date=end_date,
        hours_per_week=40.0,
        weeks_per_year=52.0,
        year_mode=ContractYearMode.COMPLETE,
        hourly_rate=5.0,
        monday_hours=8.0,
        tuesday_hours=8.0,
        wednesday_hours=8.0,
        thursday_hours=8.0,
        friday_hours=8.0,
        saturday_hours=0.0,
        sunday_hours=0.0,
        days_per_week=5,
    )
    db.add(contract)
    db.flush()
    return contract


def test_summary_requires_calendar_leave_to_be_allocated(db):
    contract = create_contract(db, start_date=date(2024, 6, 1))
    crud.upsert_paid_leave_period_settings(
        db,
        contract_id=contract.id,
        period_start=date(2024, 6, 1),
        basis_mode=PaidLeaveBasisMode.MONTHS,
        worked_months=12,
        worked_weeks=None,
        worked_days=0,
        scheduled_days_per_week=None,
        dependent_children=0,
        employee_under_21=False,
        history_confirmed=True,
        additional_days=0,
        additional_days_reason=None,
        note=None,
    )
    db.add(
        Workday(
            contract_id=contract.id,
            date=date(2025, 5, 30),
            hours=0.0,
            kind=WorkdayKind.ASSMAT_LEAVE,
        )
    )
    db.commit()

    incomplete = build_paid_leave_period_summary(
        db,
        contract=contract,
        period_start=date(2024, 6, 1),
    )
    assert incomplete["status"] == "incomplete"
    assert "ne sont rattachées" in incomplete["leave_blockers"][0]

    crud.create_paid_leave_absence(
        db,
        contract_id=contract.id,
        reference_period_start=date(2024, 6, 1),
        absence_start=date(2025, 5, 30),
        absence_end=date(2025, 5, 30),
        treatment=PaidLeaveTreatment.ACQUIRED,
        regularized_days=0,
        note=None,
    )
    db.commit()

    complete = build_paid_leave_period_summary(
        db,
        contract=contract,
        period_start=date(2024, 6, 1),
    )
    assert complete["status"] == "reliable"
    assert complete["balance"].remaining_days == 28


def test_automatic_acquisition_blocks_ambiguous_absence(db):
    contract = create_contract(
        db,
        start_date=date(2024, 6, 3),
        end_date=date(2024, 6, 3),
    )
    db.add(
        Workday(
            contract_id=contract.id,
            date=date(2024, 6, 3),
            hours=0.0,
            kind=WorkdayKind.ABSENCE,
        )
    )
    db.commit()

    result = _automatic_paid_leave_acquisition(
        db,
        contract=contract,
        period_start=date(2024, 6, 1),
        period_end=date(2025, 5, 31),
        absences=[],
    )

    assert result["base_days"] is None
    assert "statut générique" in result["blockers"][0]
