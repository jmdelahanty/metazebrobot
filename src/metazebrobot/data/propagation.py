"""Propagation events: dishes of positives handed to aquatics to raise a line.

docs/propagation_events_design.md. An event groups one or more
propagation-terminated dishes (possibly handed over on different days). Its
generation is suggested from the parents' PyRAT generations (+1), labelled
as suggested, and editable.
"""

import re
import uuid
from typing import Any, Dict, List, Optional

SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS propagation_events (
        event_id TEXT PRIMARY KEY,
        generation TEXT,
        generation_source TEXT NOT NULL DEFAULT 'none'
            CHECK (generation_source IN ('suggested', 'entered', 'none')),
        generation_basis TEXT,
        resulting_tank_id TEXT,
        notes TEXT,
        created_by TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS propagation_event_dishes (
        dish_id TEXT PRIMARY KEY,
        event_id TEXT NOT NULL REFERENCES propagation_events(event_id) ON DELETE CASCADE,
        added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
)
_GEN = re.compile(r"^F(\d+)$", re.I)


class PropagationError(Exception):
    def __init__(self, status: int, detail: Dict[str, Any]):
        super().__init__(detail.get("error"))
        self.status = status
        self.detail = detail


def ensure_schema(conn) -> None:
    for statement in SCHEMA:
        conn.execute(statement)


def unassigned_dishes(conn) -> List[Dict[str, Any]]:
    return [dict(r, handover=handover_date(r["termination_date"])) for r in conn.execute(
        """SELECT d.dish_id, d.cross_id, d.termination_date, d.current_fish_count, d.genotype
           FROM dishes d LEFT JOIN propagation_event_dishes e ON e.dish_id = d.dish_id
           WHERE d.termination_reason = 'propagation' AND e.dish_id IS NULL
           ORDER BY d.termination_date DESC, d.dish_id""")]


def suggest_generation(conn, dish_ids: List[str]) -> Dict[str, Optional[str]]:
    """Highest parent generation + 1 over the dishes' crosses, with its basis."""
    parents = []
    for dish_id in dish_ids:
        for row in conn.execute(
                """SELECT DISTINCT cp.tank_id, cp.generation, d.cross_id
                   FROM dishes d JOIN cross_parents cp ON cp.cross_id = d.cross_id
                   WHERE d.dish_id = ?""", (dish_id,)):
            parents.append(dict(row))
    numbers = [int(m.group(1)) for p in parents if (m := _GEN.match(p["generation"] or ""))]
    if not numbers:
        return {"generation": None, "basis": None}
    seen, parts = set(), []
    for p in parents:
        key = (p["tank_id"], p["generation"])
        if key not in seen:
            seen.add(key)
            parts.append(f"tank {p['tank_id']} {p['generation'] or '?'}")
    return {"generation": f"F{max(numbers) + 1}",
            "basis": "parents: " + ", ".join(parts) + f" (highest F{max(numbers)} + 1)"}


def _check_dishes(conn, dish_ids: List[str]) -> None:
    if not dish_ids:
        raise PropagationError(422, {"error": "no_dishes", "message": "Choose at least one dish."})
    for dish_id in dish_ids:
        row = conn.execute("SELECT termination_reason FROM dishes WHERE dish_id = ?",
                           (dish_id,)).fetchone()
        if not row:
            raise PropagationError(404, {"error": "dish_not_found", "dish_id": dish_id})
        if row["termination_reason"] != "propagation":
            raise PropagationError(409, {"error": "dish_not_propagated", "dish_id": dish_id,
                                         "message": f"{dish_id} isn't terminated for propagation."})
        taken = conn.execute("SELECT event_id FROM propagation_event_dishes WHERE dish_id = ?",
                             (dish_id,)).fetchone()
        if taken:
            raise PropagationError(409, {"error": "dish_in_event", "dish_id": dish_id,
                                         "event_id": taken["event_id"]})


def _refresh_suggestion(conn, event_id: str) -> None:
    row = conn.execute("SELECT generation_source FROM propagation_events WHERE event_id = ?",
                       (event_id,)).fetchone()
    if row and row["generation_source"] != "entered":
        dish_ids = [r["dish_id"] for r in conn.execute(
            "SELECT dish_id FROM propagation_event_dishes WHERE event_id = ?", (event_id,))]
        suggestion = suggest_generation(conn, dish_ids)
        conn.execute(
            """UPDATE propagation_events SET generation = ?, generation_basis = ?,
                   generation_source = ? WHERE event_id = ?""",
            (suggestion["generation"], suggestion["basis"],
             "suggested" if suggestion["generation"] else "none", event_id),
        )


def create_event(conn, dish_ids: List[str], created_by: Optional[str] = None) -> str:
    _check_dishes(conn, dish_ids)
    event_id = str(uuid.uuid4())
    conn.execute("INSERT INTO propagation_events (event_id, created_by) VALUES (?, ?)",
                 (event_id, created_by))
    for dish_id in dish_ids:
        conn.execute("INSERT INTO propagation_event_dishes (dish_id, event_id) VALUES (?, ?)",
                     (dish_id, event_id))
    _refresh_suggestion(conn, event_id)
    return event_id


def add_dishes(conn, event_id: str, dish_ids: List[str]) -> None:
    if not conn.execute("SELECT 1 FROM propagation_events WHERE event_id = ?", (event_id,)).fetchone():
        raise PropagationError(404, {"error": "propagation_event_not_found", "event_id": event_id})
    _check_dishes(conn, dish_ids)
    for dish_id in dish_ids:
        conn.execute("INSERT INTO propagation_event_dishes (dish_id, event_id) VALUES (?, ?)",
                     (dish_id, event_id))
    _refresh_suggestion(conn, event_id)


def remove_dish(conn, event_id: str, dish_id: str) -> None:
    """Take a dish out; an event left with no dishes is deleted."""
    conn.execute("DELETE FROM propagation_event_dishes WHERE event_id = ? AND dish_id = ?",
                 (event_id, dish_id))
    if not conn.execute("SELECT 1 FROM propagation_event_dishes WHERE event_id = ?",
                        (event_id,)).fetchone():
        conn.execute("DELETE FROM propagation_events WHERE event_id = ?", (event_id,))
    else:
        _refresh_suggestion(conn, event_id)


def update_details(conn, event_id: str, generation: Optional[str], resulting_tank_id: Optional[str],
                   notes: Optional[str]) -> None:
    """Entered generation sticks; an empty one returns to the suggestion."""
    generation = (generation or "").strip()
    current = conn.execute("SELECT generation, generation_source FROM propagation_events "
                           "WHERE event_id = ?", (event_id,)).fetchone()
    if not current:
        raise PropagationError(404, {"error": "propagation_event_not_found", "event_id": event_id})
    if generation and generation != current["generation"]:
        conn.execute("UPDATE propagation_events SET generation = ?, generation_source = 'entered', "
                     "generation_basis = 'entered by hand' WHERE event_id = ?",
                     (generation.upper() if _GEN.match(generation) else generation, event_id))
    elif not generation:
        conn.execute("UPDATE propagation_events SET generation_source = 'none' WHERE event_id = ?",
                     (event_id,))
        _refresh_suggestion(conn, event_id)
    conn.execute("UPDATE propagation_events SET resulting_tank_id = ?, notes = ? WHERE event_id = ?",
                 ((resulting_tank_id or "").strip() or None, (notes or "").strip() or None, event_id))


def handover_date(termination_date: Optional[str]) -> Optional[str]:
    """'20261015' -> '2026-10-15' (dish termination dates are stored compact)."""
    d = termination_date or ""
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if re.fullmatch(r"\d{8}", d) else (d or None)


def _dishes(conn, event_id: str) -> List[Dict[str, Any]]:
    return [dict(r, handover=handover_date(r["termination_date"])) for r in conn.execute(
        """SELECT d.dish_id, d.cross_id, d.termination_date, d.current_fish_count, d.genotype,
                  d.parent_dish_id, d.source_screening_datetime
           FROM propagation_event_dishes e JOIN dishes d ON d.dish_id = e.dish_id
           WHERE e.event_id = ? ORDER BY d.termination_date, d.dish_id""", (event_id,))]


def line_key(promoter: Optional[str], construct_key: Optional[str]) -> Optional[str]:
    """A line is promoter + construct key: 'gfap-grabatp10' vs 'elavl3-grabatp10'."""
    if not construct_key:
        return None
    return f"{(promoter or '').strip().lower()}-{construct_key}".strip("-")


def constructs_for(conn, dish_ids: List[str]) -> List[Dict[str, Any]]:
    seen, out = set(), []
    for dish_id in dish_ids:
        for r in conn.execute("SELECT construct, promoter, construct_key FROM dish_transgenes "
                              "WHERE dish_id = ?", (dish_id,)):
            key = line_key(r["promoter"], r["construct_key"])
            if key and key not in seen:
                seen.add(key)
                out.append({"construct": r["construct"], "line_key": key})
    return out


def get_event(conn, event_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM propagation_events WHERE event_id = ?", (event_id,)).fetchone()
    if not row:
        return None
    event = dict(row)
    dishes = _dishes(conn, event_id)
    event["dishes"] = dishes
    dates = sorted(d["handover"] for d in dishes if d["handover"])
    event["first_handover"] = dates[0] if dates else None
    event["last_handover"] = dates[-1] if dates else None
    event["fish_count"] = sum(d["current_fish_count"] or 0 for d in dishes)
    event["constructs"] = constructs_for(conn, [d["dish_id"] for d in dishes])
    return event


def list_events(conn) -> List[Dict[str, Any]]:
    ids = [r["event_id"] for r in conn.execute("SELECT event_id FROM propagation_events")]
    events = [get_event(conn, i) for i in ids]
    return sorted(events, key=lambda e: e["first_handover"] or "", reverse=True)


def line_history(conn, key: str) -> List[Dict[str, Any]]:
    """Events with a dish carrying this line (see line_key), oldest first."""
    events = [e for e in list_events(conn)
              if any(c["line_key"] == key for c in e["constructs"])]
    return sorted(events, key=lambda e: e["first_handover"] or "")
