from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, time
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


def _assert_positive(name: str, value: float) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be > 0 (got {value})")


def _round_positive_half_up(value: float) -> int:
    if value < 0:
        raise ValueError(f"value must be >= 0 (got {value})")
    return math.floor(value + 0.5)


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


# ---------------------------------------------------------------------------
# Paid leave (V1 scaffold)
# ---------------------------------------------------------------------------

def paid_leave_acquired_days_v1(
    workdays: Iterable[WorkdayFacts],
    acquisition_period: Period,
) -> float:
    """
    V1 heuristic scaffold:
    - We compute number of 'worked days' (NORMAL) in the acquisition period
    - Then apply a simple proportional rule.

    IMPORTANT:
    This is NOT a full legal implementation.
    It is a placeholder until we codify the exact rules we want.
    """
    if acquisition_period.end < acquisition_period.start:
        raise ValueError("acquisition_period.end must be >= acquisition_period.start")

    worked_days = 0
    for wd in workdays:
        if acquisition_period.start <= wd.day <= acquisition_period.end and wd.kind == WorkdayKind.NORMAL:
            worked_days += 1

    # Placeholder: 2.5 days per 4 weeks approx -> 2.5 per 20 worked days rough proxy
    # You will replace this once rules are specified precisely.
    return (worked_days / 20.0) * 2.5


def paid_leave_acquired_days(
    *,
    mode: ContractYearMode,
    weeks_worked: float | None = None,
    extra_days: int = 0,
) -> int:
    """
    Compute acquired paid leave days using explicit rules:

    - COMPLETE: 2.5 days per month x 12 months = 30 days.
    - INCOMPLETE: (weeks_worked / 4) * 2.5, rounded up to the next whole day.

    extra_days allows adding legally defined supplementary days (children, fractionnement, ...).
    """
    if extra_days < 0:
        raise ValueError("extra_days must be >= 0")

    if mode == ContractYearMode.COMPLETE:
        return 30 + extra_days

    if mode == ContractYearMode.INCOMPLETE:
        if weeks_worked is None:
            raise ValueError("weeks_worked is required for INCOMPLETE mode")
        if weeks_worked < 0:
            raise ValueError("weeks_worked must be >= 0")
        acquired = (weeks_worked / 4.0) * 2.5
        return int(math.ceil(acquired)) + extra_days

    raise ValueError(f"Unknown mode: {mode}")


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
