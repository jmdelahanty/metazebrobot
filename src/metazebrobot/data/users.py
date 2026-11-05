"""PyRAT users, kept locally for names and the user picker.

See docs/user_scoped_workflow_design.md, "Owners, screeners and names". The
PyRAT user id is the key; records elsewhere store the username; pages show
"First Last". ``app_user`` marks who appears in the picker.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    pyrat_userid INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    first_name TEXT,
    last_name TEXT,
    fullname TEXT,
    status TEXT,
    email TEXT,
    app_user INTEGER NOT NULL DEFAULT 0,
    synced_at TEXT
)
"""

# Fields requested from PyRAT api/v3/users.
PYRAT_FIELDS = ["userid", "username", "first_name", "last_name", "fullname"]


def ensure_schema(conn) -> None:
    conn.execute(SCHEMA)


def display_name(user: Optional[Dict[str, Any]], fallback: Optional[str] = None) -> Optional[str]:
    """'First Last' from first and last name, else PyRAT's full name, else ``fallback``."""
    if not user:
        return fallback
    name = " ".join(p for p in (user.get("first_name"), user.get("last_name")) if p)
    return name or user.get("fullname") or user.get("username") or fallback


def upsert_from_pyrat(conn, records: Iterable[Dict[str, Any]], status: str, synced_at: str) -> int:
    """Insert or refresh users from PyRAT; keeps the local email and app_user."""
    count = 0
    for r in records:
        if r.get("userid") is None or not r.get("username"):
            continue
        conn.execute(
            """INSERT INTO users (pyrat_userid, username, first_name, last_name, fullname, status, synced_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(pyrat_userid) DO UPDATE SET
                   username = excluded.username, first_name = excluded.first_name,
                   last_name = excluded.last_name, fullname = excluded.fullname,
                   status = excluded.status, synced_at = excluded.synced_at""",
            (int(r["userid"]), r["username"], r.get("first_name"), r.get("last_name"),
             r.get("fullname"), status, synced_at),
        )
        count += 1
    return count


def mark_app_users(conn, pyrat_userids: Iterable[int]) -> int:
    """Add these users to the picker (never removes anyone)."""
    ids = [int(i) for i in pyrat_userids]
    for i in ids:
        conn.execute("UPDATE users SET app_user = 1 WHERE pyrat_userid = ?", (i,))
    return len(ids)


def app_users(conn) -> List[Dict[str, Any]]:
    """Picker users, active first, by last then first name."""
    return [dict(r) for r in conn.execute(
        """SELECT * FROM users WHERE app_user = 1
           ORDER BY status <> 'active', COALESCE(last_name, fullname, username), first_name""")]


def by_username(conn, username: str) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return dict(row) if row else None


def by_pyrat_id(conn, pyrat_userid: int) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM users WHERE pyrat_userid = ?", (pyrat_userid,)).fetchone()
    return dict(row) if row else None
