"""Dish owner from the cross's PyRAT responsible, chosen from users (docs/user_scoped_workflow_design.md)."""

import json
import sqlite3
import uuid

import pytest

from metazebrobot.data import users
from metazebrobot.data.data_manager import data_manager


@pytest.fixture(autouse=True)
def _no_users_left_behind():
    """The test database is shared: users seeded here would change other tests' pages."""
    yield
    try:
        with data_manager.get_connection() as conn:
            conn.execute("DELETE FROM users")
            conn.commit()
    except Exception:  # this test never opened the shared database
        pass

PEOPLE = [
    {"userid": 115, "username": "lovelacea", "first_name": "Ada", "last_name": "Lovelace", "fullname": "Lovelace Ada"},
    {"userid": 135, "username": "turinga", "first_name": "Alan", "last_name": "Turing", "fullname": "Turing Alan"},
    {"userid": 300, "username": "hopperg", "first_name": "Grace", "last_name": "Hopper", "fullname": "Hopper Grace"},
]


def _seed(cross_owner_id):
    cross = f"9{uuid.uuid4().int % 10**8}"
    with data_manager.get_connection() as conn:
        conn.row_factory = sqlite3.Row
        users.upsert_from_pyrat(conn, PEOPLE, "active", "2026-11-04 00:00:00")
        users.mark_app_users(conn, [115, 135])  # the cross owner (300) isn't in the picker
        conn.execute("INSERT INTO crosses (cross_id, data) VALUES (?, ?)",
                     (cross, json.dumps({"crossing_id": int(cross), "responsible_id": cross_owner_id,
                                         "responsible_fullname": "Hopper Grace", "strain_name": "wt"})))
        conn.commit()
    return cross


def test_owner_defaults_to_the_cross_owner_and_can_be_someone_else(client):
    cross = _seed(300)
    form = client.get("/dishes/new/cross-info", params={"cross_id": cross}).text
    assert '<option value="hopperg" selected>Grace Hopper (cross owner)</option>' in form
    assert '<option value="turinga">Alan Turing</option>' in form

    resp = client.post("/dishes/new", data={
        "cross_id": cross, "dish_number": 1, "genotype": "wt", "responsible_user": "turinga",
        "dof": "2026-10-23", "fish_count": 20}, follow_redirects=False)
    assert resp.status_code == 303
    dish = data_manager.load_single_dish(f"{cross}_1")
    assert (dish["responsible_user"], dish["responsible"]) == ("turinga", "Turing Alan")

    plate = client.post(f"/dishes/{cross}_1/plate/new", data={"wells": 12},
                        follow_redirects=False).headers["location"].split("/")[2]
    assert data_manager.load_single_dish(plate)["responsible_user"] == "turinga"  # derived dishes inherit


def test_free_text_responsible_still_works_without_users(client):
    cross = f"9{uuid.uuid4().int % 10**8}"
    client.post("/dishes/new", data={"cross_id": cross, "dish_number": 1, "genotype": "wt",
                                     "responsible": "someone", "dof": "2026-10-23"})
    dish = data_manager.load_single_dish(f"{cross}_1")
    assert dish["responsible"] == "someone" and dish.get("responsible_user") is None


def test_backfill_prefers_the_named_person_then_the_cross_owner(tmp_path):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "backfill_owner", Path(__file__).resolve().parents[1] / "scripts" / "backfill_dish_owner.py")
    backfill = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(backfill)
    db = tmp_path / "o.db"
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        users.ensure_schema(conn)
        users.upsert_from_pyrat(conn, PEOPLE, "active", "2026-11-04 00:00:00")
        conn.execute("CREATE TABLE crosses (cross_id TEXT, data TEXT)")
        conn.execute("CREATE TABLE dishes (dish_id TEXT, cross_id TEXT, responsible TEXT, data TEXT)")
        conn.execute("INSERT INTO crosses VALUES ('1', ?)", (json.dumps({"responsible_id": 300}),))
        conn.executemany("INSERT INTO dishes VALUES (?, '1', ?, '{}')", [
            ("1_1", "Lovelace Ada"),   # someone used another member's cross: the named person
            ("1_2", "Ada Lovelace"),   # either name order
            ("1_3", "tour"),           # unknown text: the cross owner
        ])
    backfill.main(["--db-path", str(db)])
    with sqlite3.connect(db) as conn:
        got = dict(conn.execute("SELECT dish_id, json_extract(data, '$.responsible_user') FROM dishes"))
    assert got == {"1_1": "lovelacea", "1_2": "lovelacea", "1_3": "hopperg"}
