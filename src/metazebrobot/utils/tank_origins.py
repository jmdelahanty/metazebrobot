"""Resolve where a tank's fish came from when no cached cross lists it.

Step 2b of docs/tank_heritage_design.md. PyRAT links a tank to its producing
cross only through the crossing's ``tanks.children``. Two things hide that
link, and this module recovers both, recording results in ``tank_origins`` so
each tank is looked up once:

- **Splits.** Fish separated into a new tank: the new tank's history has a
  ``SeparateEvent`` whose ``related`` entry marked ``source`` is the old tank.
  (``copy`` relations are the same event mirrored onto other tanks; ignored.)
- **Older crosses.** A tank released straight from a cross outside the cached
  window: search crossings recorded shortly before its date of birth and cache
  them, after which ``cross_children`` usually names the producing cross.

Fish that came from outside (shipments, founders) have neither and stay
unresolved; strain ancestry (step 2c) is the fallback for those.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

SEARCH_DAYS_BEFORE_BIRTH = 21
SEARCH_DAYS_AFTER_BIRTH = 7
# Negative results ("no cross found", "no birth date") are only true for now:
# a later sync or a PyRAT correction can change them, so they are retried
# after this many days. Crossing record-days fetched this recently are not
# fetched again (searches for nearby birth dates overlap heavily).
RETRY_AFTER_DAYS = 30

STATUS_SPLIT = "split"
STATUS_RELEASED = "released"


def ensure_tank_origins_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tank_origins (
            tank_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,              -- split | released
            source_tank_id TEXT,               -- set when status = split
            event_date TEXT,                   -- SeparateEvent / ReleaseEvent date
            date_of_birth TEXT,
            cross_search TEXT,                 -- NULL | found | not_found | no_dob
            resolved_at TEXT DEFAULT CURRENT_TIMESTAMP,
            checked_at TEXT                    -- when cross_search was last set
        )
    """)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(tank_origins)")}
    if "checked_at" not in columns:
        conn.execute("ALTER TABLE tank_origins ADD COLUMN checked_at TEXT")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crossing_search_days (
            day TEXT PRIMARY KEY,              -- a date_of_record day fully fetched
            fetched_at TEXT NOT NULL
        )
    """)


def _now() -> datetime:
    return datetime.now()


def _is_stale(timestamp: Optional[str]) -> bool:
    try:
        when = datetime.fromisoformat((timestamp or "").replace("T", " ")[:19])
    except ValueError:
        return True
    return when < _now() - timedelta(days=RETRY_AFTER_DAYS)


def record_search_days(conn: sqlite3.Connection, since: date, until: date) -> None:
    """Mark every date_of_record day in [since, until] as fetched now."""
    stamp = _now().isoformat(timespec="seconds")
    day = since
    while day <= until:
        conn.execute(
            "INSERT INTO crossing_search_days (day, fetched_at) VALUES (?, ?) "
            "ON CONFLICT(day) DO UPDATE SET fetched_at = excluded.fetched_at",
            (day.isoformat(), stamp),
        )
        day += timedelta(days=1)


def uncovered_span(conn: sqlite3.Connection, since: date, until: date) -> Optional[Tuple[date, date]]:
    """Smallest [first, last] within [since, until] not fetched recently, or None."""
    fresh = {
        row[0] for row in conn.execute(
            "SELECT day, fetched_at FROM crossing_search_days WHERE day BETWEEN ? AND ?",
            (since.isoformat(), until.isoformat()),
        ) if not _is_stale(row[1])
    }
    missing = []
    day = since
    while day <= until:
        if day.isoformat() not in fresh:
            missing.append(day)
        day += timedelta(days=1)
    return (missing[0], missing[-1]) if missing else None


def fetch_crossings_for_window(
    conn: sqlite3.Connection,
    client: Any,
    cache_crossings: Callable[[List[Dict[str, Any]]], None],
    since: date,
    until: date,
) -> bool:
    """Fetch and cache crossings recorded in the window, skipping covered days.

    Returns True when PyRAT was called.
    """
    span = uncovered_span(conn, since, until)
    if span is None:
        return False
    crossings = client.crossings_recorded(span[0], span[1])
    conn.commit()  # release our read snapshot before another connection writes
    cache_crossings(crossings)
    record_search_days(conn, span[0], span[1])
    conn.commit()
    return True


def _parse_us_date(value: Optional[str]) -> Optional[str]:
    """PyRAT history changes use MM/DD/YYYY; return ISO YYYY-MM-DD."""
    match = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})$", value or "")
    if not match:
        return None
    month, day, year = (int(g) for g in match.groups())
    return date(year, month, day).isoformat()


def parse_tank_history(tank_id: Any, history: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Origin facts from one tank's PyRAT history (newest-first, as served)."""
    tank_id = str(tank_id)
    source = None
    event_date = None
    date_of_birth = None
    for event in history:  # newest first; keep overwriting so the earliest wins
        related = event.get("related") or []
        if event.get("event_type_name") == "SeparateEvent":
            sources = [
                str(r["tank_id"]) for r in related
                if r.get("relation") == "source" and str(r.get("tank_id")) != tank_id
            ]
            if sources:
                source = sources[0]
                event_date = (event.get("event_date") or "")[:10] or None
        if event.get("event_type_name") == "ReleaseEvent":
            dob = _parse_us_date((event.get("changes") or {}).get("date_of_birth_string"))
            if dob:
                date_of_birth = dob
            if source is None:
                event_date = (event.get("event_date") or "")[:10] or None
    return {
        "status": STATUS_SPLIT if source else STATUS_RELEASED,
        "source_tank_id": source,
        "event_date": event_date,
        "date_of_birth": date_of_birth,
    }


def _producing_cross_id(conn: sqlite3.Connection, tank_id: str) -> Optional[str]:
    row = conn.execute(
        "SELECT cross_id FROM cross_children WHERE tank_id = ? LIMIT 1", (tank_id,)
    ).fetchone()
    return str(row[0]) if row else None


def _cross_parent_tanks(conn: sqlite3.Connection, cross_id: str) -> List[str]:
    return [
        str(r[0]) for r in conn.execute(
            "SELECT tank_id FROM cross_parents WHERE cross_id = ? AND tank_id IS NOT NULL",
            (cross_id,),
        )
    ]


def resolve_tank_origins(
    conn: sqlite3.Connection,
    client: Any,
    cache_crossings: Callable[[List[Dict[str, Any]]], None],
    tank_ids: Iterable[Any],
    max_generations: int = 3,
) -> Dict[str, int]:
    """Resolve producing crosses for tanks and their ancestors.

    Walks back from each tank: a cached producing cross queues its parent tanks
    (next generation); a split queues the source tank (same generation); a
    released tank with no cached cross triggers one targeted crossing search.
    ``cache_crossings`` persists fetched crossings (the app's
    ``_cache_cross_rows``), which commits on its own connection.
    """
    ensure_tank_origins_schema(conn)
    stats = {"tanks": 0, "histories": 0, "splits": 0, "searches": 0,
             "searches_skipped": 0, "found": 0, "retried": 0}
    queue: List[Tuple[str, int]] = [(str(t), 0) for t in tank_ids if t is not None]
    seen = set()
    while queue:
        tank_id, generation = queue.pop(0)
        if tank_id in seen:
            continue
        seen.add(tank_id)
        stats["tanks"] += 1

        cross_id = _producing_cross_id(conn, tank_id)
        if cross_id:
            if generation < max_generations:
                queue.extend((p, generation + 1) for p in _cross_parent_tanks(conn, cross_id))
            continue

        origin = conn.execute(
            "SELECT * FROM tank_origins WHERE tank_id = ?", (tank_id,)
        ).fetchone()
        if (origin is not None and origin["cross_search"] in ("not_found", "no_dob")
                and _is_stale(origin["checked_at"])):
            conn.execute("DELETE FROM tank_origins WHERE tank_id = ?", (tank_id,))
            stats["retried"] += 1
            origin = None
        if origin is None:
            facts = parse_tank_history(tank_id, client.tank_history(tank_id))
            stats["histories"] += 1
            conn.execute(
                """
                INSERT INTO tank_origins (tank_id, status, source_tank_id, event_date, date_of_birth)
                VALUES (?, ?, ?, ?, ?)
                """,
                (tank_id, facts["status"], facts["source_tank_id"], facts["event_date"],
                 facts["date_of_birth"]),
            )
            conn.commit()
            origin = conn.execute(
                "SELECT * FROM tank_origins WHERE tank_id = ?", (tank_id,)
            ).fetchone()

        if origin["status"] == STATUS_SPLIT and origin["source_tank_id"]:
            stats["splits"] += 1
            queue.append((str(origin["source_tank_id"]), generation))
            continue

        if origin["cross_search"] is None:
            outcome, fetched = _search_producing_cross(
                conn, client, cache_crossings, tank_id, origin["date_of_birth"])
            if outcome != "no_dob":
                stats["searches" if fetched else "searches_skipped"] += 1
            conn.execute(
                "UPDATE tank_origins SET cross_search = ?, checked_at = ? WHERE tank_id = ?",
                (outcome, _now().isoformat(timespec="seconds"), tank_id),
            )
            conn.commit()
            if outcome == "found":
                stats["found"] += 1
                seen.discard(tank_id)
                queue.insert(0, (tank_id, generation))  # now has a producing cross
    return stats


def _search_producing_cross(
    conn: sqlite3.Connection,
    client: Any,
    cache_crossings: Callable[[List[Dict[str, Any]]], None],
    tank_id: str,
    date_of_birth: Optional[str],
) -> Tuple[str, bool]:
    """Returns (outcome, whether PyRAT was called)."""
    try:
        born = datetime.strptime((date_of_birth or "")[:10], "%Y-%m-%d").date()
    except ValueError:
        return "no_dob", False
    fetched = fetch_crossings_for_window(
        conn, client, cache_crossings,
        born - timedelta(days=SEARCH_DAYS_BEFORE_BIRTH),
        born + timedelta(days=SEARCH_DAYS_AFTER_BIRTH),
    )
    return ("found" if _producing_cross_id(conn, tank_id) else "not_found"), fetched


def origin_chain(conn: sqlite3.Connection, tank_id: Any, limit: int = 10) -> Dict[str, Any]:
    """Follow recorded splits from a tank to the tank its producing cross lists.

    Returns the tank the cross lists (``tank_id`` itself when unsplit) and the
    split steps taken. Reads only ``tank_origins``; never calls PyRAT.
    """
    current = str(tank_id)
    steps: List[Dict[str, Any]] = []
    try:
        for _ in range(limit):
            if _producing_cross_id(conn, current):
                break
            row = conn.execute(
                "SELECT status, source_tank_id, event_date FROM tank_origins WHERE tank_id = ?",
                (current,),
            ).fetchone()
            if not row or row["status"] != STATUS_SPLIT or not row["source_tank_id"]:
                break
            steps.append({"from_tank_id": str(row["source_tank_id"]), "to_tank_id": current,
                          "date": row["event_date"]})
            current = str(row["source_tank_id"])
    except sqlite3.OperationalError:  # tank_origins not created yet
        pass
    return {"origin_tank_id": current, "splits": steps}
