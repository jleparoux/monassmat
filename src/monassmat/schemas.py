from __future__ import annotations

from datetime import date, time

from pydantic import BaseModel, Field

from .models import WorkdayKind


class WorkdayUpsertIn(BaseModel):
    date: date
    hours: float = Field(ge=0)
    kind: WorkdayKind
    start_time: time | None = None
    end_time: time | None = None
    fee_meal: bool = False
    fee_maintenance: bool = False


class MonthlySummaryOut(BaseModel):
    period_start: date
    period_end: date
    monthly_hours_theoretical: float
    monthly_salary_theoretical: float
    hours_real: float
    hours_normal: float
    hours_majorated: float
    hours_delta: float
    work_days: int
    absence_days: int
    unpaid_leave_days: int
    assmat_leave_days: int
    holiday_days: int
    salary_base: float
    salary_majoration: float
    salary_real_estimated: float
    fee_meal_days: int = 0
    fee_maintenance_days: int = 0
    fee_meal_total: float = 0.0
    fee_maintenance_total: float = 0.0
    unpaid_leave_deduction: float = 0.0
    total_estimated: float = 0.0
    average_hours_per_day: float = 0.0
