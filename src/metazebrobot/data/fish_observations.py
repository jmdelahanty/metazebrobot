"""Screening results recorded on one fish (docs/construct_screening_link_design.md).

A fish normally inherits its calls from its origin dish. An observation
records a result on the fish itself (placed into a mixed plate, re-checked
later) and overrides the inherited call for that construct. Observations are
append-only: the latest one per construct is the fish's current call.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

RESULTS = ("positive", "negative")

SCHEMA = """
CREATE TABLE IF NOT EXISTS fish_screening_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fish_id TEXT NOT NULL,
    dish_construct TEXT NOT NULL,
    construct_key TEXT,
    result TEXT NOT NULL CHECK (result IN ('positive', 'negative')),
    observed_at TEXT NOT NULL,
    observed_by TEXT,
    source_dish_id TEXT,
    screening_datetime TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


class ObservationError(Exception):
    def __init__(self, status: int, detail: Dict[str, Any]):
        super().__init__(detail.get("error"))
        self.status = status
        self.detail = detail


def ensure_schema(conn) -> None:
    conn.execute(SCHEMA)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fish_observations_fish "
                 "ON fish_screening_observations(fish_id)")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def step_constructs(conn, dish_id: str, screening_datetime: str) -> List[Dict[str, Any]]:
    """The constructs a screening step screened for (linked indicators)."""
    return [dict(r) for r in conn.execute(
        """SELECT DISTINCT dish_construct, construct_key FROM screening_step_indicators
           WHERE dish_id = ? AND screening_datetime = ? AND kind = 'construct'""",
        (dish_id, screening_datetime),
    )]


def latest_step(conn, dish_id: str) -> Optional[str]:
    row = conn.execute(
        "SELECT MAX(screening_datetime) AS t FROM screening_steps WHERE dish_id = ?", (dish_id,)
    ).fetchone()
    return row["t"] if row else None


def record(conn, fish_id: str, result: str, constructs: List[Dict[str, Any]], *,
           observed_by: Optional[str] = None, source_dish_id: Optional[str] = None,
           screening_datetime: Optional[str] = None, notes: Optional[str] = None,
           observed_at: Optional[str] = None) -> int:
    """Record ``result`` for each construct on the fish; returns rows written."""
    if result not in RESULTS:
        raise ObservationError(422, {"error": "invalid_observation", "field": "result",
                                     "message": "positive or negative"})
    if not constructs:
        raise ObservationError(422, {"error": "invalid_observation", "field": "dish_construct",
                                     "message": "no construct to record the result for"})
    stamp = observed_at or utc_now()
    for c in constructs:
        conn.execute(
            """INSERT INTO fish_screening_observations
                   (fish_id, dish_construct, construct_key, result, observed_at, observed_by,
                    source_dish_id, screening_datetime, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (fish_id, c["dish_construct"], c.get("construct_key"), result, stamp, observed_by,
             source_dish_id, screening_datetime, notes),
        )
    return len(constructs)


def current(conn, fish_id: str) -> List[Dict[str, Any]]:
    """Latest observation per construct for a fish."""
    try:
        rows = conn.execute(
            """SELECT * FROM fish_screening_observations o
               WHERE fish_id = ? AND id = (SELECT MAX(id) FROM fish_screening_observations
                                           WHERE fish_id = o.fish_id
                                             AND dish_construct = o.dish_construct)
               ORDER BY dish_construct""",
            (fish_id,),
        ).fetchall()
    except Exception:  # table absent on older databases
        return []
    return [dict(r) for r in rows]


def all_for(conn, fish_id: str) -> List[Dict[str, Any]]:
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM fish_screening_observations WHERE fish_id = ? ORDER BY id", (fish_id,))]
    except Exception:
        return []
