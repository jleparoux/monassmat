from datetime import date

import pytest

from monassmat.calculations import (
    ContractFacts,
    ContractYearMode,
    MonthDataStatus,
    MonthlyWorkflowStatus,
    PaidLeaveMethod,
    Period,
    ScheduledDayFacts,
    WorkdayFacts,
    WorkdayKind,
    absence_deduction_46_weeks,
    absence_deduction_52_weeks,
    additional_child_paid_leave_days,
    allocate_weekly_hours,
    calculate_paid_leave_balance,
    classify_weekly_hours,
    contract_monthly_hours,
    contract_monthly_salary,
    evaluate_month_completeness,
    hours_in_period,
    monthly_workflow_status,
    paid_leave_acquired_days,
    paid_leave_acquired_days_from_months,
    paid_leave_equivalent_weeks,
    paid_leave_reference_period,
    paid_leave_taken_dates,
    paid_leave_value,
    prepare_pajemploi_declaration,
    scheduled_hours_for_day,
    validate_majoration_coefficient,
    validate_regular_contract_weeks,
    validate_weekly_schedule,
    weekly_schedule_total,
)


@pytest.mark.parametrize(
    ("data_status", "declared", "paid", "expected"),
    [
        (
            MonthDataStatus.SCHEDULE_MISSING,
            False,
            False,
            MonthlyWorkflowStatus.SETUP_REQUIRED,
        ),
        (
            MonthDataStatus.INCOMPLETE,
            False,
            False,
            MonthlyWorkflowStatus.DATA_ENTRY,
        ),
        (
            MonthDataStatus.INCOMPLETE,
            True,
            True,
            MonthlyWorkflowStatus.DATA_ENTRY,
        ),
        (
            MonthDataStatus.COMPLETE,
            False,
            False,
            MonthlyWorkflowStatus.READY_TO_DECLARE,
        ),
        (
            MonthDataStatus.COMPLETE,
            True,
            False,
            MonthlyWorkflowStatus.DECLARED,
        ),
        (
            MonthDataStatus.COMPLETE,
            False,
            True,
            MonthlyWorkflowStatus.PAYMENT_RECORDED,
        ),
        (
            MonthDataStatus.COMPLETE,
            True,
            True,
            MonthlyWorkflowStatus.CLOSED,
        ),
    ],
)
def test_monthly_workflow_status(
    data_status,
    declared,
    paid,
    expected,
):
    assert monthly_workflow_status(
        data_status=data_status,
        declaration_confirmed=declared,
        payment_recorded=paid,
    ) == expected


def test_prepare_pajemploi_declaration_52_weeks_with_extra_hours():
    preparation = prepare_pajemploi_declaration(
        monthly_salary=416.0,
        hourly_rate=3.0,
        hours_per_week=32.0,
        weeks_per_year=52.0,
        scheduled_days_per_week=4,
        absence_deduction=0.0,
        actual_activity_days=None,
        complementary_hours=13.0,
        complementary_hourly_rate=3.20,
        majorated_hours=5.0,
        majorated_hourly_rate=3.50,
        paid_leave_amount=0.0,
    )

    assert preparation.normal_hours == 139
    assert preparation.activity_days == 18
    assert preparation.salary_before_extra_hours == pytest.approx(416.0)
    assert preparation.complementary_pay == pytest.approx(41.60)
    assert preparation.majorated_pay == pytest.approx(17.50)
    assert preparation.net_salary == pytest.approx(475.10)
    assert preparation.blockers == ()


def test_prepare_pajemploi_declaration_46_weeks_or_less():
    preparation = prepare_pajemploi_declaration(
        monthly_salary=370.0,
        hourly_rate=3.0,
        hours_per_week=40.0,
        weeks_per_year=37.0,
        scheduled_days_per_week=4,
        absence_deduction=0.0,
        actual_activity_days=None,
        complementary_hours=5.0,
        complementary_hourly_rate=3.20,
        majorated_hours=5.0,
        majorated_hourly_rate=3.50,
        paid_leave_amount=0.0,
    )

    assert preparation.normal_hours == 123
    assert preparation.activity_days == 13
    assert preparation.net_salary == pytest.approx(403.50)


def test_prepare_pajemploi_declaration_uses_due_salary_after_absence():
    preparation = prepare_pajemploi_declaration(
        monthly_salary=416.0,
        hourly_rate=3.0,
        hours_per_week=32.0,
        weeks_per_year=52.0,
        scheduled_days_per_week=4,
        absence_deduction=195.76,
        actual_activity_days=9,
        complementary_hours=0.0,
        complementary_hourly_rate=None,
        majorated_hours=0.0,
        majorated_hourly_rate=None,
        paid_leave_amount=0.0,
    )

    assert preparation.normal_hours == 73
    assert preparation.activity_days == 9
    assert preparation.salary_before_extra_hours == pytest.approx(220.24)
    assert preparation.net_salary == pytest.approx(220.24)
    assert preparation.blockers == ()


def test_prepare_pajemploi_declaration_blocks_missing_extra_hour_rate():
    preparation = prepare_pajemploi_declaration(
        monthly_salary=416.0,
        hourly_rate=3.0,
        hours_per_week=32.0,
        weeks_per_year=52.0,
        scheduled_days_per_week=4,
        absence_deduction=0.0,
        actual_activity_days=None,
        complementary_hours=2.0,
        complementary_hourly_rate=None,
        majorated_hours=1.0,
        majorated_hourly_rate=None,
        paid_leave_amount=0.0,
    )

    assert preparation.complementary_pay is None
    assert preparation.majorated_pay is None
    assert preparation.net_salary is None
    assert len(preparation.blockers) == 2


def test_prepare_pajemploi_declaration_blocks_unreliable_absence():
    preparation = prepare_pajemploi_declaration(
        monthly_salary=416.0,
        hourly_rate=3.0,
        hours_per_week=32.0,
        weeks_per_year=52.0,
        scheduled_days_per_week=4,
        absence_deduction=None,
        actual_activity_days=None,
        complementary_hours=0.0,
        complementary_hourly_rate=None,
        majorated_hours=0.0,
        majorated_hourly_rate=None,
        paid_leave_amount=0.0,
    )

    assert preparation.normal_hours is None
    assert preparation.activity_days is None
    assert preparation.net_salary is None
    assert preparation.blockers == (
        "La deduction d'absence doit etre fiabilisee.",
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


@pytest.mark.parametrize("coefficient", [None, 1.10, 1.25])
def test_majoration_coefficient_accepts_contractual_values(coefficient):
    validate_majoration_coefficient(coefficient)


def test_majoration_coefficient_rejects_less_than_ten_percent():
    with pytest.raises(ValueError):
        validate_majoration_coefficient(1.09)


def test_allocate_weekly_hours_assigns_excess_to_later_days():
    workdays = [
        WorkdayFacts(day=date(2025, 1, 6), hours=10.0),
        WorkdayFacts(day=date(2025, 1, 7), hours=10.0),
        WorkdayFacts(day=date(2025, 1, 8), hours=10.0),
        WorkdayFacts(day=date(2025, 1, 9), hours=10.0),
        WorkdayFacts(day=date(2025, 1, 10), hours=10.0),
    ]

    result = allocate_weekly_hours(workdays, contracted_hours=32.0)

    assert result[date(2025, 1, 9)].normal_hours == 2.0
    assert result[date(2025, 1, 9)].complementary_hours == 8.0
    assert result[date(2025, 1, 10)].complementary_hours == 5.0
    assert result[date(2025, 1, 10)].majorated_hours == 5.0


def test_allocate_weekly_hours_rejects_multiple_weeks():
    workdays = [
        WorkdayFacts(day=date(2025, 1, 10), hours=8.0),
        WorkdayFacts(day=date(2025, 1, 13), hours=8.0),
    ]

    with pytest.raises(ValueError):
        allocate_weekly_hours(workdays, contracted_hours=35.0)


def test_absence_deduction_52_weeks_uses_month_real_schedule_hours():
    result = absence_deduction_52_weeks(
        monthly_salary=416.0,
        absence_hours=8.0,
        scheduled_hours_in_month=144.0,
    )

    assert result == pytest.approx(416.0 * 8.0 / 144.0)


def test_scheduled_hours_for_day_uses_monday_to_sunday_order():
    schedule = (8.0, 7.0, 0.0, 8.0, 7.0, 0.0, 0.0)

    assert scheduled_hours_for_day(schedule, date(2025, 1, 6)) == 8.0
    assert scheduled_hours_for_day(schedule, date(2025, 1, 8)) == 0.0


def test_scheduled_hours_for_day_keeps_legacy_schedule_unknown():
    assert scheduled_hours_for_day((None,) * 7, date(2025, 1, 6)) is None


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


def test_weekly_schedule_total_accepts_seven_explicit_days():
    schedule = (8.0, 8.0, 0.0, 8.0, 8.0, 0.0, 0.0)

    assert weekly_schedule_total(schedule) == 32.0


def test_weekly_schedule_total_returns_none_when_entire_schedule_is_missing():
    schedule = (None, None, None, None, None, None, None)

    assert weekly_schedule_total(schedule) is None


def test_weekly_schedule_total_rejects_partially_missing_schedule():
    schedule = (8.0, 8.0, None, 8.0, 8.0, 0.0, 0.0)

    with pytest.raises(ValueError):
        weekly_schedule_total(schedule)


def test_validate_weekly_schedule_matches_contract_hours():
    validate_weekly_schedule(
        (8.0, 8.0, 0.0, 8.0, 8.0, 0.0, 0.0),
        hours_per_week=32.0,
        required=True,
    )


def test_validate_weekly_schedule_rejects_wrong_total():
    with pytest.raises(ValueError):
        validate_weekly_schedule(
            (8.0, 8.0, 0.0, 8.0, 8.0, 0.0, 0.0),
            hours_per_week=40.0,
            required=True,
        )


def test_validate_weekly_schedule_allows_missing_legacy_schedule():
    validate_weekly_schedule(
        (None, None, None, None, None, None, None),
        hours_per_week=40.0,
        required=False,
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


def test_paid_leave_value_dixieme_returns_reference_amount():
    amount = paid_leave_value(
        method=PaidLeaveMethod.DIXIEME,
        days_taken=2.0,
        daily_reference_hours=8.0,
        hourly_rate=5.0,
        dixieme_reference_amount=120.0,
    )
    assert amount == 120.0


def test_month_completeness_uses_contract_schedule():
    scheduled_days = [
        ScheduledDayFacts(date(2026, 8, 3), 9.0),
        ScheduledDayFacts(date(2026, 8, 4), 0.0),
        ScheduledDayFacts(date(2026, 8, 5), 9.0),
    ]

    result = evaluate_month_completeness(
        scheduled_days,
        recorded_dates=[date(2026, 8, 3)],
        as_of=date(2026, 8, 5),
    )

    assert result.status == MonthDataStatus.INCOMPLETE
    assert result.expected_days == 2
    assert result.entered_days == 1
    assert result.missing_due_days == 1


def test_month_completeness_distinguishes_up_to_date_from_complete():
    scheduled_days = [
        ScheduledDayFacts(date(2026, 8, 27), 9.0),
        ScheduledDayFacts(date(2026, 8, 28), 9.0),
    ]

    result = evaluate_month_completeness(
        scheduled_days,
        recorded_dates=[date(2026, 8, 27)],
        as_of=date(2026, 8, 27),
    )

    assert result.status == MonthDataStatus.UP_TO_DATE
    assert result.missing_days == 1
    assert result.missing_due_days == 0


def test_month_completeness_does_not_guess_missing_schedule():
    result = evaluate_month_completeness(
        [ScheduledDayFacts(date(2026, 8, 3), None)],
        recorded_dates=[date(2026, 8, 3)],
        as_of=date(2026, 8, 3),
    )

    assert result.status == MonthDataStatus.SCHEDULE_MISSING
    assert result.expected_days is None
    assert result.missing_days is None


def test_paid_leave_acquired_days_full_period_is_capped_at_30():
    assert paid_leave_acquired_days(worked_weeks=52) == 30


def test_paid_leave_acquired_days_incomplete_rounds_up():
    acquired = paid_leave_acquired_days(worked_weeks=41)
    assert acquired == 26


def test_paid_leave_acquired_days_includes_partial_worked_week():
    acquired = paid_leave_acquired_days(
        worked_weeks=40,
        worked_days=2,
        scheduled_days_per_week=4,
    )
    assert acquired == 26


def test_paid_leave_acquired_days_from_complete_months_rounds_up():
    assert paid_leave_acquired_days_from_months(worked_months=9) == 23


def test_paid_leave_equivalent_weeks_uses_contractual_working_days():
    equivalent = paid_leave_equivalent_weeks(
        [
            date(2026, 6, 1),
            date(2026, 6, 2),
            date(2026, 6, 4),
            date(2026, 6, 5),
            date(2026, 6, 8),
            date(2026, 6, 9),
        ],
        scheduled_weekdays={0, 1, 3, 4},
    )

    assert equivalent == pytest.approx(1.5)


def test_additional_child_days_are_capped_for_employee_21_or_over():
    assert additional_child_paid_leave_days(
        base_days=27,
        dependent_children=2,
        employee_under_21=False,
    ) == 3


def test_additional_child_days_for_employee_under_21_can_exceed_30():
    assert additional_child_paid_leave_days(
        base_days=30,
        dependent_children=2,
        employee_under_21=True,
    ) == 4


def test_paid_leave_balance_shows_advance_and_regularization():
    balance = calculate_paid_leave_balance(
        base_acquired_days=23,
        dependent_children=2,
        employee_under_21=False,
        additional_days=0,
        taken_days=25,
        advance_days=10,
        regularized_days=10,
    )

    assert balance.child_days == 4
    assert balance.total_acquired_days == 27
    assert balance.charged_days == 15
    assert balance.remaining_days == 12


def test_paid_leave_reference_period_runs_from_june_to_may():
    assert paid_leave_reference_period(date(2026, 5, 31)) == Period(
        start=date(2025, 6, 1),
        end=date(2026, 5, 31),
    )
    assert paid_leave_reference_period(date(2026, 6, 1)) == Period(
        start=date(2026, 6, 1),
        end=date(2027, 5, 31),
    )


def test_paid_leave_taken_dates_counts_saturday_after_friday():
    dates = paid_leave_taken_dates(
        absence_start=date(2025, 5, 30),
        absence_end=date(2025, 5, 30),
        scheduled_weekdays={0, 1, 2, 3, 4},
    )

    assert dates == (date(2025, 5, 30), date(2025, 5, 31))


def test_paid_leave_taken_dates_excludes_sunday_and_public_holiday():
    dates = paid_leave_taken_dates(
        absence_start=date(2025, 8, 4),
        absence_end=date(2025, 8, 29),
        scheduled_weekdays={0, 1, 2, 3, 4},
        holidays={date(2025, 8, 15)},
    )

    assert len(dates) == 23
    assert date(2025, 8, 15) not in dates
    assert all(day.weekday() != 6 for day in dates)
