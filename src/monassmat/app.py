from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from . import crud
from .calculations import ContractFacts, Period, WorkdayFacts
from .calculations import WorkdayKind as CalcWorkdayKind
from .calculations import (
    contract_monthly_hours,
    contract_monthly_salary,
    hours_in_period,
    value_hours,
)
from .db import get_db, session_scope
from .models import WorkdayKind
from .schemas import MonthlySummaryOut, WorkdayUpsertIn

BASE_DIR = Path(__file__).resolve().parents[2]  # .../monassmat/
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(title="MonAssmat")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(FRONTEND_DIR / "templates"))

date_from_iso = date.fromisoformat


def build_month_summary(contract_id: int, start: date, end: date) -> MonthlySummaryOut:
    with session_scope() as db:
        contract = crud.get_contract(db, contract_id)
        if not contract:
            raise HTTPException(status_code=404, detail="Contract not found")

        wds = crud.list_workdays(db, contract_id, start, end)

    cf = ContractFacts(
        start_date=contract.start_date,
        end_date=contract.end_date,
        hours_per_week=contract.hours_per_week,
        weeks_per_year=contract.weeks_per_year,
        hourly_rate=contract.hourly_rate,
    )

    wd_facts = [
        WorkdayFacts(
            day=wd.date,
            hours=wd.hours,
            kind=CalcWorkdayKind(wd.kind.value),
        )
        for wd in wds
    ]

    period = Period(start=start, end=end)

    theo_hours = contract_monthly_hours(cf)
    theo_salary = contract_monthly_salary(cf)

    real_hours = hours_in_period(wd_facts, period)
    real_salary_est = value_hours(real_hours, cf.hourly_rate)

    return MonthlySummaryOut(
        period_start=start,
        period_end=end,
        monthly_hours_theoretical=theo_hours,
        monthly_salary_theoretical=theo_salary,
        hours_real=real_hours,
        salary_real_estimated=real_salary_est,
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/contracts/{contract_id}/workdays")
def upsert_workday_api(contract_id: int, payload: WorkdayUpsertIn):
    with session_scope() as db:
        contract = crud.get_contract(db, contract_id)
        if not contract:
            raise HTTPException(status_code=404, detail="Contract not found")

        wd = crud.upsert_workday(
            db,
            contract_id=contract_id,
            day=payload.date,
            hours=payload.hours,
            kind=payload.kind,
        )
        return {"id": wd.id, "contract_id": wd.contract_id, "date": wd.date}


@app.get("/api/contracts/{contract_id}/workdays")
def api_workdays(contract_id: int, start: date, end: date, db: Session = Depends(get_db)):
    items = crud.list_workdays(db, contract_id=contract_id, start=start, end=end)
    return {
        "items": [
            {"date": wd.date.isoformat(), "hours": wd.hours, "kind": wd.kind.value}
            for wd in items
        ]
    }


@app.get("/contracts/{contract_id}/summary/monthly", response_model=MonthlySummaryOut)
def monthly_summary(contract_id: int, start: date, end: date):
    return build_month_summary(contract_id, start, end)


@app.get("/contracts/{contract_id}/calendar", response_class=HTMLResponse)
def calendar_page(contract_id: int, request: Request, initial_date: date | None = None):
    if initial_date is None:
        initial_date = date.today()
    return templates.TemplateResponse(
        "calendar.html",
        {
            "request": request,
            "title": "Calendrier",
            "contract_id": contract_id,
            "initial_date": initial_date.isoformat(),
        },
    )


@app.get("/contracts/{contract_id}/day_form", response_class=HTMLResponse)
def day_form(contract_id: int, day: date, request: Request, db: Session = Depends(get_db)):
    wds = crud.list_workdays(db, contract_id=contract_id, start=day, end=day)
    existing = wds[0] if wds else None

    return templates.TemplateResponse(
        "partials/day_form.html",
        {
            "request": request,
            "contract_id": contract_id,
            "day": day.isoformat(),
            "hours": (existing.hours if existing else 0),
            "kind": (existing.kind.value if existing else WorkdayKind.NORMAL.value),
            "kinds": [k.value for k in WorkdayKind],
            "saved": False,
        },
    )


@app.get("/contracts/{contract_id}/month_summary", response_class=HTMLResponse)
def month_summary(contract_id: int, start: date, end: date, request: Request):
    summary = build_month_summary(contract_id, start, end)
    return templates.TemplateResponse(
        "partials/month_summary.html",
        {
            "request": request,
            "period_start": summary.period_start,
            "period_end": summary.period_end,
            "monthly_hours_theoretical": summary.monthly_hours_theoretical,
            "monthly_salary_theoretical": summary.monthly_salary_theoretical,
            "hours_real": summary.hours_real,
            "salary_real_estimated": summary.salary_real_estimated,
        },
    )


@app.post("/contracts/{contract_id}/workdays", response_class=HTMLResponse)
def save_workday(
    contract_id: int,
    request: Request,
    date_str: str = Form(..., alias="date"),
    hours: float = Form(...),
    kind: str = Form(...),
    db: Session = Depends(get_db),
):
    day = date_from_iso(date_str)
    wd = crud.upsert_workday(
        db,
        contract_id=contract_id,
        day=day,
        hours=hours,
        kind=WorkdayKind(kind),
    )
    db.commit()

    html = templates.get_template("partials/day_form.html").render(
        request=request,
        contract_id=contract_id,
        day=day.isoformat(),
        hours=wd.hours,
        kind=wd.kind.value,
        kinds=[k.value for k in WorkdayKind],
        saved=True,
    )

    resp = HTMLResponse(html)
    resp.headers["HX-Trigger"] = "workday:changed"
    return resp
