"""Per-cross screening report (docs/screening_report_design.md).

``build`` gathers what the report shows: the cross and its parents, every
dish of the cross with its screening counts and owner, each well plate's
fish, calls and thumbnails, and flags worth a second look. The page and the
saved file render the same data with templates/reports/screening_report.html.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Callable, Dict, List, Optional

from ..data import users
from ..data.data_manager import data_manager
from ..data.screening_calls import fish_calls
from ..models.fish_dish import FishDish
from ..utils.screening_labels import plate_layout, result_label, short_construct, well_sort_key

BUCKETS = (("positive_screened", "positive"), ("negative_screened", "negative"),
           ("pigmented_screened", "pigmented"))


def cross_parents(conn: sqlite3.Connection, cross_id: str) -> Dict[str, Any]:
    """The cross's parent tanks and request text, as the screening page shows them."""
    try:
        rows = conn.execute(
            """
            SELECT role, tank_id, tank_label, location_display, raw_strain_name,
                   generation, source, raw_payload
            FROM cross_parents WHERE cross_id = ? ORDER BY parent_index
            """,
            (cross_id,),
        ).fetchall()
        cross = conn.execute("SELECT data FROM crosses WHERE cross_id = ?", (cross_id,)).fetchone()
    except sqlite3.OperationalError:
        return {"parents": [], "description": None}
    parents = []
    for row in rows:
        try:
            raw = json.loads(row["raw_payload"] or "{}")
        except (TypeError, ValueError):
            raw = {}
        parents.append({
            "role": row["role"],
            "tank_id": row["tank_id"],
            "where": row["location_display"] or row["tank_label"],
            "strain": row["raw_strain_name"],
            "generation": row["generation"],
            "born": str(raw.get("date_of_birth") or "")[:10] or None,
            "manual": row["source"] == "manual",
        })
    try:
        description = (json.loads(cross["data"] or "{}").get("description") or "").strip() if cross else ""
    except (TypeError, ValueError):
        description = ""
    return {"parents": parents, "description": description or None}


def _cross_info(conn, cross_id: str) -> Dict[str, Any]:
    row = conn.execute("SELECT line_strain, data FROM crosses WHERE cross_id = ?", (cross_id,)).fetchone()
    try:
        data = json.loads(row["data"] or "{}") if row else {}
    except (TypeError, ValueError):
        data = {}
    owner = users.by_pyrat_id(conn, data["responsible_id"]) if data.get("responsible_id") is not None else None
    return {
        "cross_id": cross_id,
        "line": data.get("strain_name") or (row["line_strain"] if row else None),
        "set_up": str(data.get("date_of_set_up") or "")[:10] or None,
        "status": data.get("status"),
        "owner": users.display_name(owner, data.get("responsible_fullname")),
        "owner_user": owner,
    }


def _name(conn, username: Optional[str]) -> Optional[str]:
    return users.display_name(users.by_username(conn, username), username) if username else None


def _screened_constructs(conn, dish_id: str) -> List[str]:
    return [r["dish_construct"] for r in conn.execute(
        "SELECT DISTINCT dish_construct FROM screening_step_indicators WHERE dish_id = ? AND kind = 'construct'",
        (dish_id,))]


def _mixed_fish_calls(conn, dish_id: str) -> List[Dict[str, str]]:
    """Fish booked from this dish's steps with different results per construct (the 'other' bucket).

    Their latest observation per construct, recorded against this dish.
    """
    latest: Dict[str, Dict[str, str]] = {}
    for r in conn.execute(
            """SELECT fish_id, dish_construct, result FROM fish_screening_observations
               WHERE source_dish_id = ? ORDER BY id""", (dish_id,)):
        latest.setdefault(r["fish_id"], {})[r["dish_construct"]] = r["result"]
    return [calls for calls in latest.values() if len(set(calls.values())) > 1]


def _per_construct_from_buckets(counts: Dict[str, Optional[int]], constructs: List[str]) -> Dict[str, Dict[str, int]]:
    """A step's positive/negative groups apply to every construct it screened."""
    return {c: {"positive": counts.get("positive") or 0, "negative": counts.get("negative") or 0}
            for c in constructs}


def _held_counts(conn, dish: FishDish) -> Optional[Dict[str, Any]]:
    """What a derived dish or plate holds: its tracked fish by current call, else its group.

    A fish counts as positive when any construct call is positive, negative
    when every construct call is negative, and "no result" otherwise.
    """
    fish = data_manager.get_fish_subjects(dish.dish_id)
    if fish:
        counts = {"positive": 0, "negative": 0, "pigmented": 0, "no_result": 0}
        per_construct: Dict[str, Dict[str, int]] = {}
        for f in fish:
            calls = [c for c in (fish_calls(conn, f["fish_id"]) or {}).get("calls", []) if c["kind"] == "construct"]
            for c in calls:
                if c["result"] in ("positive", "negative"):
                    slot = per_construct.setdefault(c["dish_construct"], {"positive": 0, "negative": 0})
                    slot[c["result"]] += 1
            if any(c["result"] == "positive" for c in calls):
                counts["positive"] += 1
            elif calls and all(c["result"] == "negative" for c in calls):
                counts["negative"] += 1
            else:
                counts["no_result"] += 1
        origins: Dict[str, int] = {}
        for f in fish:
            origin = f.get("origin_dish_id") or dish.parent_dish_id
            origins[origin] = origins.get(origin, 0) + 1
        return {"counts": counts, "source": "fish calls", "origins": sorted(origins.items()),
                "per_construct": per_construct}
    label = dict(BUCKETS).get(dish.source_screening_bucket or dish.dish_population_type or "")
    if label:
        counts = {"positive": 0, "negative": 0, "pigmented": 0, "no_result": 0}
        counts[label] = dish.current_fish_count or 0
        constructs = [r["construct"] for r in conn.execute(
            "SELECT DISTINCT construct FROM dish_transgenes WHERE dish_id = ?", (dish.dish_id,))]
        return {"counts": counts, "source": "dish group",
                "origins": [(dish.parent_dish_id, dish.current_fish_count or 0)],
                "per_construct": _per_construct_from_buckets(counts, constructs)}
    return None


def _dish_row(conn, dish: FishDish) -> Dict[str, Any]:
    steps = dish.screening_results.screenings if dish.screening_results else []
    counts = {label: (dish.computed_bucket_count(bucket) or {}).get("total") for bucket, label in BUCKETS}
    destinations: Dict[str, int] = {}
    discarded = 0
    for step in steps:
        for a in step.allocations:
            if a.disposition == "derived_dish" and (a.destination_dish_id or a.derived_dish_id):
                key = a.destination_dish_id or a.derived_dish_id
                destinations[key] = destinations.get(key, 0) + a.count
            elif a.disposition == "discarded":
                discarded += a.count
    screeners = sorted({s.screened_by for s in steps if s.screened_by})
    final = dish.screening_results.final_positive_count if dish.screening_results else None
    per_construct = None
    if steps and any(s.allocations for s in steps):
        per_construct = _per_construct_from_buckets(counts, _screened_constructs(conn, dish.dish_id))
        for calls in _mixed_fish_calls(conn, dish.dish_id):  # booked as 'other': count each construct
            for construct, outcome in calls.items():
                if outcome in ("positive", "negative"):
                    per_construct.setdefault(construct, {"positive": 0, "negative": 0})[outcome] += 1
    return {
        "dish_id": dish.dish_id,
        "derived_from": dish.parent_dish_id,
        "container": ((dish.enclosure.container_type if dish.enclosure else None) or "").replace("_", " "),
        "status": dish.status,
        "owner": _name(conn, dish.responsible_user) or dish.responsible,
        "fish_count": dish.fish_count,
        "current": dish.current_fish_count,
        "steps": len(steps),
        "screened": sum(s.count_screened_this_step for s in steps),
        # Screened at the latest step but given no result (not booked to any bucket).
        "not_booked": max(steps, key=lambda s: s.screening_datetime).unallocated_count if steps else 0,
        "counts": counts,
        "has_allocations": any(s.allocations for s in steps),
        "screened_by": [_name(conn, u) for u in screeners],
        "dates": sorted({s.screening_datetime[:8] for s in steps}),
        "destinations": sorted(destinations.items()),
        "discarded": discarded,
        "finalized": final is not None,
        "final_count": final,
        "computed_positives": (dish.computed_positive_count() or {}).get("total"),
        "per_construct": per_construct,
        # Derived dishes and plates: what they hold (already counted in the parent's screen).
        "held": _held_counts(conn, dish) if dish.parent_dish_id else None,
    }


def _plate(conn, dish_id: str, thumbnail: Callable[[Dict[str, Any]], Optional[str]]) -> Optional[Dict[str, Any]]:
    units = [u for u in data_manager.get_housing_units_with_fish(dish_id) if u["unit_kind"] == "well"]
    layout = plate_layout([u["position_label"] for u in units])
    if not layout:
        return None
    images: Dict[str, Dict[str, Any]] = {}
    for link in conn.execute(
            "SELECT * FROM image_links WHERE dish_id = ? AND well_label IS NOT NULL ORDER BY id", (dish_id,)):
        images.setdefault(link["well_label"], dict(link))
    wells = {}
    for u in units:
        fish = (u.get("fish") or [None])[0]
        calls = (fish_calls(conn, fish["fish_id"]) or {}).get("calls", []) if fish else []
        image = images.get(u["position_label"])
        wells[u["position_label"]] = {
            "fish": fish["subject_label"] if fish else None,
            "call": result_label(calls) if calls else None,
            "positive": any(c["result"] == "positive" for c in calls),
            "thumbnail": thumbnail(image) if image else None,
        }
    return {"dish_id": dish_id, "layout": layout, "wells": wells,
            "imaged": sum(1 for w in wells.values() if w["thumbnail"])}


def _corrections(conn, dish_ids: List[str]) -> List[Dict[str, Any]]:
    if not dish_ids:
        return []
    marks = ",".join("?" for _ in dish_ids)
    return [dict(r) for r in conn.execute(
        f"""SELECT f.subject_label AS fish, f.dish_id, o.result, o.notes, o.observed_by, o.observed_at
            FROM fish_screening_observations o JOIN fish_subjects f ON f.fish_id = o.fish_id
            WHERE (o.notes LIKE 'Corrected from%' OR o.notes LIKE 'Correction:%')
              AND COALESCE(f.origin_dish_id, f.dish_id) IN ({marks})
            ORDER BY o.id""", dish_ids)]


def build(conn, cross_id: str, *, thumbnail: Callable[[Dict[str, Any]], Optional[str]],
          generated_at: str, generated_by: Optional[str], service_commit: Optional[str]) -> Dict[str, Any]:
    """Everything the report shows for one cross."""
    conn.row_factory = sqlite3.Row
    dish_ids = [r["dish_id"] for r in conn.execute(
        "SELECT dish_id FROM dishes WHERE cross_id = ?", (cross_id,))]
    dishes = []
    for dish_id in sorted(dish_ids, key=lambda d: [int(p) if p.isdigit() else p for p in d.split("_")]):
        data = data_manager.load_single_dish(dish_id)
        if data:
            dishes.append(FishDish(**data))
    rows = [_dish_row(conn, d) for d in dishes]
    primary = [r for r in rows if not r["derived_from"]]
    screened = [r for r in primary if r["steps"]]
    with_positives = [r for r in screened if (r["counts"]["positive"] or 0) > 0]
    flags = {
        "not_screened": [r["dish_id"] for r in primary if not r["steps"]],
        "not_finalized": [r for r in screened if not r["finalized"]],
        "positives_from_one_dish": (with_positives[0]["dish_id"]
                                    if len(with_positives) == 1 and len(screened) > 1 else None),
        "corrections": [dict(c, observed_by=_name(conn, c["observed_by"])) for c in _corrections(conn, dish_ids)],
    }
    plates = [p for p in (_plate(conn, d.dish_id, thumbnail) for d in dishes) if p]
    totals = {label: sum(r["counts"][label] or 0 for r in primary) for _, label in BUCKETS}
    constructs = [r["construct"] for r in conn.execute(
        f"SELECT DISTINCT construct FROM dish_transgenes WHERE dish_id IN ({','.join('?' for _ in dish_ids) or 'NULL'}) "
        "ORDER BY construct", dish_ids)]
    construct_totals = {c: {o: sum(((r["per_construct"] or {}).get(c) or {}).get(o, 0) for r in primary)
                            for o in ("positive", "negative")} for c in constructs}
    screeners = sorted({n for r in rows for n in r["screened_by"]})
    return {
        "cross": _cross_info(conn, cross_id),
        "parents": cross_parents(conn, cross_id),
        "dishes": rows,
        "constructs": [{"construct": c, "short": short_construct(c)} for c in constructs],
        "construct_totals": construct_totals,
        "totals": dict(totals, screened=sum(r["screened"] for r in primary),
                       not_booked=sum(r["not_booked"] for r in primary)),
        "screeners": screeners,
        "plates": plates,
        "flags": flags,
        "generated_at": generated_at,
        "generated_by": _name(conn, generated_by),
        "service_commit": service_commit,
    }


# Every saved or sent report, so it's clear what went to whom.
LOG_SCHEMA = """
CREATE TABLE IF NOT EXISTS screening_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cross_id TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    generated_by TEXT,
    service_commit TEXT,
    html_path TEXT NOT NULL,
    eml_path TEXT,
    sha256 TEXT NOT NULL,
    mode TEXT NOT NULL,
    recipients TEXT,
    result TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
)
"""


def ensure_schema(conn) -> None:
    conn.execute(LOG_SCHEMA)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_screening_reports_cross ON screening_reports(cross_id)")


def log(conn, **row: Any) -> int:
    keys = ["cross_id", "generated_at", "generated_by", "service_commit", "html_path", "eml_path",
            "sha256", "mode", "recipients", "result"]
    cursor = conn.execute(
        f"INSERT INTO screening_reports ({', '.join(keys)}) VALUES ({', '.join('?' for _ in keys)})",
        [row.get(k) for k in keys])
    return cursor.lastrowid


def history(conn, cross_id: str) -> List[Dict[str, Any]]:
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM screening_reports WHERE cross_id = ? ORDER BY id DESC", (cross_id,))]
    except sqlite3.OperationalError:
        return []
