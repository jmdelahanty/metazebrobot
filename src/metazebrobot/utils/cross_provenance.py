"""Helpers for normalizing PyRAT cross parent provenance."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from ..data.data_manager import DataManager


KNOWN_BACKGROUNDS = {"AB", "WIK", "TU", "TUE", "TUEBINGEN", "TL", "EK"}
BACKGROUND_ALIASES = {"TUEBINGEN": "TU", "TUE": "TU"}
KNOWN_MUTANT_BACKGROUNDS = {
    "casper": ("casper",),
    "nacre": ("nacre", "mitfa"),
    "roy": ("roy", "mpv17"),
}


def parent_location_display(parent: Dict[str, Any]) -> str:
    """Build the same compact tank location label used in dish forms."""
    location = parent.get("location_display")
    if location:
        return str(location)
    tank_id = parent.get("tank_id")
    rack = parent.get("location_rack_name")
    position = parent.get("tank_position")
    if tank_id and rack and position:
        return f"#{tank_id}_{rack}>{position}"
    if parent.get("tank_label"):
        return str(parent["tank_label"])
    if tank_id:
        return f"#{tank_id}"
    return ""


def infer_parent_role(parent: Dict[str, Any]) -> str:
    """Infer parent role from parent-tank sex counts when PyRAT provides them."""
    males = int(parent.get("number_of_male") or 0)
    females = int(parent.get("number_of_female") or 0)
    if males and not females:
        return "male"
    if females and not males:
        return "female"
    if males and females:
        return "mixed"
    return "unknown"


def parse_parent_background(raw_strain_name: str) -> Dict[str, Any]:
    """Conservatively parse background and transgene hints from a parent strain."""
    raw = raw_strain_name or ""
    tokens = [token for token in re.split(r"[^A-Za-z0-9_]+", raw) if token]
    token_upper = {token.upper() for token in tokens}
    token_lower = {token.lower() for token in tokens}

    backgrounds = []
    for background in sorted(KNOWN_BACKGROUNDS):
        if background in token_upper:
            backgrounds.append(BACKGROUND_ALIASES.get(background, background))
    backgrounds = sorted(set(backgrounds))

    mutant_backgrounds = []
    for label, aliases in KNOWN_MUTANT_BACKGROUNDS.items():
        if any(alias.lower() == token or alias.lower() in token for alias in aliases for token in token_lower):
            mutant_backgrounds.append(label)

    transgenes = DataManager.parse_genotype(raw)

    line_labels = []
    known_alias_tokens = {
        alias.lower()
        for aliases in KNOWN_MUTANT_BACKGROUNDS.values()
        for alias in aliases
    }
    for token in tokens:
        upper = token.upper()
        lower = token.lower()
        if upper in KNOWN_BACKGROUNDS:
            continue
        if lower in known_alias_tokens:
            continue
        if token.startswith(("Tg", "Et", "Gt", "TgBAC")):
            continue
        if "_" in token or lower in {"casper", "nacre", "roy"}:
            line_labels.append(token)

    confidence = "inferred" if backgrounds or mutant_backgrounds or transgenes or line_labels else "raw"
    return {
        "background_strains": backgrounds,
        "line_labels": sorted(set(line_labels)),
        "mutant_backgrounds": sorted(set(mutant_backgrounds)),
        "transgenes": transgenes,
        "confidence": confidence,
    }


def parent_tanks_from_cross(cross_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return parent tanks from the known PyRAT crossing payload shapes."""
    parents = cross_payload.get("parent_tanks")
    if not parents:
        parents = (cross_payload.get("tanks") or {}).get("parents") or []
    return [parent for parent in parents if isinstance(parent, dict)]


def normalize_cross_parents(cross_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalize one PyRAT crossing payload into per-parent provenance rows."""
    rows = []
    for index, parent in enumerate(parent_tanks_from_cross(cross_payload), start=1):
        raw_strain = parent.get("strain_name") or parent.get("strain_name_with_id") or ""
        parsed = parse_parent_background(raw_strain)
        rows.append({
            "parent_index": index,
            "role": infer_parent_role(parent),
            "tank_id": parent.get("tank_id"),
            "tank_label": parent.get("tank_label"),
            "location_display": parent_location_display(parent),
            "raw_strain_name": raw_strain,
            "generation": parent.get("generation"),
            "parsed_background_strains": parsed["background_strains"],
            "parsed_line_labels": parsed["line_labels"],
            "parsed_transgenes": parsed["transgenes"],
            "parsed_mutant_alleles": parsed["mutant_backgrounds"],
            "confidence": parsed["confidence"],
            "raw_payload": parent,
        })
    return rows


def summarize_cross_background(parent_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build a compact derived summary from normalized parent rows."""
    backgrounds = sorted({
        item
        for row in parent_rows
        for item in row.get("parsed_background_strains", [])
    })
    line_labels = sorted({
        item
        for row in parent_rows
        for item in row.get("parsed_line_labels", [])
    })
    mutant_backgrounds = sorted({
        item
        for row in parent_rows
        for item in row.get("parsed_mutant_alleles", [])
    })
    transgenes = [
        item
        for row in parent_rows
        for item in row.get("parsed_transgenes", [])
    ]

    label_parts = backgrounds + line_labels + mutant_backgrounds
    summary = " + ".join(label_parts)
    return {
        "background_summary": summary,
        "background_strains": backgrounds,
        "line_labels": line_labels,
        "mutant_backgrounds": mutant_backgrounds,
        "transgenes": transgenes,
        "has_mixed_background": len(backgrounds) > 1 or bool(backgrounds and (line_labels or mutant_backgrounds)),
    }
