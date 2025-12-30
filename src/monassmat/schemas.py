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
    salary_real_estimated: float
    fee_meal_days: int = 0
    fee_maintenance_days: int = 0
