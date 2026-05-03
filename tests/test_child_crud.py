from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from monassmat.models import Base, Child
from monassmat import crud


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


def test_create_child(db):
    child = crud.create_child(db, name="Emma", birth_date=date(2020, 3, 15))
    db.commit()
    assert child.id is not None
    assert child.name == "Emma"
    assert child.birth_date == date(2020, 3, 15)


def test_get_child(db):
    child = crud.create_child(db, name="Léo", birth_date=date(2021, 6, 1))
    db.commit()
    fetched = crud.get_child(db, child.id)
    assert fetched is not None
    assert fetched.name == "Léo"


def test_get_child_not_found(db):
    assert crud.get_child(db, 999) is None


def test_list_children_empty(db):
    assert crud.list_children(db) == []


def test_list_children_ordered_by_name(db):
    crud.create_child(db, name="Zoé", birth_date=date(2020, 1, 1))
    crud.create_child(db, name="Alice", birth_date=date(2021, 1, 1))
    db.commit()
    children = crud.list_children(db)
    assert [c.name for c in children] == ["Alice", "Zoé"]


def test_update_child(db):
    child = crud.create_child(db, name="Tom", birth_date=date(2019, 5, 10))
    db.commit()
    updated = crud.update_child(db, child_id=child.id, name="Thomas", birth_date=date(2019, 5, 10))
    db.commit()
    assert updated is not None
    assert updated.name == "Thomas"


def test_update_child_not_found(db):
    assert crud.update_child(db, child_id=999, name="X", birth_date=date(2020, 1, 1)) is None
