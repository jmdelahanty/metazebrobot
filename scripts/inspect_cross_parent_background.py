#!/usr/bin/env python
"""Inspect parent strain/background parsing for one cached PyRAT cross.

This is an exploratory script for designing the future ``cross_parents`` model.
It does not write to the database. It reads one row from ``crosses.data``,
prints the raw parent strain strings, and shows a conservative parsed view of
background strains, line labels, mutant/background flags, and transgenes.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from metazebrobot.utils.strain_parser import parse_strain_name  # noqa: E402
from metazebrobot.utils.pyrat_credentials import get_pyrat_api_credentials  # noqa: E402


KNOWN_BACKGROUNDS = {
    "AB",
    "WIK",
    "TU",
    "TUE",
    "TUEBINGEN",
    "TL",
    "EK",
}

KNOWN_MUTANT_BACKGROUNDS = {
    "casper": ["casper"],
    "nacre": ["nacre", "mitfa"],
    "roy": ["roy", "mpv17"],
}


def load_cross(db_path: Path, cross_id: str) -> Dict[str, Any]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT cross_id, line_strain, data FROM crosses WHERE cross_id = ?",
            (cross_id,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        raise SystemExit(f"Cross {cross_id} was not found in {db_path}")

    try:
        payload = json.loads(row["data"] or "{}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Cross {cross_id} has invalid JSON in crosses.data: {exc}") from exc

    payload.setdefault("crossing_id", row["cross_id"])
    if row["line_strain"] and not payload.get("strain_name"):
        payload["strain_name"] = row["line_strain"]
    return payload


def infer_parent_role(parent: Dict[str, Any]) -> str:
    males = int(parent.get("number_of_male") or 0)
    females = int(parent.get("number_of_female") or 0)
    if males and not females:
        return "male"
    if females and not males:
        return "female"
    if males and females:
        return "mixed"
    return "unknown"


def parent_location(parent: Dict[str, Any]) -> str:
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


def parse_background(raw_strain_name: str) -> Dict[str, Any]:
    """Conservatively parse non-transgene background hints from a strain string."""
    raw = raw_strain_name or ""
    tokens = [token for token in re.split(r"[^A-Za-z0-9_]+", raw) if token]
    token_upper = {token.upper() for token in tokens}
    token_lower = {token.lower() for token in tokens}

    backgrounds: List[str] = []
    for background in sorted(KNOWN_BACKGROUNDS):
        if background in token_upper:
            backgrounds.append(background)

    mutant_flags: List[str] = []
    for label, aliases in KNOWN_MUTANT_BACKGROUNDS.items():
        if any(
            alias.lower() == token or alias.lower() in token
            for alias in aliases
            for token in token_lower
        ):
            mutant_flags.append(label)

    transgenes = parse_strain_name(raw)

    line_labels: List[str] = []
    for token in tokens:
        upper = token.upper()
        lower = token.lower()
        if upper in KNOWN_BACKGROUNDS:
            continue
        if lower in {alias for aliases in KNOWN_MUTANT_BACKGROUNDS.values() for alias in aliases}:
            continue
        if token.startswith(("Tg", "Et", "Gt", "TgBAC")):
            continue
        if "_" in token or lower in {"casper", "nacre", "roy"}:
            line_labels.append(token)

    confidence = "raw"
    if backgrounds or mutant_flags or transgenes or line_labels:
        confidence = "inferred"

    return {
        "background_strains": backgrounds,
        "line_labels": line_labels,
        "mutant_backgrounds": mutant_flags,
        "transgenes": transgenes,
        "confidence": confidence,
    }


def inspect_cross(payload: Dict[str, Any]) -> Dict[str, Any]:
    parents = (payload.get("tanks") or {}).get("parents") or payload.get("parent_tanks") or []
    parsed_parents = []
    background_set = set()
    mutant_set = set()
    transgene_constructs: List[Dict[str, Any]] = []

    for index, parent in enumerate(parents, start=1):
        raw_strain = parent.get("strain_name") or parent.get("strain_name_with_id") or ""
        parsed = parse_background(raw_strain)
        background_set.update(parsed["background_strains"])
        mutant_set.update(parsed["mutant_backgrounds"])
        transgene_constructs.extend(parsed["transgenes"])
        parsed_parents.append({
            "parent_index": index,
            "role": infer_parent_role(parent),
            "tank_id": parent.get("tank_id"),
            "location_display": parent_location(parent),
            "raw_strain_name": raw_strain,
            "parsed": parsed,
            "raw_counts": {
                "male": parent.get("number_of_male"),
                "female": parent.get("number_of_female"),
                "unknown": parent.get("number_of_unknown"),
                "alive": parent.get("alive_count"),
            },
            "raw_parent_payload": parent,
        })

    cross_transgenes = parse_strain_name(payload.get("strain_name") or "")
    summary = {
        "cross_id": str(payload.get("crossing_id") or ""),
        "cross_status": payload.get("status"),
        "date_of_record": payload.get("date_of_record"),
        "date_of_set_up": payload.get("date_of_set_up"),
        "pyrat_responsible": payload.get("responsible_fullname"),
        "cross_strain_name": payload.get("strain_name"),
        "cross_level_transgenes": cross_transgenes,
        "parents": parsed_parents,
        "derived_background_summary": {
            "background_strains": sorted(background_set),
            "mutant_backgrounds": sorted(mutant_set),
            "has_mixed_background": len(background_set) > 1 or bool(background_set and mutant_set),
            "parent_background_pair": " x ".join(
                parent["raw_strain_name"] or "unknown" for parent in parsed_parents
            ),
            "parent_transgene_count": len(transgene_constructs),
        },
    }
    return summary


def fetch_live_tank_details(tank_ids: List[Any]) -> Dict[str, Dict[str, Any]]:
    """Fetch selected live tank fields, including generation, from PyRAT api/v3."""
    credentials = get_pyrat_api_credentials()
    if not credentials:
        raise RuntimeError("PyRAT API credentials are not configured")

    params: List[tuple[str, str]] = []
    for tank_id in tank_ids:
        if tank_id not in (None, ""):
            params.append(("tank_id", str(tank_id)))
    params.extend([
        ("l", str(max(len(tank_ids), 1))),
        ("k", "tank_id"),
        ("k", "strain_name"),
        ("k", "strain_name_with_id"),
        ("k", "generation"),
        ("k", "date_of_birth"),
        ("k", "number_of_male"),
        ("k", "number_of_female"),
        ("k", "number_of_unknown"),
        ("k", "location_rack_name"),
        ("k", "tank_position"),
    ])

    response = requests.get(
        credentials["base_url"].rstrip("/") + "/api/v3/tanks",
        auth=(credentials["client_token"], credentials["user_token"]),
        headers={"Accept": "application/json"},
        params=params,
        verify=False,
        timeout=20,
    )
    response.raise_for_status()
    return {str(item.get("tank_id")): item for item in response.json() if item.get("tank_id") is not None}


def add_live_tank_details(result: Dict[str, Any]) -> None:
    """Attach live tank detail records to parsed parents in-place."""
    tank_ids = [parent.get("tank_id") for parent in result.get("parents", [])]
    details = fetch_live_tank_details(tank_ids)
    for parent in result.get("parents", []):
        live = details.get(str(parent.get("tank_id")))
        if not live:
            continue
        parent["live_tank_details"] = live
        parent["generation"] = live.get("generation")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default="zebrobot.db", type=Path)
    parser.add_argument("--cross-id", default="18055")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    parser.add_argument(
        "--fetch-live-tank-details",
        action="store_true",
        help=(
            "Fetch live parent tank records from PyRAT api/v3/tanks. This can "
            "add generation, but current tank counts may differ from the counts "
            "recorded on the historical crossing payload."
        ),
    )
    args = parser.parse_args()

    payload = load_cross(args.db_path, args.cross_id)
    result = inspect_cross(payload)
    if args.fetch_live_tank_details:
        add_live_tank_details(result)
    indent = 2 if args.pretty else None
    print(json.dumps(result, indent=indent, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
