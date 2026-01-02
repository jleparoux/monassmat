from __future__ import annotations

from datetime import date, time
import calendar
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from . import crud
from .calculations import ContractFacts, WorkdayFacts
from .calculations import WorkdayKind as CalcWorkdayKind
from .calculations import (
    contract_monthly_hours,
    contract_monthly_salary,
    hours_between_times,
    unpaid_leave_deduction,
    workday_totals,
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
MONTH_NAMES = [
    "Janvier",
    "Fevrier",
    "Mars",
    "Avril",
    "Mai",
    "Juin",
    "Juillet",
    "Aout",
    "Septembre",
    "Octobre",
    "Novembre",
    "Decembre",
]


def parse_time(value: str | None, field_name: str) -> time | None:
    if not value:
        return None
    try:
        return time.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid {field_name}") from exc


def time_to_str(value: time | None) -> str:
    if not value:
        return ""
    return value.strftime("%H:%M")


def parse_optional_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def parse_optional_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def parse_days_list(value: str) -> list[date]:
    if not value:
        raise HTTPException(status_code=400, detail="Missing days")
    items: list[date] = []
    for raw in value.split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            items.append(date_from_iso(raw))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid day format") from exc
    if not items:
        raise HTTPException(status_code=400, detail="No valid days provided")
    return items


def summarize_period(
    contract,
    workdays,
    *,
    start: date,
    end: date,
) -> MonthlySummaryOut:
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
        for wd in workdays
    ]

    totals = workday_totals(
        wd_facts,
        hourly_rate=contract.hourly_rate,
        majoration_threshold=contract.majoration_threshold,
        majoration_rate=contract.majoration_rate,
    )

    work_days = sum(1 for wd in workdays if wd.kind == WorkdayKind.NORMAL)
    absence_days = sum(1 for wd in workdays if wd.kind == WorkdayKind.ABSENCE)
    unpaid_leave_days = sum(1 for wd in workdays if wd.kind == WorkdayKind.UNPAID_LEAVE)
    assmat_leave_days = sum(1 for wd in workdays if wd.kind == WorkdayKind.ASSMAT_LEAVE)
    holiday_days = sum(1 for wd in workdays if wd.kind == WorkdayKind.HOLIDAY)

    fee_meal_days = sum(1 for wd in workdays if wd.fee_meal)
    fee_maintenance_days = sum(1 for wd in workdays if wd.fee_maintenance)
    fee_meal_total = (contract.fee_meal_amount or 0.0) * fee_meal_days
    fee_maintenance_total = (contract.fee_maintenance_amount or 0.0) * fee_maintenance_days

    theo_hours = contract_monthly_hours(cf)
    theo_salary = contract_monthly_salary(cf)
    hours_delta = totals.total_hours - theo_hours

    unpaid_deduction = unpaid_leave_deduction(
        unpaid_leave_days,
        hours_per_week=contract.hours_per_week,
        days_per_week=contract.days_per_week,
        hourly_rate=contract.hourly_rate,
    )

    total_estimated = (
        totals.total_salary + fee_meal_total + fee_maintenance_total - unpaid_deduction
    )
    average_hours = totals.total_hours / work_days if work_days else 0.0

    return MonthlySummaryOut(
        period_start=start,
        period_end=end,
        monthly_hours_theoretical=theo_hours,
        monthly_salary_theoretical=theo_salary,
        hours_real=totals.total_hours,
        hours_normal=totals.normal_hours,
        hours_majorated=totals.majorated_hours,
        hours_delta=hours_delta,
        work_days=work_days,
        absence_days=absence_days,
        unpaid_leave_days=unpaid_leave_days,
        assmat_leave_days=assmat_leave_days,
        holiday_days=holiday_days,
        salary_base=totals.base_salary,
        salary_majoration=totals.majoration_salary,
        salary_real_estimated=totals.total_salary,
        fee_meal_days=fee_meal_days,
        fee_maintenance_days=fee_maintenance_days,
        fee_meal_total=fee_meal_total,
        fee_maintenance_total=fee_maintenance_total,
        unpaid_leave_deduction=unpaid_deduction,
        total_estimated=total_estimated,
        average_hours_per_day=average_hours,
    )


def build_month_summary(contract_id: int, start: date, end: date) -> MonthlySummaryOut:
    with session_scope() as db:
        contract = crud.get_contract(db, contract_id)
        if not contract:
            raise HTTPException(status_code=404, detail="Contract not found")

        workdays = crud.list_workdays(db, contract_id, start, end)
        return summarize_period(contract, workdays, start=start, end=end)


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
            start_time=payload.start_time,
            end_time=payload.end_time,
            fee_meal=payload.fee_meal,
            fee_maintenance=payload.fee_maintenance,
        )
        return {"id": wd.id, "contract_id": wd.contract_id, "date": wd.date}


@app.get("/api/contracts/{contract_id}/workdays")
def api_workdays(contract_id: int, start: date, end: date, db: Session = Depends(get_db)):
    items = crud.list_workdays(db, contract_id=contract_id, start=start, end=end)
    return {
        "items": [
            {
                "date": wd.date.isoformat(),
                "hours": wd.hours,
                "kind": wd.kind.value,
                "start_time": time_to_str(wd.start_time) or None,
                "end_time": time_to_str(wd.end_time) or None,
                "fee_meal": wd.fee_meal,
                "fee_maintenance": wd.fee_maintenance,
            }
            for wd in items
        ]
    }


def month_bounds(d: date) -> tuple[date, date]:
    last_day = calendar.monthrange(d.year, d.month)[1]
    return date(d.year, d.month, 1), date(d.year, d.month, last_day)


def year_bounds(year: int) -> tuple[date, date]:
    return date(year, 1, 1), date(year, 12, 31)


@app.get("/contracts/{contract_id}/summary/monthly", response_model=MonthlySummaryOut)
def monthly_summary(contract_id: int, start: date | None = None, end: date | None = None):
    if start and end:
        return build_month_summary(contract_id, start, end)

    base = start or end or date.today()
    start_date, end_date = month_bounds(base)
    return build_month_summary(contract_id, start_date, end_date)


def build_year_summary(contract_id: int, year: int) -> dict:
    with session_scope() as db:
        contract = crud.get_contract(db, contract_id)
        if not contract:
            raise HTTPException(status_code=404, detail="Contract not found")

        start, end = year_bounds(year)
        workdays = crud.list_workdays(db, contract_id, start, end)

        cf = ContractFacts(
            start_date=contract.start_date,
            end_date=contract.end_date,
            hours_per_week=contract.hours_per_week,
            weeks_per_year=contract.weeks_per_year,
            hourly_rate=contract.hourly_rate,
        )

        monthly_items = []
        totals = {
            "hours_real": 0.0,
            "hours_normal": 0.0,
            "hours_majorated": 0.0,
            "work_days": 0,
            "absence_days": 0,
            "unpaid_leave_days": 0,
            "assmat_leave_days": 0,
            "holiday_days": 0,
            "salary_base": 0.0,
            "salary_majoration": 0.0,
            "salary_real_estimated": 0.0,
            "fee_meal_days": 0,
            "fee_maintenance_days": 0,
            "fee_meal_total": 0.0,
            "fee_maintenance_total": 0.0,
            "unpaid_leave_deduction": 0.0,
            "total_estimated": 0.0,
        }

        for month in range(1, 13):
            month_start = date(year, month, 1)
            month_end = date(year, month, calendar.monthrange(year, month)[1])
            month_workdays = [wd for wd in workdays if wd.date.month == month]
            summary = summarize_period(
                contract, month_workdays, start=month_start, end=month_end
            )
            monthly_items.append(
                {"month": month, "label": MONTH_NAMES[month - 1], "summary": summary}
            )

            totals["hours_real"] += summary.hours_real
            totals["hours_normal"] += summary.hours_normal
            totals["hours_majorated"] += summary.hours_majorated
            totals["work_days"] += summary.work_days
            totals["absence_days"] += summary.absence_days
            totals["unpaid_leave_days"] += summary.unpaid_leave_days
            totals["assmat_leave_days"] += summary.assmat_leave_days
            totals["holiday_days"] += summary.holiday_days
            totals["salary_base"] += summary.salary_base
            totals["salary_majoration"] += summary.salary_majoration
            totals["salary_real_estimated"] += summary.salary_real_estimated
            totals["fee_meal_days"] += summary.fee_meal_days
            totals["fee_maintenance_days"] += summary.fee_maintenance_days
            totals["fee_meal_total"] += summary.fee_meal_total
            totals["fee_maintenance_total"] += summary.fee_maintenance_total
            totals["unpaid_leave_deduction"] += summary.unpaid_leave_deduction
            totals["total_estimated"] += summary.total_estimated

        yearly_hours_theoretical = contract_monthly_hours(cf) * 12
        yearly_salary_theoretical = contract_monthly_salary(cf) * 12
        hours_delta = totals["hours_real"] - yearly_hours_theoretical
        average_hours = (
            totals["hours_real"] / totals["work_days"] if totals["work_days"] else 0.0
        )

        totals.update(
            {
                "hours_delta": hours_delta,
                "average_hours_per_day": average_hours,
                "yearly_hours_theoretical": yearly_hours_theoretical,
                "yearly_salary_theoretical": yearly_salary_theoretical,
            }
        )

        return {
            "year": year,
            "period_start": start,
            "period_end": end,
            "monthly_items": monthly_items,
            "totals": totals,
        }


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


@app.get("/contracts/{contract_id}/settings", response_class=HTMLResponse)
def contract_settings(contract_id: int, request: Request, db: Session = Depends(get_db)):
    contract = crud.get_contract(db, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    return templates.TemplateResponse(
        "contract_settings.html",
        {
            "request": request,
            "title": "Parametres",
            "contract_id": contract_id,
            "contract": contract,
        },
    )


@app.post("/contracts/{contract_id}/settings", response_class=HTMLResponse)
def save_contract_settings(
    contract_id: int,
    request: Request,
    start_date: str = Form(...),
    end_date: str | None = Form(None),
    hours_per_week: str = Form(...),
    weeks_per_year: str = Form(...),
    hourly_rate: str = Form(...),
    days_per_week: str | None = Form(None),
    majoration_threshold: str | None = Form(None),
    majoration_rate: str | None = Form(None),
    fee_meal_amount: str | None = Form(None),
    fee_maintenance_amount: str | None = Form(None),
    salary_net_ceiling: str | None = Form(None),
    db: Session = Depends(get_db),
):
    contract = crud.get_contract(db, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    contract.start_date = date_from_iso(start_date)
    contract.end_date = date_from_iso(end_date) if end_date else None
    contract.hours_per_week = float(hours_per_week)
    contract.weeks_per_year = float(weeks_per_year)
    contract.hourly_rate = float(hourly_rate)
    contract.days_per_week = parse_optional_int(days_per_week)
    contract.majoration_threshold = parse_optional_float(majoration_threshold)
    contract.majoration_rate = parse_optional_float(majoration_rate)
    contract.fee_meal_amount = parse_optional_float(fee_meal_amount)
    contract.fee_maintenance_amount = parse_optional_float(fee_maintenance_amount)
    contract.salary_net_ceiling = parse_optional_float(salary_net_ceiling)
    db.commit()

    return templates.TemplateResponse(
        "contract_settings.html",
        {
            "request": request,
            "title": "Parametres",
            "contract_id": contract_id,
            "contract": contract,
            "saved": True,
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
            "start_time": time_to_str(existing.start_time) if existing else "",
            "end_time": time_to_str(existing.end_time) if existing else "",
            "fee_meal": (existing.fee_meal if existing else False),
            "fee_maintenance": (existing.fee_maintenance if existing else False),
            "saved": False,
            "deleted": False,
            "has_entry": existing is not None,
        },
    )


@app.get("/contracts/{contract_id}/bulk_form", response_class=HTMLResponse)
def bulk_form(contract_id: int, days: str, request: Request):
    day_list = sorted(parse_days_list(days))
    count = len(day_list)
    days_value = ",".join(d.isoformat() for d in day_list)
    if count <= 6:
        days_label = ", ".join(d.isoformat() for d in day_list)
    else:
        days_label = f"{day_list[0].isoformat()} ... {day_list[-1].isoformat()}"

    return templates.TemplateResponse(
        "partials/bulk_form.html",
        {
            "request": request,
            "contract_id": contract_id,
            "count": count,
            "days_label": days_label,
            "days_value": days_value,
            "kinds": [k.value for k in WorkdayKind],
            "saved": False,
        },
    )


@app.get("/contracts/{contract_id}/month_summary", response_class=HTMLResponse)
def month_summary(
    contract_id: int,
    request: Request,
    start: date | None = None,
    end: date | None = None,
):
    if start and end:
        summary = build_month_summary(contract_id, start, end)
    else:
        base = start or end or date.today()
        start_date, end_date = month_bounds(base)
        summary = build_month_summary(contract_id, start_date, end_date)

    return templates.TemplateResponse(
        "partials/month_summary.html",
        {
            "request": request,
            **summary.model_dump(),
        },
    )


@app.get("/contracts/{contract_id}/year_summary", response_class=HTMLResponse)
def year_summary(
    contract_id: int,
    request: Request,
    year: int | None = None,
):
    target_year = year or date.today().year
    summary = build_year_summary(contract_id, target_year)
    return templates.TemplateResponse(
        "partials/year_summary.html",
        {
            "request": request,
            **summary,
        },
    )


@app.post("/contracts/{contract_id}/workdays", response_class=HTMLResponse)
def save_workday(
    contract_id: int,
    request: Request,
    date_str: str = Form(..., alias="date"),
    kind: str = Form(...),
    start_time: str | None = Form(None),
    end_time: str | None = Form(None),
    fee_meal: bool = Form(False),
    fee_maintenance: bool = Form(False),
    db: Session = Depends(get_db),
):
    day = date_from_iso(date_str)
    kind_enum = WorkdayKind(kind)

    start_value = parse_time(start_time, "start_time")
    end_value = parse_time(end_time, "end_time")

    if kind_enum == WorkdayKind.NORMAL:
        if not start_value or not end_value:
            raise HTTPException(status_code=400, detail="Start and end times required")
        hours = hours_between_times(start_value, end_value)
    else:
        hours = 0.0
        start_value = None
        end_value = None

    wd = crud.upsert_workday(
        db,
        contract_id=contract_id,
        day=day,
        hours=hours,
        kind=kind_enum,
        start_time=start_value,
        end_time=end_value,
        fee_meal=fee_meal,
        fee_maintenance=fee_maintenance,
    )
    db.commit()

    html = templates.get_template("partials/day_form.html").render(
        request=request,
        contract_id=contract_id,
        day=day.isoformat(),
        hours=wd.hours,
        kind=wd.kind.value,
        kinds=[k.value for k in WorkdayKind],
        start_time=time_to_str(wd.start_time),
        end_time=time_to_str(wd.end_time),
        fee_meal=wd.fee_meal,
        fee_maintenance=wd.fee_maintenance,
        saved=True,
        deleted=False,
        has_entry=True,
    )

    resp = HTMLResponse(html)
    resp.headers["HX-Trigger"] = "workday:changed"
    return resp


@app.post("/contracts/{contract_id}/workdays/bulk", response_class=HTMLResponse)
def save_workdays_bulk(
    contract_id: int,
    request: Request,
    days: str = Form(...),
    kind: str = Form(...),
    start_time: str | None = Form(None),
    end_time: str | None = Form(None),
    fee_meal: bool = Form(False),
    fee_maintenance: bool = Form(False),
    db: Session = Depends(get_db),
):
    contract = crud.get_contract(db, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    day_list = sorted(parse_days_list(days))
    kind_enum = WorkdayKind(kind)

    start_value = parse_time(start_time, "start_time")
    end_value = parse_time(end_time, "end_time")

    if kind_enum == WorkdayKind.NORMAL:
        if not start_value or not end_value:
            raise HTTPException(status_code=400, detail="Start and end times required")
        hours = hours_between_times(start_value, end_value)
    else:
        hours = 0.0
        start_value = None
        end_value = None

    for day in day_list:
        crud.upsert_workday(
            db,
            contract_id=contract_id,
            day=day,
            hours=hours,
            kind=kind_enum,
            start_time=start_value,
            end_time=end_value,
            fee_meal=fee_meal,
            fee_maintenance=fee_maintenance,
        )
    db.commit()

    if len(day_list) <= 6:
        days_label = ", ".join(d.isoformat() for d in day_list)
    else:
        days_label = f"{day_list[0].isoformat()} ... {day_list[-1].isoformat()}"

    html = templates.get_template("partials/bulk_form.html").render(
        request=request,
        contract_id=contract_id,
        count=len(day_list),
        days_label=days_label,
        days_value=",".join(d.isoformat() for d in day_list),
        kinds=[k.value for k in WorkdayKind],
        saved=True,
    )

    resp = HTMLResponse(html)
    resp.headers["HX-Trigger"] = "workday:changed"
    return resp


@app.post("/contracts/{contract_id}/workdays/bulk_delete", response_class=HTMLResponse)
def delete_workdays_bulk(
    contract_id: int,
    request: Request,
    days: str = Form(...),
    db: Session = Depends(get_db),
):
    contract = crud.get_contract(db, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    day_list = sorted(parse_days_list(days))
    deleted_any = False
    for day in day_list:
        deleted = crud.delete_workday(db, contract_id=contract_id, day=day)
        deleted_any = deleted_any or deleted
    db.commit()

    if len(day_list) <= 6:
        days_label = ", ".join(d.isoformat() for d in day_list)
    else:
        days_label = f"{day_list[0].isoformat()} ... {day_list[-1].isoformat()}"

    html = templates.get_template("partials/bulk_form.html").render(
        request=request,
        contract_id=contract_id,
        count=len(day_list),
        days_label=days_label,
        days_value=",".join(d.isoformat() for d in day_list),
        kinds=[k.value for k in WorkdayKind],
        saved=deleted_any,
    )

    resp = HTMLResponse(html)
    resp.headers["HX-Trigger"] = "workday:changed"
    return resp


@app.post("/contracts/{contract_id}/workdays/delete", response_class=HTMLResponse)
def delete_workday(
    contract_id: int,
    request: Request,
    date_str: str = Form(..., alias="date"),
    db: Session = Depends(get_db),
):
    day = date_from_iso(date_str)
    deleted = crud.delete_workday(db, contract_id=contract_id, day=day)
    db.commit()

    html = templates.get_template("partials/day_form.html").render(
        request=request,
        contract_id=contract_id,
        day=day.isoformat(),
        hours=0,
        kind=WorkdayKind.NORMAL.value,
        kinds=[k.value for k in WorkdayKind],
        start_time="",
        end_time="",
        fee_meal=False,
        fee_maintenance=False,
        saved=False,
        deleted=deleted,
        has_entry=False,
    )

    resp = HTMLResponse(html)
    resp.headers["HX-Trigger"] = "workday:changed"
    return resp
