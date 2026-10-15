"""When and how an individually tracked fish's record ends.

docs/fish_deaths_design.md. A fish ends on its own (found dead, euthanized,
other: a death, which also lowers its dish's count by one through the
existing mortality records) or with its dish's termination (euthanasia ->
dead, propagation -> propagated; reversible, no count change).

``ended_at`` is UTC ``YYYY-MM-DD HH:MM:SS`` like MetaZebrobot's other stamps,
or a lab date ``YYYY-MM-DD`` when ``ended_precision`` is ``day``. An ended fish
keeps ``current_unit_id`` as its last well; its occupancy is closed.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ..utils.lab_time import LAB_TIMEZONE

FISH_END_REASONS = ("found_dead", "euthanized", "other")
TERMINATION_ENDINGS = {
    "euthanasia": ("dead", "euthanized"),
    "propagation": ("propagated", "propagated"),
}


class FishEndingError(Exception):
    def __init__(self, status: int, detail: Dict[str, Any]):
        super().__init__(detail.get("error"))
        self.status = status
        self.detail = detail


def ensure_columns(conn) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(fish_subjects)")}
    additions = {
        "status": "TEXT NOT NULL DEFAULT 'alive' "
                  "CHECK (status IN ('alive', 'dead', 'propagated'))",
        "ended_at": "TEXT",
        "ended_precision": "TEXT CHECK (ended_precision IN ('time', 'day'))",
        "end_reason": "TEXT CHECK (end_reason IN "
                      "('found_dead', 'euthanized', 'propagated', 'other'))",
        "end_source": "TEXT CHECK (end_source IN ('fish', 'dish_termination'))",
        "end_notes": "TEXT",
    }
    for col, ddl in additions.items():
        if col not in cols:
            conn.execute(f"ALTER TABLE fish_subjects ADD COLUMN {col} {ddl}")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _parse_rfc3339_utc(value: str) -> Optional[datetime]:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def end_fish(conn, fish_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """End one fish (a death). Returns {dish_id, changed}; raises FishEndingError.

    Body: ``reason`` (found_dead | euthanized | other), optional ``at`` (RFC
    3339 UTC, default now) and ``notes``. An identical repeat is a no-op.
    """
    reason = body.get("reason")
    if reason not in FISH_END_REASONS:
        raise FishEndingError(422, {"error": "invalid_fish_end", "field": "reason",
                                    "message": f"one of {', '.join(FISH_END_REASONS)}"})
    if "at" in body and body["at"] is not None:
        instant = _parse_rfc3339_utc(body["at"])
        if instant is None:
            raise FishEndingError(422, {"error": "invalid_fish_end", "field": "at",
                                        "message": "RFC 3339 UTC ending in Z"})
    else:
        instant = datetime.now(timezone.utc)
    ended_at = instant.strftime("%Y-%m-%d %H:%M:%S")
    notes = body.get("notes")

    fish = conn.execute(
        """SELECT fish_id, dish_id, subject_label, current_unit_id, status, end_reason,
                  ended_at, end_notes FROM fish_subjects WHERE fish_id = ?""",
        (fish_id,),
    ).fetchone()
    if not fish:
        raise FishEndingError(404, {"error": "fish_not_found", "fish_id": fish_id})
    if fish["status"] != "alive":
        if (fish["end_reason"], fish["ended_at"], fish["end_notes"]) == (reason, ended_at, notes):
            return {"dish_id": fish["dish_id"], "changed": False}
        raise FishEndingError(409, {"error": "fish_already_ended", "fish_id": fish_id,
                                    "status": fish["status"]})

    open_unit = conn.execute(
        "SELECT unit_id FROM housing_unit_occupancy WHERE fish_id = ? AND moved_out_at IS NULL",
        (fish_id,),
    ).fetchone()
    conn.execute(
        """UPDATE fish_subjects SET status = 'dead', ended_at = ?, ended_precision = 'time',
               end_reason = ?, end_source = 'fish', end_notes = ? WHERE fish_id = ?""",
        (ended_at, reason, notes, fish_id),
    )
    conn.execute(
        "UPDATE housing_unit_occupancy SET moved_out_at = ? WHERE fish_id = ? AND moved_out_at IS NULL",
        (ended_at, fish_id),
    )

    # The death lowers the dish's count through the existing mortality records.
    check_time = instant.astimezone(LAB_TIMEZONE).strftime("%Y%m%dT%H:%M:%S")
    note = f"Fish {fish['subject_label'] or fish_id[:8]} died ({reason})"
    if open_unit:
        conn.execute(
            """INSERT INTO housing_unit_checks (unit_id, check_time, fed, water_changed,
                   num_dead, notes) VALUES (?, ?, 0, 0, 1, ?)""",
            (open_unit["unit_id"], check_time, note),
        )
    else:
        existing = conn.execute(
            "SELECT num_dead, notes FROM quality_checks WHERE dish_id = ? AND check_time = ?",
            (fish["dish_id"], check_time),
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE quality_checks SET num_dead = COALESCE(num_dead, 0) + 1,
                       notes = TRIM(COALESCE(notes, '') || ' ' || ?)
                   WHERE dish_id = ? AND check_time = ?""",
                (note, fish["dish_id"], check_time),
            )
        else:
            conn.execute(
                """INSERT INTO quality_checks (dish_id, check_time, fed, water_changed,
                       num_dead, notes) VALUES (?, ?, 0, 0, 1, ?)""",
                (fish["dish_id"], check_time, note),
            )
    return {"dish_id": fish["dish_id"], "changed": True}


def end_fish_for_terminated_dish(conn, dish_id: str, termination_reason: Optional[str],
                                 termination_date: Optional[str]) -> int:
    """Living fish in a terminated dish end with it (no count change)."""
    ending = TERMINATION_ENDINGS.get(termination_reason or "")
    if not ending:
        return 0
    status, reason = ending
    day = (f"{termination_date[:4]}-{termination_date[4:6]}-{termination_date[6:8]}"
           if termination_date else datetime.now(LAB_TIMEZONE).strftime("%Y-%m-%d"))
    fish_ids = [r["fish_id"] for r in conn.execute(
        "SELECT fish_id FROM fish_subjects WHERE dish_id = ? AND status = 'alive'", (dish_id,))]
    for fish_id in fish_ids:
        conn.execute(
            """UPDATE fish_subjects SET status = ?, ended_at = ?, ended_precision = 'day',
                   end_reason = ?, end_source = 'dish_termination', end_notes = ?
               WHERE fish_id = ?""",
            (status, day, reason, f"Dish {dish_id} terminated ({termination_reason})", fish_id),
        )
        conn.execute(
            """UPDATE housing_unit_occupancy SET moved_out_at = ?
               WHERE fish_id = ? AND moved_out_at IS NULL""",
            (_utc_now(), fish_id),
        )
    return len(fish_ids)


def revert_dish_termination_endings(conn, dish_id: str) -> int:
    """Undo endings inherited from this dish's termination (not fish-level ones)."""
    rows = conn.execute(
        """SELECT fish_id, current_unit_id FROM fish_subjects
           WHERE dish_id = ? AND end_source = 'dish_termination'""",
        (dish_id,),
    ).fetchall()
    for row in rows:
        conn.execute(
            """UPDATE fish_subjects SET status = 'alive', ended_at = NULL, ended_precision = NULL,
                   end_reason = NULL, end_source = NULL, end_notes = NULL WHERE fish_id = ?""",
            (row["fish_id"],),
        )
        if row["current_unit_id"]:
            conn.execute(
                """INSERT INTO housing_unit_occupancy (fish_id, unit_id, moved_in_at, reason)
                   VALUES (?, ?, CURRENT_TIMESTAMP, 'restored')""",
                (row["fish_id"], row["current_unit_id"]),
            )
    return len(rows)
