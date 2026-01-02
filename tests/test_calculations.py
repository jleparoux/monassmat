from datetime import date

import pytest
from monassmat.calculations import (
    ContractFacts,
    PaidLeaveMethod,
    Period,
    WorkdayFacts,
    WorkdayKind,
    contract_monthly_hours,
    contract_monthly_salary,
    hours_in_period,
    paid_leave_value,
    unpaid_leave_deduction,
    workday_totals,
)


def test_contract_monthly_hours():
    c = ContractFacts(
        start_date=date(2025, 1, 1),
        end_date=None,
        hours_per_week=40.0,
        weeks_per_year=45.0,
        hourly_rate=5.0,
    )
    assert contract_monthly_hours(c) == 40.0 * 45.0 / 12.0


def test_contract_monthly_salary():
    c = ContractFacts(
        start_date=date(2025, 1, 1),
        end_date=None,
        hours_per_week=40.0,
        weeks_per_year=45.0,
        hourly_rate=5.0,
    )
    assert contract_monthly_salary(c) == (40.0 * 45.0 / 12.0) * 5.0


def test_hours_in_period_default_normal_only():
    wds = [
        WorkdayFacts(day=date(2025, 1, 2), hours=8.0, kind=WorkdayKind.NORMAL),
        WorkdayFacts(day=date(2025, 1, 3), hours=8.0, kind=WorkdayKind.ABSENCE),
        WorkdayFacts(day=date(2025, 1, 4), hours=4.0, kind=WorkdayKind.NORMAL),
    ]
    p = Period(start=date(2025, 1, 1), end=date(2025, 1, 31))
    assert hours_in_period(wds, p) == 12.0


def test_paid_leave_value_maintien():
    amount = paid_leave_value(
        method=PaidLeaveMethod.MAINTIEN,
        days_taken=2.0,
        daily_reference_hours=8.0,
        hourly_rate=5.0,
    )
    assert amount == 2.0 * 8.0 * 5.0


def test_paid_leave_value_dixieme_requires_amount():
    with pytest.raises(ValueError):
        paid_leave_value(
            method=PaidLeaveMethod.DIXIEME,
            days_taken=2.0,
            daily_reference_hours=8.0,
            hourly_rate=5.0,
        )


def test_workday_totals_with_majoration():
    wds = [
        WorkdayFacts(day=date(2025, 2, 1), hours=10.0, kind=WorkdayKind.NORMAL),
        WorkdayFacts(day=date(2025, 2, 2), hours=6.0, kind=WorkdayKind.NORMAL),
    ]
    totals = workday_totals(
        wds,
        hourly_rate=5.0,
        majoration_threshold=8.0,
        majoration_rate=1.25,
    )
    assert totals.total_hours == 16.0
    assert totals.normal_hours == 14.0
    assert totals.majorated_hours == 2.0
    assert totals.base_salary == 14.0 * 5.0
    assert totals.majoration_salary == 2.0 * 5.0 * 1.25
    assert totals.total_salary == totals.base_salary + totals.majoration_salary


def test_unpaid_leave_deduction_without_days_per_week():
    assert unpaid_leave_deduction(
        2, hours_per_week=40.0, days_per_week=None, hourly_rate=5.0
    ) == 0.0


def test_unpaid_leave_deduction_with_days_per_week():
    assert unpaid_leave_deduction(
        2, hours_per_week=40.0, days_per_week=5, hourly_rate=5.0
    ) == 2 * 8.0 * 5.0


def test_workday_totals_without_majoration():
    wds = [
        WorkdayFacts(day=date(2025, 3, 1), hours=7.5, kind=WorkdayKind.NORMAL),
        WorkdayFacts(day=date(2025, 3, 2), hours=0.0, kind=WorkdayKind.NORMAL),
    ]
    totals = workday_totals(wds, hourly_rate=4.0)
    assert totals.total_hours == 7.5
    assert totals.normal_hours == 7.5
    assert totals.majorated_hours == 0.0
    assert totals.base_salary == 7.5 * 4.0
    assert totals.majoration_salary == 0.0
    assert totals.total_salary == totals.base_salary


def test_workday_totals_filters_kinds():
    wds = [
        WorkdayFacts(day=date(2025, 4, 1), hours=6.0, kind=WorkdayKind.NORMAL),
        WorkdayFacts(day=date(2025, 4, 2), hours=6.0, kind=WorkdayKind.ABSENCE),
    ]
    totals = workday_totals(
        wds, hourly_rate=4.0, include_kinds={WorkdayKind.NORMAL}
    )
    assert totals.total_hours == 6.0
    assert totals.base_salary == 6.0 * 4.0


def test_unpaid_leave_deduction_zero_days():
    assert unpaid_leave_deduction(
        0, hours_per_week=40.0, days_per_week=5, hourly_rate=5.0
    ) == 0.0
