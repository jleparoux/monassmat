from __future__ import annotations

from datetime import date, time, timedelta
import calendar
import os
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
from .models import Child, Contract, WorkdayKind
from .schemas import MonthlySummaryOut, WorkdayUpsertIn

BASE_DIR = Path(__file__).resolve().parents[2]  # .../monassmat/


def resolve_frontend_dir() -> Path:
    env_path = os.environ.get("FRONTEND_DIR")
    candidates = []
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(BASE_DIR / "frontend")
    candidates.append(Path.cwd() / "frontend")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


FRONTEND_DIR = resolve_frontend_dir()

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


def iter_days(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def snapshot_from_contract(contract, valid_from: date) -> dict:
    return {
        "valid_from": valid_from,
        "hours_per_week": contract.hours_per_week,
        "weeks_per_year": contract.weeks_per_year,
        "hourly_rate": contract.hourly_rate,
        "days_per_week": contract.days_per_week,
        "majoration_threshold": contract.majoration_threshold,
        "majoration_rate": contract.majoration_rate,
        "fee_meal_amount": contract.fee_meal_amount,
        "fee_maintenance_amount": contract.fee_maintenance_amount,
        "salary_net_ceiling": contract.salary_net_ceiling,
    }


def snapshot_from_row(row) -> dict:
    return {
        "valid_from": row.valid_from,
        "hours_per_week": row.hours_per_week,
        "weeks_per_year": row.weeks_per_year,
        "hourly_rate": row.hourly_rate,
        "days_per_week": row.days_per_week,
        "majoration_threshold": row.majoration_threshold,
        "majoration_rate": row.majoration_rate,
        "fee_meal_amount": row.fee_meal_amount,
        "fee_maintenance_amount": row.fee_maintenance_amount,
        "salary_net_ceiling": row.salary_net_ceiling,
    }


def build_settings_timeline(contract, snapshots: list) -> list[dict]:
    if not snapshots:
        return [snapshot_from_contract(contract, contract.start_date)]
    ordered = [snapshot_from_row(row) for row in snapshots]
    ordered.sort(key=lambda item: item["valid_from"])
    return ordered


def summarize_period(
    contract,
    workdays,
    settings_snapshots,
    *,
    start: date,
    end: date,
) -> MonthlySummaryOut:
    settings = build_settings_timeline(contract, settings_snapshots)
    settings_index = 0

    workdays_by_date = {wd.date: wd for wd in workdays}

    theo_hours = 0.0
    theo_salary = 0.0
    real_hours = 0.0
    normal_hours = 0.0
    majorated_hours = 0.0
    salary_base = 0.0
    salary_majoration = 0.0

    work_days = 0
    absence_days = 0
    unpaid_leave_days = 0
    assmat_leave_days = 0
    holiday_days = 0

    fee_meal_days = 0
    fee_maintenance_days = 0
    fee_meal_total = 0.0
    fee_maintenance_total = 0.0
    unpaid_deduction = 0.0

    for day in iter_days(start, end):
        while (
            settings_index + 1 < len(settings)
            and settings[settings_index + 1]["valid_from"] <= day
        ):
            settings_index += 1
        current = settings[settings_index]

        facts = ContractFacts(
            start_date=contract.start_date,
            end_date=contract.end_date,
            hours_per_week=current["hours_per_week"],
            weeks_per_year=current["weeks_per_year"],
            hourly_rate=current["hourly_rate"],
        )
        days_in_month = calendar.monthrange(day.year, day.month)[1]
        theo_hours += contract_monthly_hours(facts) / days_in_month
        theo_salary += contract_monthly_salary(facts) / days_in_month

        wd = workdays_by_date.get(day)
        if not wd:
            continue

        if wd.kind == WorkdayKind.NORMAL:
            work_days += 1
        elif wd.kind == WorkdayKind.ABSENCE:
            absence_days += 1
        elif wd.kind == WorkdayKind.UNPAID_LEAVE:
            unpaid_leave_days += 1
            unpaid_deduction += unpaid_leave_deduction(
                1,
                hours_per_week=current["hours_per_week"],
                days_per_week=current["days_per_week"],
                hourly_rate=current["hourly_rate"],
            )
        elif wd.kind == WorkdayKind.ASSMAT_LEAVE:
            assmat_leave_days += 1
        elif wd.kind == WorkdayKind.HOLIDAY:
            holiday_days += 1

        if wd.kind == WorkdayKind.NORMAL and wd.hours > 0:
            wd_totals = workday_totals(
                [
                    WorkdayFacts(
                        day=wd.date,
                        hours=wd.hours,
                        kind=CalcWorkdayKind(wd.kind.value),
                    )
                ],
                hourly_rate=current["hourly_rate"],
                majoration_threshold=current["majoration_threshold"],
                majoration_rate=current["majoration_rate"],
            )
            real_hours += wd_totals.total_hours
            normal_hours += wd_totals.normal_hours
            majorated_hours += wd_totals.majorated_hours
            salary_base += wd_totals.base_salary
            salary_majoration += wd_totals.majoration_salary

        if wd.fee_meal:
            fee_meal_days += 1
            fee_meal_total += current["fee_meal_amount"] or 0.0
        if wd.fee_maintenance:
            fee_maintenance_days += 1
            fee_maintenance_total += current["fee_maintenance_amount"] or 0.0

    total_salary = salary_base + salary_majoration
    hours_delta = real_hours - theo_hours
    total_estimated = total_salary + fee_meal_total + fee_maintenance_total - unpaid_deduction
    average_hours = real_hours / work_days if work_days else 0.0

    return MonthlySummaryOut(
        period_start=start,
        period_end=end,
        monthly_hours_theoretical=theo_hours,
        monthly_salary_theoretical=theo_salary,
        hours_real=real_hours,
        hours_normal=normal_hours,
        hours_majorated=majorated_hours,
        hours_delta=hours_delta,
        work_days=work_days,
        absence_days=absence_days,
        unpaid_leave_days=unpaid_leave_days,
        assmat_leave_days=assmat_leave_days,
        holiday_days=holiday_days,
        salary_base=salary_base,
        salary_majoration=salary_majoration,
        salary_real_estimated=total_salary,
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
        snapshots = crud.list_settings_snapshots(db, contract_id)
        return summarize_period(
            contract, workdays, snapshots, start=start, end=end
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
        snapshots = crud.list_settings_snapshots(db, contract_id)

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
            "yearly_hours_theoretical": 0.0,
            "yearly_salary_theoretical": 0.0,
        }

        for month in range(1, 13):
            month_start = date(year, month, 1)
            month_end = date(year, month, calendar.monthrange(year, month)[1])
            month_workdays = [wd for wd in workdays if wd.date.month == month]
            summary = summarize_period(
                contract,
                month_workdays,
                snapshots,
                start=month_start,
                end=month_end,
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
            totals["yearly_hours_theoretical"] += summary.monthly_hours_theoretical
            totals["yearly_salary_theoretical"] += summary.monthly_salary_theoretical

        hours_delta = totals["hours_real"] - totals["yearly_hours_theoretical"]
        average_hours = (
            totals["hours_real"] / totals["work_days"] if totals["work_days"] else 0.0
        )

        totals.update(
            {
                "hours_delta": hours_delta,
                "average_hours_per_day": average_hours,
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
    snapshots = crud.list_settings_snapshots(db, contract_id)

    return templates.TemplateResponse(
        "contract_settings.html",
        {
            "request": request,
            "title": "Parametres",
            "contract_id": contract_id,
            "contract": contract,
            "snapshots": snapshots,
            "effective_from": date.today().isoformat(),
        },
    )


@app.post("/contracts/{contract_id}/settings", response_class=HTMLResponse)
def save_contract_settings(
    contract_id: int,
    request: Request,
    contract_name: str | None = Form(None),
    start_date: str = Form(...),
    end_date: str | None = Form(None),
    effective_from: str = Form(...),
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

    previous_values = {
        "hours_per_week": contract.hours_per_week,
        "weeks_per_year": contract.weeks_per_year,
        "hourly_rate": contract.hourly_rate,
        "days_per_week": contract.days_per_week,
        "majoration_threshold": contract.majoration_threshold,
        "majoration_rate": contract.majoration_rate,
        "fee_meal_amount": contract.fee_meal_amount,
        "fee_maintenance_amount": contract.fee_maintenance_amount,
        "salary_net_ceiling": contract.salary_net_ceiling,
    }

    contract.name = contract_name.strip() if contract_name else None
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

    snapshots = crud.list_settings_snapshots(db, contract_id)
    effective_from_date = date_from_iso(effective_from)
    if not snapshots:
        crud.upsert_settings_snapshot(
            db,
            contract_id=contract_id,
            valid_from=contract.start_date,
            hours_per_week=previous_values["hours_per_week"],
            weeks_per_year=previous_values["weeks_per_year"],
            hourly_rate=previous_values["hourly_rate"],
            days_per_week=previous_values["days_per_week"],
            majoration_threshold=previous_values["majoration_threshold"],
            majoration_rate=previous_values["majoration_rate"],
            fee_meal_amount=previous_values["fee_meal_amount"],
            fee_maintenance_amount=previous_values["fee_maintenance_amount"],
            salary_net_ceiling=previous_values["salary_net_ceiling"],
        )
    crud.upsert_settings_snapshot(
        db,
        contract_id=contract_id,
        valid_from=effective_from_date,
        hours_per_week=contract.hours_per_week,
        weeks_per_year=contract.weeks_per_year,
        hourly_rate=contract.hourly_rate,
        days_per_week=contract.days_per_week,
        majoration_threshold=contract.majoration_threshold,
        majoration_rate=contract.majoration_rate,
        fee_meal_amount=contract.fee_meal_amount,
        fee_maintenance_amount=contract.fee_maintenance_amount,
        salary_net_ceiling=contract.salary_net_ceiling,
    )
    db.commit()
    snapshots = crud.list_settings_snapshots(db, contract_id)

    return templates.TemplateResponse(
        "contract_settings.html",
        {
            "request": request,
            "title": "Parametres",
            "contract_id": contract_id,
            "contract": contract,
            "snapshots": snapshots,
            "effective_from": effective_from,
            "saved": True,
        },
    )


@app.get("/contracts/{contract_id}/settings_snapshot", response_class=HTMLResponse)
def edit_settings_snapshot(
    contract_id: int,
    request: Request,
    valid_from: date,
    db: Session = Depends(get_db),
):
    contract = crud.get_contract(db, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    snapshot = crud.get_settings_snapshot(
        db, contract_id=contract_id, valid_from=valid_from
    )
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    return templates.TemplateResponse(
        "settings_snapshot_form.html",
        {
            "request": request,
            "title": "Modifier snapshot",
            "contract": contract,
            "contract_id": contract_id,
            "snapshot": snapshot,
        },
    )


@app.post("/contracts/{contract_id}/settings_snapshot", response_class=HTMLResponse)
def save_settings_snapshot(
    contract_id: int,
    request: Request,
    original_valid_from: str = Form(...),
    valid_from: str = Form(...),
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

    original_valid_from_date = date_from_iso(original_valid_from)
    valid_from_date = date_from_iso(valid_from)
    snapshot = crud.get_settings_snapshot(
        db, contract_id=contract_id, valid_from=original_valid_from_date
    )
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    if valid_from_date != original_valid_from_date:
        existing = crud.get_settings_snapshot(
            db, contract_id=contract_id, valid_from=valid_from_date
        )
        if existing:
            return templates.TemplateResponse(
                "settings_snapshot_form.html",
                {
                    "request": request,
                    "title": "Modifier snapshot",
                    "contract": contract,
                    "contract_id": contract_id,
                    "snapshot": snapshot,
                    "error": "Un snapshot existe deja a cette date.",
                },
            )

        deleted = crud.delete_settings_snapshot(
            db, contract_id=contract_id, valid_from=original_valid_from_date
        )
        if not deleted:
            raise HTTPException(status_code=404, detail="Snapshot not found")

    crud.upsert_settings_snapshot(
        db,
        contract_id=contract_id,
        valid_from=valid_from_date,
        hours_per_week=float(hours_per_week),
        weeks_per_year=float(weeks_per_year),
        hourly_rate=float(hourly_rate),
        days_per_week=parse_optional_int(days_per_week),
        majoration_threshold=parse_optional_float(majoration_threshold),
        majoration_rate=parse_optional_float(majoration_rate),
        fee_meal_amount=parse_optional_float(fee_meal_amount),
        fee_maintenance_amount=parse_optional_float(fee_maintenance_amount),
        salary_net_ceiling=parse_optional_float(salary_net_ceiling),
    )
    db.commit()

    snapshot = crud.get_settings_snapshot(
        db, contract_id=contract_id, valid_from=valid_from_date
    )
    return templates.TemplateResponse(
        "settings_snapshot_form.html",
        {
            "request": request,
            "title": "Modifier snapshot",
            "contract": contract,
            "contract_id": contract_id,
            "snapshot": snapshot,
            "saved": True,
        },
    )


@app.post("/contracts/{contract_id}/settings_snapshot/delete", response_class=HTMLResponse)
def delete_settings_snapshot(
    contract_id: int,
    request: Request,
    valid_from: str = Form(...),
    db: Session = Depends(get_db),
):
    contract = crud.get_contract(db, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    valid_from_date = date_from_iso(valid_from)
    deleted = crud.delete_settings_snapshot(
        db, contract_id=contract_id, valid_from=valid_from_date
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    db.commit()

    snapshots = crud.list_settings_snapshots(db, contract_id)
    return templates.TemplateResponse(
        "contract_settings.html",
        {
            "request": request,
            "title": "Parametres",
            "contract_id": contract_id,
            "contract": contract,
            "snapshots": snapshots,
            "effective_from": date.today().isoformat(),
            "deleted": True,
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


@app.get("/contracts/{contract_id}/summary/year", response_class=HTMLResponse)
def year_summary_page(
    contract_id: int,
    request: Request,
    year: int | None = None,
):
    target_year = year or date.today().year
    with session_scope() as db:
        contract = crud.get_contract(db, contract_id)
        if not contract:
            raise HTTPException(status_code=404, detail="Contract not found")
        contract_name = contract.name
    summary = build_year_summary(contract_id, target_year)
    return templates.TemplateResponse(
        "year_summary_page.html",
        {
            "request": request,
            "title": "Synthese annuelle",
            "contract_id": contract_id,
            "contract_name": contract_name,
            "prev_year": target_year - 1,
            "next_year": target_year + 1,
            **summary,
        },
    )


@app.get("/contracts", response_class=HTMLResponse)
def contracts_summary(request: Request, db: Session = Depends(get_db)):
    contracts = crud.list_contracts(db)
    items = []
    for contract in contracts:
        facts = ContractFacts(
            start_date=contract.start_date,
            end_date=contract.end_date,
            hours_per_week=contract.hours_per_week,
            weeks_per_year=contract.weeks_per_year,
            hourly_rate=contract.hourly_rate,
        )
        items.append(
            {
                "id": contract.id,
                "name": contract.name,
                "child_name": contract.child.name if contract.child else "—",
                "start_date": contract.start_date,
                "end_date": contract.end_date,
                "hours_per_week": contract.hours_per_week,
                "weeks_per_year": contract.weeks_per_year,
                "hourly_rate": contract.hourly_rate,
                "monthly_hours_theoretical": contract_monthly_hours(facts),
                "monthly_salary_theoretical": contract_monthly_salary(facts),
                "is_active": contract.end_date is None or contract.end_date >= date.today(),
            }
        )
    return templates.TemplateResponse(
        "contracts_summary.html",
        {
            "request": request,
            "title": "Contrats",
            "items": items,
        },
    )


@app.get("/contracts/new", response_class=HTMLResponse)
def new_contract(request: Request):
    return templates.TemplateResponse(
        "contract_new.html",
        {
            "request": request,
            "title": "Nouveau contrat",
        },
    )


@app.post("/contracts/new", response_class=HTMLResponse)
def create_contract(
    request: Request,
    contract_name: str | None = Form(None),
    child_name: str = Form(...),
    child_birth_date: str = Form(...),
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
    child = Child(
        name=child_name.strip(),
        birth_date=date_from_iso(child_birth_date),
    )
    contract = Contract(
        child=child,
        name=contract_name.strip() if contract_name else None,
        start_date=date_from_iso(start_date),
        end_date=date_from_iso(end_date) if end_date else None,
        hours_per_week=float(hours_per_week),
        weeks_per_year=float(weeks_per_year),
        hourly_rate=float(hourly_rate),
        days_per_week=parse_optional_int(days_per_week),
        majoration_threshold=parse_optional_float(majoration_threshold),
        majoration_rate=parse_optional_float(majoration_rate),
        fee_meal_amount=parse_optional_float(fee_meal_amount),
        fee_maintenance_amount=parse_optional_float(fee_maintenance_amount),
        salary_net_ceiling=parse_optional_float(salary_net_ceiling),
    )
    db.add(child)
    db.add(contract)
    db.flush()

    crud.upsert_settings_snapshot(
        db,
        contract_id=contract.id,
        valid_from=contract.start_date,
        hours_per_week=contract.hours_per_week,
        weeks_per_year=contract.weeks_per_year,
        hourly_rate=contract.hourly_rate,
        days_per_week=contract.days_per_week,
        majoration_threshold=contract.majoration_threshold,
        majoration_rate=contract.majoration_rate,
        fee_meal_amount=contract.fee_meal_amount,
        fee_maintenance_amount=contract.fee_maintenance_amount,
        salary_net_ceiling=contract.salary_net_ceiling,
    )
    db.commit()

    return templates.TemplateResponse(
        "contract_new.html",
        {
            "request": request,
            "title": "Nouveau contrat",
            "saved": True,
            "contract_id": contract.id,
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
