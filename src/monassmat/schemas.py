from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from .models import WorkdayKind


class WorkdayUpsertIn(BaseModel):
    date: date
    hours: float = Field(ge=0)
    kind: WorkdayKind


class MonthlySummaryOut(BaseModel):
    period_start: date
    period_end: date
    monthly_hours_theoretical: float
    monthly_salary_theoretical: float
    hours_real: float
    salary_real_estimated: float
