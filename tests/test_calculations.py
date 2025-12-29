from datetime import date

import pytest
from monassmat.calculations import (ContractFacts, PaidLeaveMethod, Period,
                                    WorkdayFacts, WorkdayKind,
                                    contract_monthly_hours,
                                    contract_monthly_salary, hours_in_period,
                                    paid_leave_value)


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
