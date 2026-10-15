"""Assemble one fish's timeline from records MetaZebrobot owns.

docs/fish_timeline_design.md, step 1: origin and cross, inherited screening
calls, registration, moves between wells and dishes, and edits. Usage links
(recordings) and deaths are added in later steps. Read-only.

Every entry carries ``at`` as lab-local ``YYYY-MM-DDTHH:MM:SS`` (or a date for
day-precision facts), so entries from different tables sort together.
"""

from typing import Any, Dict, List, Optional

from datetime import datetime

from ..utils.lab_time import LAB_TIMEZONE
from .screening_calls import fish_calls, utc_to_lab_compact

_VIA_LABELS = {
    "web_form": "the web form",
    "web_batch": "web batch registration",
    "api": "the API",
    "tour": "the guided tour",
    "plate_setup": "plate setup",
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


def _rfc3339_to_lab_iso(value: Optional[str]) -> Optional[str]:
    """'...Z' (UTC) -> lab-local 'YYYY-MM-DDTHH:MM:SS'."""
    if not value:
        return None
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return instant.astimezone(LAB_TIMEZONE).strftime("%Y-%m-%dT%H:%M:%S")


def _sqlite_utc_to_norm(value: Optional[str]) -> Optional[str]:
    """'YYYY-MM-DD HH:MM:SS' (UTC) -> usage_links' normalized form."""
    return f"{value[:10]}T{value[11:19]}.000000Z" if value else None


def _dish_at(revisions: List[Dict[str, Any]], created_norm: Optional[str], instant: str) -> Optional[str]:
    """The fish's dish at a normalized UTC instant, from its revision history."""
    before = [r for r in revisions if _sqlite_utc_to_norm(r["recorded_at"]) <= instant]
    if before:
        return before[-1]["dish_id"]
    if revisions and created_norm and created_norm <= instant:
        return revisions[0]["dish_id"]
    return None


def _entry(at, kind, summary, source, **details):
    return {"at": at, "kind": kind, "summary": summary, "source": source,
            "details": {k: v for k, v in details.items() if v is not None}}


def fish_timeline(conn, fish_id: str) -> Optional[Dict[str, Any]]:
    fish = conn.execute(
        """SELECT f.fish_id, f.dish_id, f.subject_label, f.current_unit_id, f.created_at,
                  f.revision, COALESCE(f.origin_dish_id, f.dish_id) AS origin_dish_id,
                  f.created_via, f.created_by, f.status, f.ended_at, f.ended_precision,
                  f.end_reason, f.end_source, f.end_notes
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
        if call.get("source") == "observed":
            continue  # shown below as the observation itself
        what = call["dish_construct"] if call["kind"] == "construct" else "pigment"
        entries.append(_entry(
            _iso(call["screening_datetime"]), "screening",
            f"{what}: {call['result']} ({call['confidence']}), screened in {call['established_in_dish']}"
            + (f" at {call['dpf']} dpf" if call.get("dpf") is not None else ""),
            "screening_steps, screening_step_allocations, screening_step_indicators",
            construct_key=call.get("construct_key"), result=call["result"],
            confidence=call["confidence"], dish_id=call["established_in_dish"], basis=call["basis"],
        ))

    from .image_links import for_fish as fish_images
    for img in fish_images(conn, fish_id):
        entries.append(_entry(
            _utc_iso(img["file_mtime"]), "imaged",
            f"Imaged ({img['kind']})" + (f" in well {img['well_label']}" if img["well_label"] else "")
            + f": {img['name']}",
            "image_links",
            image_link_id=img["id"], rel_path=img["rel_path"], dish_id=img["dish_id"],
        ))

    from .fish_observations import all_for as all_observations
    for obs in all_observations(conn, fish_id):
        entries.append(_entry(
            _utc_iso(obs["observed_at"]), "observed",
            f"Observed {obs['dish_construct']}: {obs['result']}"
            + (f" (screening {obs['source_dish_id']})" if obs["source_dish_id"] else "")
            + (f" by {obs['observed_by']}" if obs["observed_by"] else "")
            + (f"; {obs['notes']}" if obs["notes"] else ""),
            "fish_screening_observations",
            dish_construct=obs["dish_construct"], construct_key=obs["construct_key"],
            result=obs["result"], source_dish_id=obs["source_dish_id"],
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

    try:
        own_links = [dict(r) for r in conn.execute(
            "SELECT * FROM usage_links WHERE fish_id = ? ORDER BY started_norm", (fish_id,))]
        dish_links = [dict(r) for r in conn.execute(
            "SELECT * FROM usage_links WHERE fish_id IS NULL ORDER BY started_norm")]
    except Exception:  # usage_links absent (older database)
        own_links, dish_links = [], []
    for link in own_links:
        where = f"rig {link['rig_id']} arena {link['arena_id']}"
        ref = link["recording_id"] or link["recording_ref"]
        end = (f", ended {_rfc3339_to_lab_iso(link['ended_at']).replace('T', ' ')} ({link['end_status']})"
               if link["ended_at"] else ", end not recorded yet")
        entries.append(_entry(
            _rfc3339_to_lab_iso(link["started_at"]), "recorded",
            f"Used in recording {ref} on {where}"
            + (f", taken from well {link['unit_id'].split(':')[-1]}" if link["unit_id"] else "")
            + end,
            "usage_links",
            recording_ref=link["recording_ref"], recording_id=link["recording_id"],
            rig_id=link["rig_id"], arena_id=link["arena_id"], unit_id=link["unit_id"],
            fish_revision=link["fish_revision"],
            ended_at=_rfc3339_to_lab_iso(link["ended_at"]), end_status=link["end_status"],
        ))
    created_norm = _sqlite_utc_to_norm(fish["created_at"])
    for link in dish_links:
        if _dish_at(revisions, created_norm, link["started_norm"]) != link["dish_id"]:
            continue
        entries.append(_entry(
            _rfc3339_to_lab_iso(link["started_at"]), "possibly_recorded",
            f"Possibly used in recording {link['recording_id'] or link['recording_ref']} on rig "
            f"{link['rig_id']} arena {link['arena_id']}: dish {link['dish_id']} was recorded"
            + (f" ({link['subject_count']} fish)" if link["subject_count"] else "")
            + " but no fish was named",
            "usage_links",
            recording_ref=link["recording_ref"], dish_id=link["dish_id"],
            subject_count=link["subject_count"],
        ))

    if fish["status"] and fish["status"] != "alive":
        at = (fish["ended_at"] if fish["ended_precision"] == "day"
              else _utc_iso(fish["ended_at"]))
        how = {"found_dead": "found dead", "euthanized": "euthanized",
               "propagated": "handed off alive (propagation)", "other": "died"}.get(
                   fish["end_reason"], fish["end_reason"])
        entries.append(_entry(
            at, "ended",
            f"{'Ended' if fish['status'] == 'propagated' else 'Died'}: {how}"
            + (" (with its dish's termination)" if fish["end_source"] == "dish_termination" else "")
            + (f"; {fish['end_notes']}" if fish["end_notes"] and fish["end_source"] == "fish" else ""),
            "fish_subjects",
            status=fish["status"], end_reason=fish["end_reason"],
            end_source=fish["end_source"], precision=fish["ended_precision"],
        ))

    entries.sort(key=lambda e: e["at"] or "")
    return {
        "fish_id": fish_id,
        "subject_label": fish["subject_label"],
        "dish_id": fish["dish_id"],
        "current_unit_id": fish["current_unit_id"],
        "origin_dish_id": fish["origin_dish_id"],
        "revision": fish["revision"],
        "entries": entries,
        "status": fish["status"],
        "not_yet_recorded": [],
    }
