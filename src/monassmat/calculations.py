from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, time, timedelta
from enum import Enum


class WorkdayKind(str, Enum):
    NORMAL = "normal"
    ABSENCE = "absence"
    UNPAID_LEAVE = "unpaid_leave"
    HOLIDAY = "holiday"
    ASSMAT_LEAVE = "assmat_leave"


class PaidLeaveMethod(str, Enum):
    MAINTIEN = "maintien"
    DIXIEME = "dixieme"


class ContractYearMode(str, Enum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


class MonthDataStatus(str, Enum):
    SCHEDULE_MISSING = "schedule_missing"
    NOT_STARTED = "not_started"
    INCOMPLETE = "incomplete"
    UP_TO_DATE = "up_to_date"
    COMPLETE = "complete"


class MonthlyWorkflowStatus(str, Enum):
    SETUP_REQUIRED = "setup_required"
    DATA_ENTRY = "data_entry"
    READY_TO_DECLARE = "ready_to_declare"
    DECLARED = "declared"
    PAYMENT_RECORDED = "payment_recorded"
    CLOSED = "closed"


@dataclass(frozen=True)
class ContractFacts:
    start_date: date
    end_date: date | None
    hours_per_week: float
    weeks_per_year: float
    hourly_rate: float


@dataclass(frozen=True)
class WorkdayFacts:
    day: date
    hours: float
    kind: WorkdayKind = WorkdayKind.NORMAL


@dataclass(frozen=True)
class Period:
    start: date  # inclusive
    end: date    # inclusive


@dataclass(frozen=True)
class ScheduledDayFacts:
    day: date
    scheduled_hours: float | None


@dataclass(frozen=True)
class MonthCompleteness:
    status: MonthDataStatus
    expected_days: int | None
    entered_days: int
    missing_days: int | None
    missing_due_days: int | None


@dataclass(frozen=True)
class WeeklyHoursBreakdown:
    normal_hours: float
    complementary_hours: float
    majorated_hours: float


@dataclass(frozen=True)
class PajemploiPreparation:
    normal_hours: int | None
    activity_days: int | None
    salary_before_extra_hours: float | None
    complementary_pay: float | None
    majorated_pay: float | None
    paid_leave_amount: float
    net_salary: float | None
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class PaidLeaveBalance:
    base_acquired_days: int
    child_days: int
    additional_days: int
    total_acquired_days: int
    taken_days: int
    advance_days: int
    regularized_days: int
    charged_days: int
    remaining_days: int


def _assert_positive(name: str, value: float) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be > 0 (got {value})")


def _round_positive_half_up(value: float) -> int:
    if value < 0:
        raise ValueError(f"value must be >= 0 (got {value})")
    return math.floor(value + 0.5)


def evaluate_month_completeness(
    scheduled_days: Iterable[ScheduledDayFacts],
    *,
    recorded_dates: Iterable[date],
    as_of: date,
) -> MonthCompleteness:
    """Evaluate whether every contractually scheduled day is documented.

    Unscheduled days do not need a calendar entry. A legacy schedule containing
    unknown values makes the result unknown instead of assuming a Monday to
    Friday week. Future scheduled days distinguish a month that is up to date
    from a month that is fully documented.
    """
    items = tuple(scheduled_days)
    if len({item.day for item in items}) != len(items):
        raise ValueError("scheduled days must have unique dates")
    if any(
        item.scheduled_hours is not None and item.scheduled_hours < 0
        for item in items
    ):
        raise ValueError("scheduled hours must be >= 0")

    if any(item.scheduled_hours is None for item in items):
        return MonthCompleteness(
            status=MonthDataStatus.SCHEDULE_MISSING,
            expected_days=None,
            entered_days=0,
            missing_days=None,
            missing_due_days=None,
        )
    if not items:
        return MonthCompleteness(
            status=MonthDataStatus.NOT_STARTED,
            expected_days=0,
            entered_days=0,
            missing_days=0,
            missing_due_days=0,
        )

    expected_dates = {
        item.day
        for item in items
        if item.scheduled_hours is not None and item.scheduled_hours > 0
    }
    entered_dates = expected_dates.intersection(recorded_dates)
    missing_dates = expected_dates - entered_dates
    missing_due_dates = {day for day in missing_dates if day <= as_of}

    if not missing_dates:
        status = MonthDataStatus.COMPLETE
    elif expected_dates and all(day > as_of for day in expected_dates):
        status = MonthDataStatus.NOT_STARTED
    elif missing_due_dates:
        status = MonthDataStatus.INCOMPLETE
    else:
        status = MonthDataStatus.UP_TO_DATE

    return MonthCompleteness(
        status=status,
        expected_days=len(expected_dates),
        entered_days=len(entered_dates),
        missing_days=len(missing_dates),
        missing_due_days=len(missing_due_dates),
    )


def monthly_workflow_status(
    *,
    data_status: MonthDataStatus,
    declaration_confirmed: bool,
    payment_recorded: bool,
) -> MonthlyWorkflowStatus:
    """Derive the next monthly action from recorded facts only."""
    if data_status == MonthDataStatus.SCHEDULE_MISSING:
        return MonthlyWorkflowStatus.SETUP_REQUIRED
    if data_status != MonthDataStatus.COMPLETE:
        return MonthlyWorkflowStatus.DATA_ENTRY
    if declaration_confirmed and payment_recorded:
        return MonthlyWorkflowStatus.CLOSED
    if declaration_confirmed:
        return MonthlyWorkflowStatus.DECLARED
    if payment_recorded:
        return MonthlyWorkflowStatus.PAYMENT_RECORDED
    return MonthlyWorkflowStatus.READY_TO_DECLARE


def prepare_pajemploi_declaration(
    *,
    monthly_salary: float,
    hourly_rate: float,
    hours_per_week: float,
    weeks_per_year: float,
    scheduled_days_per_week: int,
    absence_deduction: float | None,
    actual_activity_days: int | None,
    complementary_hours: float,
    complementary_hourly_rate: float | None,
    majorated_hours: float,
    majorated_hourly_rate: float | None,
    paid_leave_amount: float,
) -> PajemploiPreparation:
    """Prepare the numeric fields of one monthly Pajemploi declaration.

    The function deliberately returns blockers instead of guessing missing
    contractual rates or an unreliable absence deduction. Indemnities are not
    salary and therefore stay outside this calculation.
    """
    _assert_positive("monthly_salary", monthly_salary)
    _assert_positive("hourly_rate", hourly_rate)
    _assert_positive("hours_per_week", hours_per_week)
    _assert_positive("weeks_per_year", weeks_per_year)
    if not 1 <= scheduled_days_per_week <= 7:
        raise ValueError("scheduled_days_per_week must be between 1 and 7")
    if complementary_hours < 0 or majorated_hours < 0:
        raise ValueError("extra hours must be >= 0")
    if paid_leave_amount < 0:
        raise ValueError("paid_leave_amount must be >= 0")
    if absence_deduction is not None and absence_deduction < 0:
        raise ValueError("absence_deduction must be >= 0")
    if actual_activity_days is not None and actual_activity_days < 0:
        raise ValueError("actual_activity_days must be >= 0")

    blockers: list[str] = []
    salary_before_extra_hours: float | None
    normal_hours: int | None
    activity_days: int | None

    if absence_deduction is None:
        blockers.append("La deduction d'absence doit etre fiabilisee.")
        salary_before_extra_hours = None
        normal_hours = None
        activity_days = None
    else:
        salary_before_extra_hours = max(monthly_salary - absence_deduction, 0.0)
        if absence_deduction > 0:
            normal_hours = _round_positive_half_up(
                salary_before_extra_hours / hourly_rate
            )
            if actual_activity_days is None:
                blockers.append(
                    "Le nombre reel de jours d'activite doit etre fiabilise."
                )
                activity_days = None
            else:
                activity_days = actual_activity_days
        else:
            normal_hours = _round_positive_half_up(
                hours_per_week * weeks_per_year / 12.0
            )
            activity_days = math.ceil(
                scheduled_days_per_week * weeks_per_year / 12.0
            )

    complementary_pay: float | None = 0.0
    if complementary_hours > 0:
        if complementary_hourly_rate is None or complementary_hourly_rate <= 0:
            blockers.append(
                "Le taux net des heures complementaires doit etre renseigne."
            )
            complementary_pay = None
        else:
            complementary_pay = complementary_hours * complementary_hourly_rate

    majorated_pay: float | None = 0.0
    if majorated_hours > 0:
        if majorated_hourly_rate is None or majorated_hourly_rate <= 0:
            blockers.append(
                "Le taux net des heures majorees doit etre renseigne."
            )
            majorated_pay = None
        else:
            majorated_pay = majorated_hours * majorated_hourly_rate

    net_salary = None
    if (
        not blockers
        and salary_before_extra_hours is not None
        and complementary_pay is not None
        and majorated_pay is not None
    ):
        net_salary = (
            salary_before_extra_hours
            + complementary_pay
            + majorated_pay
            + paid_leave_amount
        )

    return PajemploiPreparation(
        normal_hours=normal_hours,
        activity_days=activity_days,
        salary_before_extra_hours=salary_before_extra_hours,
        complementary_pay=complementary_pay,
        majorated_pay=majorated_pay,
        paid_leave_amount=paid_leave_amount,
        net_salary=net_salary,
        blockers=tuple(blockers),
    )


def hours_between_times(start: time, end: time) -> float:
    start_minutes = start.hour * 60 + start.minute
    end_minutes = end.hour * 60 + end.minute
    if end_minutes <= start_minutes:
        raise ValueError("end time must be after start time")
    return (end_minutes - start_minutes) / 60.0


def contract_monthly_hours(contract: ContractFacts) -> float:
    """
    Monthly hours in 'annee incomplete' style:
        hours_per_week * weeks_per_year / 12
    """
    _assert_positive("hours_per_week", contract.hours_per_week)
    _assert_positive("weeks_per_year", contract.weeks_per_year)
    return contract.hours_per_week * contract.weeks_per_year / 12.0


def contract_monthly_salary(contract: ContractFacts) -> float:
    """
    Monthly salary based on contract facts:
        monthly_hours * hourly_rate

    The result uses the same net or gross basis as ``hourly_rate``. The caller
    must label that basis explicitly.
    """
    _assert_positive("hourly_rate", contract.hourly_rate)
    return contract_monthly_hours(contract) * contract.hourly_rate


def validate_regular_contract_weeks(
    *,
    mode: ContractYearMode,
    weeks_per_year: float,
) -> None:
    """Validate the two regular-care modes defined by article 97.1."""
    _assert_positive("weeks_per_year", weeks_per_year)
    if mode == ContractYearMode.COMPLETE:
        if weeks_per_year != 52.0:
            raise ValueError("52-week care must use exactly 52 weeks")
        return
    if mode == ContractYearMode.INCOMPLETE:
        if weeks_per_year > 46.0:
            raise ValueError("46-weeks-or-less care cannot exceed 46 weeks")
        return
    raise ValueError(f"Unknown mode: {mode}")


def weekly_schedule_total(
    daily_hours: Iterable[float | None],
) -> float | None:
    """Return the total of a Monday-to-Sunday schedule.

    Seven ``None`` values represent a legacy contract whose schedule has not
    been entered yet. A partially missing schedule is rejected because it
    cannot safely support absence calculations.
    """
    items = tuple(daily_hours)
    if len(items) != 7:
        raise ValueError("weekly schedule must contain exactly seven days")
    if all(value is None for value in items):
        return None
    if any(value is None for value in items):
        raise ValueError("weekly schedule must define all seven days")

    values = tuple(float(value) for value in items if value is not None)
    if any(value < 0 for value in values):
        raise ValueError("daily scheduled hours must be >= 0")
    return sum(values)


def validate_weekly_schedule(
    daily_hours: Iterable[float | None],
    *,
    hours_per_week: float,
    required: bool,
) -> None:
    """Validate an explicit weekly schedule against contractual hours."""
    _assert_positive("hours_per_week", hours_per_week)
    total = weekly_schedule_total(daily_hours)
    if total is None:
        if required:
            raise ValueError("weekly schedule is required")
        return
    if not math.isclose(total, hours_per_week, abs_tol=0.01):
        raise ValueError("weekly schedule total must match hours_per_week")


def validate_majoration_coefficient(coefficient: float | None) -> None:
    """Validate the contractual coefficient for hours worked beyond 45/week."""
    if coefficient is not None and coefficient < 1.10:
        raise ValueError("majoration coefficient must be at least 1.10")


def scheduled_hours_for_day(
    daily_hours: Iterable[float | None],
    day: date,
) -> float | None:
    """Return contractual hours for one weekday, or ``None`` for legacy data."""
    schedule = tuple(daily_hours)
    total = weekly_schedule_total(schedule)
    if total is None:
        return None
    value = schedule[day.weekday()]
    return float(value) if value is not None else None


def hours_in_period(
    workdays: Iterable[WorkdayFacts],
    period: Period,
    *,
    include_kinds: set[WorkdayKind] | None = None,
) -> float:
    """
    Sum worked hours within a period.
    Default includes only NORMAL days.
    """
    if period.end < period.start:
        raise ValueError("period.end must be >= period.start")

    if include_kinds is None:
        include_kinds = {WorkdayKind.NORMAL}

    total = 0.0
    for wd in workdays:
        if period.start <= wd.day <= period.end and wd.kind in include_kinds:
            if wd.hours < 0:
                raise ValueError(f"Workday hours must be >= 0 (got {wd.hours})")
            total += wd.hours
    return total


def value_hours(hours: float, hourly_rate: float) -> float:
    if hours < 0:
        raise ValueError("hours must be >= 0")
    _assert_positive("hourly_rate", hourly_rate)
    return hours * hourly_rate


def classify_weekly_hours(
    *,
    worked_hours: float,
    contracted_hours: float,
) -> WeeklyHoursBreakdown:
    """Classify one week's hours under articles 96.4 and 110.

    Hours beyond the weekly contract and up to 45 hours are complementary.
    Hours beyond 45 hours are majorated, including when the weekly contract
    itself exceeds 45 hours.
    """
    if worked_hours < 0:
        raise ValueError("worked_hours must be >= 0")
    _assert_positive("contracted_hours", contracted_hours)

    majoration_start = 45.0
    normal_limit = min(contracted_hours, majoration_start)
    normal_hours = min(worked_hours, normal_limit)
    complementary_hours = max(
        min(worked_hours, majoration_start) - normal_limit,
        0.0,
    )
    majorated_hours = max(worked_hours - majoration_start, 0.0)

    return WeeklyHoursBreakdown(
        normal_hours=normal_hours,
        complementary_hours=complementary_hours,
        majorated_hours=majorated_hours,
    )


def allocate_weekly_hours(
    workdays: Iterable[WorkdayFacts],
    *,
    contracted_hours: float,
) -> dict[date, WeeklyHoursBreakdown]:
    """Allocate a single week's hours chronologically between legal buckets.

    Only normal workdays are considered. All included dates must belong to the
    same Monday-to-Sunday week. This makes month-boundary allocation explicit:
    hours exceeding the thresholds are assigned to the day on which they occur.
    """
    _assert_positive("contracted_hours", contracted_hours)
    items = sorted(
        (workday for workday in workdays if workday.kind == WorkdayKind.NORMAL),
        key=lambda workday: workday.day,
    )
    if not items:
        return {}

    week_start = items[0].day.toordinal() - items[0].day.weekday()
    if any(
        workday.day.toordinal() - workday.day.weekday() != week_start
        for workday in items
    ):
        raise ValueError("workdays must belong to the same week")
    if len({workday.day for workday in items}) != len(items):
        raise ValueError("workdays must have unique dates")
    if any(workday.hours < 0 for workday in items):
        raise ValueError("workday hours must be >= 0")

    normal_remaining = min(contracted_hours, 45.0)
    complementary_remaining = max(45.0 - normal_remaining, 0.0)
    result: dict[date, WeeklyHoursBreakdown] = {}

    for workday in items:
        remaining = workday.hours
        normal = min(remaining, normal_remaining)
        remaining -= normal
        normal_remaining -= normal

        complementary = min(remaining, complementary_remaining)
        remaining -= complementary
        complementary_remaining -= complementary

        result[workday.day] = WeeklyHoursBreakdown(
            normal_hours=normal,
            complementary_hours=complementary,
            majorated_hours=remaining,
        )

    return result


def _proportional_absence_deduction(
    *,
    monthly_salary: float,
    absence_units: float,
    scheduled_units_in_month: float,
) -> float:
    if monthly_salary < 0:
        raise ValueError("monthly_salary must be >= 0")
    if absence_units < 0:
        raise ValueError("absence units must be >= 0")
    if absence_units == 0:
        return 0.0
    _assert_positive("scheduled units in month", scheduled_units_in_month)
    if absence_units > scheduled_units_in_month:
        raise ValueError("absence units cannot exceed scheduled units in month")
    return monthly_salary * absence_units / scheduled_units_in_month


def absence_deduction_52_weeks(
    *,
    monthly_salary: float,
    absence_hours: float,
    scheduled_hours_in_month: float,
) -> float:
    """Deduct an unpaid absence for a 52-week regular contract.

    ``scheduled_hours_in_month`` is the exact number of hours that would have
    been worked in that calendar month according to the contract or planning;
    it is not the number of monthly smoothed hours.
    """
    return _proportional_absence_deduction(
        monthly_salary=monthly_salary,
        absence_units=absence_hours,
        scheduled_units_in_month=scheduled_hours_in_month,
    )


def absence_deduction_46_weeks(
    *,
    monthly_salary: float,
    absence_days: float,
    scheduled_days_in_month: float,
) -> float:
    """Deduct an unpaid absence for a 46-weeks-or-less regular contract.

    ``scheduled_days_in_month`` is the exact number of days that would have
    been worked in that calendar month according to the contract or planning.
    """
    return _proportional_absence_deduction(
        monthly_salary=monthly_salary,
        absence_units=absence_days,
        scheduled_units_in_month=scheduled_days_in_month,
    )


def paid_leave_acquired_days(
    *,
    worked_weeks: float,
    worked_days: int = 0,
    scheduled_days_per_week: int | None = None,
) -> int:
    """Return base rights from explicit work-equivalent weeks and days.

    Rights accrue at 2.5 working days per four weeks of actual or equivalent
    work. A remainder expressed in worked days uses the contractual number of
    working days per week. The final result is rounded up and capped at the
    statutory 30-day base entitlement. Supplementary rights are deliberately
    calculated separately.
    """
    if worked_weeks < 0:
        raise ValueError("worked_weeks must be >= 0")
    if worked_days < 0:
        raise ValueError("worked_days must be >= 0")
    if worked_days and scheduled_days_per_week is None:
        raise ValueError("scheduled_days_per_week is required with worked_days")
    if scheduled_days_per_week is not None and not 1 <= scheduled_days_per_week <= 7:
        raise ValueError("scheduled_days_per_week must be between 1 and 7")

    equivalent_weeks = float(worked_weeks)
    if worked_days:
        equivalent_weeks += worked_days / scheduled_days_per_week
    return min(math.ceil(equivalent_weeks * 2.5 / 4.0 - 1e-9), 30)


def paid_leave_acquired_days_from_months(*, worked_months: int) -> int:
    """Return base rights for complete calendar months worked or assimilated."""
    if not 0 <= worked_months <= 12:
        raise ValueError("worked_months must be between 0 and 12")
    return min(math.ceil(worked_months * 2.5), 30)


def paid_leave_equivalent_weeks(
    work_equivalent_dates: Iterable[date],
    *,
    scheduled_weekdays: Iterable[int],
) -> float:
    """Convert explicit worked or assimilated scheduled days into weeks."""
    dates = tuple(work_equivalent_dates)
    if len(set(dates)) != len(dates):
        raise ValueError("work_equivalent_dates must be unique")
    weekdays = set(scheduled_weekdays)
    if not weekdays or any(day < 0 or day > 6 for day in weekdays):
        raise ValueError("scheduled_weekdays must contain values from 0 to 6")
    if any(day.weekday() not in weekdays for day in dates):
        raise ValueError("work-equivalent dates must be scheduled weekdays")
    return len(dates) / len(weekdays)


def additional_child_paid_leave_days(
    *,
    base_days: int,
    dependent_children: int,
    employee_under_21: bool,
) -> int:
    """Return supplementary rights for dependent children.

    For an employee aged 21 or over, total rights remain capped at 30 days.
    For an employee under 21, each child adds two days, reduced to one when the
    base entitlement does not exceed six days.
    """
    if not 0 <= base_days <= 30:
        raise ValueError("base_days must be between 0 and 30")
    if dependent_children < 0:
        raise ValueError("dependent_children must be >= 0")
    if employee_under_21:
        days_per_child = 1 if base_days <= 6 else 2
        return dependent_children * days_per_child
    return min(dependent_children * 2, 30 - base_days)


def calculate_paid_leave_balance(
    *,
    base_acquired_days: int,
    dependent_children: int,
    employee_under_21: bool,
    additional_days: int,
    taken_days: int,
    advance_days: int,
    regularized_days: int,
) -> PaidLeaveBalance:
    """Calculate a period balance from acquisition and explicit usage facts."""
    if additional_days < 0:
        raise ValueError("additional_days must be >= 0")
    if taken_days < 0:
        raise ValueError("taken_days must be >= 0")
    if advance_days < 0 or advance_days > taken_days:
        raise ValueError("advance_days must be between 0 and taken_days")
    if regularized_days < 0 or regularized_days > taken_days:
        raise ValueError("regularized_days must be between 0 and taken_days")

    child_days = additional_child_paid_leave_days(
        base_days=base_acquired_days,
        dependent_children=dependent_children,
        employee_under_21=employee_under_21,
    )
    total_acquired = base_acquired_days + child_days + additional_days
    charged_days = taken_days - regularized_days
    return PaidLeaveBalance(
        base_acquired_days=base_acquired_days,
        child_days=child_days,
        additional_days=additional_days,
        total_acquired_days=total_acquired,
        taken_days=taken_days,
        advance_days=advance_days,
        regularized_days=regularized_days,
        charged_days=charged_days,
        remaining_days=total_acquired - charged_days,
    )


def paid_leave_reference_period(day: date) -> Period:
    """Return the June 1 to May 31 acquisition period containing ``day``."""
    if day.month >= 6:
        return Period(
            start=date(day.year, 6, 1),
            end=date(day.year + 1, 5, 31),
        )
    return Period(
        start=date(day.year - 1, 6, 1),
        end=date(day.year, 5, 31),
    )


def paid_leave_taken_dates(
    *,
    absence_start: date,
    absence_end: date,
    scheduled_weekdays: Iterable[int],
    holidays: Iterable[date] = (),
) -> tuple[date, ...]:
    """Return the working days deducted for one paid-leave absence.

    Counting starts on the first day in the absence where work was scheduled,
    then includes every Monday-to-Saturday working day until the day before the
    next scheduled return. Sundays and public holidays are excluded.
    """
    if absence_end < absence_start:
        raise ValueError("absence_end must be >= absence_start")
    weekdays = set(scheduled_weekdays)
    if not weekdays or any(day < 0 or day > 6 for day in weekdays):
        raise ValueError("scheduled_weekdays must contain values from 0 to 6")
    holiday_dates = set(holidays)

    first_day = absence_start
    while first_day <= absence_end and (
        first_day.weekday() not in weekdays or first_day in holiday_dates
    ):
        first_day += timedelta(days=1)
    if first_day > absence_end:
        return ()

    return_day = absence_end + timedelta(days=1)
    while return_day.weekday() not in weekdays:
        return_day += timedelta(days=1)

    result = []
    current = first_day
    while current < return_day:
        if current.weekday() != 6 and current not in holiday_dates:
            result.append(current)
        current += timedelta(days=1)
    return tuple(result)


def paid_leave_value(
    *,
    method: PaidLeaveMethod,
    days_taken: float,
    daily_reference_hours: float,
    hourly_rate: float,
    dixieme_reference_amount: float | None = None,
) -> float:
    """
    Compute amount to pay for paid leave taken.

    - MAINTIEN: days_taken * daily_reference_hours * hourly_rate
    - DIXIEME: requires dixieme_reference_amount (10% base) and allocates proportionally.
      In V1 we keep it explicit and simple.

    All inputs are explicit; no DB access; no hidden state.
    """
    if days_taken < 0:
        raise ValueError("days_taken must be >= 0")
    _assert_positive("daily_reference_hours", daily_reference_hours)
    _assert_positive("hourly_rate", hourly_rate)

    if method == PaidLeaveMethod.MAINTIEN:
        return days_taken * daily_reference_hours * hourly_rate

    if method == PaidLeaveMethod.DIXIEME:
        if dixieme_reference_amount is None:
            raise ValueError("dixieme_reference_amount is required for DIXIEME method")
        if dixieme_reference_amount < 0:
            raise ValueError("dixieme_reference_amount must be >= 0")
        # V1: caller provides already-proportioned amount if needed; otherwise uses full reference.
        return dixieme_reference_amount

    raise ValueError(f"Unknown method: {method}")


def parse_holidays_response(data: dict[str, str]) -> list[tuple[date, str]]:
    result = []
    for date_str, name in data.items():
        try:
            result.append((date.fromisoformat(date_str), name))
        except ValueError:
            continue
    return sorted(result, key=lambda x: x[0])
