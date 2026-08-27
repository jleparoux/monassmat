from __future__ import annotations

import calendar
import csv
import io
import json
import os
import urllib.request
from datetime import date, time, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from . import crud
from .calculations import (
    ContractFacts,
    PaidLeaveMethod,
    Period,
    WorkdayFacts,
    absence_deduction_46_weeks,
    absence_deduction_52_weeks,
    allocate_weekly_hours,
    contract_monthly_hours,
    contract_monthly_salary,
    hours_between_times,
    paid_leave_acquired_days,
    paid_leave_acquired_days_v1,
    paid_leave_value,
    parse_holidays_response,
    prepare_pajemploi_declaration,
    scheduled_hours_for_day,
    validate_majoration_coefficient,
    validate_regular_contract_weeks,
    validate_weekly_schedule,
    weekly_schedule_total,
)
from .calculations import (
    ContractYearMode as CalcContractYearMode,
)
from .calculations import WorkdayKind as CalcWorkdayKind
from .db import get_db, session_scope
from .models import Contract, ContractYearMode, PaymentKind, WorkdayKind
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


@app.get("/")
def home():
    return RedirectResponse(url="/contracts", status_code=302)


date_from_iso = date.fromisoformat
MONTH_NAMES = [
    "Janvier",
    "Février",
    "Mars",
    "Avril",
    "Mai",
    "Juin",
    "Juillet",
    "Août",
    "Septembre",
    "Octobre",
    "Novembre",
    "Décembre",
]
WEEKLY_SCHEDULE_FIELDS = (
    "monday_hours",
    "tuesday_hours",
    "wednesday_hours",
    "thursday_hours",
    "friday_hours",
    "saturday_hours",
    "sunday_hours",
)


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


def parse_optional_positive_float(
    value: str | None,
    *,
    field_label: str,
) -> float | None:
    parsed = parse_optional_float(value)
    if parsed is not None and parsed <= 0:
        raise HTTPException(
            status_code=400,
            detail=f"{field_label} doit etre strictement positif.",
        )
    return parsed


def parse_majoration_coefficient(value: str | None) -> float | None:
    coefficient = parse_optional_float(value)
    try:
        validate_majoration_coefficient(coefficient)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Le coefficient de majoration doit etre au minimum de 1,10.",
        ) from exc
    return coefficient


def parse_regular_contract_mode(
    year_mode: str,
    weeks_per_year: str,
) -> tuple[ContractYearMode, float]:
    try:
        model_mode = ContractYearMode(year_mode)
        calc_mode = CalcContractYearMode(year_mode)
        weeks = float(weeks_per_year)
        validate_regular_contract_weeks(mode=calc_mode, weeks_per_year=weeks)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                "Le type d'accueil et le nombre de semaines sont incoherents: "
                "52 semaines exactement, ou 46 semaines ou moins."
            ),
        ) from exc
    return model_mode, weeks


def parse_weekly_schedule(
    *,
    hours_per_week: float,
    required: bool,
    monday_hours: str | None,
    tuesday_hours: str | None,
    wednesday_hours: str | None,
    thursday_hours: str | None,
    friday_hours: str | None,
    saturday_hours: str | None,
    sunday_hours: str | None,
) -> dict[str, float | None]:
    raw_values = (
        monday_hours,
        tuesday_hours,
        wednesday_hours,
        thursday_hours,
        friday_hours,
        saturday_hours,
        sunday_hours,
    )
    try:
        if all(value is None or value == "" for value in raw_values):
            schedule: tuple[float | None, ...] = (None,) * 7
        else:
            schedule = tuple(
                float(value) if value is not None and value != "" else 0.0
                for value in raw_values
            )
        validate_weekly_schedule(
            schedule,
            hours_per_week=hours_per_week,
            required=required,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                "Le planning doit couvrir les sept jours et son total doit "
                "correspondre aux heures hebdomadaires du contrat."
            ),
        ) from exc
    return dict(zip(WEEKLY_SCHEDULE_FIELDS, schedule, strict=True))


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
        "year_mode": contract.year_mode,
        "hourly_rate": contract.hourly_rate,
        "complementary_hourly_rate": getattr(
            contract,
            "complementary_hourly_rate",
            None,
        ),
        "days_per_week": contract.days_per_week,
        "monday_hours": contract.monday_hours,
        "tuesday_hours": contract.tuesday_hours,
        "wednesday_hours": contract.wednesday_hours,
        "thursday_hours": contract.thursday_hours,
        "friday_hours": contract.friday_hours,
        "saturday_hours": contract.saturday_hours,
        "sunday_hours": contract.sunday_hours,
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
        "year_mode": row.year_mode,
        "hourly_rate": row.hourly_rate,
        "complementary_hourly_rate": getattr(
            row,
            "complementary_hourly_rate",
            None,
        ),
        "days_per_week": row.days_per_week,
        "monday_hours": row.monday_hours,
        "tuesday_hours": row.tuesday_hours,
        "wednesday_hours": row.wednesday_hours,
        "thursday_hours": row.thursday_hours,
        "friday_hours": row.friday_hours,
        "saturday_hours": row.saturday_hours,
        "sunday_hours": row.sunday_hours,
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


def settings_for_day(settings: list[dict], day: date) -> dict:
    index = 0
    for i in range(len(settings) - 1):
        if settings[i + 1]["valid_from"] <= day:
            index = i + 1
        else:
            break
    return settings[index]


def contract_is_active_on(contract, day: date) -> bool:
    return contract.start_date <= day and (
        contract.end_date is None or day <= contract.end_date
    )


def schedule_from_settings(settings: dict) -> tuple[float | None, ...]:
    return tuple(settings[field_name] for field_name in WEEKLY_SCHEDULE_FIELDS)


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def weeks_overlapping_year(year: int) -> list[date]:
    first = week_start(date(year, 1, 1))
    last = week_start(date(year, 12, 31))
    weeks = []
    current = first
    while current <= last:
        weeks.append(current)
        current += timedelta(days=7)
    return weeks


def expanded_week_bounds(start: date, end: date) -> tuple[date, date]:
    return week_start(start), end + timedelta(days=6 - end.weekday())


def allocate_period_worked_hours(workdays, settings: list[dict]) -> dict:
    workdays_by_week: dict[date, list[WorkdayFacts]] = {}
    for workday in workdays:
        if workday.kind != WorkdayKind.NORMAL:
            continue
        monday = week_start(workday.date)
        workdays_by_week.setdefault(monday, []).append(
            WorkdayFacts(
                day=workday.date,
                hours=workday.hours,
                kind=CalcWorkdayKind.NORMAL,
            )
        )

    result = {}
    for monday, weekly_workdays in workdays_by_week.items():
        current = settings_for_day(settings, monday)
        result.update(
            allocate_weekly_hours(
                weekly_workdays,
                contracted_hours=current["hours_per_week"],
            )
        )
    return result


def calculate_unpaid_absence_deduction(
    contract,
    workdays_by_date: dict,
    settings: list[dict],
    *,
    start: date,
    end: date,
) -> tuple[float, bool, str]:
    unpaid_days = [
        day
        for day, workday in workdays_by_date.items()
        if start <= day <= end
        and contract_is_active_on(contract, day)
        and workday.kind == WorkdayKind.UNPAID_LEAVE
    ]
    if not unpaid_days:
        return 0.0, True, "Aucune absence non remuneree saisie."

    deduction = 0.0
    missing_schedule = False
    mixed_modes = False
    used_52_week_formula = False
    used_46_week_formula = False
    months = sorted({(day.year, day.month) for day in unpaid_days})

    for year, month in months:
        month_start = date(year, month, 1)
        month_end = date(year, month, calendar.monthrange(year, month)[1])
        active_days = [
            day
            for day in iter_days(month_start, month_end)
            if contract_is_active_on(contract, day)
        ]
        month_settings = [settings_for_day(settings, day) for day in active_days]
        modes = {item["year_mode"] for item in month_settings}
        if len(modes) != 1:
            mixed_modes = True
            continue

        scheduled_hours_by_day = {}
        month_missing_schedule = False
        for day, current in zip(active_days, month_settings, strict=True):
            hours = scheduled_hours_for_day(schedule_from_settings(current), day)
            if hours is None:
                missing_schedule = True
                month_missing_schedule = True
                break
            scheduled_hours_by_day[day] = hours
        if month_missing_schedule:
            continue

        monthly_salary = sum(
            contract_monthly_salary(
                ContractFacts(
                    start_date=contract.start_date,
                    end_date=contract.end_date,
                    hours_per_week=current["hours_per_week"],
                    weeks_per_year=current["weeks_per_year"],
                    hourly_rate=current["hourly_rate"],
                )
            )
            / calendar.monthrange(day.year, day.month)[1]
            for day, current in zip(active_days, month_settings, strict=True)
        )
        month_unpaid_days = [
            day
            for day in unpaid_days
            if day.year == year and day.month == month
        ]

        mode = next(iter(modes))
        if mode == ContractYearMode.COMPLETE:
            absence_hours = sum(
                scheduled_hours_by_day[day]
                for day in month_unpaid_days
            )
            if absence_hours > 0:
                deduction += absence_deduction_52_weeks(
                    monthly_salary=monthly_salary,
                    absence_hours=absence_hours,
                    scheduled_hours_in_month=sum(scheduled_hours_by_day.values()),
                )
            used_52_week_formula = True
            continue

        scheduled_days = [
            day
            for day, hours in scheduled_hours_by_day.items()
            if hours > 0
        ]
        absence_days = sum(
            1
            for day in month_unpaid_days
            if scheduled_hours_by_day[day] > 0
        )
        if absence_days > 0:
            deduction += absence_deduction_46_weeks(
                monthly_salary=monthly_salary,
                absence_days=absence_days,
                scheduled_days_in_month=len(scheduled_days),
            )
        used_46_week_formula = True

    if mixed_modes:
        return (
            deduction,
            False,
            "Deduction non calculee: le mode d'accueil change au cours du mois.",
        )
    if missing_schedule:
        return (
            deduction,
            False,
            "Deduction non calculee: le planning contractuel est manquant.",
        )
    if used_46_week_formula and not used_52_week_formula:
        message = "Deduction calculee sur les jours habituels du mois (46 semaines ou moins)."
    elif used_52_week_formula and not used_46_week_formula:
        message = "Deduction calculee sur les heures exactes du planning mensuel (52 semaines)."
    else:
        message = "Deduction calculee sur la programmation contractuelle du mois."
    return (
        deduction,
        True,
        message,
    )


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
    worked_hours_by_date = allocate_period_worked_hours(workdays, settings)
    (
        unpaid_deduction,
        absence_deduction_reliable,
        absence_deduction_message,
    ) = calculate_unpaid_absence_deduction(
        contract,
        workdays_by_date,
        settings,
        start=start,
        end=end,
    )

    theo_hours = 0.0
    theo_salary = 0.0
    real_hours = 0.0
    normal_hours = 0.0
    complementary_hours = 0.0
    majorated_hours = 0.0
    salary_base = 0.0
    salary_majoration = 0.0
    majoration_rate_missing = False

    work_days = 0
    absence_days = 0
    unpaid_leave_days = 0
    assmat_leave_days = 0
    holiday_days = 0

    fee_meal_days = 0
    fee_maintenance_days = 0
    fee_meal_total = 0.0
    fee_maintenance_total = 0.0

    for day in iter_days(start, end):
        while (
            settings_index + 1 < len(settings) and settings[settings_index + 1]["valid_from"] <= day
        ):
            settings_index += 1
        current = settings[settings_index]
        if not contract_is_active_on(contract, day):
            continue

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
        elif wd.kind == WorkdayKind.ASSMAT_LEAVE:
            assmat_leave_days += 1
        elif wd.kind == WorkdayKind.HOLIDAY:
            holiday_days += 1

        if wd.kind == WorkdayKind.NORMAL and wd.hours > 0:
            breakdown = worked_hours_by_date[day]
            real_hours += wd.hours
            normal_hours += breakdown.normal_hours
            complementary_hours += breakdown.complementary_hours
            majorated_hours += breakdown.majorated_hours
            salary_base += wd.hours * current["hourly_rate"]
            if breakdown.majorated_hours > 0:
                coefficient = current["majoration_rate"]
                if coefficient is None or coefficient < 1.10:
                    majoration_rate_missing = True
                else:
                    salary_majoration += (
                        breakdown.majorated_hours
                        * current["hourly_rate"]
                        * (coefficient - 1.0)
                    )

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
        hours_complementary=complementary_hours,
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
        absence_deduction_reliable=absence_deduction_reliable,
        absence_deduction_message=absence_deduction_message,
        majoration_rate_missing=majoration_rate_missing,
        total_estimated=total_estimated,
        average_hours_per_day=average_hours,
        paid_leave_days_annual=0,
        paid_leave_mode="",
        paid_leave_days_taken=0,
        paid_leave_days_balance=0,
    )


def build_month_summary(contract_id: int, start: date, end: date) -> MonthlySummaryOut:
    with session_scope() as db:
        contract = crud.get_contract(db, contract_id)
        if not contract:
            raise HTTPException(status_code=404, detail="Contract not found")

        workdays_start, workdays_end = expanded_week_bounds(start, end)
        workdays = crud.list_workdays(
            db,
            contract_id,
            workdays_start,
            workdays_end,
        )
        snapshots = crud.list_settings_snapshots(db, contract_id)
        summary = summarize_period(
            contract,
            workdays,
            snapshots,
            start=start,
            end=end,
        )
        paid_leave_start, paid_leave_end = paid_leave_year_bounds(start)
        paid_leave_workdays = crud.list_workdays(db, contract_id, paid_leave_start, paid_leave_end)
        settings = build_settings_timeline(contract, snapshots)
        paid_leave_settings = settings_for_day(settings, paid_leave_start)
        paid_leave_mode = CalcContractYearMode(paid_leave_settings["year_mode"].value)
        paid_leave_days_annual = paid_leave_acquired_days(
            mode=paid_leave_mode,
            weeks_worked=paid_leave_settings["weeks_per_year"]
            if paid_leave_mode == CalcContractYearMode.INCOMPLETE
            else None,
            extra_days=0,
        )
        paid_leave_days_taken = count_assmat_leave_days(paid_leave_workdays)
        summary.paid_leave_days_annual = paid_leave_days_annual
        summary.paid_leave_mode = paid_leave_settings["year_mode"].value
        summary.paid_leave_days_taken = paid_leave_days_taken
        summary.paid_leave_days_balance = paid_leave_days_annual - paid_leave_days_taken
        return summary


def build_pajemploi_preparation(contract_id: int, month: date) -> dict:
    start, end = month_bounds(month)
    summary = build_month_summary(contract_id, start, end)

    with session_scope() as db:
        contract = crud.get_contract(db, contract_id)
        if not contract:
            raise HTTPException(status_code=404, detail="Contract not found")

        snapshots = crud.list_settings_snapshots(db, contract_id)
        settings = build_settings_timeline(contract, snapshots)
        current = settings_for_day(settings, start)
        workdays = crud.list_workdays(db, contract_id, start, end)
        workdays_by_date = {item.date: item for item in workdays}
        payments = [
            item
            for item in crud.list_payments(db, contract_id)
            if item.period_start <= end and item.period_end >= start
        ]

        blockers: list[str] = []
        checks: list[str] = []
        calculation_context_supported = True
        if any(start < item.valid_from <= end for item in snapshots):
            blockers.append(
                "Des parametres contractuels changent pendant le mois; "
                "le calcul doit etre verifie manuellement."
            )
            calculation_context_supported = False
        if contract.start_date > start or (
            contract.end_date is not None and contract.end_date < end
        ):
            blockers.append(
                "Un debut ou une fin de contrat intervient pendant le mois; "
                "cette periode doit etre verifiee manuellement."
            )
            calculation_context_supported = False

        schedule = schedule_from_settings(current)
        try:
            schedule_total = weekly_schedule_total(schedule)
        except ValueError:
            schedule_total = None
        scheduled_days_per_week = (
            sum(1 for hours in schedule if hours is not None and hours > 0)
            if schedule_total is not None
            else 0
        )
        if scheduled_days_per_week == 0:
            blockers.append(
                "Le planning hebdomadaire doit etre complete avant de preparer "
                "la declaration."
            )
            calculation_context_supported = False

        actual_activity_days: int | None = 0
        for day in iter_days(start, end):
            if not contract_is_active_on(contract, day):
                continue
            applicable = settings_for_day(settings, day)
            try:
                scheduled_hours = scheduled_hours_for_day(
                    schedule_from_settings(applicable),
                    day,
                )
            except ValueError:
                scheduled_hours = None
            if scheduled_hours is None:
                actual_activity_days = None
                break
            workday = workdays_by_date.get(day)
            if scheduled_hours > 0 and (
                workday is None or workday.kind != WorkdayKind.UNPAID_LEAVE
            ):
                actual_activity_days += 1

        if current["hours_per_week"] > 45:
            blockers.append(
                "Les contrats prevoyant plus de 45 h par semaine ne sont pas "
                "encore pris en charge par cette fiche."
            )
            calculation_context_supported = False

        paid_leave_payments = [
            item for item in payments if item.kind == PaymentKind.PAID_LEAVE
        ]
        paid_leave_amount = sum(item.amount for item in paid_leave_payments)
        monthly_payments = [
            item for item in payments if item.kind == PaymentKind.MONTHLY
        ]

        majorated_hourly_rate = None
        coefficient = current["majoration_rate"]
        if coefficient is not None and coefficient >= 1.10:
            majorated_hourly_rate = current["hourly_rate"] * coefficient

        preparation = None
        if (
            calculation_context_supported
            and summary.monthly_salary_theoretical > 0
        ):
            preparation = prepare_pajemploi_declaration(
                monthly_salary=summary.monthly_salary_theoretical,
                hourly_rate=current["hourly_rate"],
                hours_per_week=current["hours_per_week"],
                weeks_per_year=current["weeks_per_year"],
                scheduled_days_per_week=scheduled_days_per_week,
                absence_deduction=(
                    summary.unpaid_leave_deduction
                    if summary.absence_deduction_reliable
                    else None
                ),
                actual_activity_days=actual_activity_days,
                complementary_hours=summary.hours_complementary,
                complementary_hourly_rate=current[
                    "complementary_hourly_rate"
                ],
                majorated_hours=summary.hours_majorated,
                majorated_hourly_rate=majorated_hourly_rate,
                paid_leave_amount=paid_leave_amount,
            )
            blockers.extend(preparation.blockers)

        if current["year_mode"] == ContractYearMode.INCOMPLETE:
            if paid_leave_amount > 0:
                blockers.append(
                    "Un paiement de conges payes est enregistre, mais le nombre "
                    "de jours payes n'est pas attribue a ce mois."
                )
            else:
                checks.append(
                    "Confirmer qu'aucun conge paye n'a ete verse ce mois-ci."
                )

        if not monthly_payments:
            checks.append(
                "La date de paiement reste a renseigner lors du versement."
            )
        checks.append(
            "Ajouter manuellement les indemnites kilometriques si elles "
            "s'appliquent."
        )

        calculation_ready = (
            preparation is not None
            and preparation.net_salary is not None
            and not blockers
        )
        return {
            "contract_id": contract_id,
            "contract_name": contract.name or f"Contrat #{contract_id}",
            "period_start": start,
            "period_end": end,
            "month_label": f"{MONTH_NAMES[start.month - 1]} {start.year}",
            "previous_month": (start - timedelta(days=1)).replace(day=1),
            "next_month": (end + timedelta(days=1)).replace(day=1),
            "year_mode": current["year_mode"].value,
            "summary": summary,
            "preparation": preparation,
            "blockers": blockers,
            "checks": checks,
            "calculation_ready": calculation_ready,
            "paid_leave_days": (
                None
                if current["year_mode"] == ContractYearMode.COMPLETE
                or paid_leave_amount > 0
                else 0
            ),
            "meal_and_maintenance_total": (
                summary.fee_meal_total + summary.fee_maintenance_total
            ),
            "monthly_payments": monthly_payments,
        }


def fetch_holidays_api(year: int) -> dict[str, str]:
    url = f"https://calendrier.api.gouv.fr/jours-feries/metropole/{year}.json"
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read())


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


def paid_leave_year_bounds(day: date) -> tuple[date, date]:
    if day.month >= 6:
        start = date(day.year, 6, 1)
        end = date(day.year + 1, 5, 31)
        return start, end
    start = date(day.year - 1, 6, 1)
    end = date(day.year, 5, 31)
    return start, end


def count_assmat_leave_days(workdays: list) -> int:
    return sum(1 for wd in workdays if wd.kind == WorkdayKind.ASSMAT_LEAVE)


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
        workdays_start, workdays_end = expanded_week_bounds(start, end)
        workdays = crud.list_workdays(
            db,
            contract_id,
            workdays_start,
            workdays_end,
        )
        snapshots = crud.list_settings_snapshots(db, contract_id)
        settings = build_settings_timeline(contract, snapshots)
        paid_leave_start, paid_leave_end = paid_leave_year_bounds(start)
        paid_leave_settings = settings_for_day(settings, paid_leave_start)
        paid_leave_mode = CalcContractYearMode(paid_leave_settings["year_mode"].value)
        paid_leave_days_annual = paid_leave_acquired_days(
            mode=paid_leave_mode,
            weeks_worked=paid_leave_settings["weeks_per_year"]
            if paid_leave_mode == CalcContractYearMode.INCOMPLETE
            else None,
            extra_days=0,
        )
        paid_leave_workdays = crud.list_workdays(db, contract_id, paid_leave_start, paid_leave_end)

        monthly_items = []
        totals = {
            "hours_real": 0.0,
            "hours_normal": 0.0,
            "hours_complementary": 0.0,
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
            "absence_deduction_reliable": True,
            "majoration_rate_missing": False,
            "total_estimated": 0.0,
            "yearly_hours_theoretical": 0.0,
            "yearly_salary_theoretical": 0.0,
            "paid_leave_days_annual": paid_leave_days_annual,
            "paid_leave_mode": paid_leave_settings["year_mode"].value,
            "paid_leave_days_taken": 0,
            "paid_leave_days_balance": 0,
        }

        for month in range(1, 13):
            month_start = date(year, month, 1)
            month_end = date(year, month, calendar.monthrange(year, month)[1])
            summary = summarize_period(
                contract,
                workdays,
                snapshots,
                start=month_start,
                end=month_end,
            )
            monthly_items.append(
                {"month": month, "label": MONTH_NAMES[month - 1], "summary": summary}
            )

            totals["hours_real"] += summary.hours_real
            totals["hours_normal"] += summary.hours_normal
            totals["hours_complementary"] += summary.hours_complementary
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
            totals["absence_deduction_reliable"] = (
                totals["absence_deduction_reliable"]
                and summary.absence_deduction_reliable
            )
            totals["majoration_rate_missing"] = (
                totals["majoration_rate_missing"]
                or summary.majoration_rate_missing
            )
            totals["total_estimated"] += summary.total_estimated
            totals["yearly_hours_theoretical"] += summary.monthly_hours_theoretical
            totals["yearly_salary_theoretical"] += summary.monthly_salary_theoretical

        totals["paid_leave_days_taken"] = count_assmat_leave_days(paid_leave_workdays)
        totals["paid_leave_days_balance"] = (
            totals["paid_leave_days_annual"] - totals["paid_leave_days_taken"]
        )

        hours_delta = totals["hours_real"] - totals["yearly_hours_theoretical"]
        average_hours = totals["hours_real"] / totals["work_days"] if totals["work_days"] else 0.0

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


@app.get("/contracts/{contract_id}/export/monthly.csv")
def export_monthly_csv(contract_id: int, start: date, end: date):
    summary = build_month_summary(contract_id, start, end)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Période",
            "Heures contractuelles",
            "Heures réelles",
            "Heures complémentaires",
            "Heures majorées",
            "Jours travaillés",
            "Jours absences",
            "Jours congés assmat",
            "Jours sans solde",
            "Jours fériés",
            "Salaire de base",
            "Majoration",
            "Frais repas",
            "Frais entretien",
            "Déduction sans solde",
            "Total estimé",
        ]
    )
    writer.writerow(
        [
            f"{summary.period_start} → {summary.period_end}",
            round(summary.monthly_hours_theoretical, 2),
            round(summary.hours_real, 2),
            round(summary.hours_complementary, 2),
            round(summary.hours_majorated, 2),
            summary.work_days,
            summary.absence_days,
            summary.assmat_leave_days,
            summary.unpaid_leave_days,
            summary.holiday_days,
            round(summary.salary_base, 2),
            round(summary.salary_majoration, 2),
            round(summary.fee_meal_total, 2),
            round(summary.fee_maintenance_total, 2),
            round(summary.unpaid_leave_deduction, 2),
            round(summary.total_estimated, 2),
        ]
    )

    filename = f"monassmat_{start.strftime('%Y-%m')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/contracts/{contract_id}/export/pajemploi.csv")
def export_pajemploi_csv(
    contract_id: int,
    month: date | None = None,
):
    selected_month = (month or date.today()).replace(day=1)
    data = build_pajemploi_preparation(contract_id, selected_month)
    preparation = data["preparation"]
    summary = data["summary"]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Champ Pajemploi", "Valeur"])
    writer.writerow(["Période", f"{data['period_start']} → {data['period_end']}"])
    writer.writerow(
        ["Heures normales", preparation.normal_hours if preparation else ""]
    )
    writer.writerow(["Heures complémentaires", round(summary.hours_complementary, 2)])
    writer.writerow(["Heures majorées", round(summary.hours_majorated, 2)])
    writer.writerow(
        ["Jours d'activité", preparation.activity_days if preparation else ""]
    )
    writer.writerow(
        [
            "Jours de congés payés",
            data["paid_leave_days"]
            if data["paid_leave_days"] is not None
            else "À vérifier / non applicable",
        ]
    )
    writer.writerow(
        [
            "Salaire net",
            round(preparation.net_salary, 2)
            if preparation and preparation.net_salary is not None
            else "",
        ]
    )
    writer.writerow(["Indemnités entretien", round(summary.fee_maintenance_total, 2)])
    writer.writerow(["Frais repas", round(summary.fee_meal_total, 2)])
    writer.writerow(["Indemnités kilométriques", "À compléter si applicable"])
    writer.writerow([])
    writer.writerow(
        [
            "Statut du calcul",
            "Prêt" if data["calculation_ready"] else "À compléter",
        ]
    )
    for blocker in data["blockers"]:
        writer.writerow(["Blocage", blocker])
    for check in data["checks"]:
        writer.writerow(["Contrôle manuel", check])

    filename = f"monassmat_pajemploi_{selected_month.strftime('%Y-%m')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/contracts/{contract_id}/export/yearly.csv")
def export_yearly_csv(contract_id: int, year: int):
    data = build_year_summary(contract_id, year)
    totals = data["totals"]
    monthly_items = data["monthly_items"]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Mois",
            "Heures réelles",
            "Heures complémentaires",
            "Heures majorées",
            "Jours travaillés",
            "Jours absences",
            "Salaire de base",
            "Majoration",
            "Frais repas",
            "Frais entretien",
            "Déduction sans solde",
            "Total estimé",
        ]
    )
    for item in monthly_items:
        s = item["summary"]
        writer.writerow(
            [
                item["label"],
                round(s.hours_real, 2),
                round(s.hours_complementary, 2),
                round(s.hours_majorated, 2),
                s.work_days,
                s.absence_days,
                round(s.salary_base, 2),
                round(s.salary_majoration, 2),
                round(s.fee_meal_total, 2),
                round(s.fee_maintenance_total, 2),
                round(s.unpaid_leave_deduction, 2),
                round(s.total_estimated, 2),
            ]
        )
    writer.writerow(
        [
            "TOTAL",
            round(totals["hours_real"], 2),
            round(totals["hours_complementary"], 2),
            round(totals["hours_majorated"], 2),
            totals["work_days"],
            totals["absence_days"],
            round(totals["salary_base"], 2),
            round(totals["salary_majoration"], 2),
            round(totals["fee_meal_total"], 2),
            round(totals["fee_maintenance_total"], 2),
            round(totals["unpaid_leave_deduction"], 2),
            round(totals["total_estimated"], 2),
        ]
    )

    filename = f"monassmat_{year}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/contracts/{contract_id}/calendar", response_class=HTMLResponse)
def calendar_page(
    contract_id: int,
    request: Request,
    initial_date: date | None = None,
    db: Session = Depends(get_db),
):
    contract = crud.get_contract(db, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    if initial_date is None:
        initial_date = date.today()
    return templates.TemplateResponse(
        request,
        "calendar.html",
        {
            "title": "Calendrier",
            "contract_id": contract_id,
            "contract_name": contract.name or f"Contrat #{contract_id}",
            "initial_date": initial_date.isoformat(),
            "current_section": "calendar",
        },
    )


@app.get("/contracts/{contract_id}/pajemploi", response_class=HTMLResponse)
def pajemploi_preparation_page(
    contract_id: int,
    request: Request,
    month: date | None = None,
):
    selected_month = (month or date.today()).replace(day=1)
    data = build_pajemploi_preparation(contract_id, selected_month)
    return templates.TemplateResponse(
        request,
        "pajemploi_preparation.html",
        {
            "title": "Preparation Pajemploi",
            "current_section": "pajemploi",
            **data,
        },
    )


@app.get("/contracts/{contract_id}/settings", response_class=HTMLResponse)
def contract_settings(contract_id: int, request: Request, db: Session = Depends(get_db)):
    contract = crud.get_contract(db, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    snapshots = crud.list_settings_snapshots(db, contract_id)

    current_mode = CalcContractYearMode(contract.year_mode.value)
    current_paid_leave_days = paid_leave_acquired_days(
        mode=current_mode,
        weeks_worked=contract.weeks_per_year
        if current_mode == CalcContractYearMode.INCOMPLETE
        else None,
        extra_days=0,
    )
    return templates.TemplateResponse(
        request,
        "contract_settings.html",
        {
            "title": "Parametres",
            "contract_id": contract_id,
            "contract_name": contract.name or f"Contrat #{contract_id}",
            "contract": contract,
            "snapshots": snapshots,
            "effective_from": date.today().isoformat(),
            "today_year": date.today().year,
            "current_section": "settings",
            "year_modes": [m.value for m in ContractYearMode],
            "paid_leave_days_annual": current_paid_leave_days,
        },
    )


@app.get("/contracts/{contract_id}/planned-weeks", response_class=HTMLResponse)
def planned_weeks_page(
    contract_id: int,
    request: Request,
    year: int | None = None,
    saved: bool = False,
    db: Session = Depends(get_db),
):
    contract = crud.get_contract(db, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    target_year = year or date.today().year
    if target_year < 1900 or target_year > 2100:
        raise HTTPException(status_code=400, detail="Invalid year")

    weeks = weeks_overlapping_year(target_year)
    stored = crud.list_week_schedules(db, contract_id, weeks[0], weeks[-1])
    stored_by_week = {item.week_start: item.planned for item in stored}
    week_rows = [
        {
            "week_start": monday,
            "week_end": monday + timedelta(days=6),
            "week_number": monday.isocalendar().week,
            "planned": stored_by_week.get(monday, True),
            "stored": monday in stored_by_week,
        }
        for monday in weeks
    ]
    return templates.TemplateResponse(
        request,
        "planned_weeks.html",
        {
            "title": "Semaines programmees",
            "contract_id": contract_id,
            "contract_name": contract.name or f"Contrat #{contract_id}",
            "contract": contract,
            "year": target_year,
            "prev_year": target_year - 1,
            "next_year": target_year + 1,
            "week_rows": week_rows,
            "configured": len(stored_by_week) == len(weeks),
            "planned_count": sum(1 for row in week_rows if row["planned"]),
            "saved": saved,
            "current_section": "planning",
        },
    )


@app.post("/contracts/{contract_id}/planned-weeks", response_class=HTMLResponse)
def save_planned_weeks(
    contract_id: int,
    year: int = Form(...),
    planned_weeks: list[str] = Form(default=[]),
    db: Session = Depends(get_db),
):
    contract = crud.get_contract(db, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    if year < 1900 or year > 2100:
        raise HTTPException(status_code=400, detail="Invalid year")

    weeks = weeks_overlapping_year(year)
    allowed = set(weeks)
    try:
        selected = {date_from_iso(value) for value in planned_weeks}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid week") from exc
    if not selected.issubset(allowed):
        raise HTTPException(status_code=400, detail="Week outside selected year")

    crud.set_week_schedules(
        db,
        contract_id=contract_id,
        statuses={monday: monday in selected for monday in weeks},
    )
    db.commit()
    return RedirectResponse(
        url=f"/contracts/{contract_id}/planned-weeks?year={year}&saved=1",
        status_code=303,
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
    year_mode: str = Form(...),
    hourly_rate: str = Form(...),
    complementary_hourly_rate: str | None = Form(None),
    days_per_week: str | None = Form(None),
    monday_hours: str | None = Form(None),
    tuesday_hours: str | None = Form(None),
    wednesday_hours: str | None = Form(None),
    thursday_hours: str | None = Form(None),
    friday_hours: str | None = Form(None),
    saturday_hours: str | None = Form(None),
    sunday_hours: str | None = Form(None),
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

    parsed_year_mode, parsed_weeks_per_year = parse_regular_contract_mode(
        year_mode,
        weeks_per_year,
    )
    parsed_hours_per_week = float(hours_per_week)
    parsed_schedule = parse_weekly_schedule(
        hours_per_week=parsed_hours_per_week,
        required=False,
        monday_hours=monday_hours,
        tuesday_hours=tuesday_hours,
        wednesday_hours=wednesday_hours,
        thursday_hours=thursday_hours,
        friday_hours=friday_hours,
        saturday_hours=saturday_hours,
        sunday_hours=sunday_hours,
    )

    previous_values = {
        "hours_per_week": contract.hours_per_week,
        "weeks_per_year": contract.weeks_per_year,
        "year_mode": contract.year_mode,
        "hourly_rate": contract.hourly_rate,
        "complementary_hourly_rate": contract.complementary_hourly_rate,
        "days_per_week": contract.days_per_week,
        "monday_hours": contract.monday_hours,
        "tuesday_hours": contract.tuesday_hours,
        "wednesday_hours": contract.wednesday_hours,
        "thursday_hours": contract.thursday_hours,
        "friday_hours": contract.friday_hours,
        "saturday_hours": contract.saturday_hours,
        "sunday_hours": contract.sunday_hours,
        "majoration_threshold": contract.majoration_threshold,
        "majoration_rate": contract.majoration_rate,
        "fee_meal_amount": contract.fee_meal_amount,
        "fee_maintenance_amount": contract.fee_maintenance_amount,
        "salary_net_ceiling": contract.salary_net_ceiling,
    }

    contract.name = contract_name.strip() if contract_name else None
    contract.start_date = date_from_iso(start_date)
    contract.end_date = date_from_iso(end_date) if end_date else None
    contract.hours_per_week = parsed_hours_per_week
    contract.weeks_per_year = parsed_weeks_per_year
    contract.year_mode = parsed_year_mode
    contract.hourly_rate = float(hourly_rate)
    contract.complementary_hourly_rate = parse_optional_positive_float(
        complementary_hourly_rate,
        field_label="Le taux des heures complementaires",
    )
    contract.days_per_week = parse_optional_int(days_per_week)
    for field_name, value in parsed_schedule.items():
        setattr(contract, field_name, value)
    contract.majoration_threshold = parse_optional_float(majoration_threshold)
    contract.majoration_rate = parse_majoration_coefficient(majoration_rate)
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
            year_mode=previous_values["year_mode"],
            hourly_rate=previous_values["hourly_rate"],
            complementary_hourly_rate=previous_values[
                "complementary_hourly_rate"
            ],
            days_per_week=previous_values["days_per_week"],
            monday_hours=previous_values["monday_hours"],
            tuesday_hours=previous_values["tuesday_hours"],
            wednesday_hours=previous_values["wednesday_hours"],
            thursday_hours=previous_values["thursday_hours"],
            friday_hours=previous_values["friday_hours"],
            saturday_hours=previous_values["saturday_hours"],
            sunday_hours=previous_values["sunday_hours"],
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
        year_mode=contract.year_mode,
        hourly_rate=contract.hourly_rate,
        complementary_hourly_rate=contract.complementary_hourly_rate,
        days_per_week=contract.days_per_week,
        monday_hours=contract.monday_hours,
        tuesday_hours=contract.tuesday_hours,
        wednesday_hours=contract.wednesday_hours,
        thursday_hours=contract.thursday_hours,
        friday_hours=contract.friday_hours,
        saturday_hours=contract.saturday_hours,
        sunday_hours=contract.sunday_hours,
        majoration_threshold=contract.majoration_threshold,
        majoration_rate=contract.majoration_rate,
        fee_meal_amount=contract.fee_meal_amount,
        fee_maintenance_amount=contract.fee_maintenance_amount,
        salary_net_ceiling=contract.salary_net_ceiling,
    )
    db.commit()
    snapshots = crud.list_settings_snapshots(db, contract_id)

    current_mode = CalcContractYearMode(contract.year_mode.value)
    current_paid_leave_days = paid_leave_acquired_days(
        mode=current_mode,
        weeks_worked=contract.weeks_per_year
        if current_mode == CalcContractYearMode.INCOMPLETE
        else None,
        extra_days=0,
    )
    return templates.TemplateResponse(
        request,
        "contract_settings.html",
        {
            "title": "Parametres",
            "contract_id": contract_id,
            "contract_name": contract.name or f"Contrat #{contract_id}",
            "contract": contract,
            "snapshots": snapshots,
            "effective_from": effective_from,
            "today_year": date.today().year,
            "saved": True,
            "year_modes": [m.value for m in ContractYearMode],
            "paid_leave_days_annual": current_paid_leave_days,
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

    snapshot = crud.get_settings_snapshot(db, contract_id=contract_id, valid_from=valid_from)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    paid_leave_days = paid_leave_acquired_days(
        mode=CalcContractYearMode(snapshot.year_mode.value),
        weeks_worked=snapshot.weeks_per_year
        if snapshot.year_mode == ContractYearMode.INCOMPLETE
        else None,
        extra_days=0,
    )
    return templates.TemplateResponse(
        request,
        "settings_snapshot_form.html",
        {
            "title": "Modifier snapshot",
            "contract": contract,
            "contract_id": contract_id,
            "contract_name": contract.name or f"Contrat #{contract_id}",
            "snapshot": snapshot,
            "current_section": "settings",
            "year_modes": [m.value for m in ContractYearMode],
            "paid_leave_days_annual": paid_leave_days,
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
    year_mode: str = Form(...),
    hourly_rate: str = Form(...),
    complementary_hourly_rate: str | None = Form(None),
    days_per_week: str | None = Form(None),
    monday_hours: str | None = Form(None),
    tuesday_hours: str | None = Form(None),
    wednesday_hours: str | None = Form(None),
    thursday_hours: str | None = Form(None),
    friday_hours: str | None = Form(None),
    saturday_hours: str | None = Form(None),
    sunday_hours: str | None = Form(None),
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

    parsed_year_mode, parsed_weeks_per_year = parse_regular_contract_mode(
        year_mode,
        weeks_per_year,
    )
    parsed_hours_per_week = float(hours_per_week)
    parsed_schedule = parse_weekly_schedule(
        hours_per_week=parsed_hours_per_week,
        required=False,
        monday_hours=monday_hours,
        tuesday_hours=tuesday_hours,
        wednesday_hours=wednesday_hours,
        thursday_hours=thursday_hours,
        friday_hours=friday_hours,
        saturday_hours=saturday_hours,
        sunday_hours=sunday_hours,
    )

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
                request,
                "settings_snapshot_form.html",
                {
                    "title": "Modifier snapshot",
                    "contract": contract,
                    "contract_id": contract_id,
                    "contract_name": contract.name or f"Contrat #{contract_id}",
                    "snapshot": snapshot,
                    "error": "Un snapshot existe deja a cette date.",
                    "year_modes": [m.value for m in ContractYearMode],
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
        hours_per_week=parsed_hours_per_week,
        weeks_per_year=parsed_weeks_per_year,
        year_mode=parsed_year_mode,
        hourly_rate=float(hourly_rate),
        complementary_hourly_rate=parse_optional_positive_float(
            complementary_hourly_rate,
            field_label="Le taux des heures complementaires",
        ),
        days_per_week=parse_optional_int(days_per_week),
        **parsed_schedule,
        majoration_threshold=parse_optional_float(majoration_threshold),
        majoration_rate=parse_majoration_coefficient(majoration_rate),
        fee_meal_amount=parse_optional_float(fee_meal_amount),
        fee_maintenance_amount=parse_optional_float(fee_maintenance_amount),
        salary_net_ceiling=parse_optional_float(salary_net_ceiling),
    )
    db.commit()

    snapshot = crud.get_settings_snapshot(db, contract_id=contract_id, valid_from=valid_from_date)
    paid_leave_days = paid_leave_acquired_days(
        mode=CalcContractYearMode(snapshot.year_mode.value),
        weeks_worked=snapshot.weeks_per_year
        if snapshot.year_mode == ContractYearMode.INCOMPLETE
        else None,
        extra_days=0,
    )
    return templates.TemplateResponse(
        request,
        "settings_snapshot_form.html",
        {
            "title": "Modifier snapshot",
            "contract": contract,
            "contract_id": contract_id,
            "contract_name": contract.name or f"Contrat #{contract_id}",
            "snapshot": snapshot,
            "saved": True,
            "year_modes": [m.value for m in ContractYearMode],
            "paid_leave_days_annual": paid_leave_days,
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
    deleted = crud.delete_settings_snapshot(db, contract_id=contract_id, valid_from=valid_from_date)
    if not deleted:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    db.commit()

    snapshots = crud.list_settings_snapshots(db, contract_id)
    current_mode = CalcContractYearMode(contract.year_mode.value)
    current_paid_leave_days = paid_leave_acquired_days(
        mode=current_mode,
        weeks_worked=contract.weeks_per_year
        if current_mode == CalcContractYearMode.INCOMPLETE
        else None,
        extra_days=0,
    )
    return templates.TemplateResponse(
        request,
        "contract_settings.html",
        {
            "title": "Parametres",
            "contract_id": contract_id,
            "contract_name": contract.name or f"Contrat #{contract_id}",
            "contract": contract,
            "snapshots": snapshots,
            "effective_from": date.today().isoformat(),
            "today_year": date.today().year,
            "deleted": True,
            "year_modes": [m.value for m in ContractYearMode],
            "paid_leave_days_annual": current_paid_leave_days,
        },
    )


@app.post("/contracts/{contract_id}/holidays/import", response_class=HTMLResponse)
def import_holidays(
    contract_id: int,
    request: Request,
    year: int = Form(...),
    db: Session = Depends(get_db),
):
    contract = crud.get_contract(db, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    snapshots = crud.list_settings_snapshots(db, contract_id)

    try:
        data = fetch_holidays_api(year)
    except Exception as exc:
        return templates.TemplateResponse(
            request,
            "contract_settings.html",
            {
                "title": "Parametres",
                "contract_id": contract_id,
                "contract_name": contract.name or f"Contrat #{contract_id}",
                "contract": contract,
                "snapshots": snapshots,
                "effective_from": date.today().isoformat(),
                "today_year": date.today().year,
                "holidays_error": f"Erreur lors de la récupération des jours fériés : {exc}",
            },
        )

    holidays = parse_holidays_response(data)
    imported = 0
    skipped = 0
    for day, _name in holidays:
        existing = crud.list_workdays(db, contract_id, day, day)
        if existing:
            skipped += 1
            continue
        crud.upsert_workday(
            db,
            contract_id=contract_id,
            day=day,
            hours=0.0,
            kind=CalcWorkdayKind.HOLIDAY,
        )
        imported += 1
    db.commit()

    snapshots = crud.list_settings_snapshots(db, contract_id)
    return templates.TemplateResponse(
        request,
        "contract_settings.html",
        {
            "title": "Parametres",
            "contract_id": contract_id,
            "contract_name": contract.name or f"Contrat #{contract_id}",
            "contract": contract,
            "snapshots": snapshots,
            "effective_from": date.today().isoformat(),
            "today_year": date.today().year,
            "holidays_imported": imported,
            "holidays_skipped": skipped,
        },
    )


@app.get("/contracts/{contract_id}/day_form", response_class=HTMLResponse)
def day_form(contract_id: int, day: date, request: Request, db: Session = Depends(get_db)):
    wds = crud.list_workdays(db, contract_id=contract_id, start=day, end=day)
    existing = wds[0] if wds else None

    return templates.TemplateResponse(
        request,
        "partials/day_form.html",
        {
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
        request,
        "partials/bulk_form.html",
        {
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
        request,
        "partials/month_summary.html",
        {
            "contract_id": contract_id,
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
        request,
        "partials/year_summary.html",
        {
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
        request,
        "year_summary_page.html",
        {
            "title": "Synthese annuelle",
            "contract_id": contract_id,
            "contract_name": contract_name,
            "prev_year": target_year - 1,
            "next_year": target_year + 1,
            "current_section": "year",
            **summary,
        },
    )


def _paid_leave_year_bounds(ref_date: date) -> tuple[date, date]:
    """Return June 1 → May 31 bounds that contain ref_date."""
    if ref_date.month >= 6:
        start = date(ref_date.year, 6, 1)
        end = date(ref_date.year + 1, 5, 31)
    else:
        start = date(ref_date.year - 1, 6, 1)
        end = date(ref_date.year, 5, 31)
    return start, end


@app.get("/contracts/{contract_id}/paid-leave", response_class=HTMLResponse)
def paid_leave_page(
    contract_id: int,
    request: Request,
    year: int | None = None,
    saved: bool = False,
    db: Session = Depends(get_db),
):
    contract = crud.get_contract(db, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    target_year = year or date.today().year
    period_start, period_end = _paid_leave_year_bounds(date(target_year, 6, 1))

    workdays = crud.list_workdays(db, contract_id, period_start, period_end)

    # Days acquired: use v1 heuristic counting NORMAL workdays
    wf_list = [
        WorkdayFacts(day=wd.date, hours=wd.hours, kind=CalcWorkdayKind(wd.kind.value))
        for wd in workdays
    ]
    acquisition_period = Period(start=period_start, end=period_end)
    days_acquired = round(paid_leave_acquired_days_v1(wf_list, acquisition_period), 2)

    # Days taken: count ASSMAT_LEAVE workdays
    days_taken = sum(1 for wd in workdays if wd.kind == WorkdayKind.ASSMAT_LEAVE)

    # Get applicable settings for amount computation
    snapshots = crud.list_settings_snapshots(db, contract_id)
    settings = build_settings_timeline(contract, snapshots)
    # Use most recent snapshot valid for this period (or first)
    applicable = settings[0]
    for snap in settings:
        if snap["valid_from"] <= period_start:
            applicable = snap
    daily_reference_hours = (
        applicable["hours_per_week"] / applicable["days_per_week"]
        if applicable.get("days_per_week") and applicable["days_per_week"] > 0
        else applicable["hours_per_week"] / 5.0
    )
    hourly_rate = applicable["hourly_rate"]

    amount_maintien = (
        paid_leave_value(
            method=PaidLeaveMethod.MAINTIEN,
            days_taken=float(days_taken),
            daily_reference_hours=daily_reference_hours,
            hourly_rate=hourly_rate,
        )
        if days_taken > 0
        else 0.0
    )

    history = crud.list_paid_leaves(db, contract_id)

    return templates.TemplateResponse(
        request,
        "paid_leave.html",
        {
            "title": "Congés payés",
            "contract_id": contract_id,
            "contract_name": contract.name or f"Contrat #{contract_id}",
            "period_start": period_start,
            "period_end": period_end,
            "paid_leave_mode": "Annuel (juin → mai)",
            "days_acquired": days_acquired,
            "days_taken": days_taken,
            "amount_maintien": amount_maintien,
            "history": history,
            "saved": saved,
            "current_section": "paid-leave",
        },
    )


@app.get("/contracts/{contract_id}/payments", response_class=HTMLResponse)
def payments_page(
    contract_id: int,
    request: Request,
    period_start: date | None = None,
    period_end: date | None = None,
    amount: float | None = None,
    saved: bool = False,
    deleted: bool = False,
    db: Session = Depends(get_db),
):
    contract = crud.get_contract(db, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    payments = crud.list_payments(db, contract_id)
    return templates.TemplateResponse(
        request,
        "payments.html",
        {
            "title": "Paiements",
            "contract_id": contract_id,
            "contract_name": contract.name or f"Contrat #{contract_id}",
            "payments": payments,
            "today": date.today().isoformat(),
            "prefill_period_start": period_start.isoformat() if period_start else None,
            "prefill_period_end": period_end.isoformat() if period_end else None,
            "prefill_amount": amount,
            "saved": saved,
            "deleted": deleted,
            "current_section": "payments",
        },
    )


@app.post("/contracts/{contract_id}/payments", response_class=HTMLResponse)
def create_payment_route(
    contract_id: int,
    request: Request,
    period_start: str = Form(...),
    period_end: str = Form(...),
    amount: str = Form(...),
    paid_at: str = Form(...),
    kind: str = Form(...),
    db: Session = Depends(get_db),
):
    from .models import PaymentKind

    contract = crud.get_contract(db, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    crud.create_payment(
        db,
        contract_id=contract_id,
        period_start=date_from_iso(period_start),
        period_end=date_from_iso(period_end),
        amount=float(amount),
        paid_at=date_from_iso(paid_at),
        kind=PaymentKind(kind),
    )
    db.commit()
    return RedirectResponse(url=f"/contracts/{contract_id}/payments?saved=1", status_code=303)


@app.post("/contracts/{contract_id}/payments/{payment_id}/delete", response_class=HTMLResponse)
def delete_payment_route(
    contract_id: int,
    payment_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    deleted = crud.delete_payment(db, payment_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Paiement introuvable")
    db.commit()
    return RedirectResponse(url=f"/contracts/{contract_id}/payments?deleted=1", status_code=303)


@app.post("/contracts/{contract_id}/paid-leave/record", response_class=HTMLResponse)
def record_paid_leave(
    contract_id: int,
    period_start: str = Form(...),
    period_end: str = Form(...),
    method: str = Form(...),
    amount_paid: str = Form(...),
    db: Session = Depends(get_db),
):
    contract = crud.get_contract(db, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    period_start_date = date_from_iso(period_start)
    period_end_date = date_from_iso(period_end)

    workdays = crud.list_workdays(db, contract_id, period_start_date, period_end_date)

    wf_list = [
        WorkdayFacts(day=wd.date, hours=wd.hours, kind=CalcWorkdayKind(wd.kind.value))
        for wd in workdays
    ]
    acquisition_period = Period(start=period_start_date, end=period_end_date)
    days_acquired = round(paid_leave_acquired_days_v1(wf_list, acquisition_period), 2)
    days_taken = float(sum(1 for wd in workdays if wd.kind == WorkdayKind.ASSMAT_LEAVE))

    paid_leave_method = PaidLeaveMethod(method)

    crud.upsert_paid_leave(
        db,
        contract_id=contract_id,
        period_start=period_start_date,
        period_end=period_end_date,
        days_acquired=days_acquired,
        days_taken=days_taken,
        method=paid_leave_method,
        amount_paid=float(amount_paid),
    )
    db.commit()

    return RedirectResponse(
        url=f"/contracts/{contract_id}/paid-leave?saved=true",
        status_code=302,
    )


@app.get("/children", response_class=HTMLResponse)
def list_children_page(request: Request, db: Session = Depends(get_db)):
    children = crud.list_children(db)
    return templates.TemplateResponse(
        request,
        "children.html",
        {
            "title": "Enfants",
            "children": children,
            "today": date.today(),
        },
    )


@app.get("/children/new", response_class=HTMLResponse)
def new_child_page(request: Request):
    return templates.TemplateResponse(
        request,
        "child_form.html",
        {"title": "Nouvel enfant", "child": None},
    )


@app.post("/children/new", response_class=HTMLResponse)
def create_child_route(
    request: Request,
    name: str = Form(...),
    birth_date: str = Form(...),
    db: Session = Depends(get_db),
):
    child = crud.create_child(db, name=name.strip(), birth_date=date_from_iso(birth_date))
    db.commit()
    return templates.TemplateResponse(
        request,
        "child_form.html",
        {"title": "Nouvel enfant", "child": child, "saved": True},
    )


@app.get("/children/{child_id}", response_class=HTMLResponse)
def edit_child_page(child_id: int, request: Request, db: Session = Depends(get_db)):
    child = crud.get_child(db, child_id)
    if not child:
        raise HTTPException(status_code=404, detail="Enfant introuvable")
    return templates.TemplateResponse(
        request,
        "child_form.html",
        {"title": "Modifier l'enfant", "child": child},
    )


@app.post("/children/{child_id}", response_class=HTMLResponse)
def update_child_route(
    child_id: int,
    request: Request,
    name: str = Form(...),
    birth_date: str = Form(...),
    db: Session = Depends(get_db),
):
    child = crud.update_child(
        db, child_id=child_id, name=name.strip(), birth_date=date_from_iso(birth_date)
    )
    if not child:
        raise HTTPException(status_code=404, detail="Enfant introuvable")
    db.commit()
    return templates.TemplateResponse(
        request,
        "child_form.html",
        {"title": "Modifier l'enfant", "child": child, "saved": True},
    )


@app.get("/contracts", response_class=HTMLResponse)
def contracts_summary(request: Request, db: Session = Depends(get_db)):
    contracts = crud.list_contracts(db)
    today = date.today()
    month_start = today.replace(day=1)
    _, last_day = calendar.monthrange(today.year, today.month)
    month_end = today.replace(day=last_day)
    days_expected = sum(1 for d in iter_days(month_start, month_end) if d.weekday() < 5)
    cp_year_start, cp_year_end = _paid_leave_year_bounds(today)

    items = []
    for contract in contracts:
        facts = ContractFacts(
            start_date=contract.start_date,
            end_date=contract.end_date,
            hours_per_week=contract.hours_per_week,
            weeks_per_year=contract.weeks_per_year,
            hourly_rate=contract.hourly_rate,
        )
        is_active = contract.end_date is None or contract.end_date >= today

        month_workdays = crud.list_workdays(db, contract.id, month_start, month_end)
        days_entered = sum(1 for w in month_workdays if w.kind != WorkdayKind.HOLIDAY)

        cp_workdays = crud.list_workdays(db, contract.id, cp_year_start, cp_year_end)
        wf_list = [
            WorkdayFacts(day=w.date, hours=w.hours, kind=CalcWorkdayKind(w.kind.value))
            for w in cp_workdays
        ]
        cp_acquired = round(
            paid_leave_acquired_days_v1(wf_list, Period(start=cp_year_start, end=cp_year_end)), 1
        )
        cp_taken = sum(1 for w in cp_workdays if w.kind == WorkdayKind.ASSMAT_LEAVE)
        cp_balance = round(cp_acquired - cp_taken, 1)

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
                "monthly_salary_theoretical": contract_monthly_salary(facts),
                "is_active": is_active,
                "days_entered": days_entered,
                "days_expected": days_expected,
                "cp_balance": cp_balance,
            }
        )

    return templates.TemplateResponse(
        request,
        "contracts_summary.html",
        {
            "title": "Contrats",
            "items": items,
            "month_name": MONTH_NAMES[today.month - 1],
            "month_year": today.year,
        },
    )


@app.get("/contracts/new", response_class=HTMLResponse)
def new_contract(request: Request, child_id: int | None = None, db: Session = Depends(get_db)):
    children = crud.list_children(db)
    return templates.TemplateResponse(
        request,
        "contract_new.html",
        {
            "title": "Nouveau contrat",
            "year_modes": [m.value for m in ContractYearMode],
            "children": children,
            "selected_child_id": child_id,
        },
    )


@app.post("/contracts/new", response_class=HTMLResponse)
def create_contract(
    request: Request,
    contract_name: str | None = Form(None),
    child_id: str | None = Form(None),
    child_name: str | None = Form(None),
    child_birth_date: str | None = Form(None),
    start_date: str = Form(...),
    end_date: str | None = Form(None),
    hours_per_week: str = Form(...),
    weeks_per_year: str = Form(...),
    year_mode: str = Form(...),
    hourly_rate: str = Form(...),
    complementary_hourly_rate: str | None = Form(None),
    days_per_week: str | None = Form(None),
    monday_hours: str | None = Form(None),
    tuesday_hours: str | None = Form(None),
    wednesday_hours: str | None = Form(None),
    thursday_hours: str | None = Form(None),
    friday_hours: str | None = Form(None),
    saturday_hours: str | None = Form(None),
    sunday_hours: str | None = Form(None),
    majoration_threshold: str | None = Form(None),
    majoration_rate: str | None = Form(None),
    fee_meal_amount: str | None = Form(None),
    fee_maintenance_amount: str | None = Form(None),
    salary_net_ceiling: str | None = Form(None),
    db: Session = Depends(get_db),
):
    parsed_year_mode, parsed_weeks_per_year = parse_regular_contract_mode(
        year_mode,
        weeks_per_year,
    )
    parsed_hours_per_week = float(hours_per_week)
    parsed_schedule = parse_weekly_schedule(
        hours_per_week=parsed_hours_per_week,
        required=True,
        monday_hours=monday_hours,
        tuesday_hours=tuesday_hours,
        wednesday_hours=wednesday_hours,
        thursday_hours=thursday_hours,
        friday_hours=friday_hours,
        saturday_hours=saturday_hours,
        sunday_hours=sunday_hours,
    )

    if child_id:
        child = crud.get_child(db, int(child_id))
        if not child:
            raise HTTPException(status_code=404, detail="Enfant introuvable")
    else:
        if not child_name or not child_birth_date:
            raise HTTPException(status_code=400, detail="Nom et date de naissance requis")
        child = crud.create_child(
            db, name=child_name.strip(), birth_date=date_from_iso(child_birth_date)
        )

    contract = Contract(
        child=child,
        name=contract_name.strip() if contract_name else None,
        start_date=date_from_iso(start_date),
        end_date=date_from_iso(end_date) if end_date else None,
        hours_per_week=parsed_hours_per_week,
        weeks_per_year=parsed_weeks_per_year,
        year_mode=parsed_year_mode,
        hourly_rate=float(hourly_rate),
        complementary_hourly_rate=parse_optional_positive_float(
            complementary_hourly_rate,
            field_label="Le taux des heures complementaires",
        ),
        days_per_week=parse_optional_int(days_per_week),
        **parsed_schedule,
        majoration_threshold=parse_optional_float(majoration_threshold),
        majoration_rate=parse_majoration_coefficient(majoration_rate),
        fee_meal_amount=parse_optional_float(fee_meal_amount),
        fee_maintenance_amount=parse_optional_float(fee_maintenance_amount),
        salary_net_ceiling=parse_optional_float(salary_net_ceiling),
    )
    db.add(contract)
    db.flush()

    crud.upsert_settings_snapshot(
        db,
        contract_id=contract.id,
        valid_from=contract.start_date,
        hours_per_week=contract.hours_per_week,
        weeks_per_year=contract.weeks_per_year,
        year_mode=contract.year_mode,
        hourly_rate=contract.hourly_rate,
        complementary_hourly_rate=contract.complementary_hourly_rate,
        days_per_week=contract.days_per_week,
        monday_hours=contract.monday_hours,
        tuesday_hours=contract.tuesday_hours,
        wednesday_hours=contract.wednesday_hours,
        thursday_hours=contract.thursday_hours,
        friday_hours=contract.friday_hours,
        saturday_hours=contract.saturday_hours,
        sunday_hours=contract.sunday_hours,
        majoration_threshold=contract.majoration_threshold,
        majoration_rate=contract.majoration_rate,
        fee_meal_amount=contract.fee_meal_amount,
        fee_maintenance_amount=contract.fee_maintenance_amount,
        salary_net_ceiling=contract.salary_net_ceiling,
    )
    db.commit()

    children = crud.list_children(db)
    return templates.TemplateResponse(
        request,
        "contract_new.html",
        {
            "title": "Nouveau contrat",
            "saved": True,
            "contract_id": contract.id,
            "year_modes": [m.value for m in ContractYearMode],
            "children": children,
            "selected_child_id": None,
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
