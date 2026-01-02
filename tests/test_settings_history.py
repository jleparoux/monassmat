from dataclasses import dataclass
from datetime import date

import pytest

from monassmat.app import summarize_period
from monassmat.calculations import ContractFacts, contract_monthly_hours
from monassmat.models import WorkdayKind


@dataclass
class DummyContract:
    start_date: date
    end_date: date | None
    hours_per_week: float
    weeks_per_year: float
    hourly_rate: float
    days_per_week: int | None
    majoration_threshold: float | None
    majoration_rate: float | None
    fee_meal_amount: float | None
    fee_maintenance_amount: float | None
    salary_net_ceiling: float | None


@dataclass
class DummyWorkday:
    date: date
    hours: float
    kind: WorkdayKind
    fee_meal: bool = False
    fee_maintenance: bool = False


@dataclass
class DummySnapshot:
    valid_from: date
    hours_per_week: float
    weeks_per_year: float
    hourly_rate: float
    days_per_week: int | None
    majoration_threshold: float | None
    majoration_rate: float | None
    fee_meal_amount: float | None
    fee_maintenance_amount: float | None
    salary_net_ceiling: float | None


def test_settings_history_affects_salary_and_fees():
    contract = DummyContract(
        start_date=date(2025, 1, 1),
        end_date=None,
        hours_per_week=40.0,
        weeks_per_year=52.0,
        hourly_rate=5.0,
        days_per_week=5,
        majoration_threshold=None,
        majoration_rate=None,
        fee_meal_amount=1.0,
        fee_maintenance_amount=2.0,
        salary_net_ceiling=None,
    )
    snapshots = [
        DummySnapshot(
            valid_from=date(2025, 1, 1),
            hours_per_week=40.0,
            weeks_per_year=52.0,
            hourly_rate=5.0,
            days_per_week=5,
            majoration_threshold=None,
            majoration_rate=None,
            fee_meal_amount=1.0,
            fee_maintenance_amount=2.0,
            salary_net_ceiling=None,
        ),
        DummySnapshot(
            valid_from=date(2025, 1, 15),
            hours_per_week=20.0,
            weeks_per_year=52.0,
            hourly_rate=6.0,
            days_per_week=5,
            majoration_threshold=None,
            majoration_rate=None,
            fee_meal_amount=1.5,
            fee_maintenance_amount=2.5,
            salary_net_ceiling=None,
        ),
    ]

    workdays = [
        DummyWorkday(date=date(2025, 1, 10), hours=8.0, kind=WorkdayKind.NORMAL, fee_meal=True),
        DummyWorkday(date=date(2025, 1, 20), hours=8.0, kind=WorkdayKind.NORMAL, fee_maintenance=True),
        DummyWorkday(date=date(2025, 1, 16), hours=0.0, kind=WorkdayKind.UNPAID_LEAVE),
    ]

    summary = summarize_period(
        contract,
        workdays,
        snapshots,
        start=date(2025, 1, 1),
        end=date(2025, 1, 31),
    )

    assert summary.salary_base == (8.0 * 5.0) + (8.0 * 6.0)
    assert summary.fee_meal_total == 1.0
    assert summary.fee_maintenance_total == 2.5
    assert summary.unpaid_leave_deduction == 1 * 4.0 * 6.0

    jan_days = 31
    first_span = 14
    second_span = 17
    theo_1 = contract_monthly_hours(
        ContractFacts(
            start_date=contract.start_date,
            end_date=contract.end_date,
            hours_per_week=40.0,
            weeks_per_year=52.0,
            hourly_rate=5.0,
        )
    )
    theo_2 = contract_monthly_hours(
        ContractFacts(
            start_date=contract.start_date,
            end_date=contract.end_date,
            hours_per_week=20.0,
            weeks_per_year=52.0,
            hourly_rate=6.0,
        )
    )
    expected_theo = (theo_1 / jan_days) * first_span + (theo_2 / jan_days) * second_span
    assert summary.monthly_hours_theoretical == pytest.approx(expected_theo)
