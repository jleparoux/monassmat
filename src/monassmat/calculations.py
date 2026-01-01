from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from enum import Enum
from typing import Iterable


class WorkdayKind(str, Enum):
    NORMAL = "normal"
    ABSENCE = "absence"
    UNPAID_LEAVE = "unpaid_leave"
    HOLIDAY = "holiday"
    ASSMAT_LEAVE = "assmat_leave"


class PaidLeaveMethod(str, Enum):
    MAINTIEN = "maintien"
    DIXIEME = "dixieme"


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


def _assert_positive(name: str, value: float) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be > 0 (got {value})")


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
    Monthly salary (gross) based on contract facts:
        monthly_hours * hourly_rate
    """
    _assert_positive("hourly_rate", contract.hourly_rate)
    return contract_monthly_hours(contract) * contract.hourly_rate


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
