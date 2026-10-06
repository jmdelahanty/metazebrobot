"""Derive a tank's heritage from cached PyRAT crossings.

Step 2a of docs/tank_heritage_design.md. Everything here reads the local cache
tables (``crosses``, ``cross_parents``, ``cross_children``); nothing calls
PyRAT. Each derived value says where it came from, and the aquatics strain
label (e.g. ``Casper_HHMI [AB-C IC] MAR26``) is parsed as a separate, lower-
confidence reading that is compared against the records, never preferred.

Background is a *set* of founder backgrounds (AB, WIK, casper, ...), not
proportions: ancestry is often incomplete, so proportions would overclaim.
"""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any, Dict, List, Optional

from .cross_provenance import parse_parent_background
from .tank_origins import origin_chain

MAX_GENERATIONS = 4

MONTHS = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04", "MAY": "05", "JUN": "06",
    "JUL": "07", "AUG": "08", "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12",
}

# Aquatics shorthand: "[AB-C]", "[WIK-C IC]", optionally followed by "MAR26".
LABEL_RE = re.compile(
    r"\[\s*(?P<background>[A-Za-z]+)-C(?P<incross>\s+IC)?\s*\]"
    r"(?:\s*(?P<month>[A-Za-z]{3})(?P<year>\d{2})\b)?"
)

def parse_strain_label(strain_name: Optional[str]) -> Optional[Dict[str, Any]]:
    """Parse the aquatics bracket shorthand, or None when the name has none.

    ``IC`` present means the label claims an incross. ``IC`` absent means the
    label says nothing about it (``[AB-C] DEC25`` came from an incross too),
    so ``incross`` is None rather than False.
    """
    match = LABEL_RE.search(strain_name or "")
    if not match:
        return None
    month = MONTHS.get((match.group("month") or "").upper())
    cohort_month = f"20{match.group('year')}-{month}" if month else None
    return {
        "backgrounds": [match.group("background").upper()],
        "mutant_backgrounds": ["casper"],
        "incross": True if match.group("incross") else None,
        "cohort_month": cohort_month,
    }


def _payload(raw: Optional[str]) -> Dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _list(raw: Optional[str]) -> List[str]:
    try:
        value = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    return value if isinstance(value, list) else []


def _tank_record(conn: sqlite3.Connection, tank_id: str) -> Dict[str, Any]:
    """Best-known strain/generation/DOB for a tank from any cached crossing."""
    record: Dict[str, Any] = {"tank_id": tank_id}
    child = conn.execute(
        "SELECT strain_id, strain_name, generation, date_of_birth FROM cross_children "
        "WHERE tank_id = ? ORDER BY updated_at DESC LIMIT 1",
        (tank_id,),
    ).fetchone()
    if child:
        record.update({k: child[k] for k in child.keys() if child[k] not in (None, "")})
    for row in conn.execute(
        "SELECT raw_strain_name, generation, raw_payload FROM cross_parents "
        "WHERE tank_id = ? ORDER BY updated_at DESC",
        (tank_id,),
    ):
        payload = _payload(row["raw_payload"])
        record.setdefault("strain_name", row["raw_strain_name"] or None)
        record.setdefault("generation", row["generation"] or None)
        for key in ("strain_id", "date_of_birth"):
            if payload.get(key) not in (None, ""):
                record.setdefault(key, payload[key])
    return {k: v for k, v in record.items() if v is not None}


def _cohort_month(date_of_birth: Optional[str]) -> Optional[str]:
    match = re.match(r"(\d{4})-(\d{2})", date_of_birth or "")
    return f"{match.group(1)}-{match.group(2)}" if match else None


def _producing_cross(conn: sqlite3.Connection, tank_id: str) -> Optional[Dict[str, Any]]:
    """The cross that produced a tank's fish, following recorded splits."""
    chain = origin_chain(conn, tank_id)
    row = conn.execute(
        "SELECT c.cross_id, x.data FROM cross_children c "
        "LEFT JOIN crosses x ON x.cross_id = c.cross_id "
        "WHERE c.tank_id = ? ORDER BY c.updated_at DESC LIMIT 1",
        (chain["origin_tank_id"],),
    ).fetchone()
    if not row:
        return None
    data = _payload(row["data"])
    parents = []
    for parent in conn.execute(
        "SELECT tank_id, raw_strain_name, generation, raw_payload, "
        "parsed_background_strains, parsed_mutant_alleles "
        "FROM cross_parents WHERE cross_id = ? ORDER BY parent_index",
        (row["cross_id"],),
    ):
        payload = _payload(parent["raw_payload"])
        parents.append({
            "tank_id": parent["tank_id"],
            "strain_name": parent["raw_strain_name"] or None,
            "strain_id": payload.get("strain_id"),
            "generation": parent["generation"] or None,
            "background_strains": _list(parent["parsed_background_strains"]),
            "mutant_backgrounds": _list(parent["parsed_mutant_alleles"]),
        })

    # One parent tank means its own males x females: an incross by definition.
    strains = [p["strain_id"] if p["strain_id"] is not None else p["strain_name"] for p in parents]
    if not parents or any(s in (None, "") for s in strains):
        cross_type = None
    else:
        cross_type = "incross" if len({str(s) for s in strains}) == 1 else "outcross"

    return {
        "cross_id": row["cross_id"],
        "date_of_set_up": data.get("date_of_set_up"),
        "parents": parents,
        "cross_type": cross_type,
        "origin_tank_id": chain["origin_tank_id"],
        "via_splits": chain["splits"],
    }


def _add(found: Dict[str, List[str]], values: List[str], source: str) -> None:
    for value in values:
        sources = found.setdefault(value, [])
        if source not in sources:
            sources.append(source)


def _collect_ancestry(
    conn: sqlite3.Connection,
    producing: Dict[str, Any],
    generation: int,
    backgrounds: Dict[str, List[str]],
    mutants: Dict[str, List[str]],
    seen_crosses: set,
) -> int:
    """Add parents' backgrounds, then their producing crosses', up to MAX_GENERATIONS.

    Returns how many generations back the walk reached.
    """
    if producing["cross_id"] in seen_crosses:
        return generation - 1
    seen_crosses.add(producing["cross_id"])
    if generation == 1:
        source = f"parents in cross {producing['cross_id']}"
    else:
        source = f"generation {generation} (cross {producing['cross_id']})"
    deepest = generation
    for parent in producing["parents"]:
        _add(backgrounds, parent["background_strains"], source)
        _add(mutants, parent["mutant_backgrounds"], source)
        if generation < MAX_GENERATIONS and parent["tank_id"]:
            earlier = _producing_cross(conn, str(parent["tank_id"]))
            if earlier:
                deepest = max(deepest, _collect_ancestry(
                    conn, earlier, generation + 1, backgrounds, mutants, seen_crosses))
    return deepest


def derive_tank_heritage(conn: sqlite3.Connection, tank_id: Any) -> Dict[str, Any]:
    """Heritage for one tank from the cache only (no PyRAT calls)."""
    tank_id = str(tank_id)
    tank = _tank_record(conn, tank_id)
    producing = _producing_cross(conn, tank_id)
    if "date_of_birth" not in tank:
        try:
            row = conn.execute(
                "SELECT date_of_birth FROM tank_origins WHERE tank_id = ?", (tank_id,)
            ).fetchone()
        except sqlite3.OperationalError:
            row = None
        if row and row["date_of_birth"]:
            tank["date_of_birth"] = row["date_of_birth"]
    label = parse_strain_label(tank.get("strain_name"))

    # Record-derived values (parents of the producing cross) are the answer.
    # Values read only from the tank's own strain name -- which for aquatics
    # cohorts *is* the label -- are kept separate and never merged in.
    backgrounds: Dict[str, List[str]] = {}
    mutants: Dict[str, List[str]] = {}
    generations_traced = 0
    if producing:
        generations_traced = _collect_ancestry(conn, producing, 1, backgrounds, mutants, set())
    own = parse_parent_background(tank.get("strain_name") or "")
    name_only = {
        "backgrounds": sorted(set(own["background_strains"]) - set(backgrounds)),
        "mutant_backgrounds": sorted(set(own["mutant_backgrounds"]) - set(mutants)),
    }

    cohort_month = _cohort_month(tank.get("date_of_birth"))
    checks: Dict[str, Optional[bool]] = {"incross": None, "cohort_month": None, "backgrounds": None}
    flags: List[str] = []
    if label:
        if label["incross"] and producing and producing["cross_type"]:
            checks["incross"] = producing["cross_type"] == "incross"
            if not checks["incross"]:
                flags.append(
                    f"label says incross (IC) but cross {producing['cross_id']} is an outcross"
                )
        if label["cohort_month"] and cohort_month:
            checks["cohort_month"] = label["cohort_month"] == cohort_month
            if not checks["cohort_month"]:
                flags.append(
                    f"label cohort {label['cohort_month']} but date of birth is {cohort_month}"
                )
        if producing:
            parent_backgrounds = {
                b for p in producing["parents"] for b in p["background_strains"]
            }
            if parent_backgrounds:
                checks["backgrounds"] = set(label["backgrounds"]) <= parent_backgrounds
                if not checks["backgrounds"]:
                    flags.append(
                        f"label background {', '.join(label['backgrounds'])} not found in "
                        f"parents of cross {producing['cross_id']}"
                    )

    return {
        "tank": tank,
        "cohort_month": cohort_month,
        "producing_cross": producing,
        "backgrounds": [{"value": k, "sources": v} for k, v in sorted(backgrounds.items())],
        "mutant_backgrounds": [{"value": k, "sources": v} for k, v in sorted(mutants.items())],
        "generations_traced": generations_traced,
        "name_only": name_only,
        "label": label,
        "label_checks": checks,
        "flags": flags,
    }
