from datetime import date

from monassmat.db import session_scope
from monassmat.models import Child, Contract

with session_scope() as db:
    child = Child(name="Test", birth_date=date(2023, 1, 1))
    db.add(child)
    db.flush()

    contract = Contract(
        child_id=child.id,
        start_date=date(2025, 1, 1),
        end_date=None,
        hours_per_week=40.0,
        weeks_per_year=45.0,
        hourly_rate=5.0,
    )
    db.add(contract)
    db.flush()

    print("child_id=", child.id, "contract_id=", contract.id)
