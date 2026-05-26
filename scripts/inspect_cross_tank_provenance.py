#!/usr/bin/env python
"""Inspect PyRAT tank provenance for parents of a cached cross.

This exploratory script reads a cross from local ``crosses.data``, extracts
parent tank IDs, then uses PyRAT api/v3 to fetch live tank summaries and tank
history. It follows source/copy/destination relations in history events to a
bounded depth and emits a JSON graph.

The output is provenance, not guaranteed genetic pedigree. PyRAT history events
can show tank release, split/separate/copy/move/crossing involvement, but those
relations may describe husbandry operations rather than parentage.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import deque
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import requests
import urllib3


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from metazebrobot.utils.pyrat_credentials import get_pyrat_api_credentials  # noqa: E402


TANK_SUMMARY_FIELDS = [
    "tank_id",
    "tank_label",
    "tank_type",
    "tank_position",
    "location_rack_name",
    "location_room_name",
    "status",
    "responsible_id",
    "responsible_fullname",
    "strain_name",
    "strain_name_with_id",
    "mutations",
    "origin_name",
    "generation",
    "age_level",
    "genetic_background_name",
    "classification_name",
    "number_of_male",
    "number_of_female",
    "number_of_unknown",
    "alive_count",
    "date_of_birth",
    "date_of_release",
    "close_date",
    "sacrifice_date",
]

EVENT_SUMMARY_FIELDS = [
    "event_id",
    "event_date",
    "event_type_name",
    "event_actor_username",
    "event_comment",
    "number_of_male",
    "number_of_female",
    "number_of_unknown",
    "related",
    "changes",
]

SOURCE_EDGE_EVENTS = {
    "SeparateEvent",
    "ReleaseEvent",
    "MoveAnimalEvent",
}


def load_cross_payload(db_path: Path, cross_id: str) -> Dict[str, Any]:
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


def cached_parent_tanks(cross_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list((cross_payload.get("tanks") or {}).get("parents") or [])


def location_label(tank: Dict[str, Any]) -> str:
    tank_id = tank.get("tank_id")
    rack = tank.get("location_rack_name")
    position = tank.get("tank_position")
    if tank_id and rack and position:
        return f"#{tank_id}_{rack}>{position}"
    if tank.get("tank_label"):
        return str(tank["tank_label"])
    if tank_id:
        return f"#{tank_id}"
    return ""


def compact_event(event: Dict[str, Any]) -> Dict[str, Any]:
    return {key: event.get(key) for key in EVENT_SUMMARY_FIELDS if key in event}


def relation_label(related_item: Dict[str, Any]) -> str:
    return related_item.get("relation") or "related"


class PyRATClient:
    def __init__(self) -> None:
        credentials = get_pyrat_api_credentials()
        if not credentials:
            raise SystemExit("PyRAT API credentials are not configured")
        self.base_url = credentials["base_url"].rstrip("/") + "/api/v3/"
        self.auth = (credentials["client_token"], credentials["user_token"])
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def get_tanks(self, tank_ids: Iterable[Any]) -> Dict[str, Dict[str, Any]]:
        ids = [str(tank_id) for tank_id in tank_ids if tank_id not in (None, "")]
        if not ids:
            return {}
        params: List[Tuple[str, str]] = []
        for tank_id in ids:
            params.append(("tank_id", tank_id))
        params.append(("l", str(len(ids))))
        for field in TANK_SUMMARY_FIELDS:
            params.append(("k", field))

        response = self.session.get(
            self.base_url + "tanks",
            auth=self.auth,
            params=params,
            verify=False,
            timeout=20,
        )
        response.raise_for_status()
        return {
            str(item.get("tank_id")): item
            for item in response.json()
            if item.get("tank_id") is not None
        }

    def get_tank_history(self, tank_id: Any) -> List[Dict[str, Any]]:
        response = self.session.get(
            self.base_url + f"tanks/{tank_id}/history",
            auth=self.auth,
            verify=False,
            timeout=20,
        )
        response.raise_for_status()
        return response.json()


def edge_direction(
    current_tank_id: str,
    event: Dict[str, Any],
    related: Dict[str, Any],
) -> Optional[str]:
    """Return relationship direction from an event relative to current tank."""
    other_tank_id = str(related.get("tank_id"))
    if not other_tank_id or other_tank_id == current_tank_id:
        return None

    relation = related.get("relation")
    event_type = event.get("event_type_name")
    if event_type not in SOURCE_EDGE_EVENTS:
        return None

    # A source relation points from the related tank into the current tank.
    if relation == "source":
        return "source_of_current"
    if relation == "destination":
        return "destination_from_current"
    if relation == "copy":
        return "copy_related_to_current"
    return "related_to_current"


def build_provenance_graph(
    client: PyRATClient,
    root_tank_ids: List[Any],
    max_depth: int,
    max_history_events: int,
) -> Dict[str, Any]:
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []
    histories: Dict[str, List[Dict[str, Any]]] = {}

    queue = deque((str(tank_id), 0) for tank_id in root_tank_ids if tank_id not in (None, ""))
    queued: Set[str] = {tank_id for tank_id, _ in queue}

    while queue:
        tank_id, depth = queue.popleft()
        if tank_id in nodes and histories.get(tank_id) is not None:
            continue

        tank_details = client.get_tanks([tank_id]).get(tank_id, {"tank_id": int(tank_id)})
        nodes[tank_id] = {
            "tank_id": tank_details.get("tank_id"),
            "depth": depth,
            "location_display": location_label(tank_details),
            "strain_name": tank_details.get("strain_name") or tank_details.get("strain_name_with_id"),
            "strain_name_with_id": tank_details.get("strain_name_with_id"),
            "generation": tank_details.get("generation"),
            "origin_name": tank_details.get("origin_name"),
            "date_of_birth": tank_details.get("date_of_birth"),
            "date_of_release": tank_details.get("date_of_release"),
            "status": tank_details.get("status"),
            "counts": {
                "male": tank_details.get("number_of_male"),
                "female": tank_details.get("number_of_female"),
                "unknown": tank_details.get("number_of_unknown"),
                "alive": tank_details.get("alive_count"),
            },
            "raw_tank": tank_details,
        }

        history = client.get_tank_history(tank_id)
        histories[tank_id] = [compact_event(event) for event in history[:max_history_events]]

        if depth >= max_depth:
            continue

        for event in history:
            related = event.get("related") or []
            if not isinstance(related, list):
                continue
            for item in related:
                if not isinstance(item, dict):
                    continue
                other_tank_id = item.get("tank_id")
                if other_tank_id in (None, ""):
                    continue
                other_tank_id = str(other_tank_id)
                direction = edge_direction(tank_id, event, item)
                if not direction:
                    continue
                edge = {
                    "from_tank_id": other_tank_id,
                    "to_tank_id": tank_id,
                    "relation": relation_label(item),
                    "direction": direction,
                    "event_id": event.get("event_id"),
                    "event_type_name": event.get("event_type_name"),
                    "event_date": event.get("event_date"),
                    "event_comment": event.get("event_comment"),
                    "changes": event.get("changes") or {},
                }
                if direction == "destination_from_current":
                    edge["from_tank_id"] = tank_id
                    edge["to_tank_id"] = other_tank_id
                edges.append(edge)
                if direction == "source_of_current" and other_tank_id not in queued:
                    queue.append((other_tank_id, depth + 1))
                    queued.add(other_tank_id)

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "histories": histories,
        "notes": [
            "Edges are inferred from PyRAT tank history related[] entries.",
            "This graph represents tank provenance/husbandry relations, not guaranteed genetic pedigree.",
            "Crossing payload parent counts may differ from live tank counts.",
        ],
    }


def print_text_summary(result: Dict[str, Any]) -> None:
    cross = result["cross"]
    graph = result["provenance_graph"]
    print(
        f"Cross {cross['cross_id']} ({cross.get('strain_name') or 'unknown strain'}) "
        f"set up {cross.get('date_of_set_up') or cross.get('date_of_record') or 'unknown date'}"
    )
    print(f"PyRAT responsible: {cross.get('responsible_fullname') or 'unknown'}")
    print()

    root_ids = {str(tank_id) for tank_id in result["root_parent_tank_ids"]}
    nodes_by_id = {str(node["tank_id"]): node for node in graph["nodes"]}
    print("Root parent tanks:")
    for tank_id in result["root_parent_tank_ids"]:
        node = nodes_by_id.get(str(tank_id), {})
        print(
            f"- {tank_id}: {node.get('strain_name') or 'unknown strain'}, "
            f"{node.get('generation') or 'unknown generation'}, "
            f"{node.get('location_display') or ''}, "
            f"DOB {node.get('date_of_birth') or 'unknown'}"
        )

    print()
    print("Provenance/source edges:")
    edges = graph["edges"]
    if not edges:
        print("- none found")
    for edge in edges:
        source = edge["from_tank_id"]
        target = edge["to_tank_id"]
        source_node = nodes_by_id.get(str(source), {})
        target_marker = "parent" if str(target) in root_ids else "related"
        print(
            f"- {source} -> {target} ({target_marker}): "
            f"{edge.get('event_type_name')} {edge.get('event_date')}; "
            f"relation={edge.get('relation')}; "
            f"source strain={source_node.get('strain_name') or 'unknown'}; "
            f"comment={edge.get('event_comment') or ''}"
        )

    print()
    print("Notes:")
    for note in graph["notes"]:
        print(f"- {note}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default="zebrobot.db", type=Path)
    parser.add_argument("--cross-id", default="18055")
    parser.add_argument("--max-depth", type=int, default=1)
    parser.add_argument("--max-history-events", type=int, default=12)
    parser.add_argument("--format", choices=("json", "text"), default="json")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    payload = load_cross_payload(args.db_path, args.cross_id)
    parents = cached_parent_tanks(payload)
    parent_tank_ids = [parent.get("tank_id") for parent in parents if parent.get("tank_id")]
    client = PyRATClient()
    graph = build_provenance_graph(
        client,
        parent_tank_ids,
        max_depth=max(args.max_depth, 0),
        max_history_events=max(args.max_history_events, 0),
    )

    result = {
        "cross": {
            "cross_id": str(payload.get("crossing_id") or args.cross_id),
            "status": payload.get("status"),
            "date_of_record": payload.get("date_of_record"),
            "date_of_set_up": payload.get("date_of_set_up"),
            "responsible_fullname": payload.get("responsible_fullname"),
            "strain_name": payload.get("strain_name"),
        },
        "cached_cross_parent_tanks": parents,
        "root_parent_tank_ids": parent_tank_ids,
        "provenance_graph": graph,
    }
    if args.format == "text":
        print_text_summary(result)
    else:
        print(json.dumps(result, indent=2 if args.pretty else None, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
