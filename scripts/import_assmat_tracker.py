from __future__ import annotations

import argparse
import json
import re
from datetime import date, time
from pathlib import Path

from monassmat import crud
from monassmat.calculations import hours_between_times
from monassmat.db import session_scope
from monassmat.models import WorkdayKind


STATUS_MAP = {
    "travail": WorkdayKind.NORMAL,
    "conge-sans-solde": WorkdayKind.UNPAID_LEAVE,
    "conge-assmat": WorkdayKind.ASSMAT_LEAVE,
    "conge-parent": WorkdayKind.ABSENCE,
    "ferie": WorkdayKind.HOLIDAY,
}
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_time(value: str | None) -> time | None:
    if not value:
        return None
    return time.fromisoformat(value)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def extract_holidays(payload: dict) -> dict[str, str]:
    holidays = payload.get("holidays")
    if isinstance(holidays, dict):
        return holidays
    if all(isinstance(key, str) and DATE_PATTERN.match(key) for key in payload.keys()):
        return payload
    return {}


def load_holidays(paths: list[Path]) -> dict[str, str]:
    merged: dict[str, str] = {}
    for path in paths:
        payload = load_json(path)
        holidays = extract_holidays(payload)
        merged.update({key: str(value) for key, value in holidays.items()})
    return merged


def apply_holidays_to_daily_data(
    daily_data: dict,
    month_key: str | None,
    holidays: dict[str, str],
) -> dict:
    if not holidays or not month_key:
        return daily_data

    updated_data = dict(daily_data)
    month_prefix = f"{month_key}-"

    for date_key in holidays.keys():
        if not date_key.startswith(month_prefix):
            continue
        if date_key in updated_data:
            if updated_data[date_key].get("status") != "ferie":
                updated_data[date_key] = {**updated_data[date_key], "status": "ferie"}
        else:
            updated_data[date_key] = {"status": "ferie"}

    return updated_data


def month_key_from_payload(payload: dict, month_path: Path) -> str | None:
    month_key = payload.get("month")
    if isinstance(month_key, str) and re.match(r"^\d{4}-\d{2}$", month_key):
        return month_key
    stem = month_path.stem
    if re.match(r"^\d{4}-\d{2}$", stem):
        return stem
    return None


def find_holiday_files(
    months_dir: Path | None,
    month_file: Path | None,
    holidays_dir: Path | None,
    holidays_file: Path | None,
) -> list[Path]:
    paths: list[Path] = []
    if holidays_file:
        paths.append(holidays_file)
    if holidays_dir:
        paths.extend(sorted(holidays_dir.glob("holidays-*.json")))
    if months_dir:
        paths.extend(sorted(months_dir.glob("holidays-*.json")))
    if month_file and not holidays_dir and not holidays_file:
        paths.extend(sorted(month_file.parent.glob("holidays-*.json")))
    return list(dict.fromkeys(paths))


def update_contract_from_settings(contract_id: int, settings_path: Path | None) -> None:
    if not settings_path:
        return
    settings = load_json(settings_path)

    hours_per_week = settings.get("nbHeuresParSemaine")
    weeks_per_year = settings.get("semainesTravailAnnee") or settings.get("semainesPourMensualisation")
    hourly_rate = settings.get("salaireHoraireNet") or settings.get("tarifHoraire")

    with session_scope() as db:
        contract = crud.get_contract(db, contract_id)
        if not contract:
            raise ValueError(f"Contract {contract_id} not found")

        if hours_per_week is not None:
            contract.hours_per_week = float(hours_per_week)
        if weeks_per_year is not None:
            contract.weeks_per_year = float(weeks_per_year)
        if hourly_rate is not None:
            contract.hourly_rate = float(hourly_rate)


def import_month(
    contract_id: int,
    month_path: Path,
    holidays: dict[str, str],
) -> None:
    payload = load_json(month_path)
    daily_data = payload.get("dailyData") or {}
    month_key = month_key_from_payload(payload, month_path)
    daily_data = apply_holidays_to_daily_data(daily_data, month_key, holidays)

    with session_scope() as db:
        for day_str, data in daily_data.items():
            day = date.fromisoformat(day_str)
            status = data.get("status") or "travail"
            kind = STATUS_MAP.get(status, WorkdayKind.NORMAL)

            start_time = parse_time(data.get("depot"))
            end_time = parse_time(data.get("reprise"))

            if kind == WorkdayKind.NORMAL and start_time and end_time:
                hours = hours_between_times(start_time, end_time)
            else:
                hours = 0.0
                start_time = None
                end_time = None

            fee_meal = bool(data.get("fraisRepas"))
            fee_maintenance = bool(data.get("fraisEntretien"))

            crud.upsert_workday(
                db,
                contract_id=contract_id,
                day=day,
                hours=hours,
                kind=kind,
                start_time=start_time,
                end_time=end_time,
                fee_meal=fee_meal,
                fee_maintenance=fee_maintenance,
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Import assmat-tracker JSON data.")
    parser.add_argument("--contract-id", type=int, required=True)
    parser.add_argument("--month-file", type=Path)
    parser.add_argument("--months-dir", type=Path)
    parser.add_argument("--settings-file", type=Path)
    parser.add_argument("--holidays-file", type=Path)
    parser.add_argument("--holidays-dir", type=Path)
    args = parser.parse_args()

    if not args.month_file and not args.months_dir:
        raise SystemExit("Provide --month-file or --months-dir")
    if args.month_file and args.months_dir:
        raise SystemExit("Use only one of --month-file or --months-dir")

    update_contract_from_settings(args.contract_id, args.settings_file)

    holiday_files = find_holiday_files(
        months_dir=args.months_dir,
        month_file=args.month_file,
        holidays_dir=args.holidays_dir,
        holidays_file=args.holidays_file,
    )
    holidays = load_holidays(holiday_files) if holiday_files else {}

    if args.months_dir:
        month_files = sorted(args.months_dir.glob("*.json"))
        for month_path in month_files:
            if month_path.name == "settings.json":
                continue
            if month_path.name.startswith("holidays-"):
                continue
            import_month(args.contract_id, month_path, holidays)
        return

    import_month(args.contract_id, args.month_file, holidays)


if __name__ == "__main__":
    main()
