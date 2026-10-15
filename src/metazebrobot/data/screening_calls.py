"""Per-construct screening calls for dishes and the fish that came from them.

docs/construct_screening_link_design.md ("Results per construct, inherited by
fish") and docs/fish_origin_and_location_design.md ("Screening results are
inherited"). A call says what a screening step established about the fish in
a dish: for each construct indicator of the step, positive or negative, plus
pigmented for fish moved out as pigmented. Fish inherit the calls of their
origin dish's lineage up to the time they left it.

All step and transfer times are lab-local compact strings (YYYYMMDDTHH:MM:SS),
which sort as text. Occupancy times are UTC and are converted first.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..utils.lab_time import LAB_TIMEZONE

_RESULT_BY_BUCKET = {"positive_screened": "positive", "negative_screened": "negative"}
_CONFIDENCE_ORDER = ["none", "low", "medium", "high"]
_MAX_DEPTH = 20


def utc_to_lab_compact(value: Optional[str]) -> Optional[str]:
    """'YYYY-MM-DD HH:MM:SS' (UTC) -> lab-local 'YYYYMMDDTHH:MM:SS'."""
    if not value:
        return None
    instant = datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return instant.astimezone(LAB_TIMEZONE).strftime("%Y%m%dT%H:%M:%S")


def _step_indicators(conn, dish_id: str, step_datetime: str) -> List[Dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        """SELECT kind, dish_construct, construct_key, match_confidence, note
           FROM screening_step_indicators
           WHERE dish_id = ? AND screening_datetime = ? AND kind = 'construct'""",
        (dish_id, step_datetime),
    )]


def _step_dpf(conn, dish_id: str, step_datetime: str) -> Optional[int]:
    row = conn.execute(
        "SELECT dpf_screened FROM screening_steps WHERE dish_id = ? AND screening_datetime = ?",
        (dish_id, step_datetime),
    ).fetchone()
    return row["dpf_screened"] if row else None


def _calls_for(conn, dish_id, step_datetime, result, basis, note=None):
    dpf = _step_dpf(conn, dish_id, step_datetime)
    calls = []
    for ind in _step_indicators(conn, dish_id, step_datetime):
        calls.append({
            "kind": "construct",
            "construct_key": ind["construct_key"],
            "dish_construct": ind["dish_construct"],
            "result": result,
            "confidence": ind["match_confidence"],
            "established_in_dish": dish_id,
            "screening_datetime": step_datetime,
            "dpf": dpf,
            "basis": basis,
            "note": ind["note"] or note,
        })
    return calls


def _merge(calls: List[Dict[str, Any]], new: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Later calls replace earlier ones for the same construct (or pigment)."""
    index = {(c["kind"], c.get("dish_construct")): i for i, c in enumerate(calls)}
    for call in new:
        key = (call["kind"], call.get("dish_construct"))
        if key in index:
            earlier = calls[index[key]]
            if earlier["result"] == call["result"]:
                # A later step confirming the same result keeps the stronger confidence.
                call = {**call, "confidence": max(earlier["confidence"], call["confidence"],
                                                  key=_CONFIDENCE_ORDER.index)}
            calls[index[key]] = call
        else:
            index[key] = len(calls)
            calls.append(call)
    return calls


def _left_parent_at(conn, dish: Dict[str, Any]) -> Optional[str]:
    """When this dish's fish left its parent (lab-local compact), if known."""
    if dish.get("source_screening_datetime"):
        return dish["source_screening_datetime"]
    row = conn.execute(
        """SELECT MIN(event_datetime) AS t FROM dish_transfer_events
           WHERE source_dish_id = ? AND destination_dish_id = ?""",
        (dish["parent_dish_id"], dish["dish_id"]),
    ).fetchone()
    if row and row["t"]:
        return row["t"]
    created = dish.get("date_created")
    return f"{created}T23:59:59" if created else None


def dish_calls(conn, dish_id: str, before: Optional[str] = None, _depth: int = 0) -> Dict[str, Any]:
    """Calls established for the fish in ``dish_id`` (from steps before ``before``).

    Returns ``{"calls": [...], "status": "ok" | "partial_mixed_sources" |
    "unknown_dish"}``. Fish transferred in from dishes other than the parent
    only keep calls every source agrees on (a plate of + and - fish has no
    dish-level call; its fish carry their own via their origin).
    """
    dish = conn.execute(
        """SELECT dish_id, parent_dish_id, source_screening_datetime,
                  source_screening_bucket, date_created FROM dishes WHERE dish_id = ?""",
        (dish_id,),
    ).fetchone()
    if not dish or _depth > _MAX_DEPTH:
        return {"calls": [], "status": "unknown_dish"}
    dish = dict(dish)
    calls: List[Dict[str, Any]] = []
    parent = dish.get("parent_dish_id")
    if parent:
        left = _left_parent_at(conn, dish)
        inherited = dish_calls(conn, parent, before=left, _depth=_depth + 1)
        calls = _merge(calls, inherited["calls"])
        bucket = dish.get("source_screening_bucket")
        step = dish.get("source_screening_datetime")
        if step and bucket in _RESULT_BY_BUCKET:
            calls = _merge(calls, _calls_for(conn, parent, step, _RESULT_BY_BUCKET[bucket],
                                             "moved_out_of_parent_as_" + bucket))
        elif step and bucket == "pigmented_screened":
            calls = _merge(calls, [{
                "kind": "pigment", "construct_key": None, "dish_construct": None,
                "result": "pigmented", "confidence": "high", "established_in_dish": parent,
                "screening_datetime": step, "dpf": _step_dpf(conn, parent, step),
                "basis": "moved_out_of_parent_as_pigmented_screened", "note": None,
            }])

    steps = [r["screening_datetime"] for r in conn.execute(
        "SELECT screening_datetime FROM screening_steps WHERE dish_id = ? ORDER BY screening_datetime",
        (dish_id,),
    )]
    for step in steps:
        if before and step >= before:
            break
        remaining = {r["bucket"] for r in conn.execute(
            """SELECT bucket FROM screening_step_allocations
               WHERE dish_id = ? AND screening_datetime = ? AND disposition = 'remain_parent'""",
            (dish_id, step),
        )}
        if len(remaining) == 1 and next(iter(remaining)) in _RESULT_BY_BUCKET:
            bucket = next(iter(remaining))
            calls = _merge(calls, _calls_for(conn, dish_id, step, _RESULT_BY_BUCKET[bucket],
                                             "remained_in_dish_as_" + bucket))
        elif not _has_allocations(conn, dish_id, step):
            kept = conn.execute(
                "SELECT number_kept FROM screening_steps WHERE dish_id = ? AND screening_datetime = ?",
                (dish_id, step),
            ).fetchone()["number_kept"]
            if kept:  # legacy steps: kept fish passed the step's criteria and stayed
                legacy = _calls_for(conn, dish_id, step, "positive", "legacy_number_kept")
                for call in legacy:
                    call["confidence"] = _cap(call["confidence"], "medium")
                calls = _merge(calls, legacy)

    # Fish transferred in from other dishes: keep only what every contributor
    # (this dish's own lineage, if it has one, and each source) agrees on.
    sources = conn.execute(
        """SELECT source_dish_id, MIN(event_datetime) AS t FROM dish_transfer_events
           WHERE destination_dish_id = ? AND source_dish_id IS NOT ?
           GROUP BY source_dish_id""",
        (dish_id, dish.get("parent_dish_id")),
    ).fetchall()
    if not sources:
        return {"calls": calls, "status": "ok"}
    contributors = [calls] if (parent or steps) else []
    status = "ok"
    for row in sources:
        other = dish_calls(conn, row["source_dish_id"], before=row["t"], _depth=_depth + 1)
        if other["status"] != "ok":
            status = "partial_mixed_sources"
        contributors.append(other["calls"])
    agreed = contributors[0]
    for other_calls in contributors[1:]:
        agreed = _agree(agreed, other_calls)
    if any(len(c) != len(agreed) for c in contributors):
        status = "partial_mixed_sources"
    return {"calls": agreed, "status": status}


def _has_allocations(conn, dish_id: str, step: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM screening_step_allocations WHERE dish_id = ? AND screening_datetime = ?",
        (dish_id, step),
    ).fetchone() is not None


def _cap(confidence: str, ceiling: str) -> str:
    return min(confidence, ceiling, key=_CONFIDENCE_ORDER.index)


def _agree(mine: List[Dict[str, Any]], theirs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Calls present in both with the same result; the lower confidence wins."""
    lookup = {(c["kind"], c.get("dish_construct")): c for c in theirs}
    agreed = []
    for call in mine:
        other = lookup.get((call["kind"], call.get("dish_construct")))
        if other and other["result"] == call["result"]:
            agreed.append({**call, "confidence": _cap(call["confidence"], other["confidence"])})
    return agreed


def fish_calls(conn, fish_id: str) -> Optional[Dict[str, Any]]:
    """Inherited calls for a fish: its origin dish's, up to when it left it."""
    fish = conn.execute(
        """SELECT fish_id, dish_id, COALESCE(origin_dish_id, dish_id) AS origin_dish_id
           FROM fish_subjects WHERE fish_id = ?""",
        (fish_id,),
    ).fetchone()
    if not fish:
        return None
    origin = fish["origin_dish_id"]
    left_origin = None
    for row in conn.execute(
        """SELECT o.moved_in_at FROM housing_unit_occupancy o
           JOIN housing_units u ON u.unit_id = o.unit_id
           WHERE o.fish_id = ? AND u.dish_id <> ? ORDER BY o.moved_in_at LIMIT 1""",
        (fish_id, origin),
    ):
        left_origin = utc_to_lab_compact(row["moved_in_at"])
    result = dish_calls(conn, origin, before=left_origin)
    for call in result["calls"]:
        call["source"] = "inherited"
    return {
        "fish_id": fish_id,
        "origin_dish_id": origin,
        "left_origin_at": left_origin,
        "status": result["status"],
        "calls": result["calls"],
    }
