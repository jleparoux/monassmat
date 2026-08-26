import calendar
from datetime import date

import pytest

from monassmat.calculations import (
    ContractFacts,
    ContractYearMode,
    PaidLeaveMethod,
    Period,
    WorkdayFacts,
    WorkdayKind,
    absence_deduction_46_weeks,
    absence_deduction_52_weeks,
    classify_weekly_hours,
    contract_monthly_hours,
    contract_monthly_salary,
    hours_in_period,
    paid_leave_acquired_days,
    paid_leave_value,
    unpaid_leave_deduction,
    validate_regular_contract_weeks,
    workday_totals,
)


def test_classify_weekly_hours_matches_urssaf_example():
    """32 h au contrat et 50 h faites donnent 13 h comp. et 5 h maj."""
    result = classify_weekly_hours(
        worked_hours=50.0,
        contracted_hours=32.0,
    )

    assert result.normal_hours == 32.0
    assert result.complementary_hours == 13.0
    assert result.majorated_hours == 5.0


def test_classify_weekly_hours_stops_complementary_hours_at_45():
    result = classify_weekly_hours(
        worked_hours=44.0,
        contracted_hours=40.0,
    )

    assert result.normal_hours == 40.0
    assert result.complementary_hours == 4.0
    assert result.majorated_hours == 0.0


def test_classify_weekly_hours_rejects_negative_values():
    with pytest.raises(ValueError):
        classify_weekly_hours(worked_hours=-1.0, contracted_hours=40.0)


def test_absence_deduction_52_weeks_uses_month_real_schedule_hours():
    result = absence_deduction_52_weeks(
        monthly_salary=416.0,
        absence_hours=8.0,
        scheduled_hours_in_month=144.0,
    )

    assert result == pytest.approx(416.0 * 8.0 / 144.0)


def test_absence_deduction_46_weeks_uses_month_real_schedule_days():
    result = absence_deduction_46_weeks(
        monthly_salary=370.0,
        absence_days=1.0,
        scheduled_days_in_month=17.0,
    )

    assert result == pytest.approx(370.0 / 17.0)


@pytest.mark.parametrize(
    ("function", "kwargs"),
    [
        (
            absence_deduction_52_weeks,
            {
                "monthly_salary": 416.0,
                "absence_hours": 8.0,
                "scheduled_hours_in_month": 0.0,
            },
        ),
        (
            absence_deduction_46_weeks,
            {
                "monthly_salary": 370.0,
                "absence_days": 18.0,
                "scheduled_days_in_month": 17.0,
            },
        ),
    ],
)
def test_absence_deduction_rejects_inconsistent_inputs(function, kwargs):
    with pytest.raises(ValueError):
        function(**kwargs)


@pytest.mark.parametrize(
    ("mode", "weeks"),
    [
        (ContractYearMode.COMPLETE, 52.0),
        (ContractYearMode.INCOMPLETE, 46.0),
        (ContractYearMode.INCOMPLETE, 37.0),
    ],
)
def test_validate_regular_contract_weeks_accepts_official_modes(mode, weeks):
    validate_regular_contract_weeks(mode=mode, weeks_per_year=weeks)


@pytest.mark.parametrize(
    ("mode", "weeks"),
    [
        (ContractYearMode.COMPLETE, 45.0),
        (ContractYearMode.INCOMPLETE, 52.0),
        (ContractYearMode.INCOMPLETE, 47.0),
    ],
)
def test_validate_regular_contract_weeks_rejects_inconsistent_modes(mode, weeks):
    with pytest.raises(ValueError):
        validate_regular_contract_weeks(mode=mode, weeks_per_year=weeks)


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


def test_paid_leave_value_dixieme_returns_reference_amount():
    amount = paid_leave_value(
        method=PaidLeaveMethod.DIXIEME,
        days_taken=2.0,
        daily_reference_hours=8.0,
        hourly_rate=5.0,
        dixieme_reference_amount=120.0,
    )
    assert amount == 120.0


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


def test_days_expected_may_2026():
    """Vérifie qu'on compte bien les lun-ven d'un mois donné."""
    _, last_day = calendar.monthrange(2026, 5)
    days = sum(1 for day in range(1, last_day + 1) if date(2026, 5, day).weekday() < 5)
    assert days == 21  # Mai 2026 : 21 jours ouvrés (lun-ven)


def test_paid_leave_acquired_days_complete_mode():
    assert (
        paid_leave_acquired_days(mode=ContractYearMode.COMPLETE, extra_days=0)
        == 30
    )


def test_paid_leave_acquired_days_incomplete_rounds_up():
    acquired = paid_leave_acquired_days(
        mode=ContractYearMode.INCOMPLETE,
        weeks_worked=41.0,
    )
    assert acquired == 26


def test_paid_leave_acquired_days_with_extra_days():
    acquired = paid_leave_acquired_days(
        mode=ContractYearMode.INCOMPLETE,
        weeks_worked=40.0,
        extra_days=4,
    )
    assert acquired == 29
