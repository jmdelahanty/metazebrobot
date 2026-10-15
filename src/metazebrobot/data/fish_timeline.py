"""Assemble one fish's timeline from records MetaZebrobot owns.

docs/fish_timeline_design.md, step 1: origin and cross, inherited screening
calls, registration, moves between wells and dishes, and edits. Usage links
(recordings) and deaths are added in later steps. Read-only.

Every entry carries ``at`` as lab-local ``YYYY-MM-DDTHH:MM:SS`` (or a date for
day-precision facts), so entries from different tables sort together.
"""

from typing import Any, Dict, List, Optional

from .screening_calls import fish_calls, utc_to_lab_compact

_VIA_LABELS = {
    "web_form": "the web form",
    "web_batch": "web batch registration",
    "api": "the API",
    "tour": "the guided tour",
}
_DIFF_FIELDS = ("dish_id", "subject_label", "sex", "genotype", "species", "notes",
                "current_unit_id", "origin_dish_id")


def _iso(compact: Optional[str]) -> Optional[str]:
    """'YYYYMMDDTHH:MM:SS' or 'YYYYMMDD' -> 'YYYY-MM-DDTHH:MM:SS' / 'YYYY-MM-DD'."""
    if not compact:
        return None
    day = f"{compact[0:4]}-{compact[4:6]}-{compact[6:8]}"
    return f"{day}T{compact[9:17]}" if len(compact) > 8 else day


def _utc_iso(value: Optional[str]) -> Optional[str]:
    return _iso(utc_to_lab_compact(value))


def _entry(at, kind, summary, source, **details):
    return {"at": at, "kind": kind, "summary": summary, "source": source,
            "details": {k: v for k, v in details.items() if v is not None}}


def fish_timeline(conn, fish_id: str) -> Optional[Dict[str, Any]]:
    fish = conn.execute(
        """SELECT f.fish_id, f.dish_id, f.subject_label, f.current_unit_id, f.created_at,
                  f.revision, COALESCE(f.origin_dish_id, f.dish_id) AS origin_dish_id,
                  f.created_via, f.created_by
           FROM fish_subjects f WHERE f.fish_id = ?""",
        (fish_id,),
    ).fetchone()
    if not fish:
        return None
    fish = dict(fish)
    origin = conn.execute(
        "SELECT dish_id, cross_id, dof, date_created, genotype FROM dishes WHERE dish_id = ?",
        (fish["origin_dish_id"],),
    ).fetchone()
    entries: List[Dict[str, Any]] = []

    if origin and origin["dof"]:
        parents = [
            {"tank_id": r["tank_id"], "role": r["role"], "strain": r["raw_strain_name"]}
            for r in conn.execute(
                "SELECT tank_id, role, raw_strain_name FROM cross_parents "
                "WHERE cross_id = ? ORDER BY parent_index", (origin["cross_id"],)
            )
        ]
        entries.append(_entry(
            _iso(origin["dof"]), "fertilized",
            f"Fertilized; cross {origin['cross_id']}"
            + (": " + " × ".join(f"tank {p['tank_id']} ({p['role']}) {p['strain']}" for p in parents)
               if parents else ""),
            "dishes.dof, cross_parents",
            cross_id=origin["cross_id"], parents=parents or None,
        ))

    calls = fish_calls(conn, fish_id)
    for call in calls["calls"]:
        what = call["dish_construct"] if call["kind"] == "construct" else "pigment"
        entries.append(_entry(
            _iso(call["screening_datetime"]), "screening",
            f"{what}: {call['result']} ({call['confidence']}), screened in {call['established_in_dish']}"
            + (f" at {call['dpf']} dpf" if call.get("dpf") is not None else ""),
            "screening_steps, screening_step_allocations, screening_step_indicators",
            construct_key=call.get("construct_key"), result=call["result"],
            confidence=call["confidence"], dish_id=call["established_in_dish"], basis=call["basis"],
        ))

    revisions = [dict(r) for r in conn.execute(
        "SELECT * FROM fish_subject_revisions WHERE fish_id = ? ORDER BY revision", (fish_id,)
    )]
    # Revision 1 if history has it; else the earliest stored state (fish older
    # than the history table), whose dish is still where it was registered
    # unless it moved before history began.
    first = revisions[0] if revisions else {}
    registered_in = first.get("dish_id") or fish["dish_id"]
    entries.append(_entry(
        _utc_iso(fish["created_at"]), "registered",
        f"Registered as {fish['subject_label'] or fish_id[:8]} in dish {registered_in}"
        + ("" if first.get("kind") == "created" else " (dish as first recorded)")
        + f" via {_VIA_LABELS.get(fish['created_via'], fish['created_via'] or 'unknown means')}"
        + (f" by {fish['created_by']}" if fish["created_by"] else ""),
        "fish_subjects, fish_subject_revisions",
        dish_id=registered_in, origin_dish_id=fish["origin_dish_id"],
        created_via=fish["created_via"], created_by=fish["created_by"],
    ))

    for row in conn.execute(
        """SELECT o.unit_id, o.moved_in_at, o.moved_out_at, o.reason, u.dish_id, u.position_label
           FROM housing_unit_occupancy o LEFT JOIN housing_units u ON u.unit_id = o.unit_id
           WHERE o.fish_id = ? ORDER BY o.moved_in_at""",
        (fish_id,),
    ):
        entries.append(_entry(
            _utc_iso(row["moved_in_at"]), "placed",
            f"Placed in well {row['position_label'] or row['unit_id']} of dish {row['dish_id']}"
            + (f" ({row['reason']})" if row["reason"] else ""),
            "housing_unit_occupancy",
            unit_id=row["unit_id"], dish_id=row["dish_id"],
            moved_out_at=_utc_iso(row["moved_out_at"]),
        ))

    previous = None
    for rev in revisions:
        if previous is not None and rev["kind"] == "changed":
            changed = [f for f in _DIFF_FIELDS if rev.get(f) != previous.get(f)]
            if changed:
                entries.append(_entry(
                    _utc_iso(rev["recorded_at"]), "edited",
                    f"Revision {rev['revision']}: " + ", ".join(
                        f"{f} {previous.get(f)!r} → {rev.get(f)!r}" for f in changed),
                    "fish_subject_revisions",
                    revision=rev["revision"], fields=changed,
                ))
        previous = rev

    entries.sort(key=lambda e: e["at"] or "")
    return {
        "fish_id": fish_id,
        "subject_label": fish["subject_label"],
        "dish_id": fish["dish_id"],
        "current_unit_id": fish["current_unit_id"],
        "origin_dish_id": fish["origin_dish_id"],
        "revision": fish["revision"],
        "entries": entries,
        "not_yet_recorded": ["recordings (usage links)", "deaths"],
    }
