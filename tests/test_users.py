"""PyRAT users table: names, picker membership (docs/user_scoped_workflow_design.md)."""

import importlib.util
import sqlite3
from pathlib import Path

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

_spec = importlib.util.spec_from_file_location(
    "sync_users", Path(__file__).resolve().parents[1] / "scripts" / "sync_users.py")
sync_users = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sync_users)

PYRAT_USERS = {
    "active": [
        {"userid": 115, "username": "lovelacea", "first_name": "Ada", "last_name": "Lovelace",
         "fullname": "Lovelace Ada"},
        {"userid": 135, "username": "turinga", "first_name": "Alan", "last_name": "Turing",
         "fullname": "Turing Alan"},
        {"userid": 500, "username": "elsewhere", "first_name": "Other", "last_name": "Lab",
         "fullname": "Lab Other"},
        {"userid": 1, "username": "hopperg", "first_name": "Grace", "last_name": "Hopper",
         "fullname": "Hopper Grace"},
    ],
    "inactive": [{"userid": 41, "username": "old", "first_name": None, "last_name": None,
                  "fullname": "Old Account"}],
}


class _Client:
    def users(self, keys, status):
        return PYRAT_USERS[status]

    def user(self, username):
        return next(u for us in PYRAT_USERS.values() for u in us if u["username"] == username)

    def tanks(self, keys, **filters):  # tanks the lab owner owns, by Responsible
        return [{"responsible_id": 115, "responsible_fullname": "Lovelace Ada"},
                {"responsible_id": 135, "responsible_fullname": "Turing Alan"},
                {"responsible_id": 41, "responsible_fullname": "Old Account"}]


def test_display_name_prefers_first_and_last():
    assert users.display_name({"first_name": "Ada", "last_name": "Lovelace",
                               "fullname": "Lovelace Ada"}) == "Ada Lovelace"
    assert users.display_name({"fullname": "Old Account"}) == "Old Account"
    assert users.display_name(None, "lovelacea") == "lovelacea"


def test_sync_marks_only_active_lab_members_and_keeps_local_fields(tmp_path):
    with sqlite3.connect(tmp_path / "u.db") as conn:
        conn.row_factory = sqlite3.Row
        assert sync_users.sync(conn, _Client(), "hopperg") == (5, 2)
        assert [u["username"] for u in users.app_users(conn)] == ["lovelacea", "turinga"]
        conn.execute("UPDATE users SET email = 'x@example.org' WHERE username = 'lovelacea'")
        PYRAT_USERS["active"][0]["first_name"] = "Augusta"
        try:
            sync_users.sync(conn, _Client())
        finally:
            PYRAT_USERS["active"][0]["first_name"] = "Ada"
        me = users.by_username(conn, "lovelacea")
        assert (me["first_name"], me["email"], me["app_user"]) == ("Augusta", "x@example.org", 1)


def test_picker_shows_names_from_the_users_table(client):
    with data_manager.get_connection() as conn:
        conn.row_factory = sqlite3.Row
        users.upsert_from_pyrat(conn, PYRAT_USERS["active"], "active", "2026-11-04 00:00:00")
        users.mark_app_users(conn, [115, 135])
        conn.commit()
    page = client.get("/screening/", cookies={"metazebrobot_user": "lovelacea"}).text
    assert '<option value="lovelacea" selected>Ada Lovelace</option>' in page
    assert ">Alan Turing</option>" in page and "elsewhere" not in page
