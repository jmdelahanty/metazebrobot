"""Hand-entered cross parents PyRAT doesn't list (docs/manual_cross_parents_design.md).

Stored in cross_parents with source 'manual' and parent_index 101+, so PyRAT
refreshes (which replace only source 'pyrat' rows) keep them. Adding or
removing one re-derives the cross's dishes' constructs and step indicators.
"""

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

MANUAL_INDEX_START = 101
ROLES = ("dam", "sire", "unknown")


class ManualParentError(Exception):
    def __init__(self, status: int, detail: Dict[str, Any]):
        super().__init__(detail.get("error"))
        self.status = status
        self.detail = detail


def normalize_strain(text: str) -> str:
    """'UAS:ReaChR-TagRFPt' -> 'Tg(UAS:ReaChR-TagRFPt)'; anything else as typed."""
    text = (text or "").strip()
    if re.fullmatch(r"[^\s();]+:[^\s();]+", text):
        return f"Tg({text})"
    return text


def add(conn, cross_id: str, strain: str, reason: str, entered_by: Optional[str],
        tank_id: Optional[str] = None, role: str = "unknown",
        generation: Optional[str] = None) -> int:
    from ..utils.cross_provenance import parse_parent_background

    strain = normalize_strain(strain)
    reason = (reason or "").strip()
    if not strain:
        raise ManualParentError(422, {"error": "strain_required",
                                      "message": "Enter the parent's strain or genotype."})
    if not reason:
        raise ManualParentError(422, {"error": "reason_required",
                                      "message": "Say why PyRAT doesn't list this parent."})
    if role not in ROLES:
        raise ManualParentError(422, {"error": "invalid_role", "message": f"Role is one of {ROLES}."})
    if not conn.execute("SELECT 1 FROM crosses WHERE cross_id = ?", (cross_id,)).fetchone():
        raise ManualParentError(404, {"error": "cross_not_found", "cross_id": cross_id})
    parsed = parse_parent_background(strain)
    index = max(MANUAL_INDEX_START - 1, conn.execute(
        "SELECT COALESCE(MAX(parent_index), 0) FROM cross_parents WHERE cross_id = ?",
        (cross_id,)).fetchone()[0]) + 1
    payload = {"entered_by": entered_by, "reason": reason,
               "entered_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    conn.execute(
        """INSERT INTO cross_parents (
               cross_id, parent_index, role, tank_id, raw_strain_name, generation,
               parsed_background_strains, parsed_line_labels, parsed_transgenes,
               parsed_mutant_alleles, source, confidence, raw_payload, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'manual', 'entered', ?, CURRENT_TIMESTAMP)""",
        (cross_id, index, role, (tank_id or "").strip() or None, strain,
         (generation or "").strip().upper() or None,
         json.dumps(parsed["background_strains"]), json.dumps(parsed["line_labels"]),
         json.dumps(parsed["transgenes"]), json.dumps(parsed["mutant_backgrounds"]),
         json.dumps(payload)))
    return index


def remove(conn, cross_id: str, parent_index: int) -> None:
    cursor = conn.execute(
        "DELETE FROM cross_parents WHERE cross_id = ? AND parent_index = ? AND source = 'manual'",
        (cross_id, parent_index))
    if cursor.rowcount == 0:
        raise ManualParentError(404, {"error": "manual_parent_not_found", "cross_id": cross_id,
                                      "parent_index": parent_index})


def parents(conn, cross_id: str) -> List[Dict[str, Any]]:
    out = []
    for row in conn.execute(
            """SELECT parent_index, role, tank_id, raw_strain_name, generation, parsed_transgenes,
                      source, raw_payload FROM cross_parents WHERE cross_id = ?
               ORDER BY parent_index""", (cross_id,)):
        item = dict(row)
        item["transgenes"] = [t.get("construct") for t in json.loads(row["parsed_transgenes"] or "[]")]
        item["manual"] = row["source"] == "manual"
        item["entry"] = json.loads(row["raw_payload"] or "{}") if item["manual"] else {}
        out.append(item)
    return out


def refresh_dishes(conn, data_manager, cross_id: str) -> List[str]:
    """Re-derive constructs and step indicators for the cross's dishes."""
    dish_ids = []
    for row in conn.execute("SELECT dish_id, genotype, cross_id FROM dishes WHERE cross_id = ?",
                            (cross_id,)).fetchall():
        data_manager._save_dish_transgenes(conn, dict(row))
        data_manager.derive_step_indicators(conn, row["dish_id"])
        dish_ids.append(row["dish_id"])
    return dish_ids
