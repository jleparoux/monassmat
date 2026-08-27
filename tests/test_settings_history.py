from dataclasses import dataclass
from datetime import date

import pytest

from monassmat.app import (
    snapshot_from_contract,
    snapshot_from_row,
    summarize_period,
    weeks_overlapping_year,
)
from monassmat.calculations import ContractFacts, contract_monthly_hours
from monassmat.models import ContractYearMode, WorkdayKind


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
    year_mode: ContractYearMode = ContractYearMode.COMPLETE
    monday_hours: float | None = None
    tuesday_hours: float | None = None
    wednesday_hours: float | None = None
    thursday_hours: float | None = None
    friday_hours: float | None = None
    saturday_hours: float | None = None
    sunday_hours: float | None = None


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
    year_mode: ContractYearMode = ContractYearMode.COMPLETE
    monday_hours: float | None = None
    tuesday_hours: float | None = None
    wednesday_hours: float | None = None
    thursday_hours: float | None = None
    friday_hours: float | None = None
    saturday_hours: float | None = None
    sunday_hours: float | None = None


def test_weeks_overlapping_year_include_boundary_weeks():
    weeks = weeks_overlapping_year(2025)

    assert weeks[0] == date(2024, 12, 30)
    assert weeks[-1] == date(2025, 12, 29)
    assert len(weeks) == 53


def test_schedule_is_kept_in_contract_and_snapshot_settings():
    contract = DummyContract(
        start_date=date(2025, 1, 1),
        end_date=None,
        hours_per_week=40.0,
        weeks_per_year=52.0,
        hourly_rate=5.0,
        days_per_week=5,
        majoration_threshold=None,
        majoration_rate=None,
        fee_meal_amount=None,
        fee_maintenance_amount=None,
        salary_net_ceiling=None,
        monday_hours=8.0,
        tuesday_hours=8.0,
        wednesday_hours=8.0,
        thursday_hours=8.0,
        friday_hours=8.0,
        saturday_hours=0.0,
        sunday_hours=0.0,
    )
    snapshot = DummySnapshot(
        valid_from=date(2025, 1, 1),
        hours_per_week=35.0,
        weeks_per_year=52.0,
        hourly_rate=5.0,
        days_per_week=5,
        majoration_threshold=None,
        majoration_rate=None,
        fee_meal_amount=None,
        fee_maintenance_amount=None,
        salary_net_ceiling=None,
        monday_hours=7.0,
        tuesday_hours=7.0,
        wednesday_hours=7.0,
        thursday_hours=7.0,
        friday_hours=7.0,
        saturday_hours=0.0,
        sunday_hours=0.0,
    )

    contract_settings = snapshot_from_contract(contract, date(2025, 1, 1))
    assert contract_settings["monday_hours"] == 8.0
    assert contract_settings["sunday_hours"] == 0.0
    assert snapshot_from_row(snapshot)["monday_hours"] == 7.0
    assert snapshot_from_row(snapshot)["sunday_hours"] == 0.0


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
        year_mode=ContractYearMode.COMPLETE,
    )
    snapshots = [
        DummySnapshot(
            valid_from=date(2025, 1, 1),
            hours_per_week=40.0,
            weeks_per_year=52.0,
            year_mode=ContractYearMode.COMPLETE,
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
            year_mode=ContractYearMode.COMPLETE,
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
    assert summary.unpaid_leave_deduction == 0.0
    assert summary.absence_deduction_reliable is False

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


def test_52_week_absence_deduction_uses_exact_month_schedule():
    contract = DummyContract(
        start_date=date(2025, 1, 1),
        end_date=None,
        hours_per_week=40.0,
        weeks_per_year=52.0,
        hourly_rate=5.0,
        days_per_week=None,
        majoration_threshold=None,
        majoration_rate=None,
        fee_meal_amount=None,
        fee_maintenance_amount=None,
        salary_net_ceiling=None,
        monday_hours=8.0,
        tuesday_hours=8.0,
        wednesday_hours=8.0,
        thursday_hours=8.0,
        friday_hours=8.0,
        saturday_hours=0.0,
        sunday_hours=0.0,
    )
    workdays = [
        DummyWorkday(
            date=date(2025, 1, 6),
            hours=0.0,
            kind=WorkdayKind.UNPAID_LEAVE,
        )
    ]

    summary = summarize_period(
        contract,
        workdays,
        [],
        start=date(2025, 1, 1),
        end=date(2025, 1, 31),
    )

    monthly_salary = 40.0 * 52.0 / 12.0 * 5.0
    january_2025_scheduled_hours = 23 * 8.0
    assert summary.unpaid_leave_deduction == pytest.approx(
        monthly_salary * 8.0 / january_2025_scheduled_hours
    )
    assert summary.absence_deduction_reliable is True


def test_46_week_absence_counts_non_care_weeks_in_month_denominator():
    contract = DummyContract(
        start_date=date(2025, 1, 1),
        end_date=None,
        hours_per_week=40.0,
        weeks_per_year=44.0,
        hourly_rate=5.0,
        days_per_week=None,
        majoration_threshold=None,
        majoration_rate=None,
        fee_meal_amount=None,
        fee_maintenance_amount=None,
        salary_net_ceiling=None,
        year_mode=ContractYearMode.INCOMPLETE,
        monday_hours=8.0,
        tuesday_hours=8.0,
        wednesday_hours=8.0,
        thursday_hours=8.0,
        friday_hours=8.0,
        saturday_hours=0.0,
        sunday_hours=0.0,
    )
    workdays = [
        DummyWorkday(
            date=date(2025, 1, 6),
            hours=0.0,
            kind=WorkdayKind.UNPAID_LEAVE,
        )
    ]

    summary = summarize_period(
        contract,
        workdays,
        [],
        start=date(2025, 1, 1),
        end=date(2025, 1, 31),
    )

    monthly_salary = 40.0 * 44.0 / 12.0 * 5.0
    assert summary.unpaid_leave_deduction == pytest.approx(monthly_salary / 23.0)
    assert summary.absence_deduction_reliable is True
    assert "jours habituels" in summary.absence_deduction_message


def test_weekly_hours_are_classified_across_workdays():
    contract = DummyContract(
        start_date=date(2025, 1, 1),
        end_date=None,
        hours_per_week=32.0,
        weeks_per_year=52.0,
        hourly_rate=5.0,
        days_per_week=None,
        majoration_threshold=None,
        majoration_rate=1.25,
        fee_meal_amount=None,
        fee_maintenance_amount=None,
        salary_net_ceiling=None,
        monday_hours=6.4,
        tuesday_hours=6.4,
        wednesday_hours=6.4,
        thursday_hours=6.4,
        friday_hours=6.4,
        saturday_hours=0.0,
        sunday_hours=0.0,
    )
    workdays = [
        DummyWorkday(day, 10.0, WorkdayKind.NORMAL)
        for day in (
            date(2025, 1, 6),
            date(2025, 1, 7),
            date(2025, 1, 8),
            date(2025, 1, 9),
            date(2025, 1, 10),
        )
    ]

    summary = summarize_period(
        contract,
        workdays,
        [],
        start=date(2025, 1, 1),
        end=date(2025, 1, 31),
    )

    assert summary.hours_normal == 32.0
    assert summary.hours_complementary == 13.0
    assert summary.hours_majorated == 5.0
    assert summary.salary_base == 50.0 * 5.0
    assert summary.salary_majoration == 5.0 * 5.0 * 0.25
    assert summary.majoration_rate_missing is False

    contract.majoration_rate = None
    summary_without_rate = summarize_period(
        contract,
        workdays,
        [],
        start=date(2025, 1, 1),
        end=date(2025, 1, 31),
    )
    assert summary_without_rate.salary_majoration == 0.0
    assert summary_without_rate.majoration_rate_missing is True


def test_weekly_classification_uses_days_before_month_boundary():
    contract = DummyContract(
        start_date=date(2024, 12, 1),
        end_date=None,
        hours_per_week=32.0,
        weeks_per_year=52.0,
        hourly_rate=5.0,
        days_per_week=None,
        majoration_threshold=None,
        majoration_rate=1.25,
        fee_meal_amount=None,
        fee_maintenance_amount=None,
        salary_net_ceiling=None,
        monday_hours=6.4,
        tuesday_hours=6.4,
        wednesday_hours=6.4,
        thursday_hours=6.4,
        friday_hours=6.4,
        saturday_hours=0.0,
        sunday_hours=0.0,
    )
    workdays = [
        DummyWorkday(day, 10.0, WorkdayKind.NORMAL)
        for day in (
            date(2024, 12, 30),
            date(2024, 12, 31),
            date(2025, 1, 1),
            date(2025, 1, 2),
            date(2025, 1, 3),
        )
    ]

    january = summarize_period(
        contract,
        workdays,
        [],
        start=date(2025, 1, 1),
        end=date(2025, 1, 31),
    )

    assert january.hours_real == 30.0
    assert january.hours_normal == 12.0
    assert january.hours_complementary == 13.0
    assert january.hours_majorated == 5.0


def test_theoretical_salary_is_prorated_to_active_contract_days():
    contract = DummyContract(
        start_date=date(2025, 1, 15),
        end_date=None,
        hours_per_week=40.0,
        weeks_per_year=52.0,
        hourly_rate=5.0,
        days_per_week=None,
        majoration_threshold=None,
        majoration_rate=None,
        fee_meal_amount=None,
        fee_maintenance_amount=None,
        salary_net_ceiling=None,
        monday_hours=8.0,
        tuesday_hours=8.0,
        wednesday_hours=8.0,
        thursday_hours=8.0,
        friday_hours=8.0,
        saturday_hours=0.0,
        sunday_hours=0.0,
    )

    summary = summarize_period(
        contract,
        [],
        [],
        start=date(2025, 1, 1),
        end=date(2025, 1, 31),
    )

    full_month_salary = 40.0 * 52.0 / 12.0 * 5.0
    assert summary.monthly_salary_theoretical == pytest.approx(
        full_month_salary * 17 / 31
    )
